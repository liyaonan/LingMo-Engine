"""MessageBus — 消息事件发布/订阅总线。

消息生命周期事件通过此总线分发给所有订阅者（MessageStore、WebSocket、GameMaster、插件）。
单个 handler 异常不影响其他 handler。依序执行（非并发），保证确定性。
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from enum import Enum
from typing import Callable, Any

logger = logging.getLogger(__name__)

# Handler: (event, message, **kwargs) -> Any
MessageHandler = Callable[..., Any]


class MessageEvent(Enum):
    """消息生命周期事件 + LLM 状态事件"""
    CREATING     = "message.creating"
    CREATED      = "message.created"
    UPDATING     = "message.updating"
    UPDATED      = "message.updated"
    DELETING     = "message.deleting"
    DELETED      = "message.deleted"
    STREAMING    = "message.streaming"
    STREAM_END   = "message.stream_end"
    STREAM_DISCARD = "message.stream_discard"
    RETRACTED    = "message.retracted"
    LLM_BUSY          = "llm.busy"
    LLM_IDLE          = "llm.idle"
    LLM_LOOP_COMPLETE = "llm.loop_complete"
    RUMOR        = "message.rumor"       # P3 传闻
    INTERRUPT    = "message.interrupt"   # P4/P5 打断


class MessageBus:
    """发布/订阅事件总线 — 消息系统事件中枢。

    订阅者按注册顺序依序执行，单个异常不影响后续。
    """

    def __init__(self) -> None:
        self._subscribers: dict[MessageEvent, list[MessageHandler]] = defaultdict(list)
        self._plugin_subscriptions: dict[str, dict] = {}

    def subscribe(self, event: MessageEvent, handler: MessageHandler) -> None:
        """注册事件处理器"""
        self._subscribers[event].append(handler)

    def unsubscribe(self, event: MessageEvent, handler: MessageHandler) -> None:
        """取消注册"""
        try:
            self._subscribers[event].remove(handler)
        except ValueError:
            pass

    def subscribe_plugin(self, plugin_name: str,
                         events: list[MessageEvent],
                         handler: MessageHandler) -> None:
        """插件注册入口。带插件名用于追踪和卸载。"""
        # 先移除旧订阅的 handler，防止重复
        if plugin_name in self._plugin_subscriptions:
            old_subs = self._plugin_subscriptions[plugin_name]
            for event, old_handler in old_subs.items():
                try:
                    self._subscribers[event].remove(old_handler)
                except ValueError:
                    pass
        for event in events:
            self._subscribers[event].append(handler)
        self._plugin_subscriptions[plugin_name] = {e: handler for e in events}

    def unsubscribe_plugin(self, plugin_name: str) -> None:
        """移除插件的所有订阅"""
        subscriptions = self._plugin_subscriptions.pop(plugin_name, {})
        for event, handler in subscriptions.items():
            try:
                self._subscribers[event].remove(handler)
            except ValueError:
                pass

    async def publish(self, event: MessageEvent, message=None, **kwargs) -> None:
        """异步发布事件。所有处理器依序执行，单个异常不会中断链。"""
        handlers = self._subscribers.get(event, [])
        for handler in handlers:
            try:
                result = handler(event, message, **kwargs)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception(
                    "MessageBus: handler failed for event '%s', handler=%s",
                    event.value, getattr(handler, "__name__", handler)
                )
