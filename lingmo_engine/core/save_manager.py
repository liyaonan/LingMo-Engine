"""SaveManager — 存档槽位管理，路径解析与 CRUD。"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_FORBIDDEN_CHARS = str.maketrans({c: "_" for c in '<>:"/\\|?*'})


def sanitize_slot_id(slot_id: str) -> str:
    """将 slot_id 转换为安全的目录名。保留原始名称在 meta.json 中。"""
    name = slot_id.strip().rstrip(".").lstrip(".")
    name = name.translate(_FORBIDDEN_CHARS)
    return name or "unnamed"


def extract_world_name(config_world: str) -> str:
    """从 config.world 路径中提取世界名（最后一段）。"""
    return Path(config_world).name


class SaveManager:
    """存档槽位管理器。"""

    def __init__(self, save_dir: Path, world_name: str) -> None:
        self._save_dir = save_dir
        self._world_name = world_name

    @property
    def world_dir(self) -> Path:
        return self._save_dir / self._world_name

    def resolve_slot_path(self, slot_id: str) -> Path:
        return self.world_dir / sanitize_slot_id(slot_id)

    def read_meta(self, slot_id: str) -> dict:
        """读取 slot meta.json，不存在返回 {}"""
        path = self.resolve_slot_path(slot_id) / "meta.json"
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def write_meta(self, slot_id: str, meta: dict) -> None:
        """原子写入 meta.json"""
        slot_dir = self.resolve_slot_path(slot_id)
        slot_dir.mkdir(parents=True, exist_ok=True)
        meta.setdefault("slot_id", slot_id)
        meta.setdefault("world_name", self._world_name)
        meta["updated_at"] = datetime.now(timezone.utc).isoformat()
        path = slot_dir / "meta.json"
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(slot_dir))
        fd_closed = False
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
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

    def update_meta(self, slot_id: str, **kwargs) -> None:
        meta = self.read_meta(slot_id)
        meta.update(kwargs)
        self.write_meta(slot_id, meta)

    def list_saves(self) -> list[dict]:
        """列出所有槽位摘要，按 updated_at 降序"""
        if not self.world_dir.exists():
            return []
        results = []
        for d in self.world_dir.iterdir():
            if not d.is_dir():
                continue
            meta = self.read_meta(d.name)
            if not meta:
                continue
            is_autosave = d.name.startswith("autosave")
            results.append({
                "slot_id": meta.get("slot_id", d.name),
                "player_name": meta.get("player_name", ""),
                "level": meta.get("player_level", 1),
                "location": meta.get("location", ""),
                "updated_at": meta.get("updated_at", ""),
                "is_autosave": is_autosave,
            })
        results.sort(key=lambda s: s["updated_at"], reverse=True)
        return results

    def slot_exists(self, slot_id: str) -> bool:
        return self.resolve_slot_path(slot_id).exists()

    def delete_slot(self, slot_id: str) -> bool:
        if slot_id.startswith("autosave"):
            logger.warning("Cannot delete autosave slot: %s", slot_id)
            return False
        slot_dir = self.resolve_slot_path(slot_id)
        if not slot_dir.exists():
            return False
        shutil.rmtree(slot_dir)
        logger.info("Slot deleted: %s", slot_id)
        return True

    def rename_slot(self, old_slot_id: str, new_slot_id: str) -> bool:
        if old_slot_id.startswith("autosave"):
            return False
        old_dir = self.resolve_slot_path(old_slot_id)
        new_dir = self.resolve_slot_path(new_slot_id)
        if not old_dir.exists() or new_dir.exists():
            return False
        old_dir.rename(new_dir)
        # 更新 meta 中的 slot_id（注意：update_meta 的 slot_id 是位置参数，不能作为 kwargs 传入）
        meta = self.read_meta(new_slot_id)
        if meta:
            meta["slot_id"] = new_slot_id
            self.write_meta(new_slot_id, meta)
        logger.info("Slot renamed: %s -> %s", old_slot_id, new_slot_id)
        return True

    def ensure_slot_dir(self, slot_id: str) -> Path:
        """Ensure slot directory and subdirectories exist, return slot dir path"""
        slot_dir = self.resolve_slot_path(slot_id)
        slot_dir.mkdir(parents=True, exist_ok=True)
        (slot_dir / "messages").mkdir(exist_ok=True)
        (slot_dir / "memory" / "long_term").mkdir(parents=True, exist_ok=True)
        (slot_dir / "memory" / "characters").mkdir(parents=True, exist_ok=True)
        (slot_dir / "npcs").mkdir(exist_ok=True)
        (slot_dir / "event").mkdir(parents=True, exist_ok=True)
        return slot_dir

    def export_slot(self, slot_id: str) -> Path:
        """Pack slot directory into ZIP, return ZIP path"""
        slot_dir = self.resolve_slot_path(slot_id)
        if not slot_dir.exists():
            raise FileNotFoundError(f"Slot not found: {slot_id}")
        zip_name = f"{self._world_name}_{sanitize_slot_id(slot_id)}_{datetime.now().strftime('%Y%m%d')}"
        zip_path = self._save_dir / zip_name
        shutil.make_archive(
            str(zip_path), "zip",
            root_dir=str(slot_dir.parent), base_dir=slot_dir.name,
        )
        logger.info("Slot exported: %s -> %s", slot_id, zip_path.with_suffix(".zip"))
        return zip_path.with_suffix(".zip")

    def import_slot(self, zip_data: bytes) -> dict:
        """Import from ZIP bytes. Returns {'slot_id', 'meta'}.

        Validates meta.json + state.json exist. Handles slot_id conflicts by appending suffix.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_zip = Path(tmp) / "import.zip"
            tmp_zip.write_bytes(zip_data)
            extract_dir = Path(tmp) / "extract"
            extract_dir.mkdir()
            with zipfile.ZipFile(tmp_zip, "r") as zf:
                # Zip Slip 防护：校验所有成员路径不越界
                for member in zf.infolist():
                    member_path = (extract_dir / member.filename).resolve()
                    try:
                        member_path.relative_to(extract_dir.resolve())
                    except ValueError:
                        raise ValueError(f"非法 ZIP 路径: {member.filename}")
                zf.extractall(extract_dir)

            meta_path = self._find_file(extract_dir, "meta.json")
            if meta_path is None:
                raise ValueError("无效的存档文件：缺少 meta.json")
            state_path = self._find_file(extract_dir, "state.json")
            if state_path is None:
                raise ValueError("存档文件损坏：缺少 state.json")

            root = meta_path.parent
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            slot_id = meta.get("slot_id", "imported")

            if self.slot_exists(slot_id):
                base = f"{slot_id}_导入"
                slot_id = base
                i = 1
                while self.slot_exists(slot_id):
                    slot_id = f"{base}_{i}"
                    i += 1

            (root / "messages").mkdir(exist_ok=True)

            dest = self.resolve_slot_path(slot_id)
            shutil.copytree(root, dest)
            self.write_meta(slot_id, {**meta, "slot_id": slot_id})

        logger.info("Slot imported: %s", slot_id)
        return {"slot_id": slot_id, "meta": self.read_meta(slot_id)}

    @staticmethod
    def _find_file(root: Path, filename: str) -> Path | None:
        candidate = root / filename
        if candidate.exists():
            return candidate
        for p in root.rglob(filename):
            return p
        return None

    def verify_slot(self, slot_id: str) -> dict:
        """验证槽位完整性，检查必需文件是否存在且可解析。

        TODO: 集成到 import_slot 和 _handle_load_save 中提供用户可见的校验。
        返回:
            {"valid": bool, "errors": list[str]} — 错误列表为空表示通过。
        """
        errors: list[str] = []
        slot_dir = self.resolve_slot_path(slot_id)

        if not slot_dir.exists():
            return {"valid": False, "errors": [f"槽位目录不存在: {slot_id}"]}

        # 检查 meta.json
        meta_path = slot_dir / "meta.json"
        if not meta_path.exists():
            errors.append("meta.json 缺失")
        else:
            try:
                json.loads(meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                errors.append(f"meta.json 解析失败: {e}")

        # 检查 state.json
        state_path = slot_dir / "state.json"
        if not state_path.exists():
            errors.append("state.json 缺失")
        else:
            try:
                json.loads(state_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                errors.append(f"state.json 解析失败: {e}")

        # 检查 npcs 目录
        npcs_dir = slot_dir / "npcs"
        if not npcs_dir.exists():
            errors.append("npcs/ 目录缺失")
        else:
            npc_files = list(npcs_dir.glob("npc_*.yaml"))
            batch_file = npcs_dir / "npcs_batch.yaml"
            if not npc_files and not batch_file.exists():
                    errors.append("npcs/ 目录下无角色文件")

        return {"valid": len(errors) == 0, "errors": errors}
