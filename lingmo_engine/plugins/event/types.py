"""事件系统数据类型。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Self


@dataclass
class EventRecord:
    """LLM 自治的事件计划记录。

    替代旧 EventPlan + EventNode + Milestone 的全部功能。
    事件以 Markdown 文档形式存储，LLM 全权管理内容。
    """
    event_id: str           # 唯一 ID，如 "evt_001"
    title: str              # 事件标题
    status: str = "active"  # "active" | "completed"
    plan_md: str = ""       # 完整 Markdown 计划（含所有段落）
    created_at: str = ""    # 创建时的游戏时间，格式如 "day15_month3_year1"
    updated_at: str = ""    # 最后更新时的游戏时间

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "title": self.title,
            "status": self.status,
            "plan_md": self.plan_md,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return cls(
            event_id=data.get("event_id", ""),
            title=data.get("title", ""),
            status=data.get("status", "active"),
            plan_md=data.get("plan_md", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )
