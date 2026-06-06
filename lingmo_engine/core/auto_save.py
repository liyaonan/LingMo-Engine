"""AutoSaveManager — 自动存档管理器。

支持两种触发方式：
1. 定时存档：每隔 interval_seconds 自动保存（由 worker 线程的 wait(timeout) 驱动）
2. 事件触发：监听特定 PluginEvent，在关键事件后立即保存

所有保存操作在单一后台线程中序列化执行，避免并发写入。
通过 threading.Event 通知后台线程进行保存，多次快速触发会
合并为一次保存操作。
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lingmo_engine.core.events import EventBus, PluginEvent

logger = logging.getLogger(__name__)


class AutoSaveManager:
    """自动存档管理器 — 单线程序列化执行，避免并发写入。"""

    def __init__(
        self,
        state,
        plugins,
        is_busy_fn,
        on_saved_fn=None,
        interval_seconds: int = 300,
        trigger_events: list[str] | None = None,
    ):
        """
        参数:
            state: GameState 实例
            plugins: PluginRegistry 实例
            is_busy_fn: 返回 bool 的可调用对象，检查 LLM 是否繁忙
            on_saved_fn: 存档成功后的回调（用于发送 WebSocket 通知等）
            interval_seconds: 定时存档间隔（秒），默认 5 分钟
            trigger_events: 触发存档的 PluginEvent value 列表
        """
        self._state = state
        self._plugins = plugins
        self._is_busy_fn = is_busy_fn
        self._on_saved_fn = on_saved_fn
        self._interval = max(60, interval_seconds)  # 下限 1 分钟
        self._trigger_events = set(trigger_events or [])
        self._last_save_time: datetime | None = None
        self._running = False
        self._consecutive_failures = 0
        # 后台线程 + 事件通知
        self._save_event = threading.Event()  # 通知后台线程执行保存
        self._stop_event = threading.Event()   # 通知后台线程退出
        self._thread: threading.Thread | None = None

    # ── 生命周期 ──────────────────────────────────

    def start(self) -> None:
        """启动自动存档后台线程。"""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._save_event.clear()
        # 启动单一后台线程（线程内部的 wait(timeout) 同时处理定时和事件触发）
        self._thread = threading.Thread(
            target=self._worker, daemon=True, name="auto-save"
        )
        self._thread.start()
        logger.info("自动存档已启动，间隔 %d 秒", self._interval)

    def stop(self) -> None:
        """停止自动存档，等待后台线程完成当前保存。"""
        if not self._running:
            return
        self._running = False
        self._stop_event.set()
        self._save_event.set()  # 唤醒线程以退出
        # 等待线程结束（最多 5 秒）
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._thread = None
        logger.info("自动存档已停止")

    def subscribe_events(self, bus: "EventBus") -> None:
        """订阅配置中指定的事件类型，触发时自动存档。

        应在 EventBus 初始化后调用一次。
        """
        if not self._trigger_events or bus is None:
            return
        for event_value in self._trigger_events:
            try:
                bus.subscribe(event_value, self._on_event_trigger)
                logger.info("自动存档已订阅事件: %s", event_value)
            except Exception:
                logger.warning("自动存档订阅事件失败: %s", event_value)

    # ── 后台线程 ──────────────────────────────────

    def _worker(self) -> None:
        """后台工作线程 — wait(timeout) 同时处理定时和事件触发两种唤醒。

        定时触发：wait(timeout=interval) 超时后自动唤醒。
        事件触发：_on_event_trigger 调用 _save_event.set() 立即唤醒。
        快速连续的事件触发会被合并为一次保存（Event 在 clear 前只计一次）。
        """
        while not self._stop_event.is_set():
            # 等待保存通知（带超时实现定时，Event.set 实现即时触发）
            self._save_event.wait(timeout=self._interval)
            self._save_event.clear()
            if self._stop_event.is_set():
                break
            self._do_save("定时/事件")

    # ── 存档执行 ──────────────────────────────────

    def _do_save(self, reason: str = "定时") -> None:
        """执行存档操作（在后台线程中调用，使用 save_all 原子操作）。"""
        try:
            if self._is_busy_fn():
                logger.debug("自动存档跳过（%s）: LLM 繁忙", reason)
                return
            self._state.save_all(self._plugins)
            self._last_save_time = datetime.now(timezone.utc)
            self._consecutive_failures = 0
            logger.info("自动存档完成（%s）: %s", reason, self._last_save_time.isoformat())
            if self._on_saved_fn:
                try:
                    self._on_saved_fn(self._last_save_time)
                except Exception:
                    logger.debug("自动存档回调异常（已忽略）")
        except Exception:
            logger.exception("自动存档失败（%s）", reason)
            self._consecutive_failures += 1
            if self._consecutive_failures >= 3:
                logger.error("自动存档连续失败 %d 次，请检查磁盘空间和权限", self._consecutive_failures)

    def _on_event_trigger(self, data=None, **kwargs) -> None:
        """事件触发的存档回调 — 仅设置标志位，由后台线程统一执行。

        快速连续的多次事件触发会被合并为一次保存。
        """
        if not self._running:
            return
        self._save_event.set()

    # ── 状态查询 ──────────────────────────────────

    @property
    def last_save_time(self) -> datetime | None:
        """上次自动存档时间。"""
        return self._last_save_time

    @property
    def is_running(self) -> bool:
        """自动存档是否正在运行。"""
        return self._running
