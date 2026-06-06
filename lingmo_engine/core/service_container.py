"""ServiceContainer — 轻量服务容器，按名称注册/解析单例服务。

设计原则：
- 最小化：字典 + 懒工厂 + 单例缓存
- 不做装饰器、不做自动装配、不做依赖图分析
- 通过闭包捕获依赖，保持 GameMaster 现有调用模式不变

用法:
    container = ServiceContainer()
    container.register("llm_handler", lambda: LLMHandler(provider))
    handler = container.resolve("llm_handler")  # 首次调用工厂，之后返回缓存
"""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ServiceContainer:
    """轻量服务容器 — 集中注册和延迟构造单例服务。"""

    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], Any]] = {}
        self._instances: dict[str, Any] = {}

    def register(self, name: str, factory: Callable[[], Any]) -> None:
        """注册服务工厂。工厂在首次 resolve 时调用，结果缓存为单例。

        Args:
            name: 服务名称（如 "llm_handler"、"skill_manager"）。
            factory: 无参工厂函数，通过闭包捕获依赖。
        """
        self._factories[name] = factory

    def register_instance(self, name: str, instance: Any) -> None:
        """直接注册已创建的实例（跳过工厂）。"""
        self._instances[name] = instance

    def resolve(self, name: str) -> Any:
        """解析服务。首次调用时执行工厂，之后返回缓存实例。

        Args:
            name: 服务名称。

        Returns:
            服务实例，未注册时返回 None。
        """
        if name in self._instances:
            return self._instances[name]
        factory = self._factories.get(name)
        if factory is None:
            logger.debug("ServiceContainer: 未注册的服务 '%s'", name)
            return None
        instance = factory()
        self._instances[name] = instance
        return instance

    def has(self, name: str) -> bool:
        """检查服务是否已注册。"""
        return name in self._factories or name in self._instances

    def clear(self) -> None:
        """清除所有已缓存实例（工厂保留，下次 resolve 重新构造）。"""
        self._instances.clear()
