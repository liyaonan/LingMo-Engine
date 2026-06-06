# lingmo_engine/core/page_snapshot.py
"""PageSnapshot — 单个 Page 处理前的完整状态快照，用于重试回滚。"""
from __future__ import annotations

import copy
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lingmo_engine.core.game_state import GameState
    from lingmo_engine.core.character_manager import CharacterManager

logger = logging.getLogger(__name__)


@dataclass
class PageSnapshot:
    """单个 Page 处理前的完整状态快照，用于重试回滚。"""

    page_id: str
    user_input: str

    # --- 内存状态快照 ---
    game_state_data: dict
    characters_data: dict[int, dict]
    custom_abilities: dict
    custom_items: dict
    llm_history: list[dict]
    dirty_set: set[int]

    # --- 记忆系统快照 ---
    memory_total_rounds: int
    memory_files_backup: dict[str, str]   # {相对路径: 文件内容}
    memory_existed_files: set[str]

    # --- 消息分片追踪 ---
    shard_line_count: int
    shard_file_path: str

    created_at: float = field(default_factory=time.time)


def create_page_snapshot(
    page_id: str,
    user_input: str,
    game_state: "GameState",
    character_manager: "CharacterManager",
    llm_history: list[dict],
    memory_system=None,
) -> PageSnapshot:
    """在 Page 处理前创建完整快照。"""
    # 1. 内存状态
    with game_state._lock:
        game_state_data = copy.deepcopy(game_state._data)
    custom_abilities = copy.deepcopy(game_state._custom_abilities)
    custom_items = copy.deepcopy(game_state._custom_items)

    characters_data = {}
    dirty_set = set(character_manager._dirty)
    for cid, char in character_manager._characters.items():
        characters_data[cid] = char.to_dict()

    llm_history_copy = copy.deepcopy(llm_history)

    # 2. 记忆系统
    memory_total_rounds = 0
    memory_files_backup: dict[str, str] = {}
    memory_existed_files: set[str] = set()
    shard_line_count = 0
    shard_file_path = ""

    if memory_system:
        index = memory_system.history_shard.load_index()
        memory_total_rounds = index.total_rounds

        # 备份记忆文件
        slot_dir = Path(memory_system._slot_dir)
        memory_dir = slot_dir / "memory"
        if memory_dir.exists():
            for fpath in memory_dir.rglob("*"):
                if fpath.is_file():
                    rel = str(fpath.relative_to(slot_dir))
                    try:
                        memory_files_backup[rel] = fpath.read_text(encoding="utf-8")
                        memory_existed_files.add(rel)
                    except Exception:
                        logger.warning("PageSnapshot: 无法读取记忆文件 %s", rel, exc_info=True)

        # 消息分片追踪
        try:
            active_shard = memory_system.history_shard._active_shard_path()
            shard_file_path = str(active_shard)
            if active_shard.exists():
                with open(active_shard, "r", encoding="utf-8") as f:
                    shard_line_count = sum(1 for _ in f)
        except Exception:
            logger.debug("PageSnapshot: 无活跃分片，跳过分片追踪")

    return PageSnapshot(
        page_id=page_id,
        user_input=user_input,
        game_state_data=game_state_data,
        characters_data=characters_data,
        custom_abilities=custom_abilities,
        custom_items=custom_items,
        llm_history=llm_history_copy,
        dirty_set=dirty_set,
        memory_total_rounds=memory_total_rounds,
        memory_files_backup=memory_files_backup,
        memory_existed_files=memory_existed_files,
        shard_line_count=shard_line_count,
        shard_file_path=shard_file_path,
    )


def restore_page_snapshot(
    snapshot: PageSnapshot,
    game_state: "GameState",
    character_manager: "CharacterManager",
    llm_history_ref: list,
    memory_system=None,
) -> None:
    """从快照恢复所有状态。"""
    from lingmo_engine.core.character import Character

    logger.info(
        "PageSnapshot: 开始恢复 page_id=%s (快照创建于 %.1fs 前)",
        snapshot.page_id,
        time.time() - snapshot.created_at,
    )

    # 1. 恢复 GameState（_data + _custom_abilities + _custom_items 统一加锁）
    with game_state._lock:
        game_state._data = copy.deepcopy(snapshot.game_state_data)
        game_state._custom_abilities = copy.deepcopy(snapshot.custom_abilities)
        game_state._custom_items = copy.deepcopy(snapshot.custom_items)

    # 2. 恢复 CharacterManager
    character_manager._characters.clear()
    for cid, data in snapshot.characters_data.items():
        character_manager._characters[cid] = Character.from_dict(data)
    character_manager._dirty = set(snapshot.dirty_set)

    # 3. 恢复 LLM 对话历史（原地修改列表）
    llm_history_ref.clear()
    llm_history_ref.extend(copy.deepcopy(snapshot.llm_history))

    # 4. 恢复记忆系统
    if memory_system and snapshot.memory_files_backup:
        slot_dir = Path(memory_system._slot_dir)

        # 4a. 恢复记忆文件：删除新增文件 + 恢复被修改的文件
        memory_dir = slot_dir / "memory"
        if memory_dir.exists():
            for fpath in memory_dir.rglob("*"):
                if fpath.is_file():
                    rel = str(fpath.relative_to(slot_dir))
                    if rel not in snapshot.memory_existed_files:
                        fpath.unlink()
                        logger.debug("PageSnapshot: 删除新增记忆文件 %s", rel)

        for rel, content in snapshot.memory_files_backup.items():
            fpath = slot_dir / rel
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content, encoding="utf-8")

        # 4b. 先截断消息分片（截断是幂等的，崩溃后可重试）
        if snapshot.shard_file_path:
            shard_path = Path(snapshot.shard_file_path)
            if shard_path.exists():
                lines = shard_path.read_text(encoding="utf-8").splitlines(keepends=True)
                if len(lines) > snapshot.shard_line_count:
                    truncated = "".join(lines[: snapshot.shard_line_count])
                    shard_path.write_text(truncated, encoding="utf-8")
                    logger.info(
                        "PageSnapshot: 截断分片 %s: %d → %d 行",
                        shard_path.name,
                        len(lines),
                        snapshot.shard_line_count,
                    )

        # 4c. 再恢复轮次计数器（确保分片已截断后再更新索引）
        index = memory_system.history_shard.load_index()
        index.total_rounds = snapshot.memory_total_rounds
        memory_system.history_shard._save_index(index)

    logger.info("PageSnapshot: 恢复完成 page_id=%s", snapshot.page_id)