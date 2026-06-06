"""记忆系统数据模型定义。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LongTermMemory:
    """单条长期记忆 — N 轮对话的剧情总结。"""
    id: str                          # 如 "ltm_003"
    round_range: tuple[int, int]     # (start_round, end_round)
    summary: str                     # 自然语言剧情总结
    created_at: str                  # ISO 时间戳


@dataclass
class CharacterMemory:
    """单个角色的记忆 — 三栏结构化字段。"""
    character_name: str
    shared_experiences: str          # 与主角的共同经历
    personal_events: str             # 该角色身上发生的大事
    opinions: str                    # 角色内心真实想法与隐秘态度
    last_updated_round: int

    def to_dict(self) -> dict:
        return {
            "character_name": self.character_name,
            "shared_experiences": self.shared_experiences,
            "personal_events": self.personal_events,
            "opinions": self.opinions,
            "last_updated_round": self.last_updated_round,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CharacterMemory":
        return cls(
            character_name=data["character_name"],
            shared_experiences=data.get("shared_experiences", ""),
            personal_events=data.get("personal_events", ""),
            opinions=data.get("opinions", ""),
            last_updated_round=data.get("last_updated_round", 0),
        )


@dataclass
class ShardEntry:
    """单个分片的索引条目。"""
    shard_id: int
    round_range: tuple[int, int]     # (start_round, end_round)
    file: str                        # 文件名，如 "shard_0001.jsonl"
    summary_id: str | None = None    # 关联的长期记忆 ID


@dataclass
class ShardIndex:
    """分片索引 — 持久化到 shard_index.json。"""
    session_id: str
    shard_size: int
    total_rounds: int
    shards: list[ShardEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "shard_size": self.shard_size,
            "total_rounds": self.total_rounds,
            "shards": [
                {
                    "shard_id": s.shard_id,
                    "round_range": list(s.round_range),
                    "file": s.file,
                    "summary_id": s.summary_id,
                }
                for s in self.shards
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ShardIndex":
        shards = [
            ShardEntry(
                shard_id=s["shard_id"],
                round_range=tuple(s["round_range"]),
                file=s["file"],
                summary_id=s.get("summary_id"),
            )
            for s in data.get("shards", [])
        ]
        return cls(
            session_id=data["session_id"],
            shard_size=data["shard_size"],
            total_rounds=data["total_rounds"],
            shards=shards,
        )

    @property
    def current_shard(self) -> ShardEntry | None:
        """返回当前活跃分片（最后一个），无分片时返回 None。"""
        return self.shards[-1] if self.shards else None
