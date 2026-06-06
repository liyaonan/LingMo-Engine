"""日历插件 - 管理游戏内年号纪元时间系统"""

from __future__ import annotations

import logging
from typing import Optional

from lingmo_engine.core.base_plugin import BasePlugin
from lingmo_engine.core.calendar import DefaultCalendar
from lingmo_engine.core.events import PluginEvent, PluginName
from lingmo_engine.core.types import ToolDefinition, ToolParameter, ModuleResult

logger = logging.getLogger(__name__)


class CalendarPlugin(BasePlugin):
    """日历插件 v0.2.0 - 年号纪元时间系统"""

    name = PluginName.CALENDAR
    version = "0.2.0"
    depends_on: list[str] = []

    def __init__(self):
        super().__init__()
        self._calendar: Optional[DefaultCalendar] = None
        self._state: dict = {}
        self._game_state = None

    @property
    def calendar(self) -> DefaultCalendar | None:
        return self._calendar

    def on_load(self) -> None:
        if self._calendar is not None:
            return
        world = self._world
        if world is None:
            logger.warning("CalendarPlugin: world 未注入，跳过加载")
            return

        calendar_config = world.get_calendar_config()
        if not calendar_config:
            logger.debug("CalendarPlugin: 世界未配置日历，跳过")
            return

        self._calendar = DefaultCalendar(calendar_config)
        logger.info("CalendarPlugin 加载完成: %s", self._calendar.get_time_display())

        if self._bus:
            self._bus.handle(PluginEvent.CALENDAR_GET_INFO, self._handle_get_calendar_info)

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="advance_time",
                description="推进游戏内时间。可用于快速旅行、等待、闭关修炼、改元等",
                parameters=[
                    ToolParameter(
                        name="amount",
                        type="integer",
                        description="推进的数量（0表示不推进，仅更新时段词或创建年号）",
                    ),
                    ToolParameter(
                        name="unit",
                        type="string",
                        description="时间单位: day/month/year",
                    ),
                    ToolParameter(
                        name="time_of_day",
                        type="string",
                        description="更新当前时段词（可选），必须是可选时段词列表中的值",
                        required=False,
                    ),
                    ToolParameter(
                        name="new_era",
                        type="string",
                        description="创建新年号（可选），从当前绝对年开始使用该年号",
                        required=False,
                    ),
                ],
            ),
        ]

    def execute_tool(self, tool_name: str, params: dict) -> ModuleResult:
        if tool_name != "advance_time":
            return ModuleResult(success=False, log=f"未知工具: {tool_name}")
        return self._execute_advance_time(params)

    def get_system_prompt(self) -> str:
        if self._calendar is None:
            return ""
        cal = self._calendar
        options = ", ".join(cal.time_of_day_options)
        era_info = cal.get_era_info()
        era_line = f"当前年号：{era_info['name']}（第{era_info['year_in_era']}年）" if era_info else "无年号纪元"
        return (
            f"\n## 当前时间\n"
            f"{cal.get_time_display()}\n\n"
            f"{era_line}\n"
            f"可选时段词：{options}"
        )

    def get_state(self) -> dict:
        """日历状态已自持久化到 calendar/state.json，不写入 state.json。"""
        return {}

    def get_persistence_dir(self) -> str:
        """日历插件自管理 calendar/ 子目录。"""
        return "calendar"

    def save_own_state(self, slot_dir) -> None:
        """将日历状态保存到 calendar/state.json。"""
        if self._calendar is None:
            return
        state_data = self._calendar.to_dict()
        self._save_plugin_json(slot_dir, "state.json", state_data)

    def load_own_state(self, slot_dir) -> None:
        """从 calendar/state.json 恢复日历状态（SelfPersistable 主路径）。"""
        data = self._load_plugin_json(slot_dir, "state.json")
        if data is not None and data:
            self._calendar = DefaultCalendar.from_dict(data)
            self._state = data
            # 标记自持久化已加载，阻止 load_state 重复创建 DefaultCalendar
            self._self_persisted_loaded = True
            logger.info("CalendarPlugin: 从自持久化恢复日历状态")

    def set_game_state(self, state) -> None:
        """注入 GameState 引用（由 PluginRegistry 自动调用）。"""
        self._game_state = state

    def _get_game_state(self):
        return self._game_state

    def load_state(self, state: dict) -> None:
        """旧格式兼容：从 state.json 的 game_time 字段恢复日历。

        新存档会由 load_own_state() 用 calendar/state.json 覆盖此结果。
        对于新格式存档，load_own_state 已有 calendar/state.json，此方法
        跳过创建以避免无用功（DefaultCalendar 被立即覆盖）。
        """
        self._state = state
        if not state:
            return
        # 如果 load_own_state 已经恢复过日历（有 calendar/state.json），
        # 跳过旧格式恢复，避免创建一个立即被丢弃的 DefaultCalendar 实例
        if getattr(self, '_self_persisted_loaded', False):
            return
        # 完整游戏状态中日历数据嵌套在 game_time 字段；
        # 测试或旧代码可能直接传入日历的 to_dict() 扁平格式
        if "game_time" in state:
            calendar_data = state["game_time"]
        else:
            calendar_data = state
        if calendar_data:
            self._calendar = DefaultCalendar.from_dict(calendar_data)

    def reset_to_initial(self) -> dict | None:
        """从世界配置重建日历为初始状态，返回 to_dict()。用于新游戏重置。"""
        world = self._world
        if world is None:
            return None
        calendar_config = world.get_calendar_config()
        if not calendar_config:
            return None
        self._calendar = DefaultCalendar(calendar_config)
        return self._calendar.to_dict()

    def _handle_get_calendar_info(self) -> dict | None:
        if self._calendar is None:
            return None
        return self._calendar.to_dict()

    def update_all_ages(self) -> int:
        """根据当前日历日期和角色生日，重新计算所有角色的年龄。

        可由其他插件（如修炼插件）在直接推进日历后调用。
        Returns:
            更新了年龄的角色数量。
        """
        if self._calendar is None:
            return 0
        gs = self._get_game_state()
        if gs is None:
            return 0
        cm = getattr(gs, 'character_manager', None)
        if cm is None:
            return 0

        updated = 0
        for char in cm.all():
            if not char.birthday:
                continue
            new_age = self._calendar.calc_age(char.birthday)
            if new_age is not None and new_age != char.age:
                char.age = new_age
                cm.mark_dirty(char.id)
                updated += 1
        return updated

    def _execute_advance_time(self, params: dict) -> ModuleResult:
        if self._calendar is None:
            return ModuleResult(success=False, log="日历模块未加载")

        amount = params.get("amount", 0)
        unit = params.get("unit", "day")
        time_of_day = params.get("time_of_day", "")
        new_era = params.get("new_era", "")

        # 至少需要一个有效操作
        if amount <= 0 and not time_of_day and not new_era:
            return ModuleResult(success=False, log="至少需要一个有效操作（amount>0 或 time_of_day 或 new_era）")

        # 校验时段词
        if time_of_day:
            if time_of_day not in self._calendar.time_of_day_options:
                return ModuleResult(success=False, log=f"无效的时段词: {time_of_day}")

        # 校验年号
        if new_era:
            if self._calendar.eras and self._calendar.eras[-1]["name"] == new_era:
                return ModuleResult(success=False, log=f"与当前年号同名: {new_era}")

        # 执行操作
        log_parts = []
        try:
            if amount > 0:
                result = self._calendar.advance(amount, unit)
                log_parts.append(result["elapsed_display"])
            if time_of_day:
                self._calendar.set_time_of_day(time_of_day)
                log_parts.append(f"时段更新为「{time_of_day}」")
            if new_era:
                self._calendar.declare_era(new_era)
                log_parts.append(f"改元「{new_era}」")
        except ValueError as e:
            return ModuleResult(success=False, log=str(e))

        # 时间推进后自动更新所有角色年龄（基于生日精确计算）
        age_updates = self.update_all_ages()
        if age_updates > 0:
            log_parts.append(f"已更新 {age_updates} 位角色的年龄")

        return ModuleResult(
            success=True,
            log="；".join(log_parts),
            data={
                "state_updates": {"game_time": self._calendar.to_dict()},
            },
        )
