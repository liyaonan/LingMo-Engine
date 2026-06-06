import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_CONFIG_PATH: str | None = None


@dataclass
class LLMConfig:
    provider: str = "openai_compatible"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    max_tokens: int = 2048
    temperature: float = 0.8
    cot_enabled: bool = True       # COT 思考引导开关。启用后每轮额外消耗 200~500 tokens
    max_rounds: int = 10            # LLM 循环最大轮次（含工具调用往返）


@dataclass
class PluginEntry:
    name: str = ""
    cls: str = ""
    module: str = ""
    enabled: bool = True
    config: dict = field(default_factory=dict)


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8000


@dataclass
class MemoryConfig:
    """记忆系统配置。"""
    interval: int = 50
    long_term_enabled: bool = True
    character_memory_enabled: bool = True
    history_keep_rounds: int = 10


@dataclass
class AutoSaveConfig:
    """自动存档配置。"""
    enabled: bool = True
    interval_seconds: int = 300  # 5 分钟
    trigger_events: list = field(default_factory=lambda: [
        "combat:ended",
        "cultivation:breakthrough",
    ])


@dataclass
class EngineConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    llm_fast: LLMConfig = field(default_factory=lambda: LLMConfig(
        provider="openai_compatible",
        model="deepseek-v4-flash",
        max_tokens=8000,
        temperature=0.6,
        cot_enabled=False,
        max_rounds=5,
    ))                            # 快推理模型配置，用于低延迟场景
    plugins: list[PluginEntry] = field(default_factory=list)
    server: ServerConfig = field(default_factory=ServerConfig)
    world: str = "worlds/example_world"
    save_dir: str = "saves"
    log_dir: str = "logs"
    log_llm: bool = True          # 是否写入 LLM 请求/响应和 token 统计日志
    debug: bool = False
    stream_response: bool = True
    max_narrative_retries: int = 2       # 叙事安全网最大重试次数
    show_thinking: bool = True           # 叙述区是否显示 LLM 思考过程
    base_dir: str = "."
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    auto_save: AutoSaveConfig = field(default_factory=AutoSaveConfig)

    @property
    def world_path(self) -> Path:
        return Path(self.base_dir) / self.world

    @property
    def save_path(self) -> Path:
        return Path(self.base_dir) / self.save_dir

    @property
    def log_path(self) -> Path:
        return Path(self.base_dir) / self.log_dir


def _resolve_env(value: str) -> str:
    if value.startswith("${") and value.endswith("}"):
        env_var = value[2:-1]
        return os.environ.get(env_var, "")
    return value


def load_config(config_path: str) -> EngineConfig:
    global _CONFIG_PATH
    _CONFIG_PATH = str(Path(config_path).resolve())

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    base_dir = str(Path(config_path).resolve().parent)

    llm_raw = raw.get("llm", {})
    llm = LLMConfig(
        provider=llm_raw.get("provider", "openai_compatible"),
        base_url=llm_raw.get("base_url", ""),
        api_key=_resolve_env(llm_raw.get("api_key", "")),
        model=llm_raw.get("model", ""),
        max_tokens=llm_raw.get("max_tokens", 2048),
        temperature=llm_raw.get("temperature", 0.8),
        cot_enabled=llm_raw.get("cot_enabled", True),
        max_rounds=llm_raw.get("max_rounds", 10),
    )

    # 快推理模型配置
    llm_fast_raw = raw.get("llm_fast", {})
    llm_fast = LLMConfig(
        provider=llm_fast_raw.get("provider", "openai_compatible"),
        base_url=llm_fast_raw.get("base_url", ""),
        api_key=_resolve_env(llm_fast_raw.get("api_key", "")),
        model=llm_fast_raw.get("model", "deepseek-v4-flash"),
        max_tokens=llm_fast_raw.get("max_tokens", 8000),
        temperature=llm_fast_raw.get("temperature", 0.6),
        cot_enabled=llm_fast_raw.get("cot_enabled", False),
        max_rounds=llm_fast_raw.get("max_rounds", 5),
    )

    plugins = []
    for p in raw.get("plugins", []):
        # 将 YAML 中未识别的键透传到 config 字典
        known_keys = {"name", "class", "module", "enabled"}
        plugin_config = {k: v for k, v in p.items() if k not in known_keys}
        plugins.append(PluginEntry(
            name=p.get("name", ""),
            cls=p.get("class", ""),
            module=p.get("module", ""),
            enabled=p.get("enabled", True),
            config=plugin_config,
        ))

    server_raw = raw.get("server", {})
    server = ServerConfig(
        host=server_raw.get("host", "0.0.0.0"),
        port=server_raw.get("port", 8000),
    )

    memory_raw = raw.get("memory", {})
    memory_config = MemoryConfig(
        interval=memory_raw.get("interval", 50),
        long_term_enabled=memory_raw.get("long_term_enabled", True),
        character_memory_enabled=memory_raw.get("character_memory_enabled", True),
        history_keep_rounds=memory_raw.get("history_keep_rounds", 10),
    )

    auto_save_raw = raw.get("auto_save", {})
    auto_save_config = AutoSaveConfig(
        enabled=auto_save_raw.get("enabled", True),
        interval_seconds=auto_save_raw.get("interval_seconds", 300),
        trigger_events=auto_save_raw.get("trigger_events", ["combat:ended", "cultivation:breakthrough"]),
    )

    return EngineConfig(
        llm=llm,
        llm_fast=llm_fast,
        plugins=plugins,
        server=server,
        memory=memory_config,
        auto_save=auto_save_config,
        world=raw.get("world", "worlds/example_world"),
        save_dir=raw.get("save_dir", "saves"),
        log_dir=raw.get("log_dir", "logs"),
        log_llm=raw.get("log_llm", True),
        debug=raw.get("debug", False),
        stream_response=raw.get("stream_response", True),
        max_narrative_retries=raw.get("max_narrative_retries", 2),
        show_thinking=raw.get("show_thinking", True),
        base_dir=base_dir,
    )


def save_config(config: EngineConfig) -> None:
    if _CONFIG_PATH is None:
        raise RuntimeError("No config path recorded. Call load_config() first.")
    raw = {}
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    # 从 EngineConfig 序列化所有顶层键，确保内存中的完整配置被持久化
    raw["llm"] = {
        "provider": config.llm.provider,
        "base_url": config.llm.base_url,
        "api_key": config.llm.api_key,
        "model": config.llm.model,
        "max_tokens": config.llm.max_tokens,
        "temperature": config.llm.temperature,
        "cot_enabled": config.llm.cot_enabled,
        "max_rounds": config.llm.max_rounds,
    }
    raw["llm_fast"] = {
        "provider": config.llm_fast.provider,
        "base_url": config.llm_fast.base_url,
        "api_key": config.llm_fast.api_key,
        "model": config.llm_fast.model,
        "max_tokens": config.llm_fast.max_tokens,
        "temperature": config.llm_fast.temperature,
        "cot_enabled": config.llm_fast.cot_enabled,
        "max_rounds": config.llm_fast.max_rounds,
    }
    raw["server"] = {
        "host": config.server.host,
        "port": config.server.port,
    }
    raw["plugins"] = [
        {
            "name": p.name,
            "class": p.cls,
            "module": p.module,
            "enabled": p.enabled,
            **p.config,
        }
        for p in config.plugins
    ]
    raw["world"] = config.world
    raw["save_dir"] = config.save_dir
    raw["log_dir"] = config.log_dir
    raw["log_llm"] = config.log_llm
    raw["debug"] = config.debug
    raw["stream_response"] = config.stream_response
    raw["max_narrative_retries"] = config.max_narrative_retries
    raw["show_thinking"] = config.show_thinking
    raw["memory"] = {
        "interval": config.memory.interval,
        "long_term_enabled": config.memory.long_term_enabled,
        "character_memory_enabled": config.memory.character_memory_enabled,
        "history_keep_rounds": config.memory.history_keep_rounds,
    }
    raw["auto_save"] = {
        "enabled": config.auto_save.enabled,
        "interval_seconds": config.auto_save.interval_seconds,
        "trigger_events": config.auto_save.trigger_events,
    }

    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(raw, f, default_flow_style=False, allow_unicode=True)


def mask_api_key(key: str) -> str:
    if not key:
        return ""
    if len(key) < 12:
        return "****"
    return key[:4] + "****" + key[-4:]
