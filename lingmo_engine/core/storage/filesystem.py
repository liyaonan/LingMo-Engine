"""FileSystemBackend — 默认文件系统存储后端。

包装 Path/json/yaml/shutil/tempfile 操作，
实现 StorageBackend 协议的所有方法。
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


class FileSystemBackend:
    """默认文件系统后端 — 包装 Path/json/yaml/shutil 操作。

    所有路径参数为字符串，内部转换为 Path 处理。
    原子写入使用 tempfile + os.replace 模式，防止写入中断导致数据损坏。
    """

    def read_json(self, path: str) -> dict | None:
        """读取 JSON 文件，不存在返回 None。"""
        p = Path(path)
        if not p.exists():
            return None
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    def write_json(self, path: str, data: dict) -> None:
        """写入 JSON 文件。"""
        p = Path(path)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def atomic_write_json(self, path: str, data: dict) -> None:
        """原子写入 JSON 文件（临时文件 + os.replace）。"""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(suffix=".json", dir=str(p.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, str(p))
        except Exception:
            # 清理临时文件
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def read_yaml(self, path: str) -> dict | None:
        """读取 YAML 文件，不存在返回 None。"""
        p = Path(path)
        if not p.exists():
            return None
        with open(p, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def atomic_write_yaml(self, path: str, data: dict) -> None:
        """原子写入 YAML 文件。"""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(suffix=".yaml", dir=str(p.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False,
                          sort_keys=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, str(p))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def file_exists(self, path: str) -> bool:
        """检查文件是否存在。"""
        return Path(path).is_file()

    def dir_exists(self, path: str) -> bool:
        """检查目录是否存在。"""
        return Path(path).is_dir()

    def ensure_dir(self, path: str) -> None:
        """确保目录存在（递归创建）。"""
        Path(path).mkdir(parents=True, exist_ok=True)

    def list_dir(self, path: str) -> list[str]:
        """列出目录下的直接子项名称。"""
        p = Path(path)
        if not p.exists():
            return []
        return [item.name for item in p.iterdir()]

    def remove_tree(self, path: str) -> None:
        """递归删除目录树。"""
        p = Path(path)
        if p.exists():
            shutil.rmtree(str(p))

    def copy_tree(self, src: str, dst: str) -> None:
        """递归复制目录树。"""
        shutil.copytree(src, dst)
