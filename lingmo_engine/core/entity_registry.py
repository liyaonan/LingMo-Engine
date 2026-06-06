"""实体缓存池 — LRU 缓存，存储最近查询的实体详情用于注入 prompt。"""

from __future__ import annotations

import json
from collections import OrderedDict


class EntityCache:
    """LRU 实体缓存池，缓存最近查询的实体详情用于注入 prompt。"""

    def __init__(self, max_size: int = 30):
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._max_size = max_size

    def _key(self, entity_type: str, name: str) -> str:
        return f"{entity_type}:{name}"

    def put(self, entity_type: str, name: str, data: dict) -> None:
        key = self._key(entity_type, name)
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = data
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def get(self, entity_type: str, name: str) -> dict | None:
        key = self._key(entity_type, name)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def preload(self, entities: list[dict]) -> None:
        for e in entities:
            self.put(e["entity_type"], e["name"], e["data"])

    def get_cached_prompt(self) -> str:
        if not self._cache:
            return ""
        lines = ["[已查询实体]"]
        for key, data in self._cache.items():
            lines.append(f"- {data.get('name', key)}: {json.dumps(data, ensure_ascii=False)}")
        return "\n".join(lines)


class EntityRegistry:
    """统一实体查询注册中心。"""

    def __init__(self, fuzzy_threshold: int = 5, type_thresholds: dict[str, int] | None = None):
        self._loaders: dict[str, object] = {}
        self._fuzzy_threshold = fuzzy_threshold
        self._type_thresholds: dict[str, int] = type_thresholds or {}

    def register(self, entity_type: str, loader) -> None:
        """注册实体类型及其 Loader。"""
        self._loaders[entity_type] = loader

    def query(self, name: str, entity_type: str | None = None) -> dict:
        """按名称查询实体，返回匹配结果。"""
        # 1. 精确匹配
        result = self._exact_match(name, entity_type)
        if result:
            return {"found": True, "exact": True, "results": [result]}

        # 2. 模糊搜索
        candidates = self._fuzzy_search(name, entity_type)
        if not candidates:
            return {"found": False, "suggestions": self.get_suggestions(entity_type)}

        threshold = self._get_threshold(entity_type)
        if len(candidates) <= threshold:
            return {"found": True, "exact": False, "results": candidates}

        return {
            "found": True,
            "exact": False,
            "too_many": True,
            "candidates": [
                {"name": c.get("name", ""), "type": c.get("type", "")}
                for c in candidates[:20]
            ],
        }

    def get_index(self) -> str:
        """生成实体索引用于注入 prompt。"""
        lines = []
        for entity_type, loader in self._loaders.items():
            for e in loader.list_entities():
                lines.append(f"{e['name']}|{e['type']}|{e.get('summary', '')}")
        return "\n".join(lines) if lines else ""

    def get_suggestions(self, entity_type: str | None = None) -> list[dict]:
        """获取同类型的建议列表。"""
        suggestions = []
        types = [entity_type] if entity_type else list(self._loaders.keys())
        for t in types:
            loader = self._loaders.get(t)
            if loader:
                for e in loader.list_entities()[:5]:
                    suggestions.append({"name": e["name"], "type": e["type"]})
        return suggestions

    @property
    def registered_types(self) -> list[str]:
        return list(self._loaders.keys())

    def _get_threshold(self, entity_type: str | None) -> int:
        """获取模糊匹配阈值，优先使用按类型配置。"""
        if entity_type and entity_type in self._type_thresholds:
            return self._type_thresholds[entity_type]
        return self._fuzzy_threshold

    def _exact_match(self, name: str, entity_type: str | None = None) -> dict | None:
        types = [entity_type] if entity_type else list(self._loaders.keys())
        for t in types:
            loader = self._loaders.get(t)
            if loader:
                result = loader.get_entity(name)
                if result:
                    return {**result, "type": t}
        return None

    def _fuzzy_search(self, name: str, entity_type: str | None = None) -> list[dict]:
        results = []
        types = [entity_type] if entity_type else list(self._loaders.keys())
        for t in types:
            loader = self._loaders.get(t)
            if loader:
                for e in loader.search_entities(name):
                    results.append({**e, "type": t})
        return results
