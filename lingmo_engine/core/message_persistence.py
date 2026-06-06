"""消息持久化服务 — 监听 MessageBus 事件并写入 MessageStore。

从 GameMaster 解耦，遵循单一职责原则。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lingmo_engine.core.message_bus import MessageBus, MessageEvent
    from lingmo_engine.core.message_store import MessageStore
    from lingmo_engine.core.message import Message

logger = logging.getLogger(__name__)


class MessagePersistenceService:
    """监听 MessageBus 的消息生命周期事件，将消息持久化到 MessageStore JSONL。"""

    def __init__(self, message_bus: "MessageBus", message_store: "MessageStore"):
        self._bus = message_bus
        self._store = message_store
        self._subscribed = False

    def start(self) -> None:
        """订阅消息事件，开始持久化。"""
        if self._subscribed:
            return
        from lingmo_engine.core.message_bus import MessageEvent

        self._bus.subscribe(MessageEvent.CREATED, self._on_message_persist)
        self._bus.subscribe(MessageEvent.UPDATED, self._on_message_persist)
        self._bus.subscribe(MessageEvent.DELETED, self._on_message_persist)
        self._subscribed = True
        logger.info("MessagePersistenceService started")

    def stop(self) -> None:
        """取消订阅（用于测试或服务关闭）。"""
        if not self._subscribed:
            return
        from lingmo_engine.core.message_bus import MessageEvent

        self._bus.unsubscribe(MessageEvent.CREATED, self._on_message_persist)
        self._bus.unsubscribe(MessageEvent.UPDATED, self._on_message_persist)
        self._bus.unsubscribe(MessageEvent.DELETED, self._on_message_persist)
        self._subscribed = False

    async def _on_message_persist(self, event: "MessageEvent", msg: "Message", **kwargs) -> None:
        """消息事件回调：根据事件类型执行对应的持久化操作。"""
        from lingmo_engine.core.message_bus import MessageEvent

        try:
            if event == MessageEvent.CREATED:
                self._store.append(msg)
            elif event == MessageEvent.UPDATED:
                self._store.update(msg.id, msg.content)
            elif event == MessageEvent.DELETED:
                self._store.mark_deleted(msg.id)
        except Exception:
            logger.exception(
                "MessagePersistenceService: 持久化失败 event=%s", event.value
            )
