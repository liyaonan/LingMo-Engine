from __future__ import annotations

from lingmo_engine.core.events import PluginEvent


class InventoryService:
    """背包服务 — 封装装备/卸下/使用操作。"""

    def __init__(self, gm):
        self._gm = gm

    def get_plugin(self):
        """获取背包插件实例（通过 EventBus 间接访问）。"""
        # 保持向后兼容：仍支持通过 registry 直接获取
        return self._gm.plugins.get_plugin("inventory") if self._gm.plugins else None

    def restore_registries(self, state):
        """从注册表恢复 LLM 生成的物品"""
        plugin = self.get_plugin()
        if plugin:
            plugin.restore_registries(state)

    def auto_push(self, state):
        """推送背包状态到前端"""
        return self._gm.plugins.bus.request(
            PluginEvent.INVENTORY_AUTO_PUSH, game_state=state,
        )
