# LingMo Engine

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)

LLM-powered text adventure engine. Deploy locally, connect to any OpenAI-compatible API, and play interactive story games generated in real-time by large language models.

Ships with a complete sample world **"Wuji"** (无极) — an immortal cultivation theme featuring combat, cultivation, map exploration, equipment crafting, and inventory management.

[中文文档](README.zh-CN.md)

---

## Features

- **Real-time LLM Narrative** — Every playthrough is unique, driven by LLM-generated stories
- **Streaming Output** — WebSocket push for character-by-character display
- **9 Built-in Plugins** — Combat, Inventory, Map, Calendar, Character, Event, Cultivation, Crafting, Entity Query
- **Multi-World Support** — YAML-driven configuration, create games of any genre
- **Dual LLM Setup** — Strong reasoning model for narrative + fast model for structured tasks
- **Memory System** — Long-term memory + character memory + conversation summaries keep the LLM contextually aware
- **Auto-Save** — Automatic state persistence with event-triggered saving
- **Debug Console** — Built-in debug commands for development and testing

## Quick Start

### Prerequisites

- Python 3.10+
- An OpenAI-compatible API endpoint (DeepSeek, OpenAI, Ollama, vLLM, etc.)

### Install

```bash
git clone https://github.com/liyaonan/LingMo-Engine.git
cd LingMo-Engine
pip install -r requirements.txt
```

### Configure

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` and fill in your LLM API details:

```yaml
llm:
  provider: openai_compatible
  base_url: https://api.deepseek.com/v1
  api_key: ${YOUR_API_KEY}              # Or set via environment variable
  model: deepseek-v4-pro
```

API keys support environment variable references: `${ENV_VAR_NAME}`.

### Run

```bash
python main.py
```

Open `http://localhost:8000` in your browser to start playing.

## Plugin System

LingMo Engine uses a modular plugin architecture. Each plugin is self-contained and can provide LLM tools, frontend components, state persistence, and WebSocket handlers.

| Plugin | Description |
|--------|-------------|
| **Combat** | Turn-based combat with AI-controlled enemies, equipment/ability integration, and dynamic combat reports |
| **Inventory** | Item management with three categories (equipment, consumable, material), dynamic LLM-generated items |
| **Map** | Hierarchical world navigation with facility nodes and spatial calculations |
| **Cultivation** | Multi-tier progression system with breakthrough mechanics and spiritual power |
| **Crafting** | LLM-driven item crafting with material consumption and quality-based rarity |
| **Character** | Schema-driven character creation with attribute validation and relationship tracking |
| **Calendar** | Custom time system with era cycles and time-based events |
| **Event** | LLM-managed event documentation with automatic summarization |
| **Entity Query** | Unified fuzzy search across abilities, items, and characters |

Plugins declare dependencies and are loaded in topological order. See [Plugin Development Guide](docs/plugin-development-guide.md) for building custom plugins.

## World Configuration

Worlds are defined entirely by YAML — no engine code changes needed.

```
lingmo_engine/worlds/
├── wuji_world/          # "Wuji" — Immortal cultivation world
│   ├── setting.yaml     # World settings, UI labels, entity config
│   ├── cultivation.yaml # Cultivation tier definitions
│   ├── calendar.yaml    # Calendar system
│   ├── combat.py        # Custom combat formulas (Python)
│   ├── pricing.py       # Custom pricing logic (Python)
│   └── ...
├── ashenveil_world/     # Dark fantasy world
└── template_world/      # Starter template for new worlds
```

Each world can optionally include Python files for custom game logic (formulas, hooks, resolvers). See [World Building Guide](docs/world-building-guide.md) for details.

### Creating a Custom World

1. Copy `template_world/` to a new directory under `worlds/`
2. Edit `setting.yaml` with your world's theme and configuration
3. Add YAML definitions for abilities, items, characters, etc.
4. Optionally add `.py` files for custom formulas and hooks
5. Point `config.yaml` to your new world directory

## Memory System

The engine maintains context across long play sessions through a three-layer architecture:

- **Conversation History** — Recent dialogue shards, automatically rotated
- **Long-term Memory** — LLM-summarized key events compressed at configurable intervals
- **Character Memory** — Structured per-character memories for consistent NPC behavior

All memory is persisted per save slot and restored on load.

## Configuration Reference

```yaml
# Main LLM (narrative, combat, complex reasoning)
llm:
  provider: openai_compatible    # openai_compatible / anthropic / google
  base_url: <your-api-endpoint>
  api_key: <your-api-key>
  model: <model-name>
  max_tokens: 20000
  temperature: 0.8
  cot_enabled: true              # Chain-of-thought guidance (+200-500 tokens/turn)
  max_rounds: 10                 # Max LLM loop rounds (including tool calls)

# Fast LLM (item generation, simple structured tasks)
llm_fast:
  provider: openai_compatible
  model: <fast-model-name>
  max_tokens: 8000
  temperature: 0.6

# Memory
memory:
  interval: 20                   # Trigger memory summary every N rounds
  long_term_enabled: true
  character_memory_enabled: true
  history_keep_rounds: 10        # Recent rounds to keep after summarization

# Auto-save
auto_save:
  enabled: true
  interval_seconds: 300
  trigger_events:                # Event-based save triggers
    - combat:ended
    - cultivation:breakthrough

# Server
server:
  host: 0.0.0.0
  port: 8000
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, FastAPI, WebSocket |
| Frontend | Vanilla HTML/CSS/JS, Web Components |
| AI | OpenAI-compatible protocol (DeepSeek, OpenAI, Ollama, vLLM) |
| Data | YAML configuration, JSON save files |

## Project Structure

```
LingMo-Engine/
├── main.py                       # Entry point
├── config.example.yaml           # Configuration template
├── requirements.txt              # Python dependencies
├── lingmo_engine/
│   ├── core/                     # Core engine (GameMaster, plugin framework, state)
│   │   ├── gamemaster/           #   LLM loop, prompt composer, tool executor
│   │   ├── memory/               #   Memory system (history, long-term, character)
│   │   └── protocols/            #   Interface definitions
│   ├── llm/                      # LLM provider (OpenAI-compatible)
│   ├── plugins/                  # Plugin implementations
│   │   ├── combat/               #   AI-driven turn-based combat
│   │   ├── inventory/            #   Item & equipment management
│   │   ├── map/                  #   Hierarchical world navigation
│   │   ├── cultivation/          #   Progression system
│   │   ├── crafting/             #   LLM-driven crafting
│   │   ├── character/            #   Character creation
│   │   ├── calendar/             #   Time system
│   │   ├── event/                #   Event logging
│   │   └── entity_query/         #   Entity search
│   ├── character_creation/       # Character creation flow
│   ├── web/                      # FastAPI server + frontend
│   ├── worlds/                   # Game world definitions
│   └── tests/                    # Test suites
└── docs/                         # Documentation
    ├── plugin-development-guide.md
    ├── world-building-guide.md
    └── debug-command.md
```

## License

[MIT License](LICENSE)
