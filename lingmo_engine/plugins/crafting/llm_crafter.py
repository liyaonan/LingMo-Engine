"""LLM 炼器器 — 构建 Prompt、调用 LLM、解析物品生成结果"""
from __future__ import annotations

import json
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)

# 合法效果类型（与 _templates.yaml 对齐）
VALID_EFFECT_TYPES = {
    "damage", "heal", "buff", "shield", "fixed_damage",
    "dispel", "lifesteal", "stun", "breakthrough_boost",
    "exp_boost", "heal_over_time", "resource_restore", "cure_status",
}

# 效果互斥规则（同组效果不能共存于一个物品）
EFFECT_EXCLUSIONS = [
    {"damage", "lifesteal"},
]


def _apply_exclusions(slots: list[dict]) -> list[dict]:
    """移除互斥组中后出现的效果类型，保留先出现的。"""
    seen_types: set[str] = set()
    result: list[dict] = []
    for slot in slots:
        slot_type = slot["type"]
        # 检查是否与已有效果互斥
        excluded = False
        for excl_set in EFFECT_EXCLUSIONS:
            if slot_type in excl_set:
                # 如果已存在同组的其他类型，跳过当前
                if seen_types & (excl_set - {slot_type}):
                    logger.warning("互斥过滤: 移除 %s", slot_type)
                    excluded = True
                    break
        if not excluded:
            seen_types.add(slot_type)
            result.append(slot)
    return result


def build_crafting_prompt(
    theme: str,
    materials: list[dict],
    effective_power: int,
    rarity: int,
    level_label: str,
) -> str:
    """构建炼制 Prompt。"""
    material_lines = []
    for m in materials:
        tags_str = "、".join(m.get("tags", []))
        material_lines.append(
            f"- {m.get('name', '未知')} (品质:{m.get('rarity', '?')}, Tags:{tags_str})"
        )
    materials_text = "\n".join(material_lines) if material_lines else "- 无材料（纯灵力炼制）"

    return f"""你是一位修仙世界的炼器大师。一位修士正在炼制{theme}。

【材料】
{materials_text}

【灵力参数】
有效灵力: {effective_power}
品质等级: {rarity}
物品等级: {level_label}

【要求】
根据材料的Tag属性，自行决定这件{theme}的炼制方向和最终成品。
- 你必须根据材料的元素、功能Tag推断出最合理的成品类型和效果
- 物品等级为{level_label}，效果强度应与该等级匹配
- 必须继承材料的元素属性Tag
- {theme}的默认Tag必须包含
- 返回严格JSON格式，不要包含任何其他文字

返回格式：
{{"name": "物品名称", "description": "物品描述（一句有修仙韵味的话）", "tags": ["tag1", "tag2"], "effect_slots": [{{"type": "效果类型", "target": "enemy|self|all_enemy|all_ally", "weight": 0.6}}]}}

合法效果类型: {', '.join(sorted(VALID_EFFECT_TYPES))}
weight 决定效果被抽中的概率（归一化），总和不超过1.0"""


def parse_llm_result(raw_text: str, warnings: List[str] | None = None) -> Optional[dict]:
    """解析 LLM 返回的 JSON 结果。

    Returns:
        解析后的 dict，或 None（格式错误时）
    """
    # 提取 JSON 块（LLM 可能返回 ```json ... ``` 包裹的内容）
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # 去掉首尾的 ``` 行
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        msg = "WARNING: 炼制结果解析失败，返回格式非 JSON。建议：以纯 JSON 格式重新返回结果"
        logger.warning("LLM 返回非 JSON: %s", text[:200])
        if warnings is not None:
            warnings.append(msg)
        return None

    # 基本结构校验
    if not isinstance(data, dict):
        return None
    if "name" not in data or "tags" not in data:
        msg = f"WARNING: 炼制结果缺少必要字段({list(data.keys())})。建议：确保结果包含 name 和 tags 字段"
        logger.warning("LLM 结果缺少必要字段: %s", list(data.keys()))
        if warnings is not None:
            warnings.append(msg)
        return None

    # 校验 effect_slots
    slots = data.get("effect_slots", [])
    if not isinstance(slots, list):
        return None

    valid_slots = []
    for slot in slots:
        if not isinstance(slot, dict):
            continue
        slot_type = slot.get("type", "")
        if slot_type not in VALID_EFFECT_TYPES:
            msg = f"WARNING: LLM 返回未知效果类型: {slot_type}。建议：使用合法效果类型 {', '.join(sorted(VALID_EFFECT_TYPES))}"
            logger.warning("LLM 返回未知效果类型: %s", slot_type)
            if warnings is not None:
                warnings.append(msg)
            continue
        valid_slots.append({
            "type": slot_type,
            "target": slot.get("target", "enemy"),
            "weight": float(slot.get("weight", 0.5)),
        })

    if not valid_slots:
        msg = "WARNING: LLM 结果无有效效果槽位。建议：至少提供一种有效的效果类型"
        logger.warning("LLM 结果无有效效果槽位")
        if warnings is not None:
            warnings.append(msg)
        return None

    # 互斥检查：移除互斥组中后出现的类型
    valid_slots = _apply_exclusions(valid_slots)

    if not valid_slots:
        msg = "WARNING: LLM 结果互斥过滤后无有效效果槽位。建议：调整效果组合避免互斥冲突"
        logger.warning("LLM 结果互斥过滤后无有效效果槽位")
        if warnings is not None:
            warnings.append(msg)
        return None

    return {
        "name": str(data.get("name", ""))[:20],
        "description": str(data.get("description", ""))[:100],
        "tags": data.get("tags", [])[:10],
        "effect_slots": valid_slots,
    }


def build_fallback_item(
    theme: str,
    materials: list[dict],
    default_tags: list[str],
    effective_power: int,
    rarity: int,
) -> dict:
    """LLM 失败时的回退模板生成。"""
    # 合并材料 tags
    material_tags = []
    for m in materials:
        material_tags.extend(m.get("tags", []))

    all_tags = list(set(default_tags + material_tags))

    # 根据题材选择默认效果
    default_effects = {
        "符箓": [{"type": "damage", "target": "enemy", "weight": 0.7}],
        "阵旗": [{"type": "buff", "target": "self", "weight": 0.5}, {"type": "damage", "target": "all_enemy", "weight": 0.5}],
        "法宝": [{"type": "damage", "target": "enemy", "weight": 0.6}, {"type": "shield", "target": "self", "weight": 0.4}],
        "丹药": [{"type": "heal", "target": "self", "weight": 0.8}],
    }

    return {
        "name": f"{theme}·{all_tags[0] if all_tags else '无名'}",
        "description": f"由灵力封存而成的{theme}",
        "tags": all_tags,
        "effect_slots": default_effects.get(theme, [{"type": "damage", "target": "enemy", "weight": 0.7}]),
    }


def build_material_prompt(context: str, count: int, valid_tags: list[str]) -> str:
    """构建材料生成 Prompt。"""
    tags_text = "、".join(valid_tags)
    return f"""你是修仙世界的天道，负责根据场景动态生成修仙材料。

【场景上下文】
{context}

【要求】
生成 {count} 个材料，根据场景强度合理确定稀有度：
- 普通小怪/日常采集 → rarity 0~40
- 精英怪/稀有资源 → rarity 40~70
- BOSS/秘境 → rarity 60~90
- 上古遗迹/仙界 → rarity 80~100

Tags 只能从以下列表中选取（可多选）：{tags_text}

返回严格 JSON 数组格式，不要包含任何其他文字：
[{{"name": "材料名", "rarity": 50, "tags": ["tag1", "tag2"], "description": "一句有修仙韵味的描述"}}]"""


def parse_material_result(raw_text: str, valid_tags: list[str]) -> list[dict]:
    """解析 LLM 返回的材料 JSON。"""
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("材料生成 LLM 返回非 JSON: %s", text[:200])
        return []

    if not isinstance(data, list):
        data = [data] if isinstance(data, dict) else []

    valid_set = set(valid_tags)
    results = []
    for item in data:
        if not isinstance(item, dict) or "name" not in item:
            continue
        tags = [t for t in item.get("tags", []) if t in valid_set]
        results.append({
            "name": str(item.get("name", ""))[:20],
            "rarity": max(0, min(100, int(item.get("rarity", 1)))),
            "tags": tags[:10],
            "description": str(item.get("description", ""))[:100],
        })

    return results


def build_equipment_prompt(
    slot_type: str,
    slot_name: str,
    materials: list[dict],
    effective_power: int,
    rarity: int,
    level_label: str,
    context: str = "",
    ability_count: int = 0,
) -> str:
    """构建装备生成 Prompt（LLM 只负责命名/描述/标签/技能槽位）。"""
    material_lines = []
    for m in materials:
        tags_str = "、".join(m.get("tags", []))
        material_lines.append(
            f"- {m.get('name', '未知')} (品质:{m.get('rarity', '?')}, Tags:{tags_str})"
        )
    materials_text = "\n".join(material_lines) if material_lines else "- 无材料"

    context_text = f"\n【场景】\n{context}\n" if context else ""

    # 技能完整定义指令（仅法宝）
    ability_section = ""
    if ability_count > 0:
        ability_section = f"""
此外，这件法宝可以附带 {ability_count} 个技能。请为每个技能指定完整定义：
- name: 技能名称
- category: attack/buff/heal/debuff
- effects: 效果列表，每个效果包含：
  - type: 效果类型（damage/buff/heal/shield/dispel/lifesteal/fixed_damage/stun）
  - target: 目标（self/enemy/all_enemy/all_ally）
  - power: 伤害/治疗倍率（0.5~5.0）/ 护盾比例（占最大生命值百分比，0.1~1.0）
  - modifier: buff百分比（0.05~0.5）
  - value: 固定值（fixed_damage）
  - duration: 持续回合（0=即时）
  - chance: 概率（stun用，0.1~1.0）
- costs: 消耗列表，每个包含 resource（spiritual_power/divine_sense/stamina/hp）和 amount
- cooldown: 冷却回合数（0~5）

注意：costs 和 cooldown 仅供参考，系统将根据物品等级和品质自动计算最终值。"""

    # 返回格式
    if ability_count > 0:
        return_format = '{"name": "装备名称", "description": "装备描述", "tags": ["tag1"], "abilities": [{"name": "技能名", "category": "attack", "effects": [{"type": "damage", "target": "enemy", "power": 1.2}], "costs": [{"resource": "spiritual_power", "amount": 8}], "cooldown": 1}]}'
    else:
        return_format = '{"name": "装备名称", "description": "装备描述", "tags": ["tag1", "tag2"]}'

    return f"""你是修仙世界的炼器大师。正在锻造一件装备。

【装备部位】
{slot_name}

【材料】
{materials_text}
{context_text}
【灵力参数】
有效灵力: {effective_power}
品质等级: {rarity}
物品等级: {level_label}

【要求】
根据材料属性，决定这件{slot_name}的名称、描述和标签。
- 名称要有修仙韵味，与材料元素和品质匹配
- 描述一句有画面感的话
- 标签从以下列表中选取：法袍, 防具, 武器, 法宝, 饰品, 刀, 剑, 枪, 杖, 环, 琴, 金, 木, 水, 火, 土, 雷, 冰, 风, 治疗, 增益, 减益, 伤害, 防御, 穿透
- 返回严格 JSON 格式，不要包含任何其他文字
{ability_section}
返回格式：
{return_format}"""


def parse_equipment_result(raw_text: str) -> Optional[dict]:
    """解析 LLM 返回的装备 JSON 结果。"""
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("装备生成 LLM 返回非 JSON: %s", text[:200])
        return None

    if not isinstance(data, dict):
        return None
    if "name" not in data:
        logger.warning("装备生成结果缺少 name: %s", list(data.keys()))
        return None

    result = {
        "name": str(data.get("name", ""))[:20],
        "description": str(data.get("description", ""))[:100],
        "tags": data.get("tags", [])[:10],
    }

    # 解析 abilities（法宝完整技能定义）
    abilities_raw = data.get("abilities", [])
    if isinstance(abilities_raw, list) and abilities_raw:
        valid_abilities = []
        for abl in abilities_raw:
            if not isinstance(abl, dict) or "name" not in abl:
                continue
            effects = []
            for eff in abl.get("effects", []):
                if not isinstance(eff, dict) or "type" not in eff:
                    continue
                effect = {"type": eff["type"]}
                # 复制已知字段
                for k in ("target", "power", "modifier", "value", "duration", "chance", "stat", "element"):
                    if k in eff:
                        effect[k] = eff[k]
                effects.append(effect)
            if not effects:
                continue
            costs = []
            for c in abl.get("costs", []):
                if isinstance(c, dict) and "resource" in c and "amount" in c:
                    costs.append({"resource": c["resource"], "amount": max(1, int(c["amount"]))})
            valid_abilities.append({
                "name": str(abl.get("name", ""))[:20],
                "category": abl.get("category", "attack"),
                "effects": effects,
                "costs": costs,
                "cooldown": max(0, min(10, int(abl.get("cooldown", 0)))),
            })
        if valid_abilities:
            result["abilities"] = valid_abilities

    return result


def build_equipment_fallback(
    slot_name: str,
    materials: list[dict],
    default_tags: list[str],
    ability_count: int = 0,
) -> dict:
    """装备生成 LLM 失败时的回退模板。"""
    material_tags = []
    for m in materials:
        material_tags.extend(m.get("tags", []))
    all_tags = list(set(default_tags + material_tags))

    result = {
        "name": f"{slot_name}·{all_tags[0] if all_tags else '无名'}",
        "description": f"由灵力封存锻造的{slot_name}",
        "tags": all_tags,
    }

    # 回退完整技能定义（法宝专用）
    if ability_count > 0:
        default_abilities = [
            {
                "name": "法宝攻击",
                "category": "attack",
                "effects": [{"type": "damage", "target": "enemy", "power": 1.0}],
                "costs": [{"resource": "spiritual_power", "amount": 5}],
                "cooldown": 1,
            },
            {
                "name": "法宝守护",
                "category": "buff",
                "effects": [{"type": "buff", "target": "self", "modifier": 0.1}],
                "costs": [{"resource": "divine_sense", "amount": 3}],
                "cooldown": 2,
            },
        ]
        result["abilities"] = default_abilities[:ability_count]

    return result
