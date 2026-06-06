"""日历核心子系统 — BaseCalendar 抽象接口 + DefaultCalendar 年号纪元实现"""
from __future__ import annotations

from abc import ABC, abstractmethod


class BaseCalendar(ABC):
    """框架日历接口，各世界观实现自己的历法"""

    @abstractmethod
    def advance(self, amount: int, unit: str) -> dict:
        """推进时间，返回变化摘要。unit: day/month/year"""

    @abstractmethod
    def get_time_display(self) -> str:
        """人类可读时间，如 '洪武3年 · 5月 · 10日 · 黄昏'"""

    @abstractmethod
    def get_day_phase(self) -> str:
        """当前时段词（如 清晨/上午/正午/下午/黄昏/夜晚/深夜）"""

    @abstractmethod
    def to_dict(self) -> dict:
        """序列化存入 GameState"""

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict) -> 'BaseCalendar':
        """反序列化"""


class DefaultCalendar(BaseCalendar):
    """年号纪元历法，内部存储绝对年，显示层映射年号。时间粒度到日。"""

    VALID_UNITS = frozenset({"day", "month", "year"})

    DEFAULT_TIME_OF_DAY_OPTIONS = ["清晨", "上午", "正午", "下午", "黄昏", "夜晚", "深夜"]

    def __init__(self, config: dict):
        self._days_per_month = config.get("days_per_month", 30)
        self._months_per_year = config.get("months_per_year", 12)
        self._time_of_day_options: list[str] = config.get("time_of_day_options") or list(self.DEFAULT_TIME_OF_DAY_OPTIONS)
        self._eras: list[dict] = [dict(e) for e in (config.get("eras") or [])]
        self._current_year = config.get("start_year", 1)
        self._current_month = config.get("start_month", 1)
        self._current_day = config.get("start_day", 1)
        self._time_of_day: str = config.get("start_time_of_day", "上午")

    def advance(self, amount: int, unit: str) -> dict:
        if unit not in self.VALID_UNITS:
            raise ValueError(f"不支持的时间单位: {unit}")
        if amount <= 0:
            raise ValueError(f"推进量必须为正数: {amount}")

        previous_display = self.get_time_display()

        if unit == "day":
            self._current_day += amount
        elif unit == "month":
            self._current_month += amount
        elif unit == "year":
            self._current_year += amount

        # 日期溢出（跨月）
        while self._current_day > self._days_per_month:
            self._current_month += 1
            self._current_day -= self._days_per_month

        # 月份溢出（跨年）
        while self._current_month > self._months_per_year:
            self._current_year += 1
            self._current_month -= self._months_per_year

        current_display = self.get_time_display()

        return {
            "previous": previous_display,
            "current": current_display,
            "elapsed_display": self._format_elapsed(amount, unit),
        }

    def get_time_display(self) -> str:
        return f"{self.get_era_display()} · {self._current_month}月 · {self._current_day}日 · {self._time_of_day}"

    def get_day_phase(self) -> str:
        return self._time_of_day

    @property
    def time_of_day_options(self) -> list[str]:
        return self._time_of_day_options

    @property
    def eras(self) -> list[dict]:
        return self._eras

    def set_time_of_day(self, value: str) -> None:
        if value not in self._time_of_day_options:
            raise ValueError(f"无效的时段词: {value}，可选: {', '.join(self._time_of_day_options)}")
        self._time_of_day = value

    def declare_era(self, name: str) -> None:
        if not name:
            raise ValueError("年号名称不能为空")
        if self._eras and self._eras[-1]["name"] == name:
            raise ValueError(f"与当前年号同名: {name}")
        self._eras.append({"name": name, "start_year": self._current_year})

    def get_era_display(self) -> str:
        info = self.get_era_info()
        if info is None:
            return f"{self._current_year}年"
        return f"{info['name']}{info['year_in_era']}年"

    def get_era_info(self) -> dict | None:
        # 倒序查找：找到第一个 start_year <= 当前绝对年
        for era in reversed(self._eras):
            if era["start_year"] <= self._current_year:
                return {
                    "name": era["name"],
                    "start_year": era["start_year"],
                    "year_in_era": self._current_year - era["start_year"] + 1,
                }
        return None

    def to_dict(self) -> dict:
        return {
            "current_year": self._current_year,
            "current_month": self._current_month,
            "current_day": self._current_day,
            "time_of_day": self._time_of_day,
            "eras": [dict(e) for e in self._eras],
            "days_per_month": self._days_per_month,
            "months_per_year": self._months_per_year,
            "time_of_day_options": list(self._time_of_day_options),
            "display": self.get_time_display(),
            "era_display": self.get_era_display(),
            "era_info": self.get_era_info(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'DefaultCalendar':
        config = {
            "days_per_month": data.get("days_per_month", 30),
            "months_per_year": data.get("months_per_year", 12),
            "time_of_day_options": data.get("time_of_day_options"),
            "eras": data.get("eras", []),
            "start_day": data.get("current_day", 1),
            "start_month": data.get("current_month", 1),
            "start_year": data.get("current_year", 1),
            "start_time_of_day": data.get("time_of_day", "上午"),
        }
        return cls(config)

    # ── 生日/年龄辅助方法 ──

    @staticmethod
    def parse_birthday(birthday_str: str) -> tuple[int, int, int] | None:
        """解析 "YYYY/MM/DD" 格式生日字符串为 (year, month, day)。

        Args:
            birthday_str: 生日字符串，如 "782645/5/10"。

        Returns:
            (year, month, day) 元组，或 None（格式无效）。
        """
        if not birthday_str or not isinstance(birthday_str, str):
            return None
        parts = birthday_str.strip().split("/")
        if len(parts) != 3:
            return None
        try:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        except (ValueError, TypeError):
            return None
        if y <= 0 or m <= 0 or d <= 0:
            return None
        return (y, m, d)

    def calc_age(self, birthday_str: str) -> int | None:
        """根据生日字符串和当前日历计算年龄。

        今年生日未过则减1。
        """
        parsed = self.parse_birthday(birthday_str)
        if parsed is None:
            return None
        by, bm, bd = parsed
        age = self._current_year - by
        if self._current_month < bm or (self._current_month == bm and self._current_day < bd):
            age -= 1
        return max(age, 0)

    def random_birthday_for_age(self, age: int) -> str:
        """根据年龄和当前日历日期随机生成生日字符串（月日随机）。

        Args:
            age: 目标年龄。

        Returns:
            "YYYY/MM/DD" 格式字符串。
        """
        import random as _random

        birth_year = self._current_year - age
        month = _random.randint(1, self._months_per_year)
        day = _random.randint(1, self._days_per_month)
        return f"{birth_year}/{month}/{day}"

    @staticmethod
    def _format_elapsed(amount: int, unit: str) -> str:
        unit_names = {
            "day": "天",
            "month": "个月",
            "year": "年",
        }
        name = unit_names.get(unit, unit)
        if amount == 1 and unit == "year":
            return "一年过去了..."
        if amount >= 100 and unit == "year":
            return f"百年（{amount}年）匆匆而过..."
        return f"时间推进了 {amount} {name}..."
