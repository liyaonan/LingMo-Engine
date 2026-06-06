"""可见性解析协议 — 核心层与角色插件的解耦接口。"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class VisibilityProtocol(Protocol):
    """LLM 可见性解析器必须实现的接口。

    具体实现由 plugins.character.schema_visibility.SchemaVisibilityResolver 提供，
    核心层通过此协议引用，避免直接依赖插件包。
    """

    def filter_attrs(self, attrs: dict) -> dict: ...

    def filter_fields(self, data: dict) -> dict: ...
