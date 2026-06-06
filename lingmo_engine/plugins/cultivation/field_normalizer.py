"""CultivationFieldNormalizer — 修炼字段规范化器。

封装所有 cultivation.yaml 驱动的字段规范化逻辑：
灵根、修炼方向、种族、修炼子阶段、境界-等级联动、LLM 枚举提示。
原先嵌入在 CharacterGenerator 中，现移至 cultivation 插件以实现引擎-世界观解耦。
"""
from __future__ import annotations

import logging
import math
import random
import re
from typing import TYPE_CHECKING

from lingmo_engine.core.types import DisplayType, ModuleResult, fuzzy_match_by_name, normalize_name

if TYPE_CHECKING:
    from lingmo_engine.core.character import Character
    from lingmo_engine.plugins.character.schema_visibility import SchemaVisibilityResolver

logger = logging.getLogger(__name__)


class CultivationFieldNormalizer:
    """修炼字段规范化器 —— 从 cultivation.yaml 驱动的所有字段处理逻辑。

    纯数据输入输出：构造时接收 cult_data（cultivation.yaml 完整数据）
    和 character_schema（提供 elements.definitions 用于灵根映射），
    不依赖任何插件类或 GameWorld。
    """

    def __init__(self, cult_data: dict, character_schema: dict | None = None):
        """
        Args:
            cult_data: cultivation.yaml 完整解析后的 dict
                       （等同于 CultivationSchema.raw 或
                        world._world_extensions["cultivation"]）。
            character_schema: character_schema.yaml 完整 dict，
                              提供 elements.definitions 用于灵根中文名→ID映射。
        """
        self._cult_data = cult_data
        self._character_schema = character_schema
        self._visibility_resolver: SchemaVisibilityResolver | None = None

        # 惰性缓存
        self._element_name_map: dict[str, str] | None = None
        self._root_quality_map: dict[int, str] | None = None
        self._path_name_map: dict[str, str] | None = None
        self._path_id_to_name: dict[str, str] | None = None
        self._path_fuzzy_index: list[tuple[str, str, str]] | None = None
        self._race_name_map: dict[str, str] | None = None
        self._race_id_to_name: dict[str, str] | None = None
        self._race_fuzzy_index: list[tuple[str, str, str]] | None = None

    # ── 能力查询 ──

    def has_cultivation_data(self) -> bool:
        """是否有修炼配置数据。"""
        return bool(self._cult_data)

    def update_schema(self, character_schema: dict | None) -> None:
        """更新 character schema 并清空依赖它的缓存。

        当 character 插件加载/变更 schema 后调用，
        确保 ensure_element_name_map 使用最新的元素定义。
        """
        self._character_schema = character_schema
        self._element_name_map = None

    def set_visibility_resolver(
        self, resolver: SchemaVisibilityResolver | None
    ) -> None:
        """更新可见性解析器引用。schema 变更时由 CharacterGenerator 同步。"""
        self._visibility_resolver = resolver

    # ── 灵根规范化 ──

    def ensure_element_name_map(self) -> dict[str, str]:
        """构建元素中文名→ID映射，惰性缓存。"""
        if self._element_name_map is not None:
            return self._element_name_map
        self._element_name_map = {}
        if self._character_schema:
            for elem in self._character_schema.get("elements", {}).get(
                "definitions", []
            ):
                name = elem.get("name", "")
                eid = elem.get("id", "")
                if name and eid:
                    self._element_name_map[name] = eid
        return self._element_name_map

    def ensure_root_quality_map(self) -> dict[int, str]:
        """构建灵根数量→品质名映射，惰性缓存。"""
        if self._root_quality_map is not None:
            return self._root_quality_map
        self._root_quality_map = {}
        if self._cult_data:
            for n, q in self._cult_data.get("spiritual_roots", {}).get(
                "count_to_quality", {}
            ).items():
                self._root_quality_map[int(n)] = q.get("name", "")
        return self._root_quality_map

    def get_cultivation_economy_data(self) -> dict:
        """返回修炼经济计算所需的完整数据快照。

        包含: stages, realms, qi_density_levels, base_absorption, root_power。
        用于年龄/灵力推断等需要访问修炼参数的场景。
        """
        if not self._cult_data:
            return {}
        return {
            "stages": self._cult_data.get("stages", []),
            "realms": self._cult_data.get("realms", []),
            "qi_density_levels": self._cult_data.get("qi_density_levels", []),
            "base_absorption": self._cult_data.get("base_absorption", {}),
            "root_power": self._cult_data.get("root_power", {}),
            "count_to_quality": self._cult_data.get("spiritual_roots", {}).get("count_to_quality", {}),
            "breakthrough_rules": self._cult_data.get("breakthrough_rules", {}),
            "cultivation_paths": self._cult_data.get("cultivation_paths", {}),
        }

    # ── 角色创建时缺失字段自动推断 ──

    def fill_default_creation_fields(
        self, character: "Character", *, substage_hint: str = "",
    ) -> str | None:
        """角色创建时自动推断修仙相关缺失字段。

        仅在字段缺失（0 或空）时填充，不覆盖已有值。
        处理: spiritual_power, age, spiritual_roots, root_quality,
              enlightenment, lifespan_remaining, 修炼精通, spirit_stones。

        Args:
            substage_hint: 可选的小境界提示（如 "初期"/"5"），
                指定后灵力限定在该小境界对应的区间内随机生成。

        Returns:
            日志说明字符串，或 None（无需推断）。
        """
        eco = self.get_cultivation_economy_data()
        if not eco:
            return None
        stages = eco.get("stages", [])
        if not stages:
            return None

        stage_id = getattr(character, "cultivation_stage", "")
        current_stage = None
        for s in stages:
            if s.get("id") == stage_id:
                current_stage = s
                break
        if current_stage is None:
            return None

        notes: list[str] = []

        # ── 灵力随机填充 ──
        sp = character.attrs.get("spiritual_power", 0)
        if sp == 0 and stage_id != "mortal":
            sp_range = current_stage.get("sp_range", [])
            if len(sp_range) == 2 and sp_range[0] is not None:
                if substage_hint:
                    new_sp, sp_note = self._fill_sp_by_substage(
                        current_stage, stage_id, substage_hint, sp_range,
                    )
                else:
                    new_sp, sp_note = self._fill_sp_full_range(
                        current_stage, stage_id, sp_range,
                    )
                if new_sp is not None:
                    character.attrs["spiritual_power"] = new_sp
                    notes.append(sp_note)
        elif substage_hint and sp != 0:
            logger.debug(
                "substage_hint '%s' ignored: character already has sp=%d",
                substage_hint, sp,
            )

        # ── 年龄推断 ──
        if character.age == 0:
            age = self._calc_age(character, stages, eco)
            if age is not None:
                character.age = age
                notes.append(f"年龄自动推断: {age}")

        # ── 灵根推断 ──
        stage_order = current_stage.get("order", 0)
        roots = getattr(character, "spiritual_roots", None) or []
        if roots == [] and stage_id != "mortal":
            if stage_order <= 2:
                root_count = random.randint(1, 5)
            elif stage_order == 3:
                root_count = random.randint(1, 3)
            else:
                root_count = random.randint(1, 2)
            all_elements = ["metal", "wood", "water", "fire", "earth"]
            roots = random.sample(all_elements, min(root_count, len(all_elements)))
            character.spiritual_roots = roots
            count_to_quality_name: dict[int, str] = {}
            for cnt, q in eco.get("count_to_quality", {}).items():
                count_to_quality_name[int(cnt)] = q.get("name", "")
            quality_name = count_to_quality_name.get(len(roots), "")
            if quality_name:
                character.root_quality = quality_name
            notes.append(f"灵根自动推断: {roots}（{quality_name}）")

        # ── 悟性推断 ──
        enlightenment = character.attrs.get("enlightenment", 0)
        if enlightenment == 0:
            en_val = self._infer_enlightenment(stage_id, eco)
            if en_val is not None:
                character.attrs["enlightenment"] = en_val
                notes.append(f"悟性自动推断: {en_val}")

        # ── 剩余寿元推断 ──
        lifespan_remaining = character.attrs.get("lifespan_remaining", 0)
        if lifespan_remaining == 0 or lifespan_remaining == 100:
            stage_lifespan = current_stage.get("lifespan", 100)
            age = character.age
            jitter = random.uniform(-stage_lifespan * 0.1, stage_lifespan * 0.1)
            remaining = int(stage_lifespan - age + jitter)
            remaining = max(age, min(remaining, stage_lifespan))
            character.attrs["lifespan_remaining"] = remaining
            notes.append(f"剩余寿元自动推断: {remaining}（境界寿元={stage_lifespan}, 年龄={age}）")

        # ── 修炼方向推断 ──
        cultivation_path = getattr(character, "cultivation_path", "") or ""
        if not cultivation_path and stage_id != "mortal":
            paths_data = eco.get("cultivation_paths", {})
            if paths_data:
                cultivation_path = random.choice(list(paths_data.keys()))
                character.cultivation_path = cultivation_path
                path_name = paths_data[cultivation_path].get("name", cultivation_path)
                notes.append(f"修炼方向自动推断: {path_name}")

        # ── 修炼方向专属精通属性推断 ──
        if cultivation_path:
            paths_data = eco.get("cultivation_paths", {})
            path_def = paths_data.get(cultivation_path)
            if path_def:
                primary_attr = path_def.get("primary_attr", {})
                attr_id = primary_attr.get("id", "")
                if attr_id and character.attrs.get(attr_id, 0) == 0:
                    mastery_val = character.level * random.randint(5, 15)
                    character.attrs[attr_id] = mastery_val
                    attr_name = primary_attr.get("name", attr_id)
                    notes.append(f"精通属性自动推断: {attr_name}={mastery_val}")

        # ── 灵石推断 ──
        spirit_stones = character.attrs.get("spirit_stones", 0)
        if spirit_stones == 0 and stage_id != "mortal":
            sp_range = current_stage.get("sp_range", [])
            if sp_range and sp_range[0] is not None:
                sp_min = sp_range[0]
                spirit_stones = int(sp_min * random.uniform(0.5, 2.0))
                character.attrs["spirit_stones"] = spirit_stones
                notes.append(f"灵石自动推断: {spirit_stones}")

        return "；".join(notes) if notes else None

    def _fill_sp_full_range(
        self, current_stage: dict, stage_id: str, sp_range: list,
    ) -> tuple[int | None, str]:
        """灵力全范围均匀随机（原有行为）。"""
        sp_max = self._sp_range_max(sp_range)
        new_sp = random.randint(sp_range[0], sp_max)
        return new_sp, f"灵力自动推断: {new_sp}（{stage_id} 灵力范围 [{sp_range[0]}, {sp_max}] 均匀随机）"

    def _fill_sp_by_substage(
        self, current_stage: dict, stage_id: str,
        substage_hint: str, sp_range: list,
    ) -> tuple[int | None, str]:
        """根据小境界提示限定灵力区间随机。"""
        normalized_sub = self.normalize_substage(substage_hint, stage_id)
        if not normalized_sub:
            new_sp, note = self._fill_sp_full_range(current_stage, stage_id, sp_range)
            return new_sp, (
                note + f"（小境界 '{substage_hint}' 无效，降级全范围）"
            )

        sub_sp_range = self.compute_sp_range_for_substage(
            current_stage, normalized_sub,
        )
        if not sub_sp_range:
            new_sp, note = self._fill_sp_full_range(current_stage, stage_id, sp_range)
            return new_sp, (
                note + f"（小境界 '{substage_hint}' 无法映射灵力区间，降级全范围）"
            )

        lo, hi = sub_sp_range
        new_sp = random.randint(lo, hi)
        return new_sp, (
            f"灵力自动推断: {new_sp}（{stage_id} 小境界 {normalized_sub} "
            f"灵力区间 [{lo}, {hi}]）"
        )

    def _infer_enlightenment(self, stage_id: str, eco: dict) -> int | None:
        """根据境界推断悟性值。"""
        if stage_id == "mortal":
            return random.randint(1, 10)
        per_transition = eco.get("breakthrough_rules", {}).get("per_transition", {})
        for _trans_key, trans_def in per_transition.items():
            requirements = trans_def.get("requirements", {})
            if requirements.get("stage") == stage_id:
                threshold = requirements.get("enlightenment")
                if threshold is not None:
                    val = int(threshold * random.uniform(0.5, 0.95))
                    return max(1, val)
                break
        return random.randint(10, 50)

    def _calc_age(self, character: "Character", stages: list[dict], eco: dict) -> int | None:
        """基于修炼体系数据计算角色默认年龄。"""
        stage_id = getattr(character, "cultivation_stage", "")
        if stage_id == "mortal":
            return random.randint(16, 60)

        current_order = -1
        for s in stages:
            if s.get("id") == stage_id:
                current_order = s.get("order", 0)
                break
        if current_order < 0:
            return None

        realm_density_map: dict[str, float] = {}
        for r in eco.get("realms", []):
            realm_density_map[r["id"]] = r.get("base_qi_density", 0.4)

        qi_levels = eco.get("qi_density_levels", [])

        def qi_speed_mult(density: float) -> float:
            for ql in qi_levels:
                r = ql.get("range", [])
                if len(r) == 2 and r[0] <= density < r[1]:
                    return ql.get("cultivation_speed_mult", 1.0)
            return 1.0

        root_quality = getattr(character, "root_quality", "")
        root_power_map = eco.get("root_power", {})
        rp_val = 0.6
        if root_quality:
            quality_to_count: dict[str, int] = {}
            for cnt, q in eco.get("count_to_quality", {}).items():
                quality_to_count[q.get("name", "")] = int(cnt)
            count_to_key = {1: "heavenly", 2: "upper", 3: "middle", 4: "lower", 5: "waste"}
            cnt = quality_to_count.get(root_quality, 3)
            key = count_to_key.get(cnt, "middle")
            if key in root_power_map:
                rp_val = root_power_map[key]

        base_rate = eco.get("base_absorption", {}).get("base", 0.025)

        total_years = 0.0
        for s in sorted(stages, key=lambda x: x.get("order", 0)):
            if s.get("order", 0) > current_order:
                break
            sp_range = s.get("sp_range", [])
            if len(sp_range) != 2 or sp_range[0] is None:
                continue
            sp_width = self._sp_range_max(sp_range) - sp_range[0]
            if sp_width <= 0:
                continue
            realm_id = s.get("realm", "mortal")
            density = realm_density_map.get(realm_id, 0.4)
            speed = qi_speed_mult(density)
            sp_per_year = base_rate * rp_val * speed * 365
            if sp_per_year <= 0:
                continue
            total_years += sp_width / sp_per_year

        variance = random.uniform(0.7, 1.3)
        age = 16 + int(total_years * variance)

        lifespan = 100
        for s in stages:
            if s.get("order") == current_order:
                lifespan = s.get("lifespan", 100)
                break
        age = min(age, int(lifespan * 0.9))
        return max(age, 16)

    @staticmethod
    def _sp_range_max(sp_range: list) -> int:
        """安全获取 sp_range 上限，null 时用下限的 1.5 倍。"""
        if sp_range[1] is not None:
            return int(sp_range[1])
        return round(sp_range[0] * 1.5)

    def normalize_root_list(self, roots: list[str]) -> tuple[list[str], list[str]]:
        """将灵根列表中的中文元素名转为ID，去重。

        LLM可能输入: ['雷灵根', '火', '木灵根', 'thunder', 'fire']
        统一转为:   ['thunder', 'fire', 'wood']
        返回 (normalized_list, notes)。
        """
        name_map = self.ensure_element_name_map()
        valid_ids = set(name_map.values())
        if not name_map:
            # 无元素映射时，仅保留已是合法ID的条目
            return [r for r in roots if r in valid_ids], []
        element_chars = "".join(name_map.keys())
        elem_pattern = re.compile(rf"([{element_chars}])灵根?")

        normalized: list[str] = []
        seen: set[str] = set()
        notes: list[str] = []

        for item in roots:
            item_str = str(item).strip()
            if not item_str:
                continue
            # 已经是合法ID
            if item_str in valid_ids:
                if item_str not in seen:
                    normalized.append(item_str)
                    seen.add(item_str)
                continue
            # 精确中文名匹配
            eid = name_map.get(item_str)
            if eid:
                if eid not in seen:
                    normalized.append(eid)
                    seen.add(eid)
                    notes.append(f"灵根 '{item_str}' → '{eid}'")
                continue
            # 从复杂文本中提取（如 "雷灵根"、"金/木"、"火灵根、木灵根"）
            matches = elem_pattern.findall(item_str)
            if matches:
                for char in matches:
                    eid = name_map.get(char)
                    if eid and eid not in seen:
                        normalized.append(eid)
                        seen.add(eid)
                        notes.append(f"灵根 '{item_str}' → '{eid}'")
            else:
                notes.append(f"灵根 '{item_str}' 无法识别，已跳过")

        return normalized, notes

    def normalize_spiritual_roots_value(
        self, value: object,
    ) -> tuple[object, str]:
        """规范化 update_character_field 的灵根值。

        处理 _parse_field_value 输出的三种格式：
        - list → 逐项规范化
        - ("add"/"remove", item) → 规范化 item，取第一个有效ID
        - 其他 → 原样返回
        """
        if isinstance(value, tuple) and len(value) == 2:
            action, item = value
            if isinstance(item, list):
                normalized, notes = self.normalize_root_list(item)
                return (action, normalized), "; ".join(notes) if notes else ""
            if isinstance(item, str):
                normalized, notes = self.normalize_root_list([item])
                if normalized:
                    return (action, normalized[0]), "; ".join(notes)
                return value, "; ".join(notes) if notes else ""
            return value, ""

        if isinstance(value, list):
            normalized, notes = self.normalize_root_list(value)
            return normalized, "; ".join(notes) if notes else ""

        return value, ""

    def sync_root_quality(self, character: Character) -> str | None:
        """根据 spiritual_roots 数量自动同步 root_quality。"""
        quality_map = self.ensure_root_quality_map()
        if not quality_map:
            return None
        roots = getattr(character, "spiritual_roots", None) or []
        n = len(roots)
        new_quality = quality_map.get(n, "")
        old_quality = getattr(character, "root_quality", "")
        if new_quality != old_quality:
            character.root_quality = new_quality
            return f"root_quality: '{old_quality}' → '{new_quality}'"
        return None

    # ── 修炼方向 ──

    def get_path_name_map(self) -> dict[str, str]:
        """构建修炼方向中文名→ID映射。

        Returns:
            {"剑修": "sword", "法修": "magic", ...}
        """
        if self._path_name_map is not None:
            return self._path_name_map
        paths = self._cult_data.get("cultivation_paths", {})
        name_map: dict[str, str] = {}
        for path_id, path_def in paths.items():
            name = path_def.get("name", "")
            if name:
                name_map[name] = path_id
            # 同时支持 ID 本身
            name_map[path_id] = path_id
        self._path_name_map = name_map
        return name_map

    def get_path_id_to_name(self) -> dict[str, str]:
        """构建修炼方向 ID→中文名映射。"""
        if self._path_id_to_name is not None:
            return self._path_id_to_name
        paths = self._cult_data.get("cultivation_paths", {})
        self._path_id_to_name = {
            pid: pdef.get("name", pid) for pid, pdef in paths.items()
        }
        return self._path_id_to_name

    def build_path_fuzzy_index(self) -> list[tuple[str, str, str]]:
        """构建修炼方向模糊匹配索引。

        Returns:
            [("sword", "剑修", "剑修"), ("magic", "法修", "法修"), ...]
        """
        if self._path_fuzzy_index is not None:
            return self._path_fuzzy_index
        paths = self._cult_data.get("cultivation_paths", {})
        self._path_fuzzy_index = [
            (pid, pdef.get("name", ""), normalize_name(pdef.get("name", "")))
            for pid, pdef in paths.items()
            if pdef.get("name")
        ]
        return self._path_fuzzy_index

    def normalize_cultivation_path(self, value: str) -> str | None:
        """将修炼方向输入规范化为 ID。三级查找：精确→名称→模糊。

        支持中文名（"剑修"）或英文 ID（"sword"），模糊输入（"剑"）。
        也支持 "主修/辅修" 格式（"sword/alchemy" 或 "剑修/丹修"）。

        Returns:
            规范化后的字符串（"sword" 或 "sword/alchemy"），或 None（无效输入）。
        """
        if not value or not isinstance(value, str):
            return None

        name_map = self.get_path_name_map()
        if not name_map:
            return value.strip() or None

        parts = value.strip().split("/")
        normalized_parts = []
        # 模糊索引提到循环外，避免重复构建
        fuzzy_index = self.build_path_fuzzy_index()
        for part in parts:
            part = part.strip()
            if not part:
                normalized_parts.append("")
                continue
            # 1. 精确匹配
            resolved = name_map.get(part)
            if resolved:
                normalized_parts.append(resolved)
                continue
            # 2. 模糊匹配
            if fuzzy_index:
                fuzzy_id = fuzzy_match_by_name(part, fuzzy_index)
                if fuzzy_id:
                    logger.info(
                        "cultivation_path: 模糊匹配 '%s' → '%s'", part, fuzzy_id
                    )
                    normalized_parts.append(fuzzy_id)
                    continue
            # 无法匹配
            return None

        return "/".join(normalized_parts) or None

    def apply_cultivation_path(
        self, character: Character, normalized: str
    ) -> str:
        """解析 "主修[/辅修]" 格式并应用到角色。

        Returns:
            联动说明文本。
        """
        notes: list[str] = []
        parts = normalized.split("/", 1)
        main_path = parts[0]
        id_to_name = self.get_path_id_to_name()

        # 设置主修
        old_main = getattr(character, "cultivation_path", "")
        character.cultivation_path = main_path
        main_name = id_to_name.get(main_path, main_path)
        if old_main != main_path:
            notes.append(
                f"主修: {id_to_name.get(old_main, old_main) or '无'} → {main_name}"
            )

        # 设置辅修（如果有）
        if len(parts) > 1:
            secondary = parts[1]
            old_secondary = getattr(character, "secondary_path", "") or ""
            character.secondary_path = secondary
            sec_name = (
                id_to_name.get(secondary, secondary) if secondary else "无"
            )
            notes.append(
                f"辅修: {id_to_name.get(old_secondary, old_secondary) or '无'} → {sec_name}"
            )

        return "；".join(notes)

    # ── 种族规范化 ──

    def get_race_name_map(self) -> dict[str, str]:
        """构建种族中文名→ID映射。

        Returns:
            {"人族": "human", "human": "human", ...}
        """
        if self._race_name_map is not None:
            return self._race_name_map
        races = self._cult_data.get("races", [])
        name_map: dict[str, str] = {}
        for race_def in races:
            race_id = race_def.get("id", "")
            name = race_def.get("name", "")
            if name and race_id:
                name_map[name] = race_id
            # 同时支持 ID 本身
            if race_id:
                name_map[race_id] = race_id
        self._race_name_map = name_map
        return name_map

    def get_race_id_to_name(self) -> dict[str, str]:
        """构建种族 ID→中文名映射。"""
        if self._race_id_to_name is not None:
            return self._race_id_to_name
        races = self._cult_data.get("races", [])
        self._race_id_to_name = {
            r.get("id", ""): r.get("name", r.get("id", ""))
            for r in races
            if r.get("id")
        }
        return self._race_id_to_name

    def build_race_fuzzy_index(self) -> list[tuple[str, str, str]]:
        """构建种族模糊匹配索引。

        Returns:
            [("human", "人族", "人族"), ("demon", "妖族", "妖族"), ...]
        """
        if self._race_fuzzy_index is not None:
            return self._race_fuzzy_index
        races = self._cult_data.get("races", [])
        self._race_fuzzy_index = [
            (r["id"], r["name"], normalize_name(r["name"]))
            for r in races
            if r.get("id") and r.get("name")
        ]
        return self._race_fuzzy_index

    def normalize_race(self, value: str) -> str | None:
        """将种族输入规范化为 ID。三级查找：精确→名称→模糊。

        支持中文名（"人族"）、英文 ID（"human"）、模糊输入（"人"）。

        Returns:
            规范化后的 ID 字符串，或 None（无效输入）。
        """
        if not value or not isinstance(value, str):
            return None

        stripped = value.strip()
        if not stripped:
            return None

        # 1. 精确匹配（ID 或中文名）
        name_map = self.get_race_name_map()
        if not name_map:
            return stripped

        resolved = name_map.get(stripped)
        if resolved:
            return resolved

        # 2. 模糊匹配
        index = self.build_race_fuzzy_index()
        if index:
            fuzzy_id = fuzzy_match_by_name(stripped, index)
            if fuzzy_id:
                logger.info("race: 模糊匹配 '%s' → '%s'", stripped, fuzzy_id)
                return fuzzy_id

        return None

    # ── 灵力驱动小境界自动计算 ──

    @staticmethod
    def compute_sp_range_for_substage(stage: dict, substage_id: str) -> tuple[int, int] | None:
        """纯函数：给定境界配置和小境界 ID，返回对应的灵力区间。

        与 compute_substage_from_stage 互为逆运算。
        使用相同的等分公式保证往返一致性。

        Args:
            stage: 境界配置 dict（来自 cultivation.yaml stages 列表）。
            substage_id: 小境界 ID，如 "5"/"early"/"late"。

        Returns:
            (lo, hi) 灵力区间元组（闭区间），或 None（无法计算时）。
        """
        sub_stages = stage.get("sub_stages", [])
        if len(sub_stages) <= 1:
            sp_range = stage.get("sp_range", [])
            if (len(sp_range) == 2 and sp_range[0] is not None
                    and sp_range[1] is not None):
                return (int(sp_range[0]), int(sp_range[1]) - 1)
            return None

        sp_range = stage.get("sp_range", [])
        if not sp_range or len(sp_range) < 2 or sp_range[1] is None:
            return None

        sp_min = float(sp_range[0])
        sp_max = float(sp_range[1])
        n = len(sub_stages)
        total_range = sp_max - sp_min

        if total_range <= 0:
            return None

        # 查找 substage_id 在 sub_stages 中的索引
        idx: int | None = None
        for i, sub in enumerate(sub_stages):
            if str(sub) == str(substage_id):
                idx = i
                break
        if idx is None:
            return None

        lo_frac = sp_min + idx * total_range / n
        hi_frac = sp_min + (idx + 1) * total_range / n

        lo_int = int(sp_min) if idx == 0 else math.ceil(lo_frac)
        hi_int = (int(sp_max) - 1) if idx == n - 1 else math.floor(hi_frac)

        if lo_int > hi_int:
            hi_int = lo_int

        return (lo_int, hi_int)

    @staticmethod
    def compute_substage_from_stage(stage: dict, spiritual_power: float) -> str:
        """纯函数：根据灵力和 stage 配置计算小境界 ID。

        灵力达到突破门槛时返回 "consummate"（圆满），表示可突破。

        Args:
            stage: 境界配置 dict（来自 cultivation.yaml stages 列表）。
            spiritual_power: 角色当前灵力值。

        Returns:
            子阶段 ID 字符串，如 "1"/"5"/"early"/"middle"/"late"/"consummate"。
        """
        sub_stages = stage.get("sub_stages", [])
        # 单子阶段（凡人、大罗金仙）→ 固定返回 "1"
        if len(sub_stages) <= 1:
            return str(sub_stages[0]) if sub_stages else "1"

        sp_range = stage.get("sp_range")
        if not sp_range or len(sp_range) < 2:
            # 无 sp_range 配置 → 降级为第一个子阶段
            return str(sub_stages[0])

        sp_min, sp_max = float(sp_range[0]), sp_range[1]
        sp = float(spiritual_power)

        # sp_max 为 null（最高境界）→ clamp 到最大子阶段
        if sp_max is None:
            return str(sub_stages[-1])

        total_range = sp_max - sp_min
        if total_range <= 0:
            return str(sub_stages[0])

        # 灵力达到或超过突破门槛 → 圆满
        if sp >= sp_max:
            return "consummate"

        ratio = (sp - sp_min) / total_range

        n = len(sub_stages)

        # 练气期 9 层：均匀分 9 档
        if n >= 9:
            tier = min(n, max(1, math.ceil(ratio * n)))
            return str(tier)

        # 3 期：early / middle / late（下界钳位防止负索引）
        idx = min(n - 1, max(0, int(ratio * n)))
        return str(sub_stages[idx])

    def compute_substage(self, stage_id: str, spiritual_power: float) -> str:
        """根据境界 ID 和灵力计算小境界。

        Args:
            stage_id: 境界 ID，如 "foundation"。
            spiritual_power: 角色当前灵力值。

        Returns:
            子阶段 ID 字符串。
        """
        stages = self._cult_data.get("stages", [])
        for s in stages:
            if s.get("id") == stage_id:
                return self.compute_substage_from_stage(s, spiritual_power)
        return "1"

    def recompute_substage(self, character: Character) -> str | None:
        """读取角色当前灵力，自动计算并写入 cultivation_substage。

        Returns:
            变更说明字符串，未变化返回 None。
        """
        stage_id = getattr(character, "cultivation_stage", "") or ""
        if not stage_id:
            return None
        sp = getattr(character, "spiritual_power", 0)
        new_sub = self.compute_substage(stage_id, sp)
        old_sub = getattr(character, "cultivation_substage", "")
        if new_sub != old_sub:
            character.cultivation_substage = new_sub
            return f"cultivation_substage: '{old_sub}' → '{new_sub}'"
        return None

    # ── 修炼子阶段规范化 ──

    def get_substage_name_map(self, stage_id: str) -> dict[str, str]:
        """构建指定境界下子阶段的中文名→ID映射。

        Args:
            stage_id: 境界ID，如 "foundation", "qi_condensation"

        Returns:
            {"初期": "early", "middle": "middle", "early": "early", ...}
            数字型子阶段返回 {"1": "1", "2": "2", ...}
        """
        if not stage_id:
            return {}

        stages = self._cult_data.get("stages", [])

        # 查找目标境界定义
        stage_def = None
        for s in stages:
            if s.get("id") == stage_id:
                stage_def = s
                break

        if stage_def is None:
            return {}

        sub_stages = stage_def.get("sub_stages", [])
        labels_cn = stage_def.get("sub_labels_cn", {})
        name_map: dict[str, str] = {}

        # 反向映射：中文名 → ID
        for sub_id, cn_name in labels_cn.items():
            name_map[cn_name] = str(sub_id)

        # ID 本身也作为键（支持英文ID直接输入）
        for sub in sub_stages:
            sub_str = str(sub)
            name_map[sub_str] = sub_str

        return name_map

    def build_substage_fuzzy_index(
        self, stage_id: str
    ) -> list[tuple[str, str, str]]:
        """构建子阶段模糊匹配索引。

        Args:
            stage_id: 境界ID

        Returns:
            [("early", "初期", "初期"), ("middle", "中期", "中期"), ...]
            数字型: [("3", "3层", "3层"), ...]
        """
        if not stage_id:
            return []

        stages = self._cult_data.get("stages", [])

        stage_def = None
        for s in stages:
            if s.get("id") == stage_id:
                stage_def = s
                break

        if stage_def is None:
            return []

        sub_stages = stage_def.get("sub_stages", [])
        labels_cn = stage_def.get("sub_labels_cn", {})
        sub_label = stage_def.get("sub_label", "")
        index: list[tuple[str, str, str]] = []

        if labels_cn:
            # 命名型子阶段：使用中文名
            for sub_id, cn_name in labels_cn.items():
                index.append((str(sub_id), cn_name, normalize_name(cn_name)))
        else:
            # 数字型子阶段：拼合 sub_label 后缀
            for sub in sub_stages:
                sub_str = str(sub)
                display = f"{sub_str}{sub_label}" if sub_label else sub_str
                index.append((sub_str, display, normalize_name(display)))

        return index

    def normalize_substage(
        self, value: str, stage_id: str
    ) -> str | None:
        """将修炼子阶段输入规范化为 ID。三级查找：精确→名称→模糊。

        支持中文名（"初期"）或英文 ID（"early"），模糊输入（"初"）。

        Args:
            value: 待规范化的子阶段值
            stage_id: 当前境界ID

        Returns:
            规范化后的 ID 字符串，或 None（无效输入）。
        """
        if not value or not isinstance(value, str):
            return None

        stripped = value.strip()
        if not stripped:
            return None

        # 1. 精确匹配（ID 或中文名）
        name_map = self.get_substage_name_map(stage_id)
        resolved = name_map.get(stripped)
        if resolved:
            return resolved

        # 2. 模糊匹配
        index = self.build_substage_fuzzy_index(stage_id)
        if index:
            fuzzy_id = fuzzy_match_by_name(stripped, index)
            if fuzzy_id:
                logger.info(
                    "substage: 模糊匹配 '%s' → '%s'", stripped, fuzzy_id
                )
                return fuzzy_id

        return None

    # ── 境界/等级联动 ──

    def level_to_stage_name(self, level: int) -> str:
        """将 level 映射到修炼阶段 ID。通过 cultivation.yaml stages 对照表。"""
        if not self._cult_data:
            return ""
        stages = self._cult_data.get("stages", [])
        level = max(0, min(13, level))
        for s in stages:
            if s.get("order") == level:
                return s.get("id", "")
        return ""

    def stage_id_to_name(self, stage_id: str) -> str:
        """将境界 ID 转换为中文显示名。"""
        if not stage_id or not self._cult_data:
            return stage_id or ""
        stages = self._cult_data.get("stages", [])
        for s in stages:
            if s.get("id") == stage_id:
                return s.get("name", stage_id)
        return stage_id

    def cascade_stage_to_level(
        self, character: Character, stage_name: str
    ) -> str:
        """cultivation_stage 变更时联动更新 level（境界阶位数字）。

        注意：cultivation_stage 标记为 read_only 后，LLM 无法触发此方法。
        保留供内部系统（如 cultivation_plugin 突破）直接调用。
        """
        if not self._cult_data:
            return ""

        stages = self._cult_data.get("stages", [])
        # 先按 name 匹配（中文名），再按 id 匹配（英文 ID）
        matched = None
        for s in stages:
            if s.get("name") == stage_name or s.get("id") == stage_name:
                matched = s
                break
        if matched is None:
            return f"未找到境界「{stage_name}」的 level 映射，level 未联动"

        new_level = matched.get("order", 0)
        old_level = character.level
        if old_level == new_level:
            return ""
        character.level = new_level
        return f"联动 level: {old_level} → {new_level}（{stage_name}）"

    def cascade_level_to_readonly(
        self,
        character: Character,
        new_level: int,
        visibility_resolver: SchemaVisibilityResolver | None = ...,  # sentinelfor backward compat
    ) -> str:
        """level 变更时自动派生所有 derived_from=level 的只读字段。

        动态查找 schema 中所有 derived_from=level 的只读字段，执行派生。
        当前典型关系：level → cultivation_stage（通过 cultivation.yaml 对照表）。
        未传入 visibility_resolver 时使用 self._visibility_resolver。
        """
        if visibility_resolver is ...:
            visibility_resolver = self._visibility_resolver

        notes: list[str] = []

        # 无 schema 时，回退到直接派生 cultivation_stage
        if not visibility_resolver:
            new_stage = self.level_to_stage_name(new_level)
            old_stage = getattr(character, "cultivation_stage", "")
            if new_stage and new_stage != old_stage:
                character.cultivation_stage = new_stage
                notes.append(
                    f"联动 cultivation_stage: {old_stage or '无'} → {new_stage}"
                )
                # 境界变化后重算小境界
                sub_note = self.recompute_substage(character)
                if sub_note:
                    notes.append(sub_note)
            return "；".join(notes)

        for field_name in visibility_resolver.get_read_only_fields(
            section="fields"
        ):
            source = visibility_resolver.get_derived_from(
                field_name, section="fields"
            )
            if source != "level":
                continue

            # cultivation_stage 派生规则：level → 对照表 → stage id
            if field_name == "cultivation_stage":
                new_stage = self.level_to_stage_name(new_level)
                old_stage = getattr(character, "cultivation_stage", "")
                if new_stage and new_stage != old_stage:
                    character.cultivation_stage = new_stage
                    notes.append(
                        f"联动 cultivation_stage: {old_stage or '无'} → {new_stage}"
                    )
                    # 境界变化后重算小境界
                    sub_note = self.recompute_substage(character)
                    if sub_note:
                        notes.append(sub_note)
            else:
                logger.warning(
                    "发现未实现的派生关系: derived_from=level → %s，已跳过",
                    field_name,
                )

        return "；".join(notes)

    # ── 枚举字段统一规范化 ──

    def normalize_enum_fields(
        self, character: Character, warnings: list[str]
    ) -> list[str]:
        """统一规范化角色的枚举类字段。

        在 create_character / update_character 路径中 from_dict 后调用。
        直接修改 character 对象的属性，返回规范化说明列表。

        规范化字段: spiritual_roots + 品质同步, race, cultivation_path,
                    secondary_path, cultivation_substage（灵力自动计算）
        """
        notes: list[str] = []

        # --- 灵根规范化 + 品质同步 ---
        roots = getattr(character, "spiritual_roots", None)
        if roots:
            normalized, root_notes = self.normalize_root_list(roots)
            character.spiritual_roots = normalized
            if root_notes:
                warnings.extend(root_notes)
        quality_note = self.sync_root_quality(character) or ""
        if quality_note:
            notes.append(quality_note)

        # --- race 规范化 ---
        race_raw = getattr(character, "race", "") or ""
        if race_raw and isinstance(race_raw, str):
            normalized_race = self.normalize_race(race_raw)
            if normalized_race is None:
                valid_names = ", ".join(self.get_race_name_map().keys())
                warnings.append(
                    f"无效的种族: '{race_raw}'。可选: {valid_names}"
                )
            elif normalized_race != race_raw:
                character.race = normalized_race
                notes.append(f"race: '{race_raw}' → '{normalized_race}'")

        # --- cultivation_path 规范化 ---
        path_raw = getattr(character, "cultivation_path", "") or ""
        if path_raw and isinstance(path_raw, str):
            normalized_path = self.normalize_cultivation_path(path_raw)
            if normalized_path is None:
                warnings.append(f"无效的修炼方向: '{path_raw}'")
            elif normalized_path != path_raw:
                character.cultivation_path = normalized_path
                notes.append(
                    f"cultivation_path: '{path_raw}' → '{normalized_path}'"
                )

        # --- secondary_path 规范化 ---
        sec_raw = getattr(character, "secondary_path", "") or ""
        if sec_raw and isinstance(sec_raw, str):
            normalized_sec = self.normalize_cultivation_path(sec_raw)
            if normalized_sec is None:
                warnings.append(f"无效的辅修方向: '{sec_raw}'")
            elif normalized_sec != sec_raw:
                character.secondary_path = normalized_sec
                notes.append(
                    f"secondary_path: '{sec_raw}' → '{normalized_sec}'"
                )

        # --- cultivation_substage 灵力自动计算 ---
        stage_id = getattr(character, "cultivation_stage", "") or ""
        if stage_id:
            sub_note = self.recompute_substage(character)
            if sub_note:
                notes.append(sub_note)

        return notes

    # ── LLM 枚举提示 ──

    def build_race_enum_hint(self) -> str:
        """从 cultivation.yaml 动态构建种族枚举说明。"""
        races = self._cult_data.get("races", [])
        if not races:
            return ""
        return "/".join(
            f"{r['id']}{r['name']}"
            for r in races
            if r.get("id") and r.get("name")
        )

    def build_path_enum_hint(self) -> str:
        """从 cultivation.yaml 动态构建修炼方向枚举说明。"""
        paths = self._cult_data.get("cultivation_paths", {})
        if not paths:
            return ""
        return "/".join(
            f"{pid}{pdef.get('name', '')}"
            for pid, pdef in paths.items()
            if pdef.get("name")
        )

    def build_field_hint(
        self, fname: str, fdef: dict
    ) -> str | None:
        """为单个修炼相关字段构建 LLM 可见的说明片段。

        处理: race, cultivation_path, spiritual_roots
        对非修炼字段返回 None，由调用方处理。
        """
        desc = fdef.get("description", "")

        if fname == "race":
            enum_hint = self.build_race_enum_hint()
            parts = [p for p in [desc, f"可选: {enum_hint}"] if p]
            return f"race（{'。'.join(parts)}）"

        if fname == "cultivation_path":
            enum_hint = self.build_path_enum_hint()
            return (
                f"cultivation_path（{desc}，"
                f"支持\"主修/辅修\"同时设置，可选: {enum_hint}）"
            )

        if fname == "spiritual_roots":
            return (
                "spiritual_roots（灵根列表，接受中文名如'雷灵根'、'火'、'火, 木'，"
                "系统自动转标准元素ID）"
            )

        # 非修炼字段，由调用方处理
        return None

    # ── 展示辅助 ──

    def format_stage_tag(self, character: Character) -> str:
        """格式化角色境界标签，用于角色列表展示。将 ID 转换为中文显示名。"""
        stage_id = getattr(character, "cultivation_stage", "") or ""
        if not stage_id:
            return ""
        stage_name = self.stage_id_to_name(stage_id)
        return f" {stage_name}" if stage_name else ""

    def format_character_display_tags(self, character: Character) -> dict:
        """构建角色统一展示标签。

        将境界、种族、修炼方向的 ID→中文转换集中到一处，
        供 _list_characters 和 get_character_summaries 共用。

        Returns:
            {"stage_tag": str, "race_tag": str, "path_tag": str}
            各值不含前导空格，调用方自行拼接格式。
        """
        # 境界
        stage_name = ""
        stage_id = getattr(character, "cultivation_stage", "") or ""
        if stage_id:
            stage_name = self.stage_id_to_name(stage_id)

        # 种族
        race_id = getattr(character, "race", "") or ""
        rmap = self.get_race_id_to_name()
        race_name = rmap.get(race_id, race_id) if race_id else ""

        # 修炼方向（主修[/辅修]）
        pmap = self.get_path_id_to_name()
        main_path = getattr(character, "cultivation_path", "") or ""
        path_name = ""
        if main_path:
            path_name = pmap.get(main_path, main_path)
            sec = getattr(character, "secondary_path", "") or ""
            if sec:
                path_name += f"/{pmap.get(sec, sec)}"

        return {"stage_tag": stage_name, "race_tag": race_name, "path_tag": path_name}

    # ── 字段更新钩子 ──

    def parse_cultivation_value(self, field: str, value) -> tuple[object, bool]:
        """解析修炼相关字段值。

        由 _parse_field_value 调用，接管 cultivation_path/secondary_path/race
        的解析分支。

        Returns:
            (parsed_value, handled) — handled=False 表示非修炼字段，调用方走通用逻辑。
        """
        if field in ("cultivation_path", "secondary_path"):
            if isinstance(value, str):
                return self.normalize_cultivation_path(value), True
            return None, True
        if field == "race":
            if isinstance(value, str):
                return self.normalize_race(value), True
            return None, True
        return value, False

    def preprocess_field_update(
        self, field: str, parsed_value
    ) -> tuple[object, str, ModuleResult | None]:
        """字段更新前的世界观预处理。

        处理：root_quality 禁写拦截、spiritual_roots 值规范化、
        race/cultivation_path 规范化失败拦截。

        Returns:
            (corrected_value, notes_str, intercept_result)
            intercept_result 非 None 时应直接返回给 LLM（字段更新被拒绝）。
        """
        # root_quality 禁止 LLM 直接修改
        if field == "root_quality":
            return (
                parsed_value,
                "",
                ModuleResult(
                    success=False,
                    log="root_quality 为系统自动维护字段，不可直接修改。"
                    "请修改 spiritual_roots，系统将自动同步品质。",
                ),
            )

        # cultivation_substage 禁止直接修改，由灵力自动计算
        if field == "cultivation_substage":
            return (
                parsed_value,
                "",
                ModuleResult(
                    success=False,
                    log="cultivation_substage 为系统自动计算字段，"
                    "由灵力自动确定，不可直接修改。",
                ),
            )

        # spiritual_roots 规范化：中文元素名→ID
        if field == "spiritual_roots":
            corrected, note = self.normalize_spiritual_roots_value(parsed_value)
            return corrected, note, None

        # race 规范化失败拦截
        if field == "race" and parsed_value is None:
            valid = ", ".join(self.get_race_name_map().keys())
            return (
                parsed_value,
                "",
                ModuleResult(
                    success=False,
                    log=f"无效的种族。可选: {valid}",
                ),
            )

        # cultivation_path/secondary_path 规范化失败拦截
        if field in ("cultivation_path", "secondary_path") and parsed_value is None:
            label = "修炼方向" if field == "cultivation_path" else "辅修方向"
            return (
                parsed_value,
                "",
                ModuleResult(success=False, log=f"无效的{label}"),
            )

        return parsed_value, "", None

    def postprocess_field_update(
        self, field: str, corrected_value, character: Character
    ) -> list[str]:
        """字段应用后的世界观后处理（级联/联动/规范化）。

        处理：level→只读字段派生、spiritual_roots→root_quality 同步、
        cultivation_path→拆分主修/辅修、spiritual_power→小境界重算。

        Returns:
            日志条目列表。
        """
        notes: list[str] = []

        # level → 派生只读字段（如 cultivation_stage）
        if field == "level":
            note = self.cascade_level_to_readonly(character, corrected_value)
            if note:
                notes.append(note)

        # spiritual_roots → root_quality 同步
        if field == "spiritual_roots":
            note = self.sync_root_quality(character)
            if note:
                notes.append(note)

        # cultivation_path → 拆分主修/辅修
        if field == "cultivation_path" and isinstance(corrected_value, str):
            note = self.apply_cultivation_path(character, corrected_value)
            if note:
                notes.append(note)

        # spiritual_power 变化时重算小境界
        if field == "spiritual_power":
            stage_id = getattr(character, "cultivation_stage", "") or ""
            if stage_id:
                new_sp = corrected_value if corrected_value is not None else 0
                new_sub = self.compute_substage(stage_id, new_sp)
                old_sub = getattr(character, "cultivation_substage", "")
                if new_sub != old_sub:
                    character.cultivation_substage = new_sub
                    notes.append(
                        f"cultivation_substage: '{old_sub}' → '{new_sub}'"
                    )

        return notes

    # ── 动态工具描述 ──

    def build_level_description(self) -> str:
        """从 cultivation.yaml 动态构建 level 参数的境界描述。

        替代 build_tools 中硬编码的境界名称列表。
        无修炼配置时返回空串（调用方使用通用回退）。
        """
        stages = self._cult_data.get("stages", [])
        if not stages:
            return ""
        parts = []
        for s in sorted(stages, key=lambda s: s.get("order", 0)):
            order = s.get("order", 0)
            name = s.get("name", "")
            if name:
                parts.append(f"{order}={name}")
        return ", ".join(parts)

    def build_spiritual_roots_value_hint(self) -> str:
        """构建 spiritual_roots 字段值提示文本。

        无修炼配置时返回空串。
        """
        if not self._cult_data:
            return ""
        return (
            "spiritual_roots 接受中文名（如 '雷灵根'、'火'、'火, 木'），"
            "系统会自动转为标准元素ID。"
        )
