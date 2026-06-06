from __future__ import annotations

from contextlib import contextmanager

from lingmo_engine.core.events import PluginEvent


class GameService:
    """游戏流程服务 — 封装 GameMaster 的所有操作和属性访问。

    Web 控制器通过此服务访问游戏功能，不直接操作 GameMaster。
    """

    def __init__(self, gm):
        self._gm = gm

    @contextmanager
    def paused_auto_save(self):
        """上下文管理器：暂停自动存档，确保加载/新游戏期间不会被后台线程干扰。"""
        auto_save = getattr(self._gm, '_auto_save', None)
        if auto_save:
            auto_save.stop()
        try:
            yield
        finally:
            if auto_save:
                auto_save.start()

    # ── 业务方法 ──

    async def process_input(self, content: str) -> None:
        """处理玩家输入"""
        await self._gm.process_input(content)

    def build_state(self) -> dict:
        """构建前端状态快照"""
        return self._gm.build_state()

    def save_game(self) -> None:
        """保存游戏（核心状态 + 插件自持久化，原子操作）"""
        self._gm.state.save_all(self._gm.plugins)

    def save_as(self, slot_id: str) -> None:
        """另存为（原子保存后复制完整目录）"""
        self._gm.state.save_all(self._gm.plugins)
        self._gm.state.save_as(slot_id)

    def list_saves(self) -> list:
        """列出存档"""
        return self._gm.state.list_saves()

    def is_busy(self) -> bool:
        """LLM 是否繁忙（仅锁状态）"""
        return self._gm.llm_handler.is_busy

    def is_locked(self) -> bool:
        """系统是否锁定，拒绝新用户输入（LLM 锁 + 消息处理中）"""
        return self.is_busy() or self.processing

    def cancel_pending(self) -> None:
        """取消待处理任务"""
        self._gm.cancel_pending()

    def update_narrative_style(self) -> None:
        """通知 GameMaster 重新加载叙事风格。"""
        self._gm.update_narrative_style()

    def get_location_info(self) -> str:
        """获取当前位置信息"""
        return self._gm.plugins.bus.request(PluginEvent.MAP_GET_LOCATION_INFO, "")

    async def initialize(self) -> None:
        """初始化游戏"""
        await self._gm.initialize()

    # ── 只读属性代理 ──

    @property
    def world(self):
        return self._gm.world

    @property
    def state(self):
        return self._gm.state

    @property
    def plugins(self):
        return self._gm.plugins

    @property
    def session_id(self) -> str:
        return getattr(self._gm, '_session_id', '')

    @property
    def message_store(self):
        return getattr(self._gm, '_store', None)

    @property
    def message_bus(self):
        return getattr(self._gm, '_bus', None)

    @property
    def memory_system(self):
        return getattr(self._gm, '_memory_system', None)

    @property
    def message_controller(self):
        return getattr(self._gm, '_message_controller', None)

    @property
    def pending_tasks(self):
        return getattr(self._gm, '_pending_tasks', set())

    # ── 会话操作 ──

    def init_new_session(self) -> str:
        """初始化新 session，返回 session_id"""
        import uuid7
        sid = str(uuid7.uuid7())
        self._gm._session_id = sid
        return sid

    def set_session_id(self, sid: str) -> None:
        self._gm._session_id = sid

    def clear_history(self, clear_disk: bool = False) -> None:
        self._gm._history = []
        if clear_disk:
            # 仅新游戏等需要彻底清除磁盘数据的场景使用
            store = getattr(self._gm, '_store', None)
            if store:
                store.delete_session()
                store.init_session()

    def set_last_page_id(self, page_id: str) -> None:
        self._gm._last_page_id = page_id

    def store_set_slot_dir(self, slot_dir: str) -> None:
        store = getattr(self._gm, '_store', None)
        if store:
            store.set_slot_dir(slot_dir)

    def store_init_session(self) -> None:
        store = getattr(self._gm, '_store', None)
        if store:
            store.init_session()

    def memory_set_slot_dir(self, slot_dir: str) -> None:
        ms = getattr(self._gm, '_memory_system', None)
        if ms:
            ms.set_slot_dir(slot_dir)
            ms.init_session()

    async def publish_message(self, event, message) -> None:
        """发布消息到消息总线"""
        bus = getattr(self._gm, '_bus', None)
        if bus:
            await bus.publish(event, message)

    def set_message_controller(self, mc) -> None:
        """设置消息控制器"""
        self._gm._message_controller = mc

    @property
    def summary_pending(self) -> bool:
        return getattr(self._gm, '_summary_pending', False)

    @property
    def processing(self) -> bool:
        """用户消息是否正在处理中（LLM 循环 + 记忆总结全生命周期）"""
        return getattr(self._gm, '_processing_count', 0) > 0

    def debug_context(self) -> dict:
        """返回 DebugHandler 需要的上下文字典。

        仅用于 /debug 命令，不应被其他控制器或服务调用。
        不暴露 GameMaster 引用。
        """
        return {
            "state": self._gm.state,
            "world": self._gm.world,
            "plugins": self._gm.plugins,
            "message_bus": getattr(self._gm, '_bus', None),
            "message_store": getattr(self._gm, '_store', None),
            "session_id_provider": lambda: self._gm._session_id or 'default',
        }
