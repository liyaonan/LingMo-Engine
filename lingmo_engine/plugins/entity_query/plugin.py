"""统一实体查询插件 — 提供 query_entity 工具供 LLM 按需查询实体详情。"""
from __future__ import annotations

import json
import logging

from lingmo_engine.core.base_plugin import BasePlugin
from lingmo_engine.core.entity_registry import EntityCache, EntityRegistry
from lingmo_engine.core.entity_loaders import AbilityLoader, ItemLoader, CharacterLoader
from lingmo_engine.core.types import ModuleResult, ToolDefinition, ToolParameter
from lingmo_engine.plugins.character.schema_visibility import SchemaVisibilityResolver

logger = logging.getLogger(__name__)


class EntityQueryPlugin(BasePlugin):
    """统一实体查询插件。"""

    name = "entity_query"
    version = "0.1.0"

    def __init__(self):
        super().__init__()
        self._entity_registry: EntityRegistry | None = None
        self._entity_cache: EntityCache | None = None

    def on_load(self) -> None:
        """插件加载后，从 world 中获取实体数据并注册 Loader。"""
        config = self._load_config()
        self._entity_cache = EntityCache(max_size=config.get("cache_size", 30))
        self._entity_registry = EntityRegistry(
            fuzzy_threshold=config.get("fuzzy_threshold", 5),
            type_thresholds=config.get("type_thresholds"),
        )

        # 注册技能/能力 Loader
        if self.world and self.world.abilities:
            self._entity_registry.register("ability", AbilityLoader(self.world.abilities))

        # 注册物品 Loader
        if self.world and self.world.items:
            self._entity_registry.register("item", ItemLoader(self.world.items))

        # 注册角色 Loader（注入 LLM 可见性 resolver）
        cm = self.world.get_character_manager() if self.world else None
        if cm:
            char_loader = CharacterLoader(cm)
            if self.world:
                char_schema = self.world.get_character_schema()
                if char_schema.get("llm_visibility"):
                    char_loader.set_visibility_resolver(
                        SchemaVisibilityResolver(char_schema)
                    )
            self._entity_registry.register("character", char_loader)

        logger.info("EntityQueryPlugin loaded, registry: %s", self._entity_registry.registered_types)

    def _load_config(self) -> dict:
        if self.world and self.world.setting:
            return self.world.setting.get("entity_query", {})
        return {}

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="query_entity",
                description=(
                    "按名称查询游戏实体详情。支持技能(ability)、物品(item)、角色(character)类型。"
                    "返回完整属性和描述。用于当你需要了解某个实体的详细信息时调用。"
                ),
                parameters=[
                    ToolParameter(
                        name="name",
                        type="string",
                        description="实体名称，支持精确和模糊匹配",
                        required=True,
                    ),
                    ToolParameter(
                        name="entity_type",
                        type="string",
                        description="限定类型: ability/item/character，不填则全类型搜索",
                        required=False,
                        enum=["ability", "item", "character"],
                    ),
                ],
            ),
        ]

    def execute_tool(self, tool_name: str, params: dict) -> ModuleResult:
        if tool_name != "query_entity":
            return ModuleResult(success=False, log=f"未知工具: {tool_name}")

        name = params.get("name", "")
        if not name:
            return ModuleResult(success=False, log="缺少必填参数: name")

        entity_type = params.get("entity_type")
        result = self._entity_registry.query(name, entity_type)

        # 缓存精确匹配和少量模糊匹配的结果
        if result.get("found") and result.get("results"):
            for r in result["results"]:
                self._entity_cache.put(r.get("type", "unknown"), r.get("name", ""), r)

        log = json.dumps(result, ensure_ascii=False)
        return ModuleResult(
            success=result.get("found", False),
            log=log,
            data=result,
        )

    def get_system_prompt(self) -> str:
        """返回实体索引 + 缓存段，注入到 system prompt。"""
        parts = []
        if self._entity_registry:
            index = self._entity_registry.get_index()
            if index:
                parts.append("[实体索引]\n" + index)
        if self._entity_cache:
            cached = self._entity_cache.get_cached_prompt()
            if cached:
                parts.append(cached)
        return "\n\n".join(parts)
