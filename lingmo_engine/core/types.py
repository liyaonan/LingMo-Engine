from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TypedDict, NotRequired, Union


def normalize_name(name: str) -> str:
    """归一化名称：移除分隔符和空白，统一小写。

    用于技能/装备等实体的模糊匹配，确保不同写法（如·-空格等）
    能正确匹配。统一字符集：ASCII空格、·(U+00B7)、-(U+002D)、
    _(U+005F)、・(U+30FB)。
    """
    return re.sub(r"[\s·\-_・]", "", name).lower()


def fuzzy_match_by_name(
    query: str,
    index: list[tuple[str, str, str]],
    threshold: float = 0.7,
) -> str | None:
    """在归一化索引中模糊匹配，返回匹配到的 ID 或 None。

    索引格式: [(id, 原始名称, 归一化名称), ...]
    匹配策略（逐级回退）：
      1. 归一化精确匹配
      2. 包含匹配（query 是 name 子串或反之）
      3. 字符重叠率匹配（阈值 threshold，默认 0.7）

    被 CharacterGenerator、SceneValidator、CombatPlugin 共用。
    """
    if not index:
        return None

    query_norm = normalize_name(query)
    if not query_norm:
        return None

    # 1. 归一化精确匹配
    for entry_id, _name, norm in index:
        if query_norm == norm:
            return entry_id

    # 2. 包含匹配（优先匹配更短的名称，即更精确的匹配）
    candidates: list[tuple[str, str, int]] = []
    for entry_id, _name, norm in index:
        if query_norm in norm or norm in query_norm:
            candidates.append((entry_id, _name, len(norm)))
    if candidates:
        candidates.sort(key=lambda x: x[2])
        return candidates[0][0]

    # 3. 字符重叠率匹配
    query_chars = set(query_norm)
    best_ratio = 0.0
    best_id: str | None = None
    for entry_id, _name, norm in index:
        norm_chars = set(norm)
        if not query_chars or not norm_chars:
            continue
        overlap = len(query_chars & norm_chars)
        ratio = overlap / max(len(query_chars | norm_chars), 1)
        if ratio > best_ratio:
            best_ratio = ratio
            best_id = entry_id

    if best_ratio >= threshold and best_id is not None:
        return best_id

    return None


class DisplayType(str, Enum):
    """ModuleResult 的展示类型，控制前端渲染行为。

    - SYSTEM: 系统消息（默认），不触发前端流终止
    - COMBAT_LOG: 战斗日志，以战斗面板样式展示
    - NARRATIVE: 叙述文本，会触发前端流终止（工具日志不应使用）
    - ENCOUNTER: 遭遇事件，展示敌人卡片
    """

    SYSTEM = "system"
    COMBAT_LOG = "combat_log"
    NARRATIVE = "narrative"
    ENCOUNTER = "encounter"

    def __str__(self) -> str:
        return self.value


class ActionUpdatePlayer(TypedDict):
    """_actions 类型: 更新玩家属性"""
    action: str  # "update_player"
    updates: dict[str, object]  # key-value pairs for player attributes


class ActionItemEntry(TypedDict):
    item_id: str
    quantity: int


class ActionAddItems(TypedDict):
    """_actions 类型: 添加物品到背包"""
    action: str  # "add_items"
    items: list[ActionItemEntry]


class ActionRemoveItems(TypedDict):
    """_actions 类型: 从背包移除物品"""
    action: str  # "remove_items"
    items: list[ActionItemEntry]


class ActionPublishMessage(TypedDict):
    """_actions 类型: 通过 MessageBus 发布消息"""
    action: str  # "publish_message"
    message: dict[str, object]  # role, content, content_blocks


class ActionGenerateNarrative(TypedDict):
    """_actions 类型: 触发生成叙述"""
    action: str  # "generate_narrative"
    prompt: str
    stream_type: NotRequired[str]  # "narrative" | "combat_narrative"
    fallback_text: NotRequired[str]


class ActionSaveState(TypedDict):
    """_actions 类型: 保存游戏状态"""
    action: str  # "save_state"


class ActionSendStateUpdate(TypedDict):
    """_actions 类型: 向前端推送状态更新"""
    action: str  # "send_state_update"


class ActionClearSceneEnemies(TypedDict):
    """_actions 类型: 清除场景敌人"""
    action: str  # "clear_scene_enemies"


class ActionRecallCharacterMemory(TypedDict):
    """_actions 类型: 拉取角色记忆"""
    action: str  # "recall_character_memory"
    character_name: str


class ActionUpdateCharacterMemory(TypedDict):
    """_actions 类型: 更新角色记忆"""
    action: str  # "update_character_memory"
    character_name: str
    shared_experiences: NotRequired[str]
    personal_events: NotRequired[str]
    opinions: NotRequired[str]


Action = Union[
    ActionUpdatePlayer,
    ActionAddItems,
    ActionRemoveItems,
    ActionPublishMessage,
    ActionGenerateNarrative,
    ActionSaveState,
    ActionSendStateUpdate,
    ActionClearSceneEnemies,
    ActionRecallCharacterMemory,
    ActionUpdateCharacterMemory,
]


@dataclass
class ToolParameter:
    name: str
    type: str = "string"
    description: str = ""
    required: bool = True
    enum: list[str] | None = None


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)
    plugin_name: str = ""

    def to_openai_schema(self) -> dict:
        params = {}
        required = []
        for p in self.parameters:
            entry: dict = {
                "type": p.type,
                "description": p.description,
            }
            if p.enum is not None:
                entry["enum"] = p.enum
            params[p.name] = entry
            if p.required:
                required.append(p.name)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": params,
                    "required": required,
                },
            },
        }


@dataclass
class ModuleResult:
    success: bool
    log: str = ""
    data: dict = field(default_factory=dict)
    display_type: DisplayType = DisplayType.SYSTEM


@dataclass
class EncounterEnemy:
    """遭遇中的单个敌人定义。source 区分 NPC（已有角色）与模板敌人（临时生成）。"""
    source: str = "hostile"           # "npc" | "hostile"
    template: str = ""                # 模板 ID（source=hostile 时必填）
    character_id: str = ""            # NPC 角色 ID（source=npc 时必填）
    name: str | None = None
    count: int = 1
    level: int = 1                    # 敌人等级（仅 source=hostile）
    aptitude: float = 0.5             # 资质 0.0-1.0（仅 source=hostile）
    aptitude_bias: dict = field(default_factory=dict)  # 模板属性偏向
    abilities: list[str] | None = None


@dataclass
class EncounterGroup:
    """一组敌人 = 前端一张可点击卡片"""
    name: str
    enemies: list[EncounterEnemy]


@dataclass
class SceneEncounters:
    """当前场景的遭遇状态"""
    groups: list[EncounterGroup]
    forced: bool = False
    narrative: str = ""

