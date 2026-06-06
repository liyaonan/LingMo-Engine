from __future__ import annotations

import json
from typing import TYPE_CHECKING

from lingmo_engine.core.types import ToolDefinition, ModuleResult
from lingmo_engine.core.plugin_protocols import (
    ToolProvider,
    StatePersistent,
    WebSocketHandler,
    PromptContributor,
    SkillProvider,
    StaticAssetProvider,
    SelfPersistable,
)

if TYPE_CHECKING:
    from lingmo_engine.core.events import EventBus


class BasePlugin(
    ToolProvider,
    StatePersistent,
    WebSocketHandler,
    PromptContributor,
    SkillProvider,
    StaticAssetProvider,
    SelfPersistable,
):
    """插件基类 — 所有自定义插件继承此类。

    实现了所有 Plugin Protocol 的默认（空）行为。
    子类按需覆盖对应方法即可，无需了解不相关的 SPI。
    """
    name: str = ""
    version: str = "0.1.0"
    depends_on: list[str] = []  # 依赖的插件名称列表，PluginRegistry 启动时验证
    _registry = None
    _world = None
    _bus = None

    def set_registry(self, registry) -> None:
        self._registry = registry

    def set_world(self, world) -> None:
        self._world = world

    def set_event_bus(self, bus: "EventBus") -> None:
        """注入事件总线，供插件间解耦通信。"""
        self._bus = bus

    def set_message_bus(self, bus) -> None:
        """注入消息事件总线，供插件监听消息生命周期事件。"""
        self._message_bus = bus

    @property
    def message_bus(self):
        """消息事件总线（可能为 None，在 register 之前）。"""
        return getattr(self, "_message_bus", None)

    @property
    def registry(self):
        return self._registry

    @property
    def world(self):
        return self._world

    @property
    def bus(self) -> "EventBus | None":
        """事件总线（可能为 None，在 register 之前）。"""
        return self._bus

    # ── 生命周期钩子 ──────────────────────────────

    def on_load(self) -> None:
        """插件注册完成后调用（world、registry、bus 已注入）"""

    def on_unload(self) -> None:
        """插件卸载前调用"""

    # ── 核心接口 ──────────────────────────────────

    def get_tools(self) -> list[ToolDefinition]:
        return []

    def get_skill_dirs(self) -> list[str]:
        """返回插件自带 Skill 目录的绝对路径列表。

        子类可覆盖此方法，SkillManager 会扫描这些目录下的 .md 文件。
        默认返回空列表。
        """
        return []

    def get_static_dir(self) -> str | None:
        """返回插件自带静态资源目录的绝对路径。

        子类可覆盖此方法，GameServer 会挂载该目录为 /static/plugins/{name}/。
        目录应包含 .css/.js/.html 等前端资源。
        默认检查子类模块所在目录下的 static/ 子目录。
        """
        import os
        import inspect
        mod = inspect.getfile(type(self))
        d = os.path.join(os.path.dirname(mod), "static")
        return d if os.path.isdir(d) else None

    def get_system_prompt(self) -> str:
        """返回插件注入系统提示词的文本片段。

        子类可覆盖此方法，GameMaster 在构建 system prompt 时
        会遍历所有启用插件并收集非空片段。
        默认返回空字符串。
        """
        return ""

    def get_semi_static_prompt(self) -> str:
        """返回半静态的提示词片段（session 期间几乎不变，适合前缀缓存）。

        子类可覆盖此方法返回在 session 期间几乎不变的内容（如角色生成指引、
        事件模板等）。这些内容会被放在 HISTORY 之前的 system message 中，
        最大化前缀缓存命中。默认返回空字符串。
        """
        return ""

    def execute_tool(self, tool_name: str, params: dict) -> ModuleResult:
        raise NotImplementedError(f"Plugin '{self.name}' does not implement '{tool_name}'")

    def call_plugin(self, plugin_name: str, tool_name: str, params: dict) -> ModuleResult:
        """[DEPRECATED] 请使用 bus.request(PluginEvent.XXX, ...) 替代。"""
        import warnings
        warnings.warn(
            f"call_plugin() is deprecated, use bus.request() instead. "
            f"Called by {self.name} -> {plugin_name}.{tool_name}",
            DeprecationWarning,
            stacklevel=2,
        )
        if self._registry is None:
            raise RuntimeError(f"Plugin '{self.name}' has no registry reference")
        return self._registry.execute(plugin_name, tool_name, params)

    def handle_websocket(self, message: dict, game_state) -> dict | None:
        """处理 WebSocket 消息。子类可覆盖以响应前端请求。

        Args:
            message: 前端发来的完整消息 dict（含 type 字段）
            game_state: GameState 实例

        Returns:
            返回给前端的响应 dict，或 None 表示不处理该消息。
        """
        return None

    def get_state(self) -> dict:
        return {}

    def load_state(self, state: dict) -> None:
        pass

    def get_context_hint(self, state: dict) -> str:
        """返回 LLM 上下文提示片段。GameMaster 构建消息时收集所有插件的提示。"""
        return ""

    def get_ui_components(self) -> list:
        """返回插件提供的 UI 组件列表。默认返回空列表。

        子类可覆盖此方法，返回实现 UIComponent 协议的对象列表。
        GameServer 启动时通过 PluginRegistry 收集所有组件并注入前端。
        """
        return []

    # ── SelfPersistable 自持久化 ─────────────────

    def get_persistence_dir(self) -> str:
        """返回自持久化子目录名。空字符串表示使用旧的 state.json 模式。"""
        return ""

    def save_own_state(self, slot_dir) -> None:
        """将插件状态写入独立目录。默认空操作。"""

    def load_own_state(self, slot_dir) -> None:
        """从独立目录恢复状态。默认空操作。"""

    # ── 自持久化辅助方法 ──────────────────────────

    def _save_plugin_json(self, slot_dir, filename: str, data: dict,
                          indent: int = 2) -> None:
        """原子写入 JSON 到插件的持久化子目录。

        使用 tempfile + fsync + os.replace 保证原子性，
        防止写入中断导致数据损坏。插件 save_own_state 应优先使用此方法。

        Args:
            slot_dir: 存档槽位根目录（由 GameState 传入）。
            filename: 文件名（如 'state.json'）。
            data: 要序列化的 dict 数据。
            indent: JSON 缩进层级，默认 2。
        """
        from lingmo_engine.core.utils import atomic_write_json
        from pathlib import Path
        pdir = self.get_persistence_dir()
        if not pdir:
            return
        target = Path(slot_dir) / pdir / filename
        atomic_write_json(target, data, indent=indent)

    def _save_plugin_yaml(self, slot_dir, filename: str, data: dict) -> None:
        """原子写入 YAML 到插件的持久化子目录。

        Args:
            slot_dir: 存档槽位根目录（由 GameState 传入）。
            filename: 文件名（如 'extensions.yaml'）。
            data: 要序列化的 dict 数据。
        """
        from lingmo_engine.core.utils import atomic_write_yaml
        from pathlib import Path
        pdir = self.get_persistence_dir()
        if not pdir:
            return
        target = Path(slot_dir) / pdir / filename
        atomic_write_yaml(target, data)

    def _load_plugin_json(self, slot_dir, filename: str) -> dict | None:
        """从插件持久化子目录读取 JSON 文件。

        Args:
            slot_dir: 存档槽位根目录。
            filename: 文件名（如 'state.json'）。

        Returns:
            解析后的 dict，文件不存在或解析失败返回 None。
        """
        from pathlib import Path
        pdir = self.get_persistence_dir()
        if not pdir:
            return None
        path = Path(slot_dir) / pdir / filename
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
