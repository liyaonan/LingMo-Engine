"""文本解析与序列化工具（无状态纯函数）。"""
from __future__ import annotations


def filter_scene_characters(all_names: set[str], text: str) -> list[str]:
    """从文本中检测出现的角色名，按长度降序匹配，避免短名单字误匹配长名。

    如角色 "艾" 不会因为出现在 "艾琳" 中而被误判为在场。
    """
    names_sorted = sorted(all_names, key=len, reverse=True)
    appeared: list[str] = []
    for name in names_sorted:
        # 跳过单字符名（误匹配率极高）
        if len(name) < 2:
            continue
        if name in text:
            # 跳过被其他已检测到的更长角色名包含的子串假匹配
            if any(name in other for other in appeared):
                continue
            appeared.append(name)
    return appeared


def extract_first_sentence(text: str, max_len: int = 80) -> str:
    """从叙述文本中提取首句作为地点描述"""
    if not text:
        return ""
    for sep in ("。", "\n", "；"):
        idx = text.find(sep)
        if idx > 0:
            text = text[:idx]
            break
    text = text.strip()
    if len(text) > max_len:
        text = text[:max_len].rsplit("，", 1)[0].strip()
    return text


def serialize_messages_for_meta(messages: list[dict], tools: list) -> str:
    """将 LLM 请求消息序列化为可读文本，供 raw_prompt 记录"""
    parts = []
    for m in messages:
        parts.append(f"[{m.get('role', '?')}] {str(m.get('content', ''))[:500]}")
    if tools:
        parts.append(f"\n--- Tools ({len(tools)}) ---")
        for t in tools:
            parts.append(f"  {t.name}: {str(t.description)[:100]}")
    return "\n".join(parts)
