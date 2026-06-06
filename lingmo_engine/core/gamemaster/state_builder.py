"""StateBuildService — 状态构建服务，收集各子系统状态片段，构建前端快照。"""
from __future__ import annotations

import logging
from typing import Callable, Any

from lingmo_engine.core.events import PluginEvent

logger = logging.getLogger(__name__)


class StateBuildService:
    """状态构建服务 — 收集各子系统状态片段，构建前端快照。

    通过 lambda getter 注入依赖，避免与 GameMaster 形成循环引用。
    """

    def __init__(
        self,
        get_state_fn: Callable[[], Any],
        get_world_fn: Callable[[], Any],
        get_plugins_fn: Callable[[], Any],
    ):
        self._get_state = get_state_fn
        self._get_world = get_world_fn
        self._get_plugins = get_plugins_fn

    def build_state(self) -> dict:
        """构建完整 game_state 快照，供 state_update 推送前端。"""
        state = self._get_state()
        gs = state.get_data_copy()
        cm = getattr(state, 'character_manager', None)
        # 若 CM 尚未挂载到 GameState（如服务器重启后 WebSocket 重连），自动挂载
        if cm is None:
            cm = getattr(self._get_world(), '_char_manager', None)
            if cm is not None:
                state.character_manager = cm
        if cm:
            player = cm.player
            gs["player"] = player.to_dict()
            gs["player"].update(player.attrs)
            # 应用显示增幅
            amplify_fn = getattr(state, '_amplify_fn', None)
            if amplify_fn:
                gs["player"] = amplify_fn(gs["player"])
            gs["inventory"] = list(player.inventory)
            gs["equipment"] = dict(player.equipment)
        plugins = self._get_plugins()
        try:
            calendar_info = plugins.bus.request(PluginEvent.CALENDAR_GET_INFO)
        except Exception:
            calendar_info = None
            logger.debug("state_builder: 获取日历信息失败", exc_info=True)
        if calendar_info:
            gs["game_time"] = calendar_info
        # 位置信息：从 MapPlugin 获取（传空字符串，MapPlugin 使用自身缓存的 current_node_id）
        try:
            location_info = plugins.bus.request(
                PluginEvent.MAP_GET_LOCATION_INFO, ""
            )
        except Exception:
            location_info = None
            logger.debug("state_builder: 获取位置信息失败", exc_info=True)
        if location_info:
            gs.update(location_info)
        return gs
