"""实体类型 Loader — 为 EntityRegistry 提供 list/get/search 接口。

每种实体类型实现三个方法（鸭子类型）：
  list_entities() -> list of {name, type, summary}
  get_entity(name) -> dict | None
  search_entities(name) -> list[dict]
"""
from __future__ import annotations

import logging

from lingmo_engine.core.protocols.visibility import VisibilityProtocol

logger = logging.getLogger(__name__)


class AbilityLoader:
    """技能/能力 Loader，适配 GameWorld.abilities dict。"""

    def __init__(self, abilities: dict[str, dict]):
        self._abilities = abilities
        # 建立 name → ability_id 反向索引
        self._name_index: dict[str, str] = {}
        for aid, ab in abilities.items():
            name = ab.get("name", "")
            if name:
                self._name_index[name] = aid

    def list_entities(self) -> list[dict]:
        results = []
        for aid, ab in self._abilities.items():
            summary = ab.get("summary", "")
            if not summary:
                tags = ab.get("tags", [])
                summary = ab.get("description", "")[:50] if ab.get("description") else ""
                if tags:
                    summary = f"{''.join(tags[:3])}，{summary}" if summary else "".join(tags[:3])
            results.append({
                "name": ab.get("name", aid),
                "type": "ability",
                "summary": summary,
            })
        return results

    def get_entity(self, name: str) -> dict | None:
        aid = self._name_index.get(name)
        if aid:
            return {"id": aid, **self._abilities[aid]}
        return None

    def search_entities(self, name: str) -> list[dict]:
        results = []
        for aid, ab in self._abilities.items():
            entity_name = ab.get("name", aid)
            if name in entity_name or name in aid:
                results.append({"id": aid, **ab})
        return results


class ItemLoader:
    """物品 Loader，适配 GameWorld.items dict。"""

    def __init__(self, items: dict[str, dict]):
        self._items = items
        self._name_index: dict[str, str] = {}
        for iid, item in items.items():
            name = item.get("name", "")
            if name:
                self._name_index[name] = iid

    def list_entities(self) -> list[dict]:
        results = []
        for iid, item in self._items.items():
            summary = item.get("summary", "")
            if not summary:
                summary = item.get("description", "")[:50] if item.get("description") else ""
            results.append({
                "name": item.get("name", iid),
                "type": "item",
                "summary": summary,
            })
        return results

    def get_entity(self, name: str) -> dict | None:
        iid = self._name_index.get(name)
        if iid:
            return {"id": iid, **self._items[iid]}
        return None

    def search_entities(self, name: str) -> list[dict]:
        results = []
        for iid, item in self._items.items():
            entity_name = item.get("name", iid)
            if name in entity_name or name in iid:
                results.append({"id": iid, **item})
        return results


class CharacterLoader:
    """角色 Loader，持有 CharacterManager 引用以动态获取最新角色。"""

    def __init__(self, character_manager):
        # 持有 CM 引用而非快照，确保新增/修改角色后查询能命中
        self._cm = character_manager
        self._visibility_resolver: VisibilityProtocol | None = None

    def set_visibility_resolver(self, resolver: VisibilityProtocol) -> None:
        """注入 LLM 可见性 resolver，用于过滤隐藏属性/字段。"""
        self._visibility_resolver = resolver

    @property
    def _characters(self) -> list:
        return self._cm.all()

    def list_entities(self) -> list[dict]:
        results = []
        for c in self._characters:
            summary = c.summary if hasattr(c, 'summary') else ""
            if not summary:
                personality = getattr(c, "personality", "")
                char_type = getattr(c.char_type, "value", str(c.char_type))
                summary = personality if personality else char_type
            results.append({
                "name": c.name,
                "type": "character",
                "summary": summary[:50],
            })
        return results

    def get_entity(self, name: str) -> dict | None:
        for c in self._characters:
            if c.name == name:
                return self._to_dict(c)
        return None

    def search_entities(self, name: str) -> list[dict]:
        results = []
        for c in self._characters:
            if name in c.name:
                results.append(self._to_dict(c))
        return results

    def _to_dict(self, c) -> dict:
        char_type = getattr(c.char_type, "value", str(c.char_type))
        attrs = {}
        raw_attrs = getattr(c, "attrs", {})
        if hasattr(raw_attrs, "items"):
            attrs = dict(raw_attrs)
        elif isinstance(raw_attrs, dict):
            attrs = raw_attrs
        result = {
            "id": getattr(c, "id", None),
            "name": c.name,
            "char_type": char_type,
            "level": getattr(c, "level", 0),
            "personality": getattr(c, "personality", ""),
            "faction": getattr(c, "faction", ""),
            "location": getattr(c, "location", ""),
            "tags": list(getattr(c, "tags", []) or []),
            "attrs": attrs,
            "abilities": list(c.abilities or []),
            "equipment": dict(getattr(c, "equipment", {}) or {}),
        }
        if self._visibility_resolver:
            result["attrs"] = self._visibility_resolver.filter_attrs(result["attrs"])
            result = self._visibility_resolver.filter_fields(result)
        return result
