"""Ashenveil — Dark Fantasy combat overrides.

Reuses engine damage formula with 4-element system (Fire/Frost/Nature/Shadow),
enemy tag bonuses, and tier-based multipliers.
"""

from __future__ import annotations

import random

# ═══════════════════════════════════════
# 层级系数（替代无极的 14 境系数）
# ═══════════════════════════════════════
_TIER_TABLE: list[dict] = [
    {"min": 1, "max": 5, "mult": 1.0, "name": "Commoner"},
    {"min": 6, "max": 10, "mult": 1.5, "name": "Veteran"},
    {"min": 11, "max": 15, "mult": 2.5, "name": "Elite"},
    {"min": 16, "max": 20, "mult": 4.0, "name": "Legend"},
]

# ═══════════════════════════════════════
# 4 元素克制表
# ═══════════════════════════════════════
_ELEMENT_ADVANTAGE: dict[str, str] = {
    "fire": "nature",
    "frost": "fire",
    "nature": "frost",
}
_ADVANTAGE_BONUS = 0.30
_DISADVANTAGE_PENALTY = -0.20

# ═══════════════════════════════════════
# 敌人标签 → 元素加成
# ═══════════════════════════════════════
_TAG_ELEMENT_BONUS: dict[str, tuple[str, float]] = {
    "Undead": ("fire", 0.50),
    "Beast": ("nature", 0.50),
    "Aberration": ("shadow", 0.50),
}

_ASHEN_BONUS = 0.25


def _get_tier_mult(level: int) -> float:
    """根据等级返回层级系数。"""
    for tier in _TIER_TABLE:
        if tier["min"] <= level <= tier["max"]:
            return tier["mult"]
    return 1.0


def _resolve_element_bonus(atk_elements: list[str],
                           defender_elements: list[str] | None = None,
                           defender_tags: list[str] | None = None) -> float:
    """计算元素克制 + 标签加成（加算修正）。

    元素克制：Fire>Nature>Frost>Fire，克制+30%，被克-20%。
    Shadow 中立，不参与克制循环。
    标签加成：Undead 受 Fire +50%，Beast 受 Nature +50%，Aberration 受 Shadow +50%。
    """
    bonus = 0.0

    # 元素克制循环
    if defender_elements:
        for atk_elem in atk_elements:
            if atk_elem == "shadow":
                continue
            strong_vs = _ELEMENT_ADVANTAGE.get(atk_elem)
            if strong_vs and strong_vs in defender_elements:
                bonus += _ADVANTAGE_BONUS
            # 检查是否被对方元素克制
            for def_elem in defender_elements:
                if def_elem == "shadow":
                    continue
                if _ELEMENT_ADVANTAGE.get(def_elem) == atk_elem:
                    bonus += _DISADVANTAGE_PENALTY

    # 标签元素加成
    if defender_tags:
        for tag in defender_tags:
            if tag in _TAG_ELEMENT_BONUS:
                bonus_element, bonus_val = _TAG_ELEMENT_BONUS[tag]
                if bonus_element in atk_elements:
                    bonus += bonus_val

    return bonus


def calculate_damage(caster, target, attrs_schema: dict,
                     effect: dict, is_crit: bool) -> int:
    """非线性伤害公式 + 层级和元素修正。

    base_damage = atk² × power / (atk + def × R)
    final = base_damage × (1 + tag_bonus + element_bonus + ashen_bonus)
            × tier_mult × crit × variance
    """
    atk = max(caster.attrs.get("force", 0), 1)
    defense = target.attrs.get("tenacity", 0)
    power = effect.get("power", 1.0)
    tags = effect.get("tags", [])

    # 基础伤害
    R = 6
    base_damage = (atk * atk * power) / (atk + defense * R)

    # 标签加成
    tag_bonus = 0.0

    # 元素加成（含克制循环 + 标签加成）
    effect_elements = [t for t in tags if t in ("fire", "frost", "nature", "shadow")]
    defender_elements = [t for t in target.extra.get("element_tags", [])
                         if t in ("fire", "frost", "nature", "shadow")]
    defender_tags = list(target.extra.get("tags", []))
    element_bonus = _resolve_element_bonus(effect_elements, defender_elements, defender_tags)

    # Ashen 类别加成
    ashen_bonus = _ASHEN_BONUS if effect.get("_category") == "ashen" else 0.0

    # 层级系数
    tier_mult = _get_tier_mult(caster.level)

    # 加算修正
    additive_mult = 1.0 + tag_bonus + element_bonus + ashen_bonus
    final = base_damage * additive_mult * tier_mult

    # 暴击
    if is_crit:
        has_tag_match = tag_bonus > 0 or element_bonus > 0
        crit_mult = 2.0 if has_tag_match else 1.5
        final *= crit_mult

    # 方差
    variance = random.uniform(0.85, 1.15)
    final *= variance

    return max(1, int(final))


def apply_pre_combat_amplification(combatant) -> None:
    """战前钩子 — 根据层级系数增幅所有战斗属性。

    签名与无极一致：接收单个 combatant，原地修改属性。
    """
    mult = _get_tier_mult(combatant.level)
    if mult <= 1.0:
        return

    # 写入层级信息
    combatant.extra["tier_mult"] = mult

    # 战斗属性增幅
    for key in ("force", "tenacity", "agility"):
        if key in combatant.attrs:
            combatant.attrs[key] = round(combatant.attrs[key] * mult)

    # 生命池增幅（Combatant 直接字段）
    if hasattr(combatant, "max_hp") and combatant.max_hp > 0:
        old_max = combatant.max_hp
        combatant.max_hp = round(old_max * mult)
        combatant.hp = round(combatant.hp * mult)


# 兼容无极钩子名
apply_cultivation_amplification = apply_pre_combat_amplification
