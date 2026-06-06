"""定价引擎协议 — 核心层与定价插件的解耦接口。"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PricingProtocol(Protocol):
    """定价引擎必须实现的接口。

    具体实现由 plugins.pricing.engine.PriceEngine 提供，
    核心层通过此协议引用，避免直接依赖插件包。
    """

    def calc_price(self, base_value: int, rarity: int) -> int: ...

    def calc_item_price(self, item: dict) -> int: ...
