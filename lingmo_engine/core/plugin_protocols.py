"""插件协议定义 — 将 BasePlugin 的庞大接口拆分为关注点分离的 Protocol。

每个 Protocol 代表一类能力。插件可以按需实现对应 Protocol，PluginRegistry 通过
isinstance 检查或 hasattr 探测来发现插件的能力。新增插件类型只需实现关心的
Protocol，无需了解其他不相关的 SPI 方法。

用法:
    class MyToolPlugin(BasePlugin, ToolProvider):
        '''只需要提供工具的插件。'''
        name = "my_tool"

        def get_tools(self) -> list[ToolDefinition]:
            ...

        def execute_tool(self, tool_name: str, params: dict) -> ModuleResult:
            ...
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from lingmo_engine.core.types import ToolDefinition, ModuleResult


# ── 工具提供者 ──────────────────────────────────


@runtime_checkable
class ToolProvider(Protocol):
    """提供 LLM 可调用的工具定义与执行逻辑。

    这是最常用的协议 —— 所有插件至少应实现此协议。
    """

    def get_tools(self) -> list[ToolDefinition]:
        """返回插件提供的工具定义列表。"""
        ...

    def execute_tool(self, tool_name: str, params: dict) -> ModuleResult:
        """根据 tool_name 执行对应逻辑并返回 ModuleResult。"""
        ...


# ── 状态持久化 ──────────────────────────────────


@runtime_checkable
class StatePersistent(Protocol):
    """需要在存档/读档时保存和恢复状态的插件。"""

    def get_state(self) -> dict:
        """返回当前插件状态（会被序列化到存档文件）。"""
        ...

    def load_state(self, state: dict) -> None:
        """从存档恢复插件状态。"""
        ...


# ── WebSocket 处理器 ────────────────────────────


@runtime_checkable
class WebSocketHandler(Protocol):
    """处理来自前端的 WebSocket 消息（如战斗操作、背包管理）。"""

    def handle_websocket(self, message: dict, game_state) -> dict | None:
        """处理 WebSocket 消息，返回响应 dict 或 None（表示不处理）。"""
        ...


# ── 提示词贡献者 ────────────────────────────────


@runtime_checkable
class PromptContributor(Protocol):
    """向 LLM 系统提示词和上下文提示注入自定义片段。"""

    def get_system_prompt(self) -> str:
        """返回插件注入系统提示词的文本片段。"""
        ...

    def get_semi_static_prompt(self) -> str:
        """返回半静态的提示词片段（session 期间几乎不变，适合前缀缓存）。"""
        ...

    def get_context_hint(self, state: dict) -> str:
        """返回 LLM 上下文提示片段（基于当前状态动态生成）。"""
        ...


# ── Skill 提供者 ────────────────────────────────


@runtime_checkable
class SkillProvider(Protocol):
    """提供自定义 Skill（从 .md 文件加载的游戏规则/技能定义）。"""

    def get_skill_dirs(self) -> list[str]:
        """返回 Skill .md 文件所在目录的绝对路径列表。"""
        ...


# ── 静态资源提供者 ──────────────────────────────


@runtime_checkable
class StaticAssetProvider(Protocol):
    """提供前端静态资源（CSS/JS/HTML），由 GameServer 挂载。"""

    def get_static_dir(self) -> str | None:
        """返回静态资源目录的绝对路径，无资源时返回 None。"""
        ...


# ── 自持久化插件 ────────────────────────────────


@runtime_checkable
class SelfPersistable(Protocol):
    """插件自管理持久化文件（在 slot_dir 下拥有独立子目录）。

    与 StatePersistent 的区别：
    - StatePersistent: 状态序列化到 state.json 的 plugins.{name} 字典中（旧模式）
    - SelfPersistable: 状态写入 slot_dir/<persistence_dir>/ 下的独立文件（新模式）

    两种模式可以共存 — 新插件优先使用 SelfPersistable，
    旧插件可按自身节奏逐步迁移。
    """

    def get_persistence_dir(self) -> str:
        """返回子目录名（如 'quest', 'weather'），空字符串表示不自管理。"""
        ...

    def save_own_state(self, slot_dir: Path) -> None:
        """将插件状态写入 slot_dir/<persistence_dir>/ 下的文件。"""
        ...

    def load_own_state(self, slot_dir: Path) -> None:
        """从 slot_dir/<persistence_dir>/ 下的文件恢复状态。"""
        ...
