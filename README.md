# LingMo Engine

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)

LLM 驱动的文字游戏引擎 — 本地部署，接入任意 OpenAI 兼容 API，即可运行由大语言模型实时生成的交互式剧情游戏。

内置完整示例世界「无极」：修仙题材，包含战斗、修炼、地图探索、装备制作、背包管理等系统。

[English](README.md)

---

## 功能特性

- **LLM 实时叙事** — 每次游玩体验不同，剧情由大模型实时生成
- **流式输出** — WebSocket 逐字推送，沉浸式阅读体验
- **9 大插件系统** — 战斗、背包、地图、日历、角色、事件、修炼、制作、实体查询
- **多世界支持** — YAML 配置驱动，可创建任意题材的游戏世界
- **双模型架构** — 强推理模型负责叙事剧情 + 快推理模型处理结构化任务
- **记忆系统** — 长期记忆 + 角色记忆 + 对话摘要，让 LLM 保持上下文连贯
- **自动存档** — 定时保存 + 事件触发保存，支持多存档槽位
- **调试控制台** — 内置调试指令，方便开发和测试

## 快速开始

### 环境要求

- Python 3.10+
- 一个 OpenAI 兼容的 API 服务（DeepSeek、OpenAI、Ollama、vLLM 等）

### 安装

```bash
git clone https://github.com/liyaonan/LingMo-Engine.git
cd LingMo-Engine
pip install -r requirements.txt
```

### 配置

```bash
cp config.example.yaml config.yaml
```

编辑 `config.yaml`，填入你的 LLM API 信息：

```yaml
llm:
  provider: openai_compatible
  base_url: https://api.deepseek.com/v1
  api_key: ${YOUR_API_KEY}              # 也可通过环境变量引用
  model: deepseek-v4-pro
```

API Key 支持环境变量引用：`${ENV_VAR_NAME}`。

### 启动

```bash
python main.py
```

浏览器访问 `http://localhost:8000` 即可开始游戏。

## 插件系统

LingMo Engine 采用模块化插件架构，每个插件自包含，可独立提供 LLM 工具、前端组件、状态持久化和 WebSocket 消息处理。

| 插件 | 说明 |
|------|------|
| **Combat（战斗）** | 回合制战斗，AI 控制敌人策略，装备/技能联动，动态战斗报告 |
| **Inventory（背包）** | 三类物品管理（装备、消耗品、材料），支持 LLM 动态生成物品 |
| **Map（地图）** | 层级化世界导航，设施节点，空间距离计算 |
| **Cultivation（修炼）** | 多境界修行体系，突破机制，灵力系统 |
| **Crafting（制作）** | LLM 驱动的物品制作，材料消耗，品质稀有度 |
| **Character（角色）** | Schema 驱动的角色创建，属性校验，人物关系追踪 |
| **Calendar（日历）** | 自定义时间系统，纪元循环，时间事件 |
| **Event（事件）** | LLM 自主管理的事件记录，自动摘要 |
| **Entity Query（实体查询）** | 跨类型模糊搜索（技能、物品、角色） |

插件通过依赖声明自动拓扑排序加载。参见[插件开发指南](docs/plugin-development-guide.md)了解如何编写自定义插件。

## 世界配置

游戏世界完全由 YAML 定义，无需修改引擎代码。

```
lingmo_engine/worlds/
├── wuji_world/          # 「无极」— 修仙世界
│   ├── setting.yaml     # 世界设定、UI 标签、实体查询配置
│   ├── cultivation.yaml # 修炼境界定义
│   ├── calendar.yaml    # 日历系统
│   ├── combat.py        # 自定义战斗公式（Python）
│   ├── pricing.py       # 自定义定价逻辑（Python）
│   └── ...
├── ashenveil_world/     # 灰幕世界（暗黑奇幻）
└── template_world/      # 新世界起始模板
```

每个世界可选择性包含 Python 文件，用于自定义游戏逻辑（公式、钩子、解析器）。详见[世界制作指南](docs/world-building-guide.md)。

### 创建自定义世界

1. 复制 `template_world/` 到 `worlds/` 下的新目录
2. 编辑 `setting.yaml`，填入世界主题和配置
3. 添加技能、物品、角色等 YAML 定义
4. 可选：添加 `.py` 文件实现自定义公式和钩子
5. 修改 `config.yaml` 中的 `world` 指向新世界目录

## 记忆系统

引擎通过三层架构在长游戏会话中保持上下文：

- **对话历史** — 最近的对话分片，自动轮转
- **长期记忆** — LLM 摘要的关键事件，按可配置间隔自动压缩
- **角色记忆** — 每个角色的结构化记忆，确保 NPC 行为一致

所有记忆按存档槽位持久化，加载时自动恢复。

## 配置参考

```yaml
# 主模型（叙事、战斗等复杂推理）
llm:
  provider: openai_compatible    # openai_compatible / anthropic / google
  base_url: <API 地址>
  api_key: <API 密钥>
  model: <模型名称>
  max_tokens: 20000
  temperature: 0.8
  cot_enabled: true              # 思维链引导（每轮额外消耗 200~500 tokens）
  max_rounds: 10                 # LLM 循环最大轮次（含工具调用往返）

# 快推理模型（物品生成等简单结构化任务）
llm_fast:
  provider: openai_compatible
  model: <快推理模型名称>
  max_tokens: 8000
  temperature: 0.6

# 记忆系统
memory:
  interval: 20                   # 每 N 轮触发记忆摘要
  long_term_enabled: true
  character_memory_enabled: true
  history_keep_rounds: 10        # 摘要后保留的最近对话轮数

# 自动存档
auto_save:
  enabled: true
  interval_seconds: 300
  trigger_events:                # 事件触发保存
    - combat:ended
    - cultivation:breakthrough

# 服务器
server:
  host: 0.0.0.0
  port: 8000
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python、FastAPI、WebSocket |
| 前端 | 原生 HTML/CSS/JS、Web Components |
| AI | OpenAI 兼容协议（DeepSeek、OpenAI、Ollama、vLLM） |
| 数据 | YAML 配置、JSON 存档 |

## 项目结构

```
LingMo-Engine/
├── main.py                       # 入口
├── config.example.yaml           # 配置模板
├── requirements.txt              # Python 依赖
├── lingmo_engine/
│   ├── core/                     # 核心引擎
│   │   ├── gamemaster/           #   LLM 循环、提示词组装、工具执行
│   │   ├── memory/               #   记忆系统（历史、长期、角色）
│   │   └── protocols/            #   接口定义
│   ├── llm/                      # LLM 服务层（OpenAI 兼容协议）
│   ├── plugins/                  # 插件实现
│   │   ├── combat/               #   AI 驱动回合制战斗
│   │   ├── inventory/            #   物品与装备管理
│   │   ├── map/                  #   层级化地图导航
│   │   ├── cultivation/          #   修行体系
│   │   ├── crafting/             #   LLM 驱动制作
│   │   ├── character/            #   角色创建
│   │   ├── calendar/             #   时间系统
│   │   ├── event/                #   事件记录
│   │   └── entity_query/         #   实体搜索
│   ├── character_creation/       # 角色创建流程
│   ├── web/                      # FastAPI 服务端 + 前端页面
│   ├── worlds/                   # 游戏世界定义
│   └── tests/                    # 测试套件
└── docs/                         # 文档
    ├── plugin-development-guide.md
    ├── world-building-guide.md
    └── debug-command.md
```

## 开发文档

| 文档 | 说明 |
|------|------|
| [插件开发指南](docs/plugin-development-guide.md) | 如何开发自定义插件（工具、提示词、WebSocket 处理、持久化） |
| [世界制作指南](docs/world-building-guide.md) | 如何创建自定义游戏世界（YAML 配置、地图、技能、物品） |
| [调试指令](docs/debug-command.md) | 内置调试控制台命令，方便开发与测试 |

## 许可证

[MIT License](LICENSE)
