from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)




class GameWorld:
    def __init__(self):
        self.setting: dict = {}
        self.items: dict[str, dict] = {}
        # 新增：装备/稀有度/分类（由 InventoryPlugin 使用）
        self.equip_slots: dict = {}
        self.item_rarities: dict = {}
        self.item_categories: dict = {}
        self._world_dir: str | None = None
        self.abilities: dict[str, dict] = {}
        self.ability_templates: dict = {}
        self.ability_budget: dict = {}
        self.ability_cost_scale: dict = {}
        self.ability_value_scale: dict = {}
        self.ability_legal_tags: list[list[str]] = []
        self.ability_tag_groups: list[dict] = []
        self.ability_tag_cost_map: dict = {}
        self.ability_exclusions: list[list[str]] = []
        self._world_extensions: dict = {}
        self.statuses: dict[str, str] = {}
        self.default_ability_id: str = "basic_attack"
        self.ability_rarities: dict = {}
        self.ability_categories: dict = {}
        # 消耗品效果模板
        self.consumable_templates: dict = {}
        self.consumable_budget: dict = {}
        self.consumable_value_scale: dict = {}
        self.consumable_legal_tags: list[list[str]] = []
        self.special_items: list[dict] = []
        self.item_tag_groups: list[dict] = []
        self.consumable_rarities: list[dict] = []
        self.consumable_exclusions: list[list[str]] = []
        # 角色标签分组
        self.character_tag_groups: list[dict] = []
        # 角色 schema（attributes + fields + elements 统一来源）
        self.attributes: dict[str, dict] = {}
        self.status_bar_order: list[str] = []
        self.elements: dict = {}
        self.fields: dict[str, dict] = {}
        self.llm_visibility: dict = {}
        self._calendar_config: dict = {}
        self._creation_config = None  # CreationConfig 实例（可选）


    @staticmethod
    def _collect_abilities(data) -> list:
        """递归提取 YAML 结构中的所有技能条目（兼容扁平列表和嵌套分组）。"""
        results = []
        if isinstance(data, list):
            for item in data:
                results.extend(GameWorld._collect_abilities(item))
        elif isinstance(data, dict):
            if "id" in data and any(k in data for k in ("name", "effects", "category", "description")):
                results.append(data)
            else:
                for v in data.values():
                    if isinstance(v, (dict, list)):
                        results.extend(GameWorld._collect_abilities(v))
        return results

    def load(self, world_dir: str | Path) -> None:
        world_dir = Path(world_dir)
        self._world_dir = str(world_dir)
        if not world_dir.exists():
            logger.warning("World directory not found: %s", world_dir)
            return

        setting_path = world_dir / "setting.yaml"
        if setting_path.exists():
            with open(setting_path, "r", encoding="utf-8") as f:
                self.setting = yaml.safe_load(f) or {}

        # 加载物品（自动扫描 items/ 目录下所有物品数据文件）
        _ITEM_CONFIG_FILES = {
            "_tags.yaml", "_templates.yaml",
            "item_categories.yaml", "item_rarities.yaml",
            "equip_slots.yaml", "equip_stats.yaml",
            "crafting.yaml",
        }
        self.items = {}
        items_dir = world_dir / "items"
        if items_dir.exists():
            for items_path in sorted(items_dir.glob("*.yaml")):
                if items_path.name.startswith("_") or items_path.name in _ITEM_CONFIG_FILES:
                    continue
                with open(items_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                top_key = items_path.stem
                items = data.get(top_key, data.get("items", [])) if isinstance(data, dict) else data
                if isinstance(items, list):
                    for i in items:
                        if isinstance(i, dict) and "id" in i:
                            self.items[i["id"]] = i

        # 加载技能（扫描 abilities/ 目录下所有非配置 yaml，递归提取技能条目）
        _ABILITY_CONFIG_FILES = {
            "_tags.yaml", "_templates.yaml",
            "ability_categories.yaml", "ability_rarities.yaml",
        }
        self.abilities = {}
        abilities_dir = world_dir / "abilities"
        if abilities_dir.exists():
            for file_path in sorted(abilities_dir.glob("*.yaml")):
                if file_path.name.startswith("_") or file_path.name in _ABILITY_CONFIG_FILES:
                    continue
                with open(file_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                for a in self._collect_abilities(data):
                    if "id" in a:
                        self.abilities[a["id"]] = a
            # 读取效果模板和预算配置
            templates_path = abilities_dir / "_templates.yaml"
            if templates_path.exists():
                with open(templates_path, "r", encoding="utf-8") as f:
                    tdata = yaml.safe_load(f) or {}
                    self.ability_templates = tdata.get("__templates__") or {}
                    self.ability_budget = tdata.get("__budget__") or {}
                    self.ability_cost_scale = tdata.get("__cost_scale__") or {}
                    self.ability_value_scale = tdata.get("__value_scale__") or {}
                    self.ability_legal_tags = tdata.get("__legal_tags__") or []
                    self.ability_exclusions = tdata.get("__exclusions__") or []
                    self.statuses = tdata.get("__statuses__") or {}
            # 加载统一效果词条定义（位于世界根目录）
            affixes_path = world_dir / "effect_affixes.yaml"
            if affixes_path.exists():
                with open(affixes_path, "r", encoding="utf-8") as f:
                    adata = yaml.safe_load(f) or {}
                    self.effect_affixes = adata.get("effect_affixes") or {}
                    self.effect_exclusions = adata.get("__exclusions__") or []
                    self.effect_cost_scale = adata.get("__cost_scale__") or {}
                    self.effect_value_scale = adata.get("__value_scale__") or {}
                    self.effect_statuses = adata.get("__statuses__") or {}
            # 加载技能标签定义（优先于 _templates.yaml 中的 __legal_tags__）
            ability_tags_path = abilities_dir / "_tags.yaml"
            if ability_tags_path.exists():
                with open(ability_tags_path, "r", encoding="utf-8") as f:
                    atdata = yaml.safe_load(f) or {}
                    groups = atdata.get("tag_groups") or []
                    if groups:
                        self.ability_tag_groups = groups
                        self.ability_legal_tags = [g["tags"] for g in groups]
                    self.ability_tag_cost_map = atdata.get("tag_cost_map") or {}

        # 加载角色 schema（替代旧 attributes.yaml）
        schema_path = world_dir / "characters" / "character_schema.yaml"
        if schema_path.exists():
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_data = yaml.safe_load(f) or {}
            self.attributes = schema_data.get("attributes", {})
            self.status_bar_order = schema_data.get("status_bar_order", [])
            self.elements = schema_data.get("elements") or {}
            self.fields = schema_data.get("fields", {})
            self.llm_visibility = schema_data.get("llm_visibility", {})

        # 加载角色标签分组（characters/_tags.yaml）
        chars_dir = world_dir / "characters"
        char_tags_path = chars_dir / "_tags.yaml"
        if char_tags_path.exists():
            with open(char_tags_path, "r", encoding="utf-8") as f:
                ctdata = yaml.safe_load(f) or {}
                groups = ctdata.get("tag_groups") or []
                if groups:
                    self.character_tag_groups = groups

        # 加载角色数据（characters/fixed/ 目录，替换旧的 npcs/monsters 单独加载）
        char_dir = world_dir / "characters" / "fixed"
        if char_dir.exists():
            from lingmo_engine.core.character_manager import CharacterManager
            from lingmo_engine.core.character import CharacterType
            self._char_manager = CharacterManager()
            self._char_manager.load(char_dir)

        # 加载装备槽位配置
        equip_slots_path = world_dir / "items" / "equip_slots.yaml"
        if equip_slots_path.exists():
            with open(equip_slots_path, "r", encoding="utf-8") as f:
                self.equip_slots = yaml.safe_load(f) or {}

        # 加载物品分类配置
        categories_path = world_dir / "items" / "item_categories.yaml"
        if categories_path.exists():
            with open(categories_path, "r", encoding="utf-8") as f:
                self.item_categories = yaml.safe_load(f) or {}

        # 加载物品稀有度配置
        rarities_path = world_dir / "items" / "item_rarities.yaml"
        if rarities_path.exists():
            with open(rarities_path, "r", encoding="utf-8") as f:
                self.item_rarities = yaml.safe_load(f) or {}

        # 加载消耗品效果模板
        consumable_templates_path = world_dir / "items" / "_templates.yaml"
        if consumable_templates_path.exists():
            with open(consumable_templates_path, "r", encoding="utf-8") as f:
                itdata = yaml.safe_load(f) or {}
                self.consumable_templates = itdata.get("__templates__") or {}
                self.consumable_budget = itdata.get("__budget__") or {}
                self.consumable_value_scale = itdata.get("__value_scale__") or {}
                self.consumable_legal_tags = itdata.get("__legal_tags__") or []
                self.consumable_rarities = itdata.get("__rarities__") or []
                self.consumable_exclusions = itdata.get("__exclusions__") or []
        # 加载物品标签定义（优先于 _templates.yaml 中的 __legal_tags__）
        item_tags_path = world_dir / "items" / "_tags.yaml"
        if item_tags_path.exists():
            with open(item_tags_path, "r", encoding="utf-8") as f:
                itagdata = yaml.safe_load(f) or {}
                groups = itagdata.get("tag_groups") or []
                if groups:
                    self.item_tag_groups = groups
                    self.consumable_legal_tags = [g["tags"] for g in groups]

        # 加载特殊道具（剧情关键道具）
        special_items_path = world_dir / "items" / "special_items.yaml"
        if special_items_path.exists():
            with open(special_items_path, "r", encoding="utf-8") as f:
                si_data = yaml.safe_load(f) or {}
                self.special_items = si_data.get("special_items", [])

        # 加载预设装备（固定角色装备，独立于特殊道具）
        preset_path = world_dir / "items" / "preset_equipment.yaml"
        if preset_path.exists():
            with open(preset_path, "r", encoding="utf-8") as f:
                pe_data = yaml.safe_load(f) or {}
                self.special_items.extend(pe_data.get("preset_equipment", []))

        # 加载技能分类配置
        ability_categories_path = world_dir / "abilities" / "ability_categories.yaml"
        if ability_categories_path.exists():
            with open(ability_categories_path, "r", encoding="utf-8") as f:
                self.ability_categories = yaml.safe_load(f) or {}

        # 加载技能稀有度配置
        ability_rarities_path = world_dir / "abilities" / "ability_rarities.yaml"
        if ability_rarities_path.exists():
            with open(ability_rarities_path, "r", encoding="utf-8") as f:
                self.ability_rarities = yaml.safe_load(f) or {}

        # 自定义模块（如 combat.py）通过 get_world_module() 按需加载

        # 加载世界扩展配置（cultivation/economy/progression 等）
        self._load_world_extensions(world_dir)

        self._load_calendar()

        # 加载角色创建配置（可选）
        creation_path = world_dir / "character_creation" / "character_creation.yaml"
        if creation_path.exists():
            from lingmo_engine.character_creation.schema import load_creation_config
            self._creation_config = load_creation_config(creation_path)
        else:
            self._creation_config = None

        logger.info("Loaded world from %s", world_dir)

    def get_system_prompt(self) -> str:
        parts = []
        world = self.setting.get("world", {})
        if world:
            parts.append(f"## 世界设定\n")
            parts.append(f"世界名称：{world.get('name', '未知')}")
        return "\n".join(parts)

    def get_character_manager(self):
        """返回 CharacterManager 实例（可能为 None）。"""
        return getattr(self, '_char_manager', None)

    def _load_world_extensions(self, world_dir: Path) -> None:
        """加载世界扩展配置文件（cultivation/economy/progression 等）。"""
        extension_files = {
            "cultivation.yaml": "cultivation",
            "economy.yaml": "economy",
            "progression.yaml": "progression",
        }
        for filename, key in extension_files.items():
            filepath = world_dir / filename
            if filepath.exists():
                with open(filepath, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                self._world_extensions[key] = data

    def _load_calendar(self) -> None:
        """加载日历配置"""
        if not self._world_dir:
            return
        path = Path(self._world_dir) / "calendar.yaml"
        if not path.exists():
            logger.debug("No calendar.yaml found at %s", path)
            return
        with open(path, "r", encoding="utf-8") as f:
            self._calendar_config = yaml.safe_load(f) or {}

    @staticmethod
    def _sanitize_module_name(name: str) -> str:
        """校验模块名安全性，防止路径遍历。"""
        if not name or len(name) > 64:
            raise ValueError(f"非法模块名: {name!r}")
        if any(c in name for c in ("/", "\\", "..", "\x00")):
            raise ValueError(f"模块名包含非法字符: {name!r}")
        return name

    def get_world_module(self, name: str) -> dict:
        """加载世界目录下的自定义模块（如 combat.py），返回模块中的公开可调用对象。"""
        if not self._world_dir:
            return {}
        name = self._sanitize_module_name(name)
        module_path = Path(self._world_dir) / f"{name}.py"
        if not module_path.exists():
            return {}
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(f"world_{name}", str(module_path))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return {
                    k: v for k, v in vars(mod).items()
                    if callable(v) and not k.startswith("_")
                }
        except Exception as e:
            logger.warning("Failed to load world module %s from %s: %s", name, module_path, e)
        return {}

    def get_combat_functions(self) -> dict:
        """向后兼容：返回世界自定义战斗公式。"""
        return self.get_world_module("combat")

    def get_calendar_config(self) -> dict:
        """返回日历配置数据（从 calendar.yaml 加载的原始 dict）。"""
        return self._calendar_config

    def get_attributes_schema(self) -> dict:
        """返回属性 schema（含 attributes、status_bar_order、elements、fields）。"""
        return self.get_character_schema()

    def get_character_schema(self) -> dict:
        """返回完整角色 schema：attributes + status_bar_order + elements + fields + llm_visibility。"""
        result = {
            "attributes": self.attributes,
            "status_bar_order": self.status_bar_order,
            "elements": self.elements,
            "fields": self.fields,
        }
        if self.llm_visibility:
            result["llm_visibility"] = self.llm_visibility
        return result

    def get_theme_dir(self) -> str | None:
        """返回世界主题目录的绝对路径。

        GameServer 会挂载该目录为 /static/theme/。
        目录应包含 theme.css 及可选的 fonts/、images/ 子目录。
        """
        if self._world_dir is None:
            return None
        theme_dir = Path(self._world_dir) / "theme"
        return str(theme_dir) if theme_dir.is_dir() else None

    def get_panel_schema_resolver(self):
        """返回 PanelSchemaResolver 实例（惰性创建、缓存复用）。"""
        from lingmo_engine.core.panel_schema_resolver import PanelSchemaResolver
        if not hasattr(self, '_panel_schema_resolver'):
            world_dir = self._world_dir or "."
            self._panel_schema_resolver = PanelSchemaResolver(world_dir)
        return self._panel_schema_resolver

    def get_combat_attrs_schema(self) -> dict:
        """返回属性名 → {name, label, default, combat_role? , combat_type? } 映射。

        包含声明了 combat_role 或 combat_type 的属性，供战斗系统使用。
        """
        mapping: dict[str, dict] = {}
        for name, defn in self.attributes.items():
            role = defn.get("combat_role")
            ctype = defn.get("combat_type")
            if role or ctype:
                entry: dict = {
                    "name": name,
                    "label": defn.get("label", name),
                    "default": defn.get("default", 0),
                }
                if role:
                    entry["combat_role"] = role
                if ctype:
                    entry["combat_type"] = ctype
                color = defn.get("color")
                if color:
                    entry["color"] = color
                pair = defn.get("pair")
                if pair:
                    entry["pair"] = pair
                core = defn.get("core")
                if core:
                    entry["core"] = core
                mapping[name] = entry
        if self.elements:
            mapping["__elements__"] = self.elements
        return mapping

    def get_ability_templates(self) -> dict:
        """返回效果模板配置。"""
        return getattr(self, "ability_templates", {})

    def get_cultivation_paths(self) -> dict:
        """返回修炼道路配置。向后兼容，从 _world_extensions 读取。"""
        cult_data = self._world_extensions.get("cultivation", {})
        return cult_data.get("cultivation_paths", {})

    def get_ability_budget(self) -> dict:
        """返回等级预算表。"""
        return getattr(self, "ability_budget", {})

    def get_ability_cost_scale(self) -> dict:
        """返回等级消耗缩放表。"""
        return getattr(self, "ability_cost_scale", {})

    def get_ability_value_scale(self) -> dict:
        """返回绝对数值增幅表。"""
        return getattr(self, "ability_value_scale", {})

    def get_tag_cost_map(self) -> dict:
        """返回 tag → 附加资源映射。"""
        return getattr(self, "ability_tag_cost_map", {})

    def get_statuses(self) -> dict[str, str]:
        """返回不可行动状态列表。"""
        return getattr(self, "statuses", {})

    def get_ability_legal_tags(self) -> list[list[str]]:
        """返回合法标签列表。"""
        return getattr(self, "ability_legal_tags", [])

    def get_ability_tag_groups(self) -> list[dict]:
        """返回技能标签分组（含 id、name、tags）。"""
        return getattr(self, "ability_tag_groups", [])

    def get_item_tag_groups(self) -> list[dict]:
        """返回物品标签分组（含 id、name、tags）。"""
        return getattr(self, "item_tag_groups", [])

    def get_character_tag_groups(self) -> list[dict]:
        """返回角色标签分组（含 id、name、tags）。"""
        return getattr(self, "character_tag_groups", [])

    def get_ability_exclusions(self) -> list[list[str]]:
        """返回效果互斥规则。"""
        return getattr(self, "ability_exclusions", [])

    def get_effect_affixes(self) -> dict:
        """返回统一效果词条定义。"""
        return getattr(self, "effect_affixes", {})

    def get_effect_exclusions(self) -> list[list[str]]:
        """返回效果互斥规则（统一）。"""
        if hasattr(self, "effect_exclusions") and self.effect_exclusions:
            return self.effect_exclusions
        return self.get_ability_exclusions()

    def get_effect_cost_scale(self) -> dict:
        """返回消耗缩放表（统一）。"""
        if hasattr(self, "effect_cost_scale") and self.effect_cost_scale:
            return self.effect_cost_scale
        return self.get_ability_cost_scale()

    def get_effect_value_scale(self) -> dict:
        """返回绝对值增幅表（统一）。"""
        if hasattr(self, "effect_value_scale") and self.effect_value_scale:
            return self.effect_value_scale
        return self.get_ability_value_scale()

    def get_effect_statuses(self) -> dict[str, str]:
        """返回不可行动状态（统一）。"""
        if hasattr(self, "effect_statuses") and self.effect_statuses:
            return self.effect_statuses
        return self.get_statuses()

    def get_default_ability_id(self) -> str:
        """返回默认技能 ID（不可遗忘、自动注入）。"""
        return getattr(self, "default_ability_id", "basic_attack")

    def build_create_ability_prompt(self) -> str:
        """从世界配置动态生成 create_ability 工具的描述文本。"""
        # 优先从统一词条定义读取类型
        affixes = self.get_effect_affixes()
        types = list(affixes.keys()) if affixes else list(self.ability_templates.keys())
        categories = [c["id"] for c in self.ability_categories.get("categories", [])]
        # 提取所有可用资源（tag_cost_map 中的 key + 默认资源）
        tag_map = self.get_tag_cost_map()
        default_resource = self._world_extensions.get("cultivation", {}).get(
            "default_resource", ""
        )
        resources: set[str] = set(tag_map.keys()) if tag_map else set()
        if default_resource:
            resources.add(default_resource)
        lines = [
            "词条类型: " + " | ".join(types),
            "分类: " + " | ".join(categories),
        ]
        # 稀有度→词条规则
        rarity_lines = []
        for r in self.get_ability_rarities().get("rarities", []):
            name = r.get("name", "")
            count = r.get("affix_count", "?")
            guarantee = r.get("guarantee")
            g_str = f"，保底一条+{guarantee}" if guarantee else ""
            rarity_lines.append(f"  {name}({r['min']}-{r['max']}): {count}条词条{g_str}")
        if rarity_lines:
            lines.append("稀有度规则:\n" + "\n".join(rarity_lines))
        # buff/debuff 需要的 stat 字段合法值
        combat_stats = [
            name for name, defn in self.attributes.items()
            if defn.get("combat_role")
        ]
        if combat_stats:
            lines.append("buff/debuff 的 stat 可选: " + " | ".join(combat_stats))
        # 标签：优先使用分组格式
        if self.ability_tag_groups:
            lines.append("合法标签:")
            for g in self.ability_tag_groups:
                lines.append(f"  {g['name']}: {' | '.join(g['tags'])}")
        else:
            tags_flat: list[str] = []
            for group in self.ability_legal_tags:
                tags_flat.extend(group)
            lines.append("合法标签: " + " ".join(tags_flat))
        lines.append("可用资源: " + " | ".join(sorted(resources)))
        # 分类加成提示
        bonus_lines = []
        for c in self.ability_categories.get("categories", []):
            bonus = c.get("combat_bonus")
            if bonus:
                bonus_lines.append(f"  {c['name']}({c['id']}): {bonus}")
        if bonus_lines:
            lines.append("分类加成:\n" + "\n".join(bonus_lines))
        # 互斥规则提示
        exclusions = self.get_ability_exclusions()
        if exclusions:
            exc_strs = [" 和 ".join(g) for g in exclusions]
            lines.append("互斥规则: " + "、".join(exc_strs) + " 不能同时出现")
        return "\n".join(lines)

    def get_ability_rarities(self) -> dict:
        """返回技能稀有度配置（raw YAML）。"""
        return getattr(self, "ability_rarities", {})

    def get_ability_rarity_info(self, rarity: int) -> dict:
        """根据稀有度数值匹配技能稀有度层级。"""
        rarities = self.get_ability_rarities().get("rarities", [])
        for r in rarities:
            if r["min"] <= rarity <= r["max"]:
                return r
        return {"id": "common", "name": "普通", "color": "#9e9e9e", "affix_count": 1, "max_stack": 3, "guarantee": None}

    def get_divine_abilities(self, path: str | None = None, rarity_tier: str | None = None) -> list[dict]:
        """返回神通预设列表，可按道路和稀有度筛选。"""
        results = [a for a in self.abilities.values() if a.get("category") == "divine"]
        if path:
            results = [a for a in results if a.get("path") == path]
        if rarity_tier:
            results = [a for a in results if a.get("rarity_tier") == rarity_tier]
        return results

    def get_consumable_templates(self) -> dict:
        """返回消耗品效果模板配置。"""
        return getattr(self, "consumable_templates", {})

    def get_consumable_budget(self) -> dict:
        """返回消耗品等级预算表。"""
        return getattr(self, "consumable_budget", {})

    def get_consumable_value_scale(self) -> dict:
        """返回消耗品数值增幅表。"""
        return getattr(self, "consumable_value_scale", {})

    def get_consumable_legal_tags(self) -> list[list[str]]:
        """返回消耗品合法标签列表。"""
        return getattr(self, "consumable_legal_tags", [])

    def get_consumable_exclusions(self) -> list[list[str]]:
        """返回消耗品效果互斥规则。"""
        return getattr(self, "consumable_exclusions", [])

    def get_consumable_rarity_info(self, rarity: int) -> dict:
        """根据稀有度数值匹配消耗品稀有度层级。"""
        # 优先从 item_rarities.yaml 读取
        item_rarities = getattr(self, "item_rarities", {})
        if isinstance(item_rarities, dict):
            for r in item_rarities.get("rarities", []):
                if r["min"] <= rarity <= r["max"]:
                    return r
        # 回退到 consumable_rarities（旧 _templates.yaml）
        for r in getattr(self, "consumable_rarities", []):
            if r["min"] <= rarity <= r["max"]:
                return r
        return {"id": "common", "name": "普通", "color": "#a0a0a0", "affix_count": 1, "max_stack": 3, "guarantee": None}

    def get_pricing_engine(self):
        """返回世界的定价引擎（懒加载）。

        返回类型遵循 core.protocols.pricing.PricingProtocol，
        具体实现由 plugins.pricing.engine.PriceEngine 注入。
        """
        if not hasattr(self, "_pricing_engine") or self._pricing_engine is None:
            # 注意：此处反向依赖 plugins 层，通过懒加载 + 协议解耦。
            # 若需完全移除耦合，可通过 set_pricing_engine() 外部注入。
            from lingmo_engine.plugins.pricing.engine import PriceEngine  # noqa: WPS433

            config = {}
            if self._world_dir:
                pricing_path = Path(self._world_dir) / "pricing.yaml"
                if pricing_path.exists():
                    with open(pricing_path, "r", encoding="utf-8") as f:
                        raw = yaml.safe_load(f) or {}
                    config = raw.get("pricing", raw)
            self._pricing_engine = PriceEngine(config)
        return self._pricing_engine

    def set_pricing_engine(self, engine) -> None:
        """注入外部定价引擎实例（遵循 PricingProtocol）。"""
        self._pricing_engine = engine

    def get_item_config_path(self, filename: str) -> str | None:
        """返回世界目录下 items/ 子目录中配置文件的完整路径。"""
        if not self._world_dir:
            return None
        path = Path(self._world_dir) / "items" / filename
        return str(path) if path.exists() else None

    @property
    def creation_config(self):
        """返回角色创建配置（可能为 None）。"""
        return self._creation_config
