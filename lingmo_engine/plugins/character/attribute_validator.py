"""AttributeValidator — 角色属性校验与修正。"""
from __future__ import annotations

import logging

from lingmo_engine.plugins.character.schema_visibility import SchemaVisibilityResolver

logger = logging.getLogger(__name__)


class _FieldRejected:
    """validate_field_update 返回此 sentinel 表示字段被拒绝修改（如 hidden 属性）。"""

    __slots__ = ("reason",)

    def __init__(self, reason: str):
        self.reason = reason


# 引擎默认校验规则
DEFAULT_VALIDATION = {
    "defaults": {
        "hard_cap": 999,
        "hard_min": 1,
    },
    "max_start_level": 50,
    "skill_limit": 20,
    "tag_limit": 10,
}


class AttributeValidator:
    """属性校验器：类型规范化 → 世界规则校验 → 合理性检查。"""

    def __init__(self):
        self._rules: dict = dict(DEFAULT_VALIDATION)
        self._attributes_schema: dict[str, dict] = {}
        self._fields_schema: dict[str, dict] = {}
        self._visibility_resolver: SchemaVisibilityResolver | None = None

    # ── 配置加载 ──

    def load_defaults(self) -> None:
        """加载引擎默认校验规则。"""
        self._rules = dict(DEFAULT_VALIDATION)

    def set_attributes_schema(self, schema: dict) -> None:
        """设置角色 schema（来自 character_schema.yaml），同时提取校验规则。"""
        self._attributes_schema = schema.get("attributes", {})
        self._fields_schema = schema.get("fields", {})
        self._merge_schema_validation_rules()

        # 构建 LLM 可见性 resolver
        self._visibility_resolver = SchemaVisibilityResolver(schema)

    def is_field_llm_visible(self, field_name: str, section: str = "fields") -> bool:
        """检查字段/属性是否对 LLM 可见。委托给内部 resolver。"""
        if not self._visibility_resolver:
            return True
        return self._visibility_resolver.is_llm_visible(field_name, section=section)

    def _merge_schema_validation_rules(self) -> None:
        """从 schema 的 validation 子键提取校验规则，合并到 self._rules。"""
        # 合并 attributes 校验规则
        attr_rules = self._rules.setdefault("attribute_rules", {})
        for name, defn in self._attributes_schema.items():
            val = defn.get("validation")
            if val:
                attr_rules[name] = val

        # 合并 fields 校验规则
        for name, defn in self._fields_schema.items():
            val = defn.get("validation")
            if val:
                field_rules = self._rules.setdefault("field_rules", {})
                field_rules[name] = val

    # ── 校验 ──

    def validate_new_character(self, char_data: dict) -> tuple[dict, list[str]]:
        """校验新创建的角色数据。

        Args:
            char_data: LLM 输出的角色字典

        Returns:
            (cleaned_data, corrections): 修正后的数据和修正说明列表
        """
        corrections: list[str] = []
        cleaned = dict(char_data)

        # 引擎层：类型规范化（不可覆盖）
        cleaned, type_corrections = self._normalize_types(cleaned)
        corrections.extend(type_corrections)

        # 引擎层：去除不在 schema 中定义的未知字段和属性
        cleaned, unknown_corrections = self._remove_unknown_fields(cleaned)
        corrections.extend(unknown_corrections)

        # 引擎层：剥离 hidden 属性（LLM 不应感知到这些属性）
        cleaned, hidden_corrections = self._strip_hidden_attrs(cleaned)
        corrections.extend(hidden_corrections)

        # 引擎层：剥离只读字段（由系统自动派生，LLM 不应设置）
        cleaned, readonly_corrections = self._strip_read_only_fields(cleaned)
        corrections.extend(readonly_corrections)

        # 世界层：范围校验
        cleaned, range_corrections = self._apply_range_rules(cleaned)
        corrections.extend(range_corrections)

        # 引擎层：合理性检查（仅警告日志）
        self._sanity_check(cleaned, corrections)

        return cleaned, corrections

    def validate_field_update(self, char_id: int, field_path: str,
                               value: object) -> tuple[object, str | None]:
        """校验单个字段的增量更新值。

        Returns:
            (corrected_value, correction_note): 修正后的值和修正说明（无修正时为 None）
        """
        parts = field_path.split(".")
        if parts[0] == "attrs" and len(parts) == 2:
            attr_name = parts[1]
            # hidden 属性拦截
            if self._visibility_resolver and not self._visibility_resolver.is_llm_visible(attr_name):
                return _FieldRejected(f"attrs.{attr_name}: 该属性为 hidden，LLM 不可修改"), None
            # read-only 属性拦截（先天资质等，创建后终身不变）
            if self._visibility_resolver and self._visibility_resolver.is_read_only(attr_name, section="attributes"):
                return _FieldRejected(f"attrs.{attr_name}: 先天资质终身不变，不可修改"), None
            if not isinstance(value, (int, float)):
                return 0, f"attrs.{attr_name}: {value}→0（类型错误，已修正为 0）"
            v = int(value)
            rules = self._get_attr_rules(attr_name)
            if v > rules["hard_cap"]:
                return rules["hard_cap"], (
                    f"attrs.{attr_name}: {v}→{rules['hard_cap']}（超过上限，已裁剪）"
                )
            if v < rules["hard_min"]:
                return rules["hard_min"], (
                    f"attrs.{attr_name}: {v}→{rules['hard_min']}（低于下限，已补齐）"
                )
            return v, None

        if field_path == "level":
            if not isinstance(value, (int, float)):
                return 1, f"level: {value}→1（类型错误，已修正）"
            v = int(value)
            level_def = self._fields_schema.get("level", {})
            max_lvl = level_def.get("validation", {}).get("max_start_level", 50)
            if v > max_lvl:
                return max_lvl, f"level: {v}→{max_lvl}（超过上限，已裁剪）"
            if v < 1:
                return 1, f"level: {v}→1（低于下限，已修正）"
            return v, None

        if field_path == "age":
            if not isinstance(value, (int, float)):
                return 0, f"age: {value}→0（类型错误，已修正）"
            v = int(value)
            age_def = self._fields_schema.get("age", {})
            validation = age_def.get("validation", {})
            age_min = validation.get("min", 0)
            age_max = validation.get("max", 999999)
            if v < age_min:
                return age_min, f"age: {v}→{age_min}（低于下限，已修正）"
            if v > age_max:
                return age_max, f"age: {v}→{age_max}（超过上限，已裁剪）"
            return v, None

        # 列表字段校验
        if field_path in self._fields_schema:
            field_def = self._fields_schema[field_path]
            if field_def.get("type", "").startswith("list"):
                # tuple 是 add/remove 语义（由 _parse_field_value 生成）
                if isinstance(value, tuple):
                    corrected, note = self._clean_list_tuple(field_path, value)
                    return corrected, note
                if not isinstance(value, list):
                    return [], f"{field_path}: 非列表类型，已重置为空列表"
                max_items = field_def.get("validation", {}).get("max_items")
                if max_items and len(value) > max_items:
                    truncated = value[:max_items]
                    return truncated, (
                        f"{field_path}: {len(value)}→{max_items}项（超过上限，已裁剪）"
                    )
                return value, None
        # 回退：硬编码列表字段
        if field_path in ("abilities", "skills", "tags"):
            if isinstance(value, tuple):
                corrected, note = self._clean_list_tuple(field_path, value)
                return corrected, note
            if not isinstance(value, list):
                return [], f"{field_path}: 非列表类型，已重置为空列表"
            limit_key = {
                "abilities": "skill_limit",
                "skills": "skill_limit",
                "tags": "tag_limit",
            }.get(field_path, "")
            if limit_key:
                limit = self._rules.get(limit_key, 99)
                if len(value) > limit:
                    truncated = value[:limit]
                    return truncated, (
                        f"{field_path}: {len(value)}→{limit}项（超过上限，已裁剪）"
                    )
            return value, None

        # 其他字段不做校验，直接通过
        return value, None

    # ── 内部：列表 tuple 清洗 ──

    @staticmethod
    def _clean_list_tuple(field_path: str, value: tuple) -> tuple[tuple, str | None]:
        """清洗列表 add/remove tuple 中条目的多余 +/- 前缀。

        LLM 有时生成 '+ability_a, +ability_b' 格式，拆分后保留多余前缀。
        """
        action, item = value
        if isinstance(item, list):
            cleaned = [e.lstrip("+-") if isinstance(e, str) else e for e in item]
            dirty = [orig for orig, c in zip(item, cleaned) if orig != c]
            if dirty:
                return (action, cleaned), (
                    f"{field_path}: 已自动去除多余前缀 {dirty}"
                )
            return value, None
        if isinstance(item, str) and item and item[0] in "+-":
            cleaned = item.lstrip("+-")
            return (action, cleaned), (
                f"{field_path}: '{item}'→'{cleaned}'（已去除多余前缀）"
            )
        return value, None

    # ── 内部：类型规范化 ──

    def _normalize_types(self, data: dict) -> tuple[dict, list[str]]:
        """Schema 驱动的类型规范化，无 schema 时回退到旧硬编码逻辑。"""
        corrections: list[str] = []
        cleaned = dict(data)

        # name 特殊处理
        name = cleaned.get("name", "")
        if not isinstance(name, str):
            name = str(name)
        name = name.strip()
        if not name:
            name = "未命名角色"
            corrections.append("name: 空值→'未命名角色'（已填充默认名称）")
        cleaned["name"] = name

        if self._fields_schema:
            # Schema 驱动路径
            for field_name, field_def in self._fields_schema.items():
                if field_name == "name":
                    continue
                cleaned, field_corrections = self._normalize_field(
                    cleaned, field_name, field_def,
                )
                corrections.extend(field_corrections)
        else:
            # 回退：硬编码字段名列表
            cleaned, legacy_corrections = self._normalize_types_legacy(cleaned)
            corrections.extend(legacy_corrections)

        # attrs.*: int
        if "attrs" in cleaned and isinstance(cleaned["attrs"], dict):
            for key in list(cleaned["attrs"].keys()):
                val = cleaned["attrs"][key]
                if not isinstance(val, int):
                    try:
                        cleaned["attrs"][key] = int(val)
                    except (ValueError, TypeError):
                        corrections.append(
                            f"attrs.{key}: {val}→0（类型错误，已修正）"
                        )
                        cleaned["attrs"][key] = 0

        return cleaned, corrections

    def _normalize_types_legacy(self, data: dict) -> tuple[dict, list[str]]:
        """旧硬编码类型规范化（无 schema 时的回退）。"""
        corrections: list[str] = []
        cleaned = dict(data)

        # level: int
        if not isinstance(cleaned.get("level"), int):
            try:
                cleaned["level"] = int(cleaned.get("level", 1))
            except (ValueError, TypeError):
                corrections.append(f"level: {cleaned.get('level')}→1（类型错误，已修正）")
                cleaned["level"] = 1

        # exp: int
        if not isinstance(cleaned.get("exp"), int):
            try:
                cleaned["exp"] = int(cleaned.get("exp", 0))
            except (ValueError, TypeError):
                cleaned["exp"] = 0

        # 字符串字段
        for str_field in ("personality", "background", "faction", "location", "avatar"):
            if str_field in cleaned and cleaned[str_field] is None:
                cleaned[str_field] = ""
            elif str_field in cleaned and not isinstance(cleaned[str_field], str):
                cleaned[str_field] = str(cleaned[str_field])

        # 列表字段
        for list_field in ("abilities", "skills", "tags", "current_affairs", "inventory"):
            if list_field in cleaned:
                if cleaned[list_field] is None:
                    cleaned[list_field] = []
                elif not isinstance(cleaned[list_field], list):
                    corrections.append(f"{list_field}: 非列表类型，已重置为空列表")
                    cleaned[list_field] = []

        # equipment
        if "equipment" in cleaned:
            if cleaned["equipment"] is None:
                cleaned["equipment"] = {}
            elif not isinstance(cleaned["equipment"], dict):
                cleaned["equipment"] = {}

        # relationships (新格式: list[dict])
        if "relationships" in cleaned:
            if cleaned["relationships"] is None:
                cleaned["relationships"] = []
            elif not isinstance(cleaned["relationships"], list):
                cleaned["relationships"] = []

        # is_alive
        if "is_alive" in cleaned and not isinstance(cleaned["is_alive"], bool):
            cleaned["is_alive"] = True

        return cleaned, corrections

    def _normalize_field(self, data: dict, field_name: str,
                         field_def: dict) -> tuple[dict, list[str]]:
        """按 schema 类型规范化单个字段。"""
        corrections: list[str] = []
        field_type = field_def.get("type", "str")
        default = field_def.get("default")
        value = data.get(field_name)

        # str / str|null
        if field_type in ("str", "str|null"):
            if value is None:
                data[field_name] = "" if "null" not in field_type else None
            elif not isinstance(value, str):
                data[field_name] = str(value)

        # int
        elif field_type == "int":
            if not isinstance(value, int):
                try:
                    data[field_name] = int(value) if value is not None else (default or 0)
                except (ValueError, TypeError):
                    fallback = default if default is not None else 0
                    data[field_name] = fallback
                    corrections.append(
                        f"{field_name}: {value}→{fallback}（类型错误，已修正）"
                    )

        # bool
        elif field_type == "bool":
            if not isinstance(value, bool):
                data[field_name] = True

        # CharacterType (enum)
        elif field_type == "CharacterType":
            allowed = field_def.get("enum", [])
            if value not in allowed:
                fallback = default or "npc"
                corrections.append(
                    f"char_type: {value}→{fallback}（不在枚举中，已修正）"
                )
                data[field_name] = fallback

        # list[str] / list[dict] / list[str|null]
        elif field_type.startswith("list"):
            if value is None:
                data[field_name] = []
            elif not isinstance(value, list):
                data[field_name] = []
                corrections.append(
                    f"{field_name}: 非列表类型，已重置为空列表"
                )

        # dict[int, int] / dict[str, str]
        elif field_type.startswith("dict"):
            if value is None:
                data[field_name] = {}
            elif not isinstance(value, dict):
                data[field_name] = {}
                corrections.append(
                    f"{field_name}: 非字典类型，已重置为空字典"
                )

        return data, corrections

    # ── 内部：移除未知字段 ──

    def _remove_unknown_fields(self, data: dict) -> tuple[dict, list[str]]:
        """移除不在 schema 中定义的顶层字段和属性键。"""
        corrections: list[str] = []

        # 移除不在 fields schema 中的顶层字段
        if self._fields_schema:
            known_fields = set(self._fields_schema.keys())
            known_fields.update(["id", "attrs", "char_type", "abilities", "temporary"])  # 始终允许
            for key in list(data.keys()):
                if key not in known_fields and not key.startswith("_"):
                    corrections.append(
                        f"{key}: 不在角色字段定义中，已移除"
                    )
                    del data[key]

        # 移除不在 attributes schema 中的属性键
        if self._attributes_schema and "attrs" in data and isinstance(data.get("attrs"), dict):
            known_attrs = set(self._attributes_schema.keys())
            cleaned_attrs = dict(data["attrs"])
            for key in list(cleaned_attrs.keys()):
                if key not in known_attrs:
                    corrections.append(
                        f"attrs.{key}: 不在属性定义中，已移除"
                    )
                    del cleaned_attrs[key]
            data["attrs"] = cleaned_attrs

        return data, corrections

    # ── 内部：范围校验 ──

    def _apply_range_rules(self, data: dict) -> tuple[dict, list[str]]:
        corrections: list[str] = []
        cleaned = dict(data)

        # level 上限
        max_level = self._rules.get("max_start_level", 50)
        if cleaned.get("level", 1) > max_level:
            corrections.append(
                f"level: {cleaned['level']}→{max_level}（超过新角色等级上限，已裁剪）"
            )
            cleaned["level"] = max_level
        if cleaned.get("level", 1) < 1:
            corrections.append(f"level: {cleaned['level']}→1（低于下限，已修正）")
            cleaned["level"] = 1

        # attrs.* 范围校验
        if "attrs" in cleaned and isinstance(cleaned["attrs"], dict):
            for key in list(cleaned["attrs"].keys()):
                rules = self._get_attr_rules(key)
                val = cleaned["attrs"][key]
                if val > rules["hard_cap"]:
                    corrections.append(
                        f"attrs.{key}: {val}→{rules['hard_cap']}（超过上限，已裁剪）"
                    )
                    cleaned["attrs"][key] = rules["hard_cap"]
                    val = rules["hard_cap"]
                if val < rules["hard_min"]:
                    corrections.append(
                        f"attrs.{key}: {val}→{rules['hard_min']}（低于下限，已补齐）"
                    )
                    cleaned["attrs"][key] = rules["hard_min"]

        # 列表字段上限
        if self._fields_schema:
            # Schema 驱动路径
            for field_name, field_def in self._fields_schema.items():
                if not field_def.get("type", "").startswith("list"):
                    continue
                if field_name not in cleaned or not isinstance(cleaned[field_name], list):
                    continue
                max_items = field_def.get("validation", {}).get("max_items")
                if max_items and len(cleaned[field_name]) > max_items:
                    corrections.append(
                        f"{field_name}: {len(cleaned[field_name])}→{max_items}项"
                        "（超过上限，已裁剪）"
                    )
                    cleaned[field_name] = cleaned[field_name][:max_items]
        else:
            # 回退：硬编码列表字段限制
            for list_field, limit_key in (
                ("abilities", "skill_limit"),
                ("skills", "skill_limit"),
                ("tags", "tag_limit"),
            ):
                if list_field in cleaned and isinstance(cleaned[list_field], list):
                    limit = self._rules.get(limit_key, 99)
                    if len(cleaned[list_field]) > limit:
                        corrections.append(
                            f"{list_field}: {len(cleaned[list_field])}→{limit}项"
                            "（超过上限，已裁剪）"
                        )
                        cleaned[list_field] = cleaned[list_field][:limit]

        return cleaned, corrections

    def _get_attr_rules(self, attr_name: str) -> dict:
        """获取指定属性的校验规则。先查 attribute_rules 具体配置，再回退 defaults。"""
        attr_rules = self._rules.get("attribute_rules", {})
        if attr_name in attr_rules:
            rules = dict(attr_rules[attr_name])
            # hard_cap=dynamic 时回退到默认上限（运行时由 mastery 系统管理）
            if rules.get("hard_cap") == "dynamic":
                rules["hard_cap"] = self._rules.get("defaults", {}).get("hard_cap", 999)
            return rules
        defaults = self._rules.get("defaults", {})
        return {
            "hard_cap": defaults.get("hard_cap", 999),
            "hard_min": defaults.get("hard_min", 1),
        }

    # ── 内部：合理性检查 ──

    def _sanity_check(self, data: dict, corrections: list[str] | None = None) -> None:
        """合理性检查，仅记录警告日志，不阻止生成。"""
        name = data.get("name", "?")
        level = data.get("level", 1)

        # 高等级无技能
        abilities = data.get("abilities", data.get("skills", []))
        if level > 10 and not abilities:
            msg = (
                f"WARNING: 角色 '{name}' Lv{level} 没有任何技能。"
                f"建议：为该角色添加合适的技能，高等级角色应有技能"
            )
            logger.warning(
                "合理性警告: 角色 '%s' Lv%d 无技能", name, level,
            )
            if corrections is not None:
                corrections.append(msg)

        # 缺少基本装备（衣服）
        equipment = data.get("equipment", {})
        if not equipment.get("body"):
            msg = (
                f"WARNING: 角色 '{name}' 没有穿着衣物（body 槽位为空），衣不蔽体。"
                f"建议：在 equipment 字段中添加 body 装备，如 "
                f"'body: 青布道袍' 或 'body: 玄铁战甲'"
            )
            logger.warning(
                "合理性警告: 角色 '%s' 缺少 body 装备", name,
            )
            if corrections is not None:
                corrections.append(msg)

    def _strip_hidden_attrs(self, data: dict) -> tuple[dict, list[str]]:
        """移除 LLM 不可见的属性，记录修正说明。"""
        if not self._visibility_resolver:
            return data, []
        corrections: list[str] = []
        if "attrs" in data and isinstance(data.get("attrs"), dict):
            for key in list(data["attrs"].keys()):
                if not self._visibility_resolver.is_llm_visible(key):
                    corrections.append(
                        f"attrs.{key}: 该属性为 hidden，已移除"
                    )
                    del data["attrs"][key]
        return data, corrections

    def _strip_read_only_fields(self, data: dict) -> tuple[dict, list[str]]:
        """移除只读字段（由系统根据 derived_from 自动派生，LLM 不应设置）。"""
        if not self._visibility_resolver:
            return data, []
        corrections: list[str] = []
        readonly_fields = self._visibility_resolver.get_read_only_fields(section="fields")
        for key in readonly_fields:
            if key in data:
                corrections.append(
                    f"{key}: 该字段为 read_only（系统自动派生），已移除"
                )
                del data[key]
        return data, corrections
