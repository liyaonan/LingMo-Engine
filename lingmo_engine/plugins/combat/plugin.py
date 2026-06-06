"""战斗插件 - 适配状态机，处理WebSocket消息路由"""

from __future__ import annotations

import logging
from typing import Optional, TypedDict, NotRequired

from lingmo_engine.core.encounter_plugin import EncounterPlugin
from lingmo_engine.core.events import PluginEvent, PluginName
from lingmo_engine.core.types import (
    ToolDefinition, ToolParameter, ModuleResult,
    Action, ActionUpdatePlayer, ActionAddItems,
    ActionRemoveItems, ActionPublishMessage,
    ActionGenerateNarrative, ActionSaveState,
    ActionSendStateUpdate, ActionClearSceneEnemies,
)
from lingmo_engine.core.utils import interpolate_table
from lingmo_engine.plugins.combat.ability_generator import _CATEGORY_MAP as CATEGORY_MAP


class CombatPluginState(TypedDict):
    """战斗插件状态 schema。"""
    scene_enemies: NotRequired[dict | None]
    player: NotRequired[dict]
    inventory: NotRequired[list[dict]]
    equipment: NotRequired[dict]
from lingmo_engine.plugins.combat.engine import Combatant, ActiveBuff
from lingmo_engine.plugins.combat.session import CombatSession
from lingmo_engine.plugins.combat.abilities import AbilitySystem
from lingmo_engine.core.protocols.item_system import ItemSystemInterface
from lingmo_engine.plugins.combat.ai.registry import AIStrategyRegistry

logger = logging.getLogger(__name__)


class CombatPlugin(EncounterPlugin):
    """战斗插件 v0.2.0 - 交互式回合制战斗"""

    name = PluginName.COMBAT
    version = "0.2.0"
    depends_on: list[str] = [PluginName.INVENTORY]
    ws_prefix = "combat"

    def __init__(self):
        super().__init__()
        self._loaded: bool = False
        self._game_state = None
        self._ability_system: Optional[AbilitySystem] = None
        self._item_system: Optional[ItemSystemInterface] = None
        self._ai_registry = AIStrategyRegistry()
        self._state: dict = {}
        self._attrs_schema: dict = {}
        self._equip_bonus: dict[str, int] = {}
        self._revert_fn = None  # 战后还原增幅的函数

    def set_game_state(self, state):
        """注入 GameState 引用（由 PluginRegistry 自动调用）。"""
        self._game_state = state

    def load_state(self, state: dict) -> None:
        self._state = state

    def get_state(self) -> dict:
        """战斗状态从 GameState 快照获取，不重复写入 state.json。

        _state 是 load_state_to_all_plugins 传入的全量快照缓存，
        用于 get_context_hint 等方法读取 scene_enemies 等数据。
        scene_enemies 已由 GameState 顶层持久化，无需插件再存储。
        """
        return {}

    def get_context_hint(self, state: dict) -> str:
        """注入遭遇敌人上下文提示到 LLM。"""
        scene_enemies = state.get("scene_enemies")
        if not scene_enemies:
            return ""
        groups = scene_enemies.get("groups", [])
        group_names = [g.get("name", "未知敌人") for g in groups]
        forced = scene_enemies.get("forced", False)
        if forced:
            return f"强制遭遇: {', '.join(group_names)}。玩家无法回避，引导进入战斗。"
        else:
            return f"当前场景有敌人: {', '.join(group_names)}。等待玩家选择迎战或回避。"

    def on_load(self) -> None:
        """插件加载时初始化技能/物品系统（仅执行一次）"""
        if self._loaded:
            return
        self._loaded = True
        world = self._world
        if world:
            abilities_data = list(world.abilities.values()) if hasattr(world, 'abilities') and world.abilities else []
            self._ability_system = AbilitySystem(abilities_data)

            # 注册显示增幅函数到 GameState
            combat_functions = world.get_combat_functions()
            if combat_functions and "amplify_player_snapshot" in combat_functions:
                gs = self._state
                if gs and hasattr(gs, "set_amplify_fn"):
                    gs.set_amplify_fn(combat_functions["amplify_player_snapshot"])
            self._revert_fn = combat_functions.get("revert_player_amplification") if combat_functions else None

        # 缓存战斗属性 schema
        if world:
            self._attrs_schema = world.get_combat_attrs_schema()

        # 通过 EventBus 获取 InventoryPlugin 的 ItemSystem（单一数据源）
        self._item_system = self._bus.request(PluginEvent.ITEMS_GET_SYSTEM) if self._bus else None
        if self._item_system is None:
            logger.error("CombatPlugin: 无法获取 ItemSystem，请确保 InventoryPlugin 已加载且依赖关系正确")

        # 注册 EventBus handler，供其他插件解耦调用
        if self._bus:
            self._bus.handle(PluginEvent.ABILITY_GENERATE, self._handle_ability_generate)
            self._bus.handle(PluginEvent.COMBAT_COMPUTE_DISPLAY_VALUE, self._handle_compute_display_value)

    # ── EventBus handler（供其他插件解耦调用） ──

    def _handle_ability_generate(self, ability_input: dict, affix_defs: dict,
                                 rarity_info: dict, **kwargs):
        """EventBus handler：代理 affix_generate_ability，解耦直接导入。"""
        from lingmo_engine.plugins.combat.ability_generator import affix_generate_ability
        return affix_generate_ability(ability_input, affix_defs, rarity_info, **kwargs)

    @staticmethod
    def _handle_compute_display_value(effect_value: float, scale_stat: str | None,
                                      power: float, creator_stats: dict,
                                      vs_table: dict, amplify_fn) -> int:
        """EventBus handler：代理 compute_display_value，解耦直接导入。"""
        from lingmo_engine.plugins.combat.resolver import compute_display_value
        return compute_display_value(effect_value, scale_stat, power,
                                     creator_stats, vs_table, amplify_fn)

    def get_skill_dirs(self) -> list[str]:
        """返回插件自带 Skill 目录。"""
        import os
        skills_dir = os.path.join(os.path.dirname(__file__), "skills")
        if os.path.isdir(skills_dir):
            return [skills_dir]
        return []

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="spawn_npcs",
                description=(
                    "与已有 NPC 发生战斗。用于剧情中与角色管理器里已存在的 NPC 对战。"
                    "NPC 的属性、技能、装备从角色数据自动加载，无需手动指定。"
                    "调用后系统展示敌人卡片，由玩家选择是否进入战斗。"
                ),
                parameters=[
                    ToolParameter(
                        name="forced",
                        type="boolean",
                        description="是否强制战斗。true=玩家必须战斗，false=玩家可选择忽略",
                        required=False,
                    ),
                    ToolParameter(
                        name="groups",
                        type="array",
                        description=(
                            "NPC 组列表。每组是一张敌人卡片。格式: "
                            '[{"name": "组名", "npcs": ['
                            '{"character_id": "角色ID或名称(必填)", '
                            '"name": "卡片显示名(可选，覆盖角色原名)}'
                            "]}]"
                        ),
                        required=True,
                    ),
                ],
            ),
            ToolDefinition(
                name="spawn_hostiles",
                description=(
                    "根据模板生成临时敌人。用于野怪、邪修、土匪等战斗场景。"
                    "可用模板: beast_monster(妖兽), demon_cultivator(邪修), "
                    "spirit_beast(灵兽), artifact_spirit(器灵), human_cultivator(人族修士)。"
                    "调用后系统展示敌人卡片，由玩家选择是否进入战斗。"
                ),
                parameters=[
                    ToolParameter(
                        name="forced",
                        type="boolean",
                        description="是否强制战斗。true=玩家必须战斗，false=玩家可选择忽略",
                        required=False,
                    ),
                    ToolParameter(
                        name="groups",
                        type="array",
                        description=(
                            "敌人组列表。每组是一张敌人卡片。格式: "
                            '[{"name": "组名", "enemies": ['
                            '{"template": "模板ID(必填)", '
                            '"name": "自定义显示名称(可选)", '
                            '"count": 数量(默认1), '
                            '"level": 等级(默认1), '
                            '"aptitude": 资质(0.0-1.0, 默认0.5, 0.3=愚钝, 0.8=优秀, 0.95=天才), '
                            '"abilities": ["技能ID"]}'
                            "]}]"
                        ),
                        required=True,
                    ),
                ],
            ),
        ]

    # write_combat_report 是系统内部工具，不暴露给LLM
    # 由 server.py 战斗结束后调用 write_combat_report 获取prompt并注入system消息

    def execute_tool(self, tool_name: str, params: dict) -> ModuleResult:
        if tool_name == "spawn_npcs":
            return self._spawn_npcs(params)
        if tool_name == "spawn_hostiles":
            return self._spawn_hostiles(params)
        return ModuleResult(success=False, log=f"未知工具: {tool_name}")

    def _build_encounter_result(
        self, groups_json: list, forced: bool, warnings: list[str],
    ) -> ModuleResult:
        """构建遭遇 ModuleResult 的公共方法。

        实际的 state 写入通过 ModuleResult.data["state_updates"] 由
        tool_executor.apply_result() 统一处理，此处不直接修改 _state。
        """
        encounter_data = {
            "groups": groups_json,
            "forced": forced,
        }

        group_names = "、".join(g["name"] for g in groups_json)
        logger.info("Spawned encounter: %s (forced=%s)", group_names, forced)

        log = f"敌人已生成：{group_names}"
        if warnings:
            log += "\n⚠ 以下问题需要关注：\n" + "\n".join(warnings)

        return ModuleResult(
            success=True,
            data={
                "encounter_created": True,
                "group_count": len(groups_json),
                "groups": groups_json,
                "forced": forced,
                "state_updates": {
                    "scene_enemies": encounter_data,
                },
                "_events": [
                    ("encounter", {
                        "forced": forced,
                        "groups": groups_json,
                    }),
                ],
            },
            log=log,
        )

    def _spawn_npcs(self, params: dict) -> ModuleResult:
        """生成 NPC 遭遇（LLM 调用）— 与已有角色战斗，只注册不触发。"""
        groups_data = params.get("groups", [])
        if not groups_data:
            return ModuleResult(success=False, log="NPC 组列表为空")

        state = self._state or {}
        char_manager = state.get("__character_manager")

        groups_json: list[dict] = []
        for g in groups_data:
            group_name = g.get("name", "未命名组")
            enemy_list: list[dict] = []
            for npc in g.get("npcs", []):
                character_id = npc.get("character_id", "")
                if not character_id:
                    return ModuleResult(
                        success=False, log="NPC character_id 不能为空")

                char = self._find_character_by_template(char_manager, character_id)
                if char is None:
                    return ModuleResult(
                        success=False,
                        log=f"NPC '{character_id}' 不存在。"
                            "请使用角色管理器中已有的角色 ID 或名称。",
                    )

                default_name = char.name
                edict: dict = {
                    "source": "npc",
                    "character_id": character_id,
                    "name": npc.get("name") or default_name,
                }
                enemy_list.append(edict)
            if not enemy_list:
                return ModuleResult(
                    success=False,
                    log=f"组 '{group_name}' 的 NPC 列表为空。"
                        "请使用 \"npcs\" 键名指定 NPC，而非 \"enemies\"。")
            groups_json.append(
                {"name": group_name, "enemies": enemy_list})

        return self._build_encounter_result(
            groups_json, params.get("forced", False), [])

    def _spawn_hostiles(self, params: dict) -> ModuleResult:
        """根据模板生成临时敌人（LLM 调用）— 只注册不触发。"""
        groups_data = params.get("groups", [])
        if not groups_data:
            return ModuleResult(success=False, log="敌人组列表为空")

        warnings: list[str] = []

        state = self._state or {}
        char_manager = state.get("__character_manager")

        groups_json: list[dict] = []
        for g in groups_data:
            group_name = g.get("name", "未命名组")
            enemy_list: list[dict] = []
            for e in g.get("enemies", []):
                template_id = e.get("template", "")
                if not template_id:
                    return ModuleResult(
                        success=False, log="template 不能为空")

                # 从 CharacterManager 查找模板，找不到则报错终止
                template = self._find_character_by_template(
                    char_manager, template_id)
                if template is None:
                    return ModuleResult(
                        success=False,
                        log=f"模板 '{template_id}' 不存在。"
                            "请使用已有的模板 ID，如: beast_monster, "
                            "demon_cultivator, spirit_beast, "
                            "artifact_spirit, human_cultivator。",
                    )

                # 从预设模板查找 aptitude_bias，用于后续属性生成
                aptitude_bias = self._get_preset_aptitude_bias(template_id)

                # 资质 clamp 到 [0.0, 1.0]，默认 0.5（普通）
                aptitude = e.get("aptitude", 0.5)
                try:
                    aptitude = max(0.0, min(1.0, float(aptitude)))
                except (ValueError, TypeError):
                    aptitude = 0.5

                edict: dict = {
                    "source": "hostile",
                    "template": template_id,
                    "name": e.get("name") or template.name,
                    "count": e.get("count", 1),
                    "level": e.get("level", 1),
                    "aptitude": aptitude,
                    "aptitude_bias": aptitude_bias,
                }
                if e.get("abilities"):
                    edict["abilities"] = e["abilities"]
                enemy_list.append(edict)
            if not enemy_list:
                return ModuleResult(
                    success=False,
                    log=f"组 '{group_name}' 的敌人列表为空。"
                        "请在 \"enemies\" 数组中至少指定一个敌人。")
            groups_json.append(
                {"name": group_name, "enemies": enemy_list})

        return self._build_encounter_result(
            groups_json, params.get("forced", False), warnings)

    @staticmethod
    def _format_combat_report_prompt(
        group_name: str, result_text: str, log_text: str,
    ) -> str:
        return (
            "请将以下战斗日志总结为精炼的战斗经过摘要。"
            "要求：\n"
            "1. 200-400字，聚焦关键攻防动作和战斗转折点\n"
            "2. 描述最终一击和战斗结果\n"
            "3. 使用【】标注技能名称\n"
            "4. 直接输出总结文本，不要加任何标签或前缀\n\n"
            f"遭遇: {group_name}  结果: {result_text}\n\n"
            f"战斗日志:\n{log_text}"
        )

    def write_combat_report(self, params: dict) -> ModuleResult:
        """生成战斗叙述（系统调用）- 将战斗日志交给LLM改写"""
        group_name = params.get("group_name", "未知敌人")
        result_text = params.get("result", "")
        combat_log = params.get("combat_log", "")

        prompt = self._format_combat_report_prompt(
            group_name, result_text, combat_log,
        )

        return ModuleResult(
            success=True,
            data={"prompt": prompt, "group_name": group_name},
            log=f"战斗报告生成请求：{group_name}",
        )

    def handle_websocket(self, message: dict, game_state) -> dict | None:
        """处理 WebSocket 消息。"""
        msg_type = message.get("type", "")

        if msg_type == "combat_action":
            return self._handle_ws_combat_action(message, game_state)

        if msg_type == "trigger_combat":
            return self._handle_ws_trigger_combat(message, game_state)

        if msg_type == "combat_get_state":
            return self._handle_ws_get_state(message, game_state)

        if msg_type == "write_combat_report":
            params = message.get("params", {})
            mr = self.write_combat_report(params)
            return {"success": mr.success, "data": {"prompt": mr.data.get("prompt", "")}}

        if msg_type == "abilities_open":
            return self._get_abilities_state(game_state)

        if msg_type == "ability_action":
            return self._handle_ws_ability_action(message, game_state)

        return None

    def _create_session(self, params, game_state):
        raise NotImplementedError("CombatPlugin uses trigger_combat, not start_session")

    def _process_action(self, action, session):
        return self.handle_combat_action(action)

    def _on_session_end(self, session, game_state):
        return []

    def _build_narrative_prompt(self, session):
        log_text = "\n".join(str(entry) for entry in session.combat_log)
        return f"战斗日志:\n{log_text}"

    def _handle_ws_combat_action(self, msg: dict, game_state) -> dict:
        """处理玩家战斗操作，返回结果（含 _actions），消息类型与前端一致。"""
        if not self.has_active_combat():
            return {"type": "no_combat"}
        action = msg.get("action", {})
        result = self.handle_combat_action(action)

        phase = result.get("phase")
        if not phase:
            return {"type": "combat_state_update", "state": result}

        actions: list[Action] = []

        # 消耗物品（战斗中使用）
        items_consumed = result.get("items_consumed", [])
        if items_consumed:
            actions.append({"action": "remove_items", "items": [
                {"item_id": item_id, "quantity": 1} for item_id in items_consumed
            ]})

        if phase in ("victory", "defeat", "flee"):
            actions.append({"action": "clear_scene_enemies"})

            # 发射 COMBAT_ENDED 事件（供 CharacterPlugin 清理临时角色）
            if self._bus:
                cm = self._state.get("__character_manager") if self._state else None
                temp_ids = []
                if cm:
                    temp_ids = [c.id for c in cm.all() if getattr(c, "temporary", False)]
                self._bus.emit(PluginEvent.COMBAT_ENDED, {
                    "phase": phase,
                    "participant_ids": temp_ids,
                })

            if phase == "defeat":
                actions.append({"action": "update_player", "updates": {"vitality": 1}})
                actions.append({"action": "save_state"})
                actions.append({"action": "send_state_update"})
            else:
                player_update = self._apply_combat_player_update(result)
                if player_update:
                    actions.append({"action": "update_player", "updates": player_update})

                rewards = result.get("rewards", {})
                if rewards.get("exp_gained"):
                    pass

                reward_actions = self._apply_combat_rewards_actions(rewards)
                actions.extend(reward_actions)

                actions.append({"action": "save_state"})
                actions.append({"action": "send_state_update"})

            # 战斗叙述生成
            narr_action = self._build_combat_narrative_action(
                result, phase, result.get("rewards", {}))
            if narr_action:
                actions.append(narr_action)

            # 战利品消息
            rewards = result.get("rewards", {})
            loot_items = rewards.get("loot", [])
            if rewards.get("exp_gained", 0) > 0 or loot_items:
                # 构建文本摘要供调试面板显示
                parts = []
                exp_gained = rewards.get("exp_gained", 0)
                if exp_gained > 0:
                    parts.append(f"获得经验: {exp_gained}")
                if loot_items:
                    item_names = []
                    for item in loot_items:
                        name = item.get("name", item.get("item_id", "?"))
                        qty = item.get("quantity", 1)
                        item_names.append(f"{name} x{qty}")
                    parts.append("获得物品: " + "、".join(item_names))
                content_text = "战利品 — " + " | ".join(parts) if parts else ""

                actions.append({
                    "action": "publish_message",
                    "message": {
                        "role": "system",
                        "content": content_text,
                        "content_blocks": [{
                            "type": "loot_card",
                            "data": {
                                "exp": exp_gained,
                                "items": loot_items,
                            },
                        }],
                    },
                })

            # 返回 combat_state_update，前端根据 phase 判断结束
            # 展开完整 result 保留 replay_actions 等渲染所需字段
            response = {
                "type": "combat_state_update",
                "state": {
                    **result,
                    "rewards": result.get("rewards", {}),
                    "full_log": result.get("full_log", []),
                },
                "_actions": actions,
            }
        else:
            response = {
                "type": "combat_state_update",
                "state": result,
                "_actions": actions,
            }

        result.pop("items_consumed", None)
        return response

    def _apply_combat_player_update(self, result: dict) -> dict[str, object]:
        """从战斗结果中动态提取玩家属性更新，还原为基础值后保存。"""
        player_data = result.get("player", {})
        pdata = {
            "vitality": player_data.get("vitality", 0),
            "max_vitality": player_data.get("max_vitality", 0),
            "level": player_data.get("level", 1),
        }
        for name, value in player_data.get("attrs", {}).items():
            pdata[name] = value
        # 还原增幅：将战斗中的增幅值转回基础值存入 attrs
        if self._revert_fn:
            pdata = self._revert_fn(pdata)
        # 展平为 update_player 所需的 kv 格式
        player_update = {}
        for key in ("vitality", "max_vitality"):
            player_update[key] = pdata.get(key, 0)
        for name, value in pdata.items():
            if name in ("vitality", "max_vitality", "level"):
                continue
            player_update[name] = value
        return player_update

    def _apply_combat_rewards_actions(self, rewards: dict) -> list[Action]:
        """构建战利品相关的 _actions。"""
        actions: list[Action] = []
        items_to_add = []
        if rewards.get("loot"):
            for loot_item in rewards["loot"]:
                items_to_add.append({
                    "item_id": loot_item["item_id"],
                    "quantity": loot_item.get("quantity", 1),
                })
        if items_to_add:
            actions.append({"action": "add_items", "items": items_to_add})
        return actions

    def _build_combat_narrative_action(self, result: dict, phase: str, rewards: dict) -> ActionGenerateNarrative | None:
        """构建战斗叙述生成的 _action。"""
        full_log = result.get("full_log", [])
        if not full_log:
            return None

        log_text = "\n".join(
            entry.get("text", str(entry)) if isinstance(entry, dict) else str(entry)
            for entry in full_log
        )

        group_name = result.get("group_name", "未知敌人")
        phase_cn = {"victory": "胜利", "defeat": "败北", "flee": "逃跑"}
        result_text = phase_cn.get(phase, phase)

        prompt = self._format_combat_report_prompt(
            group_name, result_text, log_text,
        )

        return {
            "action": "generate_narrative",
            "stream_type": "combat_narrative",
            "prompt": prompt,
            "fallback_text": f"战斗结束了。你{result_text}了{group_name}。",
            "combat_result": result_text,
        }

    def _handle_ws_trigger_combat(self, msg: dict, game_state) -> dict:
        """触发战斗，返回初始战斗状态。"""
        group_index = msg.get("group_id", 0)
        state_snapshot = dict(game_state.data)
        # 注入 CharacterManager
        cm = game_state.character_manager
        if cm:
            state_snapshot["__character_manager"] = cm
        self.load_state(state_snapshot)
        result = self.spawn_combat_from_group(group_index, state_snapshot)
        if isinstance(result, dict) and "error" in result:
            return {"type": "error", "message": result["error"]}
        return {"type": "combat_start", "state": result}

    def _handle_ws_get_state(self, msg: dict, game_state) -> dict:
        """获取当前战斗状态。"""
        session = self.get_active_session()
        if session:
            return {"type": "combat_state_update", "state": session._build_state()}
        return None

    def _expand_ability_costs(self, ability: dict, level: int) -> dict:
        """根据等级缩放技能消耗和固定伤害/持续伤害显示值。"""
        cost_table = self._world.get_effect_cost_scale() if self._world else {}
        vs_table = self._world.get_effect_value_scale() if self._world else {}
        need_cost = cost_table and level > 0
        need_vs = vs_table and level > 0
        if not need_cost and not need_vs:
            return dict(ability)

        result = dict(ability)

        if need_cost:
            expanded_costs = []
            for cost in ability.get("costs", []):
                base = cost.get("amount", 0)
                if base > 0:
                    scale = interpolate_table(level, cost_table)
                    actual = max(1, int(base * scale))
                else:
                    actual = 0
                expanded_costs.append({"resource": cost["resource"], "amount": actual})
            result["costs"] = expanded_costs

        if need_vs:
            vs_scale = interpolate_table(level, vs_table)
            if vs_scale != 1.0:
                expanded_effects = []
                for e in ability.get("effects", []):
                    ec = dict(e)
                    if ec.get("type") in ("fixed_damage", "fixed_dot") and ec.get("value", 0) > 0:
                        ec["value"] = max(1, int(ec["value"] * vs_scale))
                    expanded_effects.append(ec)
                result["effects"] = expanded_effects

        return result

    def _get_abilities_state(self, game_state) -> dict:
        """构建技能面板完整状态。"""
        self.on_load()
        player = game_state.get_player()
        native_ids = list(player.abilities)

        # 将注册表动态技能合并到 AbilitySystem（确保 LLM 生成的技能可查）
        registry_abilities = game_state.get_all_registry_abilities()
        if registry_abilities and self._ability_system:
            self._ability_system.set_custom_abilities(registry_abilities)

        # 收集装备附加技能
        equip_ability_ids: set[str] = set()
        if self._bus:
            equip_data = self._bus.request(
                PluginEvent.EQUIPMENT_GET_BONUS, game_state.data,
            ) or {}
            for ea in equip_data.get("abilities", []):
                equip_ability_ids.add(ea)

        # 全部技能 = 原生 + 装备（不含重复）
        all_ids = list(native_ids)
        for ea in equip_ability_ids:
            if ea not in all_ids:
                all_ids.append(ea)

        player_level = getattr(player, "level", 1)

        # 分类和稀有度
        categories = []
        category_ids: set[str] = set()
        if self._world:
            cats = self._world.ability_categories or {}
            for c in cats.get("categories", []):
                categories.append({"id": c["id"], "name": c["name"]})
                category_ids.add(c["id"])

        # 分类映射：将生成技能的 category 映射到面板分类，未知分类兜底到 special
        _FALLBACK_CATEGORY = "special"

        # 展开全部技能完整定义（含等级缩放消耗）
        abilities = []
        for aid in all_ids:
            ability = self._ability_system.get_ability(aid)
            if ability:
                d = self._expand_ability_costs(ability, player_level)
                d["rarity_info"] = self._world.get_ability_rarity_info(ability.get("rarity", 25)) if self._world else {}
                if aid in equip_ability_ids:
                    d["source"] = "equipment"
                # 分类映射：不在已知分类中的 category 做归一化
                raw_cat = d.get("category", "")
                if raw_cat not in category_ids:
                    d["category"] = CATEGORY_MAP.get(raw_cat, _FALLBACK_CATEGORY)
                abilities.append(d)

        rarities = []
        if self._world:
            rars = self._world.ability_rarities or {}
            for r in rars.get("rarities", []):
                rarities.append(r)

        return {
            "type": "abilities_state",
            "abilities": abilities,
            "categories": categories,
            "rarities": rarities,
            "max_abilities": 20,
        }

    def _handle_ws_ability_action(self, message: dict, game_state) -> dict:
        """处理技能面板操作：forget。"""
        action = message.get("action", "")
        player = game_state.get_player()
        player_abilities = list(player.abilities)

        if action == "forget":
            ability_id = message.get("ability_id", "")

            # 装备技能不可遗忘（通过 EventBus 实时查询判定）
            is_equip = self._is_equipment_ability(ability_id, game_state)
            if is_equip:
                return {"type": "ability_action_result", "success": False, "message": "装备技能不可遗忘，请卸下对应装备"}

            if ability_id not in player_abilities:
                return {"type": "ability_action_result", "success": False, "message": "未学会该技能"}

            # 默认技能不可遗忘
            default_ability = self._world.get_default_ability_id() if self._world else "basic_attack"
            if ability_id == default_ability:
                return {"type": "ability_action_result", "success": False, "message": "基础攻击不可遗忘"}

            # 从已学技能中移除
            player_abilities.remove(ability_id)

        else:
            return {"type": "ability_action_result", "success": False, "message": f"未知操作: {action}"}

        player.abilities = player_abilities

        return {"type": "ability_action_result", "success": True}

    def _is_equipment_ability(self, ability_id: str, game_state) -> bool:
        """检查技能 ID 是否来自当前装备。"""
        if not self._bus:
            return False
        equip_data = self._bus.request(
            PluginEvent.EQUIPMENT_GET_BONUS, game_state.data,
        ) or {}
        return ability_id in equip_data.get("abilities", [])

    def handle_combat_action(self, action: dict) -> dict:
        """处理来自WebSocket的玩家战斗操作"""
        if self._active_session is None:
            return {"error": "没有进行中的战斗"}

        result = self._active_session.submit_player_action(action)

        phase = result["phase"]
        if phase in ("victory", "defeat", "flee"):
            rewards = {}
            if phase in ("victory", "flee"):
                # 逃跑时已击杀的敌人仍给予奖励
                rewards = self._active_session.calculate_rewards()
                result["rewards"] = rewards
            result["full_log"] = list(self._active_session.combat_log)
            result["group_name"] = self._active_session.group_name
            self._active_session = None

        return result

    def get_active_session(self) -> Optional[CombatSession]:
        return self._active_session

    def has_active_combat(self) -> bool:
        return self._active_session is not None

    def _apply_equipment_bonus(self, combatant: "Combatant") -> None:
        """注入装备效果到 combatant（stat_bonus + buffs + abilities）。"""
        if self._bus:
            equip_data = self._bus.request(
                PluginEvent.EQUIPMENT_GET_BONUS, self._game_state,
            ) or {}
        else:
            equip_data = {}
        self._equip_bonus = equip_data.get("stat_bonus", {})
        for stat, val in self._equip_bonus.items():
            if stat in combatant.attrs:
                combatant.attrs[stat] += val
        for b in equip_data.get("buffs", []):
            if hasattr(b, 'params'):
                b_stat = b.params.get("stat", "")
                b_mod = b.params.get("modifier", 0)
            else:
                b_stat = b.get("params", {}).get("stat", "")
                b_mod = b.get("params", {}).get("modifier", 0)
            combatant.buffs.append(ActiveBuff(
                id=b.id if hasattr(b, 'id') else b.get("id", ""),
                name=b.id if hasattr(b, 'id') else b.get("id", ""),
                remaining=999999,
                caster_name=combatant.name,
                effect={"type": "buff", "stat": b_stat, "modifier": b_mod},
            ))
        combatant.equipment_abilities = list(equip_data.get("abilities", []))
        combined = set(combatant.abilities) | set(combatant.equipment_abilities)
        combatant.abilities = list(combined)

    def _build_player(self) -> Combatant:
        """从 CharacterManager 构建玩家 Combatant。

        优先使用 live GameState（实时数据），回退到 _state 快照（测试/旧路径）。
        不再覆盖 self._game_state，避免将 GameState 对象替换为 dict 导致
        后续工具调用崩溃。
        """
        from lingmo_engine.plugins.combat.engine import combatant_from_character

        gs = self._game_state
        if gs is not None and not isinstance(gs, dict):
            # 真实 GameState 对象 — 有 character_manager 属性
            char_manager = getattr(gs, 'character_manager', None)
        else:
            # 快照 dict 或 None（测试/旧路径）
            state = self._state or {}
            char_manager = state.get("__character_manager")
        player_char = char_manager.player if char_manager else None

        if player_char:
            combatant = combatant_from_character(player_char, is_player=True,
                                                     attrs_schema=self._attrs_schema)
        else:
            # 回退：CharacterManager 不可用时构建最小 Combatant
            combatant = Combatant(
                name="冒险者", level=1, hp=100, max_hp=100,
                is_player=True, attrs={}, abilities=[],
            )

        self._apply_equipment_bonus(combatant)
        return combatant

    def _get_attr_labels(self) -> dict:
        """从完整角色 schema 构建属性名→标签映射"""
        if not self._world:
            return {}
        labels = {}
        for name, defn in self._world.attributes.items():
            labels[name] = defn.get("label", name)
        return labels

    @staticmethod
    def _normalize_abilities(abilities: list) -> list[str]:
        """将 abilities 列表规范化为纯字符串 ID 列表（模板中可能为 {id: xxx} 格式）。"""
        result = []
        for s in (abilities or []):
            sid = s["id"] if isinstance(s, dict) else s
            if sid not in result:
                result.append(sid)
        return result

    def spawn_combat_from_group(self, group_index: int, game_state_snapshot: dict) -> dict:
        """根据敌人组索引创建战斗会话并返回初始状态"""
        scene_enemies = game_state_snapshot.get("scene_enemies")
        if not scene_enemies:
            return {"error": "当前场景没有敌人"}

        groups = scene_enemies.get("groups", [])
        if group_index < 0 or group_index >= len(groups):
            return {"error": f"无效的敌人组索引: {group_index}"}

        group = groups[group_index]

        # 确保技能/物品系统已初始化
        if self._ability_system is None or self._item_system is None:
            return {"error": "技能/物品系统未初始化"}

        # 注入最新 custom_abilities，确保运行时创建的技能在战斗中可见
        # 优先从注册表读取（YAML 持久化），再合并快照中的运行时数据
        gs = self._game_state
        registry_abilities = gs.get_all_registry_abilities() if gs else {}
        runtime_abilities = game_state_snapshot.get("custom_abilities", {})
        merged = {**registry_abilities, **runtime_abilities}
        self._ability_system.set_custom_abilities(merged)

        # 获取世界自定义战斗公式（需在构建 Combatant 前获取，供增幅使用）
        combat_functions = None
        if self._world:
            combat_functions = self._world.get_combat_functions() or None

        # 构建玩家
        player = self._build_player()

        # 收集队友和宠物
        allies_combatants = []
        party = game_state_snapshot.get("party", [])
        for member in party:
            ally = combatant_from_character(
                member, is_player=False, attrs_schema=self._attrs_schema, side="ally"
            )
            allies_combatants.append(ally)

        # 从EncounterGroup构建敌人
        enemies, warnings = self._build_enemies_from_group(group)
        if not enemies:
            return {"error": "无法创建敌人"}

        # 处理战斗启动时的警告
        if warnings:
            group_name = group.get("name", "未知敌人")
            warning_msg = f"⚠ 战斗启动警告 ({group_name}):\n" + "\n".join(warnings)
            logger.warning(warning_msg)

        # 世界自定义：战斗前属性增幅（如修仙境界增幅）
        if combat_functions:
            amp = combat_functions.get("apply_pre_combat_amplification")
            if amp:
                amp(player)
                for ally in allies_combatants:
                    amp(ally)
                for enemy in enemies:
                    amp(enemy)

        # 创建战斗会话
        session = CombatSession(
            player=player,
            enemies=enemies,
            ability_system=self._ability_system,
            item_system=self._item_system,
            ai_registry=self._ai_registry,
            attrs_schema=self._attrs_schema,
            ai_strategy_name="default",
            plugin_registry=self._registry,
            combat_functions=combat_functions,
            ability_rarities=self._world.ability_rarities if self._world else {},
            ability_categories=self._world.ability_categories if self._world else {},
            statuses=set(self._world.get_statuses().keys()) if self._world else None,
            value_scale_table=self._world.get_effect_value_scale() if self._world else None,
            cost_scale_table=self._world.get_effect_cost_scale() if self._world else None,
            allies=allies_combatants,
            attr_labels=self._get_attr_labels(),
        )

        # 从 CharacterManager 获取玩家原生技能
        cm = game_state_snapshot.get("__character_manager")
        if cm:
            player_char = cm.player
            native_abilities = list(player_char.abilities)
        else:
            native_abilities = [self._world.get_default_ability_id() if self._world else "basic_attack"]
        default_ability = self._world.get_default_ability_id() if self._world else "basic_attack"
        if default_ability not in native_abilities:
            native_abilities = [default_ability] + native_abilities

        # 装备技能（来自 _apply_equipment_bonus 注入的 Combatant）
        eq_abilities = set(getattr(player, 'equipment_abilities', []))

        # 全部技能 = 原生 + 装备
        all_abilities = list(native_abilities)
        for ea in eq_abilities:
            if ea not in all_abilities:
                all_abilities.append(ea)
        session.player_ability_ids = all_abilities

        # 设置玩家背包
        inventory = game_state_snapshot.get("inventory", [])
        if inventory:
            session.set_inventory(inventory)

        self._active_session = session
        session.group_name = group.get("name", "未知敌人")
        initial_state = session.start()

        enemy_names = "、".join(e.name for e in enemies)
        logger.info("Combat started from group '%s': player vs %s", group.get("name"), enemy_names)

        return initial_state

    def _find_character_by_template(self, char_manager, template_id: str):
        """按模板 ID 查找角色。先 O(1) 按整数 ID 查，再 O(n) 按名称/字符串 ID 扫描。"""
        if not char_manager or not template_id:
            return None
        # 阶段1: 整数 ID 直接查找
        try:
            char = char_manager.get(int(template_id))
            if char:
                return char
        except (ValueError, TypeError):
            pass
        # 阶段2: 遍历匹配名称或字符串 ID
        for c in char_manager.all():
            if c.name == template_id or str(c.id) == str(template_id):
                return c
        return None

    # 灵力门槛表 — 来自 cultivation.yaml sp_range，index = level(order)
    _SP_RANGES = [
        (0, 75),            # 0: 凡人
        (75, 200),          # 1: 练气期
        (200, 600),         # 2: 筑基期
        (600, 2000),        # 3: 金丹期
        (2000, 7500),       # 4: 元婴期
        (7500, 30000),      # 5: 化神期
        (30000, 125000),    # 6: 炼虚期
        (125000, 500000),   # 7: 合体期
        (500000, 1500000),  # 8: 大乘期
        (1500000, 3000000), # 9: 渡劫期
        (3000000, 5000000), # 10: 真仙
        (5000000, 7500000), # 11: 金仙
        (7500000, 10000000),# 12: 太乙金仙
        (10000000, 15000000),# 13: 大罗金仙
    ]

    def _rand_spiritual_power(self, level: int) -> int:
        """根据等级在对应境界灵力门槛范围内随机。"""
        import random
        idx = max(0, min(level, len(self._SP_RANGES) - 1))
        lo, hi = self._SP_RANGES[idx]
        return random.randint(lo, max(lo, hi))

    def _humanize_template_name(template_id: str) -> str:
        """将模板 ID 转为可读名称。"""
        return template_id.replace("_", " ").title()

    def _get_preset_aptitude_bias(self, template_id: str) -> dict[str, float]:
        """通过 EventBus 从 CharacterPlugin 获取预设模板的 aptitude_bias。

        依赖 CharacterPlugin 在 on_load() 中注册 handler。
        无 handler 时（CharacterPlugin 未加载）返回空 dict。
        """
        if self._bus:
            result = self._bus.request(PluginEvent.CHARACTER_GET_PRESET_BIAS, template_id)
            if result is not None:
                return result
        return {}

    def _resolve_ability_id(self, raw: str) -> str | None:
        """解析技能输入：ID → 名称精确 → 模糊匹配，返回合法 ID 或 None。

        查找链路：AbilitySystem 精确 ID → world.abilities 精确 ID
        → name 索引精确匹配 → 归一化模糊匹配(≥0.7)。
        模糊匹配使用共享工具 core.types.fuzzy_match_by_name。
        """
        if not self._world:
            # 无世界配置时直接返回原始值（无法校验）
            return raw

        # 惰性构建 name→id 索引和归一化索引
        if not hasattr(self, "_ability_name_idx"):
            from lingmo_engine.core.types import normalize_name
            self._ability_name_idx: dict[str, str] = {}
            self._ability_norm_idx: list[tuple[str, str, str]] = []
            for aid, adef in (self._world.abilities or {}).items():
                name = adef.get("name", "")
                if name:
                    self._ability_name_idx[name] = aid
                    norm = normalize_name(name)
                    if norm:
                        self._ability_norm_idx.append((aid, name, norm))

        # 1. 精确 ID 匹配
        if raw in (self._world.abilities or {}):
            return raw

        # 2. AbilitySystem 精确匹配（含自定义技能）
        if (hasattr(self, "_ability_system")
                and self._ability_system is not None
                and self._ability_system.get_ability(raw)):
            return raw

        # 3. 精确名称匹配
        if raw in self._ability_name_idx:
            aid = self._ability_name_idx[raw]
            logger.info("abilities: 名称 '%s' → ID '%s'", raw, aid)
            return aid

        # 4. 归一化模糊匹配（共享工具）
        from lingmo_engine.core.types import fuzzy_match_by_name
        matched = fuzzy_match_by_name(raw, self._ability_norm_idx)
        if matched:
            logger.info("abilities: 模糊匹配 '%s' → ID '%s'", raw, matched)
            return matched

        return None

    def _build_enemies_from_group(self, group: dict) -> tuple[list, list[str]]:
        """从遭遇组构建 Combatant 列表。根据 source 字段分发构建策略。"""
        state = self._state or {}
        char_manager = state.get("__character_manager")
        enemies: list[Combatant] = []
        warnings: list[str] = []

        for e in group.get("enemies", []):
            source = e.get("source", "hostile")  # 旧存档兼容

            if source == "npc":
                combatant = self._build_npc_combatant(
                    e, char_manager, warnings)
            else:
                combatant = self._build_hostile_combatant(
                    e, char_manager, warnings)

            if combatant is None:
                continue

            # 通用后处理: aptitude → 属性生成 / abilities
            self._apply_enemy_overrides(combatant, e, warnings)

            # count 展开（NPC 强制 count=1）
            count = e.get("count", 1)
            for idx in range(count):
                if count > 1:
                    suffix = f" {chr(65+idx)}" if count <= 26 else f" #{idx+1}"
                    enemies.append(Combatant(
                        name=combatant.name + suffix,
                        level=combatant.level,
                        hp=combatant.hp,
                        max_hp=combatant.max_hp,
                        is_player=False,
                        attrs=dict(combatant.attrs),
                        abilities=list(combatant.abilities),
                        loot_table=list(combatant.loot_table),
                        extra=dict(combatant.extra),
                    ))
                else:
                    enemies.append(combatant)

        return enemies, warnings

    def _build_npc_combatant(self, e: dict, char_manager,
                             warnings: list[str]) -> Combatant | None:
        """从 CharacterManager 加载 NPC 构建 Combatant。"""
        from lingmo_engine.plugins.combat.engine import combatant_from_character

        character_id = e.get("character_id", "")
        char = self._find_character_by_template(char_manager, character_id)

        if char:
            combatant = combatant_from_character(
                char, is_player=False,
                attrs_schema=self._attrs_schema, side="enemy")
            name_override = e.get("name")
            if name_override:
                combatant.name = name_override
            return combatant

        # 战斗启动阶段找不到 NPC → 空壳回退（不能卡住玩家）
        name = e.get("name") or self._humanize_template_name(character_id)
        msg = (f"WARNING: NPC '{character_id}' 在战斗启动时未找到，"
               f"已使用空壳回退 '{name}'")
        logger.warning("NPC '%s' 战斗启动时未找到，使用空壳回退", character_id)
        warnings.append(msg)
        return Combatant(
            name=name, level=1, hp=30, max_hp=30,
            is_player=False, attrs={}, abilities=[], loot_table=[],
        )

    def _build_hostile_combatant(self, e: dict, char_manager,
                                 warnings: list[str]) -> Combatant:
        """从模板构建临时敌人 Combatant。

        优先从 CharacterManager 查找真实角色（走 combatant_from_character
        获取完整属性）；找不到时构建空壳 Combatant，属性由后续
        _apply_enemy_overrides 根据 aptitude 自动生成。
        """
        from lingmo_engine.plugins.combat.engine import combatant_from_character

        template_id = e.get("template", "")
        name_override = e.get("name")
        level = e.get("level", 1)

        char = self._find_character_by_template(char_manager, template_id)
        if char:
            # 找到真实角色 → 使用完整属性构建
            combatant = combatant_from_character(
                char, is_player=False,
                attrs_schema=self._attrs_schema, side="enemy")
            if name_override:
                combatant.name = name_override
            return combatant

        # 未找到角色 → 空壳回退
        name = name_override or self._humanize_template_name(template_id)
        msg = (f"WARNING: 模板 '{template_id}' 未找到，"
               f"已使用回退名称 '{name}'。建议：使用已有的模板 ID")
        logger.warning("模板 '%s' 未找到，使用回退名称 '%s'",
                       template_id, name)
        warnings.append(msg)

        return Combatant(
            name=name, level=level, hp=30, max_hp=30,
            is_player=False, attrs={}, abilities=[], loot_table=[],
        )

    def _apply_enemy_overrides(self, combatant: Combatant, e: dict,
                               warnings: list[str] | None = None) -> None:
        """应用资质→属性生成、技能追加（含校验与模糊匹配）。"""
        import random

        # aptitude → 属性生成（纯函数，无实例依赖）
        apt = e.get("aptitude")
        if apt is not None:
            from lingmo_engine.plugins.character.character_generator import CharacterGenerator
            bias = e.get("aptitude_bias", {})
            attrs = CharacterGenerator.calc_attrs_from_aptitude(apt, bias)
            combatant.attrs.update(attrs)
            # vitality 作为 HP 池
            vitality = attrs.get("vitality", attrs.get("max_vitality", 0))
            if vitality > 0:
                combatant.hp = vitality
                combatant.max_hp = vitality

        # 灵力：根据等级对应的境界灵力门槛随机
        if "spiritual_power" not in combatant.attrs:
            combatant.attrs["spiritual_power"] = self._rand_spiritual_power(
                combatant.level)

        # 技能追加（校验 + 模糊匹配）

        # 技能追加（校验 + 模糊匹配）
        raw_abilities = e.get("abilities", []) or []
        for sk in raw_abilities:
            # 类型拦截：非字符串跳过
            if not isinstance(sk, str):
                msg = (f"WARNING: abilities 条目类型不支持({type(sk).__name__}: {sk!r})，"
                       "已跳过。请使用技能名称或ID字符串。")
                logger.warning("abilities: 不支持的条目类型 %s", type(sk).__name__)
                if warnings is not None:
                    warnings.append(msg)
                continue

            # 空值跳过
            if not sk.strip():
                continue

            # 解析技能 ID（精确 ID → 名称 → 模糊匹配）
            resolved = self._resolve_ability_id(sk)
            if resolved:
                # 重复检查基于解析后的 ID，避免名称变体绕过
                if resolved not in combatant.abilities:
                    combatant.abilities.append(resolved)
            else:
                msg = (f"WARNING: 技能 '{sk}' 未找到，已跳过。"
                       "请检查技能名是否拼写正确。")
                logger.warning("abilities: 技能 '%s' 未找到，已跳过", sk)
                if warnings is not None:
                    warnings.append(msg)

