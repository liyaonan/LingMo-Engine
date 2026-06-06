"""遭遇插件基类 — 封装「工具触发 → Session 生命周期 → 叙事总结」流水线。"""
from __future__ import annotations

import logging

from lingmo_engine.core.base_plugin import BasePlugin
from lingmo_engine.core.encounter_session import EncounterSession

_log = logging.getLogger(__name__)


class EncounterPlugin(BasePlugin):
    """遭遇插件基类。

    子类配置 encounter_card_type / ws_prefix / narrative_skill，
    然后实现 _create_session / _process_action / _on_session_end / _build_narrative_prompt。
    如需额外 WS 路由，覆盖 _handle_extra_ws。
    """

    encounter_card_type: str = ""
    ws_prefix: str = ""
    narrative_skill: str = ""

    def __init__(self):
        super().__init__()
        self._active_session: EncounterSession | None = None

    def has_active_session(self) -> bool:
        return self._active_session is not None and self._active_session.is_active()

    # ── WS 路由（基类提供标准三段式 + 扩展口） ──

    def handle_websocket(self, message: dict, game_state) -> dict | None:
        msg_type = message.get("type", "")
        prefix = self.ws_prefix

        if msg_type == f"{prefix}_start_session":
            return self._ws_start_session(message, game_state)
        if msg_type == f"{prefix}_action":
            return self._ws_handle_action(message, game_state)
        if msg_type == f"{prefix}_finish":
            return self._ws_finish_session(game_state)
        return self._handle_extra_ws(msg_type, message, game_state)

    # ── 钩子方法（子类必须覆盖） ──

    def _create_session(self, params: dict, game_state) -> EncounterSession:
        raise NotImplementedError

    def _process_action(self, action: dict, session: EncounterSession) -> dict:
        raise NotImplementedError

    def _on_session_end(self, session: EncounterSession, game_state) -> list:
        return []

    def _build_narrative_prompt(self, session: EncounterSession) -> str:
        raise NotImplementedError

    def _handle_extra_ws(self, msg_type: str, message: dict, game_state) -> dict | None:
        return None

    # ── 内部实现 ──

    def _ws_start_session(self, message: dict, game_state) -> dict:
        try:
            session = self._create_session(message, game_state)
            self._active_session = session
            return {
                "type": f"{self.ws_prefix}_session_start",
                "data": {"session_active": True},
                "action_result": {"success": True},
            }
        except Exception as e:
            _log.error("%s _ws_start_session error: %s", self.ws_prefix, e, exc_info=True)
            return {
                "type": f"{self.ws_prefix}_session_start",
                "data": {},
                "action_result": {"success": False, "log": f"内部错误: {e}"},
            }

    def _ws_handle_action(self, message: dict, game_state) -> dict:
        try:
            action = message.get("action", {})
            result = self._process_action(action, self._active_session)
            return result
        except Exception as e:
            _log.error("%s _ws_handle_action error: %s", self.ws_prefix, e, exc_info=True)
            return {
                "type": f"{self.ws_prefix}_state",
                "action_result": {"success": False, "log": f"内部错误: {e}"},
            }

    def _ws_finish_session(self, game_state) -> dict:
        if not self._active_session:
            return {
                "type": f"{self.ws_prefix}_session_end",
                "action_result": {"success": False, "log": "没有活跃会话"},
            }
        try:
            session = self._active_session
            summary = session.finish()
            actions = self._on_session_end(session, game_state)
            self._active_session = None

            narr_action = None
            try:
                prompt = self._build_narrative_prompt_from_session(session)
                if prompt:
                    narr_action = {
                        "action": "generate_narrative",
                        "stream_type": f"{self.ws_prefix}_narrative",
                        "prompt": prompt,
                        "fallback_text": f"{self.ws_prefix} 会话已结束。",
                    }
                    extra = self._get_narrative_extra(session, game_state)
                    if extra:
                        narr_action.update(extra)
            except NotImplementedError:
                pass

            result = {
                "type": f"{self.ws_prefix}_session_end",
                "data": summary,
            }
            all_actions = list(actions)
            if narr_action:
                all_actions.append(narr_action)
            if all_actions:
                result["_actions"] = all_actions
            return result
        except Exception as e:
            _log.error("%s _ws_finish_session error: %s", self.ws_prefix, e, exc_info=True)
            self._active_session = None
            return {
                "type": f"{self.ws_prefix}_session_end",
                "action_result": {"success": False, "log": f"内部错误: {e}"},
            }

    def _build_narrative_prompt_from_session(self, session) -> str | None:
        if session is None:
            return None
        return self._build_narrative_prompt(session)

    def _get_narrative_extra(self, session, game_state) -> dict:
        """子类可覆盖，返回额外注入到 narrative action 的字段。"""
        return {}
