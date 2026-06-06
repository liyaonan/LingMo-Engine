"""SchemaVisibilityResolver 单元测试。"""
import pytest
from lingmo_engine.plugins.character.schema_visibility import SchemaVisibilityResolver


class TestBasicVisibility:
    """无配置时默认 visible，有 override 时按 override。"""

    def test_no_config_all_visible(self):
        """无 llm_visibility 配置时，所有属性默认 visible。"""
        schema = {"attributes": {"hp": {"default": 50}}, "fields": {"name": {"type": "str"}}}
        resolver = SchemaVisibilityResolver(schema)
        assert resolver.is_llm_visible("hp") is True
        assert resolver.is_llm_visible("name", section="fields") is True

    def test_override_hidden(self):
        """overrides 中标记 hidden 的属性不可见。"""
        schema = {
            "attributes": {"hp": {"default": 50}, "karma": {"default": 0}},
            "fields": {},
            "llm_visibility": {
                "overrides": {"karma": "hidden"},
            },
        }
        resolver = SchemaVisibilityResolver(schema)
        assert resolver.is_llm_visible("hp") is True
        assert resolver.is_llm_visible("karma") is False

    def test_override_takes_priority_over_default(self):
        """overrides 优先于 defaults。"""
        schema = {
            "attributes": {
                "spirit_stones": {"default": 0, "category": "economy"},
                "karma": {"default": 0, "category": "economy"},
            },
            "fields": {},
            "llm_visibility": {
                "defaults": {"economy": "hidden"},
                "overrides": {"karma": "visible"},
            },
        }
        resolver = SchemaVisibilityResolver(schema)
        assert resolver.is_llm_visible("spirit_stones") is False
        assert resolver.is_llm_visible("karma") is True

    def test_field_override_hidden(self):
        """field_overrides 标记的字段不可见。"""
        schema = {
            "attributes": {},
            "fields": {"loot_table": {"type": "list"}, "name": {"type": "str"}},
            "llm_visibility": {
                "field_overrides": {"loot_table": "hidden"},
            },
        }
        resolver = SchemaVisibilityResolver(schema)
        assert resolver.is_llm_visible("loot_table", section="fields") is False
        assert resolver.is_llm_visible("name", section="fields") is True


class TestGroupDefaults:
    """分组默认策略测试。"""

    def test_attribute_mark_group_default(self):
        """属性通过其标记（如 innate、category）匹配 defaults。"""
        schema = {
            "attributes": {
                "vitality": {"default": 50, "innate": True},
                "force": {"default": 50, "innate": True},
                "spirit_stones": {"default": 0, "category": "economy"},
            },
            "fields": {},
            "llm_visibility": {
                "defaults": {"innate": "visible", "economy": "hidden"},
            },
        }
        resolver = SchemaVisibilityResolver(schema)
        assert resolver.is_llm_visible("vitality") is True
        assert resolver.is_llm_visible("force") is True
        assert resolver.is_llm_visible("spirit_stones") is False

    def test_display_section_group(self):
        """display_section 标记的属性匹配嵌套分组。"""
        schema = {
            "attributes": {
                "enlightenment": {"default": 0, "display_section": "cultivation"},
                "breakthrough_cooldown": {"default": 0, "display_section": "cultivation"},
            },
            "fields": {},
            "llm_visibility": {
                "defaults": {"display_section": {"cultivation": "visible"}},
                "overrides": {"breakthrough_cooldown": "hidden"},
            },
        }
        resolver = SchemaVisibilityResolver(schema)
        assert resolver.is_llm_visible("enlightenment") is True
        assert resolver.is_llm_visible("breakthrough_cooldown") is False

    def test_field_mark_group_default(self):
        """字段通过其标记（如 core）匹配 field_defaults。"""
        schema = {
            "attributes": {},
            "fields": {
                "name": {"type": "str", "core": True},
                "loot_table": {"type": "list"},
            },
            "llm_visibility": {
                "field_defaults": {"core": "visible"},
                "field_overrides": {"loot_table": "hidden"},
            },
        }
        resolver = SchemaVisibilityResolver(schema)
        assert resolver.is_llm_visible("name", section="fields") is True
        assert resolver.is_llm_visible("loot_table", section="fields") is False


class TestFilterMethods:
    """filter_attrs / filter_fields 批量过滤测试。"""

    def test_filter_attrs_removes_hidden(self):
        schema = {
            "attributes": {
                "hp": {"default": 50},
                "karma": {"default": 0},
                "spirit_stones": {"default": 0, "category": "economy"},
            },
            "fields": {},
            "llm_visibility": {
                "defaults": {"economy": "hidden"},
                "overrides": {"karma": "hidden"},
            },
        }
        resolver = SchemaVisibilityResolver(schema)
        attrs = {"hp": 100, "karma": 5, "spirit_stones": 500}
        filtered = resolver.filter_attrs(attrs)
        assert filtered == {"hp": 100}

    def test_filter_fields_removes_hidden(self):
        schema = {
            "attributes": {},
            "fields": {"name": {"type": "str"}, "loot_table": {"type": "list"}},
            "llm_visibility": {
                "field_overrides": {"loot_table": "hidden"},
            },
        }
        resolver = SchemaVisibilityResolver(schema)
        data = {"name": "张三", "loot_table": [], "faction": ""}
        filtered = resolver.filter_fields(data)
        assert "loot_table" not in filtered
        assert filtered["name"] == "张三"
        assert filtered["faction"] == ""

    def test_filter_attrs_empty_config_returns_all(self):
        schema = {"attributes": {"hp": {"default": 50}}, "fields": {}}
        resolver = SchemaVisibilityResolver(schema)
        attrs = {"hp": 100}
        assert resolver.filter_attrs(attrs) == {"hp": 100}

    def test_unknown_attr_visible_by_default(self):
        """不在 schema 中的属性名默认 visible（由 validator 负责移除 unknown）。"""
        schema = {"attributes": {"hp": {"default": 50}}, "fields": {}}
        resolver = SchemaVisibilityResolver(schema)
        assert resolver.is_llm_visible("nonexistent_attr") is True
