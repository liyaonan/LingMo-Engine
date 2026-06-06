from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, UploadFile
from fastapi.staticfiles import StaticFiles

from lingmo_engine.core.action_registry import ActionRegistry, ActionContext
from lingmo_engine.core.config import EngineConfig
from lingmo_engine.core.events import PluginEvent
from lingmo_engine.core.gamemaster import GameMaster
from lingmo_engine.core.types import Action
from lingmo_engine.web.controllers import (
    ConfigController, GameFlowController,
)
from lingmo_engine.web.controllers.message_controller import MessageController
from lingmo_engine.core.message_bus import MessageBus, MessageEvent
from lingmo_engine.core.message_store import MessageStore

logger = logging.getLogger(__name__)


def _suppress_benign_connection_errors(loop, context):
    """抑制 Windows 下客户端断开时的 ConnectionResetError 日志噪音。

    Windows Proactor 事件循环在客户端突然断开时会尝试 socket.shutdown()，
    导致 ConnectionResetError 被抛到传输层，不在用户代码 try/except 范围内。
    此处理器将其降级为 DEBUG 级别日志。
    """
    exception = context.get("exception")
    if isinstance(exception, ConnectionResetError):
        logger.debug(
            "连接被远端重置（可忽略）: %s",
            context.get("message", ""),
        )
        return
    # 其他异常走默认处理
    loop.default_exception_handler(context)


class GameServer:
    """游戏服务器 - 薄调度层，将WebSocket消息路由到对应控制器。

    动态挂载插件静态资源路由和世界主题路由。
    """

    def __init__(self, config: EngineConfig, gamemaster: GameMaster,
                 message_bus: MessageBus = None, message_store: MessageStore = None):
        self.config = config
        self.gamemaster = gamemaster
        self._message_bus = message_bus
        self._message_store = message_store
        self.app = FastAPI(title="LingMo Engine")

        @self.app.on_event("startup")
        async def _install_connection_error_handler():
            """在事件循环启动后注入异常处理器，抑制 Windows 下连接重置噪音。"""
            import asyncio
            loop = asyncio.get_running_loop()
            loop.set_exception_handler(_suppress_benign_connection_errors)
        self._connections: list[WebSocket] = []
        self._plugin_css_links: list[str] = []
        self._plugin_js_links: list[str] = []
        self._plugin_modules_script: str = ""
        self._theme_css_link: str = ""
        # UI 组件注册表（从插件收集，按类型分组）
        self._ui_components: dict[str, list] = gamemaster.plugins.get_all_ui_components()

        # 初始化消息处理器
        from lingmo_engine.web.controllers import CreationController
        from lingmo_engine.services import (
            GameService, ConfigService, CharacterService,
            InventoryService, MapService, CombatService,
        )

        # 创建服务层
        services = {
            "game": GameService(gamemaster),
            "config": ConfigService(gamemaster, config),
            "character": CharacterService(gamemaster, gamemaster.world),
            "inventory": InventoryService(gamemaster),
            "map": MapService(gamemaster),
            "combat": CombatService(gamemaster),
        }
        self._services = services
        self._game_svc = services["game"]

        self._controllers = [
            GameFlowController(services=services, config=config),
            ConfigController(services=services, config=config),
            CreationController(services=services, config=config),
        ]
        self._handlers: dict[str, callable] = {}
        for ctrl in self._controllers:
            self._handlers.update(ctrl.get_handlers())

        # 注册角色系统 WebSocket 处理器
        self._handlers["get_character"] = self._handle_get_character
        self._handlers["scene_npc_names"] = self._handle_scene_npc_names

        self._message_controller = None
        if message_bus and message_store:
            self._message_controller = MessageController(
                message_bus, message_store,
                is_locked_fn=lambda: self._game_svc.is_locked(),
            )
            self._game_svc.set_message_controller(self._message_controller)

        # 初始化可扩展 Action 注册表（插件可注册自定义 action handler）
        self._action_registry = ActionRegistry()

        # 订阅 LLM 状态事件，向前端推送 input_state 控制输入框禁用
        if message_bus:
            message_bus.subscribe(MessageEvent.LLM_BUSY, self._on_llm_busy)
            message_bus.subscribe(MessageEvent.LLM_IDLE, self._on_llm_idle)

        self._collect_theme_assets()
        self._setup_routes()

    def _collect_theme_assets(self) -> None:
        """收集世界主题 CSS（后于 base.css 和插件 CSS 加载，确保覆盖变量）。"""
        theme_dir = self._game_svc.world.get_theme_dir()
        if theme_dir:
            self._theme_css_link = '<link rel="stylesheet" href="/static/theme/theme.css">'

    async def _execute_actions(self, ws: WebSocket, actions: list[Action]) -> None:
        """执行 _actions 列表中的框架操作（通过可扩展 ActionRegistry 分发）。"""
        if not actions:
            return

        ctx = ActionContext(
            state=self._game_svc.state,
            message_bus=self._message_bus,
            websocket=ws,
            session_id=self._game_svc.session_id or "default",
            page_id=getattr(self.gamemaster, "_last_page_id", ""),
            run_narrative=self.gamemaster.run_narrative_action,
        )
        await self._action_registry.execute_all(actions, ctx)

    def _setup_routes(self) -> None:
        # 定义禁止缓存的静态文件类（用于开发阶段）
        import starlette.types

        class NoCacheStaticFiles(StaticFiles):
            async def __call__(self, scope, receive, send):
                async def send_with_header(message):
                    if message["type"] == "http.response.start":
                        headers = dict(message.get("headers", []))
                        headers[b"cache-control"] = b"no-cache, no-store, must-revalidate"
                        message["headers"] = list(headers.items())
                    await send(message)
                await super().__call__(scope, receive, send_with_header)

        # 先挂载插件静态资源（必须在 /static 通用挂载之前，否则路由被吞）
        for name, static_dir in self._game_svc.plugins.get_all_static_dirs():
            route_path = f"/static/plugins/{name}"
            self.app.mount(route_path, NoCacheStaticFiles(directory=static_dir), name=f"plugin_{name}_static")
            logger.info("Mounted plugin static: %s -> %s", route_path, static_dir)

        # 挂载世界主题
        theme_dir = self._game_svc.world.get_theme_dir()
        if theme_dir:
            self.app.mount("/static/theme", NoCacheStaticFiles(directory=theme_dir), name="world_theme")
            logger.info("Mounted theme static: /static/theme -> %s", theme_dir)

        # 最后挂载引擎静态文件（catch-all，优先级最低）
        static_dir = Path(__file__).parent / "static"
        if static_dir.exists():
            self.app.mount("/static", NoCacheStaticFiles(directory=str(static_dir)), name="static")

        @self.app.get("/")
        async def index():
            from fastapi.responses import HTMLResponse
            html_path = Path(__file__).parent / "static" / "frontend-v2" / "title.html"
            if html_path.exists():
                html = html_path.read_text(encoding="utf-8")
                html = html.replace("<!-- THEME_CSS -->", self._theme_css_link)
                html = self._inject_ui_labels(html)
                world_setting = self._game_svc.world.setting.get("world", {})
                world_title = world_setting.get("title") or world_setting.get("name", "LingMo Engine")
                world_desc = world_setting.get("description", "").strip().replace("\n", "")
                html = html.replace("{{WORLD_NAME}}", world_title)
                html = html.replace("{{WORLD_DESC}}", world_desc[:30])
                return HTMLResponse(content=html, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
            return HTMLResponse(
                content="<html><body><h1>LingMo Engine</h1><p>标题页面未找到</p></body></html>",
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )

        @self.app.get("/game")
        async def game_page(request: Request = None):
            from fastapi.responses import HTMLResponse
            use_v1 = False
            if request:
                use_v1 = request.query_params.get("v1") == "1"
            if use_v1:
                html = self._build_game_html("game")
                return HTMLResponse(content=html, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
            html_path = Path(__file__).parent / "static" / "frontend-v2" / "index.html"
            if html_path.exists():
                html = html_path.read_text(encoding="utf-8")
                html = html.replace("<!-- THEME_CSS -->", self._theme_css_link)
                html = html.replace("<!-- PLUGIN_MODULES -->", self._plugin_modules_script)
                html = self._inject_ui_labels(html)
                return HTMLResponse(content=html, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
            html = self._build_game_html("game")
            return HTMLResponse(content=html, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

        @self.app.get("/creation")
        async def creation_page():
            from fastapi.responses import HTMLResponse
            # 优先从 world 目录读取创建页面
            world_dir = getattr(self._game_svc.world, '_world_dir', None)
            if world_dir:
                html_path = Path(world_dir) / "character_creation" / "creation.html"
                if html_path.exists():
                    html = html_path.read_text(encoding="utf-8")
                    html = html.replace("<!-- THEME_CSS -->", self._theme_css_link)
                    html = self._inject_ui_labels(html)
                    return HTMLResponse(
                        content=html,
                        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
                    )
            # 回退到 v2 内置创建页面
            html_path = Path(__file__).parent / "static" / "frontend-v2" / "creation.html"
            if html_path.exists():
                html = html_path.read_text(encoding="utf-8")
                html = html.replace("<!-- THEME_CSS -->", self._theme_css_link)
                html = self._inject_ui_labels(html)
                return HTMLResponse(
                    content=html,
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
                )
            return HTMLResponse(
                content="<h1>角色创建页面未配置</h1><p>当前世界未提供 character_creation/creation.html，且内置创建页面未找到。</p>",
                status_code=404,
            )

        @self.app.get("/api/export")
        async def export_save(slot: str):
            """下载存档 ZIP。"""
            from fastapi.responses import FileResponse
            sm = getattr(self._game_svc.state, 'save_manager', None)
            if sm is None:
                return {"error": "存档管理器未初始化"}
            try:
                zip_path = sm.export_slot(slot)
                return FileResponse(
                    zip_path,
                    media_type="application/zip",
                    filename=zip_path.name,
                    headers={"Cache-Control": "no-cache"},
                )
            except FileNotFoundError:
                return {"error": f"存档不存在：{slot}"}

        @self.app.post("/api/import")
        async def import_save(file: UploadFile):
            """上传并导入存档 ZIP。"""
            sm = getattr(self._game_svc.state, 'save_manager', None)
            if sm is None:
                return {"success": False, "error": "存档管理器未初始化"}
            try:
                zip_data = await file.read()
                result = sm.import_slot(zip_data)
                return {"success": True, "slot_id": result["slot_id"], "meta": result["meta"]}
            except ValueError as e:
                return {"success": False, "error": str(e)}
            except Exception as e:
                logger.exception("Import failed")
                return {"success": False, "error": f"导入失败：{e}"}

        @self.app.websocket("/ws")
        async def websocket_endpoint(ws: WebSocket):
            await ws.accept()
            self._connections.append(ws)
            logger.info("Client connected. Total: %d", len(self._connections))

            # 从 state 恢复 session_id
            saved_id = self._game_svc.state.data.get("__session_id__", "")
            if saved_id:
                self._game_svc.set_session_id(saved_id)
            session_id = self._game_svc.session_id or 'default'
            if self._message_controller:
                self._message_controller.register_connection(session_id, ws)

            try:
                # 初始状态推送
                await ws.send_json({
                    "type": "state_update",
                    "data": self._game_svc.build_state(),
                })

                schema = self._game_svc.world.get_attributes_schema()
                if schema.get("attributes"):
                    await ws.send_json({
                        "type": "attributes_schema",
                        "data": schema,
                    })

                # 推送世界配置的 ui_labels（前端 i18n 覆盖）
                ui_labels = self._game_svc.world.setting.get("ui_labels", {})
                if ui_labels:
                    await ws.send_json({
                        "type": "ui_labels",
                        "labels": ui_labels,
                    })

                # 推送当前场景 NPC 名字（刷新后叙事区仍可高亮）
                try:
                    names = self._collect_scene_npc_names(self._get_player_location())
                    if names:
                        await ws.send_json({
                            "type": "scene_npc_names",
                            "names": names,
                        })
                except Exception:
                    logger.debug("WebSocket 连接时推送 scene_npc_names 失败", exc_info=True)

                sm = getattr(self._game_svc.state, 'save_manager', None)
                if sm:
                    saves = sm.list_saves()
                else:
                    saves = self._game_svc.list_saves()
                await ws.send_json({
                    "type": "save_list",
                    "data": {"saves": saves},
                })

                # 推送历史消息（F5 刷新后重建页面，跳过已删除消息）
                session_id = self._game_svc.session_id
                if session_id and self._message_store:
                    messages = self._message_store.load_all()
                    for m in messages:
                        if m.status == "deleted":
                            continue
                        await ws.send_json({
                            "type": "message.event",
                            "event": "message.created",
                            "data": m.to_json(),
                        })

                while True:
                    raw = await ws.receive_text()
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        await ws.send_json({"type": "error", "message": "Invalid JSON"})
                        continue

                    msg_type = msg.get("type", "")

                    # retry_page: Page 重试（回滚状态 + 重新发送）
                    if msg_type == "retry_page":
                        result = await self.gamemaster.handle_retry_page(msg.get("page_id", ""))
                        if result["success"]:
                            # 只发给请求的客户端，避免多标签页重复发送
                            await ws.send_json({
                                "type": "page_retry",
                                "page_id": msg.get("page_id", ""),
                                "user_input": result["user_input"],
                            })
                        else:
                            await ws.send_json({"type": "error", "message": result.get("error", "重试失败")})
                    # message 类型走 MessageController
                    elif msg_type == "message" and self._message_controller:
                        await self._message_controller.handle(ws, msg)
                    else:
                        handler = self._handlers.get(msg_type)
                        if handler:
                            await handler(ws, msg)
                        else:
                            # 插件 WebSocket 消息路由
                            result = self._game_svc.plugins.route_websocket(
                                msg, self._game_svc.state
                            )
                            if result:
                                actions = result.pop("_actions", None)
                                await ws.send_json(result)
                                if actions:
                                    await self._execute_actions(ws, actions)
                            else:
                                logger.warning("Unknown message type: %s", msg_type)

            except (WebSocketDisconnect, RuntimeError):
                self._connections.remove(ws)
                if self._message_controller:
                    self._message_controller.remove_connection(ws)
                self._game_svc.cancel_pending()
                logger.info("Client disconnected. Total: %d", len(self._connections))

    async def _on_llm_busy(self, event, message=None, **kwargs) -> None:
        """LLM 开始处理，通知前端禁用输入框。"""
        for ws in self._connections:
            try:
                await ws.send_json({"type": "input_state", "enabled": False})
                if self._game_svc.summary_pending:
                    await ws.send_json({"type": "llm_busy_warning", "message": "正在总结记忆..."})
            except Exception:
                pass

    async def _on_llm_idle(self, event, message=None, **kwargs) -> None:
        """LLM 处理完成，通知前端启用输入框并推送最新状态。"""
        # 系统锁定时跳过全部推送（防止迭代间隙推送不完整状态）
        if self._game_svc.is_locked():
            return

        state_data = self._game_svc.build_state()
        for ws in self._connections:
            try:
                await ws.send_json({"type": "input_state", "enabled": True})
                await ws.send_json({
                    "type": "state_update",
                    "data": state_data,
                })
            except Exception:
                pass

        # 推送插件待推送状态
        try:
            inv_state = self._game_svc.plugins.bus.request(
                PluginEvent.INVENTORY_AUTO_PUSH, game_state=self._game_svc.state
            )
            if inv_state:
                for ws in self._connections:
                    try:
                        await ws.send_json(inv_state)
                    except Exception:
                        pass
        except Exception:
            pass

        # 推送事件面板数据
        try:
            events_result = self._game_svc.plugins.route_websocket(
                {"type": "get_events"}, self._game_svc.state
            )
            if events_result and events_result.get("events"):
                for ws in self._connections:
                    try:
                        await ws.send_json(events_result)
                    except Exception:
                        pass
        except Exception:
            pass

        # 叙事完成后推送当前场景 NPC 名字列表（供叙事区高亮）
        try:
            names = self._collect_scene_npc_names(self._get_player_location())
            if names:
                for ws in self._connections:
                    try:
                        await ws.send_json({
                            "type": "scene_npc_names",
                            "names": names,
                        })
                    except Exception:
                        pass
        except Exception:
            logger.debug("推送 scene_npc_names 失败", exc_info=True)

    def _get_character_manager(self):
        """获取 CharacterManager（优先从 state，回退到 world）。"""
        cm = getattr(self._game_svc.state, 'character_manager', None)
        if cm is None:
            cm = getattr(self.gamemaster.world, '_char_manager', None)
        return cm

    def _get_player_location(self) -> str:
        """获取玩家当前位置，失败时返回空字符串。"""
        cm = self._get_character_manager()
        if cm:
            try:
                return cm.player.location or ""
            except Exception:
                pass
        return ""

    def _collect_scene_npc_names(self, location: str) -> list[dict]:
        """收集指定地点的 NPC 名字列表。"""
        if not location:
            return []
        cm = self._get_character_manager()
        if not cm:
            logger.debug("_collect_scene_npc_names: CharacterManager 未找到")
            return []
        chars = cm.list_by_location(location)
        result = [{"id": n.id, "name": n.name}
                  for n in chars
                  if getattr(n, 'char_type', None)
                  and n.char_type.value in ("npc",)
                  and n.id != 0]
        logger.debug("scene_npc_names: location=%s, found=%d", location, len(result))
        return result

    async def _handle_get_character(self, ws: WebSocket, msg: dict) -> None:
        char_id = msg.get("id", 0)
        result = self._services["character"].get_character_detail(char_id)
        if result is None:
            await ws.send_json({"type": "error", "message": f"角色不存在: {char_id}"})
            return
        await ws.send_json({"type": "character_data", **result})

    async def _handle_scene_npc_names(self, ws: WebSocket, msg: dict) -> None:
        """发送当前场景 NPC 的名字列表，供叙事区做名字高亮。"""
        location = msg.get("location", "")
        names = self._collect_scene_npc_names(location)
        await ws.send_json({"type": "scene_npc_names", "names": names})

    def _inject_ui_labels(self, html: str) -> str:
        """将世界配置的 ui_labels 注入为内联脚本，确保页面加载时 i18n 即有正确翻译。"""
        import json
        ui_labels = self._game_svc.world.setting.get("ui_labels", {})
        if not ui_labels:
            return html.replace("<!-- UI_LABELS_INJECTION -->", "")
        injection = f'<script>window.__UI_LABELS={json.dumps(ui_labels, ensure_ascii=False)};</script>'
        return html.replace("<!-- UI_LABELS_INJECTION -->", injection)

    def _build_game_html(self, page: str) -> str:
        """读取 HTML 文件并注入动态资源标签。仅用于 v1 回退路径。"""
        html_path = Path(__file__).parent / "static" / f"{page}.html"
        if not html_path.exists():
            return "<html><body><h1>Page not found</h1></body></html>"

        html = html_path.read_text(encoding="utf-8")

        replacements = {
            "<!-- PLUGIN_CSS -->": "\n    ".join(self._plugin_css_links),
            "<!-- PLUGIN_JS -->": "\n    ".join(self._plugin_js_links),
            "<!-- PLUGIN_MODULES -->": self._plugin_modules_script,
            "<!-- THEME_CSS -->": self._theme_css_link,
        }
        for marker, content in replacements.items():
            html = html.replace(marker, content)

        return html

    def run(self) -> None:
        import uvicorn
        uvicorn.run(
            self.app,
            host=self.config.server.host,
            port=self.config.server.port,
            log_level="info",
        )
