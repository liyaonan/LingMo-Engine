"""角色创建配置数据类与 YAML 加载。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# 已从 TemplateApply 移除并迁移到 world_fields 的旧修仙字段名
_WORLD_MIGRATED_FIELDS: frozenset[str] = frozenset({
    "cultivation_stage", "cultivation_substage", "cultivation_path",
    "secondary_path", "spiritual_roots", "root_quality",
})


@dataclass
class TemplateApply:
    """模板预填充数据。文本字段（background/opening_text/personality）可含 {变量} 占位符。"""
    level: int = 1
    attrs: dict[str, int] = field(default_factory=dict)
    abilities: list[str] = field(default_factory=list)
    inventory: list[dict] = field(default_factory=list)
    equipment: dict[str, str] = field(default_factory=dict)
    faction: str = ""
    location: str = ""
    personality: str = ""
    tags: list[str] = field(default_factory=list)
    background: str = ""
    opening_text: str = ""
    opening_text_dark: str = ""
    world_fields: dict = field(default_factory=dict)


@dataclass
class CharacterTemplate:
    """角色模板（职业/出身）。"""
    id: str
    name: str = ""
    description: str = ""
    apply: TemplateApply = field(default_factory=TemplateApply)


@dataclass
class RouteConfig:
    """路线选择卡片配置。"""
    id: str
    title: str = ""
    subtitle: str = ""
    chapter: str = ""
    description: str = ""
    locked: bool = True
    template_id: str = ""
    narrative_badge: str = ""
    narrative_text: list[str] = field(default_factory=list)
    narrative_text_dark: list[str] = field(default_factory=list)
    narrative_highlights: list[str] = field(default_factory=list)
    narrative_meta: str = ""


@dataclass
class FormFieldOption:
    """select 类型表单字段的选项。"""
    value: str
    label: str
    description: str = ""


@dataclass
class FormField:
    """单个表单字段定义。已知 key（name/personality/background 等）映射到 Character 字段，
    未知 key 映射到 Character.extra。"""
    key: str
    label: str = ""
    type: str = "text"  # text | select | textarea | multi_select
    required: bool = False
    placeholder: str = ""
    rows: int | None = None
    options: list[FormFieldOption] = field(default_factory=list)
    routes: list[str] = field(default_factory=list)
    min: int | None = None
    max: int | None = None


@dataclass
class CreationConfig:
    """角色创建完整配置。"""
    title: str = ""
    templates: list[CharacterTemplate] = field(default_factory=list)
    fields: list[FormField] = field(default_factory=list)
    routes: list[RouteConfig] = field(default_factory=list)


def load_creation_config(path: Path) -> CreationConfig | None:
    """从 YAML 文件加载角色创建配置。文件不存在返回 None。"""
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    templates = []
    for t in data.get("templates", []):
        apply_raw = t.get("apply", {})

        # 将旧 YAML 中的修仙字段自动迁移到 world_fields
        world_fields: dict[str, Any] = dict(apply_raw.get("world_fields", {}))
        for migrated_key in _WORLD_MIGRATED_FIELDS:
            if migrated_key in apply_raw:
                world_fields[migrated_key] = apply_raw[migrated_key]

        templates.append(CharacterTemplate(
            id=t["id"],
            name=t.get("name", ""),
            description=t.get("description", ""),
            apply=TemplateApply(
                level=apply_raw.get("level", 1),
                attrs=dict(apply_raw.get("attrs", {})),
                abilities=list(apply_raw.get("abilities", apply_raw.get("skills", []))),
                inventory=list(apply_raw.get("inventory", [])),
                equipment=dict(apply_raw.get("equipment", {})),
                faction=apply_raw.get("faction", ""),
                location=apply_raw.get("location", ""),
                personality=apply_raw.get("personality", ""),
                tags=list(apply_raw.get("tags", [])),
                background=apply_raw.get("background", ""),
                opening_text=apply_raw.get("opening_text", ""),
                opening_text_dark=apply_raw.get("opening_text_dark", ""),
                world_fields=world_fields,
            ),
        ))

    fields = []
    for f in data.get("fields", []):
        field_opts = []
        for o in f.get("options", []):
            field_opts.append(FormFieldOption(
                value=o["value"],
                label=o.get("label", o["value"]),
                description=o.get("description", ""),
            ))
        fields.append(FormField(
            key=f["key"],
            label=f.get("label", ""),
            type=f.get("type", "text"),
            required=f.get("required", False),
            placeholder=f.get("placeholder", ""),
            rows=f.get("rows"),
            options=field_opts,
            routes=list(f.get("routes", [])),
            min=f.get("min"),
            max=f.get("max"),
        ))

    routes = []
    for r in data.get("routes", []):
        routes.append(RouteConfig(
            id=r["id"],
            title=r.get("title", ""),
            subtitle=r.get("subtitle", ""),
            chapter=r.get("chapter", ""),
            description=r.get("description", ""),
            locked=r.get("locked", True),
            template_id=r.get("template_id", ""),
            narrative_badge=r.get("narrative_badge", ""),
            narrative_text=list(r.get("narrative_text", [])),
            narrative_text_dark=list(r.get("narrative_text_dark", [])),
            narrative_highlights=list(r.get("narrative_highlights", [])),
            narrative_meta=r.get("narrative_meta", ""),
        ))

    return CreationConfig(
        title=data.get("title", ""),
        templates=templates,
        fields=fields,
        routes=routes,
    )
