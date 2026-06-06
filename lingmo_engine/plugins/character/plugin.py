"""CharacterPlugin — LLM 自治角色生成与管理系统。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from lingmo_engine.core.base_plugin import BasePlugin
from lingmo_engine.core.events import PluginName, PluginEvent
from lingmo_engine.core.message_bus import MessageEvent
from lingmo_engine.core.types import ModuleResult, DisplayType
from lingmo_engine.plugins.character.character_generator import CharacterGenerator
from lingmo_engine.plugins.character.attribute_validator import AttributeValidator
from lingmo_engine.plugins.character.scene_validator import SceneValidator

if TYPE_CHECKING:
    from lingmo_engine.core.game_state import GameState

logger = logging.getLogger(__name__)


class CharacterPlugin(BasePlugin):
    """LLM 自治角色系统 —— 引擎被动存储、校验、展示，LLM 全权管理角色内容。"""

    name = PluginName.CHARACTER
    version = "0.1.0"
    depends_on: list[str] = []
    _game_state = None

    def __init__(self):
        super().__init__()
        self._generator = CharacterGenerator()
        self._validator = AttributeValidator()
        self._scene_validator: SceneValidator | None = None
        self._loaded: bool = False

    # ── 生命周期 ──

    def on_load(self) -> None:
        """加载 World 角色配置（生成指引、模板、schema）。"""
        if self._loaded:
            return
        self._loaded = True
        world = self.world
        if world is None:
            logger.warning("CharacterPlugin: world not available, using defaults")
            self._generator.load_defaults()
            self._validator.load_defaults()
            return

        world_dir = getattr(world, '_world_dir', None)
        if world_dir is None:
            logger.warning("CharacterPlugin: world_dir not found, using defaults")
            self._generator.load_defaults()
            self._validator.load_defaults()
            return

        # 注入角色 schema（替代旧 attributes.yaml + validation.yaml）
        schema = world.get_character_schema()
        if schema.get("attributes") or schema.get("fields"):
            self._validator.set_attributes_schema(schema)
            self._generator.set_schema_template(schema)
        else:
            self._validator.load_defaults()
            self._generator.load_defaults()

        # 加载世界级生成指引和示例
        chars_dir = Path(world_dir) / "characters"
        if chars_dir.is_dir():
            self._generator.load_world_config(chars_dir)

        # 注入角色标签分组
        char_tag_groups = world.get_character_tag_groups()
        if char_tag_groups:
            self._generator.set_character_tag_groups(char_tag_groups)

        # 注入 GameWorld 引用（用于 abilities 生成时获取技能配置）
        self._generator.set_world(world)

        # 注入 EventBus 引用（用于收集装备叙事效果等跨插件数据）
        self._generator._event_bus = self.bus

        # 监听战斗结束事件，清理临时角色
        if self.bus:
            self.bus.subscribe(PluginEvent.COMBAT_ENDED, self._on_combat_ended)
            self.bus.subscribe(MessageEvent.LLM_LOOP_COMPLETE, self._on_loop_complete_validate)
            # 提供预设模板数据供其他插件查询（如 CombatPlugin spawn_hostiles）
            self.bus.handle(PluginEvent.CHARACTER_GET_PRESET_BIAS, self._handle_get_preset_bias)

    # ── 系统提示 ──

    def get_semi_static_prompt(self) -> str:
        """角色生成指引在 session 期间不变，放入半静态层。"""
        return self._generator.build_system_prompt_fragment()

    def get_system_prompt(self) -> str:
        return ""

    # ── LLM 工具 ──

    def get_tools(self) -> list:
        return self._generator.build_tools()

    def execute_tool(self, tool_name: str, params: dict) -> ModuleResult:
        # 注入 game_state 引用（每次执行时更新，确保 slot_dir 正确）
        self._generator.set_game_state(self._get_game_state())

        return self._generator.execute_tool(
            tool_name, params,
            character_manager=self._get_character_manager(),
            validator=self._validator,
            event_bus=self.bus,
        )

    # ── 上下文提示 ──

    def get_context_hint(self, state: dict) -> str:
        return self._generator.get_character_summaries(self._get_character_manager())

    # ── 状态持久化 ──

    def get_state(self) -> dict:
        return self._generator.get_state()

    def load_state(self, state: dict) -> None:
        self._generator.load_state(state)

    # ── WebSocket ──

    def handle_websocket(self, message: dict, game_state) -> dict | None:
        msg_type = message.get("type", "")
        if msg_type == "get_characters":
            cm = self._get_character_manager()
            if cm:
                return {
                    "type": "characters_data",
                    "characters": [c.to_dict() for c in cm.all()],
                }
        return None

    # ── 内部方法 ──

    def _get_character_manager(self):
        """获取 CharacterManager 实例。"""
        world = self.world
        if world is None:
            return None
        return getattr(world, '_char_manager', None)

    def set_game_state(self, state):
        """注入 GameState 引用（由 PluginRegistry 自动调用）。"""
        self._game_state = state

    def _get_game_state(self) -> "GameState | None":
        return self._game_state

    def _handle_get_preset_bias(self, template_id: str) -> dict[str, float]:
        """EventBus handler：返回指定预设模板的 aptitude_bias。"""
        for t in self._generator.preset_templates:
            if t.get("id") == template_id:
                return t.get("aptitude_bias", {})
        return {}

    def _on_combat_ended(self, data: dict) -> None:
        """监听 COMBAT_ENDED 事件，清理临时角色。"""
        phase = data.get("phase", "")
        if phase not in ("victory", "flee"):
            return

        temp_ids = data.get("participant_ids", [])
        if not temp_ids:
            return

        cm = self._get_character_manager()
        if cm is None:
            return

        removed = cm.cleanup_temporary(temp_ids)

        if self.bus and removed:
            for rid in removed:
                try:
                    self.bus.emit(
                        PluginEvent.CHARACTER_REMOVED,
                        {"id": rid},
                    )
                except Exception:
                    logger.warning("发射 CHARACTER_REMOVED 失败", exc_info=True)

            logger.info("战斗结束，已清理 %d 个临时角色: %s", len(removed), removed)

    def _on_loop_complete_validate(self, event, message=None, **kwargs) -> None:
        """主 LLM 循环结束后校验当前场景的角色数据。"""
        cm = self._get_character_manager()
        sv = self._ensure_scene_validator()
        if not cm or not sv:
            return

        location = cm.player.location
        if not location:
            return

        chars = [c for c in cm.list_by_location(location) if c.is_alive]
        if not chars:
            return

        for char in chars:
            try:
                logs = sv.validate_character(char)
                if logs:
                    cm.mark_dirty(char.id)
                if logs:
                    logger.info("[SceneValidator] %s: %s", char.name, "; ".join(logs))
            except Exception:
                logger.warning(
                    "[SceneValidator] %s 校验失败", char.name, exc_info=True,
                )

    def _ensure_scene_validator(self) -> SceneValidator | None:
        """延迟初始化 SceneValidator。"""
        if self._scene_validator is not None:
            return self._scene_validator

        try:
            item_system = None
            equipment_system = None
            if self.bus:
                item_system = self.bus.request(PluginEvent.ITEMS_GET_SYSTEM)
                if item_system:
                    # 通过 EventBus 获取已初始化的 EquipmentSystem，避免直接导入
                    equipment_system = self.bus.request(PluginEvent.EQUIPMENT_GET_SYSTEM)

            game_state = self._get_game_state()
            self._scene_validator = SceneValidator(
                world=self.world,
                item_system=item_system,
                equipment_system=equipment_system,
                game_state=game_state,
            )
            self._scene_validator.set_validator(self._validator)
        except Exception:
            logger.warning("SceneValidator 初始化失败", exc_info=True)
            return None

        return self._scene_validator

