"""无极世界字段值解析器 — 境界、修炼方向、灵根"""

from __future__ import annotations

from pathlib import Path

import yaml


class CultivationResolver:
    def __init__(self, world_dir: Path | str):
        self._world_dir = Path(world_dir)
        cultivation_path = self._world_dir / "cultivation.yaml"
        if cultivation_path.exists():
            self._cultivation = yaml.safe_load(
                cultivation_path.read_text(encoding="utf-8")
            )
        else:
            self._cultivation = {}
        self._stage_map = {
            s["id"]: s for s in self._cultivation.get("stages", [])
        }
        self._path_map = self._cultivation.get("cultivation_paths", {})
        # 加载元素定义，用于灵根ID→中文名转换
        schema_path = self._world_dir / "characters" / "character_schema.yaml"
        if schema_path.exists():
            schema_data = yaml.safe_load(
                schema_path.read_text(encoding="utf-8")
            )
            elements = schema_data.get("elements", {}).get("definitions", [])
            self._element_map = {e["id"]: e["name"] for e in elements}
        else:
            self._element_map = {}

    def resolve(self, field_key: str, raw_value, character_data: dict) -> str:
        dispatch = {
            "cultivation_stage": self._resolve_stage,
            "cultivation_substage": self._resolve_substage,
            "cultivation_path": self._resolve_path,
            "secondary_path": self._resolve_path,
            "spiritual_roots": self._resolve_roots,
        }
        handler = dispatch.get(field_key)
        return handler(raw_value, character_data) if handler else (str(raw_value) if raw_value else "")

    def _resolve_stage(self, stage_id, _data) -> str:
        stage = self._stage_map.get(stage_id)
        return stage["name"] if stage else str(stage_id)

    def _resolve_substage(self, substage_key, data) -> str:
        extra = data.get("extra") or {}
        if not isinstance(extra, dict):
            extra = {}
        stage_id = extra.get("cultivation_stage", "")
        stage = self._stage_map.get(stage_id)
        if not stage:
            return str(substage_key) if substage_key else ""
        labels = stage.get("sub_labels_cn", {})
        return labels.get(substage_key, str(substage_key)) if substage_key else ""

    def _resolve_path(self, path_id, _data) -> str:
        path = self._path_map.get(path_id)
        return path["name"] if path else (str(path_id) if path_id else "")

    def _resolve_roots(self, roots, _data) -> str:
        if not roots or not isinstance(roots, list) or len(roots) == 0:
            return ""
        names = [self._element_map.get(str(r), str(r)) for r in roots]
        return " · ".join(names)
