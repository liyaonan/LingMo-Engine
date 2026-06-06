from __future__ import annotations

from typing import Callable, Awaitable

from fastapi import WebSocket

Handler = Callable[[WebSocket, dict], Awaitable[None]]


class BaseController:
    """控制器基类 — 通过 services 字典接收所有依赖。"""

    def __init__(self, *, services: dict, config=None):
        self._services = services
        self.config = config

    @property
    def game_svc(self):
        return self._services.get("game")

    @property
    def config_svc(self):
        return self._services.get("config")

    @property
    def char_svc(self):
        return self._services.get("character")

    @property
    def inventory_svc(self):
        return self._services.get("inventory")

    @property
    def map_svc(self):
        return self._services.get("map")

    @property
    def combat_svc(self):
        return self._services.get("combat")

    def get_handlers(self) -> dict[str, Handler]:
        return {}

    def _reset_calendar_to_initial(self, state) -> None:
        """重置日历插件为初始状态并写入 GameState。"""
        plugins = self.game_svc.plugins if self.game_svc else None
        if plugins:
            cal_plugin = plugins.get_plugin("calendar")
            if cal_plugin:
                initial_time = cal_plugin.reset_to_initial()
                if initial_time:
                    state.set_game_time(initial_time)

    def _init_characters_last_updated(self, cm) -> None:
        """新游戏初始化：将所有角色的 last_updated 设为日历初始日期。"""
        plugins = self.game_svc.plugins if self.game_svc else None
        if not plugins:
            return
        cal_plugin = plugins.get_plugin("calendar")
        if not cal_plugin or not cal_plugin.calendar:
            return
        cal = cal_plugin.calendar
        date_str = f"{cal._current_year}/{cal._current_month}/{cal._current_day}"
        for char in cm.all():
            if not char.last_updated:
                char.last_updated = date_str
                cm.mark_dirty(char.id)
