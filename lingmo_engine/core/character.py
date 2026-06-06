"""角色统一数据模型。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar

logger = logging.getLogger(__name__)

# 历史字段代理 — 从 dataclass 字段迁移到 extra 后的兼容桥。
# 新世界应直接使用 char.extra["field"]，不应向此列表添加字段。
# TODO: 待所有调用者迁移到 extra 访问后移除此代理。
_PROXY_TO_EXTRA: frozenset[str] = frozenset({
    "spiritual_roots", "root_quality", "dao_name",
    "cultivation_stage", "cultivation_substage",
    "cultivation_path", "secondary_path",
    "race",
})

# from_dict 已知的顶层字段名（这些不会自动进入 extra）
_FROM_DICT_KNOWN_KEYS: frozenset[str] = frozenset(
    {
        # Character dataclass 字段
        "id", "name", "char_type", "is_alive", "level", "exp",
        "attrs", "summary", "hobbies", "personality", "tags",
        "background", "avatar", "location", "current_affairs",
        "faction", "relationships", "abilities", "equipment",
        "inventory", "loot_table", "temporary", "birthday",
        "last_updated", "age", "gender", "extra",
        # 旧格式别名（已特殊处理）
        "skills", "element_tags",
    }
    | set(_PROXY_TO_EXTRA)
)

_PROXY_DEFAULTS: dict[str, object] = {
    "spiritual_roots": [],
    "root_quality": "",
    "dao_name": "",
    "cultivation_stage": "",
    "cultivation_substage": "",
    "cultivation_path": "",
    "secondary_path": "",
    "race": "",
}


def _split_list_items(raw) -> list[str]:
    """将列表中逗号分隔的字符串元素拆分为独立元素。

    例如 ["a", "b,c,d"] → ["a", "b", "c", "d"]
    """
    if not isinstance(raw, list):
        if isinstance(raw, str):
            raw = [raw]
        else:
            return list(raw) if raw else []
    result = []
    for item in raw:
        if isinstance(item, str) and "," in item:
            result.extend(v.strip() for v in item.split(",") if v.strip())
        else:
            result.append(item)
    return result


def _normalize_inventory(raw) -> list[dict]:
    """将 inventory 列表标准化为 [{"item_id": ..., "quantity": N}] 格式。

    支持输入:
      - ["item_a", "item_b"] → [{"item_id": "item_a", "quantity": 1}, ...]
      - [{"item_id": "item_a", "quantity": 3}] → 原样保留
    """
    if not isinstance(raw, list):
        return []
    result = []
    for entry in raw:
        if isinstance(entry, str):
            result.append({"item_id": entry, "quantity": 1})
        elif isinstance(entry, dict):
            result.append(entry)
    return result


def _normalize_birthday(raw) -> str:
    """将生日数据标准化为 "YYYY/MM/DD" 字符串格式。

    兼容旧格式: {"year": 3, "month": 5, "day": 10} → "3/5/10"
    新格式: "782645/5/10" → 原样返回
    空值: None / "" / {} → ""
    """
    if not raw:
        return ""
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, dict):
        try:
            y = raw["year"]
            m = raw["month"]
            d = raw["day"]
            return f"{y}/{m}/{d}"
        except (KeyError, TypeError):
            return ""
    return ""


class CharacterType(Enum):
    PLAYER = "player"
    NPC = "npc"
    MONSTER = "monster"
    PET = "pet"


@dataclass
class Character:
    """完全同构的角色数据类。所有角色类型共享全部字段。"""
    id: int                         # 0 = 主角
    name: str
    char_type: CharacterType
    is_alive: bool = True
    level: int = 1
    exp: int = 0

    # 属性（由 character_schema.yaml 定义键名和默认值）
    attrs: dict[str, int] = field(default_factory=dict)

    # 角色画像
    summary: str = ""              # 实体查询索引简报，≤30字
    hobbies: str = ""              # 爱好
    personality: str = ""
    tags: list[str] = field(default_factory=list)
    background: str = ""
    avatar: str | None = None       # 头像文件路径，空则不显示头像区域

    # 世界状态
    location: str = ""
    current_affairs: list[str] = field(default_factory=list)
    faction: str = ""
    relationships: list[dict] = field(default_factory=list)

    # 能力与物品
    abilities: list[str] = field(default_factory=list)
    equipment: dict[str, str] = field(default_factory=dict)
    inventory: list[dict] = field(default_factory=list)
    loot_table: list[dict] | None = None

    # 临时角色标记（monster 战斗后释放，npc 持久化）
    temporary: bool = False

    # 生日（"YYYY/MM/DD" 格式，如 "782645/5/10"，空串表示未设置）
    birthday: str = ""

    # 状态同步时间戳（"YYYY/MM/DD" 格式，空串表示从未同步）
    last_updated: str = ""

    # 年龄（必填，0 表示未知）
    age: int = 0

    # 性别（male / female / unknown）
    gender: str = "unknown"

    # 自定义字段（World 通过 creation YAML 定义的额外属性，如种族）
    extra: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        """构造完成后，对已有专属属性进行 mastery cap 截断。"""
        self._enforce_mastery_caps()

    # 属性代理别名（旧属性名已重命名，保留兼容）
    _ALIASES: ClassVar[dict[str, str]] = {}

    # 修炼专属属性配置（由 world 在加载时通过 set_mastery_config 设置）
    _MASTERY_CONFIG: ClassVar[dict] = {}

    def __getattr__(self, name: str):
        """将未知属性读取代理到 attrs 或 extra 字典。

        优先级：_PROXY_TO_EXTRA 字段 → attrs 字典 → AttributeError
        """
        if name == "_ALIASES":
            raise AttributeError(name)
        # 历史字段代理到 extra（迁移桥）
        if name in _PROXY_TO_EXTRA:
            try:
                extra = object.__getattribute__(self, 'extra')
                return extra.get(name, _PROXY_DEFAULTS.get(name))
            except AttributeError:
                return _PROXY_DEFAULTS.get(name)
        name = self._ALIASES.get(name, name)
        if name in self.attrs:
            return self.attrs[name]
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def __setattr__(self, name: str, value):
        """属性写入代理：extra 字段 → dataclass 字段 → attrs 字典。"""
        # 历史字段代理到 extra（迁移桥）
        if name in _PROXY_TO_EXTRA:
            try:
                extra = object.__getattribute__(self, 'extra')
                extra[name] = value
            except AttributeError:
                # extra 尚未初始化（__init__ 早期阶段），走默认行为
                object.__setattr__(self, name, value)
            return
        # dataclass 字段始终走默认行为
        if name in self.__dataclass_fields__:
            object.__setattr__(self, name, value)
            return
        # 别名映射（def_ → def）
        name = self._ALIASES.get(name, name)
        # 已有 attrs 且 key 在 attrs 中 → 写入 attrs
        try:
            attrs = object.__getattribute__(self, 'attrs')
        except AttributeError:
            # attrs 尚未初始化（__init__ 早期阶段），走默认行为
            object.__setattr__(self, name, value)
            return
        if name in attrs:
            if not isinstance(value, int):
                logger.warning(
                    "attrs.%s 期望 int 类型，收到 %s，已自动转换", name, type(value).__name__
                )
                try:
                    value = int(float(value))
                except (ValueError, TypeError):
                    logger.error("attrs.%s 转换失败: %r，使用原值 0", name, value)
                    value = 0
            # 动态 mastery cap 截断
            cap = self._get_mastery_cap(name)
            if cap is not None and value > cap:
                value = cap
            attrs[name] = value
        else:
            object.__setattr__(self, name, value)

    def to_dict(self) -> dict:
        """序列化为字典（供前端 JSON 传输）。"""
        return {
            "id": self.id,
            "name": self.name,
            "char_type": self.char_type.value,
            "is_alive": self.is_alive,
            "level": self.level,
            "exp": self.exp,
            "attrs": dict(self.attrs),
            "summary": self.summary,
            "dao_name": self.extra.get("dao_name", ""),
            "hobbies": self.hobbies,
            "personality": self.personality,
            "tags": list(self.tags),
            "background": self.background,
            "avatar": self.avatar,
            "location": self.location,
            "current_affairs": list(self.current_affairs),
            "faction": self.faction,
            "relationships": list(self.relationships),
            "abilities": list(self.abilities),
            "spiritual_roots": list(self.extra.get("spiritual_roots", [])),
            "root_quality": self.extra.get("root_quality", ""),
            "equipment": dict(self.equipment),
            "inventory": list(self.inventory),
            "loot_table": list(self.loot_table) if self.loot_table else None,
            "temporary": self.temporary,
            "birthday": self.birthday,
            "last_updated": self.last_updated,
            "age": self.age,
            "gender": self.gender,
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Character:
        """从字典反序列化。

        兼容旧格式（顶层键 spiritual_roots/root_quality/dao_name）和新格式（extra 内）。
        """
        extra = dict(data.get("extra", {}))

        # 旧格式兼容：如果顶层有代理字段，迁移到 extra
        for key in _PROXY_TO_EXTRA:
            if key in data and data[key] not in ([], ""):
                extra[key] = data[key]

        # 收集其他未识别的顶层字段到 extra（如 clothing, appearance, faction_rank）
        for key in data:
            if key not in _FROM_DICT_KNOWN_KEYS and key not in extra:
                val = data[key]
                if val is not None and val != "" and val != []:
                    extra[key] = val

        # spiritual_roots 兼容 element_tags 旧名
        if "spiritual_roots" not in extra:
            old_roots = data.get("element_tags", [])
            if old_roots:
                extra["spiritual_roots"] = list(old_roots)

        return cls(
            id=data.get("id", -1),
            name=data.get("name", ""),
            char_type=CharacterType(data.get("char_type", "npc")),
            is_alive=data.get("is_alive", True),
            level=data.get("level", 1),
            exp=data.get("exp", 0),
            attrs=dict(data.get("attrs", {})),
            summary=data.get("summary", ""),
            hobbies=data.get("hobbies", ""),
            personality=data.get("personality", ""),
            tags=list(data.get("tags", [])),
            background=data.get("background", ""),
            avatar=data.get("avatar"),
            location=data.get("location", ""),
            current_affairs=list(data.get("current_affairs", [])),
            faction=data.get("faction", ""),
            relationships=(
                list(data.get("relationships", []))
                if isinstance(data.get("relationships", []), list)
                else []
            ),
            abilities=_split_list_items(data.get("abilities", data.get("skills", []))),
            equipment=dict(data.get("equipment", {})),
            inventory=_normalize_inventory(data.get("inventory", [])),
            loot_table=data.get("loot_table"),
            temporary=data.get("temporary", False),
            birthday=_normalize_birthday(data.get("birthday")),
            last_updated=data.get("last_updated", ""),
            age=data.get("age", 0),
            gender=data.get("gender") or (extra.get("gender", "unknown") if extra.get("gender") else "unknown"),
            extra=extra,
        )

    @classmethod
    def set_mastery_config(cls, config: dict, path_attr_map: dict[str, str]) -> None:
        """设置 mastery 配置。

        Args:
            config: mastery_rules 配置，如 {"max_boost": 0.20, "caps": {"main": 100, ...}}
            path_attr_map: 修炼道ID → 专属属性ID 的映射，
                           如 {"sword": "sword_intent", "magic": "magic_affinity", ...}
        """
        cls._MASTERY_CONFIG = {
            "rules": config,
            "path_attr_map": path_attr_map,
        }

    def _get_mastery_cap(self, attr_name: str) -> int | None:
        """获取专属属性的动态上限。非专属属性返回 None。"""
        if not self._MASTERY_CONFIG:
            return None
        path_attr_map = self._MASTERY_CONFIG.get("path_attr_map", {})
        caps = self._MASTERY_CONFIG.get("rules", {}).get("caps", {})

        # 检查属性是否是某个修炼道的专属属性
        if attr_name not in path_attr_map.values():
            return None

        main_path = self.extra.get("cultivation_path", "")
        secondary_path = self.extra.get("secondary_path", "")

        main_attr = path_attr_map.get(main_path, "")
        secondary_attr = path_attr_map.get(secondary_path, "") if secondary_path else ""

        if attr_name == main_attr:
            return caps.get("main", 100)
        if attr_name == secondary_attr:
            return caps.get("secondary", 60)
        return caps.get("other", 30)

    def _enforce_mastery_caps(self) -> None:
        """重新校验所有专属属性，截断超出当前 cap 的值。"""
        if not self._MASTERY_CONFIG:
            return
        path_attr_map = self._MASTERY_CONFIG.get("path_attr_map", {})
        for attr_name in path_attr_map.values():
            if attr_name in self.attrs:
                cap = self._get_mastery_cap(attr_name)
                if cap is not None and self.attrs[attr_name] > cap:
                    self.attrs[attr_name] = cap
