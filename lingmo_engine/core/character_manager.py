"""角色统一管理器 — 角色数据的唯一来源。"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

import yaml

from lingmo_engine.core.character import Character, CharacterType
from lingmo_engine.core.events import PluginEvent

logger = logging.getLogger(__name__)

# NPC 数量超过此阈值时自动切换到批量存储模式
_NPC_BATCH_THRESHOLD = 20


class CharacterManager:
    """角色数据的唯一来源。管理所有 Character 实例的加载、查询、状态变更。"""

    def __init__(self):
        self._characters: dict[int, Character] = {}
        self._event_bus = None
        self._attributes_schema: dict | None = None
        self._dirty: set[int] = set()  # 脏标记：仅脏角色需要写入磁盘
        self._location_resolver = None  # location 标准化回调（由 MapPlugin 注入）

    def set_event_bus(self, bus) -> None:
        self._event_bus = bus

    # ── 加载 ──

    def load(self, directory: str | Path) -> None:
        """加载 characters/fixed/ 目录下所有 YAML 文件。"""
        directory = Path(directory)
        if not directory.exists():
            logger.warning("Character directory not found: %s", directory)
            return
        for yaml_path in sorted(directory.glob("*.yaml")):
            self._load_file(yaml_path)

    def _load_file(self, path: Path) -> None:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or []
        if isinstance(data, list):
            characters = data
        elif isinstance(data, dict) and "characters" in data:
            characters = data["characters"]
        elif isinstance(data, dict) and "id" in data:
            # 单角色 dict 格式（NPC 独立文件）
            characters = [data]
        else:
            characters = []
        for entry in characters:
            c = Character.from_dict(entry)
            self._characters[c.id] = c
            self._dirty.discard(c.id)
            logger.debug("Loaded character: id=%d name=%s type=%s", c.id, c.name, c.char_type.value)

    # ── 查询 ──

    @property
    def player(self) -> Character:
        """返回主角（id=0 的角色）。未加载时抛出 RuntimeError。"""
        if 0 not in self._characters:
            raise RuntimeError(
                "主角未加载：characters/fixed/ 目录中缺少 id=0 的角色。"
                "请确保 characters.yaml 中包含 id: 0 的角色条目。"
            )
        return self._characters[0]

    def get(self, id: int) -> Character | None:
        return self._characters.get(id)

    def all(self) -> list[Character]:
        return list(self._characters.values())

    def list_by_location(self, location: str) -> list[Character]:
        if self._location_resolver:
            location = self._location_resolver(location)
        return [c for c in self._characters.values() if c.location == location]

    def list_by_type(self, char_type: CharacterType) -> list[Character]:
        return [c for c in self._characters.values() if c.char_type == char_type]

    def list_by_faction(self, faction: str) -> list[Character]:
        return [c for c in self._characters.values() if c.faction == faction]

    def count(self) -> int:
        return len(self._characters)

    # ── NPC 文件管理 ──

    def load_npc_dir(self, directory: str | Path) -> None:
        """从存档目录的 npcs/ 子目录加载 NPC YAML 文件。

        支持两种模式：
        - 逐文件模式（默认）: npc_0.yaml, npc_1.yaml, ...
        - 批量模式: npcs_batch.yaml（单文件包含所有 NPC 列表）
        优先检查批量文件，不存在时 fallback 到逐文件扫描。
        """
        directory = Path(directory)
        if not directory.exists():
            return
        # 优先检查批量文件（注意：批量模式存在时，孤立 npc_*.yaml 文件会被忽略）
        batch_file = directory / "npcs_batch.yaml"
        if batch_file.exists():
            self._load_file(batch_file)
            logger.info("从批量文件加载 NPC: %s", batch_file)
            return
        # fallback 到逐文件模式
        for yaml_path in sorted(directory.glob("npc_*.yaml")):
            self._load_file(yaml_path)

    def save_npc_file(self, character: Character, npc_dir: str | Path) -> None:
        """将角色序列化到独立 YAML 文件（原子写入）。写入成功后清除脏标记。"""
        import os
        import tempfile
        npc_dir = Path(npc_dir)
        npc_dir.mkdir(parents=True, exist_ok=True)
        path = npc_dir / f"npc_{character.id}.yaml"
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(npc_dir), suffix=".yaml")
        fd_closed = False
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                yaml.dump(character.to_dict(), f, allow_unicode=True, default_flow_style=False)
                f.flush()
                os.fsync(f.fileno())
            fd_closed = True
            os.replace(tmp_path, str(path))
        except Exception:
            if not fd_closed:
                try:
                    os.close(tmp_fd)
                except OSError:
                    pass
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        self._dirty.discard(character.id)
        logger.info("NPC 文件已保存: %s", path)

    def delete_npc_file(self, char_id: int, npc_dir: str | Path) -> None:
        """删除 NPC 的持久化文件。"""
        path = Path(npc_dir) / f"npc_{char_id}.yaml"
        if path.exists():
            path.unlink()
            logger.info("NPC 文件已删除: %s", path)

    def save_all(self, npc_dir: str | Path) -> None:
        """将脏角色持久化到 npcs/ 目录。

        NPC 数量超过 _NPC_BATCH_THRESHOLD 时自动切换到批量模式
        （写入单个 npcs_batch.yaml 替代逐文件）。
        """
        # 主角始终纳入保存集合
        to_save = set(self._dirty)
        if 0 in self._characters:
            to_save.add(0)
        if not to_save:
            return

        npc_dir = Path(npc_dir)
        npc_dir.mkdir(parents=True, exist_ok=True)
        total_count = len(self._characters)

        if total_count > _NPC_BATCH_THRESHOLD:
            # 批量模式：全量写入 npcs_batch.yaml
            self._save_batch(npc_dir, to_save)
        else:
            # 逐文件模式：先写所有脏角色，再清理批量文件（避免写入失败时丢失数据）
            for cid in list(to_save):
                c = self._characters.get(cid)
                if c is not None:
                    self.save_npc_file(c, npc_dir)
            # 所有逐文件写入成功后，清理残留的批量文件
            batch_file = npc_dir / "npcs_batch.yaml"
            if batch_file.exists():
                batch_file.unlink()
                logger.info("NPC 数量低于阈值，已清理批量文件")

    def _save_batch(self, npc_dir: Path, dirty_ids: set[int]) -> None:
        """将所有角色写入单个 npcs_batch.yaml（原子写入）。"""
        # 只要有脏角色就全量重写 batch 文件
        if not dirty_ids:
            return
        all_chars = [c.to_dict() for c in self._characters.values()]
        batch_path = npc_dir / "npcs_batch.yaml"
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(npc_dir), suffix=".yaml")
        fd_closed = False
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                yaml.dump(all_chars, f, allow_unicode=True, default_flow_style=False)
                f.flush()
                os.fsync(f.fileno())
            fd_closed = True
            os.replace(tmp_path, str(batch_path))
        except Exception:
            if not fd_closed:
                try:
                    os.close(tmp_fd)
                except OSError:
                    pass
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        # 批量模式下清理旧的逐文件
        for old_file in npc_dir.glob("npc_*.yaml"):
            old_file.unlink()
        self._dirty.clear()
        logger.info("NPC 批量保存完成: %d 个角色 → %s", len(all_chars), batch_path)

    # ── 状态变更 ──

    def update_attr(self, id: int, key: str, delta: int) -> None:
        c = self._characters.get(id)
        if c is None:
            return
        if key not in c.attrs:
            c.attrs[key] = 0
        c.attrs[key] += delta
        self._dirty.add(id)
        self._emit_update(id, key, c.attrs[key])

    def set_attr(self, id: int, key: str, value: int) -> None:
        c = self._characters.get(id)
        if c is None:
            return
        c.attrs[key] = value
        self._dirty.add(id)
        self._emit_update(id, key, value)

    def update_character_attrs(self, char_id: int, updates: dict) -> None:
        """受控修改角色属性，替代直接 get() → modify 的模式。"""
        char = self.get(char_id)
        if char is None:
            return
        for key, value in updates.items():
            setattr(char, key, value)
        # 发送一次综合更新通知（key/value 使用占位符表示批量更新）
        self._emit_update(char_id, "", 0)

    def add_character(self, character: Character) -> None:
        """添加新角色到管理器。如果 ID 已存在则覆盖。"""
        self._characters[character.id] = character
        self._dirty.add(character.id)
        logger.info("CharacterManager: 添加角色 id=%d name=%s type=%s",
                    character.id, character.name, character.char_type.value)

    def remove_character(self, id: int) -> bool:
        """移除角色。成功返回 True，角色不存在返回 False。"""
        if id in self._characters:
            name = self._characters[id].name
            del self._characters[id]
            self._dirty.discard(id)
            logger.info("CharacterManager: 移除角色 id=%d name=%s", id, name)
            return True
        return False

    def clear_all(self) -> None:
        """清空所有角色和脏标记（用于加载存档前的全量替换）。"""
        self._characters.clear()
        self._dirty.clear()

    def validate_after_load(self) -> list[str]:
        """加载存档后校验角色数据，检测并移除幽灵/重复角色。

        规则：
        1. 同名角色（非 player）保留 ID 较小的，移除较大的
        2. 记录所有被移除角色的日志

        Returns:
            被移除角色的描述列表
        """
        removed: list[str] = []

        # 按名称分组，找出重复
        name_groups: dict[str, list[int]] = {}
        for cid, c in self._characters.items():
            name = c.name
            if name not in name_groups:
                name_groups[name] = []
            name_groups[name].append(cid)

        for name, ids in name_groups.items():
            if len(ids) <= 1:
                continue
            # player 不参与去重
            sorted_ids = sorted(ids)
            keeper = sorted_ids[0]
            for dup_id in sorted_ids[1:]:
                dup = self._characters[dup_id]
                if getattr(dup, "char_type", None) and dup.char_type.value == "player":
                    continue
                desc = f"id={dup_id} name={name}（保留 id={keeper}）"
                removed.append(desc)
                logger.warning(
                    "检测到重复角色 %s，移除 id=%d，保留 id=%d",
                    name, dup_id, keeper,
                )

        # 批量移除重复角色（避免遍历中修改字典）
        for name, ids in name_groups.items():
            if len(ids) <= 1:
                continue
            sorted_ids = sorted(ids)
            for dup_id in sorted_ids[1:]:
                if dup_id in self._characters:
                    dup = self._characters[dup_id]
                    if getattr(dup, "char_type", None) and dup.char_type.value == "player":
                        continue
                    del self._characters[dup_id]
                    self._dirty.discard(dup_id)

        return removed

    def cleanup_temporary(self, ids: list[int]) -> list[int]:
        """清理指定 ID 列表中的临时角色。返回被移除的 ID 列表。"""
        removed = []
        for cid in ids:
            c = self._characters.get(cid)
            if c is not None and getattr(c, "temporary", False):
                del self._characters[cid]
                self._dirty.discard(cid)
                removed.append(cid)
                logger.info("清理临时角色: id=%d name=%s", cid, c.name)
        return removed

    def get_next_id(self) -> int:
        """返回下一个可用角色 ID（当前最大整数 ID + 1）。"""
        if not self._characters:
            return 1  # 0 预留给主角
        int_ids = [k for k in self._characters.keys() if isinstance(k, int)]
        if not int_ids:
            return 1
        return max(int_ids) + 1

    def update_location(self, id: int, new_location: str) -> None:
        c = self._characters.get(id)
        if c:
            if self._location_resolver:
                new_location = self._location_resolver(new_location)
            c.location = new_location
            self._dirty.add(id)

    def set_location_resolver(self, resolver) -> None:
        """设置 location 标准化回调（由 MapPlugin 注入）。"""
        self._location_resolver = resolver

    def update_relationship(
        self, character_id: int, target_id: int, action: str,
        label: str = "", desc: str = "",
        valid_labels: list[str] | None = None,
    ) -> dict:
        """管理角色间的关系。

        Args:
            character_id: 要修改哪个角色的关系
            target_id: 关系对象的角色 ID
            action: "add" / "remove" / "change"
            label: 关系标签（add/change 时必填）
            desc: 关系来源描述，≤30 字
            valid_labels: 合法标签集，为 None 时不校验

        Returns:
            {"success": bool, "message": str}
        """
        c = self._characters.get(character_id)
        if c is None:
            return {"success": False, "message": f"角色 id={character_id} 不存在"}

        if action in ("add", "change"):
            if not label:
                return {"success": False, "message": "label 为必填参数"}
            if valid_labels and label not in valid_labels:
                return {
                    "success": False,
                    "message": f"标签 '{label}' 不合法。合法标签: {', '.join(valid_labels)}",
                }
            if len(desc) > 30:
                desc = desc[:30]

        existing = [r for r in c.relationships if r.get("target_id") == target_id]

        if action == "add":
            if existing:
                return {
                    "success": False,
                    "message": f"与 id={target_id} 的关系已存在，请使用 change 变更",
                }
            target = self._characters.get(target_id)
            if target is None:
                return {"success": False, "message": f"目标角色 id={target_id} 不存在"}
            c.relationships.append({
                "target_id": target_id,
                "label": label,
                "desc": desc,
            })
            self._dirty.add(character_id)
            return {"success": True, "message": f"已建立与 {target.name} 的关系: {label}"}

        if action == "remove":
            if not existing:
                return {"success": False, "message": f"与 id={target_id} 无关系记录"}
            c.relationships = [
                r for r in c.relationships if r.get("target_id") != target_id
            ]
            self._dirty.add(character_id)
            return {"success": True, "message": f"已移除与 id={target_id} 的关系"}

        if action == "change":
            if not existing:
                return {"success": False, "message": f"与 id={target_id} 无关系记录，请先 add"}
            existing[0]["label"] = label
            if desc:
                existing[0]["desc"] = desc
            self._dirty.add(character_id)
            return {"success": True, "message": f"已变更为: {label}"}

        return {"success": False, "message": f"未知操作: {action}，请使用 add/remove/change"}

    def get_relationships_text(
        self, character_id: int, target_id: int | None = None,
    ) -> str:
        """生成关系描述文本，供 prompt 注入和 query 工具使用。"""
        c = self._characters.get(character_id)
        if c is None:
            return f"角色 id={character_id} 不存在"
        if not c.relationships:
            return f"角色 \"{c.name}\"({character_id}) 暂无关系记录"

        if target_id is not None:
            rel = next(
                (r for r in c.relationships if r.get("target_id") == target_id), None,
            )
            other = self._characters.get(target_id)
            other_name = other.name if other else f"id={target_id}"
            if rel is None:
                return f"与 {other_name}({target_id}) 无关系记录"
            desc_part = f" — {rel['desc']}" if rel.get("desc") else ""
            return f"{other_name}({target_id}): {rel['label']}{desc_part}"

        lines = [f"角色 \"{c.name}\"({character_id})的关系："]
        for rel in c.relationships:
            tid = rel.get("target_id")
            other = self._characters.get(tid)
            other_name = other.name if other else f"id={tid}"
            desc_part = f" — {rel['desc']}" if rel.get("desc") else ""
            lines.append(f"- {other_name}({tid}): {rel['label']}{desc_part}")
        lines.append(f"（共{len(c.relationships)}段关系）")
        return "\n".join(lines)

    def update_affairs(self, id: int, affairs: list[str]) -> None:
        c = self._characters.get(id)
        if c:
            c.current_affairs = list(affairs)
            self._dirty.add(id)

    def mark_dirty(self, id: int) -> None:
        """手动标记指定角色为脏。供插件在直接修改 Character 字段后调用。"""
        if id in self._characters:
            self._dirty.add(id)

    def _emit_update(self, id: int, key: str, value: int) -> None:
        if self._event_bus:
            try:
                self._event_bus.emit(
                    PluginEvent.CHARACTER_UPDATED,
                    {"id": id, "key": key, "value": value},
                )
            except Exception:
                logger.warning(
                    "Failed to emit CHARACTER_UPDATED for id=%d key=%s",
                    id, key, exc_info=True,
                )

    def get_attributes_schema(self) -> dict | None:
        return self._attributes_schema

    def set_attributes_schema(self, schema: dict) -> None:
        self._attributes_schema = schema
