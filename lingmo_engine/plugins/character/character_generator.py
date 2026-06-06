"""CharacterGenerator — LLM 角色工具、Prompt 组装、工具执行。"""
from __future__ import annotations

import json
import logging
import random
import re
from typing import TYPE_CHECKING

import yaml

from lingmo_engine.core.types import DisplayType, ModuleResult, ToolDefinition, ToolParameter
from lingmo_engine.core.types import normalize_name
from lingmo_engine.core.character import Character, CharacterType
from lingmo_engine.plugins.character.schema_visibility import SchemaVisibilityResolver

if TYPE_CHECKING:
    from lingmo_engine.core.character_manager import CharacterManager
    from lingmo_engine.plugins.character.attribute_validator import AttributeValidator

logger = logging.getLogger(__name__)

# 引擎默认生成指引（无世界配置时使用）
DEFAULT_GENERATION_MD = """\
你是一个幻想世界的叙事者，负责在叙事过程中动态创建和更新角色。

角色类型说明：
- npc: 持久角色，自动保存到存档，可反复交互。适合所有角色类型：商人、师尊、同伴、妖兽、邪修、怪物等。

创建角色时：
1. 角色应符合世界观设定，性格鲜明
2. 属性和字段的含义、范围、规则见模板中每个字段的注释说明，严格遵循
3. 使用中文编写角色名称、性格描述和背景故事
4. 角色名应独特且有辨识度，避免使用"路人甲"等占位名
5. 如果角色有特殊能力或身份，应在 tags 中体现

创建角色时请同时定义其 abilities（技能）：
- 引用已有技能：直接写技能名，如 "御剑术"
- 定义新技能：提供 name, description, rarity(0-100), category, target, tags, affixes
  - rarity: 稀有度，决定词条数量和强度，0-20凡俗, 21-40灵韵, 41-60玄妙, 61-80通天, 81-95造化, 96-100大道
  - category: attack|heal|support|special|divine
  - target: enemy|self|all_enemy|all_ally
  - affixes: 效果词条列表，词条数量由稀有度自动决定（凡俗1条→大道4条），可用类型：
    战斗类: damage(伤害), buff(增益), debuff(减益), heal(治疗), shield(护盾),
            dot(持续伤害), fixed_damage(固定伤害), fixed_dot(固定持续伤害),
            lifesteal(吸血), stun(眩晕), dispel(净化)
  - buff/debuff 需额外指定 stat: force|tenacity|agility
- 不需要定义具体数值，引擎会根据稀有度自动计算

更新角色时：
1. 根据剧情发展合理调整属性、技能和状态
2. 重大变化（转职、觉醒等）使用 update_character 全量更新
3. 常规成长（升级、学技能、换装备）使用 update_character_field 增量修改
"""


class CharacterGenerator:
    """管理 LLM 工具定义、Prompt 组装、工具执行。"""

    def __init__(self):
        self._template_yaml: str = ""  # 由 schema 生成
        self._generation_md: str = DEFAULT_GENERATION_MD
        self._examples: list[str] = []
        self._character_schema: dict | None = None
        self._character_tag_groups: list[dict] = []  # 角色标签分组
        self._world = None           # GameWorld 引用，由 plugin 注入
        self._game_state = None      # GameState 引用，由 plugin 注入
        self._custom_abilities = {}  # 技能缓存，同步到 GameState
        self._ability_name_index: dict[str, str] = {}  # name→id 索引，惰性填充
        self._visibility_resolver: SchemaVisibilityResolver | None = None
        self._normalizer = None  # 由业务插件（如 cultivation）注入的字段规范化器
        self._location_normalizer = None  # 由 MapPlugin 注入的 location 标准化器
        # 缓存：schema 驱动的 label 映射和展示配置
        self._attr_labels: dict[str, str] = {}
        self._field_labels: dict[str, str] = {}
        self._schema_fields_set: frozenset[str] = frozenset()  # schema 中已定义的字段名
        self._extra_promote_keys: frozenset[str] = frozenset()  # extra→顶层推广的字段名
        self._panel_sections: dict = {}  # panel schema sections（展示驱动）
        self._preset_templates: list[dict] = []  # 预设模板列表

    # ── 配置加载 ──

    def load_defaults(self) -> None:
        """加载引擎默认生成配置。"""
        self._template_yaml = self._generate_template_from_schema(None)
        self._generation_md = DEFAULT_GENERATION_MD
        self._examples = []

    def load_world_config(self, chars_dir: Path) -> None:
        """加载世界级角色生成配置（generation.md + examples，模板由 schema 生成）。"""
        gen_path = chars_dir / "generation.md"
        if gen_path.exists():
            self._generation_md = gen_path.read_text(encoding="utf-8")
            logger.info("CharacterGenerator: 加载生成指引 %s", gen_path)

        examples_dir = chars_dir / "examples"
        if examples_dir.is_dir():
            for yaml_file in sorted(examples_dir.glob("*.yaml")):
                self._examples.append(yaml_file.read_text(encoding="utf-8"))
            logger.info("CharacterGenerator: 加载 %d 个示例", len(self._examples))

        # 模板由 schema 自动生成
        self._template_yaml = self._generate_template_from_schema(self._character_schema)

        # 加载预设模板
        preset_path = chars_dir / "preset_templates.yaml"
        if preset_path.exists():
            try:
                with open(preset_path, "r", encoding="utf-8") as f:
                    pdata = yaml.safe_load(f) or {}
                self._preset_templates = pdata.get("templates", [])
                logger.info("CharacterGenerator: 加载 %d 个预设模板", len(self._preset_templates))
            except Exception:
                logger.warning("加载预设模板失败: %s", preset_path, exc_info=True)
                self._preset_templates = []

    def set_schema_template(self, schema: dict | None) -> None:
        """设置角色 schema，自动生成 LLM 模板。"""
        self._character_schema = schema
        # 构建 LLM 可见性 resolver
        if schema:
            self._visibility_resolver = SchemaVisibilityResolver(schema)
        else:
            self._visibility_resolver = None
        self._template_yaml = self._generate_template_from_schema(schema)
        # 通知已注入的 normalizer schema 已变更
        if self._normalizer is not None:
            self._normalizer.update_schema(schema)
            if self._visibility_resolver:
                self._normalizer.set_visibility_resolver(self._visibility_resolver)
        # 重建缓存
        self._rebuild_schema_cache()

    def _rebuild_schema_cache(self) -> None:
        """根据当前 schema 和 world 重建 label/section 缓存。"""
        schema = self._character_schema
        if not schema:
            self._attr_labels = {}
            self._field_labels = {}
            self._schema_fields_set = frozenset()
            self._extra_promote_keys = frozenset()
            return

        # label 映射
        self._attr_labels = {
            ak: ad["label"]
            for ak, ad in schema.get("attributes", {}).items()
            if ad.get("label")
        }
        self._field_labels = {
            fk: fd["label"]
            for fk, fd in schema.get("fields", {}).items()
            if fd.get("label")
        }

        # schema 已定义的字段名集合（用于过滤非 schema 字段）
        self._schema_fields_set = frozenset(
            set(schema.get("fields", {}).keys())
            | set(schema.get("attributes", {}).keys())
        )

        # extra→顶层推广字段：从 schema fields 中提取有代理关系的字段
        # 以及 extra 中有定义但 to_dict() 不自动推广的字段
        from lingmo_engine.core.character import _PROXY_TO_EXTRA
        proxy_keys = set(_PROXY_TO_EXTRA)
        # 额外检查 extra 中还有哪些字段需要推广（appearance, clothing, faction_rank 等）
        schema_fields = schema.get("fields", {})
        extra_promote = set(proxy_keys)
        for fk, fd in schema_fields.items():
            # 在 schema 中定义但 to_dict() 不自动输出的字段
            if fk not in ("name", "char_type", "is_alive", "level", "exp",
                          "summary", "tags", "background", "location",
                          "current_affairs", "faction", "relationships",
                          "abilities", "equipment", "inventory", "loot_table",
                          "temporary", "birthday", "last_updated", "age",
                          "avatar", "hobbies", "personality"):
                if fk not in extra_promote:
                    extra_promote.add(fk)
        self._extra_promote_keys = frozenset(extra_promote)

    def set_character_tag_groups(self, groups: list[dict]) -> None:
        """设置角色标签分组，用于注入系统提示词。"""
        self._character_tag_groups = groups

    @property
    def preset_templates(self) -> list[dict]:
        """返回已加载的预设模板列表。"""
        return self._preset_templates

    def _get_valid_labels(self) -> list[str]:
        """从 character_schema.yaml 获取合法关系标签集。"""
        schema = getattr(self, '_character_schema', None) or {}
        fields = schema.get('fields', {})
        rel_field = fields.get('relationships', {})
        return rel_field.get('valid_labels', [])

    def _build_race_enum_hint(self) -> str:
        """从 cultivation.yaml 动态构建种族枚举说明。"""
        n = self._normalizer
        return n.build_race_enum_hint() if n else ""

    def _build_path_enum_hint(self) -> str:
        """从 cultivation.yaml 动态构建修炼方向枚举说明。"""
        n = self._normalizer
        return n.build_path_enum_hint() if n else ""

    def _build_field_hint(self, fname: str, fdef: dict) -> str | None:
        """为单个字段构建 LLM 可见的说明片段。

        修炼字段委托给 CultivationFieldNormalizer，
        非修炼字段就地通用处理。
        """
        n = self._normalizer
        if n:
            hint = n.build_field_hint(fname, fdef)
            if hint is not None:
                return hint
        # 通用格式：field_name（description）
        desc = fdef.get("description", "")
        if desc:
            return f"{fname}（{desc}）"
        return fname

    def _build_update_field_description(self) -> str:
        """从 schema + 配置动态构建 update_character_field 的 field 参数说明。"""
        fields = self._character_schema.get("fields", {}) if self._character_schema else {}
        hints: list[str] = []

        for fname, fdef in fields.items():
            # 跳过 hidden 字段
            if self._visibility_resolver:
                if not self._visibility_resolver.is_llm_visible(fname, section="fields"):
                    continue
                # 跳过 read_only 字段
                if self._visibility_resolver.is_read_only(fname, section="fields"):
                    continue
            # core 字段由固定前缀处理
            if fdef.get("core"):
                continue

            hint = self._build_field_hint(fname, fdef)
            if hint:
                hints.append(hint)

        # 固定前缀（level/exp/attrs 的格式说明不适合放在 schema 中）
        # 收集先天资质属性名，用于生成只读提示
        readonly_attr_hint = ""
        if self._visibility_resolver:
            readonly_attrs = self._visibility_resolver.get_read_only_fields(section="attributes")
            if readonly_attrs:
                readonly_attr_hint = (
                    f"。注意：先天资质属性（{', '.join(readonly_attrs)}）"
                    "为先天定值，创建后终身不可修改"
                )
        header = (
            "要修改的字段路径。支持：level, exp, "
            "attrs.{属性名}（如 attrs.spiritual_power）"
            + readonly_attr_hint + ", "
        )
        return header + ", ".join(hints)

    @staticmethod
    def calc_attrs_from_aptitude(aptitude: float, bias: dict[str, float]) -> dict[str, int]:
        """根据资质(0-1)和偏向权重换算先天属性。

        公式: base = 20 + aptitude * 75, final = clamp(round(base * bias), 1, 100)
        """
        aptitude = max(0.0, min(1.0, aptitude))
        base = 20 + aptitude * 75

        # 战斗属性（可被 bias 影响）
        combat_attrs = ["force", "tenacity", "agility"]
        attrs: dict[str, int] = {}
        for name in combat_attrs:
            b = bias.get(name, 1.0)
            attrs[name] = max(1, min(100, round(base * b)))

        # 资源池属性（同步 max 与当前值）
        pool_mapping = {
            "vitality": bias.get("vitality", 1.0),
            "stamina": bias.get("stamina", 1.0),
            "divine_sense": bias.get("divine_sense", 1.0),
        }
        for pool_name, pool_bias in pool_mapping.items():
            max_name = f"max_{pool_name}"
            pool_val = max(1, min(100, round(base * pool_bias)))
            attrs[pool_name] = pool_val
            attrs[max_name] = pool_val

        return attrs

    def level_to_stage_name(self, level: int) -> str:
        """将 level 映射到成长体系阶段名。"""
        n = self._normalizer
        return n.level_to_stage_name(level) if n else ""

    def stage_id_to_name(self, stage_id: str) -> str:
        """将境界 ID 转换为中文显示名。"""
        n = self._normalizer
        return n.stage_id_to_name(stage_id) if n else (stage_id or "")

    def _generate_template_from_schema(self, schema: dict | None) -> str:
        """从 schema 动态生成角色 YAML 模板。"""
        if not schema:
            # 最小化回退模板（无世界配置时使用）
            return (
                "# 角色模板\n"
                "id: <自动分配>\n"
                'name: ""\n'
                "is_alive: true\n"
                "level: 1\n"
                "exp: 0\n"
                "attrs:\n"
                "  hp: 100\n"
                'personality: ""\n'
                "tags: []\n"
                'background: ""\n'
                'location: ""\n'
                "current_affairs: []\n"
                'faction: ""\n'
                "relationships: []\n"
                "abilities: []  # 引用已有技能名或定义新技能(name/rarity/category/target/affixes)\n"
                "equipment: {}\n"
                "inventory: []\n"
                "loot_table: null\n"
            )

        lines = ["# 角色模板 - 自动生成", "id: <自动分配>"]

        # 核心字段（按 fixed 顺序，带 description 注释）
        core_order = ["name", "is_alive", "level", "exp"]
        fields = schema.get("fields", {})
        for key in core_order:
            if key in fields:
                desc = fields[key].get("description", "")
                yaml_val = self._to_yaml_value(fields[key].get('default'))
                if desc:
                    lines.append(f"{key}: {yaml_val}  # {self._sanitize_comment(desc)}")
                else:
                    lines.append(f"{key}: {yaml_val}")

        # 数值属性（过滤 LLM hidden 属性，带 description 注释）
        lines.append("attrs:")
        for attr_name, attr_def in schema.get("attributes", {}).items():
            if self._visibility_resolver and not self._visibility_resolver.is_llm_visible(attr_name):
                continue
            desc = attr_def.get("description", "") or attr_def.get("label", "")
            default = attr_def.get("default", 0)
            if desc:
                lines.append(f"  {attr_name}: {default}  # {self._sanitize_comment(desc)}")
            else:
                lines.append(f"  {attr_name}: {default}")

        # 剩余非核心字段（过滤 LLM hidden 字段和只读字段，带 description 注释）
        remaining = [
            k for k in fields
            if k not in core_order and k != "abilities"
            and (not self._visibility_resolver or self._visibility_resolver.is_llm_visible(k, section="fields"))
            and (not self._visibility_resolver or not self._visibility_resolver.is_read_only(k, section="fields"))
        ]

        # abilities 段落（替代 skills 暴露给 LLM）
        lines.append("abilities: []  # 引用已有技能名或定义新技能(name/rarity/category/target/affixes)")

        for key in remaining:
            fdef = fields[key]
            desc = fdef.get("description", "")
            yaml_val = self._to_yaml_value(fdef.get('default'))
            if desc:
                lines.append(f"{key}: {yaml_val}  # {self._sanitize_comment(desc)}")
            else:
                lines.append(f"{key}: {yaml_val}")

        return "\n".join(lines) + "\n"

    @staticmethod
    def _to_yaml_value(value) -> str:
        """将 Python 值转为 YAML 字面量字符串。"""
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, str):
            return f'"{value}"'
        if isinstance(value, list):
            if not value:
                return "[]"
            items = ", ".join(
                "null" if v is None else f'"{v}"' if isinstance(v, str) else str(v)
                for v in value
            )
            return f"[{items}]"
        if isinstance(value, dict):
            if not value:
                return "{}"
            return "{}"
        return str(value)

    @staticmethod
    def _sanitize_comment(text: str) -> str:
        """清理文本中的特殊字符，确保作为 YAML 行内注释安全。"""
        # 移除换行符、制表符，替换 # 避免提前终止注释
        return text.replace("\n", " ").replace("\r", " ").replace("#", "＃").strip()

    # ── LLM 工具定义 ──

    def build_tools(self) -> list[ToolDefinition]:
        """构建角色管理工具列表。"""
        tools = []
        valid_labels = self._get_valid_labels()

        # 预设模板工具（仅在模板存在时注册）
        if self._preset_templates:
            template_ids = [t["id"] for t in self._preset_templates]
            tools.append(ToolDefinition(
                name="create_from_template",
                description=(
                    "使用预设模板快速创建角色。只需指定模板、名字、资质和境界即可，"
                    "系统自动计算属性。适合快速生成常规 NPC 或怪物。"
                    "当需要高度定制角色时，请使用 create_character 工具。"
                ),
                parameters=[
                    ToolParameter(
                        name="template_id", type="string",
                        description="预设模板 ID",
                        required=True,
                        enum=template_ids,
                    ),
                    ToolParameter(
                        name="name", type="string",
                        description="角色名称，应独特且有辨识度",
                        required=True,
                    ),
                    ToolParameter(
                        name="personality", type="string",
                        description="角色性格描述",
                        required=True,
                    ),
                    ToolParameter(
                        name="background", type="string",
                        description="角色背景故事（可选）",
                        required=False,
                    ),
                    ToolParameter(
                        name="aptitude", type="string",
                        description=(
                            "先天资质，0~1 之间的数值。"
                            "0=废材, 0.3=愚钝, 0.5=普通, 0.8=优秀, 1.0=天才"
                        ),
                        required=True,
                    ),
                    ToolParameter(
                        name="level", type="integer",
                        description=(
                            "境界等级，"
                            + (lambda d: f"0~13。{d}" if d else "0~13 的整数")(
                                self._normalizer.build_level_description() if self._normalizer else ""
                            )
                        ),
                        required=True,
                    ),
                    ToolParameter(
                        name="substage", type="string",
                        description=(
                            "角色修炼小境界，可选。"
                            "指定后灵力限定在该小境界对应的区间内随机。"
                            "练气期: 1~9层；其他境界: 初期/中期/后期"
                        ),
                        required=False,
                    ),
                    ToolParameter(
                        name="tags", type="string",
                        description=(
                            "角色特质标签，逗号分隔。"
                            "描述角色的身份、特点或属性，"
                            "如'剑修,叛徒'、'火属性,暴躁'"
                        ),
                        required=False,
                    ),
                    ToolParameter(
                        name="story_context", type="string",
                        description="创建该角色的剧情原因简述",
                        required=True,
                    ),
                ],
                plugin_name="character",
            ))

        # 原有工具
        tools.append(ToolDefinition(
            name="create_character",
            description=(
                "根据剧情需要创建一个新角色。提供完整的角色 YAML 数据。"
                "在叙事中自然需要引入新角色时调用此工具。"
            ),
            parameters=[
                ToolParameter(
                    name="char_yaml", type="string",
                    description=(
                        "新角色的完整 YAML 数据。模板格式：\n"
                        "```yaml\n" + self._template_yaml + "\n```\n"
                        "id 字段留空，引擎自动分配。角色统一为持久角色（持久角色，自动保存到存档）。\n"
                        "abilities 字段：字符串引用已有技能名，或对象定义新技能 "
                        "(name/level/rarity/effect_slots)。引擎自动生成技能数值。\n"
                        "abilities 字段由引擎自动填充，无需提供。\n"
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="substage", type="string",
                    description=(
                        "角色修炼小境界，可选。"
                        "指定后灵力限定在该小境界对应的区间内随机。"
                        "练气期: 1~9层；其他境界: 初期/中期/后期"
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="story_context", type="string",
                    description=(
                        "创建该角色的剧情原因简述，"
                        "例如'酒馆中遇到的商人，向玩家兜售情报'"
                    ),
                    required=True,
                ),
            ],
            plugin_name="character",
        ))
        tools.append(ToolDefinition(
            name="update_character",
            description=(
                "全量重写已有角色的数据。用于角色发生重大变化时，"
                "如转职、觉醒、阵营转换等。"
            ),
            parameters=[
                ToolParameter(
                    name="character_id", type="integer",
                    description="要更新的角色 ID",
                    required=True,
                ),
                ToolParameter(
                    name="char_yaml", type="string",
                    description="角色的完整新 YAML 数据（替换原有数据）",
                    required=True,
                ),
                ToolParameter(
                    name="reason", type="string",
                    description="全量更新的原因，例如'角色完成转职仪式'",
                    required=True,
                ),
            ],
            plugin_name="character",
        ))
        tools.append(ToolDefinition(
            name="update_character_field",
            description=(
                "增量修改角色的指定字段。用于角色常规成长变化，"
                "如提升等级、学会新技能、更换装备、改变位置等。"
                "支持的操作: 覆盖(scalar/string/dict)、追加(list append)、移除(list remove)。"
            ),
            parameters=[
                ToolParameter(
                    name="character_id", type="integer",
                    description="要修改的角色 ID",
                    required=True,
                ),
                ToolParameter(
                    name="field", type="string",
                    description=self._build_update_field_description(),
                    required=True,
                ),
                ToolParameter(
                    name="value", type="string",
                    description=(
                        "新的字段值。数字类型字段传入数字，字符串传入字符串，"
                        "列表字段传入 JSON 数组字符串。"
                        "列表字段可在值前加 '+'(追加)或 '-'(移除)，"
                        "如 '+火球术' 追加技能，'-旧技能' 移除技能。"
                        + (self._normalizer.build_spiritual_roots_value_hint()
                           if self._normalizer else "")
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="reason", type="string",
                    description="修改原因简述，例如'经过修炼提升了攻击力'",
                    required=True,
                ),
            ],
            plugin_name="character",
        ))
        tools.append(ToolDefinition(
            name="list_characters",
            description=(
                "列出当前世界中的角色。可按位置或类型筛选。"
                "用于了解当前场景中有哪些角色，避免重复创建。"
            ),
            parameters=[
                ToolParameter(
                    name="filter_type", type="string",
                    description="筛选类型: 'all'（全部）, 'location'（按位置）, 'type'（按类型）",
                    required=False,
                    enum=["all", "location", "type"],
                ),
                ToolParameter(
                    name="filter_value", type="string",
                    description="筛选值。filter_type=location 时为位置名，filter_type=type 时为 npc/player/pet",
                    required=False,
                ),
            ],
            plugin_name="character",
        ))
        tools.append(ToolDefinition(
            name="get_character_detail",
            description=(
                "查看角色的完整详情（属性、境界、技能、关系、装备等）。"
                "在需要深入了解某个角色时调用，例如准备让 NPC 登场、编写互动对话、"
                "或检查角色当前状态。返回的信息已过滤系统内部字段，仅包含叙事所需数据。"
            ),
            parameters=[
                ToolParameter(
                    name="character_id", type="integer",
                    description="要查询的角色 ID",
                    required=True,
                ),
            ],
            plugin_name="character",
        ))
        tools.append(ToolDefinition(
            name="update_relationship",
            description=(
                "管理角色间的人际关系。可建立(add)、变更(change)或移除(remove)关系。"
                "label 必须从合法标签集中选择。"
                "在叙述涉及角色关系前，先用 query_relationship 查询真实关系，避免臆造。"
            ),
            parameters=[
                ToolParameter(
                    name="character_id", type="integer",
                    description="要修改哪个角色的关系（通常是玩家 ID 0）",
                    required=True,
                ),
                ToolParameter(
                    name="target_id", type="integer",
                    description="关系对象的角色 ID",
                    required=True,
                ),
                ToolParameter(
                    name="action", type="string",
                    description="操作类型: add(建立新关系)、change(变更已有关系)、remove(移除关系)",
                    required=True,
                    enum=["add", "change", "remove"],
                ),
                ToolParameter(
                    name="label", type="string",
                    description=(
                        "关系标签，必须从合法标签集中选择。"
                        f"合法标签: {', '.join(valid_labels)}"
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="desc", type="string",
                    description="关系来源描述，≤30 字，说明何时何地因何建立此关系",
                    required=False,
                ),
                ToolParameter(
                    name="reason", type="string",
                    description="修改原因简述",
                    required=True,
                ),
            ],
            plugin_name="character",
        ))
        tools.append(ToolDefinition(
            name="query_relationship",
            description=(
                "查询角色的真实人际关系。在叙述涉及某角色前，先查询真实关系状态，避免臆造不存在的师徒、旧识等关系。"
            ),
            parameters=[
                ToolParameter(
                    name="character_id", type="integer",
                    description="查询谁的关系",
                    required=True,
                ),
                ToolParameter(
                    name="target_id", type="integer",
                    description="指定目标角色 ID，为空则返回全部关系",
                    required=False,
                ),
            ],
            plugin_name="character",
        ))

        # ── 技能创建工具 ──
        tools.append(ToolDefinition(
            name="create_ability",
            description=(
                "创建新技能。指定词条类型，系统根据稀有度自动决定词条数量和强度。"
                "可通过 for_entity 参数在创建后立即赋予给目标角色，不传则只创建定义。"
            ),
            parameters=[
                ToolParameter(
                    name="abilities",
                    type="array",
                    description=(
                        "技能列表。每项格式:\n"
                        '{\n'
                        '  "name": "技能名",\n'
                        '  "rarity": 55,\n'
                        '  "category": "attack|heal|support|special|divine",\n'
                        '  "target": "enemy|self|all_enemy|all_ally (技能目标，所有词条继承此值，个别词条可覆盖)",\n'
                        '  "description": "技能描述文本",\n'
                        '  "tags": ["标签1", "标签2"],\n'
                        '  "affixes": [\n'
                        '    {"type": "damage|heal|buff|debuff|shield|dispel|lifesteal|fixed_damage|fixed_dot|dot|stun",\n'
                        '     "stat": "force|tenacity|agility (buff/debuff必填，指定影响的属性)}\n'
                        '  ]\n'
                        '}\n'
                        "词条数量由稀有度决定(凡俗1条→大道4条)，不足系统随机补足，多余裁剪。"
                        "效果数值（power/modifier/value）由系统自动决定。\n\n"
                    ) + (self._world.build_create_ability_prompt() if self._world else ""),
                    required=True,
                ),
                ToolParameter(
                    name="for_entity",
                    type="string",
                    description=(
                        "可选，创建后自动将技能赋予给目标角色。"
                        "支持: \"player\"(玩家)、角色ID、角色名称。"
                        "不传则只创建定义，需手动分配。"
                    ),
                    required=False,
                ),
            ],
            plugin_name="character",
        ))

        return tools

    def build_system_prompt_fragment(self) -> str:
        """构建注入 LLM 系统提示的角色生成指引。"""
        parts = []
        # 注入预设模板摘要
        if self._preset_templates:
            lines = [
                "## 预设模板",
                "优先使用 create_from_template 快速创建角色，无需组装完整 YAML。",
                "可用模板：",
            ]
            for t in self._preset_templates:
                lines.append(f"- {t['id']}（{t['name']}）：{t['description']}")
            lines.append(
                "当模板适用时调用 create_from_template，需要精细定制时再使用 create_character。"
            )
            parts.append("\n".join(lines))
        if self._generation_md:
            parts.append("## 角色生成指引\n" + self._generation_md)
        if self._template_yaml:
            parts.append(
                "## 角色 YAML 模板（新角色请严格按此格式编写）\n"
                "```yaml\n" + self._template_yaml + "\n```"
            )
        if self._examples:
            lines = [
                "## 角色示例",
                "**注意：以下仅为格式示例，并非当前活跃角色。**",
            ]
            for i, example in enumerate(self._examples, 1):
                lines.append(f"### 示例 {i}\n```yaml\n{example}\n```")
            parts.append("\n".join(lines))
        if self._character_tag_groups:
            tag_lines = ["## 合法标签"]
            for g in self._character_tag_groups:
                tag_lines.append(f"  {g['name']}: {' | '.join(g['tags'])}")
            parts.append("\n".join(tag_lines))
        return "\n\n".join(parts)

    def get_character_summaries(self, cm: "CharacterManager | None") -> str:
        """返回当前角色摘要，用于注入 LLM 上下文。"""
        if cm is None:
            return ""
        chars = cm.all()
        if not chars:
            return "[当前角色] 暂无角色。如果剧情需要，可调用 create_character 工具创建。"

        # 构建主角关系索引
        player_rels = {}
        player = None
        try:
            player = cm.player
            if player.relationships:
                for rel in player.relationships:
                    player_rels[rel.get("target_id")] = rel.get("label", "")
        except RuntimeError:
            pass

        lines = ["[当前角色]"]
        for c in chars:
            lifecycle = "临时" if getattr(c, "temporary", False) else "持久"
            rel_tag = f" [{player_rels[c.id]}]" if c.id in player_rels else ""
            dtags = self._normalizer.format_character_display_tags(c) if self._normalizer else {}
            stage_tag = f" {dtags['stage_tag']}" if dtags.get("stage_tag") else ""
            race_tag = f" {dtags['race_tag']}" if dtags.get("race_tag") else ""
            path_tag = dtags.get("path_tag", "")
            age_tag = f"{c.age}岁" if c.age else ""
            lines.append(
                f"- [{c.char_type.value}·{lifecycle}] {c.name} (id={c.id}, "
                f"Lv{c.level}{stage_tag}{race_tag}{', ' + age_tag if age_tag else ''}, "
                f"{c.location or '未知位置'}): "
                f"{c.personality[:50] if c.personality else '无性格描述'}{rel_tag}"
            )
            if c.tags:
                lines.append(f"  标签: {', '.join(c.tags[:5])}")
            # 修炼方向展示
            if path_tag:
                lines.append(f"  修炼: {path_tag}")
            if c.abilities:
                lines.append(f"  技能: {', '.join(c.abilities[:5])}")
            # 装备叙事效果 — 展示角色装扮描述
            equip_narratives = self._collect_equipment_narratives(c)
            if equip_narratives:
                lines.append(f"  装扮: {'；'.join(equip_narratives)}")
        return "\n".join(lines)

    def _collect_equipment_narratives(self, character) -> list[str]:
        """收集角色装备的叙事效果文本（appearance 类别优先）。"""
        equipment = getattr(character, 'equipment', None)
        if not equipment:
            return []

        bus = getattr(self, '_event_bus', None)
        if bus is None:
            return []

        from lingmo_engine.core.events import PluginEvent
        narrative_data = bus.request(PluginEvent.EQUIPMENT_GET_NARRATIVE, equipment)
        if not narrative_data:
            return []

        texts = []
        for entry in narrative_data:
            effects = entry.get("effects", {})
            # 优先取 appearance 类别
            if "appearance" in effects:
                texts.append(effects["appearance"])
            else:
                # 取第一个效果
                for _cat, text in effects.items():
                    texts.append(text)
                    break
            if len(texts) >= 2:
                break
        return texts

    # ── 工具执行 ──

    def execute_tool(
        self, tool_name: str, params: dict,
        character_manager: "CharacterManager | None",
        validator: "AttributeValidator",
        event_bus=None,
    ) -> ModuleResult:
        """分发工具调用。"""
        if character_manager is None:
            return ModuleResult(
                success=False,
                log="CharacterManager 不可用，无法执行角色操作",
            )

        if tool_name == "create_from_template":
            return self._create_from_template(params, character_manager,
                                               validator, event_bus)
        if tool_name == "create_character":
            return self._create_character(params, character_manager,
                                          validator, event_bus)
        if tool_name == "update_character":
            return self._update_character(params, character_manager,
                                          validator, event_bus)
        if tool_name == "update_character_field":
            return self._update_field(params, character_manager,
                                       validator, event_bus)
        if tool_name == "list_characters":
            return self._list_characters(params, character_manager)
        if tool_name == "get_character_detail":
            return self._get_character_detail(params, character_manager)
        if tool_name == "update_relationship":
            return self._update_relationship(params, character_manager)
        if tool_name == "query_relationship":
            return self._query_relationship(params, character_manager)
        if tool_name == "create_ability":
            return self._create_ability_tool(params, character_manager)
        return ModuleResult(success=False, log=f"未知角色工具: {tool_name}")

    # ── 模板自动赋予技能 ──

    # 境界 → 稀有度范围映射（上限 80，不超过通天）
    _RARITY_RANGES: list[tuple[int, int]] = [
        (0, 20),   # 0: 凡人
        (0, 30),   # 1: 练气
        (20, 40),  # 2: 筑基
        (41, 60),  # 3: 金丹
        (41, 70),  # 4: 元婴
        (41, 70),  # 5: 化神
        (61, 80),  # 6: 虚空
        (61, 80),  # 7: 渡劫
        (61, 80),  # 8: 大乘
        (61, 80),  # 9: 合道
        (61, 80),  # 10: 大道
        (61, 80),  # 11: 金仙
        (61, 80),  # 12: 太乙金仙
        (61, 80),  # 13: 大罗金仙
    ]

    # 境界 → 基础技能数量
    _BASE_SKILL_COUNTS: list[int] = [1, 2, 2, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4, 4]

    @staticmethod
    def _get_rarity_range(level: int) -> tuple[int, int]:
        """根据境界等级返回稀有度 (min, max) 范围。"""
        try:
            level = int(level)
        except (TypeError, ValueError):
            level = 0
        idx = max(0, min(level, len(CharacterGenerator._RARITY_RANGES) - 1))
        return CharacterGenerator._RARITY_RANGES[idx]

    @staticmethod
    def _get_skill_count(level: int, aptitude: float) -> int:
        """根据境界和资质计算应赋予的技能数量。"""
        try:
            level = int(level)
        except (TypeError, ValueError):
            level = 0
        idx = max(0, min(level, len(CharacterGenerator._BASE_SKILL_COUNTS) - 1))
        count = CharacterGenerator._BASE_SKILL_COUNTS[idx]
        try:
            if float(aptitude) >= 0.8:
                count += 1
        except (TypeError, ValueError):
            pass
        return count

    def _auto_assign_skills(
        self, tags: list[str], level: int, aptitude: float, template: dict,
    ) -> list[str]:
        """根据 tags/level/aptitude 从模板技能池自动赋予技能。

        返回技能 ID 列表。无 skill_pools 配置时返回空列表。
        fixed 技能始终包含且不受稀有度范围限制，但计入 target_count 配额。
        """
        pools = template.get("skill_pools")
        if not pools:
            return []

        tag_elements = pools.get("tag_elements", {})
        fixed = pools.get("fixed", [])
        fallback = pools.get("fallback", [])

        # 1. 收集偏好元素
        preferred_elements: list[str] = []
        for tag in tags:
            if tag in tag_elements:
                preferred_elements.extend(tag_elements[tag])
        preferred_elements = list(dict.fromkeys(preferred_elements))

        # 2. 确定稀有度范围和技能数量
        rarity_min, rarity_max = self._get_rarity_range(level)
        target_count = self._get_skill_count(level, aptitude)

        # 3. 从 world.abilities 中筛选候选技能
        candidates: list[dict] = []
        if preferred_elements and self._world:
            for aid, adef in self._world.abilities.items():
                if aid in fixed:
                    continue
                rarity = adef.get("rarity", 0)
                if rarity < rarity_min or rarity > rarity_max:
                    continue
                ability_tags = adef.get("tags", [])
                if any(elem in ability_tags for elem in preferred_elements):
                    candidates.append(adef)

        # 4. 优先类型混搭：按 category 分组，轮流抽取
        result_ids: list[str] = list(fixed)
        remaining = target_count - len(result_ids)

        if candidates and remaining > 0:
            by_category: dict[str, list[dict]] = {}
            for c in candidates:
                cat = c.get("category", "attack")
                by_category.setdefault(cat, []).append(c)

            priority = ["attack", "heal", "support"]
            sorted_cats = sorted(
                by_category.keys(),
                key=lambda cat: priority.index(cat) if cat in priority else 99,
            )

            selected: list[str] = []
            pool_indices = {cat: 0 for cat in sorted_cats}
            for cat in sorted_cats:
                random.shuffle(by_category[cat])

            while len(selected) < remaining:
                picked_any = False
                for cat in sorted_cats:
                    if len(selected) >= remaining:
                        break
                    idx = pool_indices[cat]
                    if idx < len(by_category[cat]):
                        aid = by_category[cat][idx]["id"]
                        if aid not in selected:
                            selected.append(aid)
                            picked_any = True
                        pool_indices[cat] = idx + 1
                if not picked_any:
                    break

            result_ids.extend(selected)

        # 5. 候选不足时用 fallback 补充
        still_need = target_count - len(result_ids)
        if still_need > 0 and fallback:
            for fb in fallback:
                if fb not in result_ids:
                    result_ids.append(fb)
                    still_need -= 1
                    if still_need <= 0:
                        break

        return result_ids

    def _create_from_template(
        self, params: dict, cm: "CharacterManager",
        validator: "AttributeValidator", event_bus,
    ) -> ModuleResult:
        """通过预设模板快速创建角色。"""
        template_id = params.get("template_id", "")
        name = str(params.get("name", "")).strip()
        personality = str(params.get("personality", "")).strip()
        background = str(params.get("background", "")).strip()
        story_context = str(params.get("story_context", "")).strip()
        tags_str = str(params.get("tags", "")).strip()
        substage_hint = str(params.get("substage", "")).strip()

        # 查找模板
        template = None
        for t in self._preset_templates:
            if t["id"] == template_id:
                template = t
                break
        if template is None:
            available = ", ".join(t["id"] for t in self._preset_templates)
            return ModuleResult(
                success=False,
                log=f"模板 '{template_id}' 不存在。可用模板: {available}",
            )

        # 必填校验
        if not name:
            return ModuleResult(success=False, log="name 为必填参数")

        # 解析资质
        try:
            aptitude = float(params.get("aptitude", 0.5))
            aptitude = max(0.0, min(1.0, aptitude))
        except (ValueError, TypeError):
            aptitude = 0.5

        # 解析等级
        try:
            level = int(params.get("level", 0))
            level = max(0, min(13, level))
        except (ValueError, TypeError):
            level = 0

        # 换算属性
        bias = template.get("aptitude_bias", {})
        attrs = self.calc_attrs_from_aptitude(aptitude, bias)

        # 合并标签
        default_tags = template.get("default_tags", [])
        custom_tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []
        merged_tags = list(dict.fromkeys(default_tags + custom_tags))

        # 组装角色数据 dict
        char_data = {
            "id": cm.get_next_id(),
            "name": name,
            "char_type": template.get("char_type", "npc"),
            "is_alive": True,
            "level": level,
            "exp": 0,
            "attrs": attrs,
            "personality": personality,
            "background": background,
            "tags": merged_tags,
            "abilities": [],
            "equipment": {},
            "inventory": [],
            "loot_table": None,
            "location": "",
            "current_affairs": [],
            "faction": "",
            "relationships": [],
        }

        # monster 类型自动标记为临时角色
        if char_data["char_type"] == "monster":
            char_data["temporary"] = True

        # 复用现有校验流程
        self._apply_temporary_default(char_data)
        cleaned_data, corrections = validator.validate_new_character(char_data)

        # 构建 Character 对象
        character = Character.from_dict(cleaned_data)

        # location 标准化
        if character.location and self._location_normalizer:
            character.location = self._location_normalizer.normalize(character.location)

        # 自动赋予技能（模板配置驱动）
        auto_skills_note = ""
        auto_abilities = self._auto_assign_skills(
            merged_tags, level, aptitude, template,
        )
        if auto_abilities:
            character.abilities = auto_abilities
            skill_names = []
            for aid in auto_abilities:
                adef = self._get_ability_def(aid)
                name = adef.get("name", aid) if adef else aid
                skill_names.append(name)
            auto_skills_note = f"自动赋予技能: {', '.join(skill_names)}"

        # 自动派生只读字段（如 level → cultivation_stage）
        derive_note = self._cascade_level_to_readonly(character, character.level)

        # 枚举字段规范化（防御性：模板可能未来扩展支持这些字段）
        template_warnings: list[str] = []
        enum_notes = self._normalize_enum_fields(character, template_warnings)

        # 默认字段推断（缺失字段自动填充）
        default_note = self._fill_default_creation_fields(
            character, substage_hint=substage_hint,
        )

        # age/birthday 联动：有 age 无 birthday 时自动生成
        age_sync_note = ""
        if character.age > 0 and not character.birthday:
            age_sync_note = self._sync_age_birthday(character, "age")

        # 记录创建日期
        cal = self._get_calendar()
        if cal:
            character.last_updated = f"{cal._current_year}/{cal._current_month}/{cal._current_day}"

        # 添加到 CharacterManager
        cm.add_character(character)

        # NPC 持久化（使用 save_all 确保 batch/个体模式一致）
        if not character.temporary and self._game_state:
            npc_dir = self._game_state.slot_dir / "npcs"
            cm.save_all(npc_dir)
        elif not character.temporary and not self._game_state:
            logger.warning(
                "角色「%s」已创建但未持久化：GameState 未注入，"
                "NPC 仅存在于内存中，下次存档加载后将丢失",
                character.name,
            )

        # 构建日志
        log_parts = [
            f"角色「{character.name}」通过模板「{template['name']}」创建成功"
            f"（id={character.id}, 资质={aptitude:.1f}, 境界=Lv{level}）",
        ]
        if story_context:
            log_parts.append(f"剧情原因: {story_context}")
        for corr in corrections:
            log_parts.append(f"- {corr}")
        if derive_note:
            log_parts.append(f"- {derive_note}")
        for en in enum_notes:
            log_parts.append(f"- {en}")
        if default_note:
            log_parts.append(f"- {default_note}")
        if template_warnings:
            log_parts.extend(template_warnings)
        if age_sync_note:
            log_parts.append(f"- {age_sync_note}")
        if auto_skills_note:
            log_parts.append(f"- {auto_skills_note}")

        # 发射事件
        if event_bus:
            try:
                from lingmo_engine.core.events import PluginEvent
                event_bus.emit(
                    PluginEvent.CHARACTER_CREATED,
                    {"id": character.id, "name": character.name},
                )
            except Exception:
                logger.warning("发射 CHARACTER_CREATED 失败", exc_info=True)

        return ModuleResult(
            success=True,
            log="\n".join(log_parts),
            data={"id": character.id, "name": character.name},
            display_type=DisplayType.SYSTEM,
        )

    def _create_character(
        self, params: dict, cm: "CharacterManager",
        validator: "AttributeValidator", event_bus,
    ) -> ModuleResult:
        char_yaml = params.get("char_yaml", "")
        story_context = params.get("story_context", "")
        substage_hint = str(params.get("substage", "")).strip()
        if not char_yaml:
            return ModuleResult(
                success=False,
                log="char_yaml 为必填参数。请提供角色 YAML 数据。",
            )

        # 解析 YAML
        char_data = self._parse_char_yaml(char_yaml)
        if char_data is None:
            return ModuleResult(
                success=False,
                log="无法解析角色 YAML。请检查格式后重试。"
                    "确保使用了正确的 YAML 格式，属性值不要加引号。",
            )

        # 自动分配 ID
        char_data["id"] = cm.get_next_id()

        # 收集技能处理警告
        warnings: list[str] = []

        # 设置 temporary 默认值
        self._apply_temporary_default(char_data)

        # 校验修正（abilities 在 known_fields 白名单中，不会被移除）
        cleaned_data, corrections = validator.validate_new_character(char_data)

        # 校验后提取 abilities 原始值，解析为 ID 后覆盖
        raw_abilities = cleaned_data.pop("abilities", None)
        if raw_abilities:
            ability_names = self._process_abilities(raw_abilities, warnings)
            cleaned_data["abilities"] = ability_names

        # 构建 Character 对象
        character = Character.from_dict(cleaned_data)

        # location 标准化
        if character.location and self._location_normalizer:
            character.location = self._location_normalizer.normalize(character.location)

        # 自动派生只读字段（如 level → cultivation_stage）
        derive_note = self._cascade_level_to_readonly(character, character.level)

        # 枚举字段规范化（spiritual_roots + 品质同步, race, cultivation_path, substage）
        enum_notes = self._normalize_enum_fields(character, warnings)

        # 默认字段推断（缺失字段自动填充）
        default_note = self._fill_default_creation_fields(
            character, substage_hint=substage_hint,
        )

        # age/birthday 联动：有 age 无 birthday 时自动生成
        age_sync_note = ""
        if character.age > 0 and not character.birthday:
            age_sync_note = self._sync_age_birthday(character, "age")

        # 记录创建日期
        cal = self._get_calendar()
        if cal:
            character.last_updated = f"{cal._current_year}/{cal._current_month}/{cal._current_day}"

        # 添加到 CharacterManager
        cm.add_character(character)

        # NPC 持久化（使用 save_all 确保 batch/个体模式一致）
        if not character.temporary and self._game_state:
            npc_dir = self._game_state.slot_dir / "npcs"
            cm.save_all(npc_dir)
        elif not character.temporary and not self._game_state:
            logger.warning(
                "角色「%s」已创建但未持久化：GameState 未注入，"
                "NPC 仅存在于内存中，下次存档加载后将丢失",
                character.name,
            )

        # 构建日志
        log_parts = [f"角色「{character.name}」创建成功（id={character.id}）"]
        if story_context:
            log_parts.append(f"剧情原因: {story_context}")
        for corr in corrections:
            log_parts.append(f"- {corr}")
        if derive_note:
            log_parts.append(f"- {derive_note}")
        for en in enum_notes:
            log_parts.append(f"- {en}")
        if default_note:
            log_parts.append(f"- {default_note}")
        if age_sync_note:
            log_parts.append(f"- {age_sync_note}")

        # 添加技能处理警告
        if warnings:
            log_parts.append("⚠ 以下问题需要关注：")
            log_parts.extend(warnings)

        # 发射事件
        if event_bus:
            try:
                from lingmo_engine.core.events import PluginEvent
                event_bus.emit(
                    PluginEvent.CHARACTER_CREATED,
                    {"id": character.id, "name": character.name},
                )
            except Exception:
                logger.warning("发射 CHARACTER_CREATED 失败", exc_info=True)

        return ModuleResult(
            success=True,
            log="\n".join(log_parts),
            data={"id": character.id, "name": character.name},
            display_type=DisplayType.SYSTEM,
        )

    def _update_character(
        self, params: dict, cm: "CharacterManager",
        validator: "AttributeValidator", event_bus,
    ) -> ModuleResult:
        char_id = params.get("character_id")
        char_yaml = params.get("char_yaml", "")
        reason = params.get("reason", "")

        # character_id 可能是字符串
        try:
            char_id = int(char_id)
        except (ValueError, TypeError):
            return ModuleResult(
                success=False,
                log=f"character_id 必须为整数，收到: {char_id}",
            )

        existing = cm.get(char_id)
        if existing is None:
            return ModuleResult(
                success=False,
                log=f"角色 id={char_id} 不存在。可用 list_characters 查看所有角色。",
            )

        char_data = self._parse_char_yaml(char_yaml)
        if char_data is None:
            return ModuleResult(
                success=False,
                log="无法解析角色 YAML。请检查格式后重试。",
            )

        # 保留原 ID
        char_data["id"] = char_id

        # 收集技能处理警告
        warnings: list[str] = []

        # 设置 temporary 默认值
        self._apply_temporary_default(char_data)

        # 校验修正（abilities 在 known_fields 白名单中，不会被移除）
        cleaned_data, corrections = validator.validate_new_character(char_data)

        # 校验后提取 abilities 原始值，解析为 ID 后覆盖
        raw_abilities = cleaned_data.pop("abilities", None)
        if raw_abilities:
            ability_names = self._process_abilities(raw_abilities, warnings)
            cleaned_data["abilities"] = ability_names

        # 保留先天资质（read-only attributes）：全量更新时不可覆盖
        innate_corrections: list[str] = []
        if self._visibility_resolver:
            readonly_attrs = self._visibility_resolver.get_read_only_fields(section="attributes")
            if readonly_attrs and "attrs" in cleaned_data:
                for attr_name in readonly_attrs:
                    if attr_name in existing.attrs:
                        old_val = cleaned_data.get("attrs", {}).get(attr_name)
                        cleaned_data.setdefault("attrs", {})[attr_name] = existing.attrs[attr_name]
                        if old_val is not None and old_val != existing.attrs[attr_name]:
                            innate_corrections.append(
                                f"attrs.{attr_name}: 先天资质不可修改，保留原值 {existing.attrs[attr_name]}"
                            )

        # 重建 Character 覆盖
        updated = Character.from_dict(cleaned_data)

        # 自动派生只读字段（如 level → cultivation_stage）
        derive_note = self._cascade_level_to_readonly(updated, updated.level)

        # 枚举字段规范化（spiritual_roots + 品质同步, race, cultivation_path, substage）
        enum_notes = self._normalize_enum_fields(updated, warnings)

        cm.add_character(updated)  # add_character 会对已存在 ID 执行覆盖

        # 持久 NPC 更新（使用 save_all 确保 batch/个体模式一致）
        if not updated.temporary and self._game_state:
            npc_dir = self._game_state.slot_dir / "npcs"
            cm.save_all(npc_dir)
        elif not updated.temporary and not self._game_state:
            logger.warning(
                "角色「%s」(id=%d) 全量更新未持久化：GameState 未注入",
                updated.name, char_id,
            )

        log_parts = [f"角色「{updated.name}」(id={char_id}) 已全量更新"]
        if reason:
            log_parts.append(f"原因: {reason}")
        for corr in corrections:
            log_parts.append(f"- {corr}")
        for ic in innate_corrections:
            log_parts.append(f"- {ic}")
        if derive_note:
            log_parts.append(f"- {derive_note}")
        for en in enum_notes:
            log_parts.append(f"- {en}")

        # 添加技能处理警告
        if warnings:
            log_parts.append("⚠ 以下问题需要关注：")
            log_parts.extend(warnings)

        if event_bus:
            try:
                from lingmo_engine.core.events import PluginEvent
                event_bus.emit(
                    PluginEvent.CHARACTER_UPDATED,
                    {"id": char_id, "key": "__full_update__", "value": 0},
                )
            except Exception:
                logger.warning("发射 CHARACTER_UPDATED 失败", exc_info=True)

        return ModuleResult(
            success=True,
            log="\n".join(log_parts),
            data={"id": char_id, "name": updated.name},
            display_type=DisplayType.SYSTEM,
        )

    def _update_field(
        self, params: dict, cm: "CharacterManager",
        validator: "AttributeValidator", event_bus,
    ) -> ModuleResult:
        char_id = params.get("character_id")
        field = params.get("field", "")
        value = params.get("value")
        reason = params.get("reason", "")

        # character_id 可能是字符串
        try:
            char_id = int(char_id)
        except (ValueError, TypeError):
            return ModuleResult(
                success=False,
                log=f"character_id 必须为整数，收到: {char_id}",
            )

        character = cm.get(char_id)
        if character is None:
            return ModuleResult(
                success=False,
                log=f"角色 id={char_id} 不存在。可用 list_characters 查看所有角色。",
            )

        if not field:
            return ModuleResult(success=False, log="field 为必填参数")

        # name 空值拦截
        if field == "name":
            if not value or (isinstance(value, str) and not value.strip()):
                return ModuleResult(
                    success=False,
                    log="name 不允许为空值",
                )
            if isinstance(value, str):
                value = value.strip()

        # hidden 字段拦截（非 attrs 路径的字段，如 loot_table、inventory）
        if not field.startswith("attrs."):
            if not validator.is_field_llm_visible(field, section="fields"):
                return ModuleResult(
                    success=False,
                    log=f"{field}: 该字段为 hidden，LLM 不可修改",
                )

        # 只读字段拦截（LLM 可见但不可修改，由系统根据 derived_from 自动派生）
        # root_quality 等不在 schema 中的字段由 normalizer.preprocess_field_update 拦截
        if not field.startswith("attrs."):
            if self._visibility_resolver and self._visibility_resolver.is_read_only(field, section="fields"):
                derived = self._visibility_resolver.get_derived_from(field, section="fields")
                hint = f"请修改 {derived}，系统将自动同步。" if derived else ""
                return ModuleResult(
                    success=False,
                    log=f"{field} 为系统自动维护字段，不可直接修改。{hint}",
                )

        # 解析 value（LLM 传来的可能是字符串，需转换）
        parsed_value = self._parse_field_value(field, value)

        # 世界观字段预处理：root_quality 拦截、spiritual_roots 规范化、race/path 失败拦截
        preprocess_notes = ""
        if self._normalizer:
            parsed_value, preprocess_notes, intercept = self._normalizer.preprocess_field_update(
                field, parsed_value,
            )
            if intercept:
                return intercept

        # 校验值
        corrected_value, correction_note = validator.validate_field_update(
            char_id, field, parsed_value,
        )

        # hidden 属性拦截：validate_field_update 返回 _FieldRejected sentinel
        from lingmo_engine.plugins.character.attribute_validator import _FieldRejected
        if isinstance(corrected_value, _FieldRejected):
            return ModuleResult(success=False, log=corrected_value.reason)

        # abilities 技能名→ID 合法性修正
        ability_note = ""
        if field == "abilities":
            corrected_value, ability_note = self._resolve_ability_value(
                corrected_value,
            )

        # location 字段标准化
        if field == "location" and self._location_normalizer:
            corrected_value = self._location_normalizer.normalize(corrected_value)

        # 应用字段修改
        apply_note = self._apply_field_update(character, field, corrected_value)

        # 世界观字段后处理：level cascade、quality sync、path apply、substage 规范化
        postprocess_notes: list[str] = []
        if self._normalizer:
            postprocess_notes = self._normalizer.postprocess_field_update(
                field, corrected_value, character,
            )

        # age/birthday 联动同步
        age_note = ""
        if field in ("age", "birthday"):
            age_note = self._sync_age_birthday(character, field)

        # 更新 last_updated 时间戳
        cal = self._get_calendar()
        if cal and not character.temporary:
            character.last_updated = f"{cal._current_year}/{cal._current_month}/{cal._current_day}"

        # 持久 NPC 字段更新（使用 save_all 确保 batch/个体模式一致）
        if not character.temporary and self._game_state:
            npc_dir = self._game_state.slot_dir / "npcs"
            cm.save_all(npc_dir)
        elif not character.temporary and not self._game_state:
            logger.warning(
                "角色「%s」(id=%d) 字段 %s 更新未持久化：GameState 未注入",
                character.name, char_id, field,
            )

        log_parts = [f"角色「{character.name}」(id={char_id}) {field} 已更新"]
        if reason:
            log_parts.append(f"原因: {reason}")
        if apply_note:
            log_parts.append(f"- {apply_note}")
        if preprocess_notes:
            log_parts.append(f"- 字段修正: {preprocess_notes}")
        if correction_note:
            log_parts.append(f"- {correction_note}")
        if ability_note:
            log_parts.append(f"- 技能名修正: {ability_note}")
        for note in postprocess_notes:
            log_parts.append(f"- {note}")
        if age_note:
            log_parts.append(f"- {age_note}")

        if event_bus:
            try:
                from lingmo_engine.core.events import PluginEvent
                event_bus.emit(
                    PluginEvent.CHARACTER_UPDATED,
                    {"id": char_id, "key": field, "value": corrected_value},
                )
            except Exception:
                logger.warning("发射 CHARACTER_UPDATED 失败", exc_info=True)

        return ModuleResult(
            success=True,
            log="\n".join(log_parts),
            data={"id": char_id, "field": field},
            display_type=DisplayType.SYSTEM,
        )

    def _list_characters(
        self, params: dict, cm: "CharacterManager",
    ) -> ModuleResult:
        filter_type = params.get("filter_type", "all")
        filter_value = params.get("filter_value", "")

        if filter_type == "location" and filter_value:
            chars = cm.list_by_location(filter_value)
        elif filter_type == "type" and filter_value:
            try:
                ct = CharacterType(filter_value)
                chars = cm.list_by_type(ct)
            except ValueError:
                return ModuleResult(
                    success=False,
                    log=f"无效的角色类型: {filter_value}。可选: npc, monster, player, pet",
                )
        else:
            chars = cm.all()

        if not chars:
            return ModuleResult(
                success=True,
                log="当前没有符合条件的角色。",
                data={"characters": [], "count": 0},
                display_type=DisplayType.SYSTEM,
            )

        lines = [f"共 {len(chars)} 个角色:"]
        for c in chars:
            tags_str = f" [{', '.join(c.tags[:3])}]" if c.tags else ""
            lifecycle = "临时" if getattr(c, "temporary", False) else "持久"
            dtags = self._normalizer.format_character_display_tags(c) if self._normalizer else {}
            stage_tag = f" {dtags['stage_tag']}" if dtags.get("stage_tag") else ""
            race_tag = f" {dtags['race_tag']}" if dtags.get("race_tag") else ""
            path_tag = f" {dtags['path_tag']}" if dtags.get("path_tag") else ""
            age_tag = f" {c.age}岁" if c.age else ""
            lines.append(
                f"- id={c.id} [{c.char_type.value}·{lifecycle}] {c.name} "
                f"Lv{c.level}{stage_tag}{race_tag}{age_tag}{path_tag} ({c.location or '未知位置'}){tags_str}"
            )

        # data 部分仍需 ID→名称映射
        race_id_to_name = self._get_race_id_to_name()
        return ModuleResult(
            success=True,
            log="\n".join(lines),
            data={
                "characters": [
                    {"id": c.id, "name": c.name, "char_type": c.char_type.value,
                     "level": c.level, "age": c.age,
                     "race": race_id_to_name.get(getattr(c, 'race', ''), getattr(c, 'race', '')),
                     "cultivation_stage": self.stage_id_to_name(getattr(c, 'cultivation_stage', '')),
                     "location": c.location}
                    for c in chars
                ],
                "count": len(chars),
            },
            display_type=DisplayType.SYSTEM,
        )

    def _get_character_detail(
        self, params: dict, cm: "CharacterManager",
    ) -> ModuleResult:
        """查询单个角色的完整详情（Schema 驱动：可见性过滤 + 面板翻译）。"""
        # ── 参数解析（Bug #3: 安全转换） ──
        raw_id = params.get("character_id", -1)
        try:
            char_id = int(raw_id)
        except (ValueError, TypeError):
            return ModuleResult(
                success=False,
                log=f"character_id 必须为整数，收到: {raw_id}",
            )
        char = cm.get(char_id)
        if not char:
            return ModuleResult(
                success=False,
                log=f"角色 id={char_id} 未找到",
            )

        # ── 1. 原始数据 ──
        raw = char.to_dict()

        # ── 2. 可见性过滤 ──
        vr = self._visibility_resolver
        visible_attrs = vr.filter_attrs(raw.get("attrs", {})) if vr else dict(raw.get("attrs", {}))
        # 顶层字段：从 raw 中提取所有非 attrs/extra 字段
        all_fields = {k: v for k, v in raw.items() if k not in ("attrs", "extra")}
        # extra 中代理到顶层的字段（从 schema 缓存驱动，非硬编码）
        extra = raw.get("extra", {})
        if isinstance(extra, dict):
            for key in self._extra_promote_keys:
                if key in extra:
                    all_fields[key] = extra[key]
        visible_fields = vr.filter_fields(all_fields) if vr else dict(all_fields)

        # Bug #2: 过滤掉非 schema 定义的系统字段（id/exp/summary/temporary 等）
        if self._schema_fields_set:
            visible_fields = {
                k: v for k, v in visible_fields.items()
                if k in self._schema_fields_set
            }

        # ── 3. 面板值解析（World 层 hook） ──
        display_values = {}
        if self._world:
            try:
                panel_resolver = self._world.get_panel_schema_resolver()
                display_values = panel_resolver.resolve_display_values(raw)
            except Exception:
                logger.warning("面板值解析失败", exc_info=True)

        # Bug #1: 用 val is not None 替代 if val（避免跳过 karma=0 等合法值）
        for key, val in display_values.items():
            if key in visible_fields and val is not None and val != "":
                visible_fields[key] = val

        # ── 4. Schema label 映射（已缓存到 self._attr_labels / self._field_labels） ──

        # ── 5. 构建 log 文本 ──
        lines = [f"角色详情 id={char.id}"]
        field_labels = self._field_labels
        attr_labels = self._attr_labels

        # 头部信息：从 panel schema sections.header 驱动（Bug #5/#6/#7）
        header_keys = self._extract_section_field_keys("header")
        # fallback：无 panel schema 时用 schema fields 中的核心字段
        if not header_keys:
            header_keys = [k for k in ("name", "dao_name", "level", "is_alive",
                                       "age", "location", "faction")
                           if k in visible_fields]

        for key in header_keys:
            if key not in visible_fields:
                continue
            val = visible_fields[key]
            label = field_labels.get(key, key)
            if val is None or val == "" or val == []:
                continue
            if key == "level":
                lines.append(f"  等级: Lv{val}")
            elif key == "is_alive":
                lines.append(f"  {label}: {'是' if val else '否'}")
            elif isinstance(val, list):
                lines.append(f"  {label}: {', '.join(str(v) for v in val)}")
            else:
                lines.append(f"  {label}: {val}")

        # 属性段
        if visible_attrs:
            attr_parts = [
                f"{attr_labels.get(k, k)}={v}" for k, v in visible_attrs.items()
            ]
            lines.append(f"  属性: {', '.join(attr_parts)}")

        # 关系段（补充目标角色名称）
        if "relationships" in visible_fields and visible_fields["relationships"]:
            lines.append("  关系:")
            for rel in visible_fields["relationships"]:
                if not isinstance(rel, dict):
                    continue
                target_id = rel.get("target_id", "?")
                # 安全转换 target_id
                try:
                    target_id_int = int(target_id)
                except (ValueError, TypeError):
                    target_id_int = -1
                target_char = cm.get(target_id_int) if target_id_int >= 0 else None
                target_name = target_char.name if target_char else f"id={target_id}"
                label = rel.get("label", "")
                desc = rel.get("desc", "")
                lines.append(f"    {target_name} [{label}] {desc}")

        # 列表类型字段（跳过已在 header 中展示的字段，避免重复）
        displayed_keys = set(header_keys) & set(visible_fields.keys())
        for key in ("tags", "abilities"):
            if key in visible_fields and visible_fields[key] and key not in displayed_keys:
                lbl = field_labels.get(key, key)
                lines.append(f"  {lbl}: {', '.join(str(v) for v in visible_fields[key])}")

        # 装备段
        if "equipment" in visible_fields and visible_fields["equipment"]:
            lines.append("  装备:")
            for slot, item in visible_fields["equipment"].items():
                lines.append(f"    {slot}: {item}")

        # 文本类字段：从 panel schema 中 renderer=text 的 section 驱动
        text_keys = self._extract_text_section_keys()
        for key in text_keys:
            if key in visible_fields and visible_fields[key]:
                lbl = field_labels.get(key, key)
                lines.append(f"  {lbl}: {visible_fields[key]}")

        return ModuleResult(
            success=True,
            log="\n".join(lines),
            data={"character": visible_fields, "attrs": visible_attrs},
            display_type=DisplayType.SYSTEM,
        )

    def _extract_section_field_keys(self, section_name: str) -> list[str]:
        """从 panel schema sections 配置中提取字段 key 列表。"""
        section = self._panel_sections.get(section_name, {})
        fields = section.get("fields", [])
        if not fields:
            return []
        return [f.get("key", "") for f in fields if f.get("key")]

    def _extract_text_section_keys(self) -> list[str]:
        """从 panel schema 中提取所有 renderer=text 的 section 的字段 key。"""
        keys = []
        for section_name, section in self._panel_sections.items():
            if section.get("renderer") != "text":
                continue
            # 直接 key（如 personality: key=personality）
            key = section.get("key", "")
            if key:
                keys.append(key)
            # field_path 格式（如 appearance: field_path=extra.appearance）
            field_path = section.get("field_path", "")
            if field_path:
                # "extra.appearance" → "appearance"
                parts = field_path.rsplit(".", 1)
                keys.append(parts[-1] if len(parts) > 1 else field_path)
            # fields 列表中的 key
            for f in section.get("fields", []):
                fk = f.get("key", "")
                if fk:
                    keys.append(fk)
                fp = f.get("field_path", "")
                if fp:
                    parts = fp.rsplit(".", 1)
                    keys.append(parts[-1] if len(parts) > 1 else fp)
        # fallback：无 panel schema 时用通用文本字段
        if not keys:
            keys = [k for k in ("personality", "appearance", "clothing",
                                "background", "hobbies")
                    if k in self._schema_fields_set or not self._schema_fields_set]
        return keys

    def _update_relationship(
        self, params: dict, cm: "CharacterManager",
    ) -> ModuleResult:
        """执行 update_relationship 工具调用。"""
        character_id = int(params.get("character_id", -1))
        target_id = int(params.get("target_id", -1))
        action = str(params.get("action", ""))
        label = str(params.get("label", ""))
        desc = str(params.get("desc", ""))
        reason = str(params.get("reason", ""))

        valid_labels = self._get_valid_labels()

        result = cm.update_relationship(
            character_id, target_id, action,
            label=label, desc=desc,
            valid_labels=valid_labels if valid_labels else None,
        )
        if result["success"]:
            return ModuleResult(
                success=True,
                log=f"关系变更: {result['message']}。原因: {reason}",
            )
        return ModuleResult(success=False, log=result["message"])

    def _query_relationship(
        self, params: dict, cm: "CharacterManager",
    ) -> ModuleResult:
        """执行 query_relationship 工具调用。"""
        character_id = int(params.get("character_id", -1))
        target_id = params.get("target_id")
        if target_id is not None:
            target_id = int(target_id)

        text = cm.get_relationships_text(character_id, target_id)
        return ModuleResult(success=True, log=text, display_type=DisplayType.SYSTEM)

    # ── 内部：YAML 解析 ──

    def _parse_char_yaml(self, raw: str) -> dict | None:
        """解析 LLM 输出的角色 YAML，带容错处理。"""
        # 尝试直接解析
        try:
            data = yaml.safe_load(raw)
            if isinstance(data, dict):
                return data
        except yaml.YAMLError:
            pass

        # 尝试提取 ```yaml 代码块
        match = re.search(r'```(?:yaml)?\s*\n(.*?)\n```', raw, re.DOTALL)
        if match:
            try:
                data = yaml.safe_load(match.group(1))
                if isinstance(data, dict):
                    return data
            except yaml.YAMLError:
                pass

        logger.warning("CharacterGenerator: 无法解析 YAML: %s", raw[:200])
        return None

    # ── 灵根规范化（委托 CultivationFieldNormalizer）──

    def _parse_field_value(self, field: str, value) -> object:
        """将 LLM 传入的 value 转换为正确的 Python 类型。"""
        # 修炼字段解析委托给 normalizer
        n = self._normalizer
        if n:
            parsed, handled = n.parse_cultivation_value(field, value)
            if handled:
                return parsed

        # 数字字段
        if field in ("level", "exp", "age") or field.startswith("attrs."):
            try:
                return int(value)
            except (ValueError, TypeError):
                return value

        # 布尔字段
        if field == "is_alive":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes")
            return bool(value)

        # 列表字段——检查是否有追加/移除前缀
        if field in ("abilities", "tags", "current_affairs", "spiritual_roots"):
            if isinstance(value, str):
                if value.startswith("+"):
                    items = [v.strip().lstrip("+") for v in value[1:].split(",") if v.strip()]
                    return ("add", items[0] if len(items) == 1 else items)
                if value.startswith("-"):
                    items = [v.strip().lstrip("-") for v in value[1:].split(",") if v.strip()]
                    return ("remove", items[0] if len(items) == 1 else items)
                # 尝试解析 JSON 数组
                try:
                    return json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    # 逗号分隔字符串拆分为列表
                    return [v.strip() for v in value.split(",") if v.strip()]
            if isinstance(value, list):
                return value
            return [str(value)]

        # equipment 整体字典或 equipment.{slot} 单槽位
        if field == "equipment" or field.startswith("equipment."):
            # 单槽位更新（equipment.ring_1 → 返回字符串值）
            if field.startswith("equipment.") and not isinstance(value, dict):
                return value if value and value.strip() and value != "null" else None
            if isinstance(value, dict):
                return value
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    pass
                # 兜底：解析 "部位:装备ID" 或 "部位:装备ID, 部位2:装备ID2" 格式
                if ":" in value:
                    result = {}
                    for pair in value.split(","):
                        pair = pair.strip()
                        if ":" in pair:
                            k, v = pair.split(":", 1)
                            result[k.strip()] = v.strip()
                    if result:
                        return result
            return {}

        # birthday 是字符串（"YYYY/MM/DD" 格式）
        if field == "birthday":
            if isinstance(value, dict):
                # 旧格式兼容：{"year": 3, "month": 5, "day": 10}
                try:
                    return f"{value['year']}/{value['month']}/{value['day']}"
                except (KeyError, TypeError):
                    return None
            if not isinstance(value, str):
                return None
            from lingmo_engine.core.calendar import DefaultCalendar
            parsed = DefaultCalendar.parse_birthday(value.strip())
            return value.strip() if parsed else None

        return value

    def _resolve_ability_value(self, value) -> tuple[object, str]:
        """将 abilities 值中的技能名解析为技能ID。

        处理三种格式：
        - ("add"/"remove", name) → 解析 name 为 id
        - [name1, name2, ...] → 逐项解析
        - 其他 → 原样返回
        """
        notes: list[str] = []

        if isinstance(value, tuple) and len(value) == 2:
            action, item = value
            if isinstance(item, list):
                resolved_list = []
                for entry in item:
                    resolved = self._resolve_ability_entry(entry)
                    if resolved != entry:
                        notes.append(f"'{entry}' → '{resolved}'")
                    resolved_list.append(resolved)
                return (action, resolved_list), "; ".join(notes)
            if isinstance(item, str):
                resolved = self._resolve_ability_entry(item)
                if resolved != item:
                    notes.append(f"'{item}' → '{resolved}'")
                return (action, resolved), "; ".join(notes)
            return value, ""

        if isinstance(value, list):
            resolved_list = []
            for entry in value:
                if isinstance(entry, str):
                    resolved = self._resolve_ability_entry(entry)
                    if resolved != entry:
                        notes.append(f"'{entry}' → '{resolved}'")
                    resolved_list.append(resolved)
                else:
                    resolved_list.append(entry)
            return resolved_list, "; ".join(notes)

        return value, ""

    def _ensure_ability_name_index(self) -> None:
        """惰性构建并缓存 world.abilities 的 name→id 索引。"""
        if self._ability_name_index or not self._world:
            return
        for aid, adef in self._world.abilities.items():
            name = adef.get("name")
            if name:
                self._ability_name_index[name] = aid

    def _resolve_ability_entry(self, entry: str) -> str:
        """解析单个技能条目：已知ID直接返回，否则尝试 name→id 解析。

        查找顺序：custom_abilities → game_state → world(ID) → world(精确name) → 模糊匹配
        """
        # 已是合法 ID
        if entry in self._custom_abilities:
            return entry
        if self._game_state and self._game_state.get_custom_ability(entry):
            return entry
        if self._world and entry in self._world.abilities:
            return entry

        # name → id 解析
        self._ensure_ability_name_index()

        # 精确 name 匹配
        if self._world and entry in self._ability_name_index:
            aid = self._ability_name_index[entry]
            logger.info("abilities update: 名称 '%s' → ID '%s'", entry, aid)
            return aid

        # 模糊匹配
        if self._world or self._game_state:
            fuzzy_result = self._fuzzy_match_ability(entry)
            if fuzzy_result:
                fuzzy_id, fuzzy_def = fuzzy_result
                matched_name = fuzzy_def.get("name", fuzzy_id)
                logger.info(
                    "abilities update: 模糊匹配 '%s' → '%s' (%s)",
                    entry, matched_name, fuzzy_id,
                )
                return fuzzy_id

        return entry

    def _apply_field_update(
        self, character: Character, field: str, value,
    ) -> str | None:
        """将修正后的值应用到角色字段。返回操作描述。"""
        parts = field.split(".")

        # equipment.{slot_name}
        if parts[0] == "equipment" and len(parts) == 2:
            slot_name = parts[1]
            if slot_name not in character.equipment:
                return f"equipment.{slot_name}: 非法槽位，跳过"
            old_val = character.equipment.get(slot_name)
            character.equipment[slot_name] = value
            return f"equipment.{slot_name}: {old_val or '(空)'} → {value}"

        # attrs.{attr_name}
        if parts[0] == "attrs" and len(parts) == 2:
            attr_name = parts[1]
            old_val = character.attrs.get(attr_name, 0)
            character.attrs[attr_name] = value
            return f"attrs.{attr_name}: {old_val} → {value}"

        # 列表字段（带 add/remove 语义）
        if field in ("abilities", "tags", "current_affairs", "spiritual_roots"):
            target_list: list = getattr(character, field)
            if isinstance(value, tuple) and len(value) == 2:
                action, item = value
                if action == "add":
                    if isinstance(item, list):
                        added = [i for i in item if i not in target_list]
                        target_list.extend(added)
                        return (f"{field}: 批量追加 {added}"
                                if added
                                else f"{field}: 所有项已存在，跳过")
                    if item not in target_list:
                        target_list.append(item)
                        return f"{field}: 追加 '{item}'"
                    return f"{field}: '{item}' 已存在，跳过"
                elif action == "remove":
                    if isinstance(item, list):
                        removed = [i for i in item if i in target_list]
                        for i in removed:
                            target_list.remove(i)
                        return (f"{field}: 批量移除 {removed}"
                                if removed
                                else f"{field}: 所有项不存在，跳过")
                    if item in target_list:
                        target_list.remove(item)
                        return f"{field}: 移除 '{item}'"
                    return f"{field}: '{item}' 不存在，跳过"
            # 直接覆盖
            setattr(character, field, list(value))
            return f"{field}: 已覆盖为 {value}"

        # 标量/字符串字段
        if hasattr(character, field):
            old = getattr(character, field)
            setattr(character, field, value)
            return f"{field}: {old} → {value}"

        # 字典字段
        if field == "equipment" and isinstance(value, dict):
            character.equipment.update(value)
            return f"equipment: 已合并 {list(value.keys())}"

        return f"{field}: 已更新"

    def _cascade_stage_to_level(self, character: Character, stage_name: str) -> str:
        """cultivation_stage 变更时联动更新 level。"""
        n = self._normalizer
        return n.cascade_stage_to_level(character, stage_name) if n else ""

    def _cascade_level_to_readonly(self, character: Character, new_level: int) -> str:
        """level 变更时自动派生所有 derived_from=level 的只读字段。"""
        n = self._normalizer
        if n:
            return n.cascade_level_to_readonly(character, new_level)
        return ""

    # ── 默认字段推断 ──

    def _fill_default_creation_fields(
        self, character: Character, *, substage_hint: str = "",
    ) -> str | None:
        """角色创建时自动推断缺失字段。

        修仙相关字段委托给 normalizer，通用逻辑（资源池上限同步）在此处理。
        仅在字段缺失（0 或空）时填充，不覆盖已有值。

        Args:
            substage_hint: 可选的小境界提示，传递给 normalizer 限定灵力区间。

        Returns:
            日志说明字符串，或 None（无需推断）。
        """
        notes: list[str] = []

        # 修仙相关字段：委托给 normalizer
        n = self._normalizer
        if n and hasattr(n, "fill_default_creation_fields"):
            cult_note = n.fill_default_creation_fields(
                character, substage_hint=substage_hint,
            )
            if cult_note:
                notes.append(cult_note)

        # 通用逻辑：资源池上限同步
        pool_pairs = [
            ("vitality", "max_vitality"),
            ("stamina", "max_stamina"),
            ("divine_sense", "max_divine_sense"),
        ]
        synced_pools: list[str] = []
        for key, max_key in pool_pairs:
            if character.attrs.get(max_key, 0) < character.attrs.get(key, 0):
                character.attrs[max_key] = character.attrs[key]
                synced_pools.append(f"{max_key}={character.attrs[key]}")
        if synced_pools:
            notes.append(f"资源池上限同步: {', '.join(synced_pools)}")

        return "；".join(notes) if notes else None

    def _sync_age_birthday(self, character: Character, changed_field: str) -> str:
        """age/birthday 变更时联动同步。

        - 设置 birthday 时：根据日历自动计算 age
        - 设置 age 时：如果 birthday 为空，根据日历随机生成 birthday
        """
        from lingmo_engine.core.calendar import DefaultCalendar

        calendar = self._get_calendar()
        if calendar is None:
            return ""

        notes: list[str] = []

        if changed_field == "birthday" and character.birthday:
            new_age = calendar.calc_age(character.birthday)
            if new_age is not None and new_age != character.age:
                old_age = character.age
                character.age = new_age
                notes.append(f"联动 age: {old_age} → {new_age}")

        elif changed_field == "age" and character.age > 0 and not character.birthday:
            birthday = calendar.random_birthday_for_age(character.age)
            character.birthday = birthday
            notes.append(f"联动 birthday: 随机生成 {birthday}")

        return "；".join(notes)

    def _get_calendar(self):
        """获取当前日历实例（通过 EventBus 或 GameState）。"""
        # 优先通过 event_bus 获取
        bus = getattr(self, '_event_bus', None)
        if bus:
            try:
                from lingmo_engine.core.events import PluginEvent
                cal_data = bus.request(PluginEvent.CALENDAR_GET_INFO)
                if cal_data:
                    from lingmo_engine.core.calendar import DefaultCalendar
                    return DefaultCalendar.from_dict(cal_data)
            except Exception:
                pass
        return None

    # ── 种族规范化（委托 CultivationFieldNormalizer）──

    def _get_race_id_to_name(self) -> dict[str, str]:
        """构建种族 ID→中文名映射。"""
        n = self._normalizer
        return n.get_race_id_to_name() if n else {}

    # ── 枚举字段统一规范化（委托 CultivationFieldNormalizer）──

    def _normalize_enum_fields(self, character: Character, warnings: list[str]) -> list[str]:
        """统一规范化角色的枚举类字段。"""
        n = self._normalizer
        return n.normalize_enum_fields(character, warnings) if n else []

    # ── abilities 处理 ──

    def set_world(self, world) -> None:
        """设置 GameWorld 引用，用于获取技能模板/预算表等配置。"""
        self._world = world
        # 加载 panel sections 缓存
        if world:
            try:
                panel_resolver = world.get_panel_schema_resolver()
                self._panel_sections = panel_resolver.get_sections_schema()
            except Exception:
                self._panel_sections = {}
        else:
            self._panel_sections = {}

    def set_game_state(self, game_state) -> None:
        """设置 GameState 引用，用于注册自定义技能。"""
        self._game_state = game_state

    @staticmethod
    def _normalize_name(name: str) -> str:
        """归一化技能名称：移除分隔符和空白，统一小写。"""
        return normalize_name(name)

    def _get_ability_def(self, aid: str) -> dict | None:
        """根据 ID 获取技能完整定义，依次查找 world.abilities 和 game_state。"""
        if self._world and aid in self._world.abilities:
            return self._world.abilities[aid]
        if self._game_state:
            d = self._game_state.get_custom_ability(aid)
            if d:
                return d
        return None

    def _fuzzy_match_ability(self, query: str) -> tuple[str, dict] | None:
        """在 world.abilities + game_state 自定义技能中模糊匹配，返回 (id, definition) 或 None。

        委托 core.types.fuzzy_match_by_name 执行三级匹配（精确→包含→重叠率），
        本方法只负责构建索引和包装返回值。
        """
        from lingmo_engine.core.types import fuzzy_match_by_name

        # 惰性构建归一化索引（含世界技能 + 持久化自定义技能）
        if not hasattr(self, "_ability_norm_index"):
            self._ability_norm_index: list[tuple[str, str, str]] = []
            seen_ids: set[str] = set()
            # 世界预设技能
            if self._world:
                for aid, adef in self._world.abilities.items():
                    name = adef.get("name", "")
                    norm = self._normalize_name(name)
                    if norm:
                        self._ability_norm_index.append((aid, name, norm))
                        seen_ids.add(aid)
            # GameState 持久化自定义技能
            if self._game_state:
                for aid, adef in self._game_state.get_all_custom_abilities().items():
                    if aid in seen_ids:
                        continue
                    name = adef.get("name", "")
                    norm = self._normalize_name(name)
                    if norm:
                        self._ability_norm_index.append((aid, name, norm))

        if not self._ability_norm_index:
            return None

        matched_id = fuzzy_match_by_name(query, self._ability_norm_index)
        if matched_id:
            # 获取匹配到的名称用于日志
            matched_name = ""
            for aid, name, _norm in self._ability_norm_index:
                if aid == matched_id:
                    matched_name = name
                    break
            logger.info("abilities: 模糊匹配 '%s' → '%s'", query, matched_name)
            defn = self._get_ability_def(matched_id)
            if not defn:
                logger.debug("_fuzzy_match_ability: 定义未找到 %s，使用 name-only 回退", matched_id)
                defn = {"name": matched_name}
            return matched_id, defn

        return None

    def _process_abilities(self, abilities: list | None, warnings: list[str] | None = None) -> list[str]:
        """处理 abilities 列表，返回技能 ID 列表。

        字符串 → 按 ID/name 精确查找 → 模糊匹配
        对象 → 调用 affix_generate_ability 生成新技能
        """
        if not abilities:
            return []

        # name→id 索引
        self._ensure_ability_name_index()

        skill_names: list[str] = []
        for entry in abilities:
            if isinstance(entry, str):
                # 1. 精确 ID 匹配：custom_abilities
                if entry in self._custom_abilities:
                    skill_names.append(entry)
                    continue
                # 2. 精确 ID 匹配：game_state.custom_abilities
                if self._game_state and self._game_state.get_custom_ability(entry):
                    skill_names.append(entry)
                    continue
                # 3. 精确 ID 匹配：world.abilities
                if self._world and entry in self._world.abilities:
                    skill_names.append(entry)
                    continue
                # 4. 精确 name 反查 world.abilities
                if self._world and entry in self._ability_name_index:
                    aid = self._ability_name_index[entry]
                    skill_names.append(aid)
                    continue
                # 5. 模糊匹配
                fuzzy_result = self._fuzzy_match_ability(entry)
                if fuzzy_result:
                    skill_names.append(fuzzy_result[0])
                    continue
                msg = (
                    f"WARNING: 技能 '{entry}' 未找到，已跳过。"
                    f"建议：1. 检查技能名是否拼写正确 "
                    f"2. 使用 dict 格式定义新技能，提供 name, description, level, rarity, effect_slots 字段"
                )
                logger.warning("abilities: 技能 '%s' 未找到，已跳过", entry)
                if warnings is not None:
                    warnings.append(msg)
            elif isinstance(entry, dict):
                # 前置模糊匹配：检查是否已有相似技能
                ability_name = entry.get("name", "")
                if ability_name:
                    fuzzy_result = self._fuzzy_match_ability(ability_name)
                    if fuzzy_result:
                        existing_id, existing_def = fuzzy_result
                        existing_name = existing_def.get("name", existing_id)
                        existing_level = existing_def.get("level", "?")
                        existing_rarity = existing_def.get("rarity")
                        # 构建稀有度描述
                        rarity_desc = str(existing_rarity) if existing_rarity is not None else "?"
                        if isinstance(existing_rarity, int) and self._world:
                            ri = self._world.get_ability_rarity_info(existing_rarity)
                            rarity_tier = ri.get("name", "")
                            if rarity_tier:
                                rarity_desc = f"{existing_rarity}/{rarity_tier}"
                        msg = (
                            f"WARNING: 已有相似技能「{existing_name}」"
                            f"(ID: {existing_id}, Level: {existing_level}, 稀有度: {rarity_desc})。"
                            f"建议：可直接引用该技能名或ID，或修改技能名以避免重复。"
                        )
                        logger.warning("abilities: 创建技能 '%s' 时发现已有相似技能 '%s' (%s)",
                                        ability_name, existing_name, existing_id)
                        if warnings is not None:
                            warnings.append(msg)
                        skill_names.append(existing_id)
                        continue

                ability_def = self._generate_ability(entry, warnings)
                if ability_def:
                    aid = ability_def["id"]
                    self._custom_abilities[aid] = ability_def
                    if self._game_state:
                        self._game_state.add_custom_ability(aid, ability_def)
                    # 将新生成的技能追加到归一化索引，避免同批次后续 dict 条目重复创建
                    if hasattr(self, "_ability_norm_index"):
                        new_name = ability_def.get("name", "")
                        new_norm = self._normalize_name(new_name)
                        if new_norm:
                            self._ability_norm_index.append((aid, new_name, new_norm))
                    skill_names.append(aid)
            else:
                msg = (
                    f"WARNING: abilities 条目类型不支持({type(entry).__name__})。"
                    f"建议：使用字符串引用已有技能名，或用 dict 定义新技能(name/description/level/rarity/effect_slots)"
                )
                logger.warning("abilities: 不支持的条目类型 %s", type(entry).__name__)
                if warnings is not None:
                    warnings.append(msg)

        return skill_names

    def _generate_ability(self, ability_input: dict, warnings: list[str] | None = None) -> dict | None:
        """通过 EventBus 调用 affix_generate_ability 生成技能，降级为懒加载。"""
        if self._world is None:
            msg = "WARNING: 无法生成技能，世界配置缺失。建议：此为引擎内部问题，请使用已有技能名替代"
            logger.warning("_generate_ability: world 未设置，无法生成技能")
            if warnings is not None:
                warnings.append(msg)
            return None

        affix_defs = self._world.get_effect_affixes()
        exclusions = self._world.get_effect_exclusions()
        tag_cost_map = self._world.get_tag_cost_map()

        rarity_int = ability_input.get("rarity", 25)
        rarity_info = self._world.get_ability_rarity_info(rarity_int)

        # 优先通过 EventBus 调用，解耦 combat 插件依赖
        from lingmo_engine.core.events import PluginEvent
        bus = getattr(self, '_event_bus', None)
        if bus:
            return bus.request(
                PluginEvent.ABILITY_GENERATE,
                ability_input, affix_defs, rarity_info,
                tag_cost_map=tag_cost_map,
                exclusions=exclusions,
                warnings=warnings,
            )

        # 降级：EventBus 不可用时直接懒加载
        from lingmo_engine.plugins.combat.ability_generator import affix_generate_ability
        return affix_generate_ability(
            ability_input, affix_defs, rarity_info,
            tag_cost_map=tag_cost_map,
            exclusions=exclusions,
            warnings=warnings,
        )

    # ── 技能创建工具 ──

    def _create_ability_tool(
        self,
        params: dict,
        character_manager: "CharacterManager | None",
    ) -> ModuleResult:
        """create_ability LLM 工具 — 独立创建技能，可选赋予角色。

        复用 _generate_ability() 的 EventBus 优先模式，
        通过 state_updates.custom_abilities 返回，由 ToolExecutor 统一持久化。
        不再重复调用 gs.add_registry_ability()。
        """
        abilities_input = params.get("abilities", [])
        if not abilities_input:
            return ModuleResult(success=False, log="技能列表为空")

        warnings: list[str] = []
        created: list[dict] = []
        merged_custom_abilities = dict(self._custom_abilities)

        for ability_input in abilities_input:
            ability_def = self._generate_ability(ability_input, warnings)
            if ability_def is None:
                continue

            ability_id = ability_def["id"]
            merged_custom_abilities[ability_id] = ability_def
            self._custom_abilities[ability_id] = ability_def

            rarity_int = ability_def.get("rarity", ability_input.get("rarity", 25))
            rarity_info = (
                self._world.get_ability_rarity_info(rarity_int)
                if self._world else {}
            )

            created.append({
                "ability_id": ability_id,
                "name": ability_def["name"],
                "rarity": ability_def["rarity"],
                "rarity_name": rarity_info.get("name", "普通"),
                "rarity_color": rarity_info.get("color", "#9e9e9e"),
            })

            # 更新归一化索引，避免同批次后续条目重复创建
            if hasattr(self, "_ability_norm_index"):
                new_name = ability_def.get("name", "")
                new_norm = self._normalize_name(new_name)
                if new_norm:
                    self._ability_norm_index.append(
                        (ability_id, new_name, new_norm))

        if not created:
            return ModuleResult(success=False, log="没有有效的技能被创建")

        log = "创建 {} 个技能: {}".format(
            len(created),
            ", ".join(s["name"] for s in created),
        )
        if warnings:
            log += "\n⚠ 以下问题需要关注：\n" + "\n".join(warnings)

        result_data: dict = {
            "created_abilities": created,
            "state_updates": {
                "custom_abilities": merged_custom_abilities,
            },
        }

        # for_entity: 创建后立即赋予给目标角色
        for_entity = params.get("for_entity")
        if for_entity and created and character_manager is not None:
            from lingmo_engine.core.utils import find_entity
            char = find_entity(character_manager, for_entity)
            if char:
                ability_ids = [c["ability_id"] for c in created]
                for aid in ability_ids:
                    if aid not in char.abilities:
                        char.abilities.append(aid)
                result_data["assigned_to"] = char.name
                log += f"\n已赋予给「{char.name}」"
            else:
                log += "\n⚠ 角色未找到，技能仅创建定义"

        return ModuleResult(success=True, data=result_data, log=log)

    def _apply_temporary_default(self, char_data: dict) -> None:
        """设置 char_type 和 temporary 的默认值。仅在未指定时填充默认值。"""
        if "char_type" not in char_data:
            char_data["char_type"] = "npc"
        if "temporary" not in char_data:
            char_data["temporary"] = False

    # ── 状态持久化 ──

    def get_state(self) -> dict:
        """返回插件运行时状态。角色数据由 CharacterManager 统一持久化。"""
        return {}

    def load_state(self, state: dict) -> None:
        """恢复插件运行时状态。"""
        pass
