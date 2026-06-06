"""PanelSchemaResolver — 读取 character_panel_schema.yaml 并解析字段显示值。"""

from __future__ import annotations

import importlib.util
import inspect
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


class PanelSchemaResolver:
    """读取 character_panel_schema.yaml，解析 section 配置和值解析规则。"""

    def __init__(self, world_dir: Path | str):
        self._world_dir = Path(world_dir)
        schema_path = self._world_dir / "character_panel_schema.yaml"
        if schema_path.exists():
            self._schema = yaml.safe_load(
                schema_path.read_text(encoding="utf-8")
            ) or {}
        else:
            self._schema = {}
        self._resolvers = self._load_resolvers()

    def get_sections_schema(self) -> dict:
        """返回 sections 配置给前端。"""
        return self._schema.get("sections", {})

    def resolve_display_values(self, character_data: dict) -> dict:
        """遍历 resolvers 配置，解析所有需要转换的字段值。"""
        display_values = {}
        for field_key, config in self._schema.get("resolvers", {}).items():
            raw_value = self._get_raw_value(field_key, character_data)
            resolver_class_name = config.get("resolver_class")
            if resolver_class_name and resolver_class_name in self._resolvers:
                display_values[field_key] = self._resolvers[resolver_class_name].resolve(
                    field_key, raw_value, character_data
                )
            else:
                display_values[field_key] = self._resolve_simple(raw_value, config)
        return display_values

    def _get_raw_value(self, field_key: str, character_data: dict):
        """从角色数据中提取原始值，支持 extra.xxx 嵌套路径。"""
        if "." in field_key:
            parts = field_key.split(".", 2)
            parent = character_data.get(parts[0]) or {}
            return parent.get(parts[1]) if isinstance(parent, dict) else None
        extra = character_data.get("extra") or {}
        if not isinstance(extra, dict):
            extra = {}
        if field_key in extra:
            return extra[field_key]
        return character_data.get(field_key)

    def _resolve_simple(self, raw_value, config: dict) -> str:
        """简单 lookup 解析（source + lookup_key + display_key）。"""
        source = config.get("source", "")
        if not source:
            return str(raw_value) if raw_value is not None else ""
        file_path_str, _, top_key = source.partition("#")
        data_file = self._world_dir / file_path_str
        if not data_file.exists():
            return str(raw_value) if raw_value is not None else ""
        data = yaml.safe_load(data_file.read_text(encoding="utf-8"))
        items = data.get(top_key, [])
        lookup_key = config.get("lookup_key", "id")
        display_key = config.get("display_key", "name")
        for item in items:
            if item.get(lookup_key) == raw_value:
                return str(item.get(display_key, raw_value))
        return str(raw_value) if raw_value is not None else ""

    def _load_resolvers(self) -> dict:
        """动态加载 world/resolvers/ 下的自定义解析器类。"""
        resolvers_dir = self._world_dir / "resolvers"
        if not resolvers_dir.is_dir():
            return {}
        result: dict[str, object] = {}
        for py_file in resolvers_dir.glob("*_resolver.py"):
            try:
                spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                for name, cls in inspect.getmembers(module, inspect.isclass):
                    if name.endswith("Resolver") and hasattr(cls, "resolve"):
                        result[name] = cls(self._world_dir)
            except Exception:
                logger.warning("加载解析器失败: %s", py_file, exc_info=True)
        return result
