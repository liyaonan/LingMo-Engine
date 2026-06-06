from __future__ import annotations


class CombatService:
    """战斗服务 — 封装战斗操作路由。"""

    def __init__(self, gm):
        self._gm = gm

    def route_websocket(self, msg, state):
        """将战斗 WebSocket 消息路由到插件"""
        return self._gm.plugins.route_websocket(msg, state)
