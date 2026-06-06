"""工具调用执行与结果应用。"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from lingmo_engine.core.memory import CharacterMemory
from lingmo_engine.core.message import Message
from lingmo_engine.core.message_bus import MessageEvent
from lingmo_engine.core.types import DisplayType

if TYPE_CHECKING:
    from lingmo_engine.core.gamemaster.game_master import GameMaster

logger = logging.getLogger(__name__)

_INTERNAL_KEYS = frozenset({
    "state_updates", "player_updates", "player_hp",
    "exp_gained", "loot", "_events",
})

# player_updates 允许设置的 dataclass 字段白名单（值类型用于转换校验）
_SETTABLE_FIELDS: dict[str, object] = {
    "exp": 0,
    "level": 0,
}


class ToolExecutor:
    """执行 LLM 触发的工具调用，将结果写入 GameState 并发射事件。"""

    def __init__(self, gm: "GameMaster") -> None:
        self._gm = gm

    async def execute(
        self, final_tool_calls: list,
        page_id: str = "",
    ) -> tuple[list, list, list]:
        """执行工具调用列表，返回 (tool_calls_schema, tool_results, tool_call_summaries)。"""
        import uuid7

        tool_calls_schema = []
        tool_results = []
        tool_call_summaries = []
        state = self._gm.state
        bus = self._gm._bus
        session_id = self._gm.session_id

        for tc in final_tool_calls:
            tool_calls_schema.append({
                "id": tc.id, "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(tc.params, ensure_ascii=False),
                },
            })

            system_msg = Message(
                id=str(uuid7.uuid7()),
                session_id=session_id,
                page_id=page_id,
                role="system",
                content=f"触发模块：{tc.name}",
            )
            await bus.publish(MessageEvent.CREATED, system_msg)
            logger.info("触发模块：%s，参数：%s", tc.name, tc.params)
            if tc.name == "use_skill":
                skill_result = self._gm.skill_manager.execute_use_skill(
                    tc.params.get("name", ""),
                    tc.params.get("args"),
                )
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": skill_result.get("content", ""),
                })
                tool_call_summaries.append({"name": tc.name, "params": tc.params})
                continue
            if tc.name == "recall_character_memory":
                character_name = tc.params.get("character_name", "")
                memory_system = getattr(self._gm, "_memory_system", None)
                if memory_system:
                    mem = memory_system.get_character_memory(character_name)
                    if mem:
                        content_parts = [f"## {character_name} 的记忆\n"]
                        if mem.shared_experiences:
                            content_parts.append(f"与主角的共同经历：{mem.shared_experiences}")
                        if mem.personal_events:
                            content_parts.append(f"个人大事：{mem.personal_events}")
                        if mem.opinions:
                            content_parts.append(f"内心真实想法：{mem.opinions}")
                        content = "\n".join(content_parts)
                    else:
                        content = f"未找到角色「{character_name}」的记忆。"
                else:
                    content = "记忆系统未启用。"
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": content,
                })
                tool_call_summaries.append({"name": tc.name, "params": tc.params})
                continue

            if tc.name == "update_character_memory":
                character_name = tc.params.get("character_name", "")
                memory_system = getattr(self._gm, "_memory_system", None)
                if not character_name.strip():
                    content = "角色名称不能为空。"
                elif not memory_system or not memory_system.char_memory:
                    content = "记忆系统未启用。"
                else:
                    # 至少需要提供一个更新字段
                    fields = {
                        "shared_experiences": tc.params.get("shared_experiences"),
                        "personal_events": tc.params.get("personal_events"),
                        "opinions": tc.params.get("opinions"),
                    }
                    provided = {k: v for k, v in fields.items() if v is not None}
                    if not provided:
                        content = "至少需要提供一个更新字段（shared_experiences / personal_events / opinions）。"
                    else:
                        # 合并已有记忆
                        existing = memory_system.get_character_memory(character_name)
                        shared = provided.get("shared_experiences",
                                              existing.shared_experiences if existing else "")
                        personal = provided.get("personal_events",
                                                existing.personal_events if existing else "")
                        opinions = provided.get("opinions",
                                                existing.opinions if existing else "")
                        current_round = memory_system.history_shard.load_index().total_rounds
                        mem = CharacterMemory(
                            character_name=character_name,
                            shared_experiences=shared,
                            personal_events=personal,
                            opinions=opinions,
                            last_updated_round=current_round,
                        )
                        memory_system.save_character_memory(mem)
                        updated_fields = "、".join(provided.keys())
                        content = f"已更新「{character_name}」的记忆（{updated_fields}）。"
                        logger.info("ToolExecutor: updated character memory for %s (%s)",
                                    character_name, updated_fields)
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": content,
                })
                tool_call_summaries.append({"name": tc.name, "params": tc.params})
                continue
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._gm.plugins.execute_tool_by_name, tc.name, tc.params
                    ),
                    timeout=30.0,
                )
            except asyncio.TimeoutError:
                logger.error("tool_executor: 工具 %s 执行超时（30s）", tc.name)
                result = None

            if result is None:
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps({
                        "success": False,
                        "log": f"工具 {tc.name} 执行超时（30s）",
                    }, ensure_ascii=False),
                })
                tool_call_summaries.append({
                    "name": tc.name, "params": tc.params, "success": False,
                })
                continue

            if result.success:
                logger.debug("工具 %s 执行成功: %s", tc.name, result.log)
            else:
                logger.warning("工具 %s 执行失败: %s", tc.name, result.log)

            if result.log:
                log_msg = Message(
                    id=str(uuid7.uuid7()),
                    session_id=session_id,
                    page_id=page_id,
                    role=result.display_type if result.display_type != DisplayType.SYSTEM else "system",
                    content=result.log,
                )
                await bus.publish(MessageEvent.CREATED, log_msg)

            self.apply_result(result)

            if result.data:
                for event_type, event_data in result.data.get("_events", []):
                    block_type = "encounter_card" if event_type == "encounter" else event_type
                    encounter_msg = Message(
                        id=str(uuid7.uuid7()),
                        session_id=session_id,
                        page_id=page_id,
                        role=event_type,
                        content=json.dumps(event_data, ensure_ascii=False),
                        content_blocks=[{"type": block_type, "data": event_data}],
                    )
                    await bus.publish(MessageEvent.CREATED, encounter_msg)

            if result.display_type == DisplayType.ENCOUNTER and result.data:
                if result.data.get("groups"):
                    # 战斗遭遇卡片
                    encounter_data = {
                        "groups": result.data["groups"],
                        "forced": result.data.get("forced", False),
                    }
                    encounter_msg = Message(
                        id=str(uuid7.uuid7()),
                        session_id=session_id,
                        page_id=page_id,
                        role="encounter",
                        content=json.dumps(encounter_data, ensure_ascii=False),
                        content_blocks=[{"type": "encounter_card", "data": encounter_data}],
                    )
                    await bus.publish(MessageEvent.CREATED, encounter_msg)
                elif result.data.get("cultivation_opportunity"):
                    # 修炼机缘卡片
                    cult_msg = Message(
                        id=str(uuid7.uuid7()),
                        session_id=session_id,
                        page_id=page_id,
                        role="cultivation_opportunity",
                        content=json.dumps(result.data, ensure_ascii=False),
                        content_blocks=[{"type": "cultivation_opportunity", "data": result.data}],
                    )
                    await bus.publish(MessageEvent.CREATED, cult_msg)

            # 精简 tool_result：只返回 LLM 需要的 success + log，
            # 排除内部数据（state_updates、player_updates 等）减少 token 消耗
            _MAX_FIELD_CHARS = 2000
            result_data = {}
            if result.data:
                for k, v in result.data.items():
                    if k in _INTERNAL_KEYS:
                        continue
                    val_str = json.dumps(v, ensure_ascii=False)
                    if len(val_str) > _MAX_FIELD_CHARS:
                        result_data[k] = val_str[:_MAX_FIELD_CHARS] + "\n...（截断）"
                    else:
                        result_data[k] = v
            tool_results.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps({
                    "success": result.success,
                    "log": result.log,
                    **result_data,
                }, ensure_ascii=False),
            })
            tool_call_summaries.append({
                "name": tc.name, "params": tc.params, "success": result.success,
            })

        return tool_calls_schema, tool_results, tool_call_summaries

    def apply_result(self, result) -> None:
        data = result.data
        if not data:
            return
        state = self._gm.state

        if "state_updates" in data:
            for key, value in data["state_updates"].items():
                if key == "custom_abilities" and isinstance(value, dict):
                    for aid, adef in value.items():
                        try:
                            state.add_registry_ability(aid, adef)
                        except Exception:
                            logger.warning("ToolExecutor: custom_abilities 注册失败 '%s'", aid, exc_info=True)
                else:
                    try:
                        state.set_top_level(key, value)
                    except KeyError:
                        logger.warning("ToolExecutor: state_updates 跳过未知键 '%s'", key)

        cm = getattr(state, 'character_manager', None)
        if cm is None:
            return

        player = cm.player

        if "player_updates" in data:
            for key, value in data["player_updates"].items():
                if key == "abilities":
                    player.abilities = list(value)
                elif key in ("name",):
                    player.name = value
                elif key == "location":
                    cm.update_location(player.id, value)
                elif key == "loot":
                    self._apply_loot(player, value)
                else:
                    # 允许更新 attrs 中已有属性或已知 dataclass 字段
                    if key in player.attrs:
                        try:
                            player.attrs[key] = int(float(value)) if not isinstance(value, int) else value
                        except (ValueError, TypeError):
                            logger.warning("tool_executor: 属性 %s 转换失败: %r", key, value)
                    elif key in _SETTABLE_FIELDS:
                        try:
                            setattr(player, key, int(value))
                        except (ValueError, TypeError):
                            logger.warning("tool_executor: 字段 %s 转换失败: %r", key, value)
                    else:
                        logger.warning("tool_executor: 忽略未知属性 %s", key)

        if "player_hp" in data:
            player.attrs["vitality"] = data["player_hp"]

        if "exp_gained" in data:
            player.exp += data["exp_gained"]

        if "loot" in data:
            self._apply_loot(player, data["loot"])

        # CharacterManager 是唯一数据源，无需同步

    @staticmethod
    def _apply_loot(player, loot_items: list) -> None:
        """将 loot 列表中的物品添加到玩家背包（堆叠已有条目）。"""
        for loot_item in loot_items:
            item_id = loot_item.get("item_id", "")
            qty = loot_item.get("quantity", 1)
            found = False
            for entry in player.inventory:
                if entry["item_id"] == item_id:
                    entry["quantity"] += qty
                    found = True
                    break
            if not found:
                player.inventory.append({"item_id": item_id, "quantity": qty})