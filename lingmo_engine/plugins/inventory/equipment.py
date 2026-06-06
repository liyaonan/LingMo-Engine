"""装备系统：装备/卸下/槽位管理/效果生命周期。"""

from __future__ import annotations

from lingmo_engine.plugins.inventory.items import BuffDef, EquipmentItem, ItemSystem


class EquipmentSystem:
    """管理角色装备状态和效果"""

    def __init__(self, item_system: ItemSystem):
        self._item_system = item_system
        self._slots: list[dict] = []
        # 装备数值框架配置（堆叠规则、稀有度系数等）
        self._equip_config: dict = {}

    def load_slots(self, raw: dict) -> None:
        """加载装备槽位定义"""
        self._slots = raw.get("slots", [])

    def get_slots(self) -> list[dict]:
        return self._slots

    def equip(
        self, item_id: str, slot_id: str,
        equipment: dict[str, str | None], inventory: list[dict],
        character_data: dict | None = None,
    ) -> dict:
        """装备物品到指定槽位。

        Returns:
            {success, message, previous_item_id?, changes: {equipped, removed?}}
        """
        item = self._item_system.get_item(item_id)
        if item is None or not item.is_equipment:
            return {"success": False, "message": f"物品 {item_id} 不存在或不可装备"}

        if item.equip_slot != slot_id:
            return {"success": False, "message": f"物品 {item_id} 不适用于槽位 {slot_id}"}

        # 检查背包中是否有此物品
        in_inventory = any(e["item_id"] == item_id and e["quantity"] > 0 for e in inventory)
        if not in_inventory:
            return {"success": False, "message": f"背包中没有 {item_id}"}

        # 检查装备条件（字段间 AND，字段内 OR）
        if item.equip_requirements:
            if character_data is None:
                return {"success": False, "message": f"装备 {item.name} 需要角色数据验证，但未提供"}
            for field, req in item.equip_requirements.items():
                required_values = req if isinstance(req, (list, set, tuple)) else [req]
                char_value = character_data.get(field, "")
                if isinstance(char_value, list):
                    if not any(v in char_value for v in required_values):
                        return {"success": False, "message": f"不满足装备要求：{field}"}
                else:
                    if char_value not in required_values:
                        return {"success": False, "message": f"不满足装备要求：{field}"}

        previous = equipment.get(slot_id)
        previous_item = self._item_system.get_item(previous) if previous else None

        # 装备（不扣除背包数量，装备物品仍在背包中）
        equipment[slot_id] = item_id

        return {
            "success": True,
            "message": f"装备了 {item.name}",
            "previous_item_id": previous,
            "changes": {
                "equipped": item.to_dict(),
                "removed": previous_item.to_dict() if previous_item else None,
                "slot_id": slot_id,
            },
        }

    def unequip(
        self, slot_id: str, equipment: dict[str, str | None],
        player_native_abilities: list[str],
    ) -> dict:
        """卸下指定槽位的装备。

        Returns:
            {success, message, changes: {removed, skills_removed}}
        """
        if slot_id not in equipment:
            return {"success": False, "message": f"槽位 {slot_id} 不存在"}

        item_id = equipment.get(slot_id)
        if item_id is None:
            return {"success": False, "message": f"槽位 {slot_id} 为空"}

        item = self._item_system.get_item(item_id)
        equipment[slot_id] = None

        abilities_removed = []
        if item and item.is_equipment:
            for ability_id in item.abilities:
                if ability_id not in player_native_abilities:
                    abilities_removed.append(ability_id)

        return {
            "success": True,
            "message": f"卸下了 {item.name if item else item_id}",
            "changes": {
                "removed": item.to_dict() if item else None,
                "slot_id": slot_id,
                "abilities_removed": abilities_removed,
            },
        }

    def get_combat_equipment(
        self, equipment: dict[str, str | None],
        innate_attrs: dict[str, int] | None = None,
        stat_bonus_mode: str = "full",
    ) -> dict:
        """获取战斗中应注入的装备效果。

        Args:
            equipment: 槽位→物品ID 映射
            innate_attrs: 角色先天属性（用于计算叠加上限），为 None 时不做上限处理
            stat_bonus_mode: "full" 累加 stat_bonus（默认，兼容旧世界），
                             "none" 跳过 stat_bonus（叙事模式，仅注入 abilities）

        Returns:
            {stat_bonus, buffs, abilities, capped_attrs?}
        """
        stat_bonus: dict[str, int] = {}
        buffs: list[BuffDef] = []
        abilities: list[str] = []

        for slot_id, item_id in equipment.items():
            if item_id is None:
                continue
            item = self._item_system.get_item(item_id)
            if item is None or not item.is_equipment:
                continue
            # 叙事模式下跳过 stat_bonus 累加
            if stat_bonus_mode != "none":
                for stat, val in item.stat_bonus.items():
                    stat_bonus[stat] = stat_bonus.get(stat, 0) + val
            buffs.extend(item.buffs)
            abilities.extend(item.abilities)

        capped_attrs: dict[str, dict] = {}
        cap = self.get_same_attr_cap()
        if cap < 1.0 and innate_attrs:
            for stat in stat_bonus:
                if stat not in innate_attrs:
                    continue
                cap_value = int(innate_attrs[stat] * cap)
                if stat_bonus[stat] > cap_value:
                    capped_attrs[stat] = {"raw": stat_bonus[stat], "cap": cap_value}
                    stat_bonus[stat] = cap_value

        result: dict = {
            "stat_bonus": stat_bonus,
            "buffs": buffs,
            "abilities": abilities,
        }
        if capped_attrs:
            result["capped_attrs"] = capped_attrs
        return result

    def get_narrative_effects(self, equipment: dict[str, str | None]) -> list[dict]:
        """收集所有已装备物品的叙事效果。

        Args:
            equipment: 槽位→物品ID 映射

        Returns:
            [{"item_name": str, "slot_id": str, "effects": {category: text}}]
        """
        results = []
        for slot_id, item_id in equipment.items():
            if item_id is None:
                continue
            item = self._item_system.get_item(item_id)
            if item is None or not item.is_equipment:
                continue
            if item.narrative_effects:
                results.append({
                    "item_name": item.name,
                    "slot_id": slot_id,
                    "effects": item.narrative_effects,
                })
        return results

    def get_equipment_snapshot(self, equipment: dict[str, str | None]) -> dict:
        """获取装备快照（用于前端展示）"""
        snapshot = {}
        for slot_id, item_id in equipment.items():
            if item_id:
                item = self._item_system.get_item(item_id)
                snapshot[slot_id] = item.to_dict() if item else None
            else:
                snapshot[slot_id] = None
        return snapshot

    # ── 装备数值框架配置 ──────────────────────────────────

    def load_equip_config(self, config: dict) -> None:
        """加载装备数值框架配置。

        Args:
            config: 包含 equip_formula 和 rarity_multipliers 的配置字典。
        """
        self._equip_config = config

    def get_rarity_mult(self, rarity: str) -> float:
        """获取指定稀有度的数值系数。

        Args:
            rarity: 稀有度标识，如 "fine"、"rare" 等。

        Returns:
            对应的数值系数，未找到时返回 0.0。
        """
        return self._equip_config.get("rarity_multipliers", {}).get(rarity, 0.0)

    def get_same_attr_cap(self) -> float:
        """获取同属性堆叠上限比例。"""
        return self._equip_config.get("equip_formula", {}).get("same_attr_cap", 1.0)

    def get_stack_rule(self) -> str:
        """获取属性堆叠规则名称。"""
        return self._equip_config.get("equip_formula", {}).get("stack_rule", "simple_sum")
