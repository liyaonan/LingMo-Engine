"""地图插件 — MapPlugin 实现（核心抽象已迁入 lingmo_engine.core.map）"""
from __future__ import annotations

# 向后兼容重导出
from lingmo_engine.core.map import MapNode, BaseMap, DefaultMap

__all__ = ["MapNode", "BaseMap", "DefaultMap"]
