"""遭遇会话基类 — 统一 combat/cultivation 等子系统的会话生命周期。"""
from __future__ import annotations

import logging
import time
from typing import Any

_log = logging.getLogger(__name__)


class EncounterSession:
    """遭遇会话基类。

    提供 narrative_hint、结构化 log、phase 状态机等通用能力，
    子类（如 CombatSession / CultivationSession）覆盖 process_action / finish 即可。

    生命周期: active -> (completed | failed | cancelled)
    """

    def __init__(
        self,
        player: Any | None = None,
        narrative_hint: str = "",
    ) -> None:
        self.player = player
        self.narrative_hint = narrative_hint
        self.log: list[dict] = []
        self.phase: str = "active"
        self.created_at: float = time.time()

    def is_active(self) -> bool:
        """会话是否处于活跃状态。"""
        return self.phase == "active"

    def _add_log(self, entry: dict) -> None:
        """追加一条结构化日志。"""
        self.log.append(entry)

    def get_summary(self) -> dict:
        """返回会话摘要（子类可覆盖以添加领域字段）。"""
        return {
            "narrative_hint": self.narrative_hint,
            "log_count": len(self.log),
            "phase": self.phase,
        }

    def finish(self) -> dict:
        """结束会话，返回最终摘要。

        子类应覆盖此方法执行收尾逻辑（如结算奖励、更新玩家状态）。
        覆盖时须调用 super().finish() 或手动设置 self.phase。
        """
        self.phase = "completed"
        return self.get_summary()
