"""CreationEngine — 角色创建表单引擎（单页模式）。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from lingmo_engine.core.character import Character, CharacterType, _normalize_inventory

if TYPE_CHECKING:
    from lingmo_engine.character_creation.schema import (
        CreationConfig, CharacterTemplate, FormField,
    )
    from lingmo_engine.core.character_manager import CharacterManager
    from lingmo_engine.core.game_state import GameState

logger = logging.getLogger(__name__)

# 表单字段 key → Character 属性名映射
KNOWN_CHAR_FIELDS: frozenset[str] = frozenset({
    "name", "dao_name", "hobbies", "personality", "background", "faction", "location", "tags",
    "gender",
})

# 列表类型字段：表单提交的字符串会按逗号拆分为列表
_LIST_FIELDS: frozenset[str] = frozenset({"tags"})


class CreationEngine:
    """角色创建引擎。接收 world 配置和表单提交，生成 Character。"""

    def __init__(
        self,
        config: "CreationConfig | None",
        world,
        character_manager: "CharacterManager",
        game_state: "GameState",
    ):
        self.config = config
        self.world = world
        self.character_manager = character_manager
        self.game_state = game_state
        self._opening_text: str = ""
        self._selected_route_id: str = ""

    def get_routes_data(self) -> list[dict]:
        """返回路线选择页所需的元数据列表。"""
        if not self.config or not self.config.routes:
            return []
        return [
            {
                "id": r.id,
                "title": r.title,
                "subtitle": r.subtitle,
                "chapter": r.chapter,
                "description": r.description,
                "locked": r.locked,
                "template_id": r.template_id,
                "narrative_badge": r.narrative_badge,
                "narrative_text": list(r.narrative_text),
                "narrative_text_dark": list(r.narrative_text_dark),
                "narrative_highlights": list(r.narrative_highlights),
                "narrative_meta": r.narrative_meta,
            }
            for r in self.config.routes
        ]

    def get_config_data(self) -> dict:
        """返回前端渲染所需的配置数据。"""
        if not self.config:
            return {"title": "", "templates": [], "fields": []}

        templates = []
        for t in self.config.templates:
            loc_id = t.apply.location
            templates.append({
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "apply": {
                    "level": t.apply.level,
                    "attrs": dict(t.apply.attrs),
                    "abilities": list(t.apply.abilities),
                    "inventory": list(t.apply.inventory),
                    "equipment": dict(t.apply.equipment),
                    "faction": t.apply.faction,
                    "location": loc_id,
                    "location_name": self._resolve_location_name(loc_id),
                    "personality": t.apply.personality,
                    "tags": list(t.apply.tags),
                    "background": t.apply.background,
                    "opening_text": t.apply.opening_text,
                    "opening_text_dark": t.apply.opening_text_dark,
                },
            })

        fields = []
        for f in self.config.fields:
            field_data = {
                "key": f.key,
                "label": f.label,
                "type": f.type,
                "required": f.required,
                "placeholder": f.placeholder,
            }
            if f.rows is not None:
                field_data["rows"] = f.rows
            if f.options:
                field_data["options"] = [
                    {
                        "value": o.value,
                        "label": o.label,
                        **({"description": o.description} if o.description else {}),
                    }
                    for o in f.options
                ]
            fields.append(field_data)

        return {
            "title": self.config.title,
            "templates": templates,
            "fields": fields,
            "routes": self.get_routes_data(),
        }

    def create_character(
        self, template_id: str, fields: dict[str, str]
    ) -> Character:
        """根据模板和表单数据创建玩家角色。

        Args:
            template_id: 选中的模板 ID
            fields: 前端提交的表单字段 {key: value}

        Returns:
            创建的 Character 对象（已加入 CharacterManager）

        Raises:
            ValueError: 模板无效或必填字段缺失
        """
        if not self.config:
            raise ValueError("角色创建配置未加载")

        # 查找模板
        template = None
        for t in self.config.templates:
            if t.id == template_id:
                template = t
                break
        if template is None:
            raise ValueError(f"无效的模板 ID: {template_id}")

        # 校验必填字段
        missing = self._validate_required(fields)
        if missing:
            raise ValueError(f"请填写必填字段: {', '.join(missing)}")

        # 记录选中的路线（用于后续移除对应 NPC）
        for r in self.config.routes:
            if r.template_id == template_id:
                self._selected_route_id = r.id
                break

        # 从模板创建角色
        char = self._template_to_character(template)

        # 根据 narrative_style 选择对应的 opening_text
        style = fields.get("narrative_style", "carefree")
        opening_raw = template.apply.opening_text_dark if style == "dark" and template.apply.opening_text_dark else template.apply.opening_text

        # 替换模板文本中的变量
        self._interpolate_template_fields(char, fields, opening_raw)

        # 保存叙事风格到角色 extra
        char.extra["narrative_style"] = style

        # 应用玩家编辑的表单字段
        self._apply_fields(char, fields)

        # 写入 CharacterManager（id=0 表示主角）
        char.id = 0
        char.char_type = CharacterType.PLAYER
        self.character_manager.add_character(char)

        return char

    def get_opening_text(self) -> str:
        """返回 interpolate 后的开场叙事文本。"""
        return self._opening_text

    def get_selected_route_id(self) -> str:
        """返回玩家选中的路线 ID。"""
        return self._selected_route_id

    def call_creation_hook(self, character_manager, game_state) -> None:
        """调用世界的 creation_hook.py（如果存在）。

        hook 函数签名: on_character_created(route_id, character, character_manager, game_state, world)
        """
        world_dir = getattr(self.world, '_world_dir', None)
        if not world_dir:
            return
        hook_path = Path(world_dir) / "creation_hook.py"
        if not hook_path.exists():
            return

        import importlib.util
        spec = importlib.util.spec_from_file_location("creation_hook", hook_path)
        if spec is None or spec.loader is None:
            return
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        hook_fn = getattr(module, "on_character_created", None)
        if hook_fn is None:
            logger.warning("creation_hook.py 缺少 on_character_created 函数")
            return

        player = self.character_manager.player
        hook_fn(
            route_id=self._selected_route_id,
            character=player,
            character_manager=character_manager,
            game_state=game_state,
            world=self.world,
        )

    # ── 内部方法 ──

    def _template_to_character(self, template: "CharacterTemplate") -> Character:
        """将模板的 apply 数据转换为 Character 对象。"""
        a = template.apply
        char = Character(
            id=0,
            name="",
            char_type=CharacterType.PLAYER,
            level=a.level,
            attrs=dict(a.attrs),
            abilities=list(a.abilities),
            inventory=_normalize_inventory(a.inventory),
            equipment=dict(a.equipment),
            faction=a.faction,
            location=a.location,
            personality=a.personality,
            tags=list(a.tags),
            background=a.background,
        )
        # world_fields 统一写入 extra，并设置代理属性（如 char.cultivation_stage）
        for key, value in a.world_fields.items():
            char.extra[key] = value
            if hasattr(char, key):
                setattr(char, key, value)
        return char

    def _apply_fields(self, char: Character, fields: dict[str, str]) -> None:
        """将表单字段写入 Character。已知字段直接映射，未知字段存入 extra。"""
        for key, value in fields.items():
            if not value:
                continue
            if key in KNOWN_CHAR_FIELDS:
                if key in _LIST_FIELDS:
                    # tags 按逗号拆分为列表
                    setattr(char, key, [v.strip() for v in value.split(",") if v.strip()])
                else:
                    setattr(char, key, value)
            else:
                char.extra[key] = value

        # 缓存开场叙事文本（优先使用前端传值，否则保留插值结果）
        if fields.get("_opening_text"):
            self._opening_text = fields["_opening_text"]

    def _interpolate_template_fields(
        self, char: Character, field_values: dict[str, str],
        opening_text_raw: str = "",
    ) -> None:
        """替换 Character 文本字段和 _opening_text 中的 {变量} 占位符。"""
        vars_dict = self._build_vars_dict(char, field_values)

        if "{" in char.personality:
            char.personality = self.interpolate(char.personality, vars_dict)
        if "{" in char.background:
            char.background = self.interpolate(char.background, vars_dict)

        if opening_text_raw and "{" in opening_text_raw:
            self._opening_text = self.interpolate(opening_text_raw, vars_dict)
        else:
            self._opening_text = opening_text_raw

    def _validate_required(self, fields: dict[str, str]) -> list[str]:
        """校验必填字段，返回缺失的字段 label 列表。"""
        if not self.config:
            return []
        missing = []
        for f in self.config.fields:
            if f.required:
                value = fields.get(f.key, "").strip()
                if not value:
                    missing.append(f.label or f.key)
        return missing

    def interpolate(self, template: str, vars_dict: dict[str, str] | None = None) -> str:
        """替换模板中的 {变量名} 占位符。缺失变量替换为空字符串。"""
        if vars_dict is None:
            vars_dict = self._build_vars_dict(Character(id=0, name="", char_type=CharacterType.PLAYER), {})

        class SafeDict(dict):
            def __missing__(self, key):
                return ""

        try:
            return template.format_map(SafeDict(vars_dict))
        except (KeyError, ValueError):
            return template

    def _build_vars_dict(
        self, char: Character, field_values: dict[str, str]
    ) -> dict[str, str]:
        """构建模板变量字典，来源：Character 字段 + 表单值 + world 信息。"""
        vars_dict: dict[str, str] = {}
        # 表单值优先（包含 name 等用户输入）
        for k, v in field_values.items():
            if not k.startswith("_"):
                vars_dict[k] = str(v)
        # Character 字段
        # player_name 优先从表单 name 字段获取（此时 char.name 尚未设置）
        if field_values.get("name"):
            vars_dict.setdefault("player_name", str(field_values["name"]))
        vars_dict.setdefault("player_name", char.name)
        vars_dict.setdefault("personality", "" if "{" in char.personality else char.personality)
        vars_dict.setdefault("background", "" if "{" in char.background else char.background)
        vars_dict.setdefault("faction", char.faction)
        vars_dict.setdefault("profession_name", char.extra.get("profession_name", ""))
        # 地点名称
        loc_name = self._resolve_location_name(char.location)
        vars_dict.setdefault("location", loc_name)
        vars_dict.setdefault("location_id", char.location)
        # world 名称
        vars_dict.setdefault("world_name", self.world.setting.get("world", {}).get("name", ""))
        # attrs
        for k, v in char.attrs.items():
            vars_dict.setdefault(k, str(v))
        # 汇总
        vars_dict.setdefault("all_skills", ", ".join(char.abilities))
        attrs_parts = [f"{k}:{v}" for k, v in char.attrs.items()]
        vars_dict.setdefault("all_attrs", ", ".join(attrs_parts))
        return vars_dict

    def _resolve_location_name(self, loc_id: str) -> str:
        """将 location id 解析为地图节点名称。"""
        if not loc_id:
            return ""
        node_name = self._lookup_map_node_name(loc_id)
        if node_name:
            return node_name
        return loc_id

    def _lookup_map_node_name(self, loc_id: str) -> str:
        """从 world maps/ 目录中查找节点名称。结果缓存避免重复读取。"""
        if not hasattr(self, '_map_node_names'):
            self._map_node_names: dict[str, str] = {}
            world_dir = getattr(self.world, '_world_dir', None)
            if world_dir:
                import yaml
                from pathlib import Path
                maps_dir = Path(world_dir) / "maps"
                if maps_dir.is_dir():
                    for yf in sorted(maps_dir.glob("*.yaml")):
                        try:
                            data = yaml.safe_load(yf.read_text(encoding="utf-8")) or {}
                            for n in data.get("nodes", []):
                                nid = n.get("id")
                                nname = n.get("name")
                                if nid and nname:
                                    self._map_node_names[nid] = nname
                        except Exception:
                            pass
        return self._map_node_names.get(loc_id, "")
