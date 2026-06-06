"""装备属性概率驱动生成器 — 预算控制 + 权重抽签 + 属性叠加"""
from __future__ import annotations

import random
from typing import Optional


class EquipmentGenerator:
    """概率驱动装备属性生成器。"""

    def __init__(self, config: dict) -> None:
        self._weights = config.get("slot_stat_weights", {})
        self._ranges = config.get("stat_ranges", {})
        self._equip_budget = config.get("equip_budget", {})
        self._rarity_multiplier = config.get("rarity_multiplier", [])

    def generate_stats(
        self,
        slot_type: str,
        level: int,
        rarity: int,
        materials: list[dict] | None = None,
        seed: int | None = None,
        narrative_mode: bool = False,
    ) -> dict:
        """概率驱动生成装备属性。

        Args:
            narrative_mode: 叙事模式下跳过 stat_bonus 生成，
                           只返回空的 stat_bonus 和 narrative_effects。

        Returns:
            {"stat_bonus": dict, "buffs": list, "ability_count": int,
             "narrative_effects": dict}
        """
        # 叙事模式：跳过 stat_bonus 生成，仅分配法宝技能
        if narrative_mode:
            ability_count = 1 if slot_type == "life_treasure" else 0
            return {
                "stat_bonus": {},
                "buffs": [],
                "ability_count": ability_count,
                "narrative_effects": {},
            }

        slot_weights = self._weights.get(slot_type)
        if slot_weights is None or level < 0:
            # 槽位未配置权重 → 跳过，但仍分配法宝技能
            ability_count = 1 if slot_type == "life_treasure" else 0
            return {"stat_bonus": {}, "buffs": [], "ability_count": ability_count}

        # 权重为空字典（叙事模式）→ 跳过 stat_bonus 生成
        if not slot_weights:
            ability_count = 1 if slot_type == "life_treasure" else 0
            return {"stat_bonus": {}, "buffs": [], "ability_count": ability_count}

        rarity_mult = self._get_rarity_multiplier(rarity)
        raw_budget = self._equip_budget.get(level, 2)
        budget = max(0, int(raw_budget * rarity_mult))

        if budget <= 0:
            return {"stat_bonus": {}, "buffs": [], "ability_count": 0}

        rng = random.Random(seed)

        stat_names = list(slot_weights.keys())
        weights = [slot_weights[s] for s in stat_names]
        total_w = sum(weights)
        if total_w <= 0:
            return {"stat_bonus": {}, "buffs": [], "ability_count": 0}

        stat_bonus: dict[str, int] = {}
        draws = 0
        max_draws = budget * 10

        while budget > 0 and draws < max_draws:
            chosen = rng.choices(stat_names, weights=weights, k=1)[0]
            rng_val = self._ranges.get(chosen, {})
            base = rng_val.get("base", 1)
            cap = rng_val.get("cap", 10)

            current = stat_bonus.get(chosen, 0)
            if current >= cap:
                draws += 1
                continue

            budget -= 1
            draws += 1

            if current == 0:
                increment = min(base, cap)
            else:
                increment = 1
            stat_bonus[chosen] = min(current + increment, cap)

        # 法宝固定赋予 1 个技能槽，稀有度决定技能品质
        ability_count = 1 if slot_type == "life_treasure" else 0

        return {
            "stat_bonus": stat_bonus,
            "buffs": [],
            "ability_count": ability_count,
        }

    def _get_rarity_multiplier(self, rarity: int) -> float:
        """从配置读取 rarity 区间倍率，回退到默认 1.0。"""
        for entry in self._rarity_multiplier:
            if entry["min"] <= rarity <= entry["max"]:
                return entry["multiplier"]
        return 1.0
