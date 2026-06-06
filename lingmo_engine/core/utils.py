"""引擎通用工具函数。"""

import json
import logging
import os
import random
import string
import tempfile
from pathlib import Path

import yaml

_logger = logging.getLogger(__name__)


def generate_id(prefix: str) -> str:
    """生成唯一 ID：{prefix}_{12位随机小写字母数字}。

    Args:
        prefix: ID 前缀，如 "item"、"ability"、"qp"。

    Returns:
        格式为 "{prefix}_{12位随机小写字母数字}" 的字符串。
    """
    suffix = "".join(
        random.choices(string.ascii_lowercase + string.digits, k=12)
    )
    return f"{prefix}_{suffix}"


def find_entity(character_manager, entity_ref):
    """根据 ID 或名称查找角色。支持 "player"、整数 ID、角色名称。"""
    if not entity_ref:
        return None
    cm = character_manager
    if entity_ref == "player":
        return cm.player
    if isinstance(entity_ref, int):
        return cm.get(entity_ref)
    if isinstance(entity_ref, str) and entity_ref.isdigit():
        char = cm.get(int(entity_ref))
        if char:
            return char
    return next((c for c in cm.all() if c.name == entity_ref), None)


def add_item_to_character(character, item_id: str, quantity: int = 1):
    """给角色添加物品（堆叠已有条目）。"""
    if character.inventory is None:
        character.inventory = []
    for entry in character.inventory:
        if entry["item_id"] == item_id:
            entry["quantity"] += quantity
            return
    character.inventory.append({"item_id": item_id, "quantity": quantity})


def interpolate_table(level: int, table: dict) -> float:
    """从整键缩放表中查值，表外线性插值，空表返回 1.0。"""
    if not table:
        return 1.0
    val = table.get(level)
    if val is not None:
        return float(val)
    keys = sorted(table.keys())
    if not keys:
        return 1.0
    if level <= keys[0]:
        return float(table[keys[0]])
    if level >= keys[-1]:
        return float(table[keys[-1]])
    lo_k, hi_k = keys[0], keys[-1]
    for i, k in enumerate(keys):
        if k > level:
            hi_k = k
            lo_k = keys[i - 1] if i > 0 else keys[0]
            break
    frac = (level - lo_k) / (hi_k - lo_k)
    return float(table[lo_k]) + (float(table[hi_k]) - float(table[lo_k])) * frac


# ── 原子写入工具 ────────────────────────────────


def atomic_write_json(path: str | Path, data: dict, indent: int = 2) -> None:
    """原子写入 JSON 文件（tempfile + fsync + os.replace）。

    供插件 SelfPersistable.save_own_state 复用，避免手工复制
    mkstemp + fdopen + fsync + replace + 错误清理模板。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".json")
    fd_closed = False
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
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


def atomic_write_yaml(path: str | Path, data: dict) -> None:
    """原子写入 YAML 文件（tempfile + fsync + os.replace）。

    供插件 SelfPersistable.save_own_state 复用。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".yaml")
    fd_closed = False
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
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
