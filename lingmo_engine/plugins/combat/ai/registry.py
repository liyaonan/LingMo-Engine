"""AI策略注册表"""

from typing import Optional
from lingmo_engine.plugins.combat.ai import EnemyAIStrategy
from lingmo_engine.plugins.combat.ai.default import DefaultAIStrategy


class AIStrategyRegistry:
    """AI策略注册表，管理内置和世界自定义策略"""

    def __init__(self):
        self._strategies: dict[str, EnemyAIStrategy] = {
            "default": DefaultAIStrategy(),
        }

    def register(self, name: str, strategy: EnemyAIStrategy) -> None:
        """注册自定义策略"""
        self._strategies[name] = strategy

    def get(self, name: str) -> EnemyAIStrategy:
        """获取策略，未找到时返回默认策略"""
        return self._strategies.get(name, self._strategies["default"])

    def get_default(self) -> EnemyAIStrategy:
        """获取默认策略"""
        return self._strategies["default"]
