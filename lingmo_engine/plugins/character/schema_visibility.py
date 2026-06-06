"""SchemaVisibilityResolver — 根据 schema 的 llm_visibility 配置控制属性对 LLM 的可见性。"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class SchemaVisibilityResolver:
    """根据 schema 的 llm_visibility 配置，判断属性/字段是否对 LLM 可见。

    解析优先级: overrides → defaults（按属性标记匹配）→ 默认 visible。

    Attributes:
        _attributes_schema: 属性 schema 定义字典。
        _fields_schema: 字段 schema 定义字典。
        _defaults: 属性分组默认可见性规则。
        _overrides: 属性级别可见性覆盖。
        _field_defaults: 字段分组默认可见性规则。
        _field_overrides: 字段级别可见性覆盖。
    """

    # 属性定义中不视为「标记」的元数据键（跳过匹配）。
    _ATTR_META_KEYS = frozenset({
        "default", "type", "label", "color", "pair",
        "combat_role", "combat_type", "validation",
        "show_in_status_bar", "show_in_radar",
        "innate", "read_only", "cultivation_path_attr",
    })

    # 字段定义中不视为「标记」的元数据键（跳过匹配）。
    _FIELD_META_KEYS = frozenset({
        "default", "type", "label", "validation", "required", "enum",
        "read_only", "derived_from",
    })

    def __init__(self, schema: dict) -> None:
        """初始化 resolver，从 schema 中提取 llm_visibility 配置。

        Args:
            schema: 完整的角色 schema 字典，包含 attributes、fields 及
                可选的 llm_visibility 配置段。
        """
        self._attributes_schema: dict[str, dict] = schema.get("attributes", {})
        self._fields_schema: dict[str, dict] = schema.get("fields", {})
        vis: dict = schema.get("llm_visibility", {})
        self._defaults: dict = vis.get("defaults", {})
        self._overrides: dict[str, str] = vis.get("overrides", {})
        self._field_defaults: dict = vis.get("field_defaults", {})
        self._field_overrides: dict[str, str] = vis.get("field_overrides", {})

    def is_llm_visible(self, name: str, section: str = "attributes") -> bool:
        """判断单个属性或字段是否对 LLM 可见。

        Args:
            name: 属性名或字段名。
            section: "attributes" 或 "fields"。

        Returns:
            True 表示可见，False 表示隐藏。
        """
        if section == "fields":
            return self._check_field(name)
        return self._check_attribute(name)

    def filter_attrs(self, attrs: dict) -> dict:
        """过滤 attrs 字典，仅保留 LLM 可见的属性。

        Args:
            attrs: 属性名到值的映射。

        Returns:
            仅包含可见属性的新字典。
        """
        return {k: v for k, v in attrs.items() if self.is_llm_visible(k)}

    def filter_fields(self, data: dict) -> dict:
        """过滤顶层字段，仅保留 LLM 可见的字段。

        Args:
            data: 字段名到值的映射。

        Returns:
            仅包含可见字段的新字典。
        """
        return {k: v for k, v in data.items() if self.is_llm_visible(k, section="fields")}

    def _check_attribute(self, name: str) -> bool:
        """检查单个属性是否对 LLM 可见。"""
        # 1. overrides 优先级最高
        if name in self._overrides:
            return self._overrides[name] != "hidden"

        # 2. 按属性标记匹配 defaults 分组规则
        attr_def = self._attributes_schema.get(name, {})
        for mark_key, mark_val in attr_def.items():
            if mark_key in self._ATTR_META_KEYS:
                continue
            result = self._resolve_default(mark_key, mark_val)
            if result is not None:
                return result != "hidden"

        # 3. 默认可见
        return True

    def _check_field(self, name: str) -> bool:
        """检查单个字段是否对 LLM 可见。"""
        # 1. field_overrides 优先级最高
        if name in self._field_overrides:
            return self._field_overrides[name] != "hidden"

        # 2. 按字段标记匹配 field_defaults 分组规则
        field_def = self._fields_schema.get(name, {})
        for mark_key, mark_val in field_def.items():
            if mark_key in self._FIELD_META_KEYS:
                continue
            result = self._resolve_field_default(mark_key, mark_val)
            if result is not None:
                return result != "hidden"

        # 3. 默认可见
        return True

    def _resolve_default(self, mark_key: str, mark_val: str | bool) -> str | None:
        """从 defaults 规则中解析标记对应的可见性。

        匹配策略（按优先级）:
        1. 标记键匹配: defaults 中存在与 mark_key 相同的键。
           - 嵌套形式: {"display_section": {"cultivation": "visible"}} 按标记值细分。
           - 简单形式: {"innate": "visible"} 标记存在即生效。
        2. 标记值匹配: defaults 中存在与 mark_val（str）相同的键（仅简单形式）。
           - 例: {"economy": "hidden"} 匹配 category: economy 等带 "economy" 值的标记。

        Args:
            mark_key: 标记键名。
            mark_val: 标记值。

        Returns:
            可见性字符串（"visible"/"hidden"）或 None（无匹配规则）。
        """
        # 1. 标记键匹配
        if mark_key in self._defaults:
            rule = self._defaults[mark_key]
            # 嵌套形式: 按标记值细分
            if isinstance(rule, dict) and isinstance(mark_val, str):
                return rule.get(mark_val)
            # 简单形式: 标记键存在即生效
            if isinstance(rule, str):
                return rule

        # 2. 标记值匹配（仅字符串值，避免误匹配布尔值等）
        if isinstance(mark_val, str) and mark_val in self._defaults:
            rule = self._defaults[mark_val]
            if isinstance(rule, str):
                return rule

        return None

    def _resolve_field_default(self, mark_key: str, mark_val: str | bool) -> str | None:
        """从 field_defaults 规则中解析标记对应的可见性。

        匹配策略与 _resolve_default 一致，仅作用于字段。

        Args:
            mark_key: 标记键名。
            mark_val: 标记值。

        Returns:
            可见性字符串或 None。
        """
        # 1. 标记键匹配
        if mark_key in self._field_defaults:
            rule = self._field_defaults[mark_key]
            if isinstance(rule, dict) and isinstance(mark_val, str):
                return rule.get(mark_val)
            if isinstance(rule, str):
                return rule

        # 2. 标记值匹配（仅字符串值）
        if isinstance(mark_val, str) and mark_val in self._field_defaults:
            rule = self._field_defaults[mark_val]
            if isinstance(rule, str):
                return rule

        return None

    # ── 只读字段查询 ──

    def _get_schema(self, section: str) -> dict:
        """根据 section 返回对应的 schema 字典。"""
        return self._fields_schema if section == "fields" else self._attributes_schema

    def is_read_only(self, name: str, section: str = "fields") -> bool:
        """判断字段是否为只读（LLM 可见但不可修改）。

        Args:
            name: 字段名。
            section: "attributes" 或 "fields"。

        Returns:
            True 表示只读。
        """
        field_def = self._get_schema(section).get(name, {})
        return field_def.get("read_only", False) is True

    def get_derived_from(self, name: str, section: str = "fields") -> str | None:
        """获取只读字段的派生源字段名。

        Args:
            name: 只读字段名。
            section: "attributes" 或 "fields"。

        Returns:
            派生源字段名，或 None（无派生关系）。
        """
        field_def = self._get_schema(section).get(name, {})
        return field_def.get("derived_from")

    def get_read_only_fields(self, section: str = "fields") -> list[str]:
        """获取所有只读字段名列表。

        Args:
            section: "attributes" 或 "fields"。

        Returns:
            只读字段名列表。
        """
        return [
            name for name, defn in self._get_schema(section).items()
            if defn.get("read_only", False) is True
        ]
