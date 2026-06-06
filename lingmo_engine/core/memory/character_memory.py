"""CharacterMemoryManager — 角色记忆的存储与读取。"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from lingmo_engine.core.memory.types import CharacterMemory

logger = logging.getLogger(__name__)


class CharacterMemoryManager:
    """管理每个角色的三栏结构化记忆。

    每个角色一个 JSON 文件，存储在 {slot_dir}/memory/characters/{name}.json。
    """

    def __init__(self) -> None:
        """初始化管理器。"""
        self._slot_dir = ""

    def set_slot_dir(self, slot_dir: str) -> None:
        """设置当前 slot 目录路径。

        Args:
            slot_dir: slot 根目录，如 saves/world_001/slot_01/。
        """
        self._slot_dir = slot_dir

    # ── 路径工具 ──────────────────────────────

    def _char_dir(self) -> Path:
        """返回 slot 的角色记忆目录。"""
        return Path(self._slot_dir) / "memory" / "characters"

    def _file_path(self, character_name: str) -> Path:
        """返回指定角色记忆的 JSON 文件路径。"""
        safe_name = character_name.replace("/", "_").replace("\\", "_")
        return self._char_dir() / f"{safe_name}.json"

    # ── 会话生命周期 ──────────────────────────

    def init_session(self) -> None:
        """初始化 slot 的角色记忆目录。"""
        self._char_dir().mkdir(parents=True, exist_ok=True)

    # ── 写入 ──────────────────────────────────

    def save(self, memory: CharacterMemory) -> None:
        """保存角色记忆（原子写入）。

        Args:
            memory: 角色记忆对象。
        """
        self._char_dir().mkdir(parents=True, exist_ok=True)
        path = self._file_path(memory.character_name)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(path.parent))
        fd_closed = False
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(memory.to_dict(), f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            fd_closed = True
            os.replace(tmp_path, str(path))
        except Exception:
            if not fd_closed:
                try:
                    os.close(tmp_fd)
                except OSError:
                    pass
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        logger.info("CharacterMemory saved: %s (round %d)", memory.character_name, memory.last_updated_round)

    # ── 读取 ──────────────────────────────────

    def load(self, character_name: str) -> CharacterMemory | None:
        """加载指定角色的记忆，不存在时返回 None。

        Args:
            character_name: 角色名。

        Returns:
            找到时返回 CharacterMemory，否则返回 None。
        """
        path = self._file_path(character_name)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return CharacterMemory.from_dict(json.load(f))
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("CharacterMemory: failed to load %s: %s", path, e)
            return None

    def delete(self, character_name: str) -> None:
        """删除角色记忆文件。

        Args:
            character_name: 角色名。
        """
        path = self._file_path(character_name)
        if path.exists():
            path.unlink()

    def list_all_names(self) -> list[str]:
        """列出所有已有记忆的角色名。

        文件名 {name}.json 即为角色名，无需解析文件内容。
        """
        char_dir = self._char_dir()
        if not char_dir.exists():
            return []
        return [f.stem for f in char_dir.glob("*.json")]

    # ── 场景上下文 ────────────────────────────

    def get_scene_memories_text(self, names: list[str]) -> str:
        """获取场景中角色的记忆文本，用于注入 LLM 上下文。

        只加载指定角色列表的记忆，跳过不存在的角色。
        返回格式化的 Markdown 文本，包含共同经历、个人大事和内心真实想法。

        Args:
            names: 当前场景中出现的角色名列表。

        Returns:
            格式化后的记忆文本，无任何角色记忆时返回空字符串。
        """
        parts = []
        for name in names:
            mem = self.load(name)
            if mem is None:
                continue
            parts.append(f"### {name} 的记忆")
            if mem.shared_experiences:
                parts.append(f"与主角的共同经历：{mem.shared_experiences}")
            if mem.personal_events:
                parts.append(f"个人大事：{mem.personal_events}")
            if mem.opinions:
                parts.append(f"内心真实想法：{mem.opinions}")
            parts.append("")
        return "\n".join(parts) if parts else ""
