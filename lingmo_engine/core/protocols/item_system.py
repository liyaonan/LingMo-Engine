"""物品系统接口协议 — 定义跨插件访问 ItemSystem 的最小接口。

其他插件（combat、character、crafting 等）通过此协议访问物品数据，
避免直接导入 inventory.items.ItemSystem 具体类。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable, Any


@runtime_checkable
class ItemSystemInterface(Protocol):
    """物品系统公共接口 — 跨插件访问物品数据的唯一契约。

    现有 ItemSystem 类已结构性满足此协议，无需修改。
    """

    def get_item(self, item_id: str) -> Any | None:
        """根据 ID 获取物品，不存在返回 None。"""
        ...

    def get_item_by_name(self, name: str) -> Any | None:
        """根据名称精确匹配获取物品。"""
        ...

    def get_items_by_category(self, category: str) -> list[Any]:
        """获取指定分类下的所有物品。"""
        ...

    def get_all_items(self) -> list[Any]:
        """获取所有已注册物品。"""
        ...

    def get_categories(self) -> list[dict]:
        """获取物品分类定义列表。"""
        ...

    def get_rarities(self) -> list[dict]:
        """获取稀有度定义列表。"""
        ...

    def get_rarity_info(self, rarity: int) -> dict:
        """根据稀有度等级获取稀有度信息。"""
        ...

    def register_item(self, item: Any) -> None:
        """动态注册一个物品。"""
        ...

    def get_items_for_slot(self, slot_id: str, inventory: list[dict]) -> list[Any]:
        """获取背包中可装备到指定槽位的物品。"""
        ...

    def get_items_by_tag(self, tag: str) -> list[Any]:
        """根据标签获取物品。"""
        ...
