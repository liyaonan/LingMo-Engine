from __future__ import annotations
from typing import Protocol, runtime_checkable


@runtime_checkable
class StateProvider(Protocol):
    """插件获取游戏状态的唯一接口。"""

    def get_player_data(self) -> dict: ...
    def get_scene_state(self) -> dict: ...
    def get_game_data(self) -> dict: ...
