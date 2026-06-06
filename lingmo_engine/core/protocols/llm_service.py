from __future__ import annotations
from typing import Protocol, runtime_checkable, Any


@runtime_checkable
class LLMService(Protocol):
    """插件调用 LLM 的唯一接口。"""

    async def request(self, messages: list, *, mode: str = "strong", tools: list | None = None) -> Any: ...


@runtime_checkable
class LLMProviderAccess(Protocol):
    """插件直接访问 LLM Provider（绕过 handler 锁，避免 tool_executor 死锁）。"""

    def chat(self, messages: list, *, mode: str = "fast",
             thinking: bool = False) -> Any: ...
