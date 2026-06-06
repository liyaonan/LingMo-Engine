"""游戏流程控制器 - 处理叙事流程、存档、新游戏等WebSocket消息"""
from __future__ import annotations

import logging
import shutil

from fastapi import WebSocket

from lingmo_engine.core.events import PluginEvent
from lingmo_engine.web.controllers.base_controller import BaseController

logger = logging.getLogger(__name__)


class GameFlowController(BaseController):
    """处理玩家输入、存档加载、新游戏、初始状态推送"""

    def __init__(self, *, services: dict, config=None):
        super().__init__(services=services, config=config)

    @staticmethod
    def _safe_copy_slot(source_dir, autosave_dir) -> None:
        """两阶段安全复制 source_dir 到 autosave_dir。

        防止中途失败损坏 autosave：
        1. 复制到 autosave.tmp（临时目录）
        2. autosave → autosave.bak（备份旧数据）
        3. autosave.tmp → autosave（原子替换）
        4. 删除 autosave.bak
        任何步骤失败都会回滚，确保 autosave 目录始终有效。
        """
        import os
        tmp_dir = autosave_dir.parent / (autosave_dir.name + ".tmp")
        bak_dir = autosave_dir.parent / (autosave_dir.name + ".bak")
        # 清理上次可能残留的临时目录
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
        try:
            shutil.copytree(source_dir, tmp_dir)
        except Exception:
            # 复制失败，tmp_dir 可能不完整，清理后抛出
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)
            raise
        try:
            # 备份旧 autosave（使用 shutil.move 替代 rename，跨驱动器安全）
            if autosave_dir.exists():
                if bak_dir.exists():
                    shutil.rmtree(bak_dir, ignore_errors=True)
                shutil.move(str(autosave_dir), str(bak_dir))
            # 原子替换
            shutil.move(str(tmp_dir), str(autosave_dir))
        except Exception:
            # 替换失败 — 尝试回滚：恢复 .bak 为 autosave
            logger.exception("安全复制替换阶段失败，尝试回滚")
            if not autosave_dir.exists() and bak_dir.exists():
                try:
                    shutil.move(str(bak_dir), str(autosave_dir))
                    logger.info("已回滚 autosave 目录")
                except Exception:
                    logger.critical(
                        "autosave 回滚失败！autosave 目录可能已损坏: %s", autosave_dir
                    )
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)
            raise
        # 成功 — 清理备份
        if bak_dir.exists():
            shutil.rmtree(bak_dir, ignore_errors=True)

    def get_handlers(self) -> dict:
        return {
            "player_input": self._handle_player_input,
            "load_save": self._handle_load_save,
            "new_game": self._handle_new_game,
            "list_saves": self._handle_list_saves,
            "save_game": self._handle_save_game,
            "delete_save": self._handle_delete_save,
            "rename_save": self._handle_rename_save,
            "export_save": self._handle_export_save,
        }

    async def _handle_player_input(self, ws: WebSocket, msg: dict) -> None:
        content = msg.get("content", "")
        text = content.strip()
        if not text:
            return

        # 系统锁定时拒绝新请求，避免创建新页面
        if self.game_svc.is_locked():
            await ws.send_json({
                "type": "llm_busy_warning",
                "message": "当前有请求正在处理中，请等待完成后再试",
            })
            return

        # /debug 拦截：不经过 LLM，直接执行
        if text == "/debug" or text.startswith("/debug "):
            if not self.config.debug:
                await ws.send_json({
                    "type": "system",
                    "content": "Debug 模式未启用",
                })
                await ws.send_json({"type": "input_state", "enabled": True})
                await ws.send_json({
                    "type": "state_update",
                    "data": self.game_svc.build_state(),
                })
                return
            try:
                from lingmo_engine.web.debug_handler import DebugHandler
                ctx = self.game_svc.debug_context()
                handler = DebugHandler(config=self.config, **ctx)
                await handler.handle(content, ws)
            except Exception:
                logger.exception("DebugHandler 执行失败")
                await ws.send_json({
                    "type": "error",
                    "message": "Debug 命令处理失败",
                })
            # debug 不走 LLM，需手动发送 input_state 解锁输入框
            await ws.send_json({"type": "input_state", "enabled": True})
            await ws.send_json({
                "type": "state_update",
                "data": self.game_svc.build_state(),
            })
            return

        try:
            await self.game_svc.process_input(content)
        except Exception as e:
            logger.exception("Error processing input")
            await ws.send_json({"type": "error", "message": str(e)})

    async def _handle_load_save(self, ws: WebSocket, msg: dict) -> None:
        slot_id = msg.get("slot", "autosave")
        sm = getattr(self.game_svc.state, 'save_manager', None)
        if sm is None:
            await ws.send_json({"type": "error", "message": "存档管理器未初始化"})
            return
        if not sm.slot_exists(slot_id):
            await ws.send_json({"type": "error", "message": f"存档不存在：{slot_id}"})
            return

        with self.game_svc.paused_auto_save():
            # 非 autosave 槽位：两阶段安全复制到 autosave 再加载，保持活跃槽位始终为 autosave
            if slot_id != "autosave":
                source_dir = sm.resolve_slot_path(slot_id)
                autosave_dir = sm.resolve_slot_path("autosave")
                self._safe_copy_slot(source_dir, autosave_dir)
                meta = sm.read_meta("autosave")
                meta["slot_id"] = "autosave"
                sm.write_meta("autosave", meta)
                logger.info("加载槽位 %s → 已安全复制到 autosave", slot_id)

            old_dir = self.game_svc.state.slot_dir
            new_dir = sm.resolve_slot_path("autosave")
            self.game_svc.state.set_slot_dir(new_dir)
            self.game_svc.store_set_slot_dir(str(new_dir))
            self.game_svc.memory_set_slot_dir(str(new_dir))
            self.game_svc.store_init_session()

            # 确保 CharacterManager 已初始化（服务器重启后 state._character_manager 为 None，
            # 导致 state.load() 跳过 NPC 加载，world 的默认角色会覆盖存档中的主角）
            if self.game_svc.state.character_manager is None:
                world_cm = getattr(self.game_svc.world, '_char_manager', None)
                if world_cm:
                    self.game_svc.state.character_manager = world_cm

            loaded = self.game_svc.state.load()
            if not loaded:
                # 加载失败：回滚 slot_dir 到之前的目录
                self.game_svc.state.set_slot_dir(old_dir)
                self.game_svc.store_set_slot_dir(str(old_dir))
                self.game_svc.memory_set_slot_dir(str(old_dir))
                await ws.send_json({"type": "error", "message": f"存档加载失败：{slot_id}"})
                return

            saved_sid = self.game_svc.state.get_session_id()
            if saved_sid:
                self.game_svc.set_session_id(saved_sid)
            self.game_svc.clear_history()

            # 更新 MessageController 的连接注册，确保后续 LLM 推送使用新 session_id
            mc = self.game_svc.message_controller
            if mc:
                mc.register_connection(self.game_svc.session_id, ws)

            # world._char_manager 与 state.character_manager 指向同一对象，
            # load() 已将存档角色加载到该 CM 中，无需重新赋值
            state_snapshot = self.game_svc.state.get_data_copy()
            cm = getattr(self.game_svc.state, 'character_manager', None)
            if cm is not None:
                state_snapshot["__character_manager"] = cm
            state_snapshot["_save_dir"] = str(self.game_svc.state.get_save_dir())
            # 阶段1: StatePersistent.load_state() — 旧格式兼容 + 设置目录 + 合并扩展
            # 必须优先于阶段2执行：MapPlugin.load_state 设置 _map_dir 并合并扩展节点，
            # CalendarPlugin.load_state 从旧 game_time 格式恢复（新格式由阶段2覆盖）
            self.game_svc.plugins.load_state_to_all_plugins(state_snapshot)

            # 阶段2: SelfPersistable.load_own_state() — 从独立文件恢复（主路径）
            # 覆盖阶段1的临时结果（MapPlugin._restore_current_node → load_own_state
            # 用 map/state.json 覆盖；CalendarPlugin load_state → load_own_state
            # 用 calendar/state.json 覆盖）
            self.game_svc.state.load_plugins(self.game_svc.plugins)

            # 从注册表恢复 LLM 生成的物品到 ItemSystem
            inv_plugin = self.game_svc.plugins.get_plugin("inventory") if self.game_svc.plugins else None
            if inv_plugin:
                inv_plugin.restore_registries(self.game_svc.state)
            elif self.game_svc.plugins and hasattr(self.game_svc.plugins, 'bus'):
                # 降级：通过 InventoryService 恢复
                inv_svc = self.inventory_svc
                if inv_svc:
                    inv_svc.restore_registries(self.game_svc.state)

            await ws.send_json({"type": "state_update", "data": self.game_svc.build_state()})
            await ws.send_json({"type": "game_loaded", "data": {"slot": slot_id}})

            # 校验和异常警告
            if self.game_svc.state.is_corrupted():
                logger.warning("加载的存档可能已损坏或被篡改: %s", slot_id)
                await ws.send_json({
                    "type": "system",
                    "content": "⚠️ 警告：此存档可能已损坏或被篡改，请谨慎使用。",
                })

            # 推送插件待推送状态（restore_registries 已标记 dirty）
            inv_state = self.game_svc.plugins.bus.request(
                PluginEvent.INVENTORY_AUTO_PUSH, game_state=self.game_svc.state
            )
            if inv_state:
                await ws.send_json(inv_state)

            # 重放加载存档的历史消息（与新 WebSocket 连接时的行为一致）
            store = self.game_svc.message_store
            if store:
                for m in store.load_all():
                    if m.status == "deleted":
                        continue
                    await ws.send_json({
                        "type": "message.event",
                        "event": "message.created",
                        "data": m.to_json(),
                    })

    async def _handle_new_game(self, ws: WebSocket, msg: dict) -> None:
        import uuid7
        from pathlib import Path
        from lingmo_engine.core.character_manager import CharacterManager
        from lingmo_engine.core.save_manager import extract_world_name
        from datetime import datetime, timezone

        world_name = extract_world_name(self.config.world)
        sm = self.game_svc.state.save_manager
        if sm is None:
            await ws.send_json({"type": "error", "message": "SaveManager 未初始化"})
            return

        with self.game_svc.paused_auto_save():
            # 新游戏：清除旧 autosave，重新创建
            autosave_dir = sm.resolve_slot_path("autosave")
            if autosave_dir.exists():
                shutil.rmtree(autosave_dir)
            slot_dir = sm.ensure_slot_dir("autosave")
            self.game_svc.state.set_slot_dir(slot_dir)
            self.game_svc.store_set_slot_dir(str(slot_dir))
            self.game_svc.memory_set_slot_dir(str(slot_dir))

            session_id = self.game_svc.init_new_session()

            # 更新 MessageController 的连接注册，确保后续 LLM 推送使用新 session_id
            mc = self.game_svc.message_controller
            if mc:
                mc.register_connection(session_id, ws)

            state = self.game_svc.state
            world = self.game_svc.world

            state.reset_scene_state()
            state.set_session_id(session_id)

            # 重置日历插件为初始状态（必须在 load_state_to_all_plugins 之前）
            self._reset_calendar_to_initial(state)

            # 清空所有插件的内存状态（事件、地图、战斗等）
            state_snapshot = state.get_data_copy()
            state_snapshot["_save_dir"] = str(state.get_save_dir())
            self.game_svc.plugins.load_state_to_all_plugins(state_snapshot)

            # 始终创建新的 CharacterManager，加载世界模板角色
            cm = CharacterManager()
            world_dir = getattr(world, '_world_dir', None)
            if world_dir:
                char_dir = Path(world_dir) / "characters" / "fixed"
                if char_dir.exists():
                    cm.load(char_dir)
                    # fixed 文件可能存在同名角色，加载后校验去重
                    removed = cm.validate_after_load()
                    if removed:
                        logger.warning("fixed角色加载后清理重复: %s", removed)
            world._char_manager = cm
            state.character_manager = cm
            self._init_characters_last_updated(cm)

            await self.game_svc.initialize()

            # 同步地图插件初始节点到 MapPlugin 内存
            location_info = self.game_svc.plugins.bus.request(PluginEvent.MAP_GET_LOCATION_INFO, "")
            if location_info and location_info.get("current_node"):
                node = location_info["current_node"]
                # MapPlugin 内部已维护 current_node_id
                # 更新玩家位置为完整路径
                if cm:
                    from lingmo_engine.plugins.map.plugin import MapPlugin
                    full_path = MapPlugin.build_full_path(location_info)
                    cm.update_location(0, full_path)

            state.save_all(self.game_svc.plugins)
            sm.update_meta("autosave",
                session_id=session_id,
                created_at=datetime.now(timezone.utc).isoformat(),
            )

            await ws.send_json({"type": "state_update", "data": self.game_svc.build_state()})

            await ws.send_json({
                "type": "game_started",
                "data": {"opening": ""},
            })

        # 开场白通过 MessageBus 记录
        opening_text = ""
        if opening_text:
            from lingmo_engine.core.message import Message
            from lingmo_engine.core.message_bus import MessageEvent
            import uuid7 as _uuid7
            opening_page_id = str(_uuid7.uuid7())
            self.game_svc.set_last_page_id(opening_page_id)
            opening_msg = Message(
                id=str(_uuid7.uuid7()),
                session_id=session_id,
                page_id=opening_page_id,
                role="narrative",
                content=opening_text,
                status="complete",
            )
            await self.game_svc.publish_message(MessageEvent.CREATED, opening_msg)

    async def _handle_list_saves(self, ws: WebSocket, msg: dict) -> None:
        saves = self.game_svc.list_saves()
        await ws.send_json({
            "type": "save_list",
            "data": {"saves": saves},
        })

    async def _handle_save_game(self, ws: WebSocket, msg: dict) -> None:
        """手动保存：无 slot_id=覆盖当前槽位，有 slot_id=另存为新槽位"""
        slot_id = msg.get("slot_id", "").strip()
        sm = self.game_svc.state.save_manager
        if sm is None:
            await ws.send_json({"type": "error", "message": "存档管理器未初始化"})
            return
        if slot_id:
            try:
                self.game_svc.save_as(slot_id)
                await ws.send_json({"type": "save_result", "success": True, "slot_id": slot_id})
            except FileExistsError:
                await ws.send_json({"type": "error", "message": f"槽位已存在: {slot_id}"})
            except Exception as e:
                await ws.send_json({"type": "error", "message": f"保存失败：{e}"})
        else:
            self.game_svc.save_game()
            current_slot = self.game_svc.state.slot_dir.name
            await ws.send_json({"type": "save_result", "success": True, "slot_id": current_slot})
        saves = sm.list_saves()
        await ws.send_json({"type": "save_list", "data": {"saves": saves}})

    async def _handle_delete_save(self, ws: WebSocket, msg: dict) -> None:
        slot_id = msg.get("slot_id", "")
        sm = self.game_svc.state.save_manager
        if sm is None:
            await ws.send_json({"type": "error", "message": "存档管理器未初始化"})
            return
        if slot_id.startswith("autosave"):
            await ws.send_json({"type": "error", "message": "不能删除自动存档"})
            return
        ok = sm.delete_slot(slot_id)
        await ws.send_json({"type": "delete_result", "success": ok, "slot_id": slot_id})
        saves = sm.list_saves()
        await ws.send_json({"type": "save_list", "data": {"saves": saves}})

    async def _handle_rename_save(self, ws: WebSocket, msg: dict) -> None:
        old_name = msg.get("slot_id", "")
        new_name = msg.get("new_name", "").strip()
        sm = self.game_svc.state.save_manager
        if sm is None or not new_name:
            await ws.send_json({"type": "error", "message": "参数无效"})
            return
        ok = sm.rename_slot(old_name, new_name)
        await ws.send_json({"type": "rename_result", "success": ok, "slot_id": new_name})
        if ok:
            saves = sm.list_saves()
            await ws.send_json({"type": "save_list", "data": {"saves": saves}})

    async def _handle_export_save(self, ws: WebSocket, msg: dict) -> None:
        slot_id = msg.get("slot_id", "")
        sm = self.game_svc.state.save_manager
        if sm is None:
            await ws.send_json({"type": "error", "message": "存档管理器未初始化"})
            return
        if not sm.slot_exists(slot_id):
            await ws.send_json({"type": "error", "message": f"存档不存在：{slot_id}"})
            return
        await ws.send_json({
            "type": "export_ready",
            "url": f"/api/export?slot={slot_id}",
            "slot_id": slot_id,
        })
