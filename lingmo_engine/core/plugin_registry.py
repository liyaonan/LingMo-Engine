from __future__ import annotations

import importlib
import logging

from lingmo_engine.core.events import EventBus
from lingmo_engine.core.types import ToolDefinition, ModuleResult

logger = logging.getLogger(__name__)


class PluginRegistry:
    def __init__(self, world=None):
        self._plugins: dict[str, object] = {}
        self._tool_to_plugin: dict[str, str] = {}
        self._world = world
        self._bus = EventBus()

    @property
    def bus(self) -> EventBus:
        """事件总线，供插件间解耦通信。"""
        return self._bus

    def register(self, plugin, message_bus=None) -> None:
        plugin.set_registry(self)
        if self._world is not None:
            plugin.set_world(self._world)
        # 注入事件总线
        if hasattr(plugin, 'set_event_bus'):
            plugin.set_event_bus(self._bus)
        # 注入消息事件总线
        if message_bus and hasattr(plugin, 'set_message_bus'):
            plugin.set_message_bus(message_bus)
        self._plugins[plugin.name] = plugin
        for tool in plugin.get_tools():
            self._register_tool(tool.name, plugin.name)
        plugin.on_load()
        logger.info("Registered plugin: %s v%s", plugin.name, plugin.version)

    def register_from_config(self, plugin_entries: list, message_bus=None) -> None:
        """从配置批量注册插件（两阶段加载）。

        阶段1：实例化所有插件并注入依赖（registry, world, event_bus）
        阶段2：所有插件注册完毕后统一调用 on_load()
              确保依赖方的 EventBus handler 在此阶段已全部注册
        阶段3：验证依赖关系
        """
        pending = []
        for entry in plugin_entries:
            if not entry.enabled:
                logger.info("Skipping disabled plugin: %s", entry.name)
                continue
            module_path = f"lingmo_engine.{entry.module}"
            try:
                module = importlib.import_module(module_path)
            except Exception:
                logger.exception("Failed to import plugin module: %s", module_path)
                continue
            try:
                cls = getattr(module, entry.cls)
            except AttributeError:
                logger.exception("Plugin class %s not found in module %s", entry.cls, module_path)
                continue
            try:
                plugin = cls()
            except Exception:
                logger.exception("Failed to instantiate plugin: %s.%s", module_path, entry.cls)
                continue
            # 注入依赖
            plugin.set_registry(self)
            if self._world is not None:
                plugin.set_world(self._world)
            if hasattr(plugin, 'set_event_bus'):
                plugin.set_event_bus(self._bus)
            # 注入 MessageBus
            if message_bus and hasattr(plugin, 'set_message_bus'):
                plugin.set_message_bus(message_bus)
            self._plugins[plugin.name] = plugin
            for tool in plugin.get_tools():
                self._register_tool(tool.name, plugin.name)
            pending.append(plugin)
            logger.info("Registered plugin: %s v%s", plugin.name, plugin.version)

        # 按依赖拓扑顺序调用 on_load()，确保被依赖方先完成初始化
        for plugin in self._topological_order(pending):
            plugin.on_load()

        # 验证插件依赖
        self._validate_dependencies()

    def _topological_order(self, plugins: list) -> list:
        """按依赖拓扑排序：被依赖方在前，依赖方在后。"""
        plugin_map = {p.name: p for p in plugins}
        visited: set[str] = set()
        visiting: set[str] = set()  # 当前 DFS 路径上的节点，用于检测循环依赖
        result: list = []

        def visit(name: str):
            if name in visited:
                return
            if name in visiting:
                # 检测到循环依赖，构建路径信息用于错误报告
                cycle_path = list(visiting) + [name]
                raise RuntimeError(
                    f"检测到插件循环依赖: {' -> '.join(cycle_path)}"
                )
            visiting.add(name)
            plugin = plugin_map.get(name)
            if plugin is None:
                visiting.discard(name)
                return
            for dep in getattr(plugin, 'depends_on', []):
                if dep in plugin_map:
                    visit(dep)
            visiting.discard(name)
            visited.add(name)
            result.append(plugin)

        for p in plugins:
            visit(p.name)

        return result

    def _validate_dependencies(self) -> None:
        """验证所有已注册插件的依赖是否满足。"""
        for name, plugin in self._plugins.items():
            depends_on = getattr(plugin, 'depends_on', [])
            if not depends_on:
                continue
            for dep in depends_on:
                if dep not in self._plugins:
                    raise RuntimeError(
                        f"Plugin '{name}' depends on '{dep}'，但 '{dep}' 未注册"
                    )
                logger.debug("Plugin dependency: %s -> %s (OK)", name, dep)

    def _register_tool(self, tool_name: str, plugin_name: str) -> None:
        """注册工具名称到插件的映射，检测重名冲突。"""
        existing = self._tool_to_plugin.get(tool_name)
        if existing is not None and existing != plugin_name:
            logger.error(
                "工具名冲突: '%s' 已被插件 '%s' 注册，插件 '%s' 试图覆盖",
                tool_name, existing, plugin_name,
            )
            raise RuntimeError(
                f"工具名冲突: '{tool_name}' 已被插件 '{existing}' 注册，"
                f"插件 '{plugin_name}' 无法覆盖"
            )
        if existing == plugin_name:
            logger.debug("工具 '%s' 已被同一插件 '%s' 注册，跳过", tool_name, plugin_name)
            return
        self._tool_to_plugin[tool_name] = plugin_name

    def get_plugin(self, name: str):
        """公开接口：按名称获取已注册的插件实例。不存在时返回 None。"""
        return self._plugins.get(name)

    def get_tool_definition(self, tool_name: str):
        """按名称查找工具定义。返回 ToolDefinition 或 None。"""
        plugin_name = self._tool_to_plugin.get(tool_name)
        if plugin_name is None:
            return None
        plugin = self._plugins.get(plugin_name)
        if plugin is None:
            return None
        for tool in plugin.get_tools():
            if tool.name == tool_name:
                return tool
        return None

    def set_gamemaster(self, gamemaster) -> None:
        """设置 GameMaster 引用（由 GameMaster 在初始化时调用）。"""
        self._gamemaster = gamemaster
        # 注入 LLMProviderAccess 和 GameState 到所有支持的插件
        from lingmo_engine.services.llm_provider_access import GMProviderAccess
        access = GMProviderAccess(gamemaster)
        for plugin in self._plugins.values():
            if hasattr(plugin, 'set_llm_access'):
                plugin.set_llm_access(access)
            if hasattr(plugin, 'set_game_state'):
                plugin.set_game_state(gamemaster.state)

    def set_game_state(self, state) -> None:
        """设置 GameState 引用（由 GameMaster 在初始化时调用）。"""
        self._state = state

    def get_all_tools(self) -> list[ToolDefinition]:
        tools = []
        for plugin in self._plugins.values():
            for tool in plugin.get_tools():
                tools.append(tool)
                # 动态工具注册：get_tools() 可能返回条件性工具
                # （如 EventPlugin 的 generate_event_plan），需将其注册到映射表
                if tool.name not in self._tool_to_plugin:
                    self._tool_to_plugin[tool.name] = plugin.name
        return tools

    def get_all_skill_dirs(self) -> list[str]:
        """汇总所有插件的 Skill 目录路径。"""
        dirs = []
        for plugin in self._plugins.values():
            dirs.extend(plugin.get_skill_dirs())
        return dirs

    def get_all_static_dirs(self) -> list[tuple[str, str]]:
        """汇总所有插件的静态资源目录。

        Returns:
            [(plugin_name, static_dir_path), ...] 仅包含实际存在的目录。
        """
        result = []
        for name, plugin in self._plugins.items():
            static_dir = plugin.get_static_dir()
            if static_dir:
                result.append((name, static_dir))
        return result

    def get_enabled_plugins(self) -> list:
        """返回所有已注册插件的列表。"""
        return list(self._plugins.values())

    def get_all_ui_components(self) -> dict[str, list]:
        """收集所有插件的 UI 组件，按类型分组。

        Returns:
            {"panel": [...], "overlay": [...], ...} — 按组件类型分组。
        """
        result: dict[str, list] = {}
        for plugin in self._plugins.values():
            for comp in plugin.get_ui_components():
                comp_type = comp.get_component_type()
                result.setdefault(comp_type, []).append(comp)
        return result

    def get_all_system_prompts(self) -> list[str]:
        """收集所有已启用插件的 system prompt 片段。

        Returns:
            [prompt_str, ...] 仅包含非空片段。
        """
        prompts = []
        for plugin in self._plugins.values():
            try:
                p = plugin.get_system_prompt()
                if p:
                    prompts.append(p)
            except Exception:
                logger.warning(
                    "插件 %s 的 get_system_prompt() 抛出异常，已跳过",
                    getattr(plugin, 'name', 'unknown'),
                )
        return prompts

    def get_all_semi_static_prompts(self) -> list[str]:
        """收集所有插件的半静态提示词片段（session 期间几乎不变）。

        Returns:
            [prompt_str, ...] 仅包含非空片段。
        """
        prompts = []
        for plugin in self._plugins.values():
            try:
                p = plugin.get_semi_static_prompt()
                if p:
                    prompts.append(p)
            except Exception:
                logger.warning(
                    "插件 %s 的 get_semi_static_prompt() 抛出异常，已跳过",
                    getattr(plugin, 'name', 'unknown'),
                )
        return prompts

    def execute(self, plugin_name: str, tool_name: str, params: dict) -> ModuleResult:
        plugin = self._plugins.get(plugin_name)
        if plugin is None:
            raise ValueError(f"Plugin not found: {plugin_name}")
        return plugin.execute_tool(tool_name, params)

    def execute_tool_by_name(self, tool_name: str, params: dict) -> ModuleResult:
        plugin_name = self._tool_to_plugin.get(tool_name)
        if plugin_name is not None:
            return self.execute(plugin_name, tool_name, params)
        # 动态工具兜底：遍历所有插件当前的 get_tools() 查找匹配
        for name, plugin in self._plugins.items():
            for tool in plugin.get_tools():
                if tool.name == tool_name:
                    self._tool_to_plugin[tool_name] = name
                    return plugin.execute_tool(tool_name, params)
        raise ValueError(f"No plugin handles tool: {tool_name}")

    def get_all_state(self) -> dict:
        return {
            name: plugin.get_state()
            for name, plugin in self._plugins.items()
        }

    def load_state_to_all_plugins(self, state: dict) -> None:
        """将完整游戏状态注入所有插件（用于 execute_tool 之前）"""
        for plugin in self._plugins.values():
            plugin.load_state(state)

    def route_websocket(self, msg: dict, game_state) -> dict | None:
        """将 WebSocket 消息路由到所有插件，返回第一个非 None 结果。

        插件通过实现 handle_websocket() 方法来处理前端的消息类型。
        检测多个插件响应同一消息类型的情况并发出警告。
        """
        first_result = None
        responders = []
        for plugin in self._plugins.values():
            result = plugin.handle_websocket(msg, game_state)
            if result is not None:
                if first_result is None:
                    first_result = result
                responders.append(plugin.name)
        if len(responders) > 1:
            logger.warning(
                "WebSocket 消息 '%s' 被 %d 个插件响应（%s），仅返回第一个（%s）的结果",
                msg.get("type", "?"), len(responders),
                ", ".join(responders), responders[0],
            )
        return first_result

    def get_all_context_hints(self, state: dict) -> str:
        """收集所有插件的上下文提示，拼接为单一字符串。"""
        parts = []
        for plugin in self._plugins.values():
            hint = plugin.get_context_hint(state)
            if hint:
                parts.append(hint)
        return "\n".join(parts)

    def get_location_detail_prompt(self) -> str:
        """获取 MapPlugin 的当前位置详情提示词（从 semi_static 层拆分出的动态部分）。"""
        for plugin in self._plugins.values():
            if hasattr(plugin, 'get_location_detail_prompt'):
                return plugin.get_location_detail_prompt()
        return ""

    def load_all_state(self, state: dict) -> None:
        for name, plugin in self._plugins.items():
            if name in state:
                plugin.load_state(state[name])
