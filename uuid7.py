"""UUID v7 模块 — RFC 9562 时间排序唯一标识符的纯标准库实现。"""
import os
import time
import uuid


def uuid7() -> uuid.UUID:
    """生成 UUID v7（时间排序全局唯一标识符）。

    格式（128 位）：
    - 48 位 Unix 毫秒时间戳
    - 4  位版本号 (0x7)
    - 12 位 rand_a
    - 2  位变体 (0b10)
    - 62 位 rand_b
    """
    timestamp_ms = int(time.time() * 1000)
    rand = int.from_bytes(os.urandom(10), 'big')
    rand_a = (rand >> 68) & 0xFFF   # 12 位
    rand_b = rand & ((1 << 62) - 1)  # 62 位

    # 编码为 16 字节
    ts_bytes = timestamp_ms.to_bytes(6, 'big')
    ver_rand_a = (0x7 << 12) | rand_a
    var_rand_b = (0x2 << 62) | rand_b

    return uuid.UUID(bytes=(
        ts_bytes
        + ver_rand_a.to_bytes(2, 'big')
        + var_rand_b.to_bytes(8, 'big')
    ))
