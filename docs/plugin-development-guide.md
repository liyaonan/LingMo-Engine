# Plugin Development Guide / 插件开发指南

This document explains how to develop custom plugins for LingMo Engine.

本文档介绍如何为 LingMo Engine 开发自定义插件。

---

## Table of Contents / 目录

- [Architecture Overview / 架构概览](#architecture-overview--架构概览)
- [Quick Start: Minimal Plugin / 快速开始：最小插件](#quick-start-minimal-plugin--快速开始最小插件)
- [Registration & Lifecycle / 注册与生命周期](#registration--lifecycle--注册与生命周期)
- [Core Capability Interfaces / 核心能力接口](#core-capability-interfaces--核心能力接口)
  - [Tool Provider (ToolProvider) / 工具提供者](#tool-provider-toolprovider--工具提供者)
  - [Prompt Contributor (PromptContributor) / 提示词贡献者](#prompt-contributor-promptcontributor--提示词贡献者)
  - [WebSocket Handler / WebSocket 处理器](#websocket-handler--websocket-处理器)
  - [State Persistence / 状态持久化](#state-persistence--状态持久化)
- [Inter-Plugin Communication / 插件间通信](#inter-plugin-communication--插件间通信)
  - [EventBus / 事件总线](#eventbus--事件总线)
  - [Dependency Declaration / 依赖声明](#dependency-declaration--依赖声明)
- [Encounter Plugin Pattern / 遭遇插件模式](#encounter-plugin-pattern--遭遇插件模式-encounterplugin)
- [Reading World Data / 世界数据读取](#reading-world-data--世界数据读取)
- [Registering a Plugin / 注册插件到引擎](#registering-a-plugin--注册插件到引擎)
- [Full Example: Weather Plugin / 完整示例：天气插件](#full-example-weather-plugin--完整示例天气插件)

---

## Architecture Overview / 架构概览

The plugin system is built on the **Protocol** pattern. Each protocol represents one capability:

插件系统基于 **协议 (Protocol)** 设计，每个协议代表一类能力：

```
BasePlugin
├── ToolProvider          — Provides LLM-callable tools / 提供 LLM 可调用的工具
├── PromptContributor     — Injects custom prompt fragments / 向系统提示词注入自定义片段
├── WebSocketHandler      — Responds to frontend WS messages / 响应前端 WebSocket 消息
├── StatePersistent       — Legacy persistence (writes to state.json) / 旧式状态持久化
├── SelfPersistable       — Modern persistence (independent subdirectory) / 新式自持久化
├── SkillProvider         — Provides Skill .md files / 提供 Skill .md 文件
└── StaticAssetProvider   — Provides frontend static assets / 提供前端静态资源
```

Plugins override only the methods they need. `BasePlugin` provides empty default implementations for all methods.

插件按需覆盖方法即可，无需了解不相关的协议。`BasePlugin` 为所有方法提供了空默认实现。

### Dependency Injection / 依赖注入

Plugins receive engine core components via setter methods:

插件通过 `setter` 方法接收引擎核心组件：

| Method / 方法 | Injected Object / 注入对象 | Purpose / 用途 |
|------|----------|------|
| `set_world(world)` | `GameWorld` | Read world config data / 读取世界配置数据 |
| `set_event_bus(bus)` | `EventBus` | Inter-plugin communication / 插件间通信 |
| `set_registry(registry)` | `PluginRegistry` | Access other plugins / 访问其他插件 |
| `set_game_state(state)` | `GameState` | Read/write game state / 读写游戏状态 |
| `set_message_bus(bus)` | `MessageBus` | Message lifecycle events / 消息生命周期事件 |
| `set_llm_access(access)` | `LLMProviderAccess` | Call LLM for text generation / 调用 LLM 生成文本 |

Injection order: create all plugins and inject dependencies → call `on_load()` in topological order.

注入顺序：先创建所有插件并注入依赖 → 再按依赖拓扑序调用 `on_load()`。

---

## Quick Start: Minimal Plugin / 快速开始：最小插件

The simplest plugin only needs `get_tools()` and `execute_tool()`:

一个最简单的插件只需实现 `get_tools()` 和 `execute_tool()`：

```python
# lingmo_engine/plugins/weather/plugin.py

from lingmo_engine.core.base_plugin import BasePlugin
from lingmo_engine.core.types import ToolDefinition, ToolParameter, ModuleResult


class WeatherPlugin(BasePlugin):
    name = "weather"
    version = "0.1.0"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="change_weather",
                description="Change the weather of the current scene / 改变当前场景的天气状况",
                parameters=[
                    ToolParameter(
                        name="weather",
                        type="string",
                        description="Weather type / 天气类型：晴朗/多云/小雨/暴风雨/大雾",
                        enum=["晴朗", "多云", "小雨", "暴风雨", "大雾"],
                    ),
                ],
            )
        ]

    def execute_tool(self, tool_name: str, params: dict) -> ModuleResult:
        if tool_name == "change_weather":
            weather = params["weather"]
            return ModuleResult(
                success=True,
                log=f"Weather changed to {weather} / 天气变为 {weather}",
                data={"weather": weather},
            )
        return ModuleResult(success=False, log=f"Unknown tool / 未知工具: {tool_name}")
```

---

## Registration & Lifecycle / 注册与生命周期

### Lifecycle Hooks / 生命周期钩子

```python
class MyPlugin(BasePlugin):
    def on_load(self) -> None:
        """Called after all dependencies are injected. Initialize world data
        dependencies and register EventBus handlers here.

        注册完成后调用。此时 world、registry、bus 已全部注入。
        在此初始化世界数据依赖、注册 EventBus 处理器等。"""

    def on_unload(self) -> None:
        """Called before plugin removal. / 插件卸载前调用。"""
```

### Registration Flow / 注册流程

1. Engine reads the `plugins` list from `config.yaml` / 引擎读取 `config.yaml` 的 `plugins` 列表
2. Instantiates each plugin in config order / 按配置顺序实例化每个插件
3. Injects `registry`, `world`, `event_bus`, `message_bus` / 注入依赖
4. Topological sort by `depends_on` / 拓扑排序（按 `depends_on`）
5. Validates all dependencies are satisfied / 验证依赖是否满足
6. Calls `on_load()` in sorted order / 按序调用 `on_load()`
7. Injects `game_state`, `llm_access` / 注入游戏状态和 LLM 访问

---

## Core Capability Interfaces / 核心能力接口

### Tool Provider (ToolProvider) / 工具提供者

Tools are functions the LLM can call. Once defined, the engine automatically registers them in the LLM's function calling interface.

工具是 LLM 可调用的函数。定义工具后，引擎会自动将其注册到 LLM 的 function calling 接口。

#### Defining Tools / 定义工具

```python
from lingmo_engine.core.types import ToolDefinition, ToolParameter

def get_tools(self) -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name="teleport",
            description="Teleport the player to a location / 将玩家传送到指定位置",
            parameters=[
                ToolParameter(name="location", type="string",
                             description="Target location name / 目标位置名称"),
                ToolParameter(name="method", type="string", required=False,
                             description="Travel method / 传送方式",
                             enum=["步行", "传送阵", "飞行"]),
            ],
        )
    ]
```

**`ToolParameter` fields / 字段说明：**

| Field / 字段 | Type / 类型 | Description / 说明 |
|------|------|------|
| `name` | `str` | Parameter name / 参数名 |
| `type` | `str` | `string` / `integer` / `boolean` / `array` / `object` |
| `description` | `str` | Description visible to LLM / LLM 可见的参数描述 |
| `required` | `bool` | Whether required, default `True` / 是否必填，默认 `True` |
| `enum` | `list[str]` | Allowed values / 可选值枚举列表 |

#### Executing Tools / 执行工具

```python
def execute_tool(self, tool_name: str, params: dict) -> ModuleResult:
    if tool_name == "teleport":
        location = params["location"]
        method = params.get("method", "步行")
        return ModuleResult(
            success=True,
            log=f"Player travels to {location} via {method} / 玩家通过{method}前往{location}",
            data={"location": location},
        )
    return ModuleResult(success=False, log=f"Unknown tool / 未知工具: {tool_name}")
```

**`ModuleResult` fields / 字段说明：**

| Field / 字段 | Type / 类型 | Description / 说明 |
|------|------|------|
| `success` | `bool` | Whether the operation succeeded / 操作是否成功 |
| `log` | `str` | Operation log visible to LLM / 操作日志（LLM 可见） |
| `data` | `dict` | Data returned to the engine / 返回给引擎的数据 |
| `display_type` | `DisplayType` | Frontend display type / 前端展示类型 |

**`DisplayType` enum values / 枚举值：**

| Value / 值 | Description / 说明 |
|----|------|
| `SYSTEM` | System message (default) / 系统消息（默认） |
| `COMBAT_LOG` | Combat log / 战斗日志 |
| `NARRATIVE` | Narrative text (triggers frontend stream end) / 叙述文本（会触发前端流终止） |
| `ENCOUNTER` | Encounter event card / 遭遇事件卡片 |

#### Triggering Side Effects via `data` / 通过 `data` 触发副作用

Use the `_actions` field in `ModuleResult.data` to trigger built-in engine operations:

`ModuleResult.data` 中可通过 `_actions` 字段触发引擎内置操作：

```python
return ModuleResult(
    success=True,
    log="Item acquired / 获得物品",
    data={
        "_actions": [
            {"action": "add_items", "items": [{"item_id": "sword_01", "quantity": 1}]},
            {"action": "update_player", "updates": {"exp": 100}},
            {"action": "send_state_update"},
        ]
    },
)
```

**Built-in action types / 内置 action 类型：**

| action | Description / 用途 |
|--------|------|
| `update_player` | Update player attributes / 更新玩家属性 |
| `add_items` | Add items to inventory / 添加物品到背包 |
| `remove_items` | Remove items from inventory / 从背包移除物品 |
| `publish_message` | Publish via MessageBus / 通过 MessageBus 发布消息 |
| `generate_narrative` | Trigger LLM narrative generation / 触发 LLM 生成叙述 |
| `save_state` | Save game state / 保存游戏状态 |
| `send_state_update` | Push state update to frontend / 向前端推送状态更新 |
| `clear_scene_enemies` | Clear scene enemies / 清除场景敌人 |

### Prompt Contributor (PromptContributor) / 提示词贡献者

Plugins can inject three types of prompts into the LLM context:

插件可以向 LLM 注入三种提示词：

```python
def get_system_prompt(self) -> str:
    """System prompt (included in every LLM call). Best for static rules.

    注入系统提示词（每轮 LLM 调用都包含）。适合放不变的规则说明。"""
    return "Weather system is active. Use change_weather tool to set the mood."

def get_semi_static_prompt(self) -> str:
    """Semi-static prompt (rarely changes during session, good for prefix caching).

    注入半静态提示词（session 期间几乎不变，适合前缀缓存）。"""
    return "Weather types: 晴朗 | 多云 | 小雨 | 暴风雨 | 大雾"

def get_context_hint(self, state: dict) -> str:
    """Dynamic context hint (generated per turn based on current state).

    动态上下文提示（每轮根据当前状态生成）。state 是 GameState 的 dict 快照。"""
    weather = state.get("weather", "晴朗")
    return f"Current weather / 当前天气: {weather}"
```

Injection priority: `system_prompt` (base layer) → `semi_static_prompt` (cache layer) → `context_hint` (dynamic layer).

注入位置优先级：`system_prompt`（基础层）→ `semi_static_prompt`（缓存层）→ `context_hint`（动态层）。

### WebSocket Handler / WebSocket 处理器

The frontend communicates with plugins via WebSocket. Override `handle_websocket` to respond to messages:

前端通过 WebSocket 与插件交互。覆盖 `handle_websocket` 方法响应消息：

```python
def handle_websocket(self, message: dict, game_state) -> dict | None:
    msg_type = message.get("type", "")

    if msg_type == "weather_get":
        return {
            "type": "weather_data",
            "weather": self._current_weather,
        }

    if msg_type == "weather_set":
        self._current_weather = message["weather"]
        return {
            "type": "weather_updated",
            "weather": self._current_weather,
        }

    return None  # Return None for unhandled messages / 不处理的消息返回 None
```

### State Persistence / 状态持久化

Two persistence modes can coexist:

有两种持久化模式，可共存：

#### Mode 1: SelfPersistable (Recommended) / 模式一：SelfPersistable（推荐）

Plugin manages files in its own subdirectory under the save slot:

插件在存档目录下拥有独立子目录，自行管理文件：

```python
def get_persistence_dir(self) -> str:
    """Return subdirectory name. / 返回子目录名。"""
    return "weather"

def save_own_state(self, slot_dir) -> None:
    """Save state using helper methods that write to slot_dir/weather/.

    保存状态。使用辅助方法自动定位到 slot_dir/weather/。"""
    self._save_plugin_json(slot_dir, "state.json", {
        "weather": self._current_weather,
        "history": self._history,
    })

def load_own_state(self, slot_dir) -> None:
    """Load state. File not found returns None. / 加载状态。"""
    data = self._load_plugin_json(slot_dir, "state.json")
    if data:
        self._current_weather = data.get("weather", "晴朗")
        self._history = data.get("history", [])
```

**Helper methods / 辅助方法：**

| Method / 方法 | Description / 说明 |
|------|------|
| `_save_plugin_json(slot_dir, filename, data)` | Atomic JSON write / 原子写入 JSON |
| `_save_plugin_yaml(slot_dir, filename, data)` | Atomic YAML write / 原子写入 YAML |
| `_load_plugin_json(slot_dir, filename)` | Safe JSON read, returns `None` if missing / 安全读取 JSON |

#### Mode 2: StatePersistent (Legacy) / 模式二：StatePersistent（旧式）

State is serialized into the `plugins.{name}` field of `state.json`:

状态序列化到 `state.json` 的 `plugins.{name}` 字段中：

```python
def get_state(self) -> dict:
    return {"weather": self._current_weather}

def load_state(self, state: dict) -> None:
    self._current_weather = state.get("weather", "晴朗")
```

Best for simple plugins with small data. New plugins should prefer SelfPersistable.

适用于数据量小的简单插件。新插件建议使用 SelfPersistable。

---

## Inter-Plugin Communication / 插件间通信

### EventBus / 事件总线

EventBus provides two communication modes:

EventBus 提供两种通信模式：

#### Pub/Sub Mode (One-to-Many Broadcast) / 发布/订阅模式（一对多广播）

```python
# Plugin A: Emit event / 发布事件
self.bus.emit(PluginEvent.COMBAT_ENDED, {"result": "victory", "enemies_defeated": 3})

# Plugin B: Subscribe to event / 订阅事件
class MyPlugin(BasePlugin):
    def on_load(self) -> None:
        self.bus.subscribe(PluginEvent.COMBAT_ENDED, self._on_combat_ended)

    def _on_combat_ended(self, data: dict) -> None:
        victory = data.get("result") == "victory"
        count = data.get("enemies_defeated", 0)
```

#### Request/Response Mode (One-to-One Query) / 请求/响应模式（一对一查询）

```python
# Plugin A: Register handler / 注册处理器
class InventoryPlugin(BasePlugin):
    def on_load(self) -> None:
        self.bus.handle(PluginEvent.ITEMS_GET_SYSTEM, lambda: self._item_system)

# Plugin B: Send request / 发起请求
class CombatPlugin(BasePlugin):
    def on_load(self) -> None:
        self._item_system = self.bus.request(PluginEvent.ITEMS_GET_SYSTEM)
```

#### Predefined Events / 预定义事件

Defined in the `PluginEvent` enum (`lingmo_engine/core/events.py`):

在 `PluginEvent` 枚举中定义：

| Event / 事件 | Mode / 模式 | Description / 说明 |
|------|------|------|
| `EQUIPMENT_GET_BONUS` | request | Query equipment bonuses / 查询装备加成 |
| `EQUIPMENT_GET_SYSTEM` | request | Get equipment system instance / 获取装备系统实例 |
| `ITEMS_GET_SYSTEM` | request | Get item system instance / 获取物品系统实例 |
| `CALENDAR_GET_INFO` | request | Get calendar info / 获取日历信息 |
| `COMBAT_ENDED` | subscribe | Combat ended broadcast / 战斗结束广播 |
| `ABILITY_GENERATE` | request | Request ability generation / 请求生成技能 |
| `INVENTORY_REMOVE_ITEM` | subscribe | Remove item / 移除物品 |
| `INVENTORY_REGISTER_AND_ADD` | subscribe | Register and add item / 注册并添加物品 |
| `CHARACTER_UPDATED` | subscribe | Character attributes updated / 角色属性更新 |

To add new events, simply extend the `PluginEvent` enum.

如需新事件，在 `PluginEvent` 枚举中添加即可。

### Dependency Declaration / 依赖声明

Declare dependencies via `depends_on`. The engine auto-sorts topologically and validates:

通过 `depends_on` 声明插件依赖，引擎会自动拓扑排序并验证：

```python
from lingmo_engine.core.events import PluginName

class CombatPlugin(BasePlugin):
    name = PluginName.COMBAT
    depends_on: list[str] = [PluginName.INVENTORY, PluginName.CHARACTER]
```

**`PluginName` constants (`lingmo_engine/core/events.py`):**

| Constant / 常量 | Value / 值 |
|------|----|
| `CALENDAR` | `"calendar"` |
| `COMBAT` | `"combat"` |
| `EVENTS` | `"event"` |
| `EXPLORATION` | `"exploration"` |
| `GROWTH` | `"growth"` |
| `INVENTORY` | `"inventory"` |
| `MAP` | `"map"` |
| `CHARACTER` | `"character"` |
| `CRAFTING` | `"crafting"` |

---

## Encounter Plugin Pattern / 遭遇插件模式 (EncounterPlugin)

`EncounterPlugin` is a subclass of `BasePlugin` that encapsulates the full pipeline: tool trigger → session lifecycle → narrative summary. Used for combat, cultivation, and other systems that need independent session panels.

`EncounterPlugin` 是 `BasePlugin` 的子类，封装了「工具触发 → 会话生命周期 → 叙事总结」的完整流水线。适用于战斗、修炼等需要独立会话面板的场景。

```
BasePlugin
└── EncounterPlugin
    ├── CombatPlugin      — Combat session / 战斗会话
    └── CultivationPlugin  — Cultivation session / 修炼会话
```

### Core Concepts / 核心概念

- **EncounterSession**: Base session class managing lifecycle (`active → completed/failed/cancelled`), structured logs, and narrative hints
- **EncounterPlugin**: Provides standard 3-phase WebSocket routing + narrative generation

- **EncounterSession**：会话基类，管理生命周期（`active → completed/failed/cancelled`）、结构化日志、叙事提示
- **EncounterPlugin**：提供标准 WebSocket 三段式路由 + 叙事生成

### Subclass Configuration / 子类需配置

```python
class MyEncounterPlugin(EncounterPlugin):
    encounter_card_type: str = "my_encounter"  # Encounter card type / 遭遇卡片类型
    ws_prefix: str = "my_encounter"            # WS message prefix / WebSocket 消息前缀
    narrative_skill: str = "my_narrative"       # Narrative skill name / 叙事 Skill 名称
```

### Subclass Hooks / 子类需实现的钩子

```python
def _create_session(self, params: dict, game_state) -> EncounterSession:
    """Create session instance. params comes from frontend WS message.

    创建会话实例。params 来自前端 WS 消息。"""

def _process_action(self, action: dict, session: EncounterSession) -> dict:
    """Handle user action within session (e.g. attack, use item).

    处理用户在会话中的操作（如攻击、使用物品）。"""

def _on_session_end(self, session: EncounterSession, game_state) -> list:
    """Finalization logic when session ends (e.g. distribute rewards). Returns actions list.

    会话结束时执行收尾逻辑（结算奖励等）。返回 actions 列表。"""

def _build_narrative_prompt(self, session: EncounterSession) -> str:
    """Build narrative prompt from session content for LLM to generate summary.

    根据会话内容构建叙事提示词，用于 LLM 生成会话总结。"""
```

### Auto-provided WebSocket Routes / 自动提供的 WebSocket 路由

| Message Type / 消息类型 | Description / 说明 |
|----------|------|
| `{ws_prefix}_start_session` | Start session / 开始会话 |
| `{ws_prefix}_action` | Handle in-session action / 处理会话内操作 |
| `{ws_prefix}_finish` | End session / 结束会话 |

### Encounter Card Trigger Flow / 遭遇卡片触发流程

1. LLM calls `spawn_npcs` or `spawn_hostiles` tool / LLM 调用工具
2. Plugin returns `ModuleResult(display_type=DisplayType.ENCOUNTER, data={...})`
3. Frontend renders encounter card / 前端渲染遭遇卡片
4. Player clicks card, frontend sends `{ws_prefix}_start_session`
5. Session loop: `_process_action` handles each turn / 会话循环
6. Player/engine ends session, `_on_session_end` settles results / 结算
7. `_build_narrative_prompt` generates narrative summary / 生成叙事总结

---

## Reading World Data / 世界数据读取

Plugins access world config data via `self.world` (a `GameWorld` instance):

插件通过 `self.world`（`GameWorld` 实例）访问世界配置数据：

```python
def on_load(self) -> None:
    world = self.world

    # Read world settings / 读取世界设定
    setting = world.setting  # Full content of setting.yaml
    world_name = setting.get("world", {}).get("name", "")

    # Read character attribute schema / 读取角色属性 schema
    schema = world.get_character_schema()
    attributes = schema["attributes"]  # {attr_name: {type, default, label, ...}}

    # Read item/ability data / 读取物品/技能数据
    items = world.items          # {item_id: item_dict}
    abilities = world.abilities  # {ability_id: ability_dict}

    # Read equipment slots / 读取装备槽位
    equip_slots = world.equip_slots

    # Read world custom modules (e.g. combat.py, pricing.py) / 读取世界自定义模块
    combat_funcs = world.get_world_module("combat")

    # Read world extension configs / 读取世界扩展配置
    cultivation = world._world_extensions.get("cultivation", {})

    # Get world directory path (for loading custom config files) / 获取世界目录路径
    world_dir = world._world_dir
    if world_dir:
        config_path = Path(world_dir) / "my_config.yaml"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                my_config = yaml.safe_load(f)
```

---

## Registering a Plugin / 注册插件到引擎

### 1. Create Plugin File Structure / 创建插件文件结构

```
lingmo_engine/plugins/my_plugin/
├── __init__.py
├── plugin.py          # Plugin main class (required) / 插件主类（必须）
├── static/            # Frontend assets (optional) / 前端资源（可选）
│   ├── my_plugin.js
│   └── my_plugin.css
└── skills/            # Skill .md files (optional) / Skill 文件（可选）
    └── my_skill.md
```

### 2. Register in config.yaml / 在 config.yaml 中注册

```yaml
plugins:
  # ... other plugins / 其他插件
  - name: my_plugin
    class: MyPlugin
    module: plugins.my_plugin.plugin
    enabled: true
```

**Field descriptions / 字段说明：**

| Field / 字段 | Description / 说明 |
|------|------|
| `name` | Plugin name, must match the `name` attribute in plugin class / 插件名称 |
| `class` | Plugin class name / 插件类名 |
| `module` | Python module path (relative to lingmo_engine directory) / 模块路径 |
| `enabled` | Whether to enable; `false` skips loading / 是否启用 |

---

## Full Example: Weather Plugin / 完整示例：天气插件

A fully functional weather system plugin demonstrating the complete development workflow:

一个具备完整功能的天气系统插件，演示完整的插件开发流程：

```python
"""Weather System Plugin / 天气系统插件 — Demonstrates full plugin development."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from lingmo_engine.core.base_plugin import BasePlugin
from lingmo_engine.core.events import EventBus, PluginEvent
from lingmo_engine.core.types import (
    DisplayType,
    ModuleResult,
    ToolDefinition,
    ToolParameter,
)

_log = logging.getLogger(__name__)

WEATHER_TYPES = ["晴朗", "多云", "小雨", "暴风雨", "大雾"]


class WeatherPlugin(BasePlugin):
    name = "weather"
    version = "0.1.0"

    def __init__(self) -> None:
        self._current: str = "晴朗"
        self._history: list[dict] = []

    # ── Lifecycle / 生命周期 ──

    def on_load(self) -> None:
        """Load world weather config if exists. / 加载世界天气配置（如果存在）。"""
        world = self.world
        if world and world._world_dir:
            path = Path(world._world_dir) / "weather.yaml"
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                self._current = data.get("default_weather", "晴朗")
        _log.info("Weather plugin loaded, current: %s", self._current)

    # ── Tools / 工具 ──

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="change_weather",
                description="Change the weather of the current scene / 改变当前场景天气",
                parameters=[
                    ToolParameter(
                        name="weather",
                        type="string",
                        description=f"Target weather / 目标天气: {'/'.join(WEATHER_TYPES)}",
                        enum=WEATHER_TYPES,
                    ),
                    ToolParameter(
                        name="reason",
                        type="string",
                        required=False,
                        description="Reason for weather change (used in narrative) / 变化原因",
                    ),
                ],
            )
        ]

    def execute_tool(self, tool_name: str, params: dict) -> ModuleResult:
        if tool_name != "change_weather":
            return ModuleResult(success=False, log=f"Unknown tool: {tool_name}")

        new_weather = params.get("weather", "晴朗")
        if new_weather not in WEATHER_TYPES:
            return ModuleResult(success=False, log=f"Invalid weather: {new_weather}")

        old_weather = self._current
        self._current = new_weather
        self._history.append({"from": old_weather, "to": new_weather})

        return ModuleResult(
            success=True,
            log=f"Weather: {old_weather} → {new_weather}",
            data={
                "weather": new_weather,
                "_actions": [{"action": "send_state_update"}],
            },
        )

    # ── Prompts / 提示词 ──

    def get_system_prompt(self) -> str:
        return "Weather system active. Use change_weather to set the mood."

    def get_context_hint(self, state: dict) -> str:
        return f"Current weather / 当前天气: {self._current}"

    # ── WebSocket ──

    def handle_websocket(self, message: dict, game_state) -> dict | None:
        msg_type = message.get("type", "")
        if msg_type == "weather_get":
            return {"type": "weather_data", "weather": self._current}
        return None

    # ── Persistence / 持久化 ──

    def get_persistence_dir(self) -> str:
        return "weather"

    def save_own_state(self, slot_dir) -> None:
        self._save_plugin_json(slot_dir, "state.json", {
            "current": self._current,
            "history": self._history[-50:],  # Keep last 50 / 只保留最近 50 条
        })

    def load_own_state(self, slot_dir) -> None:
        data = self._load_plugin_json(slot_dir, "state.json")
        if data:
            self._current = data.get("current", "晴朗")
            self._history = data.get("history", [])
```

Corresponding `config.yaml` registration / 对应的配置注册：

```yaml
plugins:
  - name: weather
    class: WeatherPlugin
    module: plugins.weather.plugin
    enabled: true
```
