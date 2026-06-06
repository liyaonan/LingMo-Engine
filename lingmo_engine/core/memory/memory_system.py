"""MemorySystem — 记忆系统统一入口。"""
from __future__ import annotations

import logging
import threading
from collections import deque
from typing import TYPE_CHECKING

from lingmo_engine.core.memory.long_term_memory import LongTermMemoryManager
from lingmo_engine.core.memory.character_memory import CharacterMemoryManager
from lingmo_engine.core.memory.history_shard import HistoryShardManager
from lingmo_engine.core.memory.types import CharacterMemory

if TYPE_CHECKING:
    from lingmo_engine.core.message import Message

logger = logging.getLogger(__name__)


class MemorySystem:
    """记忆系统总入口，组合三个子管理器。

    对外暴露统一接口，内部协调 LongTermMemoryManager、CharacterMemoryManager、
    HistoryShardManager 的协作。
    """

    def __init__(
        self,
        shard_size: int = 50,
        long_term_enabled: bool = True,
        character_memory_enabled: bool = True,
    ) -> None:
        self._slot_dir = ""
        self.shard_size = shard_size
        self.long_term_enabled = long_term_enabled
        self.character_memory_enabled = character_memory_enabled
        self.history_shard = HistoryShardManager(shard_size)
        self.long_term = LongTermMemoryManager() if long_term_enabled else None
        self.char_memory = CharacterMemoryManager() if character_memory_enabled else None

        # 待处理的总结队列，线程安全
        self._pending_summaries: deque[tuple[int, int]] = deque()
        self._pending_lock = threading.Lock()

        # 总结和角色记忆更新提示词缓存（由 world 在 initialize 时加载）
        self._summary_prompt: str = ""
        self._character_update_prompt: str = ""

    def set_slot_dir(self, slot_dir: str) -> None:
        """设置当前 slot 目录路径，传播到所有子管理器。

        Args:
            slot_dir: slot 根目录，如 saves/world_001/slot_01/。
        """
        self._slot_dir = slot_dir
        self.history_shard.set_slot_dir(slot_dir)
        if self.long_term:
            self.long_term.set_slot_dir(slot_dir)
        if self.char_memory:
            self.char_memory.set_slot_dir(slot_dir)

    # ── 提示词 ──────────────────────────────────

    def set_summary_prompt(self, prompt: str) -> None:
        """设置长期记忆总结的 system prompt（由 world 提供）。"""
        self._summary_prompt = prompt

    def set_character_update_prompt(self, prompt: str) -> None:
        """设置角色记忆更新的 system prompt（由 world 提供）。"""
        self._character_update_prompt = prompt

    # ── 生命周期 ──────────────────────────────

    def init_session(self) -> None:
        """初始化 slot 的所有子存储。"""
        self.history_shard.init_session()
        if self.long_term:
            self.long_term.init_session()
        if self.char_memory:
            self.char_memory.init_session()

    def on_round_complete(self) -> int:
        """每轮完成通知。内部判断是否触发总结。

        Returns: 当前总轮数。
        """
        total = self.history_shard.on_round_complete()
        if self.long_term_enabled and total % self.shard_size == 0:
            start_round = total - self.shard_size + 1
            end_round = total
            logger.info(
                "MemorySystem: triggering summary for rounds %d-%d", start_round, end_round
            )
            self._pending_summaries.append((start_round, end_round))
        return total

    @property
    def has_pending_summary(self) -> bool:
        with self._pending_lock:
            return len(self._pending_summaries) > 0

    def consume_pending_summary(self) -> tuple[int, int] | None:
        """消费一个待处理的总结请求，返回 (start_round, end_round) 或 None。

        从队列头部取出，保证先进先出。
        """
        with self._pending_lock:
            return self._pending_summaries.popleft() if self._pending_summaries else None

    def consume_all_pending_summaries(self) -> list[tuple[int, int]]:
        """消费所有待处理总结请求，返回全部后清空队列。"""
        with self._pending_lock:
            pending = list(self._pending_summaries)
            self._pending_summaries.clear()
            return pending

    def clear_pending_summaries(self) -> None:
        """清空待处理的总结队列（公开接口，供外部安全调用）。"""
        with self._pending_lock:
            self._pending_summaries.clear()

    # ── LLM 上下文接口 ─────────────────────────

    def get_long_term_memories_text(self) -> str:
        """获取所有长期记忆摘要文本，注入到 LLM system 层。"""
        if not self.long_term:
            return ""
        return self.long_term.get_all_summaries_text()

    def get_recent_rounds(self, n: int | None = None) -> list["Message"]:
        """获取最近 N 轮完整对话消息。"""
        n = n or self.shard_size
        return self.history_shard.load_recent_messages(n)

    def get_scene_character_memories_text(self, names: list[str]) -> str:
        """获取场景中角色的记忆文本。"""
        if not self.char_memory:
            return ""
        return self.char_memory.get_scene_memories_text(names)

    def get_character_memory(self, name: str) -> CharacterMemory | None:
        """获取单个角色的完整记忆。"""
        if not self.char_memory:
            return None
        return self.char_memory.load(name)

    # ── 写入接口 ──────────────────────────────

    def append_message(self, message: "Message") -> None:
        """追加消息到当前分片。"""
        self.history_shard.append(message)

    def save_long_term_memory(
        self, memory_id: str,
        round_range: tuple[int, int], summary: str,
    ) -> None:
        """保存长期记忆摘要。"""
        if self.long_term:
            self.long_term.save(memory_id, round_range, summary)

    def save_character_memory(self, memory: CharacterMemory) -> None:
        """保存角色记忆。"""
        if self.char_memory:
            self.char_memory.save(memory)
