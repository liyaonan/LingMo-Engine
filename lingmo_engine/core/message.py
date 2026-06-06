"""统一消息数据模型 — Message 是引擎内唯一的数据载体。

Message 贯穿 LLM 产出 → WebSocket 传输 → 前端展示 → 磁盘持久化全链路。
每条消息与游戏存档 session_id 一一绑定。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from enum import Enum


class MessageRole(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"
    NARRATIVE = "narrative"
    COMBAT = "combat"
    ERROR = "error"
    ENCOUNTER = "encounter"


class MessageStatus(Enum):
    STREAMING = "streaming"
    COMPLETE = "complete"
    RETRACTED = "retracted"
    DELETED = "deleted"


@dataclass
class MessageMeta:
    """消息运行时元数据 — 每条消息的完整调试信息"""
    model: str = ""
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    latency_ms: float = 0.0
    finish_reason: str = ""
    raw_prompt: str = ""          # 完整 system + messages + tools 文本（调试核心）
    raw_response: str = ""        # LLM 原始返回文本（含标签）
    tool_calls_made: list = field(default_factory=list)
    edit_version: int = 1

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "MessageMeta":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Message:
    """统一消息 — 全系统唯一的数据载体"""
    id: str                       # UUID7（时间排序全局唯一）
    session_id: str               # 所属存档 session_id
    parent_id: str | None = None  # 父消息 ID（因果链）
    page_id: str | None = None    # 前端 Page 聚合键
    role: str = "user"
    content: str = ""
    content_blocks: list = field(default_factory=list)
    status: str = "complete"
    meta: MessageMeta = field(default_factory=MessageMeta)
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    edited_at: str | None = None
    extra: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        """序列化为可 JSON 序列化的 dict（用于 JSONL 写入 / WebSocket 传输）"""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "parent_id": self.parent_id,
            "page_id": self.page_id,
            "role": self.role,
            "content": self.content,
            "content_blocks": self.content_blocks,
            "status": self.status,
            "meta": self.meta.to_dict(),
            "timestamp": self.timestamp,
            "edited_at": self.edited_at,
            "extra": self.extra,
        }

    @classmethod
    def from_json(cls, data: dict) -> "Message":
        """从 dict 反序列化（JSONL 读取 / WebSocket 接收）

        timestamp 仅在传入非空值时覆盖，否则由 dataclass default_factory 自动生成。
        """
        meta_data = data.get("meta", {})
        meta = MessageMeta.from_dict(meta_data) if meta_data else MessageMeta()
        ts = data.get("timestamp")
        kwargs = dict(
            id=data.get("id", ""),
            session_id=data.get("session_id", ""),
            parent_id=data.get("parent_id"),
            page_id=data.get("page_id"),
            role=data.get("role", "user"),
            content=data.get("content", ""),
            content_blocks=data.get("content_blocks", []),
            status=data.get("status", "complete"),
            meta=meta,
            edited_at=data.get("edited_at"),
            extra=data.get("extra", {}),
        )
        if ts:
            kwargs["timestamp"] = ts
        return cls(**kwargs)

    def edit(self, new_content: str) -> None:
        """编辑消息内容，递增版本号"""
        self.content = new_content
        self.meta.edit_version += 1
        self.edited_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    def mark_deleted(self) -> None:
        """逻辑删除：标记 status=DELETED，保留 JSONL 行用于调试"""
        self.status = MessageStatus.DELETED.value
        self.edited_at = time.strftime("%Y-%m-%dT%H:%M:%S")
