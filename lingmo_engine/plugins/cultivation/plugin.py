"""修仙 Plugin — 境界突破、修炼、灵根感知、夺舍"""
import logging
from lingmo_engine.core.encounter_plugin import EncounterPlugin
from lingmo_engine.core.events import PluginEvent
from lingmo_engine.core.types import DisplayType, ToolDefinition, ToolParameter, ModuleResult
from lingmo_engine.plugins.cultivation.schema_loader import CultivationSchema
from lingmo_engine.plugins.cultivation.breakthrough import execute_breakthrough
from lingmo_engine.plugins.cultivation.field_normalizer import (
    CultivationFieldNormalizer,
)

_log = logging.getLogger(__name__)
from lingmo_engine.plugins.cultivation.dao_rhyme import grant_dao_rhyme as _grant_rhyme


def _player_get(player, key, default=""):
    """从 player（dict 或 Character）读取字段，优先 extra 子字段。"""
    if isinstance(player, dict):
        extra = player.get("extra") or {}
        if isinstance(extra, dict) and key in extra:
            return extra[key]
        return player.get(key, default)
    extra = getattr(player, 'extra', None) or {}
    if isinstance(extra, dict) and key in extra:
        return extra[key]
    return getattr(player, key, default)


class CultivationPlugin(EncounterPlugin):
    name = "cultivation"
    version = "0.1.0"
    depends_on = ["character"]
    ws_prefix = "cultivation"

    def __init__(self):
        super().__init__()

    def on_load(self) -> None:
        world_dir = getattr(self.world, "_world_dir", None)
        self._schema = CultivationSchema(world_dir or "")

        # 将修炼字段规范化器注入到 character 插件（依赖方向：cultivation → character）
        self._inject_field_normalizer()

    def _inject_field_normalizer(self) -> None:
        """创建 CultivationFieldNormalizer 并注入到 CharacterGenerator。

        修炼字段的规范化逻辑（灵根、种族、修炼方向、境界联动等）
        属于 cultivation 插件的职责范围，由 cultivation 主动注入到 character，
        保持依赖方向：业务插件 → 基础设施插件。
        """
        if not self._schema.raw:
            _log.debug("cultivation: 无修炼配置，跳过 normalizer 注入")
            return
        registry = getattr(self, "_registry", None)
        if not registry:
            _log.warning("cultivation: 无 registry，无法注入 normalizer")
            return
        char_plugin = registry.get_plugin("character")
        if not char_plugin:
            _log.warning("cultivation: character 插件未加载，无法注入 normalizer")
            return
        generator = getattr(char_plugin, "_generator", None)
        if not generator:
            _log.warning("cultivation: character 插件缺少 _generator，无法注入 normalizer")
            return
        char_schema = getattr(generator, "_character_schema", None)
        normalizer = CultivationFieldNormalizer(self._schema.raw, char_schema)
        generator._normalizer = normalizer

        # 同步 visibility_resolver（schema 变更时由 set_schema_template 追加同步）
        vis = getattr(generator, "_visibility_resolver", None)
        if vis:
            normalizer.set_visibility_resolver(vis)

        _log.info("cultivation: 已注入字段规范化器到 character 插件")

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="offer_cultivation",
                description="当角色处于适合修炼的场景（洞府、福地、灵脉、秘境、名山等）时，"
                            "向玩家展示修炼机缘卡片。由你根据叙事场景判断是否适合修炼。"
                            "不要在不适合修炼的地方（城镇街道、战场、荒野赶路中）调用此工具。",
                parameters=[
                    ToolParameter(name="player_id", type="string", required=True,
                        description="角色ID"),
                    ToolParameter(name="narrative_hint", type="string", required=True,
                        description="修炼机缘的描述，如'你发现一处隐蔽洞府，灵气充沛'"),
                    ToolParameter(name="qi_bonus", type="number", required=False,
                        description="此地额外灵气加成倍率，如1.5表示灵气浓度×1.5"),
                ],
            ),
            ToolDefinition(
                name="convert_spirit_stones",
                description="将灵石转化为灵力。100下品灵石=1灵力。",
                parameters=[
                    ToolParameter(name="player_id", type="string", required=True),
                    ToolParameter(name="amount", type="integer", required=True,
                        description="消耗的下品灵石数量"),
                ],
            ),
            ToolDefinition(
                name="grant_dao_rhyme",
                description="授予角色道韵（对天地大道的感悟）。适用于：战斗胜利后的领悟、探索秘境的感悟、际遇中的启迪、参悟功法的顿悟。不可通过灵石购买。",
                parameters=[
                    ToolParameter(name="player_id", type="string", required=True,
                        description="角色ID"),
                    ToolParameter(name="amount", type="integer", required=True,
                        description="道韵增加量"),
                    ToolParameter(name="reason", type="string", required=True,
                        description="获得道韵的原因"),
                ],
            ),
            ToolDefinition(
                name="sync_npc_state",
                description=(
                    "同步 NPC 的离场状态（计算基准值）。当已有 NPC 再次登场时调用此工具，"
                    "系统自动根据离场天数计算灵力增长、体力恢复、突破冷却衰减等基准变化。"
                    "调用后请根据剧情需要，使用 update_character_field 对同步结果进行叙事调整。"
                ),
                parameters=[
                    ToolParameter(
                        name="character_id", type="integer", required=True,
                        description="要同步状态的 NPC 角色 ID",
                    ),
                ],
            ),
        ]

    def execute_tool(self, tool_name: str, params: dict) -> ModuleResult:
        if tool_name == "offer_cultivation":
            return self._do_offer_cultivation(params)
        elif tool_name == "convert_spirit_stones":
            return self._do_convert_stones(params)
        elif tool_name == "possess_target":
            return ModuleResult(success=False, log="夺舍需通过 DM 触发，请描述夺舍意图")
        elif tool_name == "grant_dao_rhyme":
            return self._do_grant_rhyme(params)
        elif tool_name == "sync_npc_state":
            return self._do_sync_npc_state(params)
        return ModuleResult(success=False, log=f"未知工具: {tool_name}")

    def _do_offer_cultivation(self, params: dict) -> ModuleResult:
        """LLM 调用：返回修炼机缘卡片数据，不实际执行修炼。"""
        char = self._get_char(params.get("player_id", ""))
        if not char:
            return ModuleResult(success=False, log="角色未找到")

        narrative_hint = params.get("narrative_hint", "你发现了一处适合修炼的场所。")
        qi_bonus = params.get("qi_bonus", 1.0)

        stage_id = _player_get(char, "cultivation_stage", "mortal")
        stage = self._schema.get_stage(stage_id)
        next_stage = self._schema.get_next_stage(stage_id)
        current_sp = _player_get(char, "spiritual_power", 0)
        current_rhyme = _player_get(char, "dao_rhyme", 0)

        next_threshold = 0
        if next_stage:
            rule = self._schema.get_breakthrough_rule(stage_id, next_stage.get("id", ""))
            if isinstance(rule, dict):
                _raw = rule.get("requirements", {}).get("spiritual_power_min", 0)
                next_threshold = int(_raw) if isinstance(_raw, (int, float)) else 0

        return ModuleResult(
            success=True,
            log="修炼机缘已展示给玩家",
            display_type=DisplayType.ENCOUNTER,
            data={
                "cultivation_opportunity": True,
                "narrative_hint": narrative_hint,
                "qi_bonus": qi_bonus,
                "stage_name": stage["name"] if stage else "未知",
                "spiritual_power": current_sp,
                "next_threshold": next_threshold,
                "dao_rhyme": current_rhyme,
            },
        )

    def _do_breakthrough(self, params: dict) -> ModuleResult:
        char = self._get_char(params["player_id"])
        if not char:
            return ModuleResult(success=False, log="角色未找到")
        result = execute_breakthrough(char, self._schema, qi_density=self._get_qi_density())
        if result.success:
            self._mark_dirty(char.id)
        return result

    def _do_meditate(self, params: dict) -> ModuleResult:
        hours = params.get("hours", 2)
        char = self._get_char(params["player_id"])
        if not char:
            return ModuleResult(success=False, log="角色未找到")

        stage_id = getattr(char, "cultivation_stage", "mortal")
        roots = list(getattr(char, "spiritual_roots", []))
        qi_density = self._get_qi_density()

        daily_sp = self._schema.calculate_daily_sp(stage_id, roots, qi_density, "meditation")
        hours_sp = daily_sp * (hours / 24.0)

        char.enlightenment = getattr(char, "enlightenment", 0) + hours * 2
        char.spiritual_power = getattr(char, "spiritual_power", 0) + int(hours_sp)
        char.cultivation_substage = self._schema.compute_substage(
            stage_id, char.spiritual_power)
        self._mark_dirty(char.id)

        return ModuleResult(success=True,
            log=f"修炼{hours}小时，获得{int(hours_sp)}灵力",
            data={"sp_gain": int(hours_sp),
                  "daily_rate": round(daily_sp, 4)})

    def _do_start_cultivation(self, params: dict) -> ModuleResult:
        """持续打坐指定天数。"""
        char = self._get_char(params["player_id"])
        if not char:
            return ModuleResult(success=False, log="角色未找到")

        days = params.get("days", 1)

        stage_id = getattr(char, "cultivation_stage", "mortal")
        roots = list(getattr(char, "spiritual_roots", []))
        qi_density = self._get_qi_density()

        daily_sp = self._schema.calculate_daily_sp(stage_id, roots, qi_density, "meditation")
        total_sp = round(daily_sp * days, 4)

        char.spiritual_power = round(getattr(char, "spiritual_power", 0) + total_sp, 4)
        char.cultivation_substage = self._schema.compute_substage(
            stage_id, char.spiritual_power)
        self._mark_dirty(char.id)

        return ModuleResult(success=True,
            log=f"打坐冥想{days}天，获得{total_sp}灵力（日均{round(daily_sp, 4)}）",
            data={"sp_gain": total_sp, "days": days, "daily_rate": round(daily_sp, 4),
                  "method": "meditation", "new_spiritual_power": char.spiritual_power})

    def _do_convert_stones(self, params: dict) -> ModuleResult:
        """灵石转化灵力。"""
        char = self._get_char(params["player_id"])
        if not char:
            return ModuleResult(success=False, log="角色未找到")

        amount = params.get("amount", 0)
        if amount <= 0:
            return ModuleResult(success=False, log="转化数量必须大于0")

        rate = self._schema.get_spirit_stone_rate()
        sp_gain = amount // rate

        if sp_gain <= 0:
            return ModuleResult(success=False, log=f"灵石不足，至少需要{rate}下品灵石")

        char.spiritual_power = getattr(char, "spiritual_power", 0) + sp_gain
        stage_id = getattr(char, "cultivation_stage", "mortal")
        char.cultivation_substage = self._schema.compute_substage(
            stage_id, char.spiritual_power)
        self._mark_dirty(char.id)

        return ModuleResult(success=True,
            log=f"转化{amount}下品灵石为{sp_gain}灵力",
            data={"stones_consumed": amount, "sp_gain": sp_gain, "rate": rate})

    def _do_grant_rhyme(self, params: dict) -> ModuleResult:
        """授予道韵。"""
        char = self._get_char(params["player_id"])
        if not char:
            return ModuleResult(success=False, log="角色未找到")

        amount = params.get("amount", 0)
        reason = params.get("reason", "")
        if amount <= 0:
            return ModuleResult(success=False, log="道韵增加量必须大于0")

        stage_id = getattr(char, "cultivation_stage", "mortal")
        stage = self._schema.get_stage(stage_id)
        stage_order = stage.get("order", 0) if stage else 0

        current_rhyme = getattr(char, "dao_rhyme", 0)
        result = _grant_rhyme(current_rhyme, amount, stage_order, self._schema)

        char.dao_rhyme = result["new_rhyme"]
        self._mark_dirty(char.id)

        threshold = result["threshold"]
        rhyme_status = ""
        if threshold > 0:
            _ratio = self._schema.get_dao_rhyme_config().get("enlightenment_ratio", 1.5)
            rhyme_status = f"（{result['new_rhyme']}/{threshold}）"
            if result["new_rhyme"] >= threshold * _ratio:
                rhyme_status += " ★顿悟"
            elif result["new_rhyme"] >= threshold:
                rhyme_status += " ★可突破"

        return ModuleResult(success=True,
            log=f"因「{reason}」获得{result['granted']}道韵{rhyme_status}",
            data={"granted": result["granted"], "new_rhyme": result["new_rhyme"],
                  "threshold": threshold})

    def get_context_hint(self, state: dict) -> str:
        player = state.get("player")
        if not player:
            return ""

        stage_id = _player_get(player, "cultivation_stage", "mortal")
        stage = self._schema.get_stage(stage_id)
        stage_name = stage["name"] if stage else "未知"
        next_stage = self._schema.get_next_stage(stage_id)
        next_name = next_stage["name"] if next_stage else "无"

        roots = list(_player_get(player, "spiritual_roots", []))
        quality_key = self._schema.get_root_quality_key(roots)
        qi_density = self._get_qi_density()

        next_threshold = 0
        current_rhyme = _player_get(player, "dao_rhyme", 0)
        rhyme_threshold = 0
        breakthrough_ready = False
        enlightenment_ready = False

        if next_stage:
            rule = self._schema.get_breakthrough_rule(stage_id, next_stage.get("id", ""))
            if isinstance(rule, dict):
                _raw_sp = rule.get("requirements", {}).get("spiritual_power_min", 0)
                next_threshold = int(_raw_sp) if isinstance(_raw_sp, (int, float)) else 0
            else:
                next_threshold = 0
            next_order = next_stage.get("order", 0) if isinstance(next_stage, dict) else 0
            rhyme_threshold = 0
            if isinstance(next_order, (int, float)) and next_order > 0:
                try:
                    rhyme_threshold = self._schema.get_dao_rhyme_threshold(int(next_order) - 1)
                except Exception:
                    rhyme_threshold = 0
            breakthrough_ready = _player_get(player, "spiritual_power", 0) >= next_threshold and current_rhyme >= rhyme_threshold
            _ratio = self._schema.get_dao_rhyme_config().get("enlightenment_ratio", 1.5)
            enlightenment_ready = current_rhyme >= rhyme_threshold * _ratio if rhyme_threshold > 0 else False

        daily_sp = self._schema.calculate_daily_sp(stage_id, roots, qi_density, "meditation")

        # 道韵信息
        rhyme_line = ""
        if rhyme_threshold > 0:
            _sp_ready = _player_get(player, "spiritual_power", 0) >= next_threshold
            if breakthrough_ready:
                rhyme_line = (
                    f"\n道韵：{current_rhyme} / {rhyme_threshold}"
                    f"{' ★顿悟可突破' if enlightenment_ready else ' ★可突破'}"
                )
            elif _sp_ready:
                rhyme_line = f"\n道韵：{current_rhyme} / {rhyme_threshold} （道韵不足）"

        return (
            f"## 修炼状态\n"
            f"境界：{stage_name}（{_player_get(player, 'cultivation_substage', '?')}）\n"
            f"主修：{_player_get(player, 'cultivation_path', '无')}\n"
            f"灵力：{_player_get(player, 'spiritual_power', 0)}"
            f"{f' / {next_threshold}' if next_threshold else ''}"
            f"{' ★可突破' if breakthrough_ready and rhyme_threshold == 0 else ''}"
            f"{rhyme_line}\n"
            f"寿元：{_player_get(player, 'lifespan_remaining', 100)}年\n"
            f"灵根：{quality_key} ×{self._schema.get_root_power(quality_key)}\n"
            f"修炼速度：{round(daily_sp, 4)} 灵力/天（打坐）\n"
            f"下一境界：{next_name}"
        )

    def get_static_dir(self) -> str | None:
        import os
        d = os.path.join(os.path.dirname(__file__), "static")
        return d if os.path.isdir(d) else None

    def handle_websocket(self, message: dict, game_state) -> dict | None:
        msg_type = message.get("type", "")

        if msg_type == "cultivation_action":
            try:
                return self._ws_handle_action(message, game_state)
            except Exception as e:
                _log.error("cultivation _ws_handle_action error: %s", e, exc_info=True)
                return {"type": "cultivation_state", "data": {},
                        "action_result": {"success": False, "log": f"内部错误: {e}"}}

        result = super().handle_websocket(message, game_state)
        if result is not None:
            return result

        if msg_type in ("cultivation_open", "get_cultivation_state"):
            try:
                return self._ws_get_state(game_state)
            except Exception as e:
                _log.error("cultivation _ws_get_state error: %s", e, exc_info=True)
                return {"type": "cultivation_state", "data": {},
                        "action_result": {"success": False, "log": f"内部错误: {e}"}}

        return None

    def _create_session(self, params, game_state) -> "CultivationSession":
        from lingmo_engine.plugins.cultivation.session import CultivationSession
        player = getattr(game_state, 'get_player', lambda: None)()
        if not player:
            raise ValueError("角色未找到")
        qi_bonus = params.get("qi_bonus", 1.0)
        narrative_hint = params.get("narrative_hint", "")
        return CultivationSession(player, self._schema, qi_bonus=qi_bonus,
                                  narrative_hint=narrative_hint)

    def _ws_start_session(self, message: dict, game_state) -> dict:
        """覆盖基类：返回完整面板状态（前端需要 cultivation_state 类型）。"""
        from lingmo_engine.plugins.cultivation.session import CultivationSession

        player = getattr(game_state, 'get_player', lambda: None)()
        if not player:
            return {"type": "cultivation_state", "data": {},
                    "action_result": {"success": False, "log": "角色未找到"}}

        qi_bonus = message.get("qi_bonus", 1.0)
        narrative_hint = message.get("narrative_hint", "")

        session = CultivationSession(
            player, self._schema, qi_bonus=qi_bonus,
            narrative_hint=narrative_hint,
        )
        self._active_session = session

        state = self._ws_get_state(game_state)
        state["data"]["session_active"] = True
        state["data"]["cultivation_log"] = []
        return state

    def _on_session_end(self, session, game_state) -> list:
        summary = session.get_summary()
        total_days = summary.get("total_days", 0)
        self._last_time_display = ""
        if total_days > 0:
            self._last_time_display = self._advance_game_time(total_days, game_state) or ""
        player = getattr(game_state, 'get_player', lambda: None)()
        if player:
            player_id = getattr(player, "id", None)
            if player_id is not None:
                self._mark_dirty(str(player_id))
        return []

    def _get_narrative_extra(self, session, game_state) -> dict:
        summary = session.get_summary()
        sp_gained = summary.get("total_sp_gained", 0)
        total_days = summary.get("total_days", 0)
        bt = summary.get("breakthrough")
        time_display = getattr(self, "_last_time_display", "")
        return {
            "fallback_text": f"修炼结束。{total_days}天内获得{sp_gained}灵力。",
            "cultivation_summary": {
                "total_days": total_days,
                "sp_gained": sp_gained,
                "breakthrough_success": bt.get("success") if bt else None,
                "time_advanced_display": time_display,
            },
        }

    def _build_narrative_prompt(self, session) -> str:
        summary = session.get_summary()
        log_entries = summary.get("log", [])
        if not log_entries:
            return ""
        log_text = "\n".join(
            f"第{e.get('day', '?')}天：{e.get('text', '')}" for e in log_entries
        )
        hint = summary.get("narrative_hint", "在一处灵气充沛之地修炼")
        total_days = summary.get("total_days", 0)
        sp_gained = summary.get("total_sp_gained", 0)
        bt = summary.get("breakthrough")
        bt_text = (f"突破成功 — {bt.get('data', {}).get('new_stage_name', '下一境界')}"
                   if bt and bt.get("success") else
                   (f"突破失败 — {bt.get('log', '未知原因')}" if bt else "无突破尝试"))
        time_note = ""
        time_display = getattr(self, "_last_time_display", "")
        if time_display:
            time_note = f"\n## 时间\n系统已自动推进时间{time_display}，请不要再次调用advance_time工具。\n"
        return (
            f"请将以下修炼记录改写为生动的文学化叙述。\n\n"
            f"## 修炼背景\n{hint}\n"
            f"{time_note}\n"
            f"## 修炼过程\n{log_text}\n\n"
            f"## 修炼结果\n"
            f"- 时长：{total_days}天\n- 灵力增长：+{sp_gained}\n- 突破：{bt_text}\n\n"
            "要求：\n"
            "1. 200字以内\n2. 关键节点详细描写\n3. 突破场景体现天地异象\n"
            "4. 结尾提及修炼成果\n5. 直接输出叙述文本\n"
            "6. 不要在叙述中提及任何具体数值或属性变化（灵力、境界等数值已由系统计算，"
            "无需在文本中重复），仅做文学化描写"
        )

    def _ws_get_state(self, game_state) -> dict:
        """返回修炼面板完整状态。"""
        player = getattr(game_state, 'get_player', lambda: None)()
        if not player:
            return {"type": "cultivation_state", "data": {}}

        stage_id = _player_get(player, "cultivation_stage", "mortal")
        stage = self._schema.get_stage(stage_id)
        next_stage = self._schema.get_next_stage(stage_id)
        roots = list(getattr(player, 'spiritual_roots', []))
        qi_density = self._get_qi_density()
        current_sp = _player_get(player, "spiritual_power", 0)

        next_threshold = 0
        breakthrough_ready = False
        current_rhyme = _player_get(player, "dao_rhyme", 0)
        rhyme_threshold = 0
        rule = None
        if next_stage:
            rule = self._schema.get_breakthrough_rule(stage_id, next_stage.get("id", ""))
            if isinstance(rule, dict):
                _raw_sp = rule.get("requirements", {}).get("spiritual_power_min", 0)
                next_threshold = int(_raw_sp) if isinstance(_raw_sp, (int, float)) else 0
            next_order = next_stage.get("order", 0) if isinstance(next_stage, dict) else 0
            rhyme_threshold = self._schema.get_dao_rhyme_threshold(next_order - 1) if next_order > 0 else 0
            breakthrough_ready = current_sp >= next_threshold and current_rhyme >= rhyme_threshold

        # 有活跃会话时使用会话的 qi_bonus，确保前端预览与实际修炼速率一致
        effective_qi = qi_density
        if self._active_session and hasattr(self._active_session, "qi_bonus"):
            effective_qi = qi_density * self._active_session.qi_bonus
        daily_meditation = self._schema.calculate_daily_sp(stage_id, roots, effective_qi, "meditation")

        quality_key = self._schema.get_root_quality_key(roots)
        qi_level = self._schema.get_qi_level(qi_density)
        # 会话中灵气等级基于 effective_qi，仅用于修炼速率显示
        effective_qi_level = self._schema.get_qi_level(effective_qi)

        # 顿悟判定
        _ratio = self._schema.get_dao_rhyme_config().get("enlightenment_ratio", 1.5)
        enlightenment_ready = current_rhyme >= rhyme_threshold * _ratio if rhyme_threshold > 0 else False

        # 预计算突破成功率
        bt_rates = {}
        if breakthrough_ready and rule:
            bt_params = self._schema.get_breakthrough_params()
            base_rate = bt_params.get("base_rate", 0.60)
            root_bonus = bt_params.get("root_quality_bonus", {}).get(quality_key, 0.0)
            qi_bonus = bt_params.get("qi_density_bonus", {}).get(qi_level.get("id", "thin"), 0.0)
            secondary_bonus = 0.05 if _player_get(player, "secondary_path", None) else 0.0
            min_rate = bt_params.get("min_rate", 0.10)
            max_rate = bt_params.get("max_rate", 0.95)
            m = self._schema.get_breakthrough_method("natural")
            if m:
                rate = (base_rate + root_bonus + qi_bonus + secondary_bonus) * m.get("rate_mult", 1.0)
                bt_rates["natural"] = round(max(min_rate, min(max_rate, rate)), 4)

        return {
            "type": "cultivation_state",
            "data": {
                "stage_id": stage_id,
                "stage_name": stage["name"] if stage else "未知",
                "substage": _player_get(player, "cultivation_substage", "1"),
                "substage_name": self._resolve_substage_name(stage, _player_get(player, "cultivation_substage", "1")) if stage else "",
                "path": _player_get(player, "cultivation_path", ""),
                "path_name": self._schema.get_path(_player_get(player, "cultivation_path", "")).get("name", "") if _player_get(player, "cultivation_path", "") else "",
                "spiritual_power": current_sp,
                "next_threshold": next_threshold,
                "dao_rhyme": current_rhyme,
                "dao_rhyme_threshold": rhyme_threshold,
                "breakthrough_ready": breakthrough_ready,
                "enlightenment_ready": enlightenment_ready,
                "lifespan_remaining": _player_get(player, "lifespan_remaining", 100),
                "lifespan_total": stage.get("lifespan", 100) if stage else 100,
                "roots": roots,
                "root_quality": quality_key,
                "root_quality_name": self._ROOT_QUALITY_NAMES.get(quality_key, quality_key),
                "root_modifier": self._schema.get_root_power(quality_key),
                "qi_density": qi_density,
                "qi_level_id": effective_qi_level.get("id", "thin"),
                "qi_level_name": effective_qi_level.get("name", "正常"),
                "qi_modifier": effective_qi_level.get("cultivation_speed_mult", 1.0),
                "daily_meditation": round(daily_meditation, 4),
                "stone_rate": self._schema.get_spirit_stone_rate(),
                "breakthrough_cooldown": _player_get(player, "breakthrough_cooldown", 0),
                "breakthrough_rates": bt_rates,
                "next_stage_name": next_stage["name"] if next_stage else "",
            },
        }

    def _ws_handle_action(self, message: dict, game_state) -> dict:
        """处理修炼面板操作。直接操作 game_state 中的 player 对象。"""
        action = message.get("action", "")
        player = getattr(game_state, 'get_player', lambda: None)()
        if not player:
            return {"type": "cultivation_state", "data": {},
                    "action_result": {"success": False, "log": "角色未找到"}}

        if action == "start_meditation":
            days = message.get("days", 1)

            if self._active_session:
                # 有活跃会话时走 session 路径（记录日志）
                result = self._active_session.cultivate(days, qi_density=self._get_qi_density())
                state = self._ws_get_state(game_state)
                state["action_result"] = {
                    "success": True,
                    "log": result.get("method_name", "打坐冥想") + f"{days}天，获得{result['sp_gain']}灵力",
                    "data": result,
                }
                state["data"]["cultivation_log"] = self._active_session.log
                state["data"]["session_active"] = True
                return state

            # 无会话时走原有路径
            stage_id = _player_get(player, "cultivation_stage", "mortal")
            roots = list(_player_get(player, "spiritual_roots", []))
            qi_density = self._get_qi_density()
            daily_sp = self._schema.calculate_daily_sp(stage_id, roots, qi_density, "meditation")
            total_sp = round(daily_sp * days, 4)
            cur_sp = _player_get(player, "spiritual_power", 0)
            new_sp = int(cur_sp + total_sp)
            self._set_player_attr(player, "spiritual_power", new_sp)
            self._set_player_attr(player, "cultivation_substage",
                                  self._schema.compute_substage(stage_id, new_sp))
            state = self._ws_get_state(game_state)
            state["action_result"] = {
                "success": True,
                "log": f"打坐冥想{days}天，获得{total_sp}灵力（日均{round(daily_sp, 4)}）",
            }
            return state

        if action == "convert_stones":
            amount = message.get("amount", 0)
            if amount <= 0:
                state = self._ws_get_state(game_state)
                state["action_result"] = {"success": False, "log": "转化数量必须大于0"}
                return state

            rate = self._schema.get_spirit_stone_rate()
            sp_gain = amount // rate
            if sp_gain <= 0:
                state = self._ws_get_state(game_state)
                state["action_result"] = {"success": False, "log": f"至少需要{rate}下品灵石"}
                return state

            cur_sp = _player_get(player, "spiritual_power", 0)
            new_sp = int(cur_sp + sp_gain)
            self._set_player_attr(player, "spiritual_power", new_sp)
            ws_stage_id = _player_get(player, "cultivation_stage", "mortal")
            self._set_player_attr(player, "cultivation_substage",
                                  self._schema.compute_substage(ws_stage_id, new_sp))

            state = self._ws_get_state(game_state)
            state["action_result"] = {
                "success": True,
                "log": f"转化{amount}下品灵石为{sp_gain}灵力",
            }
            return state

        if action == "attempt_breakthrough":
            if self._active_session:
                bt_result = self._active_session.attempt_breakthrough(qi_density=self._get_qi_density())
                state = self._ws_get_state(game_state)
                state["action_result"] = {
                    "success": bt_result["success"],
                    "log": bt_result["log"],
                    "data": bt_result.get("data"),
                }
                state["data"]["cultivation_log"] = self._active_session.log
                state["data"]["session_active"] = True
                return state

            result = self._ws_do_breakthrough(player, game_state)
            if result.success:
                player_id = getattr(player, "id", _player_get(player, "id", None))
                if player_id is not None:
                    self._mark_dirty(str(player_id))
            state = self._ws_get_state(game_state)
            state["action_result"] = {
                "success": result.success, "log": result.log,
                "data": result.data,
            }
            return state

        return {"type": "cultivation_state", "data": {},
                "action_result": {"success": False, "log": f"未知操作: {action}"}}

    def _advance_game_time(self, days: int, game_state) -> str:
        """推进游戏时间并返回描述文字。"""
        registry = getattr(self, "_registry", None)
        if not registry:
            return ""
        cal_plugin = registry.get_plugin("calendar")
        if not cal_plugin or not hasattr(cal_plugin, "_calendar") or cal_plugin._calendar is None:
            return ""

        try:
            result = cal_plugin._calendar.advance(days, "day")
            display = result.get("elapsed_display", f"{days}天")
            # 广播时间更新
            bus = getattr(game_state, '_message_bus', None)
            if bus:
                from lingmo_engine.core.types import MessageEvent
                bus.publish(MessageEvent.STATE_UPDATE, {
                    "state_updates": {"game_time": cal_plugin._calendar.to_dict()},
                })
            # 同步更新所有角色年龄
            if hasattr(cal_plugin, 'update_all_ages'):
                cal_plugin.update_all_ages()
            return display
        except Exception:
            return ""

    def _ws_do_breakthrough(self, player,
                            game_state) -> ModuleResult:
        """直接在 game_state player 上执行常规突破（不走 _get_char）。"""
        from lingmo_engine.plugins.cultivation.dao_rhyme import (
            check_breakthrough_eligibility,
            apply_rhyme_modifier,
        )
        import random
        stage_id = _player_get(player, "cultivation_stage", "mortal")
        next_stage = self._schema.get_next_stage(stage_id)
        if not next_stage:
            return ModuleResult(success=False, log="已是最高境界")

        rule = self._schema.get_breakthrough_rule(stage_id, next_stage["id"])
        if not rule:
            return ModuleResult(success=False, log="未找到突破规则")

        # 冷却检查
        cooldown = _player_get(player, "breakthrough_cooldown", 0)
        if cooldown and cooldown > 0:
            return ModuleResult(success=False, log=f"突破冷却中，剩余{cooldown}天")

        # 灵力门槛
        reqs = rule.get("requirements", {})
        sp_min = reqs.get("spiritual_power_min", 0)
        current_sp = _player_get(player, "spiritual_power", 0)
        if current_sp < sp_min:
            return ModuleResult(success=False,
                                log=f"灵力不足（需要≥{sp_min}，当前={current_sp}）")

        # 道韵门槛检查
        next_order = next_stage.get("order", 0)
        rhyme_threshold = self._schema.get_dao_rhyme_threshold(next_order - 1) if next_order > 0 else 0
        _rhyme_flags = {"enlightenment": False, "low_rhyme": False}
        if rhyme_threshold > 0:
            current_rhyme = _player_get(player, "dao_rhyme", 0)
            _rhyme_flags = check_breakthrough_eligibility(current_rhyme, rhyme_threshold, self._schema)
            if not _rhyme_flags["eligible"]:
                return ModuleResult(success=False, log=_rhyme_flags["reason"])

        # 突破方式（固定常规突破）
        bt_method = self._schema.get_breakthrough_method("natural")
        if not bt_method:
            return ModuleResult(success=False, log="未找到突破方式配置")

        # 成功率计算
        params = self._schema.get_breakthrough_params()
        base_rate = params.get("base_rate", 0.60)
        roots = _player_get(player, "spiritual_roots", [])
        quality_key = self._schema.get_root_quality_key(roots)
        root_bonus = params.get("root_quality_bonus", {}).get(quality_key, 0.0)
        qi_density = self._get_qi_density()
        qi_level = self._schema.get_qi_level(qi_density)
        qi_bonus = params.get("qi_density_bonus", {}).get(qi_level.get("id", "thin"), 0.0)
        method_mult = bt_method.get("rate_mult", 1.0)
        secondary_bonus = 0.05 if _player_get(player, "secondary_path", None) else 0.0
        success_rate = max(0.10, min(0.95,
            (base_rate + root_bonus + qi_bonus + secondary_bonus) * method_mult))

        # 道韵修正成功率
        _trib_mult_override = None
        if rhyme_threshold > 0:
            if _rhyme_flags["eligible"] or _rhyme_flags["low_rhyme"]:
                success_rate, _trib_mult_override = apply_rhyme_modifier(
                    success_rate, bt_method.get("tribulation_mult", 1.0),
                    _rhyme_flags["enlightenment"], _rhyme_flags["low_rhyme"],
                )

        # 天劫检查
        tribulation = rule.get("tribulation")
        if tribulation:
            effective_trib_mult = _trib_mult_override if _trib_mult_override is not None else bt_method.get("tribulation_mult", 1.0)
            return ModuleResult(success=True,
                log=f"天劫降临！{tribulation['type']}将至——",
                data={"action": "trigger_tribulation",
                      "tribulation_type": tribulation["type"],
                      "success_rate": round(success_rate, 4), "method": "natural",
                      "tribulation_mult": effective_trib_mult})

        # 掷骰
        roll = random.random()
        if roll <= success_rate:
            # 成功
            self._set_player_attr(player, "cultivation_stage", next_stage["id"])
            self._set_player_attr(player, "level", next_stage.get("order", 0))
            new_sub = self._schema.compute_substage(
                next_stage["id"], _player_get(player, "spiritual_power", 0))
            self._set_player_attr(player, "cultivation_substage", new_sub)

            lifespan_gain = rule.get("success", {}).get("lifespan_gain", 0)
            self._set_player_attr(player, "lifespan_remaining",
                                  _player_get(player, "lifespan_remaining", 100) + lifespan_gain)
            self._set_player_attr(player, "breakthrough_cooldown", 0)

            results_config = self._schema.get_breakthrough_results()
            great_threshold = results_config.get("great_success", {}).get("threshold", 0.80)
            is_great = success_rate > great_threshold
            label = "大成突破！" if is_great else "突破成功！"
            return ModuleResult(success=True,
                log=f"{label} 晋升{next_stage['name']}！",
                data={"new_stage": next_stage["id"], "new_stage_name": next_stage["name"],
                      "is_great_success": is_great,
                      "roll": round(roll, 4), "success_rate": round(success_rate, 4),
                      "lifespan_gain": lifespan_gain})
        else:
            # 失败
            results_config = self._schema.get_breakthrough_results()
            if success_rate > 0.50:
                config = results_config.get("minor_failure", {})
            else:
                config = results_config.get("major_failure", {})

            sp_loss = config.get("sp_loss", 0.30)
            cooldown_days = config.get("cooldown_days", 30)
            new_sp = max(0, int(_player_get(player, "spiritual_power", 0) * (1 - sp_loss)))
            self._set_player_attr(player, "spiritual_power", new_sp)
            stage_id = _player_get(player, "cultivation_stage", "mortal")
            self._set_player_attr(player, "cultivation_substage",
                                  self._schema.compute_substage(stage_id, new_sp))
            self._set_player_attr(player, "vitality",
                                  max(1, int(_player_get(player, "vitality", 100) * (1 - sp_loss * 0.5))))
            self._set_player_attr(player, "breakthrough_cooldown", cooldown_days)

            severity = "严重" if sp_loss > 0.5 else "轻微"
            return ModuleResult(success=False,
                log=f"突破失败（{severity}）！灵力损失{int(sp_loss*100)}%，冷却{cooldown_days}天",
                data={"severity": severity, "sp_loss_ratio": sp_loss,
                      "cooldown_days": cooldown_days,
                      "roll": round(roll, 4), "success_rate": round(success_rate, 4)})

    def _set_player_attr(self, player, key, value):
        """统一设置 player 属性（兼容 dict 和 object），与 _player_get 读取路径对称。"""
        if isinstance(player, dict):
            extra = player.get("extra")
            if isinstance(extra, dict) and key in extra:
                extra[key] = value
            else:
                player[key] = value
        else:
            extra = getattr(player, 'extra', None)
            if isinstance(extra, dict) and key in extra:
                extra[key] = value
            else:
                setattr(player, key, value)

    _CN_NUM = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五",
               6: "六", 7: "七", 8: "八", 9: "九", 10: "十"}

    def _resolve_substage_name(self, stage: dict, substage_id: str) -> str:
        """将子境界 ID 解析为中文名。"""
        labels_cn = stage.get("sub_labels_cn", {})
        if substage_id in labels_cn:
            return labels_cn[substage_id]
        # 数字阶段 → 中文数字 + "阶"
        try:
            n = int(substage_id)
            return f"{self._CN_NUM.get(n, substage_id)}阶"
        except (ValueError, TypeError):
            return substage_id

    _ROOT_QUALITY_NAMES = {
        "heavenly": "天灵根", "upper": "上品灵根",
        "middle": "中品灵根", "lower": "下品灵根", "waste": "废灵根",
    }

    def _get_qi_density(self, location: str = "") -> float:
        """通过 EventBus 从地图插件获取指定位置的灵气浓度。"""
        bus = getattr(self, "_bus", None)
        if not bus:
            return 0.4
        info = bus.request(PluginEvent.MAP_GET_LOCATION_INFO, location)
        if not info:
            return 0.4
        node = info.get("current_node", {})
        qd = node.get("qi_density")
        if qd is not None:
            return qd
        # 设施节点 qi_density 为 None，沿 breadcrumb 向上查找父节点
        for bc in info.get("breadcrumb", []):
            qd = bc.get("qi_density")
            if qd is not None:
                return qd
        return 0.4

    def _get_char(self, char_id: str):
        registry = getattr(self, "_registry", None)
        if not registry:
            return None
        char_plugin = registry.get_plugin("character")
        if not char_plugin:
            return None
        cm = char_plugin._get_character_manager()
        if not cm:
            return None
        try:
            return cm.get(int(char_id))
        except (ValueError, TypeError):
            return None

    def _mark_dirty(self, char_id) -> None:
        """标记角色为脏，确保下次 save_all 时写入磁盘。"""
        registry = getattr(self, "_registry", None)
        if not registry:
            return
        char_plugin = registry.get_plugin("character")
        if not char_plugin:
            return
        cm = char_plugin._get_character_manager()
        if cm:
            cm.mark_dirty(int(char_id))

    # ── NPC 离场状态同步 ──

    def _get_calendar_instance(self):
        """获取 DefaultCalendar 实例。"""
        registry = getattr(self, "_registry", None)
        if not registry:
            return None
        cal_plugin = registry.get_plugin("calendar")
        if cal_plugin and hasattr(cal_plugin, "_calendar") and cal_plugin._calendar:
            return cal_plugin._calendar
        return None

    @staticmethod
    def _format_calendar_date(calendar) -> str:
        """将日历实例格式化为 YYYY/MM/DD 字符串。"""
        return f"{calendar._current_year}/{calendar._current_month}/{calendar._current_day}"

    @staticmethod
    def _calc_elapsed_days(last_updated: str, calendar) -> int:
        """计算 last_updated 日期与当前日历日期之间的天数差。

        使用绝对天数近似计算：year × days_per_year + month × days_per_month + day。
        """
        from lingmo_engine.core.calendar import DefaultCalendar
        parsed = DefaultCalendar.parse_birthday(last_updated)
        if not parsed:
            return 0
        ly, lm, ld = parsed
        dpm = calendar._days_per_month
        dpy = calendar._months_per_year * dpm
        last_abs = ly * dpy + lm * dpm + ld
        curr_abs = calendar._current_year * dpy + calendar._current_month * dpm + calendar._current_day
        return max(0, curr_abs - last_abs)

    def _do_sync_npc_state(self, params: dict) -> ModuleResult:
        """同步 NPC 离场期间的状态变化。

        仅计算基准值（按公式计算的"正常"状态变化），
        LLM 收到返回后可根据剧情上下文用 update_character_field 进行调整。
        """
        # 1. 获取角色
        char_id = params.get("character_id")
        char = self._get_char(str(char_id))
        if not char:
            return ModuleResult(success=False, log=f"角色 id={char_id} 未找到")

        # 已死亡角色无需同步
        if not getattr(char, "is_alive", True):
            return ModuleResult(success=False, log=f"角色「{char.name}」已死亡，无法同步状态")

        # 2. 获取日历
        calendar = self._get_calendar_instance()
        if calendar is None:
            return ModuleResult(success=False, log="日历系统不可用，无法同步 NPC 状态")

        # 3. 计算经过天数
        last_updated = getattr(char, "last_updated", "")
        today_str = self._format_calendar_date(calendar)

        if not last_updated:
            # 首次同步，仅记录日期
            char.last_updated = today_str
            self._mark_dirty(char.id)
            return ModuleResult(
                success=True,
                log=f"角色「{char.name}」首次状态同步，已记录日期 {today_str}",
            )

        elapsed = self._calc_elapsed_days(last_updated, calendar)
        if elapsed <= 0:
            return ModuleResult(
                success=True,
                log=f"角色「{char.name}」状态已是最新",
            )

        # 4. 状态更新
        notes: list[str] = [f"离场 {elapsed} 天"]

        # 用于返回数据的变量
        sp_old = sp_new = None
        cd_old = cd_new = 0

        # 4a. 灵力增长（非凡人 + 有灵根）
        stage_id = getattr(char, "cultivation_stage", "") or "mortal"
        roots = list(getattr(char, "spiritual_roots", []))
        if stage_id != "mortal" and roots:
            qi_density = self._get_qi_density(getattr(char, "location", ""))
            daily_sp = self._schema.calculate_daily_sp(stage_id, roots, qi_density, "meditation")
            sp_gain = int(round(daily_sp * elapsed))
            notes.append(f"灵气浓度: {qi_density}")
            if sp_gain > 0:
                sp_old = getattr(char, "spiritual_power", 0)
                sp_new = sp_old + sp_gain
                char.spiritual_power = sp_new
                notes.append(f"灵力: {sp_old} → {sp_new}")
                # 重算小境界
                new_sub = self._schema.compute_substage(stage_id, sp_new)
                old_sub = getattr(char, "cultivation_substage", "")
                if new_sub != old_sub:
                    char.cultivation_substage = new_sub

        # 4b. 突破冷却衰减
        cd_old = char.attrs.get("breakthrough_cooldown", 0)
        if cd_old > 0:
            cd_new = max(0, cd_old - elapsed)
            char.attrs["breakthrough_cooldown"] = cd_new
            notes.append(f"突破冷却: {cd_old} → {cd_new}")

        # 4c. 体力/生机恢复
        max_v = char.attrs.get("max_vitality", 50)
        max_s = char.attrs.get("max_stamina", 50)
        cur_v = char.attrs.get("vitality", max_v)
        cur_s = char.attrs.get("stamina", max_s)
        if cur_v < max_v:
            char.attrs["vitality"] = max_v
            notes.append(f"生机恢复: {cur_v} → {max_v}")
        if cur_s < max_s:
            char.attrs["stamina"] = max_s
            notes.append(f"体力恢复: {cur_s} → {max_s}")

        # 4d. 更新 last_updated
        char.last_updated = today_str
        self._mark_dirty(char.id)

        # 构建同步结果数据，供 LLM 参考
        sync_result = {
            "spiritual_power": {"old": sp_old, "new": sp_new},
            "breakthrough_cooldown": {"old": cd_old, "new": cd_new if cd_old > 0 else cd_old},
            "vitality": {"old": cur_v, "new": char.attrs.get("vitality", cur_v)},
            "stamina": {"old": cur_s, "new": char.attrs.get("stamina", cur_s)},
        }

        return ModuleResult(
            success=True,
            log=f"角色「{char.name}」状态已同步（基准值）: {'; '.join(notes)}。"
                f"请根据剧情需要使用 update_character_field 调整。",
            data={
                "elapsed_days": elapsed,
                "sync_result": sync_result,
            },
        )
