"""战斗公式：伤害计算、追击判定、状态效果。"""

from __future__ import annotations

import random


def get_attr_by_role(combatant, attrs_schema: dict, role: str) -> int:
    """按 combat_role 查找属性值，找不到返回 0"""
    for name, defn in attrs_schema.items():
        if defn.get("combat_role") == role:
            return combatant.attrs.get(name, defn.get("default", 0))
    return 0


def get_attr_name_by_role(attrs_schema: dict, role: str) -> str | None:
    """按 combat_role 查找属性名"""
    for name, defn in attrs_schema.items():
        if defn.get("combat_role") == role:
            return name
    return None


def calc_damage(caster, target, attrs_schema: dict, power: float = 1.0) -> int:
    """基础伤害 = attack * power - defense * 0.5，下限1"""
    atk = get_attr_by_role(caster, attrs_schema, "attack")
    defense = get_attr_by_role(target, attrs_schema, "defense")
    base = atk * power - defense * 0.5
    variance = random.uniform(0.85, 1.15)
    return max(1, int(base * variance))


def calc_pursuit_chance(caster, target, attrs_schema: dict) -> float:
    """追击概率 = 速度差比 × 25%。范围 0%~50%。

    攻击必中，速度优势转化为追击（额外一次伤害，系数 0.5）。
    """
    caster_spd = get_attr_by_role(caster, attrs_schema, "speed")
    target_spd = get_attr_by_role(target, attrs_schema, "speed")
    if caster_spd <= 0:
        return 0.0
    speed_ratio = (caster_spd - target_spd) / caster_spd
    return max(0.0, min(0.50, speed_ratio * 0.25))


def calc_crit(crit_rate: float = 0.1) -> bool:
    return random.random() < crit_rate


def exp_for_kill(enemy_level: int) -> int:
    """[废弃] 请使用 calculate_rewards。保留用于向后兼容。"""
    return enemy_level * 10 + random.randint(0, 10)


def calculate_rewards(enemy: "Combatant") -> dict:
    """默认战利品计算（level 驱动），世界 combat.py 可覆盖。

    返回格式：{"exp_gained": int, "loot": list[dict]}
    """
    exp = enemy.level * 10 + random.randint(0, 10)
    return {"exp_gained": exp, "loot": []}


def calc_ability_damage(caster, target, attrs_schema: dict, power: float) -> int:
    return calc_damage(caster, target, attrs_schema, power)


def calc_defense_reduction(target, attrs_schema: dict) -> float:
    """防御状态下的伤害减免比例（基于防御力，上限75%）"""
    defense = get_attr_by_role(target, attrs_schema, "defense")
    return min(0.75, 0.3 + defense * 0.005)


def calc_heal(caster, attrs_schema: dict, power: float = 1.0) -> int:
    """治疗量 = magic * power * 0.8 ± 10%"""
    magic = get_attr_by_role(caster, attrs_schema, "magic") or get_attr_by_role(caster, attrs_schema, "attack")
    base = magic * power * 0.8
    variance = random.uniform(0.9, 1.1)
    return max(1, int(base * variance))


def calc_flee_chance(player_level: int, enemy_level: int) -> float:
    base = 0.5
    level_bonus = (player_level - enemy_level) * 0.1
    return max(0.1, min(0.95, base + level_bonus))


def loot_drop(loot_table: list[dict]) -> list[dict]:
    drops = []
    for entry in loot_table:
        if random.random() < entry.get("chance", 1.0):
            drops.append({
                "item_id": entry["item_id"],
                "quantity": entry.get("quantity", 1),
            })
    return drops


def normalize_element_ratios(elements: list[dict]) -> list[dict]:
    """归一化 ratio，使总和为 1.0"""
    if not elements:
        return []
    total = sum(e.get("ratio", 0.0) for e in elements)
    if total <= 0:
        return []
    return [{**e, "ratio": e.get("ratio", 0.0) / total} for e in elements]


def calc_element_modifier(
    caster_tags: list[str],
    target_tags: list[str],
    elements: list[dict],
    affinity_bonus: float,
    resistance_reduction: float,
) -> float:
    """计算多元素复合伤害的综合倍率。

    Args:
        caster_tags: 施法者的元素标签列表
        target_tags: 目标的元素标签列表
        elements: 技能的元素列表 [{"id": "fire", "ratio": 0.6}, ...]
        affinity_bonus: 攻方标签匹配时的伤害加成倍率
        resistance_reduction: 守方标签匹配时的伤害减免倍率

    Returns:
        综合倍率，无元素时返回 1.0
    """
    if not elements:
        return 1.0
    total = 0.0
    for elem in elements:
        ratio = elem.get("ratio", 1.0)
        aff = affinity_bonus if elem["id"] in caster_tags else 0.0
        res = resistance_reduction if elem["id"] in target_tags else 0.0
        total += ratio * (1.0 + aff) * (1.0 - res)
    return total
