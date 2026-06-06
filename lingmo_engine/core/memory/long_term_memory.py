"""LongTermMemoryManager — 长期记忆总结的存储与读取。"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from lingmo_engine.core.memory.types import LongTermMemory

logger = logging.getLogger(__name__)


class LongTermMemoryManager:
    """管理长期记忆摘要的 Markdown 文件存储。

    每条长期记忆存储为 {slot_dir}/memory/long_term/{id}.md，
    使用 YAML frontmatter 记录元数据。
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

    def _memory_dir(self) -> Path:
        """返回 slot 的长期记忆目录。"""
        return Path(self._slot_dir) / "memory" / "long_term"

    def _file_path(self, memory_id: str) -> Path:
        """返回指定记忆 ID 的 Markdown 文件路径。"""
        # 防止路径遍历
        if any(c in memory_id for c in ("/", "\\", "..", "\x00")):
            raise ValueError(f"非法记忆 ID: {memory_id!r}")
        return self._memory_dir() / f"{memory_id}.md"

    def init_session(self) -> None:
        """初始化 slot 的长期记忆目录。"""
        self._memory_dir().mkdir(parents=True, exist_ok=True)

    def save(
        self,
        memory_id: str,
        round_range: tuple[int, int],
        summary: str,
    ) -> Path:
        """保存一条长期记忆为 Markdown 文件。

        Args:
            memory_id: 记忆 ID，如 "ltm_001"。
            round_range: 轮次范围 (start, end)。
            summary: 剧情总结内容。

        Returns:
            写入的文件路径。
        """
        self._memory_dir().mkdir(parents=True, exist_ok=True)
        from datetime import datetime, timezone
        import yaml
        created_at = datetime.now(timezone.utc).isoformat()
        meta = {
            "id": memory_id,
            "round_range": [round_range[0], round_range[1]],
            "created_at": created_at,
        }
        content = f"---\n{yaml.dump(meta, allow_unicode=True, sort_keys=False)}---\n\n{summary}\n"
        path = self._file_path(memory_id)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(path.parent))
        fd_closed = False
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(content)
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
        logger.info(
            "LongTermMemory saved: %s (%d-%d)", memory_id, round_range[0], round_range[1]
        )
        return path

    def load(self, memory_id: str) -> LongTermMemory | None:
        """加载单条长期记忆。

        Args:
            memory_id: 记忆 ID。

        Returns:
            找到时返回 LongTermMemory，否则返回 None。
        """
        path = self._file_path(memory_id)
        if not path.exists():
            return None
        return self._parse_file(path)

    def load_all(self) -> list[LongTermMemory]:
        """加载所有长期记忆，按 round_range 起始轮次排序。

        Returns:
            排序后的 LongTermMemory 列表。
        """
        mem_dir = self._memory_dir()
        if not mem_dir.exists():
            return []
        memories = []
        for md_file in sorted(mem_dir.glob("*.md")):
            mem = self._parse_file(md_file)
            if mem:
                memories.append(mem)
        memories.sort(key=lambda m: m.round_range[0])
        return memories

    def get_all_summaries_text(self) -> str:
        """获取所有长期记忆摘要的拼接文本，用于注入 LLM 上下文。

        Returns:
            格式化后的摘要文本，无记忆时返回空字符串。
        """
        memories = self.load_all()
        if not memories:
            return ""
        parts = ["## 长期记忆（剧情回顾）\n"]
        for mem in memories:
            parts.append(
                f"### 第{mem.round_range[0]}-{mem.round_range[1]}轮\n{mem.summary}\n"
            )
        return "\n".join(parts)

    def _parse_file(self, path: Path) -> LongTermMemory | None:
        """解析 Markdown 文件为 LongTermMemory。

        Args:
            path: Markdown 文件路径。

        Returns:
            解析成功时返回 LongTermMemory，否则返回 None。
        """
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            logger.warning("LongTermMemory: failed to read %s", path)
            return None

        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                import yaml
                try:
                    meta = yaml.safe_load(parts[1]) or {}
                except yaml.YAMLError:
                    meta = {}
                summary = parts[2].strip()
                round_range_raw = meta.get("round_range", [0, 0])
                return LongTermMemory(
                    id=meta.get("id", path.stem),
                    round_range=(round_range_raw[0], round_range_raw[1]),
                    summary=summary,
                    created_at=meta.get("created_at", ""),
                )
        # 无 frontmatter 回退
        return LongTermMemory(
            id=path.stem,
            round_range=(0, 0),
            summary=text.strip(),
            created_at="",
        )
