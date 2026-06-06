from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class GMProviderAccess:
    """从 GameMaster 的 LLMHandler 直接访问 Provider，绕过 asyncio.Lock。

    用于插件在 tool_executor 线程中同步调用 LLM（持有锁时不能再次请求锁）。
    """

    def __init__(self, gm):
        self._gm = gm

    def chat(self, messages: list, *, mode: str = "fast",
             thinking: bool = False) -> Any:
        handler = self._gm.llm_handler
        provider = handler.fast_provider if mode == "fast" else handler.strong_provider

        try:
            return provider.chat(messages, tools=None, thinking=thinking)
        except Exception:
            if mode != "fast":
                raise
            logger.warning("快推理 Provider 失败，回退到强推理", exc_info=True)
            return handler.strong_provider.chat(messages, tools=None, thinking=thinking)

    @property
    def handler(self):
        """暴露 LLMHandler 引用，供需要异步调用的场景。"""
        return self._gm.llm_handler

    @property
    def pending_tasks(self):
        """暴露 GM 的 pending_tasks，供插件注册异步任务。"""
        return getattr(self._gm, '_pending_tasks', set())
