from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class CharacterService:
    """角色服务 — 封装角色查询、详情、NPC 列表。"""

    def __init__(self, gm, world):
        self._gm = gm
        self._world = world

    def get_player(self):
        """获取玩家角色"""
        return self._gm.state.get_player()

    def get_character(self, char_id):
        """获取指定角色"""
        cm = self._gm.state.character_manager
        if cm is None:
            return None
        return cm.get(char_id)

    def get_nearby_characters(self) -> list:
        """获取与玩家同位置的角色列表。"""
        cm = getattr(self._gm.state, 'character_manager', None)
        if cm is None:
            cm = getattr(self._world, '_char_manager', None)
        if cm is None:
            return []
        player = cm.player
        return [c for c in cm.all() if c.location == player.location and c.id != player.id]

    @property
    def world(self):
        return self._world

    def get_character_detail(self, char_id: int) -> dict | None:
        """获取角色详情（含面板配置、装备、记忆、关系）。"""
        cm = getattr(self._gm.state, 'character_manager', None)
        if cm is None:
            return None
        char = cm.get(char_id)
        if char is None:
            return None

        world = self._world

        # 面板配置
        panel_config = {}
        world_dir = getattr(world, '_world_dir', None)
        if world_dir:
            panel_config_path = Path(world_dir) / "panel_config.yaml"
            if panel_config_path.exists():
                import yaml
                with open(panel_config_path, "r", encoding="utf-8") as f:
                    panel_config = yaml.safe_load(f) or {}

        # 面板 schema
        panel_schema = {}
        display_values = {}
        try:
            resolver = world.get_panel_schema_resolver()
            panel_schema = resolver.get_sections_schema()
            display_values = resolver.resolve_display_values(char.to_dict())
        except Exception:
            logger.warning("面板 schema 解析失败", exc_info=True)

        # 技能数据：世界静态 + 注册表动态
        abilities_data = {}
        if hasattr(world, 'abilities'):
            abilities_data = dict(world.abilities)
        gs = self._gm.state
        registry_abilities = gs.get_all_registry_abilities() if gs else {}
        abilities_data.update(registry_abilities)

        # 装备数据：解析槽位名称和物品名称
        equipment_expanded = {}
        slot_names = {}
        if hasattr(world, 'equip_slots') and world.equip_slots:
            for s in world.equip_slots.get("slots", []):
                slot_names[s["id"]] = s.get("name", s["id"])

        inv_plugin = (self._gm.plugins.get_plugin("inventory")
                      if self._gm.plugins else None)
        item_system = inv_plugin.item_system if inv_plugin else None
        for slot_id, item_id in char.equipment.items():
            slot_name = slot_names.get(slot_id, slot_id)
            item_name = item_id
            if item_system:
                item_obj = item_system.get_item(item_id)
                if item_obj:
                    item_name = item_obj.name
            if item_name == item_id and hasattr(world, 'items') and item_id in world.items:
                item_name = world.items[item_id].get("name", item_id)
            equipment_expanded[slot_name] = item_name

        # 角色记忆
        memories_data = None
        ms = getattr(self._gm, '_memory_system', None)
        if ms and ms.char_memory:
            mem = ms.get_character_memory(char.name)
            if mem:
                memories_data = {
                    "shared_experiences": mem.shared_experiences,
                    "personal_events": mem.personal_events,
                    "opinions": mem.opinions,
                    "last_updated_round": mem.last_updated_round,
                }

        # 人际关系
        relationships_resolved = []
        if char.relationships and cm:
            for rel in char.relationships:
                other = cm.get(rel.get("target_id"))
                if other:
                    relationships_resolved.append({
                        "name": other.name,
                        "label": rel.get("label", ""),
                        "desc": rel.get("desc", ""),
                    })

        return {
            "character": char.to_dict(),
            "panel_config": panel_config.get("panel_config", {}).get(
                char.char_type.value, {}
            ),
            "panel_schema": panel_schema,
            "display_values": display_values,
            "attributes_schema": world.get_attributes_schema(),
            "elements": world.elements,
            "abilities": abilities_data,
            "equipment_expanded": equipment_expanded,
            "memories": memories_data,
            "relationships": relationships_resolved,
        }

    def list_npcs_by_location(self, location_name: str) -> dict:
        """递归查询指定地点（任意层级）下所有叶子节点的 NPC。"""
        cm = getattr(self._gm.state, 'character_manager', None)
        if cm is None:
            cm = getattr(self._world, '_char_manager', None)
        map_tree = getattr(self._world, '_map', None)
        return self.query_npcs_by_location(cm, map_tree, location_name)

    @staticmethod
    def query_npcs_by_location(cm, map_tree, location_name: str) -> dict:
        """递归查询指定地点下所有叶子节点的 NPC（无状态，可跨模块调用）。

        角色的 location 字段可能有三种格式：节点 id、节点 name、完整路径。
        本方法对每个叶子节点同时用多种格式查询，取并集去重。

        Args:
            cm: CharacterManager 实例。
            map_tree: 地图树实例（需有 _nodes 属性），None 时退化为精确匹配。
            location_name: 目标地点名称。

        Returns:
            包含 location、leaf_locations、npcs、total 的汇总字典。
        """
        if cm is None:
            return {"location": location_name, "leaf_locations": [], "npcs": [], "total": 0}

        # 没有地图树时退化为精确匹配
        if map_tree is None:
            npcs = CharacterService._filter_npcs(cm.list_by_location(location_name))
            return {"location": location_name, "leaf_locations": [location_name], "npcs": npcs, "total": len(npcs)}

        # 在地图树节点中按 name 或 id 查找目标节点
        target_node = None
        for node in map_tree._nodes.values():
            if getattr(node, 'name', None) == location_name:
                target_node = node
                break
            if str(getattr(node, 'id', None)) == location_name:
                target_node = node
                break

        if target_node is None:
            npcs = CharacterService._filter_npcs(cm.list_by_location(location_name))
            return {"location": location_name, "leaf_locations": [location_name], "npcs": npcs, "total": len(npcs)}

        # 递归收集所有叶子节点
        leaf_nodes = []
        CharacterService._collect_leaf_nodes(map_tree, target_node, leaf_nodes)
        if not leaf_nodes:
            leaf_nodes = [target_node]

        # 对每个叶子节点，构建多种 location 格式查询 NPC（取并集去重）
        seen_ids = set()
        all_npcs = []
        leaf_names = []
        for node in leaf_nodes:
            leaf_names.append(node.name)
            for loc in CharacterService._build_location_keys(map_tree, node):
                for n in CharacterService._filter_npcs(cm.list_by_location(loc)):
                    if n["id"] not in seen_ids:
                        seen_ids.add(n["id"])
                        all_npcs.append(n)

        return {"location": location_name, "leaf_locations": leaf_names, "npcs": all_npcs, "total": len(all_npcs)}

    @staticmethod
    def _collect_leaf_nodes(map_tree, node, result: list) -> None:
        """递归收集节点下所有叶子节点对象。"""
        children_ids = getattr(node, 'children_ids', [])
        if not children_ids:
            result.append(node)
            return
        for child_id in children_ids:
            child_node = map_tree._nodes.get(child_id)
            if child_node is not None:
                CharacterService._collect_leaf_nodes(map_tree, child_node, result)

    @staticmethod
    def _build_location_keys(map_tree, node) -> list[str]:
        """为一个地图节点生成所有可能的 location 格式。

        角色的 location 字段可能是：节点 id、节点 name、或完整路径。
        返回去重的格式列表。
        """
        keys = set()
        node_id = getattr(node, 'id', None)
        if node_id:
            keys.add(str(node_id))
        node_name = getattr(node, 'name', None)
        if node_name:
            keys.add(node_name)
        # 完整路径 — 复用 MapPlugin 的路径构建逻辑
        from lingmo_engine.plugins.map.plugin import MapPlugin
        full_path = MapPlugin._build_node_full_path(map_tree, node)
        if full_path:
            keys.add(full_path)
        return list(keys)

    @staticmethod
    def _filter_npcs(chars) -> list[dict]:
        """过滤并转换 NPC 角色列表。

        仅保留 char_type 为 "npc" 且 id 不为 0 的角色，
        返回包含指定字段的字典列表。

        Args:
            chars: 原始角色列表，通常来自 character_manager.list_by_location。

        Returns:
            过滤后的 NPC 字典列表。
        """
        npcs = [
            n for n in chars
            if n.char_type.value in ("npc",) and n.id != 0
        ]
        return [
            {
                "id": n.id,
                "name": n.name,
                "tags": n.tags,
                "location": n.location,
                "current_affairs": n.current_affairs,
                "avatar": n.avatar,
                "faction": n.faction,
                "personality": n.personality,
            }
            for n in npcs
        ]
