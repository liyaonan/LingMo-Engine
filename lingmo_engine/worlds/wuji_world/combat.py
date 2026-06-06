"""无极 — 修仙战斗公式。

覆盖默认公式，引入境界增幅、标签系统、五行生克。
"""

from __future__ import annotations
import random
from pathlib import Path
import yaml

_schema_cache: dict | None = None


def _load_cultivation_schema() -> dict:
    """加载 cultivation.yaml。"""
    global _schema_cache
    if _schema_cache is not None:
        return _schema_cache
    schema_path = Path(__file__).resolve().parent / "cultivation.yaml"
    if schema_path.exists():
        with open(schema_path, "r", encoding="utf-8") as f:
            _schema_cache = yaml.safe_load(f) or {}
    else:
        _schema_cache = {}
    return _schema_cache


def clear_schema_cache() -> None:
    """清除 cultivation.yaml 缓存，用于热重载或测试。"""
    global _schema_cache
    _schema_cache = None


def _get_stage(stage_id: str) -> dict | None:
    schema = _load_cultivation_schema()
    for stage in schema.get("stages", []):
        if stage.get("id") == stage_id:
            return stage
    return None


def _get_path_config(path_id: str) -> dict | None:
    """获取修炼道路配置（path_mods + tag_rules）。"""
    schema = _load_cultivation_schema()
    for path_id_key, path_data in schema.get("cultivation_paths", {}).items():
        if path_id_key == path_id:
            return path_data
    return None


def _get_stage_order(stage_id: str) -> int:
    stage = _get_stage(stage_id)
    return stage.get("order", 0) if stage else 0


def level_to_stage(level: int) -> str | None:
    """将等级数字转换为境界 id。未找到返回 None。"""
    schema = _load_cultivation_schema()
    for stage in schema.get("stages", []):
        if stage.get("order") == level:
            return stage["id"]
    return None


def stage_to_level(stage_id: str) -> int:
    """将境界 id 转换为等级（= order）。未找到返回 0。"""
    return _get_stage_order(stage_id)


# ═══════════════════════════════════════
# 境界系数
# ═══════════════════════════════════════

def get_stage_mult(stage_id: str) -> float:
    """获取境界的 combat_mult。未找到返回 1.0。"""
    stage = _get_stage(stage_id)
    if stage:
        return stage.get("combat_mult", 1.0)
    return 1.0


def get_sub_stage_factor(stage_id: str, sub_stage: str | None = None) -> float:
    """计算子阶段修正因子。多子阶段时首个 ×0.8，末个 ×1.1，中间线性。

    "consummate"（圆满）视为末位子阶段（×1.1）。
    """
    stage = _get_stage(stage_id)
    if not stage:
        return 1.0
    sub_stages = stage.get("sub_stages", [])
    if len(sub_stages) <= 1:
        return 1.0
    if sub_stage is None:
        return 1.0
    # 圆满 → 等同末位子阶段
    if str(sub_stage) == "consummate":
        return 1.1
    # 兼容 int/str 类型（YAML 加载 int 列表，外部可能传 str）
    normalized_sub = [str(s) for s in sub_stages]
    try:
        idx = normalized_sub.index(str(sub_stage))
    except ValueError:
        return 1.0
    progress = idx / (len(sub_stages) - 1)
    return 0.8 + 0.3 * progress


# ═══════════════════════════════════════
# 战斗增幅
# ═══════════════════════════════════════

def get_stage_mult_for_level(level: int) -> float:
    """根据等级返回境界增幅系数，用于显示时增幅。"""
    stage_id = level_to_stage(level)
    if not stage_id:
        return 1.0
    return get_stage_mult(stage_id)


def amplify_player_snapshot(pdata: dict) -> dict:
    """对玩家快照 dict 应用境界增幅（仅影响显示，不修改原始数据）。

    增幅逻辑与 apply_cultivation_amplification 对齐：
    - vitality / max_vitality 同比增幅
    - force / tenacity / agility 增幅
    - max_divine_sense / max_stamina 增幅，当前值保持比例
    """
    level = pdata.get("level", 0)
    mult = get_stage_mult_for_level(level)
    if mult <= 1.0:
        return pdata

    result = dict(pdata)

    # vitality / max_vitality（round 减少截断漂移）
    if result.get("max_vitality", 0) > 0:
        old_max = result["max_vitality"]
        result["max_vitality"] = round(old_max * mult)
        ratio = result.get("vitality", 0) / old_max
        result["vitality"] = round(result["max_vitality"] * ratio)

    # force / tenacity / agility
    for key in ("force", "tenacity", "agility"):
        val = result.get(key)
        if val is not None:
            result[key] = round(val * mult)

    # 资源池 max
    for max_key in ("max_divine_sense", "max_stamina"):
        old_max = result.get(max_key)
        if old_max:
            cur_key = max_key[4:]
            result[max_key] = round(old_max * mult)
            ratio = result.get(cur_key, 0) / old_max if old_max > 0 else 1.0
            result[cur_key] = round(result[max_key] * ratio)

    return result


def revert_player_amplification(pdata: dict) -> dict:
    """将增幅后的战斗属性还原为基础值（战后保存用）。"""
    level = pdata.get("level", 0)
    mult = get_stage_mult_for_level(level)
    if mult <= 1.0:
        return pdata

    result = dict(pdata)

    # vitality / max_vitality（round 减少截断漂移）
    max_vitality = result.get("max_vitality", 0)
    if max_vitality > 0:
        result["max_vitality"] = max(1, round(max_vitality / mult))
        result["vitality"] = max(1, round(result.get("vitality", 0) / mult))

    # force / tenacity / agility
    for key in ("force", "tenacity", "agility"):
        val = result.get(key)
        if val is not None:
            result[key] = max(1, round(val / mult))

    # 资源池 max
    for max_key in ("max_divine_sense", "max_stamina"):
        old_max = result.get(max_key)
        if old_max:
            cur_key = max_key[4:]
            result[max_key] = max(1, round(old_max / mult))
            result[cur_key] = max(1, round(result.get(cur_key, 0) / mult))

    return result


def apply_cultivation_amplification(combatant) -> None:
    """通过等级查询境界 combat_mult，对敌我双方统一增幅所有战斗属性。"""
    stage_id = level_to_stage(combatant.level)
    if not stage_id:
        return
    mult = get_stage_mult(stage_id)
    if mult <= 1.0:
        return
    # 仅玩家写入 cultivation_stage（怪物由 level 推导，不需要持久化）
    if combatant.is_player:
        combatant.extra.setdefault("cultivation_stage", stage_id)
    combatant.extra["stage_order"] = _get_stage_order(stage_id)

    # 战斗属性增幅（round 与 amplify_player_snapshot/revert 保持一致）
    for key in ("force", "tenacity", "agility"):
        if key in combatant.attrs:
            combatant.attrs[key] = round(combatant.attrs[key] * mult)

    # 生命池增幅（Combatant 直接字段）
    if combatant.max_hp > 0:
        old_max = combatant.max_hp
        combatant.max_hp = round(old_max * mult)
        ratio = combatant.hp / old_max
        combatant.hp = round(combatant.max_hp * ratio)

    # 其他资源池增幅（attrs 中）
    for max_key in ("max_divine_sense", "max_stamina"):
        if max_key in combatant.attrs:
            cur_key = max_key[4:]  # "max_divine_sense" → "divine_sense"
            old_max = combatant.attrs[max_key]
            combatant.attrs[max_key] = round(old_max * mult)
            ratio = combatant.attrs.get(cur_key, 0) / old_max if old_max > 0 else 1.0
            combatant.attrs[cur_key] = round(combatant.attrs[max_key] * ratio)


def apply_pre_combat_amplification(combatant) -> None:
    """通用战斗前增幅入口（解耦后的钩子名）。"""
    return apply_cultivation_amplification(combatant)


# ═══════════════════════════════════════
# 标签解析
# ═══════════════════════════════════════

def resolve_tag_mods(path_id: str, tags: list[str], role: str,
                     source: str | None = None,
                     mastery_value: int = 0) -> dict:
    """解析标签规则，返回各类型修正值的字典。

    返回 dict，至少包含 "damage_bonus" 键。
    可能包含：def_ignore, self_damage, lifesteal, stat_buff 等。

    mastery_value: 专属属性值（0-100），仅增幅 damage_multiply 类型规则。
    """
    if not path_id or not tags:
        return {"damage_bonus": 0.0}
    path_config = _get_path_config(path_id)
    if not path_config:
        return {"damage_bonus": 0.0}
    tag_rules = path_config.get("tag_rules", [])
    if not tag_rules:
        return {"damage_bonus": 0.0}

    # 读取 mastery_rules 配置
    schema = _load_cultivation_schema()
    mastery_rules = schema.get("mastery_rules", {})
    max_boost = mastery_rules.get("max_boost", 0.20)

    damage_bonus = 0.0
    special_effects: dict[str, float] = {}

    for rule in tag_rules:
        if rule.get("role") != role:
            continue
        rule_tags = rule.get("tags")
        if rule_tags is None:
            continue
        if not any(t in tags for t in rule_tags):
            continue
        # 规则指定了 source 时，调用方也必须提供匹配的 source
        rule_source = rule.get("source")
        if rule_source:
            if not source or rule_source != source:
                continue

        rule_type = rule.get("type", "damage_multiply")
        value = rule.get("value", 1.0)

        # 仅对 damage_multiply 类型应用 mastery 增幅
        if rule_type == "damage_multiply" and mastery_value > 0:
            bonus = value - 1.0
            bonus = bonus * (1 + mastery_value / 100 * max_boost)
            damage_bonus += bonus
        elif rule_type == "damage_multiply":
            damage_bonus += value - 1.0
        else:
            if rule_type in special_effects:
                special_effects[rule_type] = max(special_effects[rule_type], value)
            else:
                special_effects[rule_type] = value

    special_effects["damage_bonus"] = damage_bonus
    return special_effects


# ═══════════════════════════════════════
# 五行生克
# ═══════════════════════════════════════

_GENERATION_CHAIN = ["wood", "fire", "earth", "metal", "water"]
_CONQUER_MAP = {"metal": "wood", "wood": "earth", "earth": "water",
                "water": "fire", "fire": "metal"}

# 中文元素标签 → 英文 ID 映射（与 character_schema.yaml elements.definitions 对齐）
_ELEMENT_NAME_TO_ID = {
    "金": "metal", "木": "wood", "水": "water", "火": "fire",
    "土": "earth", "雷": "thunder", "冰": "ice", "风": "wind",
}
_VARIANT_ELEMENTS = {"thunder", "ice", "wind"}


def _single_element_mod(atk_element: str, def_element: str) -> float:
    """计算攻击元素与单个防御元素的五行加算修正。"""
    if atk_element == def_element:
        return -0.10
    if _CONQUER_MAP.get(atk_element) == def_element:
        return 0.30
    if _CONQUER_MAP.get(def_element) == atk_element:
        return -0.30
    try:
        atk_idx = _GENERATION_CHAIN.index(atk_element)
        if _GENERATION_CHAIN[(atk_idx + 1) % 5] == def_element:
            return -0.20
    except ValueError:
        pass
    return 0.00


def resolve_element_mod(atk_elements: list[str] | str | None,
                        defender_elements: list[str]) -> float:
    """根据五行生克计算元素加算修正（攻防双方均等权平均）。"""
    if not atk_elements or not defender_elements:
        return 0.0
    if isinstance(atk_elements, str):
        atk_elements = [atk_elements]
    total = 0.0
    count = 0
    for atk in atk_elements:
        for de in defender_elements:
            total += _single_element_mod(atk, de)
            count += 1
    return total / count if count > 0 else 0.0


# ═══════════════════════════════════════
# 伤害公式
# ═══════════════════════════════════════

def calculate_level_penalty(caster, target, effect: dict) -> float:
    """计算等级差衰减系数（0.05~1.0）。

    技能：施法者等级和目标等级分别与技能等级比较，取衰减。
    物品：仅创作者等级与目标等级比较，不考虑使用者等级。
    同级返回 1.0。
    """
    is_item = effect.get("_source") == "item"
    if is_item:
        creator_attrs = effect.get("_creator_attrs", {})
        source_level = creator_attrs.get("level")
    else:
        source_level = effect.get("_source_level")
    if source_level is None:
        return 1.0
    caster_level = getattr(caster, "level", None)
    target_level = getattr(target, "level", None)

    skill_cm = get_stage_mult(level_to_stage(source_level))
    penalty = 1.0

    # 物品衰减仅比较创作者等级与目标等级
    if not is_item and caster_level is not None and caster_level > source_level:
        caster_cm = get_stage_mult(level_to_stage(caster_level))
        penalty *= max(0.05, (skill_cm / caster_cm) ** 0.25)

    if target_level is not None and target_level > source_level:
        target_cm = get_stage_mult(level_to_stage(target_level))
        penalty *= max(0.05, (skill_cm / target_cm) ** 0.25)

    return penalty


def calculate_damage(caster, target, attrs_schema: dict,
                     effect: dict, is_crit: bool) -> int:
    """非线性伤害公式 + 加算修正。

    base_damage = combat_atk² × power / (combat_atk + combat_def × R)
    final = base_damage × (1 + tag + element + divine) × crit × variance
    """
    atk = max(caster.attrs.get("force", 0), 1)
    # 消耗品创作者属性优先
    creator_attrs = effect.get("_creator_attrs", {})
    if creator_attrs and "force" in creator_attrs:
        atk = max(creator_attrs["force"], 1)
    defense = target.attrs.get("tenacity", 0)
    power = effect.get("power", 1.0)
    tags = effect.get("tags", [])

    # 标签修正
    caster_path = caster.extra.get("cultivation_path", "")
    target_path = target.extra.get("cultivation_path", "")
    effect_source = effect.get("_source")

    # 获取施法者专属属性值用于 mastery 增幅
    caster_mastery = 0
    caster_path_config = _get_path_config(caster_path) if caster_path else None
    if caster_path_config:
        caster_mastery_attr = caster_path_config.get("primary_attr", {}).get("id", "")
        if caster_mastery_attr:
            caster_mastery = caster.attrs.get(caster_mastery_attr, 0)

    # 获取防御方专属属性值
    target_mastery = 0
    target_path_config = _get_path_config(target_path) if target_path else None
    if target_path_config:
        target_mastery_attr = target_path_config.get("primary_attr", {}).get("id", "")
        if target_mastery_attr:
            target_mastery = target.attrs.get(target_mastery_attr, 0)

    caster_mods = resolve_tag_mods(caster_path, tags, "attacker",
                                    source=effect_source,
                                    mastery_value=caster_mastery)
    defender_mods = resolve_tag_mods(target_path, tags, "defender",
                                      source=effect_source,
                                      mastery_value=target_mastery)

    # 处理特殊效果（resolve_tag_mods 始终返回 dict）
    def_ignore = caster_mods.get("def_ignore", 0)
    tag_bonus = (caster_mods.get("damage_bonus", 0.0)
                 + defender_mods.get("damage_bonus", 0.0))

    # 防御无视（下界保护 50%）
    effective_def = defense * max(0.5, 1 - def_ignore)

    # 等级差衰减由 resolver 在调用前统一处理，此处不再重复
    # （见 calculate_level_penalty + resolve_effect）

    # 基础伤害: atk² × power / (atk + def × R)
    R = 20
    base_damage = (atk * atk * power) / (atk + effective_def * R)

    # 五行修正（同时支持五行英文名 + 变异元素名）
    all_elements = set(_GENERATION_CHAIN) | set(_CONQUER_MAP.keys()) | _VARIANT_ELEMENTS
    effect_elements = []
    for t in tags:
        if t in all_elements:
            effect_elements.append(t)
        elif t in _ELEMENT_NAME_TO_ID:
            effect_elements.append(_ELEMENT_NAME_TO_ID[t])
    defender_roots = target.extra.get("spiritual_roots", [])
    element_bonus = resolve_element_mod(effect_elements if effect_elements else None,
                                        defender_roots)

    # 神通加成
    divine_bonus = 0.25 if effect.get("_category") == "divine" else 0.0

    # 加算修正：base_damage × (1 + tag + element + divine)
    additive_mult = 1.0 + tag_bonus + element_bonus + divine_bonus
    final = base_damage * additive_mult

    # 暴击（乘算，在加算括号之外）
    if is_crit:
        has_tag_match = tag_bonus > 0
        crit_mult = 2.0 if has_tag_match else 1.5
        final *= crit_mult

    # 方差
    variance = random.uniform(0.85, 1.15)
    final *= variance

    return max(1, int(final))


# ═══════════════════════════════════════
# 追击 / 暴击 / 逃跑
# ═══════════════════════════════════════

def calculate_pursuit(caster, target, attrs_schema: dict, effect: dict | None = None) -> bool:
    """追击判定：速度差比 × 25% + 道路追击修正。范围 0%-50%。

    攻击必中，速度优势转化为追击概率（额外一次 50% 系数伤害）。
    神通类技能获得 1.2 倍追击概率加成。
    """
    caster_spd = caster.attrs.get("agility", 0)
    target_spd = target.attrs.get("agility", 0)
    speed_ratio = (caster_spd - target_spd) / max(caster_spd, 1)
    base = max(0.0, speed_ratio * 0.25)
    path_id = caster.extra.get("cultivation_path", "")
    path_config = _get_path_config(path_id) if path_id else None
    path_pursuit_mod = path_config.get("path_mods", {}).get("pursuit_mod", 0.0) if path_config else 0.0
    rate = base + path_pursuit_mod
    if effect and effect.get("_category") == "divine":
        rate *= 1.2
    rate = max(0.0, min(0.50, rate))
    return random.random() < rate


def calculate_critical(caster, target, attrs_schema: dict) -> bool:
    """暴击率: 5% + 道路暴击修正 + 主属性/500。范围 5%-60%。"""
    base = 0.05
    path_id = caster.extra.get("cultivation_path", "")
    path_config = _get_path_config(path_id) if path_id else None
    if path_config:
        base += path_config.get("path_mods", {}).get("crit_mod", 0.05)
        primary_attr_info = path_config.get("primary_attr") or {}
        primary_attr_id = primary_attr_info.get("id", "")
        if primary_attr_id:
            attr_val = caster.attrs.get(primary_attr_id, 0)
            base += attr_val / 500.0
    else:
        base += 0.05
    rate = max(0.05, min(0.60, base))
    return random.random() < rate


def calculate_stun_chance(caster, base_chance: float) -> float:
    """眩晕成功率修正：基础概率 + 道路 stun_mod。范围 0%-100%。"""
    path_id = caster.extra.get("cultivation_path", "")
    path_config = _get_path_config(path_id) if path_id else None
    stun_mod = path_config.get("path_mods", {}).get("stun_mod", 0.0) if path_config else 0.0
    return max(0.0, min(1.0, base_chance + stun_mod))


def calculate_flee_chance(actor, enemy_level: int, enemy_spd: int = 0) -> float:
    """逃跑率: 40% + 境界阶差 × 12% + 速度比修正。范围 5%-90%。"""
    stage_id = actor.extra.get("cultivation_stage", "")
    actor_order = _get_stage_order(stage_id)
    enemy_order = max(enemy_level, 0)
    base = 0.40
    order_bonus = (actor_order - enemy_order) * 0.12
    actor_spd = actor.attrs.get("agility", 10)
    effective_enemy_spd = enemy_spd if enemy_spd > 0 else max(actor_spd * 0.5, 1)
    speed_bonus = (actor_spd / max(effective_enemy_spd, 1) - 1.0) * 0.15
    chance = base + order_bonus + speed_bonus
    return max(0.05, min(0.90, chance))


def calculate_rewards(enemy) -> dict:
    return {"exp_gained": 0, "loot": []}
