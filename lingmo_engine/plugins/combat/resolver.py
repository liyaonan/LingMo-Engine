# lingmo_engine/plugins/combat/resolver.py

"""操作解析器 - 统一 effect 驱动的结算引擎"""

import random
from typing import Optional

from lingmo_engine.core.utils import interpolate_table
from lingmo_engine.plugins.combat.engine import Combatant, ActiveBuff, TargetDelta
from lingmo_engine.plugins.combat.formulas import (
    calc_damage, calc_heal, calc_crit, calc_pursuit_chance,
    calc_flee_chance, calc_defense_reduction, get_attr_by_role,
    calc_element_modifier, normalize_element_ratios,
)
from lingmo_engine.plugins.combat.abilities import AbilitySystem
from lingmo_engine.core.protocols.item_system import ItemSystemInterface

_DEFAULT_DISABLE_STATUSES = {"frozen", "stunned", "paralyzed", "petrified"}


def compute_display_value(effect_value: float, scale_stat: str | None,
                          power: float, creator_stats: dict,
                          vs_table: dict, amplify_fn: callable) -> int:
    """预计算 fixed_damage/fixed_dot 的增幅显示值，供前端展示。

    amplify_fn: ActionResolver._amplify_creator_attrs 绑定方法，用于属性增幅。
    """
    amplified = effect_value
    stage_order = creator_stats.get("level", 0)
    amplified = int(amplified * interpolate_table(stage_order, vs_table))
    if scale_stat:
        amp_attrs = amplify_fn(creator_stats)
        stat_val = amp_attrs.get(scale_stat, 0)
        amplified += int(stat_val * (power or 1.0))
    return amplified


def _check_stun_disable(buffs: list, statuses: set[str] | None = None) -> bool:
    """检查是否被无法行动的状态影响。stunned 按 chance 概率判定。"""
    import random
    effective = statuses or _DEFAULT_DISABLE_STATUSES
    for b in buffs:
        status = b.effect.get("status", "")
        if status in effective and status != "stunned":
            return True
        if status == "stunned":
            chance = b.effect.get("chance", 1.0)
            if random.random() < chance:
                return True
    return False


class ActionResult:
    """操作结算结果"""

    def __init__(self):
        self.logs: list[str] = []
        self.target_deltas: list[TargetDelta] = []
        self.resources_consumed: int = 0
        self.items_consumed: list[str] = []
        self.ability_used: Optional[str] = None
        self.fled: bool = False
        self.defending: bool = False
        self.kills: list[str] = []

    def add_log(self, msg: str):
        self.logs.append(msg)


class ActionResolver:
    """解析并执行战斗操作"""

    def __init__(
        self,
        ability_system: AbilitySystem,
        item_system: ItemSystemInterface,
        attrs_schema: dict,
        combat_functions: dict | None = None,
        statuses: set[str] | None = None,
        value_scale_table: dict | None = None,
        cost_scale_table: dict | None = None,
        attr_labels: dict | None = None,
    ):
        self.abilities = ability_system
        self.items = item_system
        self.attrs_schema = attrs_schema
        self._registry = None
        self._cf = combat_functions or {}
        self._statuses = statuses
        self._value_scale_table = value_scale_table or {}
        self._cost_scale_table = cost_scale_table or {}
        self._attr_labels = attr_labels or {}
        self._element_config = self.attrs_schema.get("__elements__")
        self._tag_to_element: dict[str, str] = {}
        if self._element_config:
            for defn in self._element_config.get("definitions", []):
                self._tag_to_element[defn["name"]] = defn["id"]

        # 从 schema 动态推导核心生命池键名
        self._hp_key = "hp"
        self._max_hp_key = "max_hp"
        if attrs_schema:
            for name, defn in attrs_schema.items():
                if defn.get("combat_type") == "pool" and defn.get("core"):
                    self._hp_key = name
                    self._max_hp_key = defn.get("pair", f"max_{name}")
                    break

    # ---- 属性读写 helper（hp 在固定字段上） ----

    def _stat_label(self, stat: str) -> str:
        """将属性/状态 key 转为显示名，找不到则返回原值。"""
        return self._attr_labels.get(stat, stat)

    def _lookup_value_scale(self, level: int) -> float:
        """从 VS 表查值，表外线性插值。"""
        return interpolate_table(level, self._value_scale_table)

    def _amplify_creator_attrs(self, creator_attrs: dict) -> dict:
        """按创作者等级增幅基础属性（force/tenacity/agility）。"""
        level = creator_attrs.get("level", 0)
        level_to_stage_fn = self._cf.get("level_to_stage")
        get_stage_mult_fn = self._cf.get("get_stage_mult")
        if level_to_stage_fn and get_stage_mult_fn:
            stage_id = level_to_stage_fn(level)
            mult = get_stage_mult_fn(stage_id) if stage_id else 1.0
        else:
            mult = 1.0
        result = dict(creator_attrs)
        if mult > 1.0:
            for key in ("force", "tenacity", "agility"):
                if key in result:
                    result[key] = int(result[key] * mult)
        return result

    def _scale_cost(self, base_amount: int, level: int) -> int:
        """根据等级缩放基础消耗。"""
        if level <= 0 or not self._cost_scale_table:
            return max(1, base_amount)
        scale = interpolate_table(level, self._cost_scale_table)
        return max(1, int(base_amount * scale))

    # 公开接口（供 CombatSession 使用）
    scale_cost = _scale_cost

    def set_plugin_registry(self, registry) -> None:
        """设置 PluginRegistry 引用。"""
        self._registry = registry

    def _get_stat(self, actor: Combatant, stat_name: str) -> int:
        """统一获取属性值：核心生命池走固定字段，其余走 attrs"""
        if stat_name == self._hp_key:
            return actor.hp
        return actor.attrs.get(stat_name, 0)

    def _set_stat(self, actor: Combatant, stat_name: str, value: int) -> None:
        """统一设置属性值：schema pair 驱动 clamp"""
        if stat_name == self._hp_key:
            actor.hp = max(0, min(value, actor.max_hp))
            return
        if stat_name == self._max_hp_key:
            actor.max_hp = max(1, value)
            if actor.hp > actor.max_hp:
                actor.hp = actor.max_hp
            return

        # Schema pair 驱动：查找配对的 max 属性
        stat_def = self.attrs_schema.get(stat_name, {})
        pair_key = stat_def.get("pair", "")
        if pair_key:
            max_val = actor.attrs.get(pair_key)
            if max_val is not None:
                value = max(0, min(value, max_val))

        actor.attrs[stat_name] = value

    def resolve(
        self,
        action: dict,
        actor: Combatant,
        targets: list[Combatant],
        allies: list[Combatant],
    ) -> ActionResult:
        result = ActionResult()
        action_type = action.get("type", "attack")

        if action_type == "attack":
            self._resolve_attack(action, actor, targets, result)
        elif action_type == "ability":
            self._resolve_ability(action, actor, targets, allies, result)
        elif action_type == "item":
            self._resolve_item(action, actor, targets, allies, result)
        elif action_type == "defend":
            self._resolve_defend(actor, result)
        elif action_type == "flee":
            self._resolve_flee(action, actor, targets, result)

        return result

    # ---- resolve_effect：统一效果执行入口 ----

    def resolve_effect(
        self,
        effect: dict,
        caster: Combatant,
        targets: list[Combatant],
        allies: list[Combatant],
        create_buffs: bool = True,
        target_index: int = 0,
        override_targets: list[Combatant] | None = None,
    ) -> list[TargetDelta]:
        """执行单个效果，返回 TargetDelta 列表。技能/Buff/物品均走此入口。

        Args:
            create_buffs: 是否创建持久效果。Buff tick 时传 False 避免重复叠加。
            target_index: 单目标时指定目标索引（技能/物品的 target_index）。
            override_targets: 跳过目标解析，直接使用指定目标列表。
        """
        deltas: list[TargetDelta] = []
        if override_targets is not None:
            target_list = override_targets
        else:
            target_list = self._resolve_targets(
                effect.get("target", "enemy"), caster, targets, allies,
                target_index=target_index,
            )

        # AOE 效果衰减 50%（仅原始施放路径，buff tick 时 override_targets 跳过）
        is_aoe = override_targets is None and effect.get("target", "enemy") in ("all_enemy", "all_ally")

        for target in target_list:
            if not target.is_alive and effect.get("type") != "heal":
                continue

            # 等级差衰减（per-target 独立计算，修复 AOE 多等级目标共享惩罚的问题）
            level_mult = self._compute_level_penalty(effect, caster, [target])
            penalized = self._apply_level_penalty(effect, level_mult) if level_mult < 1.0 else dict(effect)
            if is_aoe:
                penalized = self._apply_level_penalty(penalized, 0.5)

            if penalized["type"] in ("damage", "dot"):
                deltas.extend(self._apply_damage_effect(penalized, caster, target))
            elif penalized["type"] in ("fixed_damage", "fixed_dot"):
                deltas.extend(self._apply_fixed_damage_effect(penalized, caster, target))
            elif penalized["type"] == "heal":
                deltas.extend(self._apply_heal_effect(penalized, caster, target))
            elif penalized["type"] == "buff":
                deltas.extend(self._apply_buff_effect(penalized, caster, target))
            elif penalized["type"] == "debuff":
                # debuff 模板值为正，统一取负 modifier
                penalized = dict(penalized)
                if "modifier" in penalized and penalized["modifier"] > 0:
                    penalized["modifier"] = -penalized["modifier"]
                deltas.extend(self._apply_buff_effect(penalized, caster, target))
            elif penalized["type"] == "shield":
                deltas.extend(self._apply_shield_effect(penalized, caster, target))
            elif penalized["type"] == "dispel":
                deltas.extend(self._apply_dispel_effect(penalized, target))
            elif penalized["type"] == "lifesteal":
                deltas.extend(self._apply_lifesteal_effect(penalized, caster, target))
            elif penalized["type"] == "stun":
                deltas.extend(self._apply_stun_effect(penalized, target, caster))

            # 创建持久效果（stun 由 _apply_stun_effect 自行创建，跳过避免重复）
            if create_buffs and penalized["type"] != "stun":
                duration = penalized.get("duration", 0)
                if duration > 0:
                    # 存储原始 effect（tick 时由 resolve_effect 重新计算惩罚，避免复利衰减）
                    buff_effect = dict(effect)
                    # 护盾需要 _applied_shield 用于过期时扣减
                    if penalized["type"] == "shield":
                        buff_effect["_applied_shield"] = penalized.get("_applied_shield", 0)
                    target.buffs.append(ActiveBuff(
                        id=effect.get("id", ""),
                        name=effect.get("name", ""),
                        remaining=duration,
                        caster_name=caster.name,
                        effect=buff_effect,
                    ))
                elif penalized["type"] in ("buff", "debuff") and penalized.get("stat"):
                    # 即时增益/减益（无 duration）：仅展示，不参与 tick 重算
                    effect_copy = dict(effect)
                    effect_copy["_instant"] = True
                    target.buffs.append(ActiveBuff(
                        id=effect.get("id", ""),
                        name=effect.get("name", ""),
                        remaining=999,
                        caster_name=caster.name,
                        effect=effect_copy,
                    ))

        return deltas

    def _compute_level_penalty(
        self, effect: dict, caster: Combatant, targets: list[Combatant],
    ) -> float:
        """通过世界自定义函数计算等级差衰减系数。无注册函数时返回 1.0。"""
        penalty_fn = self._cf.get("calculate_level_penalty")
        if not penalty_fn:
            return 1.0
        # 取第一个目标用于双侧计算（self 目标时 target=caster）
        sample_target = targets[0] if targets else caster
        return penalty_fn(caster, sample_target, effect)

    @staticmethod
    def _apply_level_penalty(effect: dict, level_mult: float) -> dict:
        """将衰减系数乘入效果的数值参数，返回副本。"""
        penalized = dict(effect)
        for key in ("power", "modifier", "chance", "ratio"):
            if key in penalized:
                penalized[key] = penalized[key] * level_mult
        for key in ("value", "count"):
            if key in penalized:
                penalized[key] = max(0, int(penalized[key] * level_mult))
        return penalized

    def _resolve_targets(
        self, target_type: str, caster: Combatant,
        targets: list[Combatant], allies: list[Combatant],
        target_index: int = 0,
    ) -> list[Combatant]:
        if target_type == "self":
            return [caster]
        elif target_type == "enemy":
            idx = min(target_index, len(targets) - 1) if targets else 0
            return [targets[idx]] if targets else []
        elif target_type == "all_enemy":
            return [t for t in targets if t.is_alive]
        elif target_type == "all_ally":
            return [caster] + [a for a in allies if a is not caster and a.is_alive]
        return []

    def _extract_elements(self, effect: dict) -> list[dict]:
        """从 effect 中提取元素列表。优先 elements 字段，其次从 tags 推导。"""
        elements = effect.get("elements")
        if elements:
            return normalize_element_ratios(elements)
        tags = effect.get("tags", [])
        if not tags or not self._tag_to_element:
            return []
        matched = [self._tag_to_element[t] for t in tags if t in self._tag_to_element]
        if not matched:
            return []
        ratio = 1.0 / len(matched)
        return [{"id": eid, "ratio": ratio} for eid in matched]

    # ---- 私有效果方法 ----

    @staticmethod
    def _deduct_hp_with_shield(target: Combatant, damage: int) -> int:
        """先扣护盾再扣 HP，返回实际 HP 伤害量。"""
        if target.shield > 0:
            absorbed = min(target.shield, damage)
            target.shield -= absorbed
            damage -= absorbed
        if damage <= 0:
            return 0
        target.hp = max(0, target.hp - damage)
        return damage

    def _apply_damage_effect(self, effect: dict, caster: Combatant,
                              target: Combatant) -> list[TargetDelta]:
        """常规伤害：暴击 → 防御减免 → 追击"""
        schema = self.attrs_schema

        # 暴击判定（优先世界自定义公式）
        custom_crit = self._cf.get("calculate_critical")
        if custom_crit:
            is_crit = custom_crit(caster, target, schema)
        else:
            is_crit = calc_crit()

        # 伤害计算（优先世界自定义公式）
        if self._cf.get("calculate_damage"):
            damage = self._cf["calculate_damage"](caster, target, schema, effect, is_crit)
        else:
            power = effect.get("power", 1.0)
            dmg_mult = 2.0 if is_crit else 1.0
            damage = calc_damage(caster, target, schema, power * dmg_mult)

        # 元素修正（仅在非自定义伤害公式时应用，自定义公式自行处理五行）
        if not self._cf.get("calculate_damage"):
            elements = self._extract_elements(effect)
            if elements and self._element_config:
                modifier = calc_element_modifier(
                    caster.extra.get("spiritual_roots", []),
                    target.extra.get("spiritual_roots", []),
                    elements,
                    self._element_config.get("affinity_bonus", 0.0),
                    self._element_config.get("resistance_reduction", 0.0),
                )
                damage = max(1, int(damage * modifier))

        if target.defending:
            reduction = calc_defense_reduction(target, schema)
            damage = max(1, int(damage * (1 - reduction)))
        target.defending = False
        actual_damage = self._deduct_hp_with_shield(target, damage)
        if actual_damage <= 0:
            return []

        deltas = [TargetDelta(target_name=target.name, stat=self._hp_key,
                              delta=-actual_damage, new_value=target.hp)]

        # 追击判定：速度优势触发额外伤害（50% 系数）
        if target.is_alive:
            custom_pursuit = self._cf.get("calculate_pursuit")
            if custom_pursuit:
                is_pursuit = custom_pursuit(caster, target, schema, effect)
            else:
                is_pursuit = random.random() < calc_pursuit_chance(caster, target, schema)
            if is_pursuit:
                pursuit_dmg = max(1, int(actual_damage * 0.5))
                pursuit_actual = self._deduct_hp_with_shield(target, pursuit_dmg)
                if pursuit_actual > 0:
                    deltas.append(TargetDelta(
                        target_name=target.name, stat=self._hp_key,
                        delta=-pursuit_actual, new_value=target.hp,
                        is_pursuit=True,
                    ))

        self._check_triggers(caster, target, effect.get("tags", []), deltas)
        return deltas

    def _apply_fixed_damage_effect(self, effect: dict, caster: Combatant,
                                    target: Combatant) -> list[TargetDelta]:
        """固定伤害：直接扣 HP，无视命中/暴击/防御，受 VS 缩放"""
        target.defending = False
        value = effect.get("value", 0)
        if self._value_scale_table:
            stage_order = effect.get("_creator_stage_order",
                                     caster.extra.get("stage_order", 0))
            value = int(value * self._lookup_value_scale(stage_order))
        scale_stat = effect.get("scale_stat")
        if scale_stat:
            creator_attrs = effect.get("_creator_attrs", {})
            if creator_attrs and scale_stat in creator_attrs:
                stat_val = creator_attrs[scale_stat]
            elif scale_stat in caster.attrs:
                stat_val = caster.attrs[scale_stat]
            else:
                stat_val = 0
            value += int(stat_val * effect.get("power", 1.0))

        actual_damage = self._deduct_hp_with_shield(target, value)
        if actual_damage <= 0:
            return []

        deltas = [TargetDelta(target_name=target.name, stat=self._hp_key,
                              delta=-actual_damage, new_value=target.hp)]
        self._check_triggers(caster, target, effect.get("tags", []), deltas)
        return deltas

    def _apply_heal_effect(self, effect: dict, caster: Combatant,
                            target: Combatant) -> list[TargetDelta]:
        """治疗效果：优先固定值（受 VS 缩放），否则公式；支持指定属性（mp等）"""
        stat = effect.get("stat", self._hp_key)  # 默认治疗核心生命池
        is_item = effect.get("_source") == "item"
        creator_attrs = effect.get("_creator_attrs", {})
        value = effect.get("value", 0)
        if value > 0:
            if self._value_scale_table:
                stage_order = effect.get("_creator_stage_order",
                                         caster.extra.get("stage_order", 0))
                value = int(value * self._lookup_value_scale(stage_order))
            heal_amount = value
        elif is_item and creator_attrs:
            power = effect.get("power", 1.0)
            magic = creator_attrs.get("force", 50)
            heal_amount = max(1, int(magic * power * 0.8))
        else:
            power = effect.get("power", 1.0)
            heal_amount = calc_heal(caster, self.attrs_schema, power)

        if stat == self._hp_key:
            old = target.hp
            target.hp = min(target.hp + heal_amount, target.max_hp)
            actual = target.hp - old
        else:
            # Schema pair 驱动：查找配对的 max 属性
            stat_def = self.attrs_schema.get(stat, {})
            pair_key = stat_def.get("pair", "")
            max_val = target.attrs.get(pair_key) if pair_key else None
            if max_val is None:
                max_val = target.attrs.get(stat, 0) + heal_amount
            old = target.attrs.get(stat, 0)
            target.attrs[stat] = min(old + heal_amount, max_val)
            actual = target.attrs[stat] - old

        return [TargetDelta(target_name=target.name, stat=stat,
                            delta=actual, new_value=(target.hp if stat == self._hp_key else target.attrs[stat]))]

    def _apply_buff_effect(self, effect: dict, caster: Combatant,
                            target: Combatant) -> list[TargetDelta]:
        """属性修改效果（正=增益，负=减益）。核心生命池走固定字段，其余走 attrs。"""
        stat = effect.get("stat")
        if stat is None:
            # 尝试从模板取默认 stat（buff→force, debuff→tenacity）
            eff_type = effect.get("type", "")
            if eff_type == "buff":
                stat = "force"
            elif eff_type == "debuff":
                stat = "tenacity"
            else:
                return []

        # 核心生命池是 Combatant 固定字段，不在 attrs 中
        if stat == self._hp_key:
            old_value = target.hp
        elif stat == self._max_hp_key:
            old_value = target.max_hp
        else:
            old_value = target.attrs.get(stat, 0)

        delta = effect.get("value", 0)

        if effect.get("power") and effect.get("scale_stat"):
            creator_attrs = effect.get("_creator_attrs", {})
            if creator_attrs and effect["scale_stat"] in creator_attrs:
                scale_val = creator_attrs[effect["scale_stat"]]
            else:
                scale_val = caster.attrs.get(effect["scale_stat"], 0)
            delta += int(scale_val * effect["power"])
        elif effect.get("modifier") is not None:
            delta += int(old_value * effect["modifier"])

        new_value = old_value + delta

        # clamp：从 schema pair 字段获取配对的 max 属性
        stat_def = self.attrs_schema.get(stat, {})
        pair_key = stat_def.get("pair", "")

        if stat_def.get("combat_type") == "pool" and pair_key:
            # stat 是当前值（如 hp, qi），pair 指向 max 属性
            max_val = target.attrs.get(pair_key, 1)
            new_value = max(0, min(new_value, max_val))
        elif stat in (self._hp_key, self._max_hp_key):
            # Combatant 独立字段（核心生命池直接存储）
            if stat == self._hp_key:
                new_value = max(0, min(new_value, target.max_hp))
                target.hp = new_value
            else:
                new_value = max(1, new_value)
                target.max_hp = new_value
                if target.hp > target.max_hp:
                    target.hp = target.max_hp
            actual_delta = new_value - old_value
            return [
                TargetDelta(target_name=target.name, stat=stat,
                            delta=actual_delta, new_value=new_value)
            ]

        target.attrs[stat] = new_value

        actual_delta = new_value - old_value
        return [TargetDelta(target_name=target.name, stat=stat,
                            delta=actual_delta, new_value=new_value)]

    def _apply_shield_effect(self, effect: dict, caster: Combatant,
                              target: Combatant) -> list[TargetDelta]:
        """护盾效果：power 百分比型，shield = max_hp × power。"""
        power = effect.get("power", 0)
        value = int(target.max_hp * power)
        effect["_applied_shield"] = value
        old_shield = target.shield
        target.shield = min(target.shield + value, target.max_hp)
        actual = target.shield - old_shield
        return [TargetDelta(target_name=target.name, stat="shield",
                            delta=actual, new_value=target.shield)]

    def _apply_dispel_effect(self, effect: dict,
                              target: Combatant) -> list[TargetDelta]:
        """驱散效果：auto 模式下对敌方驱散增益、对己方驱散减益。

        携带"青帝"标签的 dot/debuff 效果无法被驱散。
        """
        mode = effect.get("mode", "auto")
        count = effect.get("count", 0)

        def _is_undispellable(buff: ActiveBuff) -> bool:
            """青帝标签的 dot/debuff 效果不可驱散。"""
            tags = buff.effect.get("tags", [])
            if "青帝" not in tags:
                return False
            is_debuff = (buff.effect.get("modifier", 0) < 0
                         or "status" in buff.effect
                         or buff.effect.get("type") in ("dot", "fixed_dot"))
            return is_debuff

        def _is_debuff(buff: ActiveBuff) -> bool:
            return (buff.effect.get("type") == "debuff"
                    or buff.effect.get("modifier", 0) < 0
                    or "status" in buff.effect
                    or buff.effect.get("type") in ("dot", "fixed_dot"))

        def _is_buff(buff: ActiveBuff) -> bool:
            return (buff.effect.get("modifier", 0) > 0
                    or (buff.effect.get("type") == "buff" and buff.effect.get("value", 0) > 0))

        # auto: 对敌方驱散增益，对己方驱散减益
        if mode == "auto":
            effect_target = effect.get("target", "enemy")
            mode = "buff" if effect_target in ("enemy", "all_enemy") else "debuff"

        if mode == "debuff":
            candidates = [b for b in target.buffs
                          if _is_debuff(b) and not _is_undispellable(b)]
        elif mode == "buff":
            candidates = [b for b in target.buffs if _is_buff(b)]
        else:
            candidates = [b for b in target.buffs if not _is_undispellable(b)]

        to_remove = candidates if count == 0 else candidates[:count]
        removed_count = len(to_remove)
        for b in to_remove:
            target.buffs.remove(b)
            # 驱散护盾型 buff 时同步扣除护盾值
            if b.effect.get("type") == "shield":
                shield_value = b.effect.get("_applied_shield", 0)
                target.shield = max(0, target.shield - shield_value)

        return [TargetDelta(target_name=target.name, stat="buffs_removed",
                            delta=removed_count, new_value=len(target.buffs))]

    def _apply_lifesteal_effect(self, effect: dict, caster: Combatant,
                                 target: Combatant) -> list[TargetDelta]:
        """吸血效果：造成伤害（走护盾扣减），按实际 HP 伤害回复施法者。"""
        schema = self.attrs_schema

        # 暴击判定
        custom_crit = self._cf.get("calculate_critical")
        if custom_crit:
            is_crit = custom_crit(caster, target, schema)
        else:
            is_crit = calc_crit()

        # 伤害计算
        if self._cf.get("calculate_damage"):
            damage = self._cf["calculate_damage"](caster, target, schema, effect, is_crit)
        else:
            power = effect.get("power", 1.0)
            dmg_mult = 2.0 if is_crit else 1.0
            damage = calc_damage(caster, target, schema, power * dmg_mult)

        # 元素修正
        if not self._cf.get("calculate_damage"):
            elements = self._extract_elements(effect)
            if elements and self._element_config:
                modifier = calc_element_modifier(
                    caster.extra.get("spiritual_roots", []),
                    target.extra.get("spiritual_roots", []),
                    elements,
                    self._element_config.get("affinity_bonus", 0.0),
                    self._element_config.get("resistance_reduction", 0.0),
                )
                damage = max(1, int(damage * modifier))

        if target.defending:
            reduction = calc_defense_reduction(target, schema)
            damage = max(1, int(damage * (1 - reduction)))

        target.defending = False
        actual_damage = self._deduct_hp_with_shield(target, damage)
        if actual_damage <= 0:
            return []

        deltas = [TargetDelta(target_name=target.name, stat=self._hp_key,
                              delta=-actual_damage, new_value=target.hp)]

        # 回血（按实际 HP 伤害的 ratio）
        ratio = effect.get("ratio", 0.0)
        heal_amount = max(1, int(actual_damage * ratio))
        old_caster_hp = caster.hp
        caster.hp = min(caster.hp + heal_amount, caster.max_hp)
        actual_heal = caster.hp - old_caster_hp
        deltas.append(TargetDelta(target_name=caster.name, stat=self._hp_key,
                                  delta=actual_heal, new_value=caster.hp))

        self._check_triggers(caster, target, effect.get("tags", []), deltas)
        return deltas

    def _apply_stun_effect(self, effect: dict, target: Combatant,
                            caster: Combatant | None = None) -> list[TargetDelta]:
        """眩晕效果：创建带 status=stunned + chance 的 buff，每回合按概率跳过行动。"""
        chance = effect.get("chance", 0.5)
        # 世界自定义眩晕修正（如道路 stun_mod）
        if caster:
            stun_mod_fn = self._cf.get("calculate_stun_chance")
            if stun_mod_fn:
                chance = stun_mod_fn(caster, chance)
        chance = max(0.0, min(1.0, chance))
        # remaining 最少 2：保证眩晕至少存活 1 次 tick，UI 可见
        remaining = max(effect.get("duration", 1), 2)
        stun_def = {
            "type": "stun",
            "status": "stunned",
            "chance": chance,
            "duration": remaining,
            "_source_key": effect.get("_source_key", ""),
            "name": effect.get("name", "眩晕"),
        }
        target.buffs.append(ActiveBuff(
            id=effect.get("id", "stun"),
            name=effect.get("name", "眩晕"),
            remaining=remaining,
            caster_name="",
            effect=stun_def,
        ))
        return [TargetDelta(target_name=target.name, stat="stunned",
                            delta=1, new_value=chance,
                            name=stun_def.get("name", "眩晕"))]

    def _check_triggers(self, caster: Combatant, target: Combatant,
                        attack_tags: list[str], deltas: list[TargetDelta]) -> None:
        """检查目标身上的 trigger buff，匹配攻击标签时触发额外效果。"""
        if not attack_tags:
            return

        triggered = []
        for buff in target.buffs:
            trigger = buff.effect.get("trigger")
            if not trigger:
                continue
            trigger_tags = trigger.get("tags", [])
            if not set(attack_tags) & set(trigger_tags):
                continue

            trigger_effect = dict(trigger["effect"])
            trigger_deltas = self.resolve_effect(
                trigger_effect, caster, [target], [caster],
                create_buffs=False,
            )
            deltas.extend(trigger_deltas)

            if trigger.get("consume", True):
                triggered.append(buff)

        for b in triggered:
            target.buffs.remove(b)

    # ---- action type 分发 ----

    def _resolve_attack(self, action: dict, actor: Combatant,
                        targets: list[Combatant], result: ActionResult):
        """普攻 = 一个无消耗的 damage effect"""
        target_idx = action.get("target_index", 0)
        if target_idx >= len(targets) or not targets[target_idx].is_alive:
            result.add_log(f"{actor.name} 的攻击没有目标！")
            return

        target = targets[target_idx]
        effect = {"type": "damage", "target": "enemy", "power": 1.0}
        deltas = self.resolve_effect(effect, actor, targets, [actor],
                                     target_index=target_idx)
        result.target_deltas.extend(deltas)

        if not deltas:
            return

        for d in deltas:
            if d.stat == self._hp_key:
                prefix = "追击！" if getattr(d, "is_pursuit", False) else ""
                result.add_log(f"{actor.name} {prefix}攻击 {d.target_name}，造成 {-d.delta} 点伤害")

        if not target.is_alive:
            result.add_log(f"{target.name} 被击败！")
            result.kills.append(target.name)

    def _resolve_ability(self, action: dict, actor: Combatant,
                         targets: list[Combatant], allies: list[Combatant],
                         result: ActionResult):
        ability_id = action.get("ability_id", "")
        ability = self.abilities.get_ability(ability_id)
        if ability is None:
            result.add_log(f"技能 {ability_id} 不存在！")
            return

        # 校验冷却
        if actor.cooldowns.get(ability_id, 0) > 0:
            result.add_log(f"{ability.get('name', ability_id)} 还在冷却中！")
            return

        # 校验多资源消耗（costs: [{resource, amount}, ...]，amount 为基础值）
        costs = ability.get("costs", [])
        for cost in costs:
            resource = cost["resource"]
            base = cost.get("amount", 0)
            if base <= 0:
                continue
            actual = self._scale_cost(base, actor.level)
            if self._get_stat(actor, resource) < actual:
                result.add_log(
                    f"{self._stat_label(resource)}不足，无法使用 {ability.get('name', ability_id)}！"
                )
                return

        # 扣除资源
        for cost in costs:
            resource = cost["resource"]
            base = cost.get("amount", 0)
            if base <= 0:
                continue
            actual = self._scale_cost(base, actor.level)
            self._set_stat(actor, resource,
                           self._get_stat(actor, resource) - actual)
            result.resources_consumed += actual

        cooldown = ability.get("cooldown", 0)
        if cooldown > 0:
            actor.cooldowns[ability_id] = cooldown

        result.ability_used = ability_id
        result.add_log(f"{actor.name} 使用 {ability.get('name', ability_id)}")

        # 按效果类型优先级排序：buff → debuff → 伤害类
        _EFFECT_PRIORITY = {
            "buff": 0,
            "debuff": 1,
            "damage": 2, "fixed_damage": 2,
            "dot": 2, "fixed_dot": 2,
            "heal": 3, "lifesteal": 3,
            "shield": 3, "dispel": 3, "stun": 3,
        }
        raw_effects = list(enumerate(ability.get("effects", [])))
        sorted_effects = sorted(
            raw_effects,
            key=lambda pair: _EFFECT_PRIORITY.get(pair[1].get("type"), 99),
        )

        for i, effect in sorted_effects:
            effect_with_id = dict(effect)
            if "id" not in effect_with_id:
                effect_with_id["id"] = f"{ability_id}:{i}"
            if "name" not in effect_with_id:
                effect_with_id["name"] = ability.get("name", ability_id)
            if "tags" not in effect_with_id:
                effect_with_id["tags"] = ability.get("tags", [])
            if "_source" not in effect_with_id:
                effect_with_id["_source"] = "ability"
            if "_source_key" not in effect_with_id:
                effect_with_id["_source_key"] = ability_id
            if "_source_level" not in effect_with_id:
                effect_with_id["_source_level"] = ability.get("level")
            if "_category" not in effect_with_id:
                effect_with_id["_category"] = ability.get("category")

            tgt_idx = action.get("target_index", 0)
            deltas = self.resolve_effect(effect_with_id, actor, targets, allies,
                                         target_index=tgt_idx)
            result.target_deltas.extend(deltas)

            for d in deltas:
                if d.stat == self._hp_key and d.delta < 0:
                    pursuit_tag = " [追击]" if getattr(d, "is_pursuit", False) else ""
                    result.add_log(
                        f"对 {d.target_name}{pursuit_tag} 造成 {-d.delta} 伤害"
                    )
                    for t in targets:
                        if t.name == d.target_name and not t.is_alive:
                            result.add_log(f"{d.target_name} 被击败！")
                            result.kills.append(d.target_name)
                elif d.stat == self._hp_key and d.delta > 0:
                    result.add_log(f"{d.target_name} 恢复 {d.delta} {self._stat_label(self._hp_key)}")
                elif d.stat == "stunned":
                    stun_name = effect.get("name", "眩晕")
                    result.add_log(f"{d.target_name} 被{stun_name}！")
                elif d.stat == "buffs_removed":
                    result.add_log(f"{d.target_name} 被驱散了 {abs(d.delta)} 个效果")
                elif effect.get("duration", 0) > 0:
                    dir_text = "提升" if d.delta > 0 else "降低"
                    result.add_log(
                        f"{d.target_name} {self._stat_label(d.stat)} {dir_text} {abs(d.delta)}，"
                        f"持续 {effect['duration']} 回合"
                    )
                elif d.stat != self._hp_key:
                    dir_text = "提升" if d.delta > 0 else "降低"
                    result.add_log(
                        f"{d.target_name} {self._stat_label(d.stat)} {dir_text} {abs(d.delta)}"
                    )

    def _resolve_item(self, action: dict, actor: Combatant,
                      targets: list[Combatant], allies: list[Combatant],
                      result: ActionResult):
        item_id = action.get("item_id", "")
        item = self.items.get_item(item_id)

        if item is None:
            result.add_log(f"物品 {item_id} 不存在！")
            return

        if not item.is_consumable:
            result.add_log(f"{item.name} 不可使用！")
            return

        # 检查代价
        for cost in item.costs:
            if cost.amount <= 0:
                continue
            if self._get_stat(actor, cost.resource) < cost.amount:
                result.add_log(f"{self._stat_label(cost.resource)} 不足，无法使用 {item.name}")
                return

        # 扣除代价
        for cost in item.costs:
            if cost.amount > 0:
                self._set_stat(actor, cost.resource,
                               self._get_stat(actor, cost.resource) - cost.amount)

        result.items_consumed.append(item_id)
        result.add_log(f"{actor.name} 使用 {item.name}")

        # 按效果类型优先级排序：buff → debuff → 伤害类
        _EFFECT_PRIORITY = {
            "buff": 0,
            "debuff": 1,
            "damage": 2, "fixed_damage": 2,
            "dot": 2, "fixed_dot": 2,
            "heal": 3, "lifesteal": 3,
            "shield": 3, "dispel": 3, "stun": 3,
        }
        sorted_item_effects = sorted(
            enumerate(item.effects),
            key=lambda pair: _EFFECT_PRIORITY.get(pair[1].type, 99),
        )

        # 执行效果
        for _, effect in sorted_item_effects:
            effect_dict = {
                "type": effect.type,
                "target": effect.target,
                "power": effect.power,
                "value": effect.value,
            }
            if effect.scale_stat:
                effect_dict["scale_stat"] = effect.scale_stat
            if effect.stat:
                effect_dict["stat"] = effect.stat
            if effect.modifier is not None:
                effect_dict["modifier"] = effect.modifier
            if effect.elements:
                effect_dict["elements"] = effect.elements
            if effect.element:
                effect_dict["element"] = effect.element
            if effect.duration:
                effect_dict["duration"] = effect.duration
            if effect.status:
                effect_dict["status"] = effect.status
            if effect.count is not None:
                effect_dict["count"] = effect.count
            if effect.chance is not None:
                effect_dict["chance"] = effect.chance
            if effect.ratio is not None:
                effect_dict["ratio"] = effect.ratio
            if effect.mode is not None:
                effect_dict["mode"] = effect.mode
            if hasattr(item, 'tags') and item.tags:
                effect_dict["tags"] = item.tags
            effect_dict["_source"] = "item"
            effect_dict["name"] = effect.name or item.name
            effect_dict["_source_key"] = item_id
            if hasattr(item, "creator_stats") and item.creator_stats:
                effect_dict["_creator_attrs"] = self._amplify_creator_attrs(item.creator_stats)
                effect_dict["_creator_stage_order"] = item.creator_stats.get("level", 0)

            tgt_idx = action.get("target_index", 0)
            deltas = self.resolve_effect(effect_dict, actor, targets, allies,
                                         target_index=tgt_idx)
            result.target_deltas.extend(deltas)

            for d in deltas:
                if d.stat == self._hp_key and d.delta < 0:
                    result.add_log(
                        f"对 {d.target_name} 造成 {-d.delta} 伤害"
                    )
                    for t in targets:
                        if t.name == d.target_name and not t.is_alive:
                            result.add_log(f"{d.target_name} 被击败！")
                            result.kills.append(d.target_name)
                elif d.stat == self._hp_key and d.delta > 0:
                    result.add_log(f"{d.target_name} 恢复 {d.delta} {self._stat_label(self._hp_key)}")
                elif d.stat == "stunned":
                    stun_name = effect_dict.get("name", "眩晕")
                    result.add_log(f"{d.target_name} 被{stun_name}！")
                elif effect.duration > 0:
                    dir_text = "提升" if d.delta > 0 else "降低"
                    result.add_log(
                        f"{d.target_name} {self._stat_label(d.stat)} {dir_text} {abs(d.delta)}，"
                        f"持续 {effect.duration} 回合"
                    )
                elif d.delta != 0 and d.stat != self._hp_key:
                    dir_text = "提升" if d.delta > 0 else "降低"
                    result.add_log(
                        f"{d.target_name} {self._stat_label(d.stat)} {dir_text} {abs(d.delta)}"
                    )

    def _resolve_defend(self, actor: Combatant, result: ActionResult):
        actor.defending = True
        result.defending = True
        result.add_log(f"{actor.name} 进入防御姿态！")

    def _resolve_flee(self, action: dict, actor: Combatant,
                      targets: list[Combatant], result: ActionResult):
        if not actor.is_player:
            result.add_log("只有玩家可以逃跑！")
            return

        enemy_level = max((t.level for t in targets if t.is_alive), default=1)
        enemy_spd = max((t.attrs.get("agility", 10) for t in targets if t.is_alive), default=10)

        # 优先世界自定义逃跑公式
        custom_flee = self._cf.get("calculate_flee_chance")
        if custom_flee:
            chance = custom_flee(actor, enemy_level, enemy_spd)
        else:
            chance = calc_flee_chance(actor.level, enemy_level)

        if random.random() < chance:
            result.fled = True
            result.add_log(f"{actor.name} 成功逃跑！")
        else:
            result.add_log(f"{actor.name} 逃跑失败！")
