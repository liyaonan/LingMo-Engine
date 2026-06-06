"""事件总线 — 插件间解耦通信。

支持两种模式：
- pub/sub（emit + subscribe）：一对多广播，无返回值
- request/response（request + handle）：一对一请求，有返回值

用法示例:
    # 发布-订阅（广播）
    bus.subscribe(PluginEvent.COMBAT_ENDED, lambda data: print(data))
    bus.emit(PluginEvent.COMBAT_ENDED, {"result": "victory"})

    # 请求-响应（查数据）
    bus.handle(PluginEvent.EQUIPMENT_GET_BONUS, lambda state: compute_bonus(state))
    result = bus.request(PluginEvent.EQUIPMENT_GET_BONUS, game_state)
"""

from __future__ import annotations

import logging
from collections import defaultdict
from enum import Enum
from typing import Callable, Any

logger = logging.getLogger(__name__)

Handler = Callable[..., Any]
EventCallback = Callable[[dict], None]


class PluginEvent(str, Enum):
    """插件间 EventBus 事件类型常量。

    所有通过 EventBus 的跨插件通信必须使用此枚举成员，
    避免字符串拼写错误导致的运行时静默失败。
    """

    # ── 装备系统 ──
    EQUIPMENT_GET_BONUS = "equipment:get_bonus"
    EQUIPMENT_GET_NARRATIVE = "equipment:get_narrative"

    # ── 物品系统 ──
    ITEMS_GET_SYSTEM = "items:get_system"
    ITEMS_GET = "items:get"

    # ── 日历系统 ──
    CALENDAR_GET_INFO = "calendar:get_info"

    # ── 地图系统 ──
    MAP_GET_LOCATION_INFO = "map:get_location_info"

    # ── 装备系统扩展 ──
    EQUIPMENT_GET_SYSTEM = "equipment:get_system"

    # ── 战斗系统 ──
    COMBAT_ENDED = "combat:ended"
    COMBAT_CLEAR_ABILITY_SLOTS = "combat:clear_ability_slots"
    COMBAT_COMPUTE_DISPLAY_VALUE = "combat:compute_display_value"
    ABILITY_GENERATE = "ability:generate"
    ENCOUNTER = "encounter"

    # ── 角色系统 ──
    CHARACTER_UPDATED = "character_updated"
    CHARACTER_CREATED = "character_created"
    CHARACTER_REMOVED = "character_removed"
    CHARACTER_GET_PRESET_BIAS = "character:get_preset_bias"

    # ── 背包系统（替代 call_plugin） ──
    INVENTORY_REMOVE_ITEM = "inventory:remove_item"
    INVENTORY_REGISTER_AND_ADD = "inventory:register_and_add_item"
    INVENTORY_REGISTER_ONLY = "inventory:register_item"
    INVENTORY_GET_INVENTORY = "inventory:get_inventory"
    INVENTORY_AUTO_PUSH = "inventory.auto_push"

    def __str__(self) -> str:
        return self.value


class PluginName:
    """插件名称常量 — 用于 depends_on 声明和跨插件引用。

    避免字符串拼写错误导致依赖验证在运行时失败。

    用法:
        class MyPlugin(BasePlugin):
            name = PluginName.MY_PLUGIN
            depends_on: list[str] = [PluginName.INVENTORY, PluginName.COMBAT]
    """

    CALENDAR = "calendar"
    COMBAT = "combat"
    EVENTS = "event"
    EXPLORATION = "exploration"
    GROWTH = "growth"
    INVENTORY = "inventory"
    MAP = "map"
    CHARACTER = "character"
    CRAFTING = "crafting"


class EventBus:
    """插件间通信总线，解耦直接模块依赖。"""

    def __init__(self) -> None:
        # pub/sub: event_type -> list[callback]
        self._subscribers: dict[str, list[EventCallback]] = defaultdict(list)
        # request/response: event_type -> handler (只有最后一个注册者生效)
        self._handlers: dict[str, Handler] = {}

    # ── Pub/Sub 模式 ──────────────────────────────

    def subscribe(self, event_type: str, callback: EventCallback) -> None:
        """订阅事件。callback 接收 event_data dict。"""
        self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: EventCallback) -> None:
        """取消订阅。"""
        try:
            self._subscribers[event_type].remove(callback)
        except ValueError:
            pass

    def emit(self, event_type: str, data: dict | None = None) -> None:
        """广播事件到所有订阅者。"""
        callbacks = self._subscribers.get(event_type, [])
        payload = data or {}
        for cb in callbacks:
            try:
                cb(payload)
            except Exception:
                logger.exception("EventBus: handler failed for event '%s'", event_type)

    # ── Request/Response 模式 ─────────────────────

    def handle(self, event_type: str, handler: Handler) -> None:
        """注册请求处理器（同类型只保留最后一个）。"""
        if event_type in self._handlers:
            logger.warning("EventBus: 处理器 %s 被覆盖", event_type)
        self._handlers[event_type] = handler

    def remove_handler(self, event_type: str) -> None:
        """移除请求处理器。"""
        self._handlers.pop(event_type, None)

    def request(self, event_type: str, *args, **kwargs) -> Any:
        """发送请求并等待响应。无处理器时返回 None。"""
        handler = self._handlers.get(event_type)
        if handler is None:
            logger.debug("EventBus: no handler for request '%s'", event_type)
            return None
        try:
            return handler(*args, **kwargs)
        except Exception:
            logger.exception("EventBus: handler failed for request '%s'", event_type)
            raise
