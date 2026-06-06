"""Action 注册表 — 允许插件注册自定义 action handler。

替代 server.py 中硬编码的 if/elif 链，让框架 action 系统可扩展。
插件可通过 EventBus 或 PluginRegistry 注册新的 action 类型处理器。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Awaitable, TYPE_CHECKING

if TYPE_CHECKING:
    from lingmo_engine.core.game_state import GameState
    from lingmo_engine.core.message_bus import MessageBus

logger = logging.getLogger(__name__)

# Action handler 签名: async def handler(action: dict, ctx: ActionContext) -> None
ActionHandler = Callable[["ActionContext", dict], Awaitable[None]]


@dataclass
class ActionContext:
    """action handler 的执行上下文，持有所有需要的依赖引用。"""

    state: "GameState"
    message_bus: "MessageBus"
    websocket: object  # WebSocket 连接
    session_id: str = ""
    page_id: str = ""
    run_narrative: Callable | None = None  # async (action: dict) -> None


class ActionRegistry:
    """可扩展的 action 处理注册表。

    内置 8 种框架 action，插件可通过 register() 添加自定义 handler。
    """

    def __init__(self):
        self._handlers: dict[str, ActionHandler] = {}
        self._register_defaults()

    def register(self, action_type: str, handler: ActionHandler) -> None:
        """注册一个 action 类型的处理器（覆盖已有类型会报警）。"""
        if action_type in self._handlers:
            logger.warning(
                "ActionRegistry: 覆盖已注册的 action '%s' (原: %s → 新: %s)",
                action_type,
                getattr(self._handlers[action_type], "__name__", "unknown"),
                getattr(handler, "__name__", "unknown"),
            )
        self._handlers[action_type] = handler
        logger.debug("ActionRegistry: 注册 action '%s'", action_type)

    def get_handler(self, action_type: str) -> ActionHandler | None:
        """获取指定 action 类型的处理器。"""
        return self._handlers.get(action_type)

    async def execute(self, action: dict, ctx: ActionContext) -> None:
        """根据 action dict 的 'action' 字段查表并执行对应 handler。"""
        action_type = action.get("action", "")
        handler = self._handlers.get(action_type)
        if handler is None:
            logger.warning("ActionRegistry: 未知 action 类型 '%s'，已忽略", action_type)
            return
        await handler(ctx, action)

    async def execute_all(self, actions: list[dict], ctx: ActionContext) -> None:
        """依次执行一组 actions。"""
        for action in actions:
            await self.execute(action, ctx)

    # ── 内置 action 处理器 ──────────────────────

    def _register_defaults(self) -> None:
        self.register("update_player", _handle_update_player)
        self.register("add_items", _handle_add_items)
        self.register("remove_items", _handle_remove_items)
        self.register("publish_message", _handle_publish_message)
        self.register("generate_narrative", _handle_generate_narrative)
        self.register("save_state", _handle_save_state)
        self.register("send_state_update", _handle_send_state_update)
        self.register("clear_scene_enemies", _handle_clear_scene_enemies)


# ── 内置 action handler 实现 ────────────────────


async def _handle_update_player(ctx: ActionContext, action: dict) -> None:
    ctx.state.update_player(**action.get("updates", {}))


async def _handle_add_items(ctx: ActionContext, action: dict) -> None:
    for item in action.get("items", []):
        ctx.state.add_player_item(
            item.get("item_id", ""),
            item.get("quantity", 1),
        )


async def _handle_remove_items(ctx: ActionContext, action: dict) -> None:
    for item in action.get("items", []):
        ctx.state.remove_player_item(
            item.get("item_id", ""),
            item.get("quantity", 1),
        )


async def _handle_publish_message(ctx: ActionContext, action: dict) -> None:
    import uuid7
    from lingmo_engine.core.message import Message
    from lingmo_engine.core.message_bus import MessageEvent

    msg_data = action.get("message", {})
    msg = Message(
        id=str(uuid7.uuid7()),
        session_id=ctx.session_id or "default",
        page_id=ctx.page_id,
        role=msg_data.get("role", "system"),
        content=msg_data.get("content", ""),
        content_blocks=msg_data.get("content_blocks", []),
    )
    await ctx.message_bus.publish(MessageEvent.CREATED, msg)


async def _handle_generate_narrative(ctx: ActionContext, action: dict) -> None:
    if ctx.run_narrative is None:
        logger.warning("ActionContext.run_narrative 未注入，无法生成叙事")
        return
    await ctx.run_narrative(action)


async def _handle_save_state(ctx: ActionContext, action: dict) -> None:
    ctx.state.save()
    # ActionContext 没有 plugins 引用，无法调用 save_plugins()
    # 但 LLM 回合结束时的 save 在 game_master 中已包含 save_plugins
    # 此处的 save_state 是动作中间的轻量保存，不刷新插件状态


async def _handle_send_state_update(ctx: ActionContext, action: dict) -> None:
    from fastapi import WebSocket
    ws = ctx.websocket
    if ws is not None:
        await ws.send_json({
            "type": "state_update",
            "data": ctx.state.data,
        })


async def _handle_clear_scene_enemies(ctx: ActionContext, action: dict) -> None:
    ctx.state.clear_scene_enemies()
