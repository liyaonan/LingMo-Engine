"""灵力封存物品制作核心计算逻辑"""
from __future__ import annotations

import random
from typing import Optional


class CraftingEngine:
    """制作系统核心引擎，负责损耗率、等级判定、品质、budget 计算。"""

    def __init__(self, config: dict) -> None:
        self._config = config
        self._themes = config.get("themes", {})
        self._sealing = config.get("sealing", {})
        self._quality = config.get("quality", {})
        self._budget = config.get("budget", {})
        self._level_thresholds = sorted(
            config.get("level_thresholds", []),
            key=lambda t: t.get("min_power", 0),
        )
        self._equip_slots: list[dict] = []

    # ── 公开接口 ──────────────────────────

    def calc_loss_rate(self, theme: str, skill_value: int, is_bonus: bool = True) -> float:
        """计算损耗率。

        Args:
            theme: 题材名称（符箓/阵旗/法宝/丹药）
            skill_value: 对应技能值 0~100
            is_bonus: 是否享受对应技能加成（专业道=True，其他道=False）

        Returns:
            损耗率，范围 [min_loss_rate, base_loss_rate]
        """
        if not is_bonus:
            return self._sealing.get("base_loss_rate", 0.40)

        base = self._sealing.get("base_loss_rate", 0.40)
        per_point = self._sealing.get("skill_bonus_per_point", 0.005)
        minimum = self._sealing.get("min_loss_rate", 0.05)

        return round(max(minimum, base - skill_value * per_point), 4)

    def calc_effective_power(self, spiritual_power: int, loss_rate: float) -> int:
        """计算有效灵力。"""
        return int(spiritual_power * (1 - loss_rate))

    def determine_level(self, effective_power: int) -> dict:
        """根据有效灵力判定物品等级。

        Returns:
            {"level": int, "label": str}
        """
        result = {"level": 0, "label": "凡品"}
        for threshold in self._level_thresholds:
            if effective_power >= threshold["min_power"]:
                result = {"level": threshold["level"], "label": threshold["label"]}
            else:
                break
        return result

    def get_level_info(self, level: int) -> dict:
        """根据等级反查标签和代表性灵力。

        Returns:
            {"level": int, "label": str, "representative_power": int}
        """
        for threshold in self._level_thresholds:
            if threshold["level"] == level:
                return {
                    "level": threshold["level"],
                    "label": threshold["label"],
                    "representative_power": threshold["min_power"],
                }
        return {"level": 0, "label": "凡品", "representative_power": 0}

    def calc_quality(self, materials: list[dict], base_roll: Optional[int] = None) -> int:
        """计算成品品质 (rarity)。

        Args:
            materials: 材料列表，每项含 "rarity" 字段
            base_roll: 基础随机值，None 则自动生成

        Returns:
            rarity 值，范围 [1, 100]
        """
        if base_roll is None:
            roll_min = self._quality.get("base_roll_min", 1)
            roll_max = self._quality.get("base_roll_max", 100)
            base_roll = random.randint(roll_min, roll_max)

        if not materials:
            return max(1, min(100, base_roll))

        ratio = self._quality.get("material_bonus_ratio", 0.3)
        avg_rarity = sum(m.get("rarity", 1) for m in materials) / len(materials)
        bonus = int(avg_rarity * ratio)

        return max(1, min(100, base_roll + bonus))

    def calc_budget(self, effective_power: int, rarity: int) -> int:
        """根据有效灵力和品质计算效果 budget。"""
        multiplier = self._get_rarity_multiplier(rarity)
        return max(0, int(effective_power * multiplier))

    def get_theme_config(self, theme: str) -> Optional[dict]:
        """获取题材配置。"""
        return self._themes.get(theme)

    def calc_material_power(self, rarity: int) -> int:
        """根据 rarity 计算材料灵力值。"""
        mp = self._config.get("material_power", {})
        base = mp.get("base", 2)
        multiplier = mp.get("multiplier", 1.146)
        return round(base * multiplier ** rarity)

    def calc_max_spiritual_power(self, materials: list[dict]) -> int:
        """计算材料灵力求和，作为封存灵力上限。"""
        return sum(m.get("spirit_power", 0) for m in materials)

    def validate_input(
        self,
        theme: str,
        material_ids: list[str],
        spiritual_power: int,
        max_spiritual_power: int = 0,
    ) -> tuple[bool, str]:
        """校验制作输入参数。"""
        if theme not in self._themes:
            return False, f"无效题材: {theme}"
        max_slots = self._sealing.get("max_slots", 6)
        if len(material_ids) > max_slots:
            return False, f"材料数量超过最大槽位({max_slots})"
        if len(material_ids) == 0:
            return False, "必须至少投入1个材料"
        if spiritual_power <= 0:
            return False, "封入灵力必须大于0"
        if spiritual_power > max_spiritual_power:
            return False, f"封入灵力({spiritual_power})超过材料灵力上限({max_spiritual_power})"
        return True, ""

    def get_bonus_skill(self, theme: str) -> str:
        """获取题材对应的加成技能名称。"""
        theme_config = self._themes.get(theme, {})
        return theme_config.get("bonus_skill", "")

    def get_default_tags(self, theme: str) -> list[str]:
        """获取题材默认 Tags。"""
        theme_config = self._themes.get(theme, {})
        return theme_config.get("default_tags", [])

    def get_equipment_config(self) -> dict:
        """获取装备生成配置节。"""
        return self._config.get("equipment", {})

    def get_equip_slots(self) -> list[dict]:
        """获取已加载的装备槽位定义。"""
        return self._equip_slots

    def load_equip_slots(self, slots: list[dict]) -> None:
        """加载装备槽位定义（由 plugin.on_load 调用）。"""
        self._equip_slots = slots

    # ── 内部方法 ──────────────────────────

    def _get_rarity_multiplier(self, rarity: int) -> float:
        """根据 rarity 值获取倍率。"""
        for entry in self._budget.get("rarity_multiplier", []):
            if entry["min"] <= rarity <= entry["max"]:
                return entry["multiplier"]
        return 1.0
