"""地图插件 - 管理世界地图、位置导航和扩展持久化"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

import yaml  # noqa: F401 — _write_extensions_file 仍使用 yaml

from lingmo_engine.core.base_plugin import BasePlugin
from lingmo_engine.core.events import PluginEvent, PluginName
from lingmo_engine.core.types import ToolDefinition, ToolParameter, ModuleResult
from lingmo_engine.core.map import MapNode, DefaultMap
from lingmo_engine.core.spatial import SpatialCalc

logger = logging.getLogger(__name__)


class LocationNormalizer:
    """Location 标准化器 — 由 MapPlugin 注入到 character_generator。"""

    def __init__(self, map_getter):
        self._map_getter = map_getter

    def normalize(self, location: str) -> str:
        """将任意格式的 location 标准化为完整路径。"""
        from lingmo_engine.plugins.map.plugin import MapPlugin
        return MapPlugin.resolve_to_full_path(location, self._map_getter())


class MapPlugin(BasePlugin):
    """地图插件 v0.1.0 - 树形地图导航"""

    name = PluginName.MAP
    version = "0.1.0"
    depends_on: list[str] = []

    def __init__(self):
        super().__init__()
        self._map: DefaultMap | None = None
        self._world_dir: str = ""
        self._state: dict = {}
        self._map_dir: Path | None = None  # saves/{slot}/map/ 目录
        self._map_config: dict = {}

    def on_load(self) -> None:
        """从 world 目录加载 maps/ 下所有 yaml 构建 DefaultMap，兼容旧版 map.yaml"""
        if self._map is not None:
            return
        world = self._world
        if world and hasattr(world, '_world_dir') and world._world_dir:
            self._world_dir = world._world_dir
            world_path = Path(self._world_dir)

            # 优先读取 maps/ 目录下所有 yaml 文件
            maps_dir = world_path / "maps"
            if maps_dir.is_dir():
                all_nodes: list[MapNode] = []
                start_node_id = ""
                seen_ids: set[str] = set()
                yaml_files = sorted(
                    [f for f in maps_dir.iterdir() if f.suffix in (".yaml", ".yml")]
                )
                for yaml_file in yaml_files:
                    try:
                        with open(yaml_file, "r", encoding="utf-8") as f:
                            map_config = yaml.safe_load(f) or {}
                    except (yaml.YAMLError, OSError) as e:
                        logger.error("加载地图文件 %s 失败: %s，已跳过", yaml_file.name, e)
                        continue
                    nodes_data = map_config.get("nodes", [])
                    for n in nodes_data:
                        node = MapNode.from_dict(n)
                        if node.id in seen_ids:
                            logger.warning(
                                "重复节点ID '%s' (来自 %s)，将覆盖已有节点",
                                node.id, yaml_file.name,
                            )
                        seen_ids.add(node.id)
                        all_nodes.append(node)
                    if not start_node_id:
                        start_node_id = map_config.get("start_node", "")
                    logger.info(
                        "  加载地图文件 %s: %d 个节点", yaml_file.name, len(nodes_data)
                    )
                self._map = DefaultMap(nodes=all_nodes, start_node_id=start_node_id)
                self._map.sync_parent_child()
                # 将世界定义的设施膨胀为子节点
                self._inflate_facilities_to_nodes()
                self._map.compute_intermediate_coords()
                logger.info(
                    "地图加载完成: %d 个文件, %d 个节点, 起点=%s",
                    len(yaml_files), len(all_nodes), start_node_id,
                )
            else:
                # 兼容旧版单个 map.yaml
                path = world_path / "map.yaml"
                if path.exists():
                    with open(path, "r", encoding="utf-8") as f:
                        map_config = yaml.safe_load(f) or {}
                    nodes_data = map_config.get("nodes", [])
                    nodes = [MapNode.from_dict(n) for n in nodes_data]
                    start_node_id = map_config.get("start_node", "")
                    self._map = DefaultMap(nodes=nodes, start_node_id=start_node_id)
                    # 将世界定义的设施膨胀为子节点
                    self._inflate_facilities_to_nodes()
                    self._map.compute_intermediate_coords()
                    logger.info("地图加载完成: %d 个节点, 起点=%s", len(nodes), start_node_id)

        # 通过 EventBus 注册位置信息服务，供 GameMaster.build_state() 解耦调用
        if self._bus:
            self._bus.handle(PluginEvent.MAP_GET_LOCATION_INFO, self._handle_get_location_info)

        # 读取世界 map 配置
        if self._world and hasattr(self._world, 'setting'):
            self._map_config = self._world.setting.get("map", {})

        # 向 character 插件注入 location 标准化器
        self._inject_location_normalizer()

    def _inflate_facilities_to_nodes(self) -> None:
        """将节点中的 facilities 列表膨胀为子 MapNode（设施节点）。

        遍历所有节点，对每个有非空 facilities 的节点：
        - 兼容字典格式 {name, type, description} 和字符串格式 "inn"
        - 为每个设施创建 MapNode 子节点（type="facility:类型"）
        - 如果父节点下已有同名子节点，跳过（避免重复）
        - 膨胀后清空 node.facilities
        """
        if not self._map:
            return

        # 收集需要膨胀的设施（避免在遍历时修改集合）
        to_inflate: list[tuple[MapNode, list[dict]]] = []
        for node in self._map._nodes.values():
            if not node.facilities:
                continue
            normalized = []
            for fac in node.facilities:
                if isinstance(fac, str):
                    normalized.append({"name": fac, "type": fac, "description": ""})
                elif isinstance(fac, dict) and "name" in fac:
                    normalized.append(fac)
            if normalized:
                to_inflate.append((node, normalized))

        for parent_node, facilities in to_inflate:
            for fac in facilities:
                # 检查父节点下是否已有同名子节点
                existing = self._map._find_child_by_name(parent_node.id, fac["name"])
                if existing:
                    logger.debug(
                        "设施 '%s' 已作为子节点存在（id=%s），跳过膨胀",
                        fac["name"], existing.id,
                    )
                    continue
                # 创建设施子节点
                fac_type = fac.get("type", "")
                slug = self._map._generate_slug_id(fac["name"], prefix="facility_")
                fac_node = MapNode(
                    id=slug,
                    name=fac["name"],
                    description=fac.get("description", ""),
                    parent_id=parent_node.id,
                    type=f"facility:{fac_type}",
                )
                self._map._nodes[slug] = fac_node
                parent_node.children_ids.append(slug)
            # 清空 facilities
            parent_node.facilities = []

    def _inject_location_normalizer(self) -> None:
        """向 character 插件注入 location 标准化器。"""
        registry = getattr(self, "_registry", None)
        if not registry:
            return
        char_plugin = registry.get_plugin("character")
        if not char_plugin:
            return
        generator = getattr(char_plugin, "_generator", None)
        if not generator:
            return
        normalizer = LocationNormalizer(lambda: self._map)
        generator._location_normalizer = normalizer
        # 同时注入 resolver 到 CharacterManager
        cm = getattr(self._world, '_char_manager', None) if self._world else None
        if cm:
            cm.set_location_resolver(normalizer.normalize)
        logger.info("map: 已注入 location 标准化器到 character 插件")

    def load_state(self, state: dict) -> None:
        """从 state snapshot 恢复（旧格式兼容 + 设置目录 + 合并扩展节点）。

        新格式存档的节点恢复由 load_own_state() 处理。
        此方法保证 _map_dir 已设置且扩展节点已合并，供后续方法使用。
        """
        self._state = state
        # 设置地图持久化目录（与 npcs/、event/ 同级）
        save_dir = state.get("_save_dir", "")
        if save_dir:
            self._map_dir = Path(save_dir) / "map"
        # 先加载扩展节点，确保 _map._nodes 包含存档中的扩展地图
        self._merge_extensions()
        # 旧存档兼容：尝试从 state 残留的 current_node_id 恢复
        # 新存档会由 load_own_state() 用 map/state.json 覆盖此结果
        self._restore_current_node(state)

    def _find_fallback_node_id(self, state: dict) -> str | None:
        """从玩家记录的位置路径中逐层提取，找到地图中存在的最底层祖先节点。

        玩家 location 格式如 "仙界/金云仙域/混沌虚空"，
        从最深层开始逐层向上尝试匹配，返回找到的最深层节点 ID。
        """
        if not self._map:
            return None

        # 获取玩家记录的完整位置路径
        location_path = self._get_player_location_path(state)
        if not location_path:
            return None

        parts = [p.strip() for p in location_path.split("/") if p.strip()]
        if not parts:
            return None

        # 从最深层开始，逐层向上尝试匹配
        for depth in range(len(parts), 0, -1):
            node = self._find_node_by_name_path(parts[:depth])
            if node:
                return node.id

        return None

    def _find_node_id_by_path(self, location_path: str) -> str | None:
        """从完整路径字符串解析并查找地图节点 ID。

        location_path 格式如 "仙界/天枢域/天枢仙城"，
        按名称逐层匹配，返回最终节点 ID。
        """
        if not location_path or not self._map:
            return None
        parts = [p.strip() for p in location_path.split("/") if p.strip()]
        if not parts:
            return None
        node = self._find_node_by_name_path(parts)
        return node.id if node else None

    @staticmethod
    def build_full_path(location_info: dict) -> str:
        """从位置信息构建完整斜杠路径（面包屑转路径）。

        供 creation_controller 和 game_flow_controller 共用，避免重复代码。
        """
        breadcrumb = location_info.get("breadcrumb", [])
        if breadcrumb:
            return "/".join(b["name"] for b in breadcrumb)
        node = location_info.get("current_node", {})
        return node.get("name", "")

    @staticmethod
    def resolve_to_full_path(input_location: str, map_obj) -> str:
        """将任意格式的 location 解析为完整路径。

        支持输入：节点 id（如 qingshi_town）、节点 name（如 青石镇）、完整路径。
        无 map 或匹配不到时返回原始输入。
        """
        if not input_location or map_obj is None:
            return input_location

        # 按节点 id 精确匹配
        for node in map_obj._nodes.values():
            if getattr(node, 'id', None) == input_location:
                return MapPlugin._build_node_full_path(map_obj, node)

        # 按节点 name 精确匹配（同名歧义时记录警告）
        name_matches = [
            n for n in map_obj._nodes.values()
            if getattr(n, 'name', None) == input_location
        ]
        if name_matches:
            if len(name_matches) > 1:
                logger.warning(
                    "resolve_to_full_path: 节点名 '%s' 有 %d 个匹配，取第一个: %s",
                    input_location, len(name_matches),
                    MapPlugin._build_node_full_path(map_obj, name_matches[0]),
                )
            return MapPlugin._build_node_full_path(map_obj, name_matches[0])

        # 输入可能已经是完整路径，验证一下
        # 尝试按 "/" 拆分，逐级匹配节点
        parts = input_location.split("/")
        if len(parts) > 1:
            # 从根节点开始匹配
            root_candidates = [
                n for n in map_obj._nodes.values()
                if n.parent_id is None and getattr(n, 'name', '') == parts[0]
            ]
            if root_candidates:
                current = root_candidates[0]
                matched = True
                for part in parts[1:]:
                    found = False
                    for child_id in current.children_ids:
                        child = map_obj._nodes.get(child_id)
                        if child and getattr(child, 'name', '') == part:
                            current = child
                            found = True
                            break
                    if not found:
                        matched = False
                        break
                if matched:
                    return MapPlugin._build_node_full_path(map_obj, current)

        # 匹配不到，返回原始输入
        return input_location

    @staticmethod
    def _build_node_full_path(map_obj, node) -> str:
        """从节点沿 parent 链构建完整路径。"""
        parts = []
        current = node
        while current is not None:
            name = getattr(current, 'name', '')
            if name:
                parts.append(name)
            parent_id = getattr(current, 'parent_id', None)
            current = map_obj._nodes.get(parent_id) if parent_id else None
        return "/".join(reversed(parts))

    def _get_player_location_path(self, state: dict) -> str:
        """从 CharacterManager 获取玩家的完整位置路径。"""
        cm = state.get("__character_manager")
        if cm:
            loc = getattr(cm.player, 'location', '')
            if loc:
                return loc
        return ""

    def _find_node_by_name_path(self, path_parts: list[str]) -> MapNode | None:
        """按名称路径逐层匹配地图节点，委托给 DefaultMap。"""
        if not path_parts or not self._map:
            return None
        return self._map._find_node_by_name_path(path_parts)

    def get_state(self) -> dict:
        """地图状态已自持久化到 map/state.json，不写入 state.json。"""
        return {}

    def get_persistence_dir(self) -> str:
        """地图插件自管理 map/ 子目录。"""
        return "map"

    def save_own_state(self, slot_dir) -> None:
        """将地图运行时状态保存到 map/state.json。"""
        state_data = {"current_node_id": self._state.get("current_node_id", "")}
        self._save_plugin_json(slot_dir, "state.json", state_data)

    def load_own_state(self, slot_dir) -> None:
        """从 map/state.json 恢复地图运行时状态（SelfPersistable 主路径）。

        使用 _merge_done 标志跳过 load_state() 中已执行的 _merge_extensions，
        避免重复 YAML 解析。如果保存的节点已被世界 YAML 删除，
        回退到 start_node_id 作为安全兜底。
        """
        map_dir = Path(slot_dir) / "map"
        if not map_dir.exists():
            return
        # 确保 _map_dir 指向正确位置
        self._map_dir = map_dir
        # 仅在 load_state 未执行过时才合并扩展节点
        if not getattr(self, '_merge_done', False):
            self._merge_extensions()
        state_path = map_dir / "state.json"
        if not state_path.exists():
            return
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            current_node_id = data.get("current_node_id", "")
            if current_node_id and self._map and current_node_id in self._map._nodes:
                self._map._current_node_id = current_node_id
                self._state["current_node_id"] = current_node_id
            elif self._map:
                # 保存的节点不存在（世界 YAML 已更新），回退到起始节点
                start_id = getattr(self._map, '_start_node_id', '') or ""
                if start_id and start_id in self._map._nodes:
                    self._map._current_node_id = start_id
                    self._state["current_node_id"] = start_id
                    logger.warning(
                        "保存的节点 '%s' 不存在于当前地图，已回退到起始节点 '%s'",
                        current_node_id, start_id,
                    )
                else:
                    # 最后兜底：使用根节点
                    root = self._map._get_root_node()
                    if root:
                        self._map._current_node_id = root.id
                        self._state["current_node_id"] = root.id
                        logger.warning(
                            "保存的节点 '%s' 不存在，回退到根节点 '%s'",
                            current_node_id, root.id,
                        )
        except Exception:
            logger.warning("加载地图自持久化状态失败", exc_info=True)

    def _restore_current_node(self, state: dict) -> None:
        """从 state 恢复当前节点（旧格式兼容，新格式由 load_own_state 覆盖）。"""
        # 优先从 CharacterManager.player.location 解析
        cm = state.get("__character_manager")
        if cm and self._map:
            player_loc = getattr(cm.player, 'location', '')
            if player_loc:
                node_id = self._find_node_id_by_path(player_loc)
                if node_id:
                    self._map._current_node_id = node_id
                    self._state["current_node_id"] = node_id
                    return
        # 旧存档兼容：从 state 残留的 current_node_id 恢复
        saved_node_id = state.get("current_node_id", "")
        if saved_node_id and self._map and saved_node_id in self._map._nodes:
            self._map._current_node_id = saved_node_id
            self._state["current_node_id"] = saved_node_id
        elif self._map:
            # 节点丢失，从玩家位置路径逐层回退
            fallback_id = self._find_fallback_node_id(state)
            if fallback_id:
                self._map._current_node_id = fallback_id
                self._state["current_node_id"] = fallback_id
                logger.warning(
                    "节点 '%s' 不存在，已回退到祖先节点 '%s'",
                    saved_node_id, fallback_id,
                )
            elif saved_node_id:
                logger.error(
                    "节点 '%s' 不存在且无法从玩家位置回退，地图位置未恢复",
                    saved_node_id,
                )

    def get_tools(self) -> list[ToolDefinition]:
        # 动态构建 set_location 描述，注入世界层级结构
        hierarchy = self._map_config.get("hierarchy", [])
        if hierarchy:
            # 每层可能有逗号分隔的多种类型，用 / 连接各层
            hierarchy_hint = "/".join(hierarchy)
            set_loc_desc = (
                f"设置当前位置。输入从世界根节点到目标的完整路径，用 / 分隔。"
                f"世界层级结构为：{hierarchy_hint}。"
                f"路径必须严格遵循此层级，从第1层开始，每层一个节点。"
                f"如果路径中的节点不存在，系统会自动创建。"
                f"可通过 type 参数指定末尾节点的类型，如 facility:客栈 表示设施节点。"
            )
        else:
            set_loc_desc = (
                "设置当前位置。输入从世界根节点到目标的完整路径，"
                "用 / 分隔。如果路径中的节点不存在，系统会自动创建。"
                "路径深度必须满足世界层级要求。"
                "可通过 type 参数指定末尾节点的类型，如 facility:客栈 表示设施节点。"
            )
        return [
            ToolDefinition(
                name="set_location",
                description=set_loc_desc,
                parameters=[
                    ToolParameter(
                        name="path",
                        type="string",
                        description="从根节点到目标位置的完整路径，/ 分隔",
                        required=True,
                    ),
                    ToolParameter(
                        name="type",
                        type="string",
                        description="末尾节点的类型，如 facility:客栈、facility:铁匠铺。不填则创建普通区域节点",
                        required=False,
                    ),
                    ToolParameter(
                        name="description",
                        type="string",
                        description="末尾节点的描述",
                        required=False,
                    ),
                ],
            ),
            ToolDefinition(
                name="list_npcs",
                description=(
                    "根据地点名称查询该地点及所有子区域下的 NPC 列表。"
                    "支持任意层级的地点：传入父级地名可递归查询所有子区域。"
                    "用于了解某个区域中有哪些 NPC。"
                ),
                parameters=[
                    ToolParameter(
                        name="location",
                        type="string",
                        description="地点名称，可以是任意层级（如'青云门'查整个门派，'后山'查具体地点）",
                        required=True,
                    ),
                ],
                plugin_name="map",
            ),
        ]

    def execute_tool(self, tool_name: str, params: dict) -> ModuleResult:
        if tool_name == "set_location":
            return self._execute_set_location(params)
        if tool_name == "list_npcs":
            return self._list_npcs(params)
        return ModuleResult(success=False, log=f"MapPlugin 不支持工具: {tool_name}")

    def _execute_set_location(self, params: dict) -> ModuleResult:
        if self._map is None:
            return ModuleResult(success=False, log="地图未初始化")

        path_str = params.get("path", "").strip()
        if not path_str:
            return ModuleResult(success=False, log="路径为空")

        node_type = params.get("type", "").strip()
        node_desc = params.get("description", "").strip()

        location_path = [s.strip() for s in path_str.split("/") if s.strip()]

        # 校验：不能有空段（双斜杠或首尾斜杠导致）
        raw_segments = path_str.split("/")
        if len(location_path) != len(raw_segments):
            return ModuleResult(success=False, log="路径包含空白段，请检查格式（如 '仙界//天枢域'）")

        # 校验：路径至少有 1 层
        if not location_path:
            return ModuleResult(success=False, log="路径解析后为空")

        result = self._map.ensure_path(location_path)

        if result["arrived"]:
            # 校验：层级深度（仅对新创建的非设施节点生效）
            hierarchy = self._map_config.get("hierarchy", [])
            new_nodes = result.get("new_nodes", [])
            target_node = self._map._nodes.get(result["node"]["id"])
            is_new = target_node.id in {n["id"] for n in new_nodes} if new_nodes else False

            # 仅对新创建的末尾节点设置 type 和 description
            if is_new and target_node:
                if node_type:
                    target_node.type = node_type
                if node_desc:
                    target_node.description = node_desc

            if hierarchy:
                if new_nodes and target_node and not target_node.is_facility:
                    if len(location_path) < len(hierarchy):
                        # 回滚 ensure_path 已创建的节点，防止孤儿节点残留
                        self._rollback_new_nodes(new_nodes)
                        return ModuleResult(
                            success=False,
                            log=f"路径深度不足：当前 {len(location_path)} 层，世界要求 {len(hierarchy)} 层（{'/'.join(hierarchy)}）",
                        )
            self._state["current_node_id"] = result["node"]["id"]
            # 完整路径字符串（斜杠分隔）
            full_path = "/".join(location_path)
            if new_nodes:
                self._save_map_extensions(new_nodes)
            # 更新 result 中的 node 数据（type/description 可能已修改）
            if target_node:
                result["node"] = target_node.to_dict()
            return ModuleResult(
                success=True,
                log=f"到达 {result['node']['name']}",
                data={
                    "node": result["node"],
                    "breadcrumb": result["breadcrumb"],
                    "children": result["children"],
                    "connections": result["connections"],
                    "new_nodes": new_nodes,
                    "state_updates": {
                        "current_node_id": result["node"]["id"],
                    },
                    "player_updates": {
                        "location": full_path,
                    },
                },
            )
        return ModuleResult(success=False, log=result.get("error", "未知错误"))

    def _rollback_new_nodes(self, new_nodes: list[dict]) -> None:
        """回滚 ensure_path 已创建的节点，防止层级校验失败后残留孤儿节点。"""
        if not self._map or not new_nodes:
            return
        for node_data in new_nodes:
            node_id = node_data.get("id", "")
            node = self._map._nodes.pop(node_id, None)
            if node and node.parent_id and node.parent_id in self._map._nodes:
                parent = self._map._nodes[node.parent_id]
                if node_id in parent.children_ids:
                    parent.children_ids.remove(node_id)
            self._map._extension_ids.discard(node_id)
        # 恢复 _current_node_id 为回滚前的状态
        if self._state.get("current_node_id"):
            self._map._current_node_id = self._state["current_node_id"]
        logger.debug("已回滚 %d 个因层级校验失败而创建的节点", len(new_nodes))

    def _split_existing_and_new(self, path: list[str]) -> tuple[list[str], list[str]]:
        """将路径拆分为已存在部分和新增部分。"""
        existing = []
        current_id = None
        for name in path:
            node = self._map._find_child_by_name(current_id, name)
            if node:
                existing.append(name)
                current_id = node.id
            else:
                break
        new_part = path[len(existing):]
        return existing, new_part

    def _list_npcs(self, params: dict) -> "ModuleResult":
        """根据地点名称递归查询该地点及所有子区域下的 NPC 列表。"""
        from lingmo_engine.core.types import ModuleResult, DisplayType
        location = params.get("location", "")
        if not location:
            return ModuleResult(success=False, log="请提供地点名称。")

        # 获取 character_manager：优先从 _world._char_manager 获取
        cm = getattr(self._world, '_char_manager', None) if self._world else None
        if not cm:
            return ModuleResult(success=False, log="角色管理器不可用。")

        from lingmo_engine.services.character_service import CharacterService
        result = CharacterService.query_npcs_by_location(cm, self._map, location)

        if not result["npcs"]:
            return ModuleResult(
                success=True,
                log=f"在「{location}」及其子区域中没有找到 NPC。",
                data=result,
                display_type=DisplayType.SYSTEM,
            )

        lines = [f"在「{location}」找到 {result['total']} 个 NPC（覆盖区域: {', '.join(result['leaf_locations'])}）:"]
        for n in result["npcs"]:
            tags_str = f" [{', '.join(n['tags'][:3])}]" if n.get('tags') else ""
            lines.append(f"- id={n['id']} {n['name']} ({n['location']}){tags_str}")

        return ModuleResult(
            success=True,
            log="\n".join(lines),
            data=result,
            display_type=DisplayType.SYSTEM,
        )

    def _write_extensions_file(self, nodes: list[dict]) -> None:
        """原子写入 map_extensions.yaml。"""
        import os
        import tempfile
        try:
            self._map_dir.mkdir(parents=True, exist_ok=True)
            save_data = {"nodes": nodes}
            target = self._map_dir / "map_extensions.yaml"
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=str(self._map_dir), suffix=".yaml"
            )
            fd_closed = False
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    yaml.dump(save_data, f, allow_unicode=True, default_flow_style=False)
                    f.flush()
                    os.fsync(f.fileno())
                fd_closed = True
                os.replace(tmp_path, str(target))
            except Exception:
                if not fd_closed:
                    os.close(tmp_fd)
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise
        except Exception:
            logger.warning("写入扩展文件失败", exc_info=True)

    def get_semi_static_prompt(self) -> str:
        """世界地图概览树 — 仅地图配置变更时改变，保持前缀缓存稳定。"""
        if self._map is None:
            return ""
        self._merge_extensions()
        node = self._map.get_current_node()
        if not node:
            return ""
        root = self._map._get_root_node()
        if not root:
            return ""
        rendered = self._render_map_tree(root, node.id, 0)
        if not rendered:
            return ""
        return f"## 世界地图\n{rendered}"

    def get_location_detail_prompt(self) -> str:
        """当前位置详情 — 玩家移动即变，属于动态层。"""
        if self._map is None:
            return ""
        node = self._map.get_current_node()
        if not node:
            return ""
        parts = []
        parts.append("## 当前位置")
        breadcrumb = self._map.get_breadcrumb()
        parts.append(f"路径：{' > '.join(n.name for n in breadcrumb)}")

        hierarchy = self._map_config.get("hierarchy", [])
        depth = self._map.get_depth(node.id)
        if hierarchy and depth < len(hierarchy):
            parts.append(f"层级：{hierarchy[depth]}")

        if node.type:
            parts.append(f"类型：{node.type}")

        parts.append(f"描述：{node.description or '（暂无描述）'}")

        if node.parent_id and node.parent_id in self._map._nodes:
            parent = self._map._nodes[node.parent_id]
            parts.append(f"上级区域：{parent.name}")

        if node.parent_id:
            siblings = self._map.get_children(node.parent_id)
            sibling_names = [s.name for s in siblings if s.id != node.id]
            if sibling_names:
                parts.append(f"同级区域：{', '.join(sibling_names)}")

        children = self._map.get_children(node.id)
        if children:
            parts.append(f"子区域：{', '.join(c.name for c in children)}")

        connections = self._map.get_connections(node.id)
        if connections:
            parts.append(f"相邻区域：{', '.join(c.name for c in connections)}")

        # 从子节点中读取设施（已统一迁移为子节点）
        facility_children = self._map.get_facility_children(node.id)
        if facility_children:
            parts.append("\n## 设施")
            for fac_node in facility_children:
                fac_type = fac_node.type.replace("facility:", "") if fac_node.type.startswith("facility:") else fac_node.type
                parts.append(f"- {fac_node.name}（{fac_type}）：{fac_node.description or '（暂无描述）'}")

        nearby = self._get_nearby_locations(node)
        if nearby:
            scale = self._map_config.get("scale", 1)
            range_li = int(node.radius * self._map_config.get("visibility_multiplier", 4) * scale)
            parts.append(f"\n## 周边地点（{range_li}里内）")
            for name, direction, dist_li in nearby:
                parts.append(f"- {name}：{direction}，约{int(dist_li)}里")

        return "\n".join(parts)

    def get_system_prompt(self) -> str:
        return ""

    def _render_map_tree(self, node: MapNode, current_id: str, depth: int) -> str:
        """递归渲染地图树为缩进文本，☆ 标记当前位置，（）标注节点类型，* 标记设施"""
        indent = "    " * depth
        marker = " ☆" if node.id == current_id else ""
        # 设施节点用 * 前缀和简化类型标注
        if node.is_facility:
            fac_type = node.type.replace("facility:", "") if node.type.startswith("facility:") else ""
            type_label = f"（{fac_type}）" if fac_type else ""
            prefix = "*"
        else:
            type_label = f"（{node.type}）" if node.type else ""
            prefix = ""
        lines = [f"{indent}{'├── ' if depth > 0 else ''}{prefix}{node.name}{type_label}{marker}"]
        children = self._map.get_children(node.id)
        for child in children:
            lines.append(self._render_map_tree(child, current_id, depth + 1))
        return "\n".join(lines)

    def _get_nearby_locations(self, node: MapNode) -> list[tuple[str, str, float]]:
        """获取当前节点可视范围内的相邻叶子节点（名称、方位、距离）。"""
        if node.center is None:
            return []

        scale = self._map_config.get("scale", 1)
        multiplier = self._map_config.get("visibility_multiplier", 4)
        root_id = self._map.get_root_id()
        if not root_id:
            return []

        results = []
        for leaf in self._map.get_leaf_nodes(include_facilities=False):
            if leaf.id == node.id or leaf.center is None:
                continue
            leaf_root = self._map.get_root_of(leaf.id)
            if leaf_root != root_id:
                continue
            if not SpatialCalc.is_visible(node.center, node.radius, leaf.center, scale, multiplier):
                continue
            direction = SpatialCalc.bearing(node.center, leaf.center)
            dist_li = SpatialCalc.to_li(SpatialCalc.distance(node.center, leaf.center), scale)
            results.append((leaf.name, direction, dist_li))

        results.sort(key=lambda x: x[2])
        return results

    def _merge_extensions(self) -> None:
        """从 map/map_extensions.yaml 单文件加载扩展节点，合并到内存地图。"""
        if not self._map_dir or not self._map_dir.is_dir():
            return
        ext_path = self._map_dir / "map_extensions.yaml"
        if not ext_path.exists():
            # 兼容旧版：检测逐文件格式并迁移
            self._migrate_per_file_extensions()
            return
        try:
            with open(ext_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            nodes = data.get("nodes", [])
            if not nodes:
                return
            full_nodes = [n for n in nodes if "name" in n]
            # 迁移：将扩展节点中的 facilities 膨胀为子节点
            for ext_data in full_nodes[:]:  # 使用切片避免遍历时修改
                ext_facilities = ext_data.get("facilities")
                if not ext_facilities:
                    continue
                parent_id = ext_data.get("id", "")
                for fac in ext_facilities:
                    if isinstance(fac, str):
                        fac = {"name": fac, "type": fac, "description": ""}
                    if not isinstance(fac, dict) or "name" not in fac:
                        continue
                    fac_slug = self._map._generate_slug_id(fac["name"], prefix="facility_")
                    fac_type = fac.get("type", "")
                    fac_node_data = {
                        "id": fac_slug,
                        "name": fac["name"],
                        "description": fac.get("description", ""),
                        "parent_id": parent_id,
                        "type": f"facility:{fac_type}",
                        "center": None,
                        "radius": 0.0,
                        "children_ids": [],
                        "connection_ids": [],
                        "facilities": [],
                    }
                    # 如果扩展数据中已有同名节点，跳过
                    existing_names = {n.get("name") for n in full_nodes if n.get("id") != fac_slug}
                    if fac["name"] not in existing_names:
                        full_nodes.append(fac_node_data)
                # 清空该扩展节点的 facilities
                ext_data["facilities"] = []
            if full_nodes:
                self._map.merge_extensions({"nodes": full_nodes})
            logger.info("从 %s 加载了 %d 个扩展节点", ext_path, len(full_nodes))
        except Exception:
            logger.warning("加载地图扩展失败", exc_info=True)
        # 标记已执行，避免 load_own_state 重复调用
        self._merge_done = True

    def _save_map_extensions(self, new_nodes: list[dict]) -> None:
        """将所有扩展节点保存到 map/map_extensions.yaml 单文件（原子写入）。"""
        if not self._map_dir:
            return
        # 收集所有扩展节点（包括已有的和新增的）
        all_ext = self._map.get_extension_nodes()
        # 合并新节点（按 id 去重）
        existing_ids = {n["id"] for n in all_ext}
        for nd in new_nodes:
            if nd["id"] not in existing_ids:
                all_ext.append(nd)
        self._write_extensions_file(all_ext)
        logger.info(
            "已保存 %d 个地图扩展节点到 %s", len(all_ext), self._map_dir / "map_extensions.yaml"
        )

    def _migrate_per_file_extensions(self) -> None:
        """将旧版逐文件 {node_id}.yaml 格式迁移到单文件 map_extensions.yaml。"""
        if not self._map_dir or not self._map_dir.is_dir():
            return
        per_node_files = [
            p for p in self._map_dir.glob("*.yaml")
            if p.name != "map_extensions.yaml"
        ]
        if not per_node_files:
            return
        all_nodes: list[dict] = []
        for yaml_path in sorted(per_node_files):
            try:
                with open(yaml_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                if isinstance(data, dict) and "id" in data:
                    if "name" not in data:
                        logger.warning("跳过不完整的旧扩展文件 %s", yaml_path.name)
                        continue
                    all_nodes.append(data)
            except (yaml.YAMLError, OSError) as e:
                logger.warning("读取旧扩展文件 %s 失败: %s", yaml_path.name, e)
        if all_nodes:
            self._write_extensions_file(all_nodes)
            self._map.merge_extensions({"nodes": all_nodes})
            for f in per_node_files:
                f.unlink()
            logger.info("已迁移 %d 个旧版扩展文件到 map_extensions.yaml", len(all_nodes))

    def get_current_node(self) -> MapNode | None:
        if self._map is None:
            return None
        return self._map.get_current_node()

    def get_map(self) -> DefaultMap | None:
        return self._map

    def _handle_get_location_info(self, current_node_id: str = "") -> dict | None:
        """EventBus 处理器：返回当前位置信息，供 GameMaster.build_state() 使用。

        current_node_id: 指定要查询的节点 ID；为空则保持当前位置。
                         如果节点存在，会先导航到该节点再返回信息。
        """
        map_obj = self._map
        if map_obj is None:
            return None
        # 尝试导航到请求的节点（如果存在）
        if current_node_id:
            if current_node_id in map_obj._nodes:
                map_obj._current_node_id = current_node_id
            else:
                # 按名称模糊查找（支持 template 使用 location name 而非 id 的情况）
                for nid, n in map_obj._nodes.items():
                    if n.name == current_node_id:
                        map_obj._current_node_id = nid
                        break
        node = map_obj.get_current_node()
        if node is None:
            return None
        breadcrumb = [n.to_dict() for n in map_obj.get_breadcrumb()]
        info = {
            "current_node": node.to_dict(),
            "breadcrumb": breadcrumb,
            "children": [
                {"id": c.id, "name": c.name, "type": c.type}
                for c in map_obj.get_children(node.id)
            ],
            "connections": [
                {"id": c.id, "name": c.name, "type": c.type}
                for c in map_obj.get_connections(node.id)
            ],
            "current_node_id": map_obj.to_dict().get("current_node_id", ""),
        }
        # 从 CharacterManager.player.location 取值，与角色数据保持单一来源
        cm = getattr(self._world, '_char_manager', None) if self._world else None
        info["location"] = cm.player.location if cm and cm.player.location else ""
        if node.parent_id and node.parent_id in map_obj._nodes:
            parent_node = map_obj._nodes[node.parent_id]
            info["parent"] = {"id": parent_node.id, "name": parent_node.name, "type": parent_node.type}
        else:
            info["parent"] = None
        return info
