"""地图子系统核心抽象 — MapNode, BaseMap, DefaultMap"""
from __future__ import annotations

import re as _re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from pypinyin import pinyin as _pinyin, Style as _Style


@dataclass
class MapNode:
    """地图树节点"""

    id: str
    name: str
    description: str = ""
    parent_id: Optional[str] = None
    children_ids: list[str] = field(default_factory=list)
    connection_ids: list[str] = field(default_factory=list)
    center: Optional[tuple[float, float]] = None
    radius: float = 0.0
    type: str = ""
    facilities: list[dict] = field(default_factory=list)  # 已废弃：设施统一迁移为子节点，运行时膨胀后清空
    qi_density: Optional[float] = None  # 节点灵气浓度，None 表示使用所属界的 base_qi_density

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "parent_id": self.parent_id,
            "children_ids": list(self.children_ids),
            "connection_ids": list(self.connection_ids),
            "center": list(self.center) if self.center is not None else None,
            "radius": self.radius,
            "type": self.type,
            "facilities": list(self.facilities),
            "qi_density": self.qi_density,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'MapNode':
        center_raw = data.get("center")
        center = tuple(center_raw) if center_raw is not None else None
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            parent_id=data.get("parent_id"),
            children_ids=list(data.get("children_ids", [])),
            connection_ids=list(data.get("connection_ids", [])),
            center=center,
            radius=float(data.get("radius", 0.0)),
            type=data.get("type", ""),
            facilities=list(data.get("facilities", [])),
            qi_density=data.get("qi_density"),
        )

    @property
    def is_facility(self) -> bool:
        """是否为设施节点（type 以 'facility:' 开头）。"""
        return self.type.startswith("facility:")


class BaseMap(ABC):
    """框架地图接口"""

    @abstractmethod
    def get_current_node(self) -> MapNode | None: ...

    @abstractmethod
    def get_breadcrumb(self) -> list[MapNode]: ...

    @abstractmethod
    def get_children(self, node_id: str) -> list[MapNode]: ...

    @abstractmethod
    def get_connections(self, node_id: str) -> list[MapNode]: ...

    @abstractmethod
    def move_to(self, node_id: str) -> dict: ...

    @abstractmethod
    def to_dict(self) -> dict: ...

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict) -> 'BaseMap': ...


class DefaultMap(BaseMap):
    """默认地图实现，支持 maps/ 目录多文件加载及旧版 map.yaml"""

    def __init__(self, nodes: list[MapNode] | None = None, start_node_id: str = ""):
        self._nodes: dict[str, MapNode] = {}
        self._extension_ids: set[str] = set()
        self._current_node_id: str = start_node_id
        self._start_node_id: str = start_node_id
        if nodes:
            for node in nodes:
                self._nodes[node.id] = node
            self._validate()

    def _validate(self) -> None:
        """校验树结构：父子双向对应、无孤立节点引用"""
        for node in self._nodes.values():
            for child_id in node.children_ids:
                if child_id not in self._nodes:
                    raise ValueError(f"节点 '{node.id}' 的子节点 '{child_id}' 不存在")
                child = self._nodes[child_id]
                if child.parent_id != node.id:
                    raise ValueError(
                        f"子节点 '{child_id}' 的 parent_id='{child.parent_id}' "
                        f"与节点 '{node.id}' 的 children_ids 不匹配"
                    )
            for conn_id in node.connection_ids:
                if conn_id not in self._nodes:
                    raise ValueError(f"节点 '{node.id}' 的相邻节点 '{conn_id}' 不存在")

    def get_current_node(self) -> MapNode | None:
        return self._nodes.get(self._current_node_id)

    def get_breadcrumb(self) -> list[MapNode]:
        result: list[MapNode] = []
        current_id = self._current_node_id
        visited = set()
        while current_id:
            if current_id in visited:
                break
            visited.add(current_id)
            node = self._nodes.get(current_id)
            if not node:
                break
            result.append(node)
            current_id = node.parent_id
        result.reverse()
        return result

    def get_children(self, node_id: str) -> list[MapNode]:
        node = self._nodes.get(node_id)
        if not node:
            return []
        return [self._nodes[cid] for cid in node.children_ids if cid in self._nodes]

    def get_facility_children(self, node_id: str) -> list[MapNode]:
        """返回指定节点的设施子节点（type 以 'facility:' 开头）。"""
        return [c for c in self.get_children(node_id) if c.is_facility]

    def get_area_children(self, node_id: str) -> list[MapNode]:
        """返回指定节点的区域子节点（非设施）。"""
        return [c for c in self.get_children(node_id) if not c.is_facility]

    def get_connections(self, node_id: str) -> list[MapNode]:
        node = self._nodes.get(node_id)
        if not node:
            return []
        return [self._nodes[cid] for cid in node.connection_ids if cid in self._nodes]

    def move_to(self, node_id: str) -> dict:
        if node_id not in self._nodes:
            return {
                "arrived": False,
                "error": f"节点 '{node_id}' 不存在",
            }
        self._current_node_id = node_id
        node = self._nodes[node_id]
        breadcrumb = self.get_breadcrumb()
        children = self.get_children(node_id)
        connections = self.get_connections(node_id)
        return {
            "arrived": True,
            "node": node.to_dict(),
            "breadcrumb": [n.to_dict() for n in breadcrumb],
            "children": [{"id": c.id, "name": c.name} for c in children],
            "connections": [{"id": c.id, "name": c.name} for c in connections],
        }

    def ensure_path(self, path: list[str]) -> dict:
        """按层级路径查找/创建节点 — 从后往前匹配最深层已有路径，剩余部分挂载为新分支。"""
        if not path:
            return {"arrived": False, "error": "路径为空"}

        root = self._get_root_node()
        if root and path[0] != root.name:
            return {"arrived": False, "error": f"路径根节点 '{path[0]}' 与地图根节点 '{root.name}' 不匹配"}

        # 从最长前缀开始，逐层缩短，找到最深的已有路径
        mount_depth = 0
        mount_node_id = None
        for depth in range(len(path), 0, -1):
            node = self._find_node_by_name_path(path[:depth])
            if node:
                mount_depth = depth
                mount_node_id = node.id
                break

        if mount_depth == 0:
            return {"arrived": False, "error": f"路径根节点 '{path[0]}' 不存在于地图中"}

        # 创建剩余的新节点
        new_nodes = []
        current_parent_id = mount_node_id
        for i in range(mount_depth, len(path)):
            # 检查父节点下是否已有同名子节点（避免重复创建）
            existing = self._find_child_by_name(current_parent_id, path[i])
            if existing:
                current_parent_id = existing.id
                continue
            new_id = self._generate_slug_id(path[i])
            new_node = MapNode(
                id=new_id,
                name=path[i],
                description="",
                parent_id=current_parent_id,
            )
            self._nodes[new_id] = new_node
            self._extension_ids.add(new_id)
            if current_parent_id in self._nodes:
                self._nodes[current_parent_id].children_ids.append(new_id)
            new_nodes.append(new_node.to_dict())
            current_parent_id = new_id

        self._current_node_id = current_parent_id
        node = self._nodes[current_parent_id]
        breadcrumb = self.get_breadcrumb()
        children = self.get_children(current_parent_id)
        connections = self.get_connections(current_parent_id)

        return {
            "arrived": True,
            "node": node.to_dict(),
            "breadcrumb": [n.to_dict() for n in breadcrumb],
            "children": [{"id": c.id, "name": c.name} for c in children],
            "connections": [{"id": c.id, "name": c.name} for c in connections],
            "new_nodes": new_nodes,
        }

    def _get_root_node(self) -> MapNode | None:
        for node in self._nodes.values():
            if node.parent_id is None:
                return node
        return None

    def _find_node_by_name_path(self, path_parts: list[str]) -> MapNode | None:
        """按名称路径逐层匹配节点。"""
        if not path_parts:
            return None
        # 找到匹配第一层的根节点
        current = None
        for node in self._nodes.values():
            if node.parent_id is None and node.name == path_parts[0]:
                current = node
                break
        if not current:
            return None
        for name in path_parts[1:]:
            children = self.get_children(current.id)
            found = None
            for child in children:
                if child.name == name:
                    found = child
                    break
            if not found:
                return None
            current = found
        return current

    def _find_child_by_name(self, parent_id: str | None, name: str) -> MapNode | None:
        parent = self._nodes.get(parent_id) if parent_id else None
        if parent_id and not parent:
            return None
        if parent_id is None:
            for node in self._nodes.values():
                if node.name == name:
                    return node
            return None
        for child_id in parent.children_ids:
            child = self._nodes.get(child_id)
            if child and child.name == name:
                return child
        return None

    _SLUG_RE = _re.compile(r'[^a-z0-9_]')

    def _generate_slug_id(self, name: str, prefix: str = "") -> str:
        """将中文名称转为拼音 slug ID，冲突时追加数字后缀。"""
        if not name or not name.strip():
            base = "location"
        else:
            parts = _pinyin(name.strip(), style=_Style.NORMAL)
            flat = "_".join(p[0] for p in parts if p[0])
            base = self._SLUG_RE.sub("", flat.lower()) or "location"
        if prefix:
            base = prefix + base

        if base not in self._nodes:
            return base
        n = 2
        while f"{base}_{n}" in self._nodes:
            n += 1
        return f"{base}_{n}"

    def sync_parent_child(self) -> None:
        """确保所有父子关系双向对应 — 子节点声明的 parent_id 自动回填到父节点的 children_ids"""
        import logging
        _logger = logging.getLogger(__name__)
        for node in self._nodes.values():
            if not node.parent_id:
                continue
            if node.parent_id in self._nodes:
                parent = self._nodes[node.parent_id]
                if node.id not in parent.children_ids:
                    parent.children_ids.append(node.id)
            else:
                _logger.warning(
                    "节点 '%s' 的 parent_id='%s' 指向不存在的节点，已跳过",
                    node.id, node.parent_id,
                )

    def merge_extensions(self, ext_data: dict) -> None:
        nodes_data = ext_data.get("nodes", [])
        for nd in nodes_data:
            node = MapNode.from_dict(nd)
            if node.id not in self._nodes:
                self._nodes[node.id] = node
                self._extension_ids.add(node.id)
        if nodes_data:
            self.sync_parent_child()
            self._validate()

    def get_extension_nodes(self) -> list[dict]:
        result = []
        for nid in self._extension_ids:
            if nid in self._nodes:
                result.append(self._nodes[nid].to_dict())
        return result

    def get_leaf_nodes(self, include_facilities: bool = True) -> list[MapNode]:
        """返回所有叶子节点（children_ids 为空的节点）。

        Args:
            include_facilities: 是否包含设施节点（type 以 'facility:' 开头）。
                               空间计算时应传 False 以排除无坐标的设施。
        """
        result = [n for n in self._nodes.values() if not n.children_ids]
        if not include_facilities:
            result = [n for n in result if not n.is_facility]
        return result

    def compute_intermediate_coords(self) -> None:
        """从叶子节点自动计算中间层坐标（包围盒中心）。仅计算 center 为 None 的非叶子节点。"""
        for node in self._nodes.values():
            if node.center is not None or not node.children_ids:
                continue
            leaves = self._collect_leaf_coords(node)
            if leaves:
                avg_x = sum(c[0] for c in leaves) / len(leaves)
                avg_y = sum(c[1] for c in leaves) / len(leaves)
                node.center = (avg_x, avg_y)

    def _collect_leaf_coords(self, node: MapNode) -> list[tuple[float, float]]:
        """递归收集节点下所有叶子节点的坐标。"""
        coords: list[tuple[float, float]] = []
        for cid in node.children_ids:
            child = self._nodes.get(cid)
            if not child:
                continue
            if not child.children_ids:
                if child.center is not None:
                    coords.append(child.center)
            else:
                coords.extend(self._collect_leaf_coords(child))
        return coords

    def get_root_of(self, node_id: str) -> str | None:
        """获取指定节点所在树的根节点 ID。"""
        current = node_id
        visited = set()
        while current:
            if current in visited:
                break
            visited.add(current)
            node = self._nodes.get(current)
            if not node or node.parent_id is None:
                return current
            current = node.parent_id
        return current or None

    def get_root_id(self) -> str | None:
        """获取当前节点所在树的根节点 ID。"""
        return self.get_root_of(self._current_node_id)

    def get_depth(self, node_id: str) -> int:
        """获取节点深度（根节点=0）。"""
        depth = 0
        current = node_id
        visited = set()
        while current:
            if current in visited:
                break
            visited.add(current)
            node = self._nodes.get(current)
            if not node or node.parent_id is None:
                break
            current = node.parent_id
            depth += 1
        return depth

    def to_dict(self) -> dict:
        return {
            "current_node_id": self._current_node_id,
            "start_node_id": self._start_node_id,
            "nodes": {nid: node.to_dict() for nid, node in self._nodes.items()},
            "extension_ids": list(self._extension_ids),
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'DefaultMap':
        nodes_data = data.get("nodes", {})
        nodes = [MapNode.from_dict(n) for n in nodes_data.values()]
        instance = cls(nodes=nodes, start_node_id=data.get("start_node_id", ""))
        instance._current_node_id = data.get("current_node_id", instance._start_node_id)
        instance._extension_ids = set(data.get("extension_ids", []))
        return instance


__all__ = ["MapNode", "BaseMap", "DefaultMap"]
