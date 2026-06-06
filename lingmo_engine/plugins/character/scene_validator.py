"""SceneValidator — 场景角色校验器，叙事后自动修正角色数据。"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from lingmo_engine.core.types import normalize_name

if TYPE_CHECKING:
    from lingmo_engine.core.character import Character
    from lingmo_engine.core.protocols.equipment_system import EquipmentSystemInterface
    from lingmo_engine.core.protocols.item_system import ItemSystemInterface

logger = logging.getLogger(__name__)


class SceneValidator:
    """场景角色校验器 — 叙事后自动修正角色数据。

    两阶段管线：
    1. check_format — 格式校验（类型修正）
    2. check_existence + check_range — 存在性与数值范围校验
    """

    def __init__(
        self,
        world=None,
        item_system: "ItemSystemInterface | None" = None,
        equipment_system: "EquipmentSystemInterface | None" = None,
        game_state=None,
    ):
        self._world = world
        self._item_system = item_system
        self._equipment_system = equipment_system
        self._game_state = game_state
        self._validator = None  # AttributeValidator 引用，延迟注入

    def set_validator(self, validator) -> None:
        """注入 AttributeValidator 实例（用于范围校验）。"""
        self._validator = validator

    # ── 阶段1：格式校验 ──

    def check_format(self, char: "Character") -> list[str]:
        """修正 abilities、equipment、attrs、tags 的格式问题。

        Returns:
            修正日志列表。
        """
        logs: list[str] = []
        logs.extend(self._fix_abilities_format(char))
        logs.extend(self._fix_equipment_format(char))
        logs.extend(self._fix_attrs_format(char))
        logs.extend(self._fix_tags_format(char))
        return logs

    def _fix_abilities_format(self, char: "Character") -> list[str]:
        """修正 abilities 列表中的格式问题。"""
        logs: list[str] = []
        fixed: list[str] = []
        for item in char.abilities:
            if isinstance(item, dict):
                name = item.get("name")
                if name and isinstance(name, str):
                    fixed.append(name)
                    logs.append(f"abilities: dict→'{name}'（已提取 name 字段）")
                else:
                    logs.append(f"abilities: 移除无 name 的 dict 项 {item}")
            elif isinstance(item, str) and item.strip():
                fixed.append(item)
            elif item is None:
                logs.append("abilities: 移除 None 项")
            elif isinstance(item, str):
                logs.append("abilities: 移除空字符串项")
            else:
                logs.append(f"abilities: 移除非预期类型 {type(item).__name__}")
        char.abilities = fixed
        return logs

    def _fix_equipment_format(self, char: "Character") -> list[str]:
        """修正 equipment dict 中的 value 格式问题，并将名称解析为物品ID。"""
        logs: list[str] = []
        fixed: dict[str, str] = {}
        for slot_id, value in char.equipment.items():
            if isinstance(value, str):
                resolved = self._resolve_equipment_value(slot_id, value, logs)
                fixed[slot_id] = resolved
            elif isinstance(value, dict):
                name = value.get("name") or value.get("id")
                if name and isinstance(name, str):
                    resolved = self._resolve_equipment_value(slot_id, name, logs)
                    fixed[slot_id] = resolved
                else:
                    logs.append(f"equipment.{slot_id}: dict→跳过（无 name/id）")
            elif value is None:
                logs.append(f"equipment.{slot_id}: 值为 None，已跳过")
            else:
                resolved = self._resolve_equipment_value(slot_id, str(value), logs)
                fixed[slot_id] = resolved
        char.equipment = fixed
        return logs

    def _resolve_equipment_value(
        self, slot_id: str, value: str, logs: list[str],
    ) -> str:
        """将装备值解析为物品ID：已是ID则保留，是名称则查找ID。"""
        # 已经是合法的物品ID
        if self._item_system and self._item_system.get_item(value):
            return value
        # 尝试按名称查找
        if self._item_system:
            item = self._item_system.get_item_by_name(value)
            if item:
                logs.append(f"equipment.{slot_id}: '{value}'→'{item.id}'（名称→ID）")
                return item.id
        # 无法解析，保留原值
        logs.append(f"equipment.{slot_id}: '{value}' 未找到对应物品")
        return value

    def _fix_attrs_format(self, char: "Character") -> list[str]:
        """修正 attrs 中值的类型问题。"""
        logs: list[str] = []
        for key in list(char.attrs.keys()):
            val = char.attrs[key]
            if isinstance(val, int):
                continue
            try:
                char.attrs[key] = int(val)
                logs.append(f"attrs.{key}: {val!r}→{char.attrs[key]}（类型已修正）")
            except (ValueError, TypeError):
                char.attrs[key] = 0
                logs.append(f"attrs.{key}: {val!r}→0（无法转换，已置零）")
        return logs

    def _fix_tags_format(self, char: "Character") -> list[str]:
        """修正 tags 列表中的非 string 元素。"""
        logs: list[str] = []
        if not char.tags:
            return logs
        fixed: list[str] = []
        for tag in char.tags:
            if isinstance(tag, str):
                fixed.append(tag)
            else:
                converted = str(tag)
                fixed.append(converted)
                logs.append(f"tags: {tag!r}→'{converted}'（类型已修正）")
        char.tags = fixed
        return logs

    # ── 阶段2：存在性校验 ──

    def check_existence(self, char: "Character") -> list[str]:
        """校验 abilities 和 equipment 中的引用是否存在。"""
        logs: list[str] = []
        logs.extend(self._check_abilities_existence(char))
        logs.extend(self._check_equipment_existence(char))
        return logs

    def _check_abilities_existence(self, char: "Character") -> list[str]:
        """检查 abilities 中每个ID是否存在于世界技能表，不存在时尝试模糊匹配。"""
        logs: list[str] = []
        known_ids = self._get_known_ability_ids()
        if not known_ids:
            return logs

        fixed: list[str] = []
        for aid in char.abilities:
            if known_ids and aid in known_ids:
                fixed.append(aid)
            else:
                # 模糊匹配：LLM 可能填写名称而非 ID
                matched = self._fuzzy_match_ability(aid)
                if matched:
                    fixed.append(matched)
                    logs.append(f"abilities: '{aid}'→'{matched}'（模糊匹配替换ID）")
                else:
                    logs.append(f"abilities: '{aid}' 不存在于技能表，已移除")
        char.abilities = fixed
        return logs

    def _get_known_ability_ids(self) -> set[str]:
        """收集所有已知技能ID（world.abilities + game_state custom_abilities）。"""
        ids: set[str] = set()
        if self._world and hasattr(self._world, "abilities"):
            ids.update(self._world.abilities.keys())
        if self._game_state and hasattr(self._game_state, "get_all_registry_abilities"):
            ids.update(self._game_state.get_all_registry_abilities().keys())
        return ids

    @staticmethod
    def _normalize_name(name: str) -> str:
        """归一化名称：移除分隔符和空白，统一小写。"""
        return normalize_name(name)

    def _fuzzy_match_ability(self, query: str) -> str | None:
        """模糊匹配技能，返回匹配到的ID或 None。"""
        if not self._world or not hasattr(self._world, "abilities"):
            return None
        # 惰性构建归一化索引
        if not hasattr(self, "_ability_norm_index"):
            self._ability_norm_index: list[tuple[str, str, str]] = []
            for aid, adef in self._world.abilities.items():
                name = adef.get("name", "")
                norm = self._normalize_name(name)
                if norm:
                    self._ability_norm_index.append((aid, name, norm))
        return self._fuzzy_match(query, self._ability_norm_index)

    def _check_equipment_existence(self, char: "Character") -> list[str]:
        """检查 equipment 的 slot key 合法性和 item ID 存在性，不存在时尝试模糊匹配。"""
        logs: list[str] = []
        valid_slots = self._get_valid_slots()
        fixed: dict[str, str] = {}

        for slot_id, item_id in char.equipment.items():
            if valid_slots and slot_id not in valid_slots:
                logs.append(f"equipment: 无效部位 '{slot_id}'，已移除")
                continue
            if self._item_system and not self._item_exists(item_id):
                # 模糊匹配：LLM 可能填写装备名称而非 ID
                matched = self._fuzzy_match_item(item_id)
                if matched:
                    fixed[slot_id] = matched
                    logs.append(f"equipment.{slot_id}: '{item_id}'→'{matched}'（模糊匹配替换ID）")
                else:
                    logs.append(f"equipment.{slot_id}: '{item_id}' 不存在于物品表，已移除")
                continue
            fixed[slot_id] = item_id

        char.equipment = fixed
        return logs

    def _get_valid_slots(self) -> set[str]:
        """获取合法的装备部位ID集合。"""
        if not self._equipment_system:
            return set()
        return {s["id"] for s in self._equipment_system.get_slots() if "id" in s}

    def _item_exists(self, item_id: str) -> bool:
        """检查物品ID是否存在于物品系统。"""
        if not self._item_system:
            return True
        item = self._item_system.get_item(item_id)
        return item is not None

    def _fuzzy_match_item(self, query: str) -> str | None:
        """模糊匹配物品，返回匹配到的ID或 None。"""
        if not self._item_system:
            return None
        # 惰性构建归一化索引
        if not hasattr(self, "_item_norm_index"):
            self._item_norm_index: list[tuple[str, str, str]] = []
            for item in self._item_system.get_all_items():
                norm = self._normalize_name(item.name)
                if norm:
                    self._item_norm_index.append((item.id, item.name, norm))
        return self._fuzzy_match(query, self._item_norm_index)

    @staticmethod
    def _fuzzy_match(query: str, index: list[tuple[str, str, str]]) -> str | None:
        """共享模糊匹配：委托 core.types.fuzzy_match_by_name。"""
        from lingmo_engine.core.types import fuzzy_match_by_name
        return fuzzy_match_by_name(query, index)

    # ── 阶段2：范围校验 ──

    def check_range(self, char: "Character") -> list[str]:
        """校验 attrs 数值范围，裁剪超限值。"""
        logs: list[str] = []
        if not self._validator:
            return logs

        for key in list(char.attrs.keys()):
            rules = self._validator._get_attr_rules(key)
            val = char.attrs[key]
            cap = rules.get("hard_cap", 999)
            floor = rules.get("hard_min", 1)

            if val > cap:
                char.attrs[key] = cap
                logs.append(f"attrs.{key}: {val}→{cap}（超过上限，已裁剪）")
            elif val < floor:
                char.attrs[key] = floor
                logs.append(f"attrs.{key}: {val}→{floor}（低于下限，已补齐）")

        return logs

    # ── 公共接口 ──

    def validate_character(self, char: "Character") -> list[str]:
        """对单个角色执行阶段1+2校验。"""
        logs: list[str] = []
        logs.extend(self.check_format(char))
        logs.extend(self.check_existence(char))
        logs.extend(self.check_range(char))
        return logs
