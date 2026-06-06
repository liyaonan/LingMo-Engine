"""MessageController — WebSocket 消息路由中枢。

入站: WebSocket JSON → MessageBus 事件
出站: 订阅 MessageBus → 序列化为 JSON → WebSocket 发送
"""
from __future__ import annotations

import logging

from fastapi import WebSocket

from lingmo_engine.core.message import Message
from lingmo_engine.core.message_bus import MessageBus, MessageEvent
from lingmo_engine.core.message_store import MessageStore

logger = logging.getLogger(__name__)


class MessageController:
    """统一消息路由中枢"""

    def __init__(self, message_bus: MessageBus, message_store: MessageStore,
                 is_locked_fn=None) -> None:
        self._bus = message_bus
        self._store = message_store
        self._is_locked_fn = is_locked_fn
        self._connections: dict[str, WebSocket] = {}  # session_id → ws
        self._current_session_id: str = ""

        # 订阅消息事件推送到前端（LLM_BUSY/LLM_IDLE 由 server.py 直接处理）
        for event in MessageEvent:
            if event in (MessageEvent.LLM_BUSY, MessageEvent.LLM_IDLE):
                continue
            self._bus.subscribe(event, self._on_message_event)

    # ── 入站处理 ──

    async def handle(self, ws: WebSocket, raw: dict) -> None:
        """WebSocket 消息总入口"""
        msg_type = raw.get("type", "")
        if msg_type == "message":
            await self._handle_message(ws, raw)

    async def _handle_message(self, ws: WebSocket, raw: dict) -> None:
        action = raw.get("action", "")
        if action == "create":
            msg_data = raw.get("message", {})
            msg = Message.from_json(msg_data)
            # user 消息在系统锁定时拒绝，避免创建新页面
            if msg.role == "user" and self._is_locked_fn and self._is_locked_fn():
                await ws.send_json({
                    "type": "llm_busy_warning",
                    "message": "当前有请求正在处理中，请等待完成后再试",
                })
                return
            if not msg.id:
                import uuid7
                msg.id = str(uuid7.uuid7())
            if not msg.session_id:
                msg.session_id = self._current_session_id
            await self._bus.publish(MessageEvent.CREATING, msg)
            await self._bus.publish(MessageEvent.CREATED, msg)
        elif action == "delete":
            msg_id = raw.get("message_id", "")
            if self._store.mark_deleted(msg_id):
                msg = self._store.load_all()
                deleted = next((m for m in msg if m.id == msg_id), None)
                await self._bus.publish(MessageEvent.DELETED, deleted or Message(
                    id=msg_id, session_id=self._current_session_id, role="narrative", status="deleted"))
            else:
                await ws.send_json({"type": "error", "message": "消息不存在，删除失败"})
        elif action == "query":
            filters = raw.get("filters", {})
            messages = self._store.query(**filters)
            await ws.send_json({
                "type": "message.query_result",
                "data": {"messages": [m.to_json() for m in messages]},
            })
        elif action == "get_meta":
            messages = self._store.load_all()
            for m in messages:
                if m.id == raw.get("message_id"):
                    await ws.send_json({
                        "type": "message.meta_result",
                        "data": m.meta.to_dict(),
                    })
                    return
            await ws.send_json({"type": "error", "message": "消息不存在"})
        elif action == "get_prompt":
            messages = self._store.load_all()
            for m in messages:
                if m.id == raw.get("message_id"):
                    await ws.send_json({
                        "type": "message.prompt_result",
                        "data": {"prompt": m.meta.raw_prompt},
                    })
                    return
            await ws.send_json({"type": "error", "message": "消息不存在"})

    # ── 出站处理 ──

    async def _on_message_event(self, event: MessageEvent, message=None, **data) -> None:
        """MessageBus 事件 → WebSocket JSON"""
        session_id = None
        if message and hasattr(message, 'session_id'):
            session_id = message.session_id

        # 构建 payload：message 序列化 + 合并 kwargs 中的事件数据（如 delta）
        if message:
            payload = message.to_json()
            payload.update(data)
        else:
            payload = data

        ws = self._connections.get(session_id) if session_id else None
        # 回退: session_id 尚未生成时使用 default 键
        if ws is None:
            ws = self._connections.get("default")
        if ws is None:
            logger.warning(
                "MessageController: no connection for session=%s (default=%s)",
                session_id, bool(self._connections.get("default")))
            # 没有 session_id 对应连接时，广播到所有连接（初始状态等场景）
            for conn in self._connections.values():
                try:
                    if conn.client_state.name == "DISCONNECTED":
                        continue
                    await conn.send_json({
                        "type": "message.event",
                        "event": event.value,
                        "data": payload,
                    })
                except RuntimeError:
                    continue
                except Exception:
                    logger.exception("MessageController: broadcast failed")
            return

        try:
            # 检查连接状态，避免向已关闭的连接发送
            if ws.client_state.name == "DISCONNECTED":
                self.remove_connection(ws)
                return
            await ws.send_json({
                "type": "message.event",
                "event": event.value,
                "data": payload,
            })
        except RuntimeError:
            # WebSocket 已关闭，静默清理
            self.remove_connection(ws)
        except Exception:
            logger.exception("MessageController: send failed")

    # ── 连接管理 ──

    def register_connection(self, session_id: str, ws: WebSocket) -> None:
        self._connections[session_id] = ws
        self._current_session_id = session_id

    def remove_connection(self, ws: WebSocket) -> None:
        to_remove = [sid for sid, w in self._connections.items() if w is ws]
        for sid in to_remove:
            del self._connections[sid]

    async def broadcast(self, payload: dict) -> None:
        """向所有活跃连接广播消息。"""
        for ws in list(self._connections.values()):
            try:
                if ws.client_state.name == "DISCONNECTED":
                    continue
                await ws.send_json(payload)
            except RuntimeError:
                continue
            except Exception:
                logger.exception("MessageController: broadcast failed")
