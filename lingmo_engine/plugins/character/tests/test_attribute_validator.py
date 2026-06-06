"""AttributeValidator 单元测试。"""
import pytest
from lingmo_engine.plugins.character.attribute_validator import AttributeValidator


class TestTypeNormalization:
    """类型规范化测试。"""

    def test_level_float_to_int(self):
        v = AttributeValidator()
        data = {"name": "测试", "level": 5.7, "attrs": {}}
        cleaned, _ = v.validate_new_character(data)
        assert cleaned["level"] == 5
        assert isinstance(cleaned["level"], int)

    def test_level_string_to_int(self):
        v = AttributeValidator()
        data = {"name": "测试", "level": "10", "attrs": {}}
        cleaned, _ = v.validate_new_character(data)
        assert cleaned["level"] == 10

    def test_level_invalid_defaults_to_1(self):
        v = AttributeValidator()
        data = {"name": "测试", "level": "abc", "attrs": {}}
        cleaned, _ = v.validate_new_character(data)
        assert cleaned["level"] == 1

    def test_name_empty_defaults(self):
        v = AttributeValidator()
        data = {"name": "", "level": 1, "attrs": {}}
        cleaned, corrections = v.validate_new_character(data)
        assert cleaned["name"] == "未命名角色"
        assert any("name" in c for c in corrections)

    def test_name_strips_whitespace(self):
        v = AttributeValidator()
        data = {"name": "  铁剑  ", "level": 1, "attrs": {}}
        cleaned, _ = v.validate_new_character(data)
        assert cleaned["name"] == "铁剑"

    def test_attr_float_to_int(self):
        v = AttributeValidator()
        data = {"name": "测试", "level": 1, "attrs": {"hp": 100.5, "mp": 50.0}}
        cleaned, _ = v.validate_new_character(data)
        assert cleaned["attrs"]["hp"] == 100
        assert cleaned["attrs"]["mp"] == 50

    def test_attr_invalid_defaults_to_0(self):
        v = AttributeValidator()
        data = {"name": "测试", "level": 1, "attrs": {"hp": "xxx"}}
        cleaned, corrections = v.validate_new_character(data)
        # 类型规范化: "xxx"→0, 然后范围校验: 0<hard_min(1)→1
        assert cleaned["attrs"]["hp"] == 1
        assert any("hp" in c for c in corrections)

    def test_none_lists_become_empty(self):
        v = AttributeValidator()
        data = {"name": "测试", "level": 1, "attrs": {},
                "abilities": None, "tags": None}
        cleaned, _ = v.validate_new_character(data)
        assert cleaned["abilities"] == []
        assert cleaned["tags"] == []

    def test_none_equipment_becomes_empty_dict(self):
        v = AttributeValidator()
        data = {"name": "测试", "level": 1, "attrs": {},
                "equipment": None}
        cleaned, _ = v.validate_new_character(data)
        assert cleaned["equipment"] == {}

    def test_is_alive_defaults_to_true(self):
        v = AttributeValidator()
        data = {"name": "测试", "level": 1, "attrs": {},
                "is_alive": "not_a_bool"}
        cleaned, _ = v.validate_new_character(data)
        assert cleaned["is_alive"] is True

    def test_none_relationships_becomes_empty_list(self):
        v = AttributeValidator()
        data = {"name": "测试", "level": 1, "attrs": {},
                "relationships": None}
        cleaned, _ = v.validate_new_character(data)
        assert cleaned["relationships"] == []


class TestRemoveUnknownAttrs:
    """未知属性移除测试。"""

    def test_removes_attrs_not_in_schema(self):
        v = AttributeValidator()
        v.set_attributes_schema({
            "attributes": {
                "hp": {"default": 100},
                "mp": {"default": 50},
            }
        })
        data = {"name": "测试", "level": 1,
                "attrs": {"hp": 100, "mp": 50, "qigong": 9999}}
        cleaned, corrections = v.validate_new_character(data)
        assert "qigong" not in cleaned["attrs"]
        assert any("qigong" in c for c in corrections)
        assert cleaned["attrs"]["hp"] == 100
        assert cleaned["attrs"]["mp"] == 50

    def test_no_schema_passes_all_attrs(self):
        v = AttributeValidator()
        data = {"name": "测试", "level": 1,
                "attrs": {"hp": 100, "custom_attr": 500}}
        cleaned, _ = v.validate_new_character(data)
        assert "custom_attr" in cleaned["attrs"]


class TestRangeRules:
    """范围校验测试。"""

    def test_level_caps_at_max_start_level(self):
        v = AttributeValidator()
        data = {"name": "测试", "level": 99, "attrs": {}}
        cleaned, corrections = v.validate_new_character(data)
        assert cleaned["level"] == 50  # DEFAULT max_start_level
        assert any("level" in c for c in corrections)

    def test_level_minimum_1(self):
        v = AttributeValidator()
        data = {"name": "测试", "level": -5, "attrs": {}}
        cleaned, corrections = v.validate_new_character(data)
        assert cleaned["level"] == 1

    def test_attr_clamped_to_hard_cap(self):
        v = AttributeValidator()
        data = {"name": "测试", "level": 1,
                "attrs": {"hp": 99999}}
        cleaned, corrections = v.validate_new_character(data)
        assert cleaned["attrs"]["hp"] == 999  # DEFAULT hard_cap
        assert any("hp" in c for c in corrections)

    def test_attr_within_hard_cap_passes(self):
        v = AttributeValidator()
        data = {"name": "测试", "level": 1,
                "attrs": {"hp": 500}}
        cleaned, corrections = v.validate_new_character(data)
        assert cleaned["attrs"]["hp"] == 500
        assert not any("hp" in c for c in corrections)

    def test_attr_raised_to_hard_min(self):
        v = AttributeValidator()
        data = {"name": "测试", "level": 1,
                "attrs": {"hp": -10}}
        cleaned, corrections = v.validate_new_character(data)
        assert cleaned["attrs"]["hp"] == 1  # DEFAULT hard_min
        assert any("hp" in c for c in corrections)

    def test_skills_truncated_at_limit(self):
        v = AttributeValidator()
        skills = [f"skill_{i}" for i in range(30)]
        data = {"name": "测试", "level": 1, "attrs": {},
                "abilities": skills}
        cleaned, corrections = v.validate_new_character(data)
        assert len(cleaned["abilities"]) == 20  # DEFAULT skill_limit
        assert any("abilities" in c for c in corrections)

    def test_tags_truncated_at_limit(self):
        v = AttributeValidator()
        tags = [f"tag_{i}" for i in range(15)]
        data = {"name": "测试", "level": 1, "attrs": {},
                "tags": tags}
        cleaned, corrections = v.validate_new_character(data)
        assert len(cleaned["tags"]) == 10  # DEFAULT tag_limit


class TestWorldConfigOverride:
    """世界级配置覆盖测试。"""

    def test_custom_attr_rules_override_defaults(self):
        v = AttributeValidator()
        v.set_attributes_schema({
            "attributes": {"hp": {"default": 100}},
        })
        v._rules = {
            "defaults": {"hard_cap": 999, "hard_min": 1},
            "attribute_rules": {
                "hp": {"hard_cap": 5000, "hard_min": 10},
            },
            "max_start_level": 50,
            "skill_limit": 20,
            "tag_limit": 10,
            "element_tag_limit": 5,
        }
        data = {"name": "测试", "level": 1,
                "attrs": {"hp": 6000}}
        cleaned, corrections = v.validate_new_character(data)
        assert cleaned["attrs"]["hp"] == 5000
        assert any("hp" in c for c in corrections)


class TestFieldUpdateValidation:
    """单字段校验测试。"""

    def test_attr_field_update_clamped(self):
        v = AttributeValidator()
        val, note = v.validate_field_update(1, "attrs.hp", 99999)
        assert val == 999
        assert note is not None

    def test_level_field_update_clamped(self):
        v = AttributeValidator()
        val, note = v.validate_field_update(1, "level", 999)
        assert val == 50
        assert note is not None

    def test_valid_value_passes_through(self):
        v = AttributeValidator()
        val, note = v.validate_field_update(1, "attrs.hp", 50)
        assert val == 50
        assert note is None

    def test_list_field_truncated(self):
        v = AttributeValidator()
        val, note = v.validate_field_update(1, "abilities",
                                            [f"s{i}" for i in range(30)])
        assert len(val) == 20
        assert note is not None


class TestSanityCheck:
    """合理性检查测试——仅警告不抛异常。"""

    def test_high_attr_total_warns(self, caplog):
        import logging
        caplog.set_level(logging.WARNING)
        v = AttributeValidator()
        data = {"name": "超强角色", "level": 1,
                "attrs": {"hp": 5000, "mp": 5000, "force": 500}}
        cleaned, _ = v.validate_new_character(data)
        assert cleaned  # 仍然成功生成
        assert any("合理性警告" in r.message for r in caplog.records)

    def test_high_level_no_skills_warns(self, caplog):
        import logging
        caplog.set_level(logging.WARNING)
        v = AttributeValidator()
        data = {"name": "空壳Boss", "level": 30,
                "attrs": {"hp": 500}, "abilities": []}
        cleaned, _ = v.validate_new_character(data)
        assert cleaned
        assert any("合理性警告" in r.message for r in caplog.records)


class TestDynamicHardCap:
    """hard_cap=dynamic 回退到默认上限的测试。"""

    def test_dynamic_hard_cap_uses_default_as_fallback(self):
        """hard_cap=dynamic 时，回退到默认 hard_cap(999)。"""
        validator = AttributeValidator()
        validator.set_attributes_schema({
            "attributes": {
                "sword_intent": {
                    "type": "int", "default": 0,
                    "cultivation_path_attr": True,
                    "validation": {"hard_cap": "dynamic", "hard_min": 0},
                },
            },
            "fields": {},
        })
        data = {"name": "测试", "attrs": {"sword_intent": 1500}}
        cleaned, corrections = validator.validate_new_character(data)
        assert cleaned["attrs"]["sword_intent"] == 999  # 默认 hard_cap
        assert len(corrections) == 1

    def test_dynamic_hard_cap_within_range(self):
        """hard_cap=dynamic 且值在默认上限内，不触发修正。"""
        validator = AttributeValidator()
        validator.set_attributes_schema({
            "attributes": {
                "sword_intent": {
                    "type": "int", "default": 0,
                    "cultivation_path_attr": True,
                    "validation": {"hard_cap": "dynamic", "hard_min": 0},
                },
            },
            "fields": {},
        })
        data = {"name": "测试", "attrs": {"sword_intent": 50}}
        cleaned, corrections = validator.validate_new_character(data)
        assert cleaned["attrs"]["sword_intent"] == 50
        assert len(corrections) == 0

    def test_validate_field_update_dynamic_cap(self):
        """validate_field_update 处理 hard_cap=dynamic 时回退到默认上限。"""
        validator = AttributeValidator()
        validator.set_attributes_schema({
            "attributes": {
                "sword_intent": {
                    "type": "int", "default": 0,
                    "cultivation_path_attr": True,
                    "validation": {"hard_cap": "dynamic", "hard_min": 0},
                },
            },
            "fields": {},
        })
        val, note = validator.validate_field_update(1, "attrs.sword_intent", 1500)
        assert val == 999  # 默认 hard_cap
        assert note is not None

    def test_validate_field_update_dynamic_cap_normal_attr(self):
        """非 dynamic 的普通属性仍走原逻辑。"""
        validator = AttributeValidator()
        validator.set_attributes_schema({
            "attributes": {
                "hp": {
                    "type": "int", "default": 50,
                    "validation": {"hard_cap": 100, "hard_min": 1},
                },
            },
            "fields": {},
        })
        val, note = validator.validate_field_update(1, "attrs.hp", 150)
        assert val == 100
        assert note is not None


class TestHiddenAttributeStripping:
    """LLM 尝试设置 hidden 属性时的校验测试。"""

    def test_create_character_strips_hidden_attrs(self):
        """create_character 时 hidden 属性被静默移除。"""
        v = AttributeValidator()
        v.set_attributes_schema({
            "attributes": {
                "hp": {"default": 50, "validation": {"hard_cap": 999, "hard_min": 1}},
                "spirit_stones": {"default": 0, "category": "economy",
                                  "validation": {"hard_cap": 999999999, "hard_min": 0}},
            },
            "fields": {},
            "llm_visibility": {
                "defaults": {"economy": "hidden"},
            },
        })
        data = {"name": "测试", "level": 1, "attrs": {"hp": 80, "spirit_stones": 100}}
        cleaned, corrections = v.validate_new_character(data)
        assert cleaned["attrs"]["hp"] == 80
        assert "spirit_stones" not in cleaned["attrs"]
        assert any("spirit_stones" in c and "hidden" in c for c in corrections)

    def test_update_field_rejects_hidden_attr(self):
        """update_character_field 时 hidden 属性拒绝修改。"""
        from lingmo_engine.plugins.character.attribute_validator import _FieldRejected
        v = AttributeValidator()
        v.set_attributes_schema({
            "attributes": {
                "hp": {"default": 50, "validation": {"hard_cap": 999, "hard_min": 1}},
                "spirit_stones": {"default": 0, "category": "economy",
                                  "validation": {"hard_cap": 999999999, "hard_min": 0}},
            },
            "fields": {},
            "llm_visibility": {
                "defaults": {"economy": "hidden"},
            },
        })
        val, note = v.validate_field_update(1, "attrs.spirit_stones", 500)
        assert isinstance(val, _FieldRejected)
        assert "hidden" in val.reason

    def test_update_field_allows_visible_attr(self):
        """visible 属性正常通过校验。"""
        v = AttributeValidator()
        v.set_attributes_schema({
            "attributes": {
                "hp": {"default": 50, "validation": {"hard_cap": 100, "hard_min": 1}},
            },
            "fields": {},
            "llm_visibility": {
                "overrides": {},
            },
        })
        val, note = v.validate_field_update(1, "attrs.hp", 80)
        assert val == 80
        assert note is None

    def test_is_field_llm_visible_delegates_to_resolver(self):
        """is_field_llm_visible 正确委托给 resolver。"""
        v = AttributeValidator()
        v.set_attributes_schema({
            "attributes": {},
            "fields": {"loot_table": {"type": "list"}, "name": {"type": "str"}},
            "llm_visibility": {
                "field_overrides": {"loot_table": "hidden"},
            },
        })
        assert v.is_field_llm_visible("loot_table") is False
        assert v.is_field_llm_visible("name") is True
        assert v.is_field_llm_visible("nonexistent") is True

    def test_is_field_llm_visible_no_schema_returns_true(self):
        """无 schema 时所有字段都可见。"""
        v = AttributeValidator()
        assert v.is_field_llm_visible("anything") is True
