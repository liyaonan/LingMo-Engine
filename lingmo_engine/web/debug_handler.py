"""Debug 控制台处理器 — 在 WebSocket 层拦截 /debug 指令，绕过 LLM 直接执行"""
from __future__ import annotations

import inspect
import json
import logging
from pathlib import Path

import yaml
from fastapi import WebSocket

logger = logging.getLogger(__name__)

# 兼容别名：旧名 → schema 字段名
_DEBUG_ATTR_ALIASES = {
    "hp": "vitality",
    "max_hp": "max_vitality",
    "mp": "spiritual_power",
    "max_mp": "spiritual_power",
    "attack": "force",
    "defense": "tenacity",
    "speed": "agility",
    "gold": "spirit_stones",
}


class DebugHandler:
    """解析并执行 /debug <子命令> 指令"""

    def __init__(self, state, world, plugins, config,
                 message_bus=None, message_store=None,
                 session_id_provider=None):
        self.state = state
        self.world = world
        self.plugins = plugins
        self.config = config
        self._bus = message_bus
        self._store = message_store
        self._get_session_id = session_id_provider or (lambda: "default")
        self._commands = {
            "add_item": self._handle_add_item,
            "remove_item": self._handle_remove_item,
            "combat": self._handle_combat,
            "spawn": self._handle_spawn,
            "cultivate": self._handle_cultivate,
            "set": self._handle_set,
            "list": self._handle_list,
        }

        # 从 world.attributes 动态构建可设置属性名列表
        self._settable_attrs: list[str] = []
        self._attr_labels: dict[str, str] = {}
        if hasattr(world, "attributes") and world.attributes:
            for name, defn in world.attributes.items():
                if defn.get("read_only"):
                    continue
                self._settable_attrs.append(name)
                self._attr_labels[name] = defn.get("label", name)
        # 旧别名也纳入可用列表
        for alias in _DEBUG_ATTR_ALIASES:
            if alias not in self._settable_attrs:
                self._settable_attrs.append(alias)

        # 加载预设模板（用于 /debug spawn）
        self._preset_templates: list[dict] = self._load_preset_templates()

        # 注册 msg 子命令
        if message_store:
            self._msg_handler = MessageCommandHandler(
                message_store, message_bus, self._get_session_id
            )
            self._commands["msg"] = self._handle_msg

        # 注册 panel 命令
        self._commands["panel"] = self._handle_panel

    async def handle(self, input_text: str, ws: WebSocket) -> None:
        """入口：解析 /debug 指令并执行"""
        parts = input_text.strip().split()
        if len(parts) < 2:
            await self._reply(ws, "用法: /debug <add_item|remove_item|combat|spawn|cultivate|set|list|msg|panel> ...")
            return

        sub_cmd = parts[1]
        handler = self._commands.get(sub_cmd)
        if handler is None:
            available = "、".join(self._commands.keys())
            await self._reply(ws, f"未知 debug 子命令: {sub_cmd}。可用: {available}")
            return

        try:
            if inspect.iscoroutinefunction(handler):
                result = await handler(parts[2:])
            else:
                result = handler(parts[2:])
            if isinstance(result, tuple):
                text, extra = result
            else:
                text = result
                extra = None

            if extra and extra.get("type") == "encounter":
                if self._bus:
                    import uuid7 as _uuid7
                    from lingmo_engine.core.message import Message
                    from lingmo_engine.core.message_bus import MessageEvent
                    encounter_data = extra["payload"]
                    encounter_msg = Message(
                        id=str(_uuid7.uuid7()),
                        session_id=self._get_session_id(),
                        page_id=str(_uuid7.uuid7()),
                        role="encounter",
                        content=json.dumps(encounter_data, ensure_ascii=False),
                        content_blocks=[{"type": "encounter_card", "data": encounter_data}],
                    )
                    await self._bus.publish(MessageEvent.CREATED, encounter_msg)
                else:
                    await ws.send_json({
                        "type": "encounter",
                        "content": json.dumps(extra["payload"], ensure_ascii=False),
                    })
            elif extra and extra.get("type") == "debug_panel":
                await ws.send_json({"type": "debug_panel", "action": extra["action"]})
            await self._reply(ws, text)
            self.state.save()
        except Exception as e:
            logger.exception("Debug command failed: %s", sub_cmd)
            await self._reply(ws, f"Debug 指令执行失败: {e}")

    # ── 子命令处理器 ──────────────────────────────────

    async def _handle_add_item(self, args: list[str]) -> str:
        if not args:
            return "用法: /debug add_item <物品ID> [数量]"
        item_id = args[0]
        try:
            count = int(args[1]) if len(args) > 1 else 1
        except ValueError:
            return f"错误：数量必须是整数，收到 '{args[1]}'"
        if count <= 0:
            return "错误：数量必须为正整数"

        item_data = self.world.items.get(item_id) if hasattr(self.world, "items") else None
        if item_data is None:
            return f"错误：物品 '{item_id}' 不存在。使用 /debug list items 查看可用物品"

        display_name = item_data.get("name", item_id)
        self.state.add_player_item(item_id, count)
        return f"已添加：{display_name} x{count}"

    async def _handle_remove_item(self, args: list[str]) -> str:
        if not args:
            return "用法: /debug remove_item <物品ID> [数量]"
        item_id = args[0]
        if len(args) > 1:
            try:
                count = int(args[1])
            except ValueError:
                return f"错误：数量必须是整数，收到 '{args[1]}'"
            if count <= 0:
                return "错误：数量必须为正整数"
        else:
            count = None

        inventory = self.state.data.get("inventory", [])
        entry = next((e for e in inventory if e["item_id"] == item_id), None)
        if entry is None:
            return f"错误：背包中没有 '{item_id}'"

        remove_count = count if count is not None else entry["quantity"]
        ok = self.state.remove_player_item(item_id, remove_count)
        if not ok:
            return f"错误：数量不足，背包中仅有 {entry['quantity']} 个"

        item_data = self.world.items.get(item_id) if hasattr(self.world, "items") else {}
        display_name = item_data.get("name", item_id)
        return f"已移除：{display_name} x{remove_count}"

    async def _handle_combat(self, args: list[str]) -> tuple[str, dict]:
        """与固定 NPC 角色战斗（从 CharacterManager 中查找）。"""
        if not args:
            return "用法: /debug combat <NPC名称或ID>", {}
        enemy_id = args[0]

        # 从 CharacterManager 查找角色（按 ID 或名称）
        cm = getattr(self.state, 'character_manager', None) or self._get_world_cm()
        target = None
        if cm:
            try:
                target = cm.get(int(enemy_id))
            except (ValueError, TypeError):
                pass
            if target is None:
                for c in cm.all():
                    if c.name == enemy_id or str(c.id) == str(enemy_id):
                        target = c
                        break

        if target is None:
            return (f"错误：角色 '{enemy_id}' 不存在。"
                    "使用 /debug list enemies 查看固定角色，"
                    "/debug list templates 查看模板"), {}

        target_name = target.name or enemy_id
        encounter_data = {
            "groups": [{
                "name": target_name,
                "enemies": [{
                    "source": "npc",
                    "character_id": str(target.id),
                    "name": target_name,
                }],
            }],
            "forced": True,
        }
        self.state.set_scene_enemies(encounter_data)
        return (
            f"固定NPC战斗：{target_name}(ID:{target.id})",
            {"type": "encounter", "payload": encounter_data},
        )

    async def _handle_spawn(self, args: list[str]) -> tuple[str, dict]:
        """根据预设模板生成临时敌人并触发战斗。"""
        if not args:
            return (f"用法: /debug spawn <模板ID> [等级] [数量] [资质]\n"
                    f"可用模板: {', '.join(t['id'] for t in self._preset_templates) or '无'}"), {}

        template_id = args[0]
        template = None
        for t in self._preset_templates:
            if t["id"] == template_id:
                template = t
                break
        if template is None:
            available = ", ".join(t["id"] for t in self._preset_templates)
            return f"错误：模板 '{template_id}' 不存在。可用: {available}", {}

        level = 1
        count = 1
        aptitude = 0.5

        if len(args) > 1:
            try:
                level = int(args[1])
            except ValueError:
                return f"错误：等级必须是整数，收到 '{args[1]}'", {}
        if len(args) > 2:
            try:
                count = int(args[2])
            except ValueError:
                return f"错误：数量必须是整数，收到 '{args[2]}'", {}
        if len(args) > 3:
            try:
                aptitude = max(0.0, min(1.0, float(args[3])))
            except ValueError:
                return f"错误：资质必须是 0~1 的浮点数，收到 '{args[3]}'", {}

        aptitude_bias = template.get("aptitude_bias", {})
        template_name = template.get("name", template_id)
        encounter_data = {
            "groups": [{
                "name": template_name,
                "enemies": [{
                    "source": "hostile",
                    "template": template_id,
                    "name": template_name,
                    "count": count,
                    "level": level,
                    "aptitude": aptitude,
                    "aptitude_bias": aptitude_bias,
                }],
            }],
            "forced": True,
        }
        self.state.set_scene_enemies(encounter_data)
        desc = f"{template_name} LV{level} x{count} (资质:{aptitude:.1f})"
        return (
            f"模板战斗：{desc}",
            {"type": "encounter", "payload": encounter_data},
        )

    async def _handle_cultivate(self, args: list[str]) -> tuple[str, dict]:
        """调出修炼机缘卡片。"""
        qi_bonus = 1.0
        narrative_hint = "Debug 触发修炼机缘。"
        if args:
            try:
                qi_bonus = float(args[0])
            except ValueError:
                narrative_hint = " ".join(args)
                qi_bonus = 1.0
        if len(args) > 1:
            narrative_hint = " ".join(args[1:])

        # 读取玩家角色修炼状态
        try:
            player = self.state.get_player()
        except Exception:
            return "错误：玩家角色未初始化", {}

        cm = self._get_world_cm()
        if cm is None:
            return "错误：角色系统未加载", {}

        # 通过 Character 的 attrs 获取修炼属性
        attrs = player.attrs if hasattr(player, "attrs") else {}
        stage_id = attrs.get("cultivation_stage", "mortal")
        current_sp = attrs.get("spiritual_power", 0)
        current_rhyme = attrs.get("dao_rhyme", 0)

        # 从 cultivation.yaml 查境界信息
        stage_name = stage_id
        next_threshold = 0
        cult_data = self._load_cultivation_config()
        if cult_data:
            for s in cult_data.get("stages", []):
                if s["id"] == stage_id:
                    stage_name = s.get("name", stage_id)
                    bt = s.get("breakthrough_to")
                    if bt:
                        next_stage_id = bt
                        key = f"{stage_id}_to_{next_stage_id}"
                        rule = cult_data.get("breakthrough_rules", {}).get(
                            "per_transition", {}).get(key)
                        if rule:
                            raw_min = rule.get("requirements", {}).get(
                                "spiritual_power_min", 0)
                            next_threshold = int(raw_min) if isinstance(
                                raw_min, (int, float)) else 0
                    break

        card_data = {
            "cultivation_opportunity": True,
            "narrative_hint": narrative_hint,
            "qi_bonus": qi_bonus,
            "stage_name": stage_name,
            "spiritual_power": current_sp,
            "next_threshold": next_threshold,
            "dao_rhyme": current_rhyme,
        }

        # 通过 MessageBus 发布修炼卡片消息
        if self._bus:
            import uuid7 as _uuid7
            from lingmo_engine.core.message import Message
            from lingmo_engine.core.message_bus import MessageEvent
            cult_msg = Message(
                id=str(_uuid7.uuid7()),
                session_id=self._get_session_id(),
                page_id=str(_uuid7.uuid7()),
                role="cultivation_opportunity",
                content=json.dumps(card_data, ensure_ascii=False),
                content_blocks=[{"type": "cultivation_opportunity", "data": card_data}],
            )
            await self._bus.publish(MessageEvent.CREATED, cult_msg)
            return (
                f"修炼卡片已调出：{stage_name} / 灵力 {current_sp}"
                + (f" / 下一境 {next_threshold}" if next_threshold else ""),
                {},
            )

        return "错误：MessageBus 不可用", {}

    async def _handle_set(self, args: list[str]) -> str:
        if len(args) < 2:
            return "用法: /debug set <属性> <值>\n可用属性: " + ", ".join(self._settable_attrs)
        attr = args[0].lower()
        if attr not in self._settable_attrs:
            return f"错误：未知属性 '{attr}'。可用: {', '.join(self._settable_attrs)}"

        try:
            value = int(args[1])
        except ValueError:
            return f"错误：值必须是整数，收到 '{args[1]}'"

        # 别名 → 实际字段名
        player_key = _DEBUG_ATTR_ALIASES.get(attr, attr)
        label = self._attr_labels.get(player_key, player_key)
        self.state.update_player(**{player_key: value})
        return f"已设置 {label}({player_key}) = {value}"

    async def _handle_list(self, args: list[str]) -> str:
        if not args:
            return "用法: /debug list <items|enemies|npcs|templates>"
        list_type = args[0].lower()

        if list_type == "items":
            if not self.world or not hasattr(self.world, "items") or not self.world.items:
                return "世界没有定义物品"
            lines = ["可用物品:"]
            for item_id, data in sorted(self.world.items.items()):
                name = data.get("name", item_id)
                lines.append(f"  - {item_id}: {name}")
            return "\n".join(lines)

        if list_type == "enemies":
            cm = self._get_world_cm()
            if not cm:
                return "角色系统未初始化"
            from lingmo_engine.core.character import CharacterType
            monsters = cm.list_by_type(CharacterType.MONSTER)
            if not monsters:
                return "没有固定怪物角色（试试 /debug list templates）"
            lines = ["固定怪物角色（/debug combat <名称或ID>）:"]
            for m in sorted(monsters, key=lambda x: x.id):
                lines.append(f"  - {m.id}: {m.name} (LV{m.level})")
            return "\n".join(lines)

        if list_type == "npcs":
            cm = self._get_world_cm()
            if not cm:
                return "角色系统未初始化"
            from lingmo_engine.core.character import CharacterType
            npcs = cm.list_by_type(CharacterType.NPC)
            if not npcs:
                return "没有固定 NPC"
            lines = ["固定 NPC 角色（/debug combat <名称或ID>）:"]
            for n in sorted(npcs, key=lambda x: x.id):
                lines.append(f"  - {n.id}: {n.name} (LV{n.level})")
            return "\n".join(lines)

        if list_type == "templates":
            if not self._preset_templates:
                return "没有预设模板"
            lines = ["预设模板（/debug spawn <模板ID> [等级] [数量] [资质]）:"]
            for t in self._preset_templates:
                char_type = t.get("char_type", "?")
                desc = t.get("description", "")[:40]
                lines.append(f"  - {t['id']}: {t['name']} ({char_type}) {desc}")
            return "\n".join(lines)

        return f"未知列表类型: {list_type}。可用: items, enemies, npcs, templates"

    def _handle_msg(self, args: list[str]) -> str:
        """处理 /debug msg 子命令"""
        subcmd = args[0] if args else "list"
        return self._msg_handler.handle(subcmd, args[1:])

    async def _handle_panel(self, args: list[str]):
        """发送消息通知前端打开 DebugPanel"""
        return "panel", {"type": "debug_panel", "action": "toggle"}

    # ── Helpers ───────────────────────────────────────

    def _get_world_cm(self):
        """获取世界的 CharacterManager 实例。"""
        return getattr(self.world, '_char_manager', None)

    def _load_preset_templates(self) -> list[dict]:
        """从世界配置加载预设模板列表。"""
        world_dir = getattr(self.world, '_world_dir', None)
        if not world_dir:
            return []
        preset_path = Path(world_dir) / "characters" / "preset_templates.yaml"
        if not preset_path.exists():
            return []
        try:
            with open(preset_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return data.get("templates", [])
        except Exception:
            logger.warning("加载预设模板失败", exc_info=True)
            return []

    def _load_cultivation_config(self) -> dict:
        """加载 cultivation.yaml 配置。"""
        world_dir = getattr(self.world, '_world_dir', None)
        if not world_dir:
            return {}
        cult_path = Path(world_dir) / "cultivation.yaml"
        if not cult_path.exists():
            return {}
        try:
            with open(cult_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            logger.warning("加载修炼配置失败", exc_info=True)
            return {}

    async def _reply(self, ws: WebSocket, text: str) -> None:
        try:
            await ws.send_json({"type": "system", "content": text})
        except Exception:
            logger.exception("Failed to send debug reply")


class MessageCommandHandler:
    """/debug msg 子命令处理器"""

    def __init__(self, message_store, message_bus, session_id_provider=None):
        self._store = message_store
        self._bus = message_bus
        self._get_session_id = session_id_provider or (lambda: "default")

    def handle(self, subcmd: str, args: list[str]) -> str:
        session_id = self._get_session_id()

        if subcmd == "list":
            n = int(args[0]) if args else 20
            messages = self._store.load_all()
            recent = messages[-n:]
            lines = ["─" * 60]
            role_icon = {"user": "👤", "narrative": "🤖", "tool": "🔧",
                         "combat": "⚔", "system": "⚙", "error": "❌"}
            for i, m in enumerate(reversed(recent)):
                preview = m.content[:60].replace("\n", " ")
                t = m.timestamp[11:19] if m.timestamp else "--:--:--"
                icon = role_icon.get(m.role, "📄")
                lines.append(
                    f"#{len(recent) - i:03d} [{t}] {icon} {m.role}: {preview}..."
                )
            lines.append("─" * 60)
            lines.append(f"共 {len(messages)} 条消息")
            return "\n".join(lines)

        elif subcmd == "show":
            if not args:
                return "用法: /debug msg show <消息ID或序号>"
            msg = self._find_msg(session_id, args[0])
            if not msg:
                return f"消息不存在: {args[0]}"
            lines = [
                f"ID: {msg.id}",
                f"角色: {msg.role}  状态: {msg.status}  版本: {msg.meta.edit_version}",
                f"时间: {msg.timestamp}",
                f"内容:",
                msg.content,
            ]
            return "\n".join(lines)

        elif subcmd == "meta":
            if not args:
                return "用法: /debug msg meta <消息ID或序号>"
            msg = self._find_msg(session_id, args[0])
            if not msg:
                return f"消息不存在: {args[0]}"
            m = msg.meta
            lines = [
                f"模型: {m.model or '-'}",
                f"Tokens: {m.total_tokens} (prompt={m.prompt_tokens}, completion={m.completion_tokens})",
                f"耗时: {m.latency_ms}ms",
                f"finish_reason: {m.finish_reason or '-'}",
                f"编辑版本: {m.edit_version}",
                f"工具调用: {len(m.tool_calls_made)} 个",
            ]
            return "\n".join(lines)

        elif subcmd == "prompt":
            if not args:
                return "用法: /debug msg prompt <消息ID或序号>"
            msg = self._find_msg(session_id, args[0])
            if not msg:
                return f"消息不存在: {args[0]}"
            prompt = msg.meta.raw_prompt or "(无记录)"
            if len(prompt) > 2000:
                prompt = prompt[:2000] + f"\n\n... (截断，共 {len(msg.meta.raw_prompt)} 字符)"
            return f"Raw Prompt:\n{prompt}"

        elif subcmd == "search":
            if not args:
                return "用法: /debug msg search <关键词>"
            keyword = " ".join(args)
            messages = self._store.load_all()
            found = []
            for m in messages:
                if keyword.lower() in m.content.lower():
                    found.append(m)
            if not found:
                return f"未找到包含 '{keyword}' 的消息"
            lines = [f"搜索 '{keyword}' 找到 {len(found)} 条:"]
            for m in found[-20:]:
                preview = m.content[:80].replace("\n", " ")
                lines.append(f"  [{m.timestamp[11:19] if m.timestamp else '--:--:--'}] {m.id}: {preview}...")
            return "\n".join(lines)

        elif subcmd == "stats":
            messages = self._store.load_all()
            role_counts = {}
            total_tokens = 0
            for m in messages:
                role_counts[m.role] = role_counts.get(m.role, 0) + 1
                total_tokens += m.meta.total_tokens
            lines = [
                f"消息总数: {len(messages)}",
                f"总 Tokens: {total_tokens}",
                f"按角色:",
            ]
            for role, count in sorted(role_counts.items()):
                lines.append(f"  {role}: {count}")
            return "\n".join(lines)

        elif subcmd == "edit":
            if len(args) < 2:
                return "用法: /debug msg edit <消息ID> <新内容>"
            msg = self._find_msg(session_id, args[0])
            if not msg:
                return f"消息不存在: {args[0]}"
            new_content = " ".join(args[1:])
            updated = self._store.update(msg.id, new_content)
            if updated:
                # 通过 MessageBus 通知前端（如果有 bus）
                if self._bus:
                    from lingmo_engine.core.message_bus import MessageEvent
                    import asyncio
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.ensure_future(
                                self._bus.publish(MessageEvent.UPDATED, updated)
                            )
                    except RuntimeError:
                        pass
                return f"消息 {args[0]} 已更新 (version {updated.meta.edit_version})"
            return "更新失败"

        elif subcmd == "delete":
            if not args:
                return "用法: /debug msg delete <消息ID或序号>"
            msg = self._find_msg(session_id, args[0])
            if not msg:
                return f"消息不存在: {args[0]}"
            if self._store.mark_deleted(msg.id):
                return f"消息 {args[0]} 已删除"
            return "删除失败"

        elif subcmd == "export":
            path = self._store._messages_path()
            return f"当前会话消息文件: {path}"

        else:
            return (
                "用法: /debug msg <list|show|meta|prompt|search|stats|edit|delete|export>\n"
                "  list [n]          - 列出最近 n 条消息\n"
                "  show <id>         - 显示消息完整内容\n"
                "  meta <id>         - 显示消息元数据\n"
                "  prompt <id>       - 显示 raw_prompt\n"
                "  search <kw>       - 搜索消息\n"
                "  stats             - 消息统计\n"
                "  edit <id> <text>  - 编辑消息\n"
                "  delete <id>       - 删除消息\n"
                "  export            - 导出文件路径"
            )

    def _find_msg(self, session_id: str, identifier: str):
        messages = self._store.load_all()
        for m in messages:
            if m.id == identifier or m.id.startswith(identifier):
                return m
        try:
            index = int(identifier)
            if 1 <= index <= len(messages):
                return messages[index - 1]
        except ValueError:
            pass
        return None
