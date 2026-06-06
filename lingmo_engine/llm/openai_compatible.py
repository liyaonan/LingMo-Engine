import json
import logging
import threading
from collections.abc import Generator
from datetime import datetime
from pathlib import Path

from openai import OpenAI

from lingmo_engine.llm.base_provider import BaseLLMProvider, LLMResponse, LLMStreamEvent, ToolCall
from lingmo_engine.core.types import ToolDefinition

logger = logging.getLogger(__name__)

_log_dir: Path | None = None
_log_enabled: bool = True
_log_lock = threading.Lock()


def set_log_dir(path: Path) -> None:
    global _log_dir
    _log_dir = path
    _log_dir.mkdir(parents=True, exist_ok=True)


def set_log_enabled(enabled: bool) -> None:
    global _log_enabled
    _log_enabled = enabled


def _write_llm_log(direction: str, payload: dict) -> None:
    if not _log_enabled or _log_dir is None:
        return
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = _log_dir / f"llm_{today}.jsonl"
    record = {
        "timestamp": datetime.now().isoformat(),
        "direction": direction,
        **payload,
    }
    with _log_lock:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _extract_usage(usage) -> tuple[int, int, int]:
    """从 API response.usage 安全提取 token 统计。

    Returns: (prompt_tokens, completion_tokens, cached_tokens)
    """
    if usage is None:
        return 0, 0, 0
    prompt = getattr(usage, "prompt_tokens", 0) or 0
    completion = getattr(usage, "completion_tokens", 0) or 0
    details = getattr(usage, "prompt_tokens_details", None)
    cached = getattr(details, "cached_tokens", 0) if details else 0
    return prompt, completion, cached


class OpenAICompatibleProvider(BaseLLMProvider):
    def __init__(self, config):
        super().__init__(config)
        self._client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url or None,
            timeout=60.0,
            max_retries=2,
        )

    def chat(
        self,
        messages: list[dict],
        tools: list[ToolDefinition] | None = None,
        *,
        thinking: bool | None = None,
    ) -> LLMResponse:
        kwargs: dict = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
        }

        if tools:
            kwargs["tools"] = self.build_tool_schema(tools)
            kwargs["tool_choice"] = "auto"

        if thinking is not None:
            kwargs["extra_body"] = {"thinking": {"type": "enabled" if thinking else "disabled"}}

        logger.debug(
            "LLM request: %d messages, %d tools, thinking=%s",
            len(messages), len(tools or []), thinking,
        )

        _write_llm_log("request", {
            "model": self.config.model,
            "messages": messages,
            "tools": kwargs.get("tools"),
            "thinking": thinking,
        })

        response = self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]

        text = choice.message.content or ""
        reasoning_content = getattr(choice.message, "reasoning_content", None)
        tool_calls = []

        raw_tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                try:
                    params = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    logger.warning("Failed to parse tool arguments: %s", tc.function.arguments)
                    params = {}
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    params=params,
                ))
                raw_tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                })

        prompt_tokens, completion_tokens, cached_tokens = _extract_usage(response.usage)

        _write_llm_log("response", {
            "text": text,
            "tool_calls": raw_tool_calls,
            "finish_reason": choice.finish_reason,
            "reasoning_content": reasoning_content,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cached_tokens": cached_tokens,
        })

        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            reasoning_content=reasoning_content,
        )

    def chat_stream(
        self,
        messages: list[dict],
        tools: list[ToolDefinition] | None = None,
        *,
        thinking: bool | None = None,
    ) -> Generator[LLMStreamEvent, None, None]:
        """流式对话，每次 yield LLMStreamEvent。"""
        kwargs: dict = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "stream": True,
        }

        if tools:
            kwargs["tools"] = self.build_tool_schema(tools)
            kwargs["tool_choice"] = "auto"

        if thinking is not None:
            kwargs["extra_body"] = {"thinking": {"type": "enabled" if thinking else "disabled"}}

        logger.debug(
            "LLM stream request: %d messages, %d tools, thinking=%s",
            len(messages), len(tools or []), thinking,
        )

        _write_llm_log("request", {
            "model": self.config.model,
            "messages": messages,
            "tools": kwargs.get("tools"),
            "thinking": thinking,
        })

        stream = self._client.chat.completions.create(**kwargs)

        full_text = ""
        reasoning_text = ""
        tool_call_acc: dict[int, dict] = {}  # index -> {id, name, arguments}

        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta is None:
                continue
            finish = chunk.choices[0].finish_reason

            text_delta = delta.content or ""
            reasoning_delta = getattr(delta, "reasoning_content", None) or ""

            full_text += text_delta
            reasoning_text += reasoning_delta

            # Accumulate tool call deltas
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_call_acc:
                        tool_call_acc[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc_delta.id:
                        tool_call_acc[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tool_call_acc[idx]["name"] += tc_delta.function.name
                        if tc_delta.function.arguments:
                            tool_call_acc[idx]["arguments"] += tc_delta.function.arguments

            if finish is not None:
                # Stream ended — build tool_calls list
                tool_calls = []
                raw_tool_calls = []
                for idx in sorted(tool_call_acc.keys()):
                    tc = tool_call_acc[idx]
                    if tc["name"]:
                        try:
                            params = json.loads(tc["arguments"]) if tc["arguments"] else {}
                        except json.JSONDecodeError:
                            logger.warning("Failed to parse stream tool arguments: %s", tc["arguments"])
                            params = {}
                        tool_calls.append(ToolCall(
                            id=tc["id"],
                            name=tc["name"],
                            params=params,
                        ))
                        raw_tool_calls.append({
                            "id": tc["id"],
                            "name": tc["name"],
                            "arguments": tc["arguments"],
                        })

                prompt_tokens, completion_tokens, cached_tokens = _extract_usage(
                    getattr(chunk, "usage", None),
                )

                _write_llm_log("response", {
                    "text": full_text,
                    "tool_calls": raw_tool_calls,
                    "finish_reason": finish,
                    "reasoning_content": reasoning_text or None,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "cached_tokens": cached_tokens,
                })

                yield LLMStreamEvent(
                    text_delta="",
                    tool_calls=tool_calls if tool_calls else None,
                    finish_reason=finish,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cached_tokens=cached_tokens,
                )
            elif text_delta or reasoning_delta:
                yield LLMStreamEvent(
                    text_delta=text_delta,
                    reasoning_delta=reasoning_delta,
                )
