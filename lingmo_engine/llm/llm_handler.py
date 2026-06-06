"""LLM 统一请求处理器 — 封装流式/非流式调用、并发控制。"""
from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable, Awaitable
from dataclasses import dataclass, field

from lingmo_engine.core.types import ToolDefinition
from lingmo_engine.llm.base_provider import BaseLLMProvider, LLMResponse, ToolCall

logger = logging.getLogger(__name__)


class LLMBusyError(Exception):
    """当前有 LLM 请求正在进行中，拒绝新请求。"""


@dataclass
class StreamResult:
    """流式请求的完整结果。"""
    narrative_text: str = ""       # 完整叙述文本（等同于 full_text）
    full_text: str = ""            # LLM 原始输出全文
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    reasoning_content: str | None = None  # 模型的思维链/推理内容
    prompt_tokens: int = 0          # 输入 token 数量
    completion_tokens: int = 0     # 输出 token 数量
    cached_tokens: int = 0         # 缓存 token 数量


class LLMHandler:
    """LLM 统一请求处理器。

    职责：
    - 封装流式和非流式 LLM 调用
    - 并发互斥（asyncio.Lock）：同时只允许一个请求
    - 锁获取/释放时通知外部（如锁定前端输入）
    - 流式模式下通过 on_chunk 回调发射文本块（直通，不解析标签）
    """

    def __init__(
        self,
        provider: BaseLLMProvider,
        fast_provider: BaseLLMProvider | None = None,
        *,
        on_lock_acquire: Callable[[], Awaitable[None]] | None = None,
        on_lock_release: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._strong_provider = provider
        self._fast_provider = fast_provider or provider
        self._provider = provider  # 默认（向后兼容）
        self._lock = threading.Lock()
        self._cancel_event: threading.Event | None = None
        self._on_lock_acquire = on_lock_acquire
        self._on_lock_release = on_lock_release
        # 由 _acquire 在持锁时设置，仅供同一请求的 _release 使用。
        # 单锁保证 _acquire/_release 之间无并发调用。
        self._main_loop: asyncio.AbstractEventLoop | None = None

    async def _acquire(self) -> None:
        """获取锁并通知外部。"""
        if not self._lock.acquire(blocking=False):
            raise LLMBusyError("当前有 LLM 请求正在进行中，请等待完成后再试")
        # 记录主事件循环引用，供 _release 跨线程回调使用
        self._main_loop = asyncio.get_running_loop()
        if self._on_lock_acquire:
            try:
                await self._on_lock_acquire()
            except Exception:
                logger.warning("on_lock_acquire 回调失败", exc_info=True)

    def _release(self) -> None:
        """释放锁并通知外部。支持在主循环或工具线程中调用。"""
        self._lock.release()
        if self._on_lock_release:
            try:
                coro = self._on_lock_release()
                if asyncio.iscoroutine(coro):
                    loop = self._main_loop
                    if loop and loop.is_running():
                        asyncio.ensure_future(coro, loop=loop)
                    elif loop:
                        loop.call_soon_threadsafe(lambda: asyncio.ensure_future(coro, loop=loop))
            except RuntimeError:
                logger.debug("on_lock_release: 无可用事件循环，跳过回调")
            except Exception:
                logger.warning("on_lock_release 回调失败", exc_info=True)

    @property
    def is_busy(self) -> bool:
        return self._lock.locked()

    def cancel(self) -> None:
        """取消当前正在进行的 LLM 请求。"""
        if self._cancel_event is not None:
            self._cancel_event.set()
            logger.info("LLMHandler: 取消信号已发送")

    def update_strong_provider(self, new_provider: BaseLLMProvider) -> None:
        """更新强推理 Provider。"""
        self._strong_provider = new_provider
        self._provider = new_provider
        logger.info("LLMHandler strong provider updated: %s", new_provider.config.model)

    @property
    def strong_provider(self) -> BaseLLMProvider:
        return self._strong_provider

    @property
    def fast_provider(self) -> BaseLLMProvider:
        return self._fast_provider

    def update_fast_provider(self, new_provider: BaseLLMProvider) -> None:
        """更新快推理 Provider。"""
        self._fast_provider = new_provider
        logger.info("LLMHandler fast provider updated: %s", new_provider.config.model)

    def update_provider(self, new_provider: BaseLLMProvider) -> None:
        """向后兼容：同时更新强推理 Provider。"""
        self.update_strong_provider(new_provider)

    async def request_stream(
        self,
        messages: list[dict],
        tools: list[ToolDefinition] | None,
        *,
        on_chunk: Callable[[str, str], Awaitable[None]],
        stream_type: str = "narrative",
        mode: str = "strong",
        thinking: bool | None = None,
    ) -> StreamResult | None:
        """流式请求 LLM。

        Args:
            messages: 消息列表
            tools: 工具定义列表（可为 None）
            on_chunk: 每个文本块的回调 (text, stream_type) -> awaitable
            stream_type: 流类型标识，透传给回调 ("narrative" 或 "combat_narrative")
            mode: 推理模式 "strong"(默认) 或 "fast"
            thinking: 是否启用思维链（None 为不干预）

        Returns:
            StreamResult | None: 被取消时返回 None

        Raises:
            LLMBusyError: 当前有请求正在进行中
        """
        provider = self._fast_provider if mode == "fast" else self._strong_provider

        await self._acquire()
        try:
            try:
                return await self._run_stream_impl(
                    provider, messages, tools, thinking, on_chunk, stream_type,
                )
            except Exception:
                if mode != "fast":
                    raise
                logger.warning("快推理流式请求失败，回退到强推理", exc_info=True)
                return await self._run_stream_impl(
                    self._strong_provider, messages, tools, thinking, on_chunk, stream_type,
                )
        finally:
            self._release()

    async def _run_stream_impl(
        self,
        provider: BaseLLMProvider,
        messages: list[dict],
        tools: list[ToolDefinition] | None,
        thinking: bool | None,
        on_chunk: Callable[[str, str], Awaitable[None]],
        stream_type: str,
    ) -> StreamResult | None:
        """流式请求的内部实现。"""
        full_text = ""
        reasoning_content = ""
        final_tool_calls = None
        finish_reason = None
        prompt_tokens = 0
        completion_tokens = 0
        cached_tokens = 0
        _thinking_started = False
        _thinking_ended = False
        self._cancel_event = threading.Event()

        event_queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _run_stream() -> None:
            try:
                for event in provider.chat_stream(messages, tools, thinking=thinking):
                    if self._cancel_event.is_set():
                        break
                    asyncio.run_coroutine_threadsafe(
                        event_queue.put(event), loop
                    )
                asyncio.run_coroutine_threadsafe(
                    event_queue.put(None), loop
                )
            except Exception as exc:
                asyncio.run_coroutine_threadsafe(
                    event_queue.put(exc), loop
                )

        executor_future = loop.run_in_executor(None, _run_stream)

        try:
            while True:
                if self._cancel_event.is_set():
                    logger.info("LLMHandler: 流式请求被取消")
                    break
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    if executor_future.done():
                        exc = executor_future.exception()
                        if exc is not None:
                            raise exc
                    continue
                if event is None:
                    break
                if isinstance(event, Exception):
                    raise event
                if event.reasoning_delta:
                    reasoning_content += event.reasoning_delta
                    if not _thinking_started:
                        await on_chunk("<thinking>\n", stream_type)
                        _thinking_started = True
                    await on_chunk(event.reasoning_delta, stream_type)
                if event.text_delta:
                    if _thinking_started and not _thinking_ended:
                        await on_chunk("\n</thinking>\n", stream_type)
                        _thinking_ended = True
                    full_text += event.text_delta
                    await on_chunk(event.text_delta, stream_type)
                    await asyncio.sleep(0.03)
                if event.tool_calls is not None:
                    final_tool_calls = event.tool_calls
                if event.finish_reason is not None:
                    if _thinking_started and not _thinking_ended:
                        await on_chunk("\n</thinking>\n", stream_type)
                        _thinking_ended = True
                    finish_reason = event.finish_reason
                    prompt_tokens += event.prompt_tokens
                    completion_tokens += event.completion_tokens
                    cached_tokens += event.cached_tokens
        finally:
            cancelled = self._cancel_event is not None and self._cancel_event.is_set()
            self._cancel_event = None

        if cancelled:
            return None

        return StreamResult(
            narrative_text=full_text,
            full_text=full_text,
            tool_calls=final_tool_calls or [],
            finish_reason=finish_reason or "stop",
            reasoning_content=reasoning_content or None,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
        )

    async def request(
        self,
        messages: list[dict],
        tools: list[ToolDefinition] | None = None,
        *,
        wait: bool = False,
        timeout: float = 60.0,
        mode: str = "strong",
        thinking: bool | None = None,
    ) -> LLMResponse | None:
        """非流式请求 LLM。

        Args:
            wait: 为 True 时等待锁释放而非立即抛异常（适合后台任务）
            timeout: wait=True 时的最大等待秒数
            mode: 推理模式 "strong"(默认) 或 "fast"
            thinking: 是否启用思维链（None 为不干预）

        Returns:
            LLMResponse | None: 被取消时返回 None

        Raises:
            LLMBusyError: 当前有请求正在进行中（仅 wait=False）
            asyncio.TimeoutError: 等待锁超时（仅 wait=True）
        """
        provider = self._fast_provider if mode == "fast" else self._strong_provider

        if wait:
            # wait=True 时循环尝试获取锁
            import time
            deadline = time.monotonic() + timeout
            while not self._lock.acquire(blocking=False):
                if time.monotonic() >= deadline:
                    raise asyncio.TimeoutError("等待 LLM 锁超时")
                await asyncio.sleep(0.1)
            self._main_loop = asyncio.get_running_loop()
            if self._on_lock_acquire:
                try:
                    await self._on_lock_acquire()
                except Exception:
                    logger.warning("on_lock_acquire 回调失败", exc_info=True)
        else:
            if not self._lock.acquire(blocking=False):
                raise LLMBusyError("当前有 LLM 请求正在进行中，请等待完成后再试")
            self._main_loop = asyncio.get_running_loop()
            if self._on_lock_acquire:
                try:
                    await self._on_lock_acquire()
                except Exception:
                    logger.warning("on_lock_acquire 回调失败", exc_info=True)

        try:
            self._cancel_event = threading.Event()
            try:
                result = await self._request_with_fallback(provider, messages, tools, thinking, mode)
                if self._cancel_event.is_set():
                    logger.info("LLMHandler: 非流式请求被取消，丢弃结果")
                    return None
                return result
            finally:
                self._cancel_event = None
        finally:
            self._release()

    async def _request_with_fallback(
        self,
        provider: BaseLLMProvider,
        messages: list[dict],
        tools: list[ToolDefinition] | None,
        thinking: bool | None,
        mode: str,
    ) -> LLMResponse:
        """非流式请求，快推理失败时回退到强推理。"""
        try:
            return await asyncio.to_thread(
                provider.chat, messages, tools, thinking=thinking,
            )
        except Exception:
            if mode != "fast":
                raise
            logger.warning("快推理 Provider 失败，回退到强推理", exc_info=True)
            return await asyncio.to_thread(
                self._strong_provider.chat, messages, tools, thinking=thinking,
            )
