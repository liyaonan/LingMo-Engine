# lingmo_engine/plugins/combat/session.py

"""战斗会话状态机 - 管理回合流转、操作队列、战斗日志"""

import logging
from enum import Enum
from typing import Optional, Callable

from lingmo_engine.core.encounter_session import EncounterSession
from lingmo_engine.plugins.combat.engine import Combatant, ActiveBuff
from lingmo_engine.plugins.combat.resolver import ActionResolver, _check_stun_disable, compute_display_value
from lingmo_engine.plugins.combat.abilities import AbilitySystem
from lingmo_engine.core.protocols.item_system import ItemSystemInterface
from lingmo_engine.plugins.combat.ai.registry import AIStrategyRegistry
from lingmo_engine.plugins.combat.formulas import get_attr_by_role


class CombatPhase(Enum):
    IDLE = "idle"
    PLAYER_TURN = "player_turn"
    RESOLVING = "resolving"
    ENEMY_TURN = "enemy_turn"
    VICTORY = "victory"
    DEFEAT = "defeat"
    FLEE = "flee"


class CombatSession(EncounterSession):
    """战斗会话状态机"""

    MAX_ROUNDS = 50
    _logger = logging.getLogger("lingmo_engine.combat")

    def __init__(
        self,
        player: Combatant,
        enemies: list[Combatant],
        ability_system: AbilitySystem,
        item_system: ItemSystemInterface,
        ai_registry: AIStrategyRegistry,
        attrs_schema: dict,
        ai_strategy_name: str = "default",
        on_state_update: Optional[Callable] = None,
        plugin_registry=None,
        combat_functions: dict | None = None,
        ability_rarities: dict | None = None,
        ability_categories: dict | None = None,
        statuses: set[str] | None = None,
        value_scale_table: dict | None = None,
        cost_scale_table: dict | None = None,
        allies: list | None = None,
        attr_labels: dict | None = None,
    ):
        super().__init__(player=player, narrative_hint="")
        self.enemies = enemies
        self.allies = allies or []
        self.ability_system = ability_system
        self.items = item_system
        self.attrs_schema = attrs_schema
        self._attr_labels = attr_labels or {}
        self._statuses = statuses
        self.group_name = ""
        self.ai = ai_registry.get(ai_strategy_name)
        self.resolver = ActionResolver(
            ability_system, item_system, attrs_schema, combat_functions,
            statuses=statuses,
            value_scale_table=value_scale_table,
            cost_scale_table=cost_scale_table,
            attr_labels=attr_labels or {},
        )
        self._cost_scale_func = self.resolver.scale_cost
        if plugin_registry:
            self.resolver.set_plugin_registry(plugin_registry)
        self._on_state_update = on_state_update
        self.ability_rarities = ability_rarities or {}
        self.ability_categories = ability_categories or {}
        self.replay_actions: list[dict] = []

        self.phase = CombatPhase.IDLE
        self.round = 0
        self.combat_log: list[str] = []
        self._inventory: list[dict] = []
        self.player_ability_ids: list[str] = []

    def _log(self, msg: str) -> None:
        """写入战斗日志并同时输出到后台。"""
        self.combat_log.append(msg)
        self._logger.info(msg)

    def _log_lines(self, lines: list[str]) -> None:
        """批量写入战斗日志并同时输出到后台。"""
        self.combat_log.extend(lines)
        for line in lines:
            self._logger.info(line)

    def _record_replay(self, actor_id: str, actor_side: str, action_type: str,
                       action_name: str, targets: list[dict], effects: list[dict]) -> None:
        """记录行动回放数据"""
        self.replay_actions.append({
            "actor_id": actor_id,
            "actor_name": actor_id,
            "actor_side": actor_side,
            "action_type": action_type,
            "action_name": action_name,
            "targets": targets,
            "effects": effects,
        })

    def start(self) -> dict:
        """开始战斗，进入玩家回合"""
        self.replay_actions = []
        self.phase = CombatPhase.PLAYER_TURN
        self.round = 1
        self._log(f"=== 战斗开始！第 {self.round} 回合 ===")
        return self._build_state()

    def submit_player_action(self, action: dict) -> dict:
        """接收玩家操作"""
        if self.phase != CombatPhase.PLAYER_TURN:
            return self._build_state()

        action_type = action.get("type", "attack")
        # 不可行动状态检查（defend 放行）
        if action_type != "defend" and not self._player_can_act():
            self._log("你无法行动！")
            self.phase = CombatPhase.ENEMY_TURN
            self._process_enemy_turns()
            return self._finish_round()

        self.phase = CombatPhase.RESOLVING

        result = self.resolver.resolve(
            action, self.player, self.enemies, self.allies + [self.player]
        )
        self._log_lines(result.logs)

        # 记录玩家行动回放
        if result.target_deltas:
            for delta in result.target_deltas:
                effect_data = {"type": delta.stat, "value": delta.delta}
                if getattr(delta, "is_pursuit", False):
                    effect_data["pursuit"] = True
                if getattr(delta, "name", ""):
                    effect_data["name"] = delta.name
                self._record_replay(
                    actor_id=self.player.name, actor_side="player",
                    action_type=action.get("type", "attack"),
                    action_name=action.get("ability_id", "攻击"),
                    targets=[{"id": delta.target_name, "side": self._get_side(delta.target_name)}],
                    effects=[effect_data],
                )

        if result.fled:
            self.phase = CombatPhase.FLEE
            return self._build_state()

        self._last_items_consumed = list(result.items_consumed)
        for item_id in result.items_consumed:
            for entry in self._inventory:
                if entry["item_id"] == item_id and entry["quantity"] > 0:
                    entry["quantity"] -= 1
                    break
        self._inventory = [e for e in self._inventory if e["quantity"] > 0]

        if self._all_enemies_dead():
            self.phase = CombatPhase.VICTORY
            return self._build_state()

        self.phase = CombatPhase.ENEMY_TURN

        # 队友 AI 行动
        self._process_ally_turns()

        # 检查队友行动后敌人是否全灭
        if self._all_enemies_dead():
            self.phase = CombatPhase.VICTORY
            return self._build_state()

        self._process_enemy_turns()

        return self._finish_round()

    def _finish_round(self) -> dict:
        """回合结束：胜负检查 → 冷却递减 → 清防御 → tick → 回合递增"""
        if not self.player.is_alive:
            self.phase = CombatPhase.DEFEAT
            return self._build_state()

        if self._all_enemies_dead():
            self.phase = CombatPhase.VICTORY
            return self._build_state()

        self._tick_cooldowns()
        self.player.defending = False
        for a in self.allies:
            a.defending = False
        for e in self.enemies:
            e.defending = False

        self.round += 1
        if self.round > self.MAX_ROUNDS:
            self.phase = CombatPhase.DEFEAT
            self._log("战斗时间过长，强制结束！")
            return self._build_state()

        self._tick_buffs()

        self.phase = CombatPhase.PLAYER_TURN
        state = self._build_state()
        self.replay_actions = []
        self._log(f"=== 第 {self.round} 回合 ===")
        return state

    def _player_can_act(self) -> bool:
        return not _check_stun_disable(self.player.buffs, statuses=self._statuses)

    def _tick_buffs(self):
        """回合切换时对所有存活者执行 buff tick（每回合末用最新状态重算）"""
        all_combatants = [self.player] + self.allies + self.enemies
        for combatant in all_combatants:
            if not combatant.is_alive:
                continue
            expired = []
            for buff in combatant.buffs:
                # 即时 buff 仅做展示，不参与 tick 重算和倒计时
                if buff.effect.get("_instant"):
                    continue
                caster = self._find_combatant_by_name(buff.caster_name) or combatant
                # 从施放者视角确定敌我列表
                tick_targets, tick_allies = self._get_perspective_lists(caster)
                eff_type = buff.effect.get("type")
                # 护盾/眩晕仅 duration 倒计时，不做属性重算
                if eff_type in ("shield", "stun"):
                    pass
                elif eff_type in ("dot", "fixed_dot"):
                    # DOT tick: 伤害作用于 buff 携带者，保留原始施放者 ATK
                    tick_effect = dict(buff.effect)
                    tick_deltas = self.resolver.resolve_effect(
                        tick_effect, caster,
                        tick_targets, tick_allies,
                        create_buffs=False,
                        override_targets=[combatant],
                    )
                    for td in (tick_deltas or []):
                        self._record_replay(
                            actor_id=combatant.name,
                            actor_side=self._get_side(combatant.name),
                            action_type="dot", action_name=buff.name,
                            targets=[{"id": td.target_name,
                                      "side": self._get_side(td.target_name)}],
                            effects=[{"type": "dot", "value": td.delta}],
                        )
                elif eff_type != "shield":
                    tick_effect = dict(buff.effect, target="self")
                    self.resolver.resolve_effect(
                        tick_effect, caster,
                        tick_targets, tick_allies,
                        create_buffs=False,
                    )
                buff.remaining -= 1
                if buff.remaining <= 0:
                    expired.append(buff)
                    self._log(
                        f"{combatant.name} 的 {buff.name} 效果消失了"
                    )
            for b in expired:
                combatant.buffs.remove(b)
                # 护盾过期：扣减对应护盾值
                if b.effect.get("type") == "shield":
                    shield_value = b.effect.get("_applied_shield", 0)
                    combatant.shield = max(0, combatant.shield - shield_value)

    def _find_combatant_by_name(self, name: str) -> Combatant | None:
        if self.player.name == name:
            return self.player
        for a in self.allies:
            if a.name == name:
                return a
        for e in self.enemies:
            if e.name == name:
                return e
        return None

    def _get_side(self, name: str) -> str:
        """根据名称判断阵营"""
        if self.player.name == name:
            return "player"
        if any(a.name == name for a in self.allies):
            return "ally"
        return "enemy"

    def _get_perspective_lists(self, combatant: Combatant) -> tuple[list, list]:
        """从指定 combatant 的视角返回 (enemies, allies) 列表。"""
        side = self._get_side(combatant.name)
        if side in ("player", "ally"):
            return self.enemies, self.allies + [self.player]
        return [self.player] + self.allies, self.enemies

    def _process_enemy_turns(self):
        """处理所有存活敌人的行动（按 speed role 降序，跳过不可行动者）"""
        alive_enemies = sorted(
            [e for e in self.enemies if e.is_alive],
            key=lambda e: get_attr_by_role(e, self.attrs_schema, "speed"),
            reverse=True,
        )
        for enemy in alive_enemies:
            if not self.player.is_alive:
                self._log(f"{enemy.name} 及后续敌人因玩家倒下而跳过行动")
                break
            if _check_stun_disable(enemy.buffs, statuses=self._statuses):
                self._log(f"{enemy.name} 无法行动！")
                continue
            action = self.ai.choose_action(
                enemy, self.player, alive_enemies, self.ability_system,
                attrs_schema=self.attrs_schema,
            )
            result = self.resolver.resolve(
                action, enemy, [self.player], alive_enemies,
            )
            self._log_lines(result.logs)
            if result.target_deltas:
                for delta in result.target_deltas:
                    effect_data = {"type": delta.stat, "value": delta.delta}
                    if getattr(delta, "is_pursuit", False):
                        effect_data["pursuit"] = True
                    if getattr(delta, "name", ""):
                        effect_data["name"] = delta.name
                    self._record_replay(
                        actor_id=enemy.name, actor_side="enemy",
                        action_type=action.get("type", "attack"),
                        action_name=action.get("ability_id", "攻击"),
                        targets=[{"id": delta.target_name, "side": self._get_side(delta.target_name)}],
                        effects=[effect_data],
                    )

    def _process_ally_turns(self) -> None:
        """AI 队友依次行动"""
        for ally in self.allies:
            if not ally.is_alive:
                continue
            if _check_stun_disable(ally.buffs, statuses=self._statuses):
                self._log(f"{ally.name} 无法行动！")
                continue
            action = self.ai.choose_action(ally, self.player, self.enemies,
                                           self.ability_system,
                                           attrs_schema=self.attrs_schema)
            result = self.resolver.resolve(action, ally, self.enemies,
                                           self.allies + [self.player])
            self._log_lines(result.logs)
            if result.target_deltas:
                for delta in result.target_deltas:
                    effect_data = {"type": delta.stat, "value": delta.delta}
                    if getattr(delta, "is_pursuit", False):
                        effect_data["pursuit"] = True
                    if getattr(delta, "name", ""):
                        effect_data["name"] = delta.name
                    self._record_replay(
                        actor_id=ally.name, actor_side="ally",
                        action_type=action.get("type", "attack"),
                        action_name=action.get("ability_id", "攻击"),
                        targets=[{"id": delta.target_name, "side": self._get_side(delta.target_name)}],
                        effects=[effect_data],
                    )

    def _tick_cooldowns(self):
        for combatant in [self.player] + self.allies + self.enemies:
            for ability_id in list(combatant.cooldowns.keys()):
                if combatant.cooldowns[ability_id] > 0:
                    combatant.cooldowns[ability_id] -= 1
                    if combatant.cooldowns[ability_id] == 0:
                        del combatant.cooldowns[ability_id]

    def _all_enemies_dead(self) -> bool:
        return all(not e.is_alive for e in self.enemies)

    def get_available_actions(self) -> list[str]:
        return ["ability", "defend", "item", "flee"]

    def get_available_abilities(self) -> list[dict]:
        return self.ability_system.get_player_available_abilities(
            self.player_ability_ids,
            self.player.attrs,
            self.player.hp,
            self.player.cooldowns,
            level=self.player.level,
            scale_func=self._cost_scale_func,
        )

    def calculate_rewards(self) -> dict:
        from lingmo_engine.plugins.combat.formulas import calculate_rewards, loot_drop

        total_exp = 0
        all_loot = []

        # 优先世界自定义战利品公式
        custom_rewards = None
        if self.resolver._cf:
            custom_rewards = self.resolver._cf.get("calculate_rewards")

        for enemy in self.enemies:
            if enemy.is_alive:
                continue
            if custom_rewards:
                reward = custom_rewards(enemy)
                total_exp += reward.get("exp_gained", 0)
                all_loot.extend(reward.get("loot", []))
            else:
                reward = calculate_rewards(enemy)
                total_exp += reward.get("exp_gained", 0)
            if enemy.loot_table:
                all_loot.extend(loot_drop(enemy.loot_table))

        for loot in all_loot:
            item_id = loot.get("item_id", "")
            if item_id and self.items:
                item = self.items.get_item(item_id)
                if item:
                    loot["name"] = item.name

        return {"exp_gained": total_exp, "loot": all_loot}

    def _build_state(self) -> dict:
        # 构建 pool 属性列表（schema pair 驱动：仅当前值属性入选，排除 max_* 条目）
        # 约定：当前值属性的 pair 指向对应的 max_* 属性，max_* 自身也有 pair 指回当前值
        # 通过 not name.startswith("max_") 过滤掉 max 端，只保留当前值端
        pool_attrs = []
        for name, defn in self.attrs_schema.items():
            if defn.get("combat_type") != "pool":
                continue
            pair = defn.get("pair", "")
            if pair and not name.startswith("max_"):
                pool_attrs.append({
                    "name": name,
                    "label": defn.get("label", name),
                    "color": defn.get("color", "#666"),
                    "max_name": pair,
                })

        state = {
            "phase": self.phase.value,
            "round": self.round,
            "player": self._combatant_to_dict(self.player),
            "enemies": [self._combatant_to_dict(e) for e in self.enemies],
            "allies": [self._combatant_to_dict(a) for a in self.allies],
            "replay_actions": list(self.replay_actions),
            "log": list(self.combat_log),
            "available_actions": self.get_available_actions(),
            "available_abilities": self.get_available_abilities(),
            "pool_attrs": pool_attrs,
            "attr_labels": self._attr_labels,
            "ability_rarities": self.ability_rarities,
            "ability_categories": self.ability_categories,
            "level_colors": self._get_level_colors(),
        }
        if self._inventory:
            state["available_items"] = self._inventory
        if hasattr(self, '_last_items_consumed') and self._last_items_consumed:
            state["items_consumed"] = list(self._last_items_consumed)
        return state

    def set_inventory(self, inventory: list[dict]) -> None:
        enriched = []
        for entry in inventory:
            item = self.items.get_item(entry.get("item_id", ""))
            if item is None:
                continue
            if not (item.is_consumable and item.combat_only):
                continue
            # 仅单一 enemy 需要目标选择，self/all_enemy/all_ally 直接使用
            needs_target = any(
                e.target == "enemy" for e in item.effects
            )
            # 转换 costs 为前端可用格式
            item_costs = [
                {"resource": c.resource, "amount": c.amount}
                for c in item.costs if c.amount > 0
            ]
            # 转换 effects 为前端可用格式（用于判断目标类型 + 显示增幅后数值）
            item_effects = []
            for e in item.effects:
                ed = {
                    "type": e.type,
                    "target": e.target,
                    "value": e.value,
                    "power": e.power,
                    "modifier": e.modifier,
                    "duration": e.duration,
                    "chance": e.chance,
                    **({"name": e.name} if e.name else {}),
                }
                # fixed_damage / fixed_dot 预计算增幅后数值
                if e.type in ("fixed_damage", "fixed_dot") and e.value:
                    creator = getattr(item, 'creator_stats', {})
                    if creator and self.resolver._value_scale_table:
                        ed["display_value"] = compute_display_value(
                            e.value, e.scale_stat, e.power, creator,
                            self.resolver._value_scale_table,
                            self.resolver._amplify_creator_attrs,
                        )
                item_effects.append(ed)
            enriched.append({
                "item_id": entry["item_id"],
                "name": item.name,
                "quantity": entry.get("quantity", 0),
                "description": item.description,
                "rarity": item.rarity,
                "is_consumable": True,
                "combat_only": True,
                "needs_target": needs_target,
                "costs": item_costs,
                "effects": item_effects,
            })
        self._inventory = enriched

    def _get_level_colors(self) -> list[dict]:
        """获取 Level 配色（优先从世界注入获取，否则使用默认值）"""
        if hasattr(self, '_level_colors') and self._level_colors:
            return self._level_colors
        return [
            {"min": 1, "max": 3, "color": "#a0a0a0", "label": "白色"},
            {"min": 4, "max": 6, "color": "#50c878", "label": "绿色"},
            {"min": 7, "max": 9, "color": "#4a9eff", "label": "蓝色"},
            {"min": 10, "max": 12, "color": "#b066ff", "label": "紫色"},
            {"min": 13, "max": 99, "color": "#c9a961", "label": "金色"},
        ]

    @staticmethod
    def _combatant_to_dict(c: Combatant) -> dict:
        return {
            "name": c.name,
            "level": c.level,
            "vitality": c.hp,
            "max_vitality": c.max_hp,
            "shield": c.shield,
            "is_player": c.is_player,
            "defending": c.defending,
            "side": c.side,
            "is_ai_controlled": c.is_ai_controlled,
            "cooldowns": dict(c.cooldowns),
            "attrs": dict(c.attrs),
            "spiritual_roots": list(c.extra.get("spiritual_roots", [])),
            "buffs": [
                {
                    "id": b.id, "name": b.name,
                    "remaining": b.remaining,
                    "effect_type": b.effect.get("type", ""),
                    "stat": b.effect.get("stat", ""),
                    "modifier": b.effect.get("modifier", 0),
                    "value": b.effect.get("value", 0),
                    "status": b.effect.get("status", ""),
                    "source_name": b.effect.get("name", "") or b.name,
                    "source_key": b.effect.get("_source_key", ""),
                }
                for b in c.buffs
            ],
        }

    def get_summary(self) -> dict:
        return {
            "group_name": self.group_name,
            "phase": self.phase.value,
            "log": list(self.combat_log),
            "round": self.round,
        }

    def finish(self) -> dict:
        self.phase = CombatPhase.VICTORY
        return self.get_summary()
