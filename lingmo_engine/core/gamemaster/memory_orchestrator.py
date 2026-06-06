"""MemoryOrchestrator — 记忆编排服务，管理长期记忆总结和角色记忆更新。"""
from __future__ import annotations

import logging
from typing import Any, Callable

from lingmo_engine.core.memory import CharacterMemory
from lingmo_engine.core.types import ToolDefinition, ToolParameter
from lingmo_engine.core.gamemaster.text_utils import filter_scene_characters

logger = logging.getLogger(__name__)


def _sanitize_for_json(name: str) -> str:
    """转义角色名中的特殊字符，防止破坏 JSON 格式。"""
    return name.replace('"', '\\"').replace('}', '\\}').replace('{', '\\{')


class MemoryOrchestrator:
    """记忆编排服务 — 管理长期记忆总结和角色记忆更新。

    通过 lambda getter/setter 访问 history、state 等可变状态，
    避免与 GameMaster 形成循环引用。
    """

    def __init__(
        self,
        memory_system: Any,
        llm_handler: Any,
        get_history_fn: Callable[[], list[dict]],
        set_history_fn: Callable[[list[dict]], None],
        get_character_manager_fn: Callable[[], Any],
        get_config_fn: Callable[[], Any],
    ):
        self._memory = memory_system
        self._llm = llm_handler
        self._get_history = get_history_fn
        self._set_history = set_history_fn
        self._get_cm = get_character_manager_fn
        self._get_config = get_config_fn

    # ── 记忆工具定义 ──────────────────────────────────

    def get_memory_tools(self) -> list:
        """获取记忆系统提供的 LLM 工具定义。"""
        tools: list[ToolDefinition] = []
        ms = self._memory
        if ms and ms.char_memory:
            tools.append(ToolDefinition(
                name="recall_character_memory",
                description="拉取指定角色的记忆，包括该角色与主角的共同经历、个人大事和内心真实想法。用于角色即将登场但系统尚未自动注入其记忆时。",
                parameters=[
                    ToolParameter(
                        name="character_name",
                        type="string",
                        description="要查询的角色名称",
                        required=True,
                    ),
                ],
            ))
            tools.append(ToolDefinition(
                name="update_character_memory",
                description="更新指定角色的记忆。在剧情关键节点（结盟、背叛、重要事件等）主动记录，无需等待系统自动总结。提供的内容会替换对应字段，如需保留旧内容请先 recall 再提供合并后的完整内容。",
                parameters=[
                    ToolParameter(
                        name="character_name",
                        type="string",
                        description="要更新记忆的角色名称",
                        required=True,
                    ),
                    ToolParameter(
                        name="shared_experiences",
                        type="string",
                        description="与主角的共同经历（替换写入）",
                        required=False,
                    ),
                    ToolParameter(
                        name="personal_events",
                        type="string",
                        description="该角色身上发生的大事（替换写入）",
                        required=False,
                    ),
                    ToolParameter(
                        name="opinions",
                        type="string",
                        description="对事物/人物的看法（替换写入）",
                        required=False,
                    ),
                ],
            ))
        return tools

    # ── 记忆总结 ──────────────────────────────────

    async def run_memory_summary(
        self, start_round: int, end_round: int,
    ) -> None:
        """执行长期记忆总结（同步 LLM 调用，阻塞主流程直到完成）。"""
        ms = self._memory
        if ms is None:
            return

        logger.info("MemorySystem: running summary for rounds %d-%d", start_round, end_round)

        try:
            # 收集这 N 轮的对话文本
            recent_msgs = ms.get_recent_rounds(ms.shard_size)
            conversation_text = "\n".join(
                f"[{m.role}] {m.content}" for m in recent_msgs
            )

            # 构建总结请求
            summary_prompt = getattr(ms, '_summary_prompt', None) or (
                "你是一个剧情总结助手。请阅读以下游戏对话，提取关键剧情：\n"
                "- 重要的情节推进和转折\n"
                "- 新角色登场或旧角色退场\n"
                "- 关键物品获取、地点变化\n"
                "- 重要的冲突和解决\n\n"
                "输出纯文本叙述，简洁全面。"
            )

            # 截断过长的对话文本
            _MAX_SUMMARY_CHARS = 8000
            if len(conversation_text) > _MAX_SUMMARY_CHARS:
                conversation_text = conversation_text[-_MAX_SUMMARY_CHARS:]
            summary_messages = [
                {"role": "system", "content": summary_prompt},
                {"role": "user", "content": f"请总结以下{end_round - start_round + 1}轮游戏对话的剧情：\n\n{conversation_text}"},
            ]

            summary_text = "（总结生成失败）"
            try:
                response = await self._llm.request(summary_messages, [], wait=True, timeout=60)
                summary_text = response.text if response else "（总结生成失败）"
            except Exception:
                logger.exception("MemorySystem: summary generation failed")

            # 角色记忆更新
            if ms.char_memory:
                try:
                    await self.update_character_memories(
                        conversation_text, summary_text, end_round
                    )
                except Exception:
                    logger.exception("MemorySystem: character memory updates failed")

            # 保存长期记忆
            memory_id = f"ltm_{(start_round - 1) // ms.shard_size + 1:03d}"
            ms.save_long_term_memory(memory_id, (start_round, end_round), summary_text)

            # 关联分片
            shard_id = (start_round - 1) // ms.shard_size + 1
            ms.history_shard.link_summary(shard_id, memory_id)

            # 总结完成后截断 history，保留最近 N 轮以恢复前缀缓存
            config = self._get_config()
            keep = max(1, config.memory.history_keep_rounds)
            history = self._get_history()
            user_indices = [i for i, h in enumerate(history) if h.get("role") == "user"]
            if len(user_indices) > keep:
                removed = len(history) - user_indices[-keep]
                self._set_history(history[user_indices[-keep]:])
                logger.info(
                    "MemorySystem: truncated history to last %d rounds (removed %d messages)",
                    keep, removed,
                )

            logger.info("MemorySystem: summary saved as %s", memory_id)
        finally:
            logger.info("MemorySystem: summary completed for rounds %d-%d", start_round, end_round)

    async def update_character_memories(
        self, conversation_text: str,
        summary_text: str, current_round: int,
    ) -> None:
        """批量更新所有出现在最近对话中的角色记忆（一次 LLM 调用）。"""
        ms = self._memory
        cm = self._get_cm()
        if ms is None or cm is None:
            return

        all_names = {c.name for c in cm.all() if c.name}
        appeared = filter_scene_characters(all_names, conversation_text)
        # 排除玩家角色
        player_name = cm.player.name if cm.player else ""
        appeared = [n for n in appeared if n != player_name]

        if not appeared:
            return

        # 构建每个角色的已有记忆信息
        character_blocks: list[str] = []
        for name in appeared:
            existing = ms.get_character_memory(name)
            existing_text = ""
            if existing:
                existing_text = (
                    f"已有共同经历：{existing.shared_experiences}\n"
                    f"已有个人大事：{existing.personal_events}\n"
                    f"已有内心真实想法：{existing.opinions}"
                )
            else:
                existing_text = "（新角色，无已有记忆）"
            character_blocks.append(f"### {name}\n{existing_text}")

        update_prompt = getattr(ms, '_character_update_prompt', None) or (
            "你是一个角色记忆更新助手。请根据最近的游戏对话和剧情总结，"
            "更新所有角色的三栏记忆：\n"
            "1. 与主角的共同经历（shared_experiences）\n"
            "2. 个人大事（personal_events）\n"
            "3. 内心真实想法（opinions）\n\n"
            "【格式要求】\n"
            "- shared_experiences 和 personal_events 必须逐条列举，每条以序号开头，"
            "格式如：\n1. xxx\n2. xxx\n3. xxx\n"
            "不要写成段落叙述。\n"
            "- opinions 可为自然语言段落。\n\n"
            "【重要】第三栏「内心真实想法」记录的是该角色自己内心深处的真实心理活动，"
            "而非他人对该角色的评价。重点关注：\n"
            "- 角色口是心非、言不由衷的内心独白（嘴上说愿意但内心抗拒）\n"
            "- 被迫违心行事时的无奈与挣扎（身不由己的真实感受）\n"
            "- 对其他角色或事件的隐秘态度（表面友好但内心警惕/厌恶/嫉妒）\n"
            "- 未说出口的计划、顾虑和情感（隐藏的目的、压抑的感情）\n\n"
            "这栏记忆的目的是让AI能够据此塑造出心口不一、表里不同的复杂角色，"
            "请务必从该角色自身的视角出发提取内心想法，不要写成外部观察者的描述。\n\n"
            "对于已有记忆，智能合并：新经历追加，观点变化更新，旧信息不重复。"
        )

        user_content = (
            f"请更新以下角色的记忆。\n\n"
            f"{chr(10).join(character_blocks)}\n\n"
            f"最近对话：\n{conversation_text}\n\n"
            f"剧情总结：\n{summary_text}\n\n"
            f"请严格按照 JSON 格式输出，key 为角色名，value 包含 shared_experiences / personal_events / opinions（内心真实想法） 三个字段：\n"
            f'{{"{_sanitize_for_json(appeared[0]) if appeared else "角色名"}": {{"shared_experiences": "...", "personal_events": "...", "opinions": "..."}}, ...}}'
        )

        update_messages = [
            {"role": "system", "content": update_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            response = await self._llm.request(update_messages, [], wait=True, timeout=60)
            if not response or not response.text:
                logger.warning("MemorySystem: empty character memory update response")
                return

            import json as json_module
            import re
            text = response.text.strip()
            # 从代码块中提取 JSON
            code_match = re.search(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL)
            if code_match:
                text = code_match.group(1).strip()
            else:
                # 尝试直接从文本中提取 JSON 对象
                brace_match = re.search(r'\{.*\}', text, re.DOTALL)
                if brace_match:
                    text = brace_match.group(0)
            data = json_module.loads(text)

            for name in appeared:
                char_data = data.get(name, {})
                if not char_data:
                    logger.warning("MemorySystem: no data for character %s in batch response", name)
                    continue
                mem = CharacterMemory(
                    character_name=name,
                    shared_experiences=str(char_data.get("shared_experiences", "")),
                    personal_events=str(char_data.get("personal_events", "")),
                    opinions=str(char_data.get("opinions", "")),
                    last_updated_round=current_round,
                )
                ms.save_character_memory(mem)
                logger.info("MemorySystem: updated character memory for %s", name)
        except Exception:
            logger.exception("MemorySystem: batch character memory update failed")

    # ── 工具方法 ──────────────────────────────────
