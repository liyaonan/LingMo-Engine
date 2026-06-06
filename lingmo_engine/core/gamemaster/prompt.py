"""系统提示词、上下文提示与消息构建。

消息结构（按缓存稳定性排列）:
  [0] system: HEAD_ANCHORS       — 真正静态，永不改变
  [1] system: WORLD_DATA         — 半静态，LLM创作内容时才变更
  [2] system: ENTITY_INDEX       — 半静态，实体索引+已查询缓存
  [3] system: SEMI_STATIC_PLUGINS — 半静态，插件指引/模板（session期间不变）
  [4] system: COT_THINKING_GUIDE — 静态思考引导（session期间不变）
  [5] system: LONG_TERM_MEMORY   — 长期记忆摘要
  [6..K] history                 — 最近N轮对话（前缀匹配缓存）
  [K+1] system: DYNAMIC_CONTEXT  — 动态上下文（场景记忆+状态+位置+提醒+提示）
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lingmo_engine.core.game_state import GameState
    from lingmo_engine.core.plugin_registry import PluginRegistry
    from lingmo_engine.core.gamemaster.prompt_composer import PromptComposer

logger = logging.getLogger(__name__)


def build_system_prompt(prompt_composer: "PromptComposer") -> str:
    """构建 HEAD_ANCHORS — 仅返回真正静态的提示词文件内容。

    这些内容整个 session 永不改变，最大化前缀缓存命中率。
    """
    return prompt_composer.head_prompt


def build_dynamic_state_prompt(
    plugins: "PluginRegistry",
    state: "GameState",
) -> str:
    """构建动态状态消息 — 每轮可能变化的内容。

    包含：玩家名 + 非实体插件的 system prompt + 地图位置详情。
    实体查询插件的 prompt 由 build_entity_index_prompt 单独处理。
    """
    parts = []

    cm = getattr(state, 'character_manager', None)
    if cm:
        player = cm.player
        parts.append(f"当前主角：{player.name}")
        parts.append(
            f"【叙事人称】{player.name} 是玩家操控的角色。"
            f"正文剧情中必须始终使用「你」来指代 {player.name}，"
            f"绝对禁止使用「他」「她」「它」或「{player.name}」来叙述玩家视角的内容。"
        )
    else:
        player_name = state.data.get("player", {}).get("name", "")
        if player_name:
            parts.append(f"当前主角：{player_name}")
            parts.append(
                f"【叙事人称】{player_name} 是玩家操控的角色。"
                f"正文剧情中必须始终使用「你」来指代 {player_name}，"
                f"绝对禁止使用「他」「她」「它」或「{player_name}」来叙述玩家视角的内容。"
            )

    # 收集非 entity_query 插件的 system prompt
    for p in plugins.get_all_system_prompts():
        if p.startswith("[实体索引]"):
            continue
        parts.append(p)

    # 注入 MapPlugin 位置详情（从 semi_static 层拆分出，避免移动破坏前缀）
    loc_detail = plugins.get_location_detail_prompt()
    if loc_detail:
        parts.append(loc_detail)

    return "\n\n".join(parts) if parts else ""


def build_entity_index_prompt(
    plugins: "PluginRegistry",
) -> str:
    """构建 ENTITY_INDEX 消息 — 半静态实体索引 + 已查询缓存。

    只收集以 [实体索引] 开头的 prompt（来自 entity_query 插件），
    放在 WORLD_DATA 之后利用前缀缓存。
    """
    for p in plugins.get_all_system_prompts():
        if p.startswith("[实体索引]"):
            return p
    return ""


def build_semi_static_prompt(
    plugins: "PluginRegistry",
    skill_manager=None,
) -> str:
    """构建 SEMI_STATIC_PLUGINS 消息 — 低频变化的插件提示词。

    放在 HISTORY 之前以利用前缀缓存。该层每轮重建：大部分轮次内容不变（缓存命中），
    偶尔变化时（如玩家移动导致地图更新）缓存失效一轮后恢复，属可接受的 trade-off。

    Args:
        plugins: 插件注册表
        skill_manager: 可选的 SkillManager，非 None 时合并 base_skills
    """
    parts = []

    # base_skills 始终排在插件提示词之前
    if skill_manager:
        base = skill_manager.load_base_skills()
        if base:
            parts.append(base)

    parts.extend(plugins.get_all_semi_static_prompts())
    return "\n\n".join(parts) if parts else ""


def render_tail_condensed(
    template: str,
    state: "GameState",
    plugins: "PluginRegistry",
) -> str:
    """渲染 tail_condensed 模板中的动态变量。

    支持:
    - {{player_summary}} → 玩家状态摘要
    - {{location_summary}} → 当前位置摘要
    - {{nearby_summary}} → 附近角色列表
    """
    if "{{" not in template:
        return template

    result = template
    if "{{player_summary}}" in result:
        result = result.replace("{{player_summary}}", _build_player_summary(state))
    if "{{location_summary}}" in result:
        result = result.replace("{{location_summary}}", _build_location_summary(state, plugins))
    if "{{nearby_summary}}" in result:
        result = result.replace("{{nearby_summary}}", _build_nearby_summary(state))
    return result


def _build_player_summary(state: "GameState") -> str:
    cm = getattr(state, 'character_manager', None)
    if cm is None:
        player = state.data.get("player", {})
        name = player.get("name", "未知")
        return f"[玩家] {name}" if name != "未知" else ""

    player = cm.player
    schema = getattr(cm, '_attributes_schema', None) or {}
    attrs_schema = schema.get('attributes', {})

    # 第一行：名称、等级、标签
    header = f"[玩家] {player.name} | Lv{player.level}"
    tags = getattr(player, 'tags', [])
    if tags:
        header += f" | {' · '.join(tags)}"

    # 按配对关系组织属性：pair 类型只显示一次 "当前/上限"
    paired = set()
    lines = [header]
    attr_parts: list[str] = []

    for key, val in player.attrs.items():
        if key in paired:
            continue
        attr_def = attrs_schema.get(key, {})
        pair_key = attr_def.get('pair', '')
        label = attr_def.get('label', key)

        if pair_key and pair_key in player.attrs:
            paired.add(pair_key)
            # 确保 max_ 开头的属性作为上限，始终用基础属性名显示
            if key.startswith("max_"):
                pair_def = attrs_schema.get(pair_key, {})
                attr_parts.append(f"{pair_def.get('label', pair_key)}: {player.attrs[pair_key]}/{val}")
            else:
                attr_parts.append(f"{label}: {val}/{player.attrs[pair_key]}")
        else:
            attr_parts.append(f"{label}: {val}")

    if attr_parts:
        lines.append(" | ".join(attr_parts))

    # 追加关系信息
    if player.relationships:
        rel_parts = []
        for rel in player.relationships:
            tid = rel.get("target_id")
            other = cm.get(tid) if cm else None
            other_name = other.name if other else f"id={tid}"
            label = rel.get("label", "")
            desc = rel.get("desc", "")
            desc_part = f" — {desc}" if desc else ""
            rel_parts.append(f"{other_name}({tid}): {label}{desc_part}")
        lines.append("【关系】" + " | ".join(rel_parts))

    # 装备叙事效果 — 注入到玩家摘要中影响 LLM 描写
    narrative_lines = _build_equipment_narrative(state)
    if narrative_lines:
        lines.append("【装扮】" + "；".join(narrative_lines))

    return "\n".join(lines)


def _build_equipment_narrative(state: "GameState") -> list[str]:
    """收集玩家当前装备的叙事效果文本。

    通过 EventBus 请求 EquipmentSystem 获取所有已装备物品的 narrative_effects，
    合并为平铺文本列表，限制最多3条以控制 token 消耗。
    """
    bus = getattr(state, '_event_bus', None)
    if bus is None:
        return []

    cm = getattr(state, 'character_manager', None)
    if cm is None:
        return []

    player = cm.player
    equipment = getattr(player, 'equipment', None)
    if not equipment:
        return []

    from lingmo_engine.core.events import PluginEvent
    narrative_data = bus.request(PluginEvent.EQUIPMENT_GET_NARRATIVE, equipment)
    if not narrative_data:
        return []

    texts = []
    for entry in narrative_data:
        for _category, text in entry.get("effects", {}).items():
            texts.append(text)
            if len(texts) >= 3:
                return texts
    return texts


def _build_location_summary(state: "GameState", plugins: "PluginRegistry") -> str:
    map_plugin = None
    for plugin in plugins._plugins.values():
        if hasattr(plugin, 'get_current_node'):
            map_plugin = plugin
            break

    if map_plugin:
        node = map_plugin.get_current_node()
        if node:
            map_obj = getattr(map_plugin, '_map', None)
            breadcrumb = map_obj.get_breadcrumb() if map_obj else []
            path = " > ".join(n.name for n in breadcrumb) if breadcrumb else node.name
            desc = node.description or ""
            return f"当前位置：{path}\n{desc}"

    cm = getattr(state, 'character_manager', None)
    location = cm.player.location if cm else ""
    return f"当前位置：{location}" if location else ""


def _build_nearby_summary(state: "GameState") -> str:
    cm = getattr(state, 'character_manager', None)
    if cm is None:
        return ""

    player = cm.player
    location = getattr(player, 'location', '')
    if not location:
        return ""

    nearby = [c for c in cm.all() if c.location == location and c.id != player.id]
    if not nearby:
        return ""

    # 构建玩家关系索引
    player_rels = {}
    if player.relationships:
        for rel in player.relationships:
            player_rels[rel.get("target_id")] = rel.get("label", "")

    lines = []
    for c in nearby:
        type_label = getattr(c.char_type, 'value', str(c.char_type))
        status = "" if c.is_alive else " (已死亡)"
        rel_tag = f" [{player_rels[c.id]}]" if c.id in player_rels else ""
        lines.append(f"- {c.name} ({type_label}, Lv{c.level}){status}{rel_tag}")
    return "附近角色：\n" + "\n".join(lines)


def build_context_hint(state: "GameState") -> str:
    """根据当前游戏状态生成上下文提示。"""
    hints = []

    cm = getattr(state, 'character_manager', None)
    if cm:
        player = cm.player
        hp = player.attrs.get("vitality")
        max_hp = player.attrs.get("max_vitality", 100)
    else:
        player = state.data.get("player", {})
        hp = player.get("vitality")
        max_hp = player.get("max_vitality", 100)

    if hp is not None and max_hp > 0 and hp <= max_hp * 0.3:
        hints.append("玩家血量较低，考虑在叙述中营造紧迫感")

    if not hints:
        return ""
    return "\n".join(hints)


def build_messages(
    system_prompt: str,
    world_data: str,
    history: list[dict],
    plugins: "PluginRegistry",
    state: "GameState",
    dynamic_state_prompt: str = "",
    tail_condensed: str = "",
    long_term_memory_text: str = "",
    scene_character_memory_text: str = "",
    cot_thinking_guide: str = "",
    entity_index_prompt: str = "",
    semi_static_prompt: str = "",
) -> list[dict]:
    """构建完整的 LLM 消息数组。

    消息顺序按缓存稳定性排列:
      [0] HEAD_ANCHORS — 真正静态，100%前缀缓存命中
      [1] WORLD_DATA   — 半静态，LLM创作内容时才变更
      [2] ENTITY_INDEX — 半静态，实体索引+已查询缓存
      [3] SEMI_STATIC_PLUGINS — 半静态，插件指引/模板
      [4] COT_THINKING_GUIDE  — 静态思考引导（session期间不变）
      [5] LONG_TERM_MEMORY    — 长期记忆摘要（低频变化）
      [6..K] history          — 最近N轮对话（前缀匹配缓存）
      [K+1] DYNAMIC_CONTEXT   — 动态上下文（合并: 场景记忆+状态+提醒+提示）
    """
    messages = []

    # ── 稳定前缀层（缓存命中） ──

    # [0] HEAD_ANCHORS — 真正静态
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    # [1] WORLD_DATA — 半静态，LLM创作内容时才变更
    if world_data:
        messages.append({"role": "system", "content": world_data})

    # [2] ENTITY_INDEX — 半静态，实体索引+已查询缓存
    if entity_index_prompt:
        messages.append({"role": "system", "content": entity_index_prompt})

    # [3] SEMI_STATIC_PLUGINS — 半静态，插件指引/模板
    if semi_static_prompt:
        messages.append({"role": "system", "content": semi_static_prompt})

    # [4] COT_THINKING_GUIDE — 静态，session 期间不变
    if cot_thinking_guide:
        messages.append({"role": "system", "content": cot_thinking_guide})

    # [5] LONG_TERM_MEMORY — 长期记忆摘要
    if long_term_memory_text:
        messages.append({"role": "system", "content": long_term_memory_text})

    # ── 每轮变化层 ──

    # [6..K] history
    messages.extend(history)

    # [K+1] DYNAMIC_CONTEXT — 合并为单个 system 消息
    dynamic_parts = []
    if scene_character_memory_text:
        dynamic_parts.append(scene_character_memory_text)
    if dynamic_state_prompt:
        dynamic_parts.append(dynamic_state_prompt)
    if tail_condensed:
        dynamic_parts.append(tail_condensed)
    engine_hint = build_context_hint(state)
    if engine_hint:
        dynamic_parts.append(engine_hint)
    plugin_hint = plugins.get_all_context_hints(state.data)
    if plugin_hint:
        dynamic_parts.append(plugin_hint)

    if dynamic_parts:
        messages.append({"role": "system", "content": "\n\n".join(dynamic_parts)})

    return messages
