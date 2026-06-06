"""存档版本管理 — 版本号常量 + 迁移注册表。

v0 = 无版本号的旧存档（2026-05-30 之前的所有存档）。
每项迁移是纯函数 dict -> dict，从旧版本升级到下一版本。
"""
from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)

# 当前存档格式版本
CURRENT_SAVE_VERSION: int = 1

# 迁移注册表：from_version -> 迁移函数
_MIGRATIONS: dict[int, Callable[[dict], dict]] = {}


def register_migration(from_version: int):
    """装饰器：注册从 from_version 到 from_version+1 的迁移函数。

    迁移函数签名为 (data: dict) -> dict，应返回修改后的数据。
    """
    def decorator(fn: Callable[[dict], dict]) -> Callable[[dict], dict]:
        if from_version in _MIGRATIONS:
            raise ValueError(f"迁移 {from_version} -> {from_version + 1} 已注册")
        _MIGRATIONS[from_version] = fn
        return fn
    return decorator


def run_migrations(data: dict) -> dict:
    """按顺序运行迁移链：从 data 中的版本升级到 CURRENT_SAVE_VERSION。

    如果 data 中无 save_version 字段，视为 v0（旧存档）。
    """
    version = data.get("save_version", 0)
    if version > CURRENT_SAVE_VERSION:
        logger.warning(
            "存档版本 %d 高于引擎版本 %d，可能由更高版本引擎创建",
            version, CURRENT_SAVE_VERSION,
        )
        return data
    while version < CURRENT_SAVE_VERSION:
        migration = _MIGRATIONS.get(version)
        if migration is None:
            logger.info("无迁移函数 v%d -> v%d，直接升级版本号", version, version + 1)
        else:
            logger.info("运行存档迁移: v%d -> v%d", version, version + 1)
            data = migration(data)
        data["save_version"] = version + 1
        version += 1
    return data
