from __future__ import annotations

from lingmo_engine.core.events import PluginEvent


class MapService:
    """地图服务 — 封装位置查询和导航。"""

    def __init__(self, gm):
        self._gm = gm

    def get_location_info(self, location: str = ""):
        """获取当前位置信息"""
        return self._gm.plugins.bus.request(PluginEvent.MAP_GET_LOCATION_INFO, location)
