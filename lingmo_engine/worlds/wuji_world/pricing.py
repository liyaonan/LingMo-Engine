"""无极世界定价公式。读取 pricing.yaml，提供世界级便捷函数。"""
from __future__ import annotations

from pathlib import Path

import yaml

from lingmo_engine.plugins.pricing.engine import PriceEngine

_engine: PriceEngine | None = None


def _load_config() -> dict:
    """加载 pricing.yaml 配置。"""
    config_path = Path(__file__).resolve().parent / "pricing.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("pricing", {})
    return {}


def get_price_engine() -> PriceEngine:
    """懒加载定价引擎（读取 pricing.yaml）。"""
    global _engine
    if _engine is None:
        _engine = PriceEngine(_load_config())
    return _engine


def calc_price(spirit_power: int, rarity: int) -> int:
    """便捷函数：直接计算无极世界物品价格。"""
    return get_price_engine().calc_price(spirit_power, rarity)