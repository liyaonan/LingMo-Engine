"""GameMaster — 游戏主控，编排 LLM 对话、消息路由和状态管理。"""
from __future__ import annotations

import asyncio
import logging

from lingmo_engine.core.config import EngineConfig
from lingmo_engine.core.game_state import GameState
from lingmo_engine.core.game_world import GameWorld
from lingmo_engine.core.message import Message
from lingmo_engine.core.message_bus import MessageBus, MessageEvent
from lingmo_engine.core.message_persistence import MessagePersistenceService
from lingmo_engine.core.message_store import MessageStore
from lingmo_engine.core.plugin_registry import PluginRegistry
from lingmo_engine.core.service_container import ServiceContainer
from lingmo_engine.core.types import ToolDefinition
from lingmo_engine.llm.base_provider import BaseLLMProvider

from lingmo_engine.core.gamemaster.prompt import (
    build_system_prompt, build_dynamic_state_prompt, build_messages,
    build_entity_index_prompt, build_semi_static_prompt,
    render_tail_condensed,
)
from lingmo_engine.core.gamemaster.prompt_composer import PromptComposer
from lingmo_engine.core.gamemaster.tool_executor import ToolExecutor
from lingmo_engine.core.gamemaster.llm_loop import LLMLoopRunner
from lingmo_engine.core.gamemaster.state_builder import StateBuildService
from lingmo_engine.core.gamemaster.memory_orchestrator import MemoryOrchestrator
from lingmo_engine.core.gamemaster.text_utils import filter_scene_characters
from lingmo_engine.core.page_snapshot import create_page_snapshot, restore_page_snapshot

logger = logging.getLogger(__name__)


class GameMaster:
    """游戏主控 — 编排 LLM 对话、消息路由和状态管理。

    内部委托:
    - LLMLoopRunner: LLM 请求、工具执行、叙事终结
    - ToolExecutor: 工具调用执行与结果应用
    - MessagePersistenceService: 消息持久化到 JSONL
    - prompt 模块: 系统提示词与消息构建
    """

    def __init__(
        self,
        config: EngineConfig,
        llm_provider: BaseLLMProvider,
        plugin_registry: PluginRegistry,
        game_world: GameWorld,
        game_state: GameState,
        message_bus: MessageBus,
        message_store: MessageStore,
        memory_system=None,
    ):
        self.config = config
        self.llm = llm_provider
        self._memory_system = memory_system
        self.plugins = plugin_registry
        self.world = game_world
        self.state = game_state
        # 注册显示增幅函数（世界自定义，如境界增幅）
        combat_fns = game_world.get_combat_functions() if hasattr(game_world, 'get_combat_functions') else {}
        if combat_fns and "amplify_player_snapshot" in combat_fns and hasattr(game_state, "set_amplify_fn"):
            game_state.set_amplify_fn(combat_fns["amplify_player_snapshot"])
        # 注入 GameMaster 引用，同时自动注入 LLMProviderAccess 和 GameState 到所有插件
        self.plugins.set_gamemaster(self)
        # 注入 EventBus 到 GameState（供 prompt 构建时访问跨插件数据）
        game_state._event_bus = plugin_registry.bus
        self._history: list[dict] = []
        self._system_prompt: str = ""
        self._bus = message_bus
        self._store = message_store
        self._session_id: str = ""
        # 跟踪后台任务，防止静默异常
        self._pending_tasks: set[asyncio.Task] = set()
        # 记忆总结进行中标志，防止 LLM_IDLE 过早启用前端输入
        self._summary_pending: bool = False
        # 用户消息处理引用计数，覆盖 LLM 循环 + 记忆总结全生命周期
        # >0 时阻止 _on_llm_idle 启用前端输入和 MessageController 放行新消息
        self._processing_count: int = 0
        # Page 快照（单例，新 Page 自动覆盖旧快照）
        self._current_page_snapshot = None

        # ── 自动存档 ──
        self._auto_save = None
        if config.auto_save.enabled:
            from lingmo_engine.core.auto_save import AutoSaveManager
            self._auto_save = AutoSaveManager(
                state=game_state,
                plugins=plugin_registry,
                is_busy_fn=lambda: self.llm_handler.is_busy,
                interval_seconds=config.auto_save.interval_seconds,
                trigger_events=config.auto_save.trigger_events,
            )

        # ── 通过 ServiceContainer 注册内部服务 ──
        self._container = ServiceContainer()
        self._register_services(llm_provider, memory_system)

        # 从容器解析服务（公共属性保持不变）
        self.llm_handler = self._container.resolve("llm_handler")
        self.skill_manager = self._container.resolve("skill_manager")
        self._prompt_composer = self._container.resolve("prompt_composer")
        self._llm_loop = self._container.resolve("llm_loop")
        self._tool_executor = self._container.resolve("tool_executor")
        self._state_builder = self._container.resolve("state_builder")
        self._memory_orchestrator = self._container.resolve("memory_orchestrator")
        self._persistence = self._container.resolve("persistence")

        # 订阅用户消息事件
        self._bus.subscribe(MessageEvent.CREATED, self._on_message_created)

    def _get_narrative_style(self) -> str:
        """从角色数据读取叙事风格，默认 carefree。"""
        cm = getattr(self.state, 'character_manager', None)
        if cm and cm.player:
            return cm.player.extra.get("narrative_style", "carefree")
        return "carefree"

    def _register_services(self, llm_provider: BaseLLMProvider, memory_system) -> None:
        """将内部服务注册到 ServiceContainer（延迟构造 + 单例缓存）。"""
        from lingmo_engine.llm.llm_handler import LLMHandler
        from lingmo_engine.llm.openai_compatible import OpenAICompatibleProvider
        from lingmo_engine.core.skill_manager import SkillManager

        async def _on_llm_lock():
            await self._bus.publish(MessageEvent.LLM_BUSY)

        async def _on_llm_unlock():
            await self._bus.publish(MessageEvent.LLM_IDLE)

        def _create_fast_provider():
            if self.config.llm_fast.api_key or self.config.llm_fast.model:
                return OpenAICompatibleProvider(self.config.llm_fast)
            return None

        self._container.register("llm_handler", lambda: LLMHandler(
            llm_provider,
            fast_provider=_create_fast_provider(),
            on_lock_acquire=_on_llm_lock,
            on_lock_release=_on_llm_unlock,
        ))
        self._container.register("skill_manager", lambda: SkillManager(
            self.config.world_path, self.plugins,
        ))
        self._container.register("prompt_composer", lambda: PromptComposer(
            self.config.world_path,
            style=self._get_narrative_style(),
        ))
        self._container.register("llm_loop", lambda: LLMLoopRunner(self))
        self._container.register("tool_executor", lambda: ToolExecutor(self))
        self._container.register("state_builder", lambda: StateBuildService(
            get_state_fn=lambda: self.state,
            get_world_fn=lambda: self.world,
            get_plugins_fn=lambda: self.plugins,
        ))
        self._container.register("memory_orchestrator", lambda: MemoryOrchestrator(
            memory_system=memory_system,
            llm_handler=self._container.resolve("llm_handler"),
            get_history_fn=lambda: self._history,
            set_history_fn=lambda h: setattr(self, '_history', h),
            get_character_manager_fn=lambda: getattr(self.state, 'character_manager', None),
            get_config_fn=lambda: self.config,
        ))
        self._container.register("persistence", lambda: MessagePersistenceService(
            self._bus, self._store,
        ))

    async def initialize(self) -> None:
        self._persistence.start()
        self._system_prompt = build_system_prompt(self._prompt_composer)
        self._history = []

        # 加载记忆系统提示词
        if self._memory_system:
            world_path = self.config.world_path
            summary_path = world_path / "prompts" / "memory_summary.md"
            if summary_path.exists():
                self._memory_system.set_summary_prompt(
                    summary_path.read_text(encoding="utf-8")
                )
            char_update_path = world_path / "prompts" / "character_memory_update.md"
            if char_update_path.exists():
                self._memory_system.set_character_update_prompt(
                    char_update_path.read_text(encoding="utf-8")
                )

        logger.info("GameMaster initialized. System prompt length: %d", len(self._system_prompt))

        # 启动自动存档
        if self._auto_save:
            self._auto_save.subscribe_events(self._bus)
            self._auto_save.start()

    # ── 生命周期管理 ──────────────────────────────────

    def cancel_pending(self) -> None:
        """取消所有后台任务和当前 LLM 请求（WS 断开时调用）。"""
        self.llm_handler.cancel()
        for task in list(self._pending_tasks):
            task.cancel()
        if self._pending_tasks:
            logger.info("GameMaster: 已取消 %d 个后台任务", len(self._pending_tasks))

    # ── 消息入口 ──────────────────────────────────

    async def process_input(self, player_input: str, page_id: str = "") -> None:
        """处理玩家输入（公共接口）。

        创建 user Message 并发布到 MessageBus。
        _on_message_created 订阅会自动触发 LLM 循环。
        """
        import uuid7
        if not self._session_id:
            self._session_id = str(uuid7.uuid7())
            self._store.init_session()
            self.state.set_session_id(self._session_id)
            self.state.save()
            # 初始化记忆系统 session
            if self._memory_system:
                self._memory_system.init_session()
        # 确保 user 消息与后续 narrative 消息共享同一 page_id
        page_id = page_id or str(uuid7.uuid7())
        msg = Message(
            id=str(uuid7.uuid7()),
            session_id=self._session_id,
            page_id=page_id,
            role="user",
            content=player_input,
        )
        await self._bus.publish(MessageEvent.CREATING, msg)
        await self._bus.publish(MessageEvent.CREATED, msg)

    # ── MessageBus 事件处理 ─────────────────────

    async def _on_message_created(self, event, msg, **kwargs):
        """收到 MessageBus CREATED 事件 → 如果是用户消息则触发 LLM 循环"""
        if not hasattr(msg, 'role') or msg.role != "user":
            return
        task = asyncio.create_task(self._process_user_message(msg))
        # 跟踪任务，防止静默异常丢失
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)

    async def _process_user_message(self, msg) -> None:
        """处理用户消息的核心入口"""
        self._processing_count += 1
        try:
            await self._process_user_message_impl(msg)
        except asyncio.CancelledError:
            logger.info("GameMaster: 用户消息处理被取消")
        finally:
            self._processing_count -= 1
            if self._processing_count == 0:
                # 处理全部完成，通知前端启用输入框
                # asyncio.shield 防止 CancelledError 中断清理
                try:
                    await asyncio.shield(
                        self._bus.publish(MessageEvent.LLM_IDLE)
                    )
                except (asyncio.CancelledError, Exception):
                    logger.warning("GameMaster: LLM_IDLE 发布失败，前端输入可能需要刷新", exc_info=True)

    async def _process_user_message_impl(self, msg) -> None:
        """_process_user_message 的实际实现。"""
        import uuid7

        logger.info("Player input: %s", msg.content[:100])

        # 创建 Page 快照（在任何状态变更之前）
        cm = getattr(self.state, 'character_manager', None)
        if cm is None:
            cm = getattr(self.world, '_char_manager', None)
            if cm is not None:
                self.state.character_manager = cm
        try:
            self._current_page_snapshot = create_page_snapshot(
                page_id=msg.page_id or str(uuid7.uuid7()),
                user_input=msg.content,
                game_state=self.state,
                character_manager=cm,
                llm_history=self._history,
                memory_system=self._memory_system,
            )
        except Exception:
            logger.warning("GameMaster: Page 快照创建失败，重试功能不可用", exc_info=True)
            self._current_page_snapshot = None

        state_snapshot = self.state.get_data_copy()
        # 注入 CharacterManager 引用，供插件按模板 ID 查找角色数据
        if cm is not None:
            state_snapshot["__character_manager"] = cm
        state_snapshot["_save_dir"] = str(self.state.get_save_dir())
        self.plugins.load_state_to_all_plugins(state_snapshot)

        user_content = msg.content

        self._history.append({"role": "user", "content": user_content})

        tools = self.plugins.get_all_tools()
        use_skill_tool = self.skill_manager.build_skill_tool_definition()
        if use_skill_tool is not None:
            tools = tools + [use_skill_tool]
        memory_tools = self._get_memory_tools()
        if memory_tools:
            tools = tools + memory_tools
        messages = self._build_messages()

        page_id = msg.page_id or str(uuid7.uuid7())
        self._last_page_id = page_id

        await self._run_llm_loop(messages, tools, page_id=page_id)

        self.state.save_all(self.plugins)

        # 记忆总结：同步执行，前端显示总结提示
        # _processing_count 已阻止 _on_llm_idle 提前启用输入，无需手动发布 LLM_BUSY/IDLE
        if self._memory_system:
            self._memory_system.on_round_complete()
            if self._memory_system.has_pending_summary:
                self._summary_pending = True
                try:
                    while self._memory_system.has_pending_summary:
                        pending = self._memory_system.consume_pending_summary()
                        if pending:
                            start_round, end_round = pending
                            await self._run_memory_summary(start_round, end_round)
                finally:
                    self._summary_pending = False

    # ── Page 重试 ──────────────────────────────

    async def handle_retry_page(self, page_id: str) -> dict:
        """处理前端的重试请求。

        Returns:
            {"success": bool, "user_input": str, "error": str}
        """
        # 拒绝 LLM 处理中或消息处理中的重试请求，防止并发修改状态
        if self.llm_handler.is_busy or self._processing_count > 0:
            return {"success": False, "error": "当前有请求正在处理中，请等待完成后再试"}

        snapshot = self._current_page_snapshot
        if snapshot is None:
            return {"success": False, "error": "无可用的快照，无法重试"}
        if snapshot.page_id != page_id:
            return {"success": False, "error": f"快照 page_id 不匹配: 快照={snapshot.page_id}, 请求={page_id}"}

        try:
            cm = getattr(self.state, 'character_manager', None)
            if cm is None:
                return {"success": False, "error": "CharacterManager 未初始化"}

            # 恢复所有状态
            restore_page_snapshot(
                snapshot,
                game_state=self.state,
                character_manager=cm,
                llm_history_ref=self._history,
                memory_system=self._memory_system,
            )

            # 持久化恢复后的状态到磁盘
            self.state.save_all(self.plugins)

            # 清空待处理的记忆总结队列，防止重复总结
            if self._memory_system and self._memory_system.has_pending_summary:
                self._memory_system.clear_pending_summaries()
                logger.info("GameMaster: 已清空 _pending_summaries 队列")

            # 清除快照（已使用，防止重复恢复）
            self._current_page_snapshot = None

            logger.info("GameMaster: Page 重试完成 page_id=%s", page_id)
            return {"success": True, "user_input": snapshot.user_input}

        except Exception:
            logger.exception("GameMaster: Page 重试恢复失败 page_id=%s", page_id)
            return {"success": False, "error": "状态恢复失败，请查看日志"}

    # ── 委托方法（供 server.py 和内部调用） ──────

    def _build_messages(self) -> list[dict]:
        world_data = self.world.get_system_prompt()
        entity_index = build_entity_index_prompt(self.plugins)
        semi_static = build_semi_static_prompt(self.plugins, self.skill_manager)
        dynamic_state = build_dynamic_state_prompt(self.plugins, self.state)

        # 记忆系统数据
        ms = getattr(self, "_memory_system", None)
        long_term_text = ""
        scene_char_text = ""
        recent_history = self._history

        if ms:
            long_term_text = ms.get_long_term_memories_text()
            # 按轮次截断：统计 user 消息数（每轮一个 user 消息），保留最近 N 轮
            n = ms.shard_size
            user_indices = [i for i, h in enumerate(self._history) if h.get("role") == "user"]
            if len(user_indices) > n:
                start_idx = user_indices[-n]
                recent_history = self._history[start_idx:]
            else:
                recent_history = list(self._history)

            # 检测场景角色名 — 从最近对话中提取
            scene_names = self._detect_scene_characters()
            if scene_names:
                scene_char_text = ms.get_scene_character_memories_text(scene_names)

        # 🆕 COT 开关：仅当配置启用时传入思考引导
        cot_guide = ""
        if self.config.llm.cot_enabled:
            cot_guide = self._prompt_composer.cot_thinking_guide

        # 渲染 tail_condensed 模板变量
        rendered_tail = render_tail_condensed(
            self._prompt_composer.tail_condensed, self.state, self.plugins,
        )

        # 渲染 usertail 并追加到最后一条 user message
        rendered_usertail = ""
        if self._prompt_composer.user_tail:
            rendered_usertail = render_tail_condensed(
                self._prompt_composer.user_tail, self.state, self.plugins,
            ).strip()

        if rendered_usertail and recent_history:
            recent_history = list(recent_history)
            for i in range(len(recent_history) - 1, -1, -1):
                if recent_history[i].get("role") == "user":
                    recent_history[i] = {
                        **recent_history[i],
                        "content": recent_history[i]["content"]
                        + "\n(" + rendered_usertail + ")",
                    }
                    break

        return build_messages(
            self._system_prompt, world_data, recent_history,
            self.plugins, self.state,
            dynamic_state_prompt=dynamic_state,
            tail_condensed=rendered_tail,
            long_term_memory_text=long_term_text,
            scene_character_memory_text=scene_char_text,
            cot_thinking_guide=cot_guide,
            entity_index_prompt=entity_index,
            semi_static_prompt=semi_static,
        )

    def _detect_scene_characters(self) -> list[str]:
        """从最近对话和 CharacterManager 中检测当前场景出现的角色名。"""
        cm = getattr(self.state, 'character_manager', None)
        if cm is None:
            return []
        all_names = {c.name for c in cm.all() if c.name}
        # 从最近3轮对话中查找出现的角色名（每轮约2条消息 = 用户输入 + LLM回复）
        recent_text = " ".join(
            h.get("content", "") for h in self._history[-6:]
        )
        return filter_scene_characters(all_names, recent_text)

    async def _run_llm_loop(
        self, messages: list[dict], tools: list[ToolDefinition],
        stream_type: str = "narrative", page_id: str = "",
    ) -> None:
        await self._llm_loop.run(
            messages, tools, stream_type, page_id,
            max_rounds=self.config.llm.max_rounds,
        )

    async def run_narrative_action(self, action: dict) -> None:
        """执行叙事生成 action（由 ActionRegistry 通过回调调用）。

        封装了战斗叙事、修炼叙事、默认叙事三个分支，
        避免将 GM 内部方法暴露给 ActionContext。

        注意: asyncio 单线程模型下 _history.append 安全，
        若未来引入线程池需加锁。
        """
        import uuid7
        from lingmo_engine.core.message import Message
        from lingmo_engine.core.message_bus import MessageEvent

        prompt = action.get("prompt", "")
        stream_type = action.get("stream_type", "narrative")
        page_id = getattr(self, "_last_page_id", "")
        fallback_text = action.get("fallback_text", "")

        # ── 战斗叙事分支：独立总结 → 作为玩家输入发送给主 LLM ──
        if stream_type == "combat_narrative" and prompt:
            combat_result = action.get("combat_result", "胜利")
            summary_messages = [{"role": "user", "content": prompt}]
            try:
                resp = await self.llm_handler.request(
                    summary_messages, tools=None, wait=True,
                    mode="fast", thinking=False,
                )
                summary_text = resp.text if resp else None
            except Exception:
                logger.exception("战斗总结 LLM 调用失败")
                summary_text = None

            if not summary_text:
                summary_text = fallback_text or "战斗结束了。"

            user_content = f"（战斗回顾|{combat_result}）{summary_text}"
            await self.process_input(user_content)
            return

        # ── 修炼叙事分支：独立总结 → 作为玩家输入发送给主 LLM ──
        elif stream_type == "cultivation_narrative" and prompt:
            summary_data = action.get("cultivation_summary", {})
            bt_success = summary_data.get("breakthrough_success")

            try:
                resp = await self.llm_handler.request(
                    [{"role": "user", "content": prompt}],
                    tools=None, wait=True, mode="fast", thinking=False,
                )
                summary_text = resp.text if resp else None
            except Exception:
                summary_text = None

            if not summary_text:
                summary_text = fallback_text or "修炼结束了。"

            bt_label = "修炼结束"
            if bt_success is True:
                bt_label = "突破成功"
            elif bt_success is False:
                bt_label = "突破失败"
            user_content = f"（修炼回顾|{bt_label}）{summary_text}"
            # 附加系统提示：禁止 GM LLM 再次更新玩家属性或推进时间
            sp_gained = summary_data.get("sp_gained", 0)
            total_days = summary_data.get("total_days", 0)
            user_content += (
                f"\n[系统提示：修炼结束，所有状态已由系统计算完毕"
                f"（{total_days}天，灵力+{sp_gained}）。"
                "请勿调用 update_character 或 update_character_field "
                "修改任何修炼相关属性（spiritual_power、cultivation_stage、"
                "cultivation_substage、level、lifespan_remaining、"
                "breakthrough_cooldown、vitality、force、tenacity、agility 等）。"
                "请直接基于以上修炼回顾继续叙事。"
            )
            time_display = summary_data.get("time_advanced_display", "")
            if time_display:
                user_content += (
                    f"另外，修炼期间已自动推进了{time_display}"
                    "时间，无需再调用 advance_time 工具。"
                )
            user_content += "]"
            await self.process_input(user_content)
            return

        # ── 默认分支：原有逻辑 ──
        if prompt:
            self._history.append({
                "role": "user",
                "content": prompt,
            })
        try:
            await self._run_llm_loop(
                self._build_messages(), [],
                stream_type=stream_type,
                page_id=page_id,
            )
        except Exception:
            logger.exception("LLM narrative generation failed")
            if fallback_text:
                fallback_msg = Message(
                    id=str(uuid7.uuid7()),
                    session_id=self._session_id or "default",
                    role="narrative",
                    content=fallback_text,
                    status="complete",
                )
                await self._bus.publish(MessageEvent.CREATED, fallback_msg)

    async def _execute_tool_calls(
        self, final_tool_calls: list,
        page_id: str = "",
    ) -> tuple[list, list, list]:
        return await self._tool_executor.execute(
            final_tool_calls, page_id,
        )

    def _apply_result(self, result) -> None:
        self._tool_executor.apply_result(result)

    def _get_memory_tools(self) -> list:
        """获取记忆系统提供的 LLM 工具定义。"""
        return self._memory_orchestrator.get_memory_tools()

    # ── 记忆总结 ──────────────────────────────────

    async def _run_memory_summary(
        self, start_round: int, end_round: int,
    ) -> None:
        """执行长期记忆总结（委托给 MemoryOrchestrator）。"""
        await self._memory_orchestrator.run_memory_summary(start_round, end_round)

    async def _update_character_memories(
        self, conversation_text: str,
        summary_text: str, current_round: int,
    ) -> None:
        """批量更新所有出现在最近对话中的角色记忆（委托给 MemoryOrchestrator）。"""
        await self._memory_orchestrator.update_character_memories(
            conversation_text, summary_text, current_round
        )

    # ── 状态快照 ──────────────────────────────────

    def build_state(self) -> dict:
        """构建完整 game_state 快照，供 state_update 推送前端。"""
        return self._state_builder.build_state()

    def reload_llm(self, new_provider: BaseLLMProvider, fast_provider: BaseLLMProvider | None = None) -> None:
        """热更新 LLM Provider。"""
        self.llm = new_provider
        self.llm_handler.update_strong_provider(new_provider)
        if fast_provider is not None:
            self.llm_handler.update_fast_provider(fast_provider)
        self.skill_manager.reload()
        self._prompt_composer.reload()
        logger.info("LLM provider reloaded: strong=%s, fast=%s", self.config.llm.model, self.config.llm_fast.model)

    def update_narrative_style(self) -> None:
        """从角色数据重新读取叙事风格并更新 PromptComposer。"""
        style = self._get_narrative_style()
        self._prompt_composer.set_style(style)
        self._system_prompt = build_system_prompt(self._prompt_composer)
        logger.info("叙事风格已切换: %s", style)

    # ── 属性 ──────────────────────────────────────

    @property
    def history(self) -> list[dict]:
        return self._history

    @property
    def session_id(self) -> str:
        return self._session_id

    @session_id.setter
    def session_id(self, value: str) -> None:
        self._session_id = value

    @property
    def last_page_id(self) -> str:
        return self._last_page_id
