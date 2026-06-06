"""角色创建 WebSocket 控制器（单页模式）。"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import WebSocket

from lingmo_engine.core.events import PluginEvent
from lingmo_engine.web.controllers.base_controller import BaseController

logger = logging.getLogger(__name__)


class CreationController(BaseController):
    """处理角色创建表单的 WebSocket 消息。"""

    def __init__(self, *, services: dict, config=None, creation_engine=None):
        super().__init__(services=services, config=config)
        self._engine = creation_engine

    def get_handlers(self) -> dict:
        return {
            "creation.start": self._handle_start,
            "creation.confirm": self._handle_confirm,
        }

    async def _handle_start(self, ws: WebSocket, msg: dict) -> None:
        world = self.game_svc.world
        config = getattr(world, 'creation_config', None)

        if config is None:
            # 无创建配置 → 回退到传统新游戏流程（无开场文本）
            await self._init_new_game_state()
            opening = ""
            await self._publish_opening_message(opening)
            cm = getattr(self.game_svc.state, 'character_manager', None)
            await ws.send_json({
                "type": "creation.done",
                "opening_text": opening,
                "character": self.game_svc.state.get_player().to_dict()
                    if cm else {},
            })
            return

        from lingmo_engine.character_creation.engine import CreationEngine
        from lingmo_engine.core.character_manager import CharacterManager

        cm = getattr(self.game_svc.state, 'character_manager', None)
        if cm is None:
            cm = CharacterManager()
            self.game_svc.state.character_manager = cm

        engine = CreationEngine(
            config=config,
            world=world,
            character_manager=cm,
            game_state=self.game_svc.state,
        )
        self._engine = engine

        config_data = engine.get_config_data()
        await ws.send_json({"type": "creation.config", **config_data})

    async def _handle_confirm(self, ws: WebSocket, msg: dict) -> None:
        engine = self._engine
        if engine is None:
            await ws.send_json({
                "type": "creation.error",
                "message": "创建引擎未初始化",
            })
            return

        template_id = msg.get("template_id", "")
        fields = msg.get("fields", {})

        try:
            engine.create_character(template_id, fields)
        except ValueError as e:
            await ws.send_json({
                "type": "creation.error",
                "message": str(e),
            })
            return

        opening_text = engine.get_opening_text()

        # 初始化完整游戏状态，注入模板角色
        player = engine.character_manager.player
        await self._init_new_game_state(
            player_location=player.location,
            player_character=player,
        )

        # 更新叙事风格（触发 PromptComposer 重新加载）
        self.game_svc.update_narrative_style()

        await ws.send_json({
            "type": "creation.done",
            "opening_text": opening_text,
            "character": player.to_dict(),
        })

    # ── 辅助方法 ──

    async def _init_new_game_state(
        self,
        player_location: str = "",
        player_character: "Character | None" = None,
    ) -> None:
        """初始化新游戏状态（session、日历、地图、插件），可复用。"""
        import uuid7
        from lingmo_engine.core.character_manager import CharacterManager

        session_id = self.game_svc.init_new_session()
        state = self.game_svc.state

        with self.game_svc.paused_auto_save():
            # 新游戏：清除旧 autosave，重新创建
            sm = getattr(state, 'save_manager', None)
            if sm:
                import shutil
                autosave_dir = sm.resolve_slot_path("autosave")
                if autosave_dir.exists():
                    shutil.rmtree(autosave_dir)
                slot_dir = sm.ensure_slot_dir("autosave")
                state.set_slot_dir(slot_dir)
                self.game_svc.store_set_slot_dir(str(slot_dir))
                self.game_svc.memory_set_slot_dir(str(slot_dir))

            self.game_svc.store_init_session()
            world = self.game_svc.world

            state.reset_scene_state()
            state.set_session_id(session_id)

            # 重置日历插件为初始状态（必须在 load_state_to_all_plugins 之前）
            self._reset_calendar_to_initial(state)

            # 清空所有插件的内存状态（事件、地图、战斗等）
            if sm:
                state_snapshot = state.get_data_copy()
                state_snapshot["_save_dir"] = str(state.get_save_dir())
                self.game_svc.plugins.load_state_to_all_plugins(state_snapshot)

            # 始终创建新的 CharacterManager，加载世界模板角色
            cm = CharacterManager()
            world_dir = getattr(world, '_world_dir', None)
            if world_dir:
                char_dir = Path(world_dir) / "characters" / "fixed"
                if char_dir.exists():
                    cm.load(char_dir)

            # 如果有模板创建的角色，覆盖默认主角
            if player_character is not None:
                player_character.id = 0
                cm.add_character(player_character)

                # 调用世界的 creation_hook.py（如果存在），处理开场数据
                if self._engine:
                    self._engine.call_creation_hook(cm, state)

            world._char_manager = cm
            state.character_manager = cm
            self._init_characters_last_updated(cm)

            # 设置起始位置
            loc = player_location
            if loc:
                if cm:
                    cm.update_location(0, loc)

            await self.game_svc.initialize()

            # 同步地图插件初始节点（传入角色实际位置，避免被默认根节点覆盖）
            location_info = self.game_svc.plugins.bus.request(
                PluginEvent.MAP_GET_LOCATION_INFO, loc or ""
            )
            if location_info and location_info.get("current_node"):
                node = location_info["current_node"]
                # MapPlugin 内部已通过 load_state 恢复 current_node_id
                # 更新玩家位置为完整路径（确保路径精确匹配）
                if cm and node.get("name"):
                    from lingmo_engine.plugins.map.plugin import MapPlugin
                    full_path = MapPlugin.build_full_path(location_info)
                    cm.update_location(0, full_path)

            state.save_all(self.game_svc.plugins)

    async def _publish_opening_message(self, opening_text: str) -> None:
        """将开场白发布为第一条叙事消息。"""
        if not opening_text:
            return
        from lingmo_engine.core.message import Message
        from lingmo_engine.core.message_bus import MessageEvent
        import uuid7
        opening_page_id = str(uuid7.uuid7())
        self.game_svc.set_last_page_id(opening_page_id)
        opening_msg = Message(
            id=str(uuid7.uuid7()),
            session_id=self.game_svc.session_id,
            page_id=opening_page_id,
            role="narrative",
            content=opening_text,
            status="complete",
        )
        await self.game_svc.publish_message(MessageEvent.CREATED, opening_msg)
