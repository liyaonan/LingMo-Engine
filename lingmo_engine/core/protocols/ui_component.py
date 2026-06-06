"""UIComponent 协议 — 插件声明式注册前端 UI 组件。

插件通过实现此协议，告知框架自己需要哪些 UI 面板/覆盖层，
框架自动收集并在前端生成对应的 HTML/JS 资源注入。

用法:
    class MyPanelComponent:
        def get_component_id(self) -> str: return "my_panel"
        def get_component_type(self) -> str: return "panel"
        def get_component_config(self) -> dict: return {"position": "right"}
        def get_required_events(self) -> list[str]: return ["my_state_update"]

    class MyPlugin(BasePlugin):
        def get_ui_components(self) -> list:
            return [MyPanelComponent()]
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class UIComponent(Protocol):
    """插件 UI 组件注册协议 — 声明式前端扩展。

    插件通过 get_ui_components() 返回 UIComponent 实例列表，
    PluginRegistry 收集所有组件，GameServer 根据组件配置生成前端代码。
    """

    def get_component_id(self) -> str:
        """组件唯一标识（如 'combat_panel', 'inventory_bar'）。

        用于前端 JavaScript 组件注册和 CSS 类名前缀。
        """
        ...

    def get_component_type(self) -> str:
        """组件类型，决定渲染位置和默认样式。

        可选值: 'panel' | 'overlay' | 'sidebar' | 'toolbar'
        """
        ...

    def get_component_config(self) -> dict:
        """组件配置（位置、大小、优先级、显示条件等）。

        常用字段:
        - position: str — 在容器中的位置
        - z_index: int — 层叠优先级
        - auto_show: list[str] — 收到哪些 WebSocket 消息时自动显示
        - priority: int — 同类型组件中的排序优先级（越高越靠前）
        """
        ...

    def get_required_events(self) -> list[str]:
        """组件订阅的 WebSocket 消息类型列表。

        框架自动为这些消息类型注册路由。
        """
        ...
