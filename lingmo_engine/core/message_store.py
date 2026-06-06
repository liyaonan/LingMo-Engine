"""MessageStore — 消息 JSONL 持久化的唯一入口。

每条消息一行 JSON，原子追加。编辑/删除时重写整个文件（消息量 <500 时无性能问题）。
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import threading
from pathlib import Path

from lingmo_engine.core.message import Message

logger = logging.getLogger(__name__)


class MessageStore:
    """消息持久化存储 — JSONL 格式，按 slot_dir 分目录"""

    def __init__(self, slot_dir: str = "", shard_manager=None) -> None:
        self._slot_dir = slot_dir
        self._shard_manager = shard_manager  # HistoryShardManager 或 None（向后兼容）
        self._write_lock = threading.Lock()

    def set_slot_dir(self, slot_dir: str) -> None:
        """运行时切换 slot 目录。"""
        self._slot_dir = slot_dir
        if self._shard_manager:
            self._shard_manager.set_slot_dir(slot_dir)

    # ── 路径管理 ──────────────────────────────

    def _messages_dir(self) -> str:
        return os.path.join(self._slot_dir, "messages")

    def _messages_path(self) -> str:
        return os.path.join(self._messages_dir(), "messages.jsonl")

    # ── 会话生命周期 ──────────────────────────

    def init_session(self, _session_id: str = "") -> None:
        """创建存档目录和空 JSONL 文件。分片模式时委托给 shard_manager。

        _session_id 参数保留用于向后兼容，不再参与路径计算。
        """
        if self._shard_manager is not None:
            self._shard_manager.init_session()
            return
        os.makedirs(self._messages_dir(), exist_ok=True)
        msg_path = self._messages_path()
        if not os.path.exists(msg_path):
            Path(msg_path).touch()
        logger.info("MessageStore: slot %s initialized", self._slot_dir)

    def delete_session(self) -> None:
        """删除消息持久化数据（仅 messages/ 子目录）。"""
        msgs_dir = self._messages_dir()
        if os.path.exists(msgs_dir):
            shutil.rmtree(msgs_dir)
        logger.info("MessageStore: messages deleted for slot %s", self._slot_dir)

    # ── 写入 ──────────────────────────────────

    def append(self, message: Message) -> None:
        """原子追加一行 JSON 到 JSONL（带 fsync 保证崩溃安全）。

        如果 shard_manager 已设置，委托给分片管理器。
        message.session_id 仅用于 shard_manager 委托，不参与路径计算。
        """
        if self._shard_manager is not None:
            self._shard_manager.append(message)
            return
        msg_path = self._messages_path()
        line = json.dumps(message.to_json(), ensure_ascii=False) + "\n"
        with self._write_lock:
            # 直接追加模式，避免 copy2 全量复制
            os.makedirs(self._messages_dir(), exist_ok=True)
            with open(msg_path, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())

    def _read_all_lines(self) -> list[dict]:
        """读取 JSONL 全部行，返回 dict 列表。"""
        msg_path = self._messages_path()
        if not os.path.exists(msg_path):
            return []
        lines = []
        with open(msg_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        lines.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning("MessageStore: skip corrupted line in %s", msg_path)
        return lines

    def _write_all_lines(self, lines: list[dict]) -> None:
        """原子写入全部行到 JSONL（带 fsync 保证崩溃安全）。"""
        msg_path = self._messages_path()
        with self._write_lock:
            tmp_fd, tmp_path = tempfile.mkstemp(dir=self._messages_dir())
            fd_closed = False
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    for line_data in lines:
                        f.write(json.dumps(line_data, ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                fd_closed = True
                os.replace(tmp_path, msg_path)
            except Exception:
                if not fd_closed:
                    try:
                        os.close(tmp_fd)
                    except OSError:
                        pass
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise

    def update(self, message_id: str, new_content: str) -> Message | None:
        """编辑消息：更新消息内容并写回持久化存储。"""
        if self._shard_manager is not None:
            updated = [None]
            def _updater(m):
                m.edit(new_content)
                updated[0] = m
            if self._shard_manager.update_message(message_id, _updater):
                return updated[0]
            return None
        lines = self._read_all_lines()
        for i, data in enumerate(lines):
            if data.get("id") == message_id:
                msg = Message.from_json(data)
                msg.edit(new_content)
                lines[i] = msg.to_json()
                self._write_all_lines(lines)
                return msg
        return None

    def mark_deleted(self, message_id: str) -> bool:
        """逻辑删除消息（status=DELETED）。"""
        if self._shard_manager is not None:
            return self._shard_manager.update_message(message_id, lambda m: m.mark_deleted())
        lines = self._read_all_lines()
        for i, data in enumerate(lines):
            if data.get("id") == message_id:
                msg = Message.from_json(data)
                msg.mark_deleted()
                lines[i] = msg.to_json()
                self._write_all_lines(lines)
                return True
        return False

    # ── 读取 ──────────────────────────────────

    def load_all(self) -> list[Message]:
        """读取全部消息（按 JSONL 行顺序，即追加顺序）。

        分片模式时委托给 HistoryShardManager 从 shard_*.jsonl 文件读取。
        """
        if self._shard_manager is not None:
            return self._shard_manager.load_all_messages()
        lines = self._read_all_lines()
        return [Message.from_json(d) for d in lines]

    def load_recent(self, n: int) -> list[Message]:
        """加载最近 N 轮的消息（分片模式时委托给 shard_manager）。"""
        if self._shard_manager is not None:
            return self._shard_manager.load_recent_messages(n)
        all_msgs = self.load_all()
        user_indices = [i for i, m in enumerate(all_msgs) if m.role == "user"]
        if len(user_indices) == 0:
            return all_msgs[-n:] if len(all_msgs) > n else all_msgs
        if len(user_indices) > n:
            return all_msgs[user_indices[-n]:]
        return all_msgs

    def load_page(self, page_id: str) -> list[Message]:
        """读取某个 Page 的全部消息。"""
        all_msgs = self.load_all()
        return [m for m in all_msgs if m.page_id == page_id]

    def query(self, **filters) -> list[Message]:
        """按条件过滤消息。支持 role, status 过滤。"""
        all_msgs = self.load_all()
        for key, value in filters.items():
            if key == "role":
                all_msgs = [m for m in all_msgs if m.role == value]
            elif key == "status":
                all_msgs = [m for m in all_msgs if m.status == value]
        return all_msgs
