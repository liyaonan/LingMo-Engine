"""HistoryShardManager — 对话历史分片存储与读取。"""
from __future__ import annotations

import json
import logging
import os
import threading
import tempfile
from pathlib import Path

from lingmo_engine.core.message import Message
from lingmo_engine.core.memory.types import ShardIndex, ShardEntry

logger = logging.getLogger(__name__)


class HistoryShardManager:
    """管理对话历史的 JSONL 分片存储。

    每个 slot 的消息按 N 轮分片存储在 {slot_dir}/messages/ 下。
    分片索引维护在 shard_index.json 中。
    """

    def __init__(self, shard_size: int = 50) -> None:
        self._slot_dir = ""
        self._shard_size = shard_size
        self._lock = threading.Lock()

    def set_slot_dir(self, slot_dir: str) -> None:
        """设置当前 slot 目录路径。

        Args:
            slot_dir: slot 根目录，如 saves/world_001/slot_01/。
        """
        self._slot_dir = slot_dir

    # ── 路径工具 ──────────────────────────────

    def _messages_dir(self) -> Path:
        return Path(self._slot_dir) / "messages"

    def _index_path(self) -> Path:
        return self._messages_dir() / "shard_index.json"

    def _shard_path(self, shard_id: int) -> Path:
        filename = f"shard_{shard_id:04d}.jsonl"
        return self._messages_dir() / filename

    def _active_shard_path(self) -> Path:
        """返回当前活跃（最后一个）分片的路径。无分片时触发异常。"""
        index = self.load_index()
        shard = index.current_shard
        if shard is None:
            raise RuntimeError(f"No active shard for slot {self._slot_dir}")
        return self._messages_dir() / shard.file

    # ── 索引管理 ──────────────────────────────

    def load_index(self) -> ShardIndex:
        """加载分片索引，不存在时返回空索引。"""
        path = self._index_path()
        if not path.exists():
            session_id = Path(self._slot_dir).name
            return ShardIndex(session_id=session_id, shard_size=self._shard_size, total_rounds=0)
        with open(path, "r", encoding="utf-8") as f:
            return ShardIndex.from_dict(json.load(f))

    def _atomic_write(self, path: Path, content: str) -> None:
        """原子写入文件：写入临时文件 → fsync → rename。"""
        path.parent.mkdir(parents=True, exist_ok=True)
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

    def _save_index(self, index: ShardIndex) -> None:
        """原子写入分片索引。"""
        path = self._index_path()
        data = json.dumps(index.to_dict(), ensure_ascii=False, indent=2)
        self._atomic_write(path, data)

    # ── 会话生命周期 ──────────────────────────

    def init_session(self) -> None:
        """初始化 slot 的消息目录和第一个分片。"""
        msgs_dir = self._messages_dir()
        msgs_dir.mkdir(parents=True, exist_ok=True)
        index = self.load_index()
        if not index.shards:
            entry = ShardEntry(
                shard_id=1,
                round_range=(1, self._shard_size),
                file="shard_0001.jsonl",
            )
            index.shards.append(entry)
            index.total_rounds = 0
            self._save_index(index)
            self._shard_path(1).touch()
            logger.info("HistoryShard: session %s initialized, shard 1 created",
                        Path(self._slot_dir).name)

    # ── 轮次计数 ──────────────────────────────

    def on_round_complete(self) -> int:
        """每轮完成时调用，返回当前总轮数。

        如果总轮数是 shard_size 的倍数，触发分片封口并创建新分片。
        """
        with self._lock:
            index = self.load_index()
            index.total_rounds += 1

            if index.total_rounds % index.shard_size == 0:
                self._seal_and_create(index)

            self._save_index(index)
            return index.total_rounds

    def _seal_and_create(self, index: ShardIndex) -> None:
        """封口当前分片，创建下一个分片。"""
        next_id = len(index.shards) + 1
        start_round = index.total_rounds + 1
        end_round = index.total_rounds + self._shard_size
        entry = ShardEntry(
            shard_id=next_id,
            round_range=(start_round, end_round),
            file=f"shard_{next_id:04d}.jsonl",
        )
        index.shards.append(entry)
        new_path = self._shard_path(next_id)
        new_path.touch()
        logger.info(
            "HistoryShard: sealed shard %d, created shard %d (rounds %d-%d)",
            next_id - 1, next_id, start_round, end_round,
        )

    # ── 写入 ──────────────────────────────────

    def append(self, message: Message) -> None:
        """追加一条消息到当前活跃分片（直接 fsync 追加）。

        JSONL 每行为独立 JSON 对象，崩溃时最多产生一行不完整结尾。
        load_shard() 读取时会跳过损坏行，无需完整文件原子替换。
        """
        with self._lock:
            msg_path = self._active_shard_path()
            line = json.dumps(message.to_json(), ensure_ascii=False) + "\n"
            with open(msg_path, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())

    def update_message(self, message_id: str, updater) -> bool:
        """按 ID 查找消息并原地更新。

        遍历所有分片，找到目标消息后调用 updater(msg) 修改，
        然后原子重写该分片文件。返回是否找到并更新成功。

        updater 签名为 (Message) -> None，例如 msg.mark_deleted()。
        """
        with self._lock:
            return self._update_message_locked(message_id, updater)

    def _update_message_locked(self, message_id: str, updater) -> bool:
        index = self.load_index()
        for shard_entry in index.shards:
            path = self._shard_path(shard_entry.shard_id)
            if not path.exists():
                continue
            updated = False
            lines_out = []
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        lines_out.append(line)
                        continue
                    if data.get("id") == message_id:
                        msg = Message.from_json(data)
                        updater(msg)
                        lines_out.append(json.dumps(msg.to_json(), ensure_ascii=False))
                        updated = True
                    else:
                        lines_out.append(line)
            if updated:
                content = "\n".join(lines_out) + "\n"
                self._atomic_write(path, content)
                return True
        return False

    # ── 读取 ──────────────────────────────────

    def load_shard(self, shard_id: int) -> list[Message]:
        """加载指定分片的全部消息。"""
        path = self._shard_path(shard_id)
        if not path.exists():
            return []
        messages = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        messages.append(Message.from_json(json.loads(line)))
                    except json.JSONDecodeError:
                        logger.warning("HistoryShard: skip corrupted line in %s", path)
        return messages

    def load_all_messages(self) -> list[Message]:
        """加载所有分片的全部消息（按时间顺序）。"""
        index = self.load_index()
        if not index.shards:
            return []
        all_messages = []
        for shard in index.shards:
            msgs = self.load_shard(shard.shard_id)
            all_messages.extend(msgs)
        return all_messages

    def load_recent_messages(self, n: int) -> list[Message]:
        """加载最近 N 轮的全部消息（按 role="user" 的消息计数轮次边界）。

        每轮恰好有一条 user 消息。从后往前统计 user 消息数，
        截取最近 N 个 user 消息及其之后的所有消息返回。

        无 user 消息时回退到返回最后 N 条消息。
        """
        all_messages = self.load_all_messages()
        if not all_messages:
            return []

        user_indices = [i for i, m in enumerate(all_messages) if m.role == "user"]
        if len(user_indices) == 0:
            return all_messages[-n:] if len(all_messages) > n else all_messages
        if len(user_indices) > n:
            return all_messages[user_indices[-n]:]
        return all_messages

    def link_summary(self, shard_id: int, summary_id: str) -> None:
        """将分片与长期记忆摘要关联。"""
        index = self.load_index()
        for shard in index.shards:
            if shard.shard_id == shard_id:
                shard.summary_id = summary_id
                break
        self._save_index(index)
