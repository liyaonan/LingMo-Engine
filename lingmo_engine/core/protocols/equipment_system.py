"""装备系统接口协议 — 定义跨插件访问 EquipmentSystem 的最小接口。

其他插件（character、combat 等）通过此协议访问装备数据，
避免直接导入 inventory.equipment.EquipmentSystem 具体类。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable, Any


@runtime_checkable
class EquipmentSystemInterface(Protocol):
    """装备系统公共接口 — 跨插件访问装备数据的唯一契约。

    现有 EquipmentSystem 类已结构性满足此协议，无需修改。
    """

    def get_slots(self) -> list[dict]:
        """获取装备槽位定义列表。"""
        ...

    def equip(
        self,
        item_id: str,
        slot_id: str,
        equipment: dict[str, str | None],
        inventory: list[dict],
        character_data: dict | None = None,
    ) -> dict:
        """将物品装备到指定槽位，返回操作结果。"""
        ...

    def unequip(
        self,
        slot_id: str,
        equipment: dict[str, str | None],
        player_native_abilities: list[str],
    ) -> dict:
        """从指定槽位卸下装备，返回操作结果。"""
        ...

    def get_combat_equipment(
        self,
        equipment: dict[str, str | None],
        innate_attrs: dict[str, int] | None = None,
        stat_bonus_mode: str = "full",
    ) -> dict:
        """获取战斗装备效果（属性加成、技能等）。"""
        ...

    def get_narrative_effects(self, equipment: dict[str, str | None]) -> list[dict]:
        """获取装备的叙事效果列表。"""
        ...

    def get_equipment_snapshot(self, equipment: dict[str, str | None]) -> dict:
        """获取装备快照（用于前端显示）。"""
        ...

    def load_slots(self, raw: dict) -> None:
        """从原始数据加载槽位定义。"""
        ...

    def load_equip_config(self, config: dict) -> None:
        """加载装备数值框架配置。"""
        ...

    def get_rarity_mult(self, rarity: str) -> float:
        """获取指定稀有度的数值系数。"""
        ...

    def get_same_attr_cap(self) -> float:
        """获取同类属性叠加上限比例。"""
        ...

    def get_stack_rule(self) -> str:
        """获取属性叠加规则名称。"""
        ...
