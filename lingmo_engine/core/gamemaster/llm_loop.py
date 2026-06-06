"""LLM 循环执行器 — 流式/非流式请求、工具执行、叙事终结。"""
from __future__ import annotations

import json
import logging
import re
from collections import deque
from html.parser import HTMLParser
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from lingmo_engine.core.message import Message, MessageMeta
from lingmo_engine.core.message_bus import MessageEvent
from lingmo_engine.core.types import ToolDefinition
from lingmo_engine.core.gamemaster.text_utils import (
    serialize_messages_for_meta,
)

if TYPE_CHECKING:
    from lingmo_engine.core.gamemaster.game_master import GameMaster

logger = logging.getLogger(__name__)

_token_log_dir: Path | None = None
_token_log_enabled: bool = True


def set_token_log_dir(path: Path) -> None:
    """设置 token 日志目录。"""
    global _token_log_dir
    _token_log_dir = path
    _token_log_dir.mkdir(parents=True, exist_ok=True)


def set_token_log_enabled(enabled: bool) -> None:
    """控制是否写入 token 统计日志。"""
    global _token_log_enabled
    _token_log_enabled = enabled


def _write_token_log(record: dict) -> None:
    """追加一条 token 统计记录到 JSONL 日志。"""
    if not _token_log_enabled or _token_log_dir is None:
        return
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = _token_log_dir / f"token_{today}.jsonl"
    record["timestamp"] = datetime.now().isoformat()
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


class _PNarrativeFixer(HTMLParser):
    """修复 LLM 输出的 HTML：提取 <p> 段落文本，处理未闭合/多余标签。

    返回修复后的 HTML 字符串（每个段落用 <p> 包裹），
    以及纯文本字数（去空白后）用于安全网判断。
    """

    def __init__(self) -> None:
        super().__init__()
        self._paragraphs: list[str] = []
        self._current: list[str] = []
        self._in_p = 0
        self._thinking_depth = 0

    # 允许透传到输出的内联标签（不破坏段落结构）
    _INLINE_TAGS = frozenset({"em", "strong", "b", "i"})

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "p":
            self._in_p += 1
        elif tag == "thinking":
            self._thinking_depth += 1
        elif tag in self._INLINE_TAGS and self._in_p > 0:
            self._current.append(self.get_starttag_text())

    def handle_endtag(self, tag: str) -> None:
        if tag == "p" and self._in_p > 0:
            self._in_p -= 1
            if self._in_p == 0:
                self._paragraphs.append("".join(self._current))
                self._current = []
        elif tag == "thinking" and self._thinking_depth > 0:
            self._thinking_depth -= 1
        elif tag in self._INLINE_TAGS and self._in_p > 0:
            self._current.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._thinking_depth > 0:
            return
        if self._in_p > 0:
            self._current.append(data)

    def close(self) -> None:
        super().close()
        # 处理未闭合的 <p>：将残余内容作为最后一个段落
        if self._current:
            self._paragraphs.append("".join(self._current))
            self._current = []

    @property
    def fixed_html(self) -> str:
        return "".join(f"<p>{t}</p>" for t in self._paragraphs if t.strip())

    @property
    def core_text(self) -> str:
        return re.sub(r"\s", "", "".join(self._paragraphs))

    @property
    def core_len(self) -> int:
        return len(self.core_text)


def _fix_narrative_html(text: str) -> tuple[str, int]:
    """修复叙事 HTML，返回 (修复后HTML, 正文纯字数)。"""
    if not text:
        return "", 0
    # 先剥离 <thinking> 块（外层已做，但防御性保留）
    cleaned = re.sub(r"<thinking>.*?</thinking>\s*", "", text, flags=re.DOTALL)
    fixer = _PNarrativeFixer()
    fixer.feed(cleaned)
    fixer.close()
    return fixer.fixed_html, fixer.core_len


class LLMLoopRunner:
    """封装 LLM 请求、工具执行和叙事终结逻辑。"""

    def __init__(self, gm: "GameMaster") -> None:
        self._gm = gm
        self._reasoning_history: deque[str] = deque(maxlen=5)

    def _build_reasoning_bridge(self) -> str:
        """将历史推理内容构建为桥接提示词。"""
        if not self._reasoning_history:
            return ""
        total = len(self._reasoning_history)
        parts: list[str] = []
        for i, rc in enumerate(self._reasoning_history, 1):
            label = "最新思考" if i == total else f"过往思考({i}/{total})"
            parts.append(f"【{label}】\n{rc[:2000]}")
        return f"[近期思考记录（共{total}条）]\n" + "\n\n".join(parts)

    # ── 公共入口 ──────────────────────────────────

    async def run(
        self, messages: list[dict], tools: list[ToolDefinition],
        stream_type: str = "narrative", page_id: str = "",
        max_rounds: int = 10,
    ) -> None:
        """运行 LLM 循环。"""
        token_accum = {"prompt": 0, "completion": 0, "cached": 0, "llm_calls": 0}
        try:
            await self._run_impl(
                messages, tools, stream_type, page_id, max_rounds,
                token_accum=token_accum,
            )
        finally:
            prompt = token_accum["prompt"]
            completion = token_accum["completion"]
            cached = token_accum["cached"]
            calls = token_accum["llm_calls"]
            total = prompt + completion
            cache_pct = cached / prompt * 100 if prompt > 0 and cached > 0 else 0
            logger.info(
                "[Page %s] Token统计: 输入=%d%s 输出=%d 总计=%d | LLM调用=%d次",
                page_id[:8] if page_id else "?", prompt,
                f"(缓存={cached},{cache_pct:.1f}%)" if cached > 0 else "",
                completion, total, calls,
            )
            _write_token_log({
                "page_id": page_id,
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "cached_tokens": cached,
                "total_tokens": total,
                "llm_calls": calls,
                "cache_pct": round(cache_pct, 1),
                "model": self._gm.config.llm.model,
            })
            await self._gm._bus.publish(MessageEvent.LLM_LOOP_COMPLETE)

    async def finalize_narrative(
        self, narrative_text: str,
        assistant_msg: Message | None = None,
        *,
        _did_stream: bool = False,
        role: str = "narrative",
        page_id: str = "",
    ) -> Message:
        """统一处理叙事终结。

        流式模式（assistant_msg 存在 + _did_stream）：更新 content → STREAM_END → CREATED
        非流式模式（assistant_msg 为 None）：新建 Message → CREATED

        Returns: 最终 Message 对象（新建或更新后的）
        """
        import uuid7

        bus = self._gm._bus
        session_id = self._gm.session_id

        if assistant_msg is not None:
            assistant_msg.content = narrative_text or assistant_msg.content
            assistant_msg.status = "complete"
            if _did_stream:
                await bus.publish(MessageEvent.STREAM_END, assistant_msg)
            await bus.publish(MessageEvent.CREATED, assistant_msg)
            return assistant_msg

        msg = Message(
            id=str(uuid7.uuid7()),
            session_id=session_id,
            page_id=page_id,
            role=role,
            content=narrative_text,
            status="complete",
        )
        await bus.publish(MessageEvent.CREATED, msg)
        return msg

    # ── LLM 请求 ──────────────────────────────────

    async def request_stream(
        self, messages: list[dict], tools: list[ToolDefinition],
        stream_type: str, page_id: str,
    ) -> dict | None:
        """流式请求，通过 MessageBus 发布 STREAMING 事件"""
        import uuid7
        from lingmo_engine.llm.llm_handler import LLMBusyError

        gm = self._gm
        bus = gm._bus
        session_id = gm.session_id

        assistant_msg = Message(
            id=str(uuid7.uuid7()),
            session_id=session_id,
            parent_id=None,
            page_id=page_id,
            role="narrative",
            status="streaming",
        )

        async def _on_chunk(text: str, stype: str) -> None:
            await bus.publish(MessageEvent.STREAMING, assistant_msg, delta=text)

        try:
            result = await gm.llm_handler.request_stream(
                messages, tools, on_chunk=_on_chunk, stream_type=stream_type,
            )
            if result is None:
                # 流式被取消但前端可能已收到部分 chunk，补发 STREAM_END
                if assistant_msg.status == "streaming":
                    assistant_msg.status = "complete"
                    await bus.publish(MessageEvent.STREAM_END, assistant_msg)
                return None
        except LLMBusyError as e:
            error_msg = Message(
                id=str(uuid7.uuid7()),
                session_id=session_id,
                role="error",
                content=str(e),
            )
            await bus.publish(MessageEvent.CREATED, error_msg)
            return None

        assistant_msg.meta.raw_prompt = serialize_messages_for_meta(messages, tools)
        assistant_msg.meta.model = gm.config.llm.model

        return {
            "full_text": result.full_text,
            "narrative_text": result.narrative_text,
            "final_tool_calls": result.tool_calls or None,
            "finish_reason": result.finish_reason,
            "reasoning_content": result.reasoning_content,
            "assistant_msg": assistant_msg,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "cached_tokens": result.cached_tokens,
        }

    async def request_nonstream(
        self, messages: list[dict], tools: list[ToolDefinition], page_id: str = "",
    ) -> dict | None:
        """非流式请求 LLM，返回解析后的字段 dict（含 assistant_msg）或 None（出错时）。"""
        import uuid7
        from lingmo_engine.llm.llm_handler import LLMBusyError

        gm = self._gm
        session_id = gm.session_id

        try:
            response = await gm.llm_handler.request(messages, tools)
            if response is None:
                return None
        except LLMBusyError as e:
            error_msg = Message(
                id=str(uuid7.uuid7()),
                session_id=session_id,
                role="error",
                content=str(e),
            )
            await gm._bus.publish(MessageEvent.CREATED, error_msg)
            return None

        assistant_msg = Message(
            id=str(uuid7.uuid7()),
            session_id=session_id,
            page_id=page_id,
            role="narrative",
            content=response.text,
            status="complete",
            meta=MessageMeta(
                model=gm.config.llm.model,
                raw_prompt=serialize_messages_for_meta(messages, tools),
                raw_response=response.text,
                finish_reason=response.finish_reason or "stop",
            ),
        )
        return {
            "full_text": response.text,
            "narrative_text": response.text,
            "final_tool_calls": response.tool_calls if response.has_tool_calls else None,
            "finish_reason": response.finish_reason,
            "reasoning_content": response.reasoning_content,
            "assistant_msg": assistant_msg,
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens,
            "cached_tokens": response.cached_tokens,
        }

    # ── 核心循环 ──────────────────────────────────

    async def _run_impl(
        self, messages: list[dict], tools: list[ToolDefinition],
        stream_type: str = "narrative", page_id: str = "",
        max_rounds: int = 10,
        *,
        token_accum: dict | None = None,
    ) -> None:
        """LLM 循环的实际实现，由外层 run() 的 finally 块负责发布 LLM_LOOP_COMPLETE。"""
        import uuid7

        gm = self._gm
        bus = gm._bus
        history = gm.history
        session_id = gm.session_id
        tool_executor = gm._tool_executor
        _use_stream = gm.config.stream_response

        # 新 page 清空推理桥接，不跨 page 保留
        self._reasoning_history.clear()

        narrative_retries = 0
        narrative_generated = False

        for _round_num in range(max_rounds):
            # ── 1. LLM 请求 ──
            assistant_msg = None
            try:
                if _use_stream:
                    resp = await self.request_stream(messages, tools, stream_type, page_id)
                else:
                    resp = await self.request_nonstream(messages, tools, page_id)
                if resp:
                    assistant_msg = resp.get("assistant_msg")

                    # 记录每轮 token 统计
                    pt = resp.get("prompt_tokens", 0)
                    ct = resp.get("completion_tokens", 0)
                    cct = resp.get("cached_tokens", 0)
                    if assistant_msg is not None:
                        assistant_msg.meta.prompt_tokens = pt
                        assistant_msg.meta.completion_tokens = ct
                        assistant_msg.meta.cached_tokens = cct
                        assistant_msg.meta.total_tokens = pt + ct
                    if token_accum is not None:
                        token_accum["prompt"] += pt
                        token_accum["completion"] += ct
                        token_accum["cached"] += cct
                        token_accum["llm_calls"] += 1

                if resp is None:
                    return

                full_text = resp["full_text"]
                narrative_text = resp["narrative_text"]
                final_tool_calls = resp["final_tool_calls"]
                reasoning_content = resp["reasoning_content"]
                finish_reason = resp.get("finish_reason") or "stop"

                _did_stream = _use_stream

                # 非流式模式下，将思考内容插入叙事文本前端
                if reasoning_content and not _did_stream:
                    narrative_text = (
                        f"<thinking>\n{reasoning_content}\n</thinking>\n{narrative_text}"
                    )

                # ── 2. 修复 HTML 并提取 <p> 正文 ──
                fixed_html, p_core_len = _fix_narrative_html(narrative_text)
                stripped = re.sub(
                    r"<thinking>.*?</thinking>\s*", "", narrative_text, flags=re.DOTALL,
                ) if narrative_text else ""

                # ── 3A. 裸文本格式错误：大量文字但无有效 <p> 标签 → 丢弃，直接重试 ──
                raw_len = len(re.sub(r"\s", "", stripped))
                if raw_len > 300 and p_core_len < 300 and narrative_retries < self._gm.config.max_narrative_retries:
                    narrative_retries += 1
                    if _did_stream and assistant_msg is not None:
                        if assistant_msg.status == "streaming":
                            assistant_msg.status = "complete"
                            await bus.publish(MessageEvent.STREAM_END, assistant_msg)
                        await bus.publish(MessageEvent.STREAM_DISCARD, assistant_msg)
                    # 不注入任何消息，上下文已回退到正确状态，直接重试
                    logger.info(
                        "正文格式错误（重试 %d/%d）raw=%d p=%d",
                        narrative_retries, self._gm.config.max_narrative_retries, raw_len, p_core_len,
                    )
                    continue

                # ── 3B. 无工具调用且未生成正文但已停止 → 丢弃，直接重试 ──
                if (not final_tool_calls and finish_reason != "tool_calls"
                        and not narrative_generated and p_core_len < 300
                        and narrative_retries < self._gm.config.max_narrative_retries):
                    narrative_retries += 1
                    if _did_stream and assistant_msg is not None:
                        if assistant_msg.status == "streaming":
                            assistant_msg.status = "complete"
                            await bus.publish(MessageEvent.STREAM_END, assistant_msg)
                        await bus.publish(MessageEvent.STREAM_DISCARD, assistant_msg)
                    # 不注入任何消息，上下文已回退到正确状态，直接重试
                    logger.info(
                        "未生成正文（重试 %d/%d）p=%d",
                        narrative_retries, self._gm.config.max_narrative_retries, p_core_len,
                    )
                    continue

                # ── 3C. 有效正文：发送修复后的叙事 ──
                if p_core_len >= 300:
                    # 用修复后的 HTML 替换正文部分，保留 thinking 前缀
                    if fixed_html:
                        if reasoning_content and not _did_stream:
                            narrative_text = f"<thinking>\n{reasoning_content}\n</thinking>\n{fixed_html}"
                        else:
                            narrative_text = fixed_html
                    assistant_msg = await self.finalize_narrative(
                        narrative_text, assistant_msg,
                        _did_stream=_did_stream,
                        role="narrative",
                        page_id=page_id,
                    )
                    narrative_generated = True
                elif assistant_msg is not None and _did_stream and assistant_msg.status == "streaming":
                    # ── 3D. 过渡语句：不发送叙事，结束流式状态 ──
                    assistant_msg.status = "complete"
                    await bus.publish(MessageEvent.STREAM_END, assistant_msg)

                # ── 4. 无工具调用 → 终结 ──
                if not final_tool_calls:
                    if reasoning_content:
                        self._reasoning_history.append(reasoning_content)
                    msg = {"role": "assistant", "content": fixed_html}
                    if reasoning_content:
                        msg["reasoning_content"] = reasoning_content
                    history.append(msg)
                    return

                # ── 5. 有工具调用 → 执行 ──
                narrative_retries = 0

                history_entry = {"role": "assistant", "content": full_text or ""}
                if reasoning_content:
                    history_entry["reasoning_content"] = reasoning_content

                tool_calls_schema, tool_results, tc_summaries = (
                    await tool_executor.execute(
                        final_tool_calls, page_id,
                    )
                )

                if assistant_msg is not None:
                    assistant_msg.meta.tool_calls_made = tc_summaries

                if tool_calls_schema:
                    history_entry["tool_calls"] = tool_calls_schema
                    messages.append(history_entry)

                messages.extend(tool_results)

                # 叙事已生成时注入系统提示，防止后续轮次重复生成叙事
                if narrative_generated:
                    messages.append({
                        "role": "system",
                        "content": "【系统提示】本轮正文叙事已经生成并发送给玩家。后续只需调用工具或输出极简过渡语句，不要重新生成正文叙事。",
                    })

                # 推理桥接：将本轮思考追加到 messages，保持多轮工具调用间思维连贯
                if reasoning_content:
                    self._reasoning_history.append(reasoning_content)
                if self._reasoning_history:
                    bridge = self._build_reasoning_bridge()
                    messages.append({"role": "system", "content": bridge})


            finally:
                # 安全网：显式路径已将 status 设为 "complete"，此处仅捕获遗漏场景
                try:
                    if _use_stream and assistant_msg is not None and assistant_msg.status == "streaming":
                        assistant_msg.status = "complete"
                        await bus.publish(MessageEvent.STREAM_END, assistant_msg)
                except Exception:
                    logger.warning("STREAM_END 安全网发布失败", exc_info=True)

        history.append({"role": "assistant", "content": "（游戏主循环达到最大轮次）"})

        # 发布到前端
        try:
            import uuid7 as _uuid7
            max_rounds_msg = Message(
                id=str(_uuid7.uuid7()),
                session_id=session_id,
                page_id=page_id,
                role="system",
                content="（游戏主循环达到最大轮次）",
                status="complete",
            )
            await bus.publish(MessageEvent.CREATED, max_rounds_msg)
        except Exception:
            logger.warning("发布最大轮次消息失败", exc_info=True)
