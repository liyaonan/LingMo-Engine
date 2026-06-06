"""修炼会话 — 记录一次修炼过程的完整日志和状态。"""

from lingmo_engine.core.encounter_session import EncounterSession
from lingmo_engine.plugins.cultivation.breakthrough import execute_breakthrough

_YEAR = 365
_MONTH = 30


def _fmt_days(days: int) -> str:
    """天数 → 友好文字（365天=1年, 30天=1月）。"""
    if days < _MONTH:
        return f"{days}天"
    if days < _YEAR:
        m = days // _MONTH
        d = days % _MONTH
        return f"{d}天" if d > 0 and m == 0 else (f"{m}个月" if d == 0 else f"{m}个月{d}天")
    y = days // _YEAR
    rem = days % _YEAR
    if rem == 0:
        return f"{y / 10000:.1f}万年" if y >= 10000 else f"{y}年"
    m = rem // _MONTH
    return f"{y}年{m}个月" if m > 0 else f"{y}年{rem}天"


class CultivationSession(EncounterSession):
    """一次修炼过程的状态机。"""

    def __init__(self, player, schema, qi_bonus: float = 1.0,
                 narrative_hint: str = ""):
        super().__init__(player=player, narrative_hint=narrative_hint)
        self.schema = schema
        self.qi_bonus = qi_bonus
        self.total_days: int = 0
        self.total_sp_gained: float = 0.0
        self.breakthrough_result: dict | None = None

    def cultivate(self, days: int, qi_density: float = 0.4) -> dict:
        """执行打坐并记录日志。"""
        from lingmo_engine.plugins.cultivation.plugin import _player_get

        stage_id = _player_get(self.player, "cultivation_stage", "mortal")
        roots = list(_player_get(self.player, "spiritual_roots", []))

        daily_sp = self.schema.calculate_daily_sp(
            stage_id, roots, qi_density * self.qi_bonus, "meditation")
        total_sp = round(daily_sp * days, 4)

        cur_sp = _player_get(self.player, "spiritual_power", 0)
        new_sp = int(cur_sp + total_sp)
        self._set_player_attr("spiritual_power", new_sp)
        self._set_player_attr("cultivation_substage",
                              self.schema.compute_substage(stage_id, new_sp))

        self.total_days += days
        self.total_sp_gained += total_sp

        self.log.append({
            "day": self.total_days,
            "type": "cultivate",
            "text": f"打坐冥想{_fmt_days(days)}，获得{total_sp}灵力（日均{round(daily_sp, 4)}）",
            "sp_gain": total_sp,
            "method": "meditation",
            "daily_rate": round(daily_sp, 4),
        })

        next_stage = self.schema.get_next_stage(stage_id)
        milestone_reached = False
        breakthrough_ready = False
        if next_stage:
            rule = self.schema.get_breakthrough_rule(stage_id, next_stage.get("id", ""))
            if isinstance(rule, dict):
                threshold = rule.get("requirements", {}).get("spiritual_power_min", 0)
                if isinstance(threshold, (int, float)):
                    threshold = int(threshold)
                if new_sp >= threshold and threshold > 0:
                    if not milestone_reached:
                        milestone_reached = True
                        breakthrough_ready = True
                        self.log.append({
                            "day": self.total_days,
                            "type": "milestone",
                            "text": f"灵力已达突破阈值（{new_sp}/{threshold}）！",
                        })

        return {
            "sp_gain": total_sp,
            "days": days,
            "daily_rate": round(daily_sp, 4),
            "method": "meditation",
            "method_name": "打坐冥想",
            "new_spiritual_power": new_sp,
            "milestone_reached": milestone_reached,
            "breakthrough_ready": breakthrough_ready,
        }

    def attempt_breakthrough(self, qi_density: float = 0.4) -> dict:
        """尝试突破，记录日志。"""
        result = execute_breakthrough(self.player, self.schema, qi_density=qi_density)
        self.breakthrough_result = {
            "success": result.success,
            "log": result.log,
            "data": result.data,
        }
        self.log.append({
            "day": self.total_days,
            "type": "breakthrough",
            "text": result.log,
            "success": result.success,
            "data": result.data,
        })
        return {
            "success": result.success,
            "log": result.log,
            "data": result.data,
        }

    def get_summary(self) -> dict:
        return {
            "narrative_hint": self.narrative_hint,
            "total_days": self.total_days,
            "total_sp_gained": self.total_sp_gained,
            "breakthrough": self.breakthrough_result,
            "log": list(self.log),
        }

    def finish(self) -> dict:
        self.phase = "completed"
        return self.get_summary()

    def _set_player_attr(self, key, value):
        """设置 player 属性，兼容 dict 和 object。"""
        if isinstance(self.player, dict):
            extra = self.player.get("extra")
            if isinstance(extra, dict) and key in extra:
                extra[key] = value
            else:
                self.player[key] = value
        else:
            extra = getattr(self.player, 'extra', None)
            if isinstance(extra, dict) and key in extra:
                extra[key] = value
            else:
                setattr(self.player, key, value)
