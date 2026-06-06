from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class StateSnapshot:
    """不可变状态快照 — 用于跨层传递游戏状态。

    替代直接返回 dict 的方式，防止消费者意外修改内部数据。
    to_dict() 保持与前端兼容的输出格式。
    """

    player_data: dict
    scene_state: dict
    game_data: dict
    location_info: str

    def to_dict(self) -> dict:
        """序列化为前端兼容的 dict。"""
        return asdict(self)
