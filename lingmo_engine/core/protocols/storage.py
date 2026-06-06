"""存储后端抽象 — 解耦 GameState/SaveManager 与文件系统。

支持未来替换为数据库、云存储等后端，只需实现此协议。
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable, Any


@runtime_checkable
class StorageBackend(Protocol):
    """存储后端接口 — 所有文件 I/O 操作的统一抽象。

    默认实现为 FileSystemBackend（包装 Path/json/yaml/shutil 操作）。
    替换后端只需实现此协议即可，GameState/SaveManager 无需修改。
    """

    def read_json(self, path: str) -> dict | None:
        """读取 JSON 文件，不存在返回 None。"""
        ...

    def write_json(self, path: str, data: dict) -> None:
        """写入 JSON 文件。"""
        ...

    def atomic_write_json(self, path: str, data: dict) -> None:
        """原子写入 JSON 文件（先写临时文件再替换，防止写入中断导致数据丢失）。"""
        ...

    def read_yaml(self, path: str) -> dict | None:
        """读取 YAML 文件，不存在返回 None。"""
        ...

    def atomic_write_yaml(self, path: str, data: dict) -> None:
        """原子写入 YAML 文件。"""
        ...

    def file_exists(self, path: str) -> bool:
        """检查文件是否存在。"""
        ...

    def dir_exists(self, path: str) -> bool:
        """检查目录是否存在。"""
        ...

    def ensure_dir(self, path: str) -> None:
        """确保目录存在（递归创建）。"""
        ...

    def list_dir(self, path: str) -> list[str]:
        """列出目录下的直接子项名称。"""
        ...

    def remove_tree(self, path: str) -> None:
        """递归删除目录树。"""
        ...

    def copy_tree(self, src: str, dst: str) -> None:
        """递归复制目录树。"""
        ...
