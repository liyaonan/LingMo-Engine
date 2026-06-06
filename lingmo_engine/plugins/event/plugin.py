"""EventPlugin — 轻量事件系统插件（LLM 自治 Markdown 文档方案）。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from lingmo_engine.core.base_plugin import BasePlugin
from lingmo_engine.core.events import PluginName
from lingmo_engine.core.types import ModuleResult
from lingmo_engine.plugins.event.event_manager import EventManager

if TYPE_CHECKING:
    from lingmo_engine.core.game_state import GameState

logger = logging.getLogger(__name__)


class EventPlugin(BasePlugin):
    """LLM 自治事件系统 —— 引擎仅被动存储、展示、注入摘要。"""

    name = PluginName.EVENTS
    version = "0.2.0"
    depends_on: list[str] = []
    _game_state = None

    def __init__(self):
        super().__init__()
        self._manager = EventManager()

    # ── 生命周期 ──

    def on_load(self) -> None:
        """加载 World 事件配置（模板、指引、示例）。"""
        world = self.world
        if world is None:
            logger.warning("EventPlugin: world not available")
            return

        world_dir = getattr(world, '_world_dir', None)
        if world_dir is None:
            logger.warning("EventPlugin: world_dir not found")
            return

        events_dir = Path(world_dir) / "events"
        if events_dir.is_dir():
            self._manager.load_world_config(events_dir)
        else:
            logger.info("EventPlugin: events/ 目录不存在，使用默认配置")

    # ── 系统提示 ──

    def get_semi_static_prompt(self) -> str:
        """事件生成指引在 session 期间不变，放入半静态层。"""
        return self._manager.build_system_prompt_fragment()

    def get_system_prompt(self) -> str:
        return ""

    # ── LLM 工具 ──

    def get_tools(self) -> list:
        return self._manager.build_tools()

    def execute_tool(self, tool_name: str, params: dict) -> ModuleResult:
        self._ensure_slot_dir()
        game_time = self._get_game_time_str()
        return self._manager.execute_tool(tool_name, params, game_time)

    # ── 上下文提示 ──

    def get_context_hint(self, state: dict) -> str:
        return self._manager.get_summaries()

    # ── 状态持久化 ──

    def get_persistence_dir(self) -> str:
        """事件插件自管理 event/ 子目录。"""
        return "event"

    def save_own_state(self, slot_dir) -> None:
        """确保所有内存中的事件都写入磁盘。

        事件在 create/update/append 时已急切写入文件（_save_event_file），
        此方法为安全网。使用 list() 快照避免并发修改 dict。
        """
        self._manager.set_slot_dir(slot_dir)
        for record in list(self._manager._events.values()):
            self._manager._save_event_file(record)

    def load_own_state(self, slot_dir) -> None:
        """从 event/ 目录恢复事件状态（SelfPersistable 主路径）。"""
        self._manager.set_slot_dir(slot_dir)
        self._manager.load_from_files()

    def get_state(self) -> dict:
        """事件已持久化到独立文件，不写入 state.json。"""
        return {}

    def load_state(self, state: dict) -> None:
        """旧格式兼容：从 state.json 迁移事件到独立文件。"""
        self._ensure_slot_dir()
        self._manager.migrate_from_state(state)

    # ── WebSocket ──

    def handle_websocket(self, message: dict, game_state) -> dict | None:
        msg_type = message.get("type", "")
        if msg_type == "get_events":
            return {
                "type": "events_data",
                "events": self._manager.list_events(),
            }
        return None

    # ── 静态资源 ──

    def get_static_dir(self) -> str | None:
        import os
        static_dir = os.path.join(os.path.dirname(__file__), "static")
        if os.path.isdir(static_dir):
            return static_dir
        return None

    # ── 内部方法 ──

    def _ensure_slot_dir(self) -> None:
        """从 GameState 获取 slot_dir 并设置到 EventManager。"""
        if self._manager.has_slot_dir:
            return
        gs = self._get_game_state()
        if gs is not None and hasattr(gs, "slot_dir"):
            self._manager.set_slot_dir(gs.slot_dir)

    def _get_game_time_str(self) -> str:
        gs = self._get_game_state()
        if gs is None:
            return ""
        gt = gs.data.get("game_time", {}) if hasattr(gs, "data") else {}
        if isinstance(gt, dict):
            return (
                f"day{gt.get('day','?')}_"
                f"month{gt.get('month','?')}_"
                f"year{gt.get('year','?')}"
            )
        return ""

    def set_game_state(self, state):
        """注入 GameState 引用（由 PluginRegistry 自动调用）。"""
        self._game_state = state

    def _get_game_state(self) -> "GameState | None":
        return self._game_state
