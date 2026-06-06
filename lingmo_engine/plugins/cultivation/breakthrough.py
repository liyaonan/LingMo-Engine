"""境界突破系统（v2 重构）

突破流程：门槛检查 → 成功率计算 → 结果判定
"""
import random
from lingmo_engine.core.types import ModuleResult
from lingmo_engine.plugins.cultivation.field_normalizer import (
    CultivationFieldNormalizer,
)
from lingmo_engine.plugins.cultivation.dao_rhyme import (
    check_breakthrough_eligibility,
    apply_rhyme_modifier,
)


def execute_breakthrough(char, schema: "CultivationSchema",
                         qi_density: float = 0.4) -> ModuleResult:
    """执行常规境界突破流程。"""
    stage_id = getattr(char, "cultivation_stage", "mortal")
    next_stage = schema.get_next_stage(stage_id)
    if not next_stage:
        return ModuleResult(success=False, log="已是最高境界，无法突破")

    rule = schema.get_breakthrough_rule(stage_id, next_stage["id"])
    if not rule:
        return ModuleResult(success=False,
                            log=f"未找到突破规则: {stage_id}_to_{next_stage['id']}")

    # 1. 冷却检查
    cooldown = getattr(char, "breakthrough_cooldown", 0)
    if cooldown > 0:
        return ModuleResult(success=False, log=f"突破冷却中，剩余{cooldown}天")

    # 2. 灵力门槛检查
    reqs = rule.get("requirements", {})
    sp_min = reqs.get("spiritual_power_min", 0)
    current_sp = getattr(char, "spiritual_power", 0)
    if current_sp < sp_min:
        return ModuleResult(success=False,
                            log=f"灵力不足（需要≥{sp_min}，当前={current_sp}）")

    # 2.5. 道韵门槛检查
    next_order = next_stage.get("order", 0)
    rhyme_threshold = schema.get_dao_rhyme_threshold(next_order - 1)
    _rhyme_flags = {"enlightenment": False, "low_rhyme": False}
    if rhyme_threshold > 0:
        current_rhyme = getattr(char, "dao_rhyme", 0)
        _rhyme_flags = check_breakthrough_eligibility(
            current_rhyme, rhyme_threshold, schema)
        if not _rhyme_flags["eligible"]:
            return ModuleResult(success=False, log=_rhyme_flags["reason"])

    # 3. 悟性门槛检查
    eng_req = reqs.get("enlightenment", 0)
    current_eng = getattr(char, "enlightenment", 0)
    if current_eng < eng_req:
        return ModuleResult(success=False,
                            log=f"悟性不足（需要≥{eng_req}，当前={current_eng}）")

    # 4. 获取突破方式配置
    bt_method = schema.get_breakthrough_method("natural")
    if not bt_method:
        return ModuleResult(success=False, log="未找到突破方式配置")

    # 5. 计算成功率
    success_rate = _calculate_success_rate(char, schema, rule, bt_method, qi_density)

    # 5.5. 道韵修正
    _trib_mult_override = None
    if rhyme_threshold > 0:
        if _rhyme_flags["eligible"] or _rhyme_flags["low_rhyme"]:
            success_rate, _trib_mult_override = apply_rhyme_modifier(
                success_rate,
                bt_method.get("tribulation_mult", 1.0),
                _rhyme_flags["enlightenment"],
                _rhyme_flags["low_rhyme"],
            )

    # 6. 检查天劫（跨境界大突破）
    tribulation = rule.get("tribulation")
    if tribulation:
        trib_type = tribulation["type"]
        # 天劫强度修正
        effective_trib_mult = (
            _trib_mult_override if _trib_mult_override is not None
            else bt_method.get("tribulation_mult", 1.0))
        trib_method = dict(bt_method)
        trib_method["tribulation_mult"] = effective_trib_mult
        if trib_type == "thunder":
            enemies = _spawn_thunder_tribulation(char, tribulation, trib_method)
        elif trib_type == "inner_demon":
            enemies = [_spawn_inner_demon(char, tribulation)]
        else:
            enemies = []
        return ModuleResult(success=True,
                            log=f"天劫降临！{trib_type}将至——",
                            data={
                                "action": "trigger_tribulation",
                                "tribulation_type": trib_type,
                                "tribulation": tribulation,
                                "enemies": enemies,
                                "next_stage_id": next_stage["id"],
                                "next_stage_name": next_stage["name"],
                                "success_rate": round(success_rate, 4),
                                "method": "natural",
                            })

    # 7. 掷骰判定
    roll = random.random()
    if roll <= success_rate:
        return _apply_success(char, next_stage, rule, success_rate, roll, schema)
    else:
        return _apply_failure(char, rule, success_rate, roll, schema)


def _calculate_success_rate(char, schema, rule: dict,
                            bt_method: dict, qi_density: float = 0.4) -> float:
    """计算突破成功率。"""
    params = schema.get_breakthrough_params()

    base_rate = params.get("base_rate", 0.60)

    # 灵根品质加成
    roots = char.spiritual_roots
    quality_key = schema.get_root_quality_key(roots)
    root_bonus_table = params.get("root_quality_bonus", {})
    root_bonus = root_bonus_table.get(quality_key, 0.0)

    # 灵气浓度加成
    qi_level = schema.get_qi_level(qi_density)
    qi_level_id = qi_level.get("id", "thin")
    qi_bonus_table = params.get("qi_density_bonus", {})
    qi_bonus = qi_bonus_table.get(qi_level_id, 0.0)

    # 突破方式修正
    method_mult = bt_method.get("rate_mult", 1.0)

    # 辅修加成
    secondary_bonus = 0.05 if getattr(char, "secondary_path", None) else 0.0

    total = (base_rate + root_bonus + qi_bonus + secondary_bonus) * method_mult

    min_rate = params.get("min_rate", 0.10)
    max_rate = params.get("max_rate", 0.95)
    return max(min_rate, min(max_rate, total))


def _apply_success(char, next_stage: dict, rule: dict,
                   success_rate: float, roll: float,
                   schema: "CultivationSchema") -> ModuleResult:
    """应用突破成功效果。"""
    char.cultivation_stage = next_stage["id"]
    char.level = next_stage.get("order", 0)
    char.cultivation_substage = CultivationFieldNormalizer.compute_substage_from_stage(
        next_stage, getattr(char, "spiritual_power", 0)
    )

    lifespan_gain = rule.get("success", {}).get("lifespan_gain", 0)
    char.lifespan_remaining = getattr(char, "lifespan_remaining", 100) + lifespan_gain
    char.breakthrough_cooldown = 0

    results_config = schema.get_breakthrough_results()
    great_threshold = results_config.get("great_success", {}).get("threshold", 0.80)
    is_great = success_rate > great_threshold
    label = "大成突破！" if is_great else "突破成功！"
    return ModuleResult(success=True,
                        log=f"{label} 晋升{next_stage['name']}！",
                        data={
                            "new_stage": next_stage["id"],
                            "new_stage_name": next_stage["name"],
                            "is_great_success": is_great,
                            "roll": round(roll, 4),
                            "success_rate": round(success_rate, 4),
                            "lifespan_gain": lifespan_gain,
                        })


def _apply_failure(char, rule: dict,
                   success_rate: float, roll: float,
                   schema: "CultivationSchema") -> ModuleResult:
    """应用突破失败惩罚。"""
    results_config = schema.get_breakthrough_results()

    if success_rate > 0.50:
        config = results_config.get("minor_failure", {})
    else:
        config = results_config.get("major_failure", {})

    sp_loss = config.get("sp_loss", 0.30)
    cooldown_days = config.get("cooldown_days", 30)

    char.spiritual_power = max(0, int(getattr(char, "spiritual_power", 0) * (1 - sp_loss)))
    char.vitality = max(1, int(getattr(char, "vitality", 100) * (1 - sp_loss * 0.5)))
    # 灵力变化后重算小境界
    stage_id = getattr(char, "cultivation_stage", "mortal")
    char.cultivation_substage = CultivationFieldNormalizer.compute_substage_from_stage(
        schema.get_stage(stage_id) or {}, char.spiritual_power
    )
    char.breakthrough_cooldown = cooldown_days

    severity = "严重" if sp_loss > 0.5 else "轻微"
    return ModuleResult(success=False,
                        log=f"突破失败（{severity}）！灵力损失{int(sp_loss*100)}%，冷却{cooldown_days}天"
                            f"（掷骰{round(roll,4)} > 成功率{round(success_rate,4)}）",
                        data={
                            "severity": severity,
                            "sp_loss_ratio": sp_loss,
                            "cooldown_days": cooldown_days,
                            "roll": round(roll, 4),
                            "success_rate": round(success_rate, 4),
                        })


def _spawn_thunder_tribulation(char, tribulation: dict, bt_method: dict) -> list[dict]:
    """生成雷劫敌人。

    注意：敌人字典的 key（hp/max_hp/force/tenacity/agility）是战斗引擎
    Combatant 的固定字段名，而非角色属性名。getattr 读取角色属性时
    使用重命名后的名称（max_vitality, force, tenacity, agility）。
    """
    waves = tribulation.get("waves", 3)
    ratio = tribulation.get("enemy_power_ratio", 0.5)
    trib_mult = bt_method.get("tribulation_mult", 1.0)
    enemies = []
    for w in range(waves):
        enemies.append({
            "id": f"tribulation_thunder_{w+1}",
            "name": f"天雷·第{w+1}波",
            "template": "tribulation_thunder",
            # 以下 key 为战斗引擎字段，非角色属性名
            "hp": int(getattr(char, "max_vitality", 100) * ratio * trib_mult),
            "max_hp": int(getattr(char, "max_vitality", 100) * ratio * trib_mult),
            "force": int(getattr(char, "force", 10) * ratio * trib_mult),
            "tenacity": 0,
            "agility": 20 + w * 5,
            "spiritual_power": 100,
        })
    return enemies


def _spawn_inner_demon(char, tribulation: dict) -> dict:
    """生成心魔敌人。

    注意：敌人字典的 key（hp/max_hp/force/tenacity/agility）是战斗引擎
    Combatant 的固定字段名，而非角色属性名。getattr 读取角色属性时
    使用重命名后的名称（max_vitality, force, tenacity, agility）。
    """
    ratio = tribulation.get("enemy_power_ratio", 1.2)
    return {
        "id": "inner_demon",
        "name": "心魔",
        "template": "inner_demon",
        # 以下 key 为战斗引擎字段，非角色属性名
        "hp": int(getattr(char, "max_vitality", 100) * ratio),
        "max_hp": int(getattr(char, "max_vitality", 100) * ratio),
        "force": int(getattr(char, "force", 10) * ratio),
        "tenacity": getattr(char, "tenacity", 5),
        "agility": getattr(char, "agility", 10) + 5,
        "spiritual_power": getattr(char, "spiritual_power", 0),
        "divine_sense": int(getattr(char, "divine_sense", 30) * ratio),
        "abilities": getattr(char, "abilities", getattr(char, "skills", [])),
    }
