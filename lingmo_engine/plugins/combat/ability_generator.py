"""能力生成器 — 词条(Affix)驱动生成

稀有度决定词条数量(affix_count)和每条最大堆叠(max_stack)。
LLM 提供名称、稀有度、词条类型列表，系统分配 stack 并计算最终数值。
"""

from __future__ import annotations

import logging
import math
import random
from typing import Optional

from lingmo_engine.core.safe_formula import safe_eval
from lingmo_engine.core.utils import generate_id, interpolate_table

logger = logging.getLogger(__name__)

VALID_CATEGORIES = frozenset({"attack", "heal", "support", "special", "divine"})
VALID_TARGETS = frozenset({"enemy", "self", "all_enemy", "all_ally"})

_CATEGORY_MAP = {"buff": "support", "debuff": "attack"}
_TARGET_MAP = {
    "ally": "self",
    "all": "all_enemy",
    "all_ally": "all_ally",
    "enemies": "all_enemy",
    "allies": "all_ally",
}

_RARITY_RANGE = (0, 100)
_COOLDOWN_RANGE = (0, 99)


# ═══════════════════════════════════════════════════════
# 词条池与数量修正
# ═══════════════════════════════════════════════════════


def _get_affix_pool(combat_only: bool, affix_defs: dict) -> list[str]:
    """获取词条池（战斗或非战斗）。"""
    pool = []
    for name, defn in affix_defs.items():
        is_combat = defn.get("combat", True)
        if combat_only == is_combat:
            pool.append(name)
    return pool


def _correct_affix_count(
    affixes: list[dict],
    target_count: int,
    affix_pool: list[str],
    exclusions: list[list[str]] | None = None,
    rng: random.Random | None = None,
) -> list[dict]:
    """修正词条数量：不足则从池中补，多余则裁剪。"""
    if rng is None:
        rng = random.Random()

    result = list(affixes[:target_count])

    if len(result) < target_count and affix_pool:
        existing_types = {a.get("type", "") for a in result}
        available = [t for t in affix_pool if t not in existing_types]

        if exclusions:
            for group in exclusions:
                group_set = set(group)
                present = existing_types & group_set
                if present:
                    available = [t for t in available if t not in group_set]

        rng.shuffle(available)
        for affix_type in available[: target_count - len(result)]:
            result.append({"type": affix_type})

    return result


# ═══════════════════════════════════════════════════════
# Stack 分配
# ═══════════════════════════════════════════════════════


def _assign_stacks(
    count: int,
    max_stack: int,
    guarantee: int | None,
    rng: random.Random | None = None,
) -> list[int]:
    """为每条词条分配 stack 值 [0, max_stack]，遵守保底规则。"""
    if rng is None:
        rng = random.Random()

    stacks = [rng.randint(0, max_stack) for _ in range(count)]

    if guarantee is not None and stacks:
        if not any(s >= guarantee for s in stacks):
            idx = rng.randint(0, len(stacks) - 1)
            stacks[idx] = guarantee

    return stacks


# ═══════════════════════════════════════════════════════
# 数值计算
# ═══════════════════════════════════════════════════════


def _calculate_affix_values(
    affixes: list[dict],
    stacks: list[int],
    affix_defs: dict,
) -> list[dict]:
    """根据 base + stack × stack_increment 计算每条词条的最终效果值。"""
    effects = []

    for affix, stack in zip(affixes, stacks):
        affix_type = affix.get("type", "")
        defn = affix_defs.get(affix_type, {})
        base = defn.get("base", {})
        inc = defn.get("stack_increment", {})

        eff: dict = {"type": affix_type}

        # 复制定性参数（target, duration, stat, element 等）
        for k, v in affix.items():
            if k not in ("type", "weight"):
                eff[k] = v

        # 计算定量参数: base + stack × increment
        for param, base_val in base.items():
            increment = inc.get(param, base_val)
            eff[param] = base_val + stack * increment

        # buff/debuff: 自动填充 default_stat
        if affix_type in ("buff", "debuff") and "stat" not in eff:
            default_stat = defn.get("default_stat")
            if default_stat:
                eff["stat"] = default_stat

        # dot/fixed_dot: 自动填充 default_duration
        if affix_type in ("dot", "fixed_dot") and "duration" not in eff:
            default_duration = defn.get("default_duration", 3)
            eff["duration"] = default_duration

        # debuff: modifier 取负
        if affix_type == "debuff" and "modifier" in eff:
            eff["modifier"] = -eff["modifier"]

        effects.append(eff)

    return effects


# ═══════════════════════════════════════════════════════
# 消耗 / 冷却自动计算
# ═══════════════════════════════════════════════════════


def auto_compute_costs(
    effects: list[dict],
    templates: dict,
    tags: list[str] | None = None,
    tag_cost_map: dict[str, list[str]] | None = None,
    category: str | None = None,
) -> list[dict]:
    """根据效果模板的 auto_cost formula 计算基础消耗（不含等级缩放）。

    神通(category=divine)只消耗灵力(spiritual_power)。
    非神通根据 tags 消耗神识/体力，无匹配 tag 时默认消耗神识。
    """
    base_amount = 0
    for eff in effects:
        tmpl = templates.get(eff["type"], {})
        auto = tmpl.get("auto_cost")
        if not auto:
            continue
        formula = auto["formula"]
        namespace = _build_formula_namespace(eff)
        base_amount += max(1, int(safe_eval(formula, namespace)))

    cost_map: dict[str, int] = {}
    if base_amount > 0:
        if category == "divine":
            cost_map["spiritual_power"] = base_amount
        else:
            if tags and tag_cost_map:
                for resource, tag_list in tag_cost_map.items():
                    if any(t in tag_list for t in tags):
                        cost_map[resource] = base_amount
            if not cost_map:
                cost_map["divine_sense"] = base_amount

    return [{"resource": s, "amount": a} for s, a in cost_map.items()]


def auto_compute_cooldown(effects: list[dict], templates: dict) -> int:
    """取所有效果的 auto_cooldown 最大值。"""
    max_cd = 0
    for eff in effects:
        tmpl = templates.get(eff["type"], {})
        formula = tmpl.get("auto_cooldown")
        if not formula:
            continue
        namespace = _build_formula_namespace(eff)
        cd = max(0, int(safe_eval(formula, namespace)))
        max_cd = max(max_cd, cd)
    return max_cd


def _build_formula_namespace(eff: dict) -> dict:
    """构建公式计算命名空间。"""
    return {
        "power": eff.get("power", 0),
        "modifier": eff.get("modifier", 0),
        "duration": eff.get("duration", 0),
        "value": eff.get("value", 0),
        "count": eff.get("count", 0),
        "ratio": eff.get("ratio", 0),
        "chance": eff.get("chance", 0),
        "abs": abs,
        "max": max,
        "min": min,
        "floor": math.floor,
        "ceil": math.ceil,
    }


def _lookup_scale(level: int, table: dict) -> float:
    """从缩放表中查值，表外线性插值。"""
    return interpolate_table(level, table)


# ═══════════════════════════════════════════════════════
# 主入口: 词条驱动技能生成
# ═══════════════════════════════════════════════════════


def affix_generate_ability(
    ability_input: dict,
    affix_defs: dict,
    rarity_info: dict,
    *,
    tag_cost_map: dict | None = None,
    exclusions: list[list[str]] | None = None,
    seed: int | None = None,
    combat_only: bool = True,
    warnings: list[str] | None = None,
) -> Optional[dict]:
    """词条驱动技能生成。

    Args:
        ability_input: {name, rarity, category, description, summary, tags,
                        affixes: [{type, target?, duration?}]}
        affix_defs: effect_affixes.yaml 中的 effect_affixes 部分
        rarity_info: {affix_count, max_stack, guarantee, name, color}
        tag_cost_map: tag → 附加资源映射
        exclusions: 效果互斥规则
        seed: 随机种子
        combat_only: True=战斗词条池，False=非战斗词条池
        warnings: 警告列表
    """
    raw_affixes = ability_input.get("affixes", [])
    if not raw_affixes:
        raw_affixes = ability_input.get("effect_slots", [])
    if not raw_affixes:
        return None

    affix_count = rarity_info.get("affix_count", 1)
    max_stack = rarity_info.get("max_stack", 2)
    guarantee = rarity_info.get("guarantee")

    rng = random.Random(seed)

    # 1. 过滤无效词条类型
    valid_affixes = []
    for a in raw_affixes:
        affix_type = a.get("type", "")
        if affix_type in affix_defs:
            valid_affixes.append(a)
        else:
            msg = f"WARNING: 词条类型 '{affix_type}' 无效，已跳过"
            logger.warning("未知词条类型 '%s'，已跳过", affix_type)
            if warnings is not None:
                warnings.append(msg)

    if not valid_affixes:
        return None

    # 1.5 互斥校验：移除与已有词条冲突的词条（保留先出现的）
    if exclusions:
        seen_types = set()
        filtered = []
        for a in valid_affixes:
            t = a.get("type", "")
            conflict = False
            for group in exclusions:
                if t in group:
                    for other in group:
                        if other != t and other in seen_types:
                            conflict = True
                            break
                if conflict:
                    break
            if conflict:
                msg = f"WARNING: 词条 '{t}' 与已有词条互斥，已移除"
                logger.warning("词条 '%s' 互斥冲突，已移除", t)
                if warnings is not None:
                    warnings.append(msg)
            else:
                seen_types.add(t)
                filtered.append(a)
        valid_affixes = filtered

    # 2. 修正词条数量
    affix_pool = _get_affix_pool(combat_only, affix_defs)
    corrected = _correct_affix_count(valid_affixes, affix_count, affix_pool, exclusions, rng)

    # 3. 分配 stack
    stacks = _assign_stacks(len(corrected), max_stack, guarantee, rng)

    # 4. 计算数值
    effects = _calculate_affix_values(corrected, stacks, affix_defs)

    if not effects:
        return None

    # 4.5 传播 ability 级 target 到缺少 target 的 effect
    ability_target = ability_input.get("target", "")
    if ability_target:
        if ability_target not in VALID_TARGETS:
            ability_target = _TARGET_MAP.get(ability_target, "")
        if ability_target:
            for eff in effects:
                eff.setdefault("target", ability_target)

    # 5. 自动计算消耗和冷却
    costs = auto_compute_costs(
        effects, affix_defs,
        tags=ability_input.get("tags"),
        tag_cost_map=tag_cost_map,
        category=ability_input.get("category"),
    )
    cooldown = auto_compute_cooldown(effects, affix_defs)

    ability_id = generate_ability_id(ability_input.get("name", ""))

    return validate_ability_fields({
        "id": ability_id,
        "name": ability_input.get("name", ""),
        "summary": ability_input.get("summary", ""),
        "category": ability_input.get("category", "attack"),
        "description": ability_input.get("description", ""),
        "rarity": ability_input.get("rarity", 0),
        "costs": costs,
        "cooldown": cooldown,
        "effects": effects,
        "tags": ability_input.get("tags", []),
    })


# ═══════════════════════════════════════════════════════
# 字段校验
# ═══════════════════════════════════════════════════════


def generate_ability_id(name: str = "") -> str:
    """生成唯一技能 ID。"""
    return generate_id("ability")


def validate_ability_fields(ability: dict, templates: dict | None = None) -> dict:
    """校验并纠正技能字段。"""
    cat = ability.get("category", "")
    if cat not in VALID_CATEGORIES:
        corrected = _CATEGORY_MAP.get(cat, "special")
        logger.info("技能 '%s' category '%s' 无效，纠正为 '%s'",
                     ability.get("name", "?"), cat, corrected)
        ability["category"] = corrected

    rarity = ability.get("rarity", 0)
    if not isinstance(rarity, (int, float)):
        ability["rarity"] = 25
    else:
        ability["rarity"] = max(_RARITY_RANGE[0], min(_RARITY_RANGE[1], int(rarity)))

    cd = ability.get("cooldown", 0)
    if not isinstance(cd, (int, float)):
        ability["cooldown"] = 0
    else:
        ability["cooldown"] = max(_COOLDOWN_RANGE[0], min(_COOLDOWN_RANGE[1], int(cd)))

    costs = ability.get("costs", [])
    if isinstance(costs, list):
        valid_costs = []
        for c in costs:
            if isinstance(c, dict) and "resource" in c and "amount" in c:
                amt = c["amount"]
                if isinstance(amt, (int, float)) and amt >= 0:
                    valid_costs.append({"resource": str(c["resource"]), "amount": int(amt)})
        ability["costs"] = valid_costs

    effects = ability.get("effects", [])
    if isinstance(effects, list):
        valid_effects = []
        for eff in effects:
            if not isinstance(eff, dict):
                continue
            tgt = eff.get("target", "")
            if tgt and tgt not in VALID_TARGETS:
                corrected = _TARGET_MAP.get(tgt, "enemy")
                logger.info("技能 '%s' 效果 target '%s' 无效，纠正为 '%s'",
                             ability.get("name", "?"), tgt, corrected)
                eff["target"] = corrected
            if "duration" in eff:
                dur = eff["duration"]
                if isinstance(dur, (int, float)):
                    eff["duration"] = max(0, int(dur))
                else:
                    eff["duration"] = 1
            for num_field in ("power", "modifier", "value", "count", "ratio", "chance"):
                if num_field in eff and not isinstance(eff[num_field], (int, float)):
                    eff[num_field] = 0
            valid_effects.append(eff)
        ability["effects"] = valid_effects

    return ability
