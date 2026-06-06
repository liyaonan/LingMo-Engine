"""夺舍系统 — 元婴出窍夺取他人肉身"""
from lingmo_engine.core.types import ModuleResult
from lingmo_engine.plugins.cultivation.field_normalizer import (
    CultivationFieldNormalizer,
)


def check_possession_prerequisites(possessor, target, schema: "CultivationSchema") -> ModuleResult | None:
    """检查夺舍前置条件。返回None=通过, ModuleResult=不满足"""
    # 夺舍者必须≥元婴期
    stage_id = getattr(possessor, "cultivation_stage", "mortal")
    stage = schema.get_stage(stage_id)
    if not stage or stage.get("order", 0) < 4:
        return ModuleResult(success=False, log="仅元婴期及以上方可夺舍")

    # 目标必须存活
    if not getattr(target, "is_alive", True):
        return ModuleResult(success=False, log="目标已死亡，无法夺舍")

    # 目标境界必须低于夺舍者
    target_stage_id = getattr(target, "cultivation_stage", "mortal")
    target_stage = schema.get_stage(target_stage_id)
    possessor_order = stage.get("order", 0)
    target_order = target_stage.get("order", 0) if target_stage else 0
    if target_order >= possessor_order:
        return ModuleResult(success=False, log="目标境界必须低于夺舍者")

    # 不可跨越两大境界
    if possessor_order - target_order > 2:
        return ModuleResult(success=False, log="境界差距过大，无法夺舍")

    return None


def execute_possession(possessor, target, schema: "CultivationSchema") -> ModuleResult:
    """执行夺舍流程"""
    prereq = check_possession_prerequisites(possessor, target, schema)
    if prereq:
        return prereq

    # 神识对决
    possessor_ds = getattr(possessor, "divine_sense", 30)
    target_ds = getattr(target, "divine_sense", 10)

    # 成功率 = 夺舍者神识 / (夺舍者神识 + 目标神识)
    import random
    success_rate = possessor_ds / (possessor_ds + target_ds)
    roll = random.random()

    if roll <= success_rate:
        _transfer_body(possessor, target, schema)
        return ModuleResult(success=True,
            log=f"夺舍成功！已占据{target.name}的肉身",
            data={
                "new_body": target.name,
                "new_spiritual_roots": possessor.spiritual_roots,
                "success_rate": round(success_rate, 2),
                "roll": round(roll, 3),
            })
    else:
        _possession_failure(possessor)
        return ModuleResult(success=False,
            log=f"夺舍失败！神识受损，肉身受创",
            data={
                "success_rate": round(success_rate, 2),
                "roll": round(roll, 3),
            })


def _transfer_body(possessor, target, schema: "CultivationSchema") -> None:
    """将夺舍者的灵魂转入目标肉身"""
    # 保留灵魂的属性
    saved_stage = getattr(possessor, "cultivation_stage", "mortal")
    saved_ds = getattr(possessor, "divine_sense", 30)
    saved_max_ds = getattr(possessor, "max_divine_sense", 30)
    saved_path = getattr(possessor, "cultivation_path", "")
    saved_secondary = getattr(possessor, "secondary_path", None)
    saved_abilities = getattr(possessor, "abilities", getattr(possessor, "skills", []))
    saved_inventory = getattr(possessor, "inventory", [])
    saved_enlightenment = getattr(possessor, "enlightenment", 0)

    # 从目标继承肉身的属性
    possessor.name = target.name
    possessor.avatar = getattr(target, "avatar", None)
    possessor.spiritual_roots = list(target.spiritual_roots)
    possessor.root_quality = getattr(target, "root_quality", "")
    possessor.vitality = getattr(target, "vitality", 100)
    possessor.max_vitality = getattr(target, "max_vitality", 100)
    possessor.force = getattr(target, "force", 10)
    possessor.tenacity = getattr(target, "tenacity", 5)
    possessor.agility = getattr(target, "agility", 10)
    possessor.stamina = getattr(target, "stamina", 80)
    possessor.max_stamina = getattr(target, "max_stamina", 80)
    possessor.spiritual_power = getattr(target, "spiritual_power", 50)
    possessor.faction = getattr(target, "faction", "")

    # 恢复灵魂属性
    possessor.cultivation_stage = saved_stage
    # 根据保留的灵力直接计算小境界
    possessor.cultivation_substage = CultivationFieldNormalizer.compute_substage_from_stage(
        schema.get_stage(saved_stage) or {},
        getattr(possessor, "spiritual_power", 0),
    )
    possessor.divine_sense = saved_ds
    possessor.max_divine_sense = saved_max_ds
    possessor.cultivation_path = saved_path
    possessor.secondary_path = saved_secondary
    possessor.abilities = saved_abilities
    possessor.inventory = saved_inventory
    possessor.enlightenment = saved_enlightenment

    # 标记目标已死亡
    target.is_alive = False
    # 夺舍冷却
    possessor.breakthrough_cooldown = 365


def _possession_failure(possessor) -> None:
    """夺舍失败的反噬"""
    possessor.divine_sense = max(1, int(getattr(possessor, "divine_sense", 30) * 0.5))
    possessor.vitality = max(1, int(getattr(possessor, "vitality", 100) * 0.5))
    # 小境界由灵力驱动，不改灵力则小境界不变
    possessor.breakthrough_cooldown = 365
    possessor.heaven_mark = getattr(possessor, "heaven_mark", 0) + 1
