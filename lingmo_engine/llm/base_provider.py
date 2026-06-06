from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any

from lingmo_engine.core.types import ToolDefinition


@dataclass
class ToolCall:
    id: str
    name: str
    params: dict


@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    reasoning_content: str | None = None

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


@dataclass
class LLMStreamEvent:
    """流式 LLM 响应的单个事件。"""
    text_delta: str = ""
    tool_calls: list[ToolCall] | None = None  # 仅流结束时非 None
    finish_reason: str | None = None  # 仅流结束时非 None
    reasoning_delta: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0


class BaseLLMProvider:
    def __init__(self, config):
        self.config = config

    def chat(
        self,
        messages: list[dict],
        tools: list[ToolDefinition] | None = None,
        *,
        thinking: bool | None = None,
    ) -> LLMResponse:
        raise NotImplementedError

    def chat_stream(
        self,
        messages: list[dict],
        tools: list[ToolDefinition] | None = None,
        *,
        thinking: bool | None = None,
    ) -> Generator[LLMStreamEvent, None, None]:
        """流式对话。返回 Generator，每次 yield LLMStreamEvent。
        最后一个事件包含 tool_calls 和 finish_reason。
        """
        raise NotImplementedError

    def build_tool_schema(self, tools: list[ToolDefinition]) -> list[dict]:
        return [t.to_openai_schema() for t in tools]
