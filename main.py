import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from lingmo_engine.core.config import load_config
from lingmo_engine.core.game_state import GameState
from lingmo_engine.core.game_world import GameWorld
from lingmo_engine.core.gamemaster import GameMaster
from lingmo_engine.core.memory import MemorySystem
from lingmo_engine.core.message_bus import MessageBus
from lingmo_engine.core.message_store import MessageStore
from lingmo_engine.core.plugin_registry import PluginRegistry
from lingmo_engine.core.save_manager import SaveManager, extract_world_name
from lingmo_engine.llm.openai_compatible import OpenAICompatibleProvider, set_log_dir, set_log_enabled
from lingmo_engine.core.gamemaster.llm_loop import set_token_log_dir, set_token_log_enabled
from lingmo_engine.web.server import GameServer


def setup_logging(level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main():
    parser = argparse.ArgumentParser(description="LingMo Engine v0.1")
    parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    args = parser.parse_args()

    setup_logging(args.log_level)
    logger = logging.getLogger("main")

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    config = load_config(str(config_path))
    logger.info("Config loaded from %s", config_path)

    # Initialize LLM provider
    set_log_dir(config.log_path)
    set_log_enabled(config.log_llm)
    set_token_log_dir(config.log_path)
    set_token_log_enabled(config.log_llm)
    llm = OpenAICompatibleProvider(config.llm)
    logger.info("LLM provider: %s (%s)", config.llm.provider, config.llm.model)
    logger.info("LLM log dir: %s", config.log_path)

    # Initialize game world
    world = GameWorld()
    world.load(config.world_path)
    logger.info("World loaded from %s", config.world_path)

    # Initialize MessageBus (必须在插件注册前创建，EventPlugin 等需要 message_bus 引用)
    message_bus = MessageBus()

    # Initialize plugin registry (传入 world 引用)
    plugins = PluginRegistry(world=world)
    plugins.register_from_config(config.plugins, message_bus=message_bus)
    logger.info("Plugins registered: %d", len(config.plugins))

    # 获取世界名
    world_name = extract_world_name(config.world)
    save_dir = config.save_path

    # 初始化 SaveManager
    save_manager = SaveManager(save_dir, world_name)

    # 创建 autosave 槽位目录（新游戏/首次启动）
    autosave_dir = save_manager.ensure_slot_dir("autosave")

    # 初始化 GameState（指向 autosave 槽位）
    state = GameState(autosave_dir)
    state.save_manager = save_manager

    # 在 load() 前注入 CharacterManager，确保存档 NPC（npcs_batch.yaml）能正确加载
    if hasattr(world, '_char_manager') and world._char_manager is not None:
        state.character_manager = world._char_manager

    # 自动加载 autosave（如果存在）
    if state.load():
        logger.info("Auto-loaded autosave from %s", autosave_dir)
    else:
        logger.info("No autosave found, starting fresh")

    # 初始化 MemorySystem
    memory_system = MemorySystem(
        shard_size=config.memory.interval,
        long_term_enabled=config.memory.long_term_enabled,
        character_memory_enabled=config.memory.character_memory_enabled,
    )
    memory_system.set_slot_dir(str(autosave_dir))

    # 初始化 MessageStore
    message_store = MessageStore(
        slot_dir=str(autosave_dir),
        shard_manager=memory_system.history_shard,
    )

    # 初始化 shard index（自动加载 autosave 时尚未调用 init_session）
    memory_system.init_session()

    # 初始化 GameMaster
    gm = GameMaster(
        config, llm, plugins, world, state, message_bus, message_store,
        memory_system=memory_system,
    )

    # 从存档恢复 session_id
    saved_sid = state.get_session_id()
    if saved_sid:
        gm._session_id = saved_sid

    asyncio.run(gm.initialize())

    # 从注册表恢复 LLM 生成的物品到 ItemSystem（启动时 autosave 已加载到 _custom_items）
    inv_plugin = plugins.get_plugin("inventory")
    if inv_plugin:
        inv_plugin.restore_registries(state)

    # 启动服务器
    server = GameServer(config, gm, message_bus=message_bus, message_store=message_store)
    logger.info("Starting server on %s:%d", config.server.host, config.server.port)

    # 优雅关闭
    shutdown_flag = {"done": False}

    def _shutdown(signum, frame):
        if shutdown_flag["done"]:
            return
        shutdown_flag["done"] = True
        sig_name = signal.Signals(signum).name
        logger.info("收到 %s 信号，正在优雅关闭...", sig_name)
        try:
            state.save_all(plugins)
            logger.info("游戏状态已保存")
        except Exception:
            logger.exception("保存游戏状态失败")
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    server.run()


if __name__ == "__main__":
    main()
