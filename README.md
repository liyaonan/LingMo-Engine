# LingMo Engine

LLM 驱动的文字游戏引擎 — 本地部署，接入任意 OpenAI 兼容 API，即可运行由大语言模型实时生成的交互式剧情游戏。

内置完整示例世界「无极」：修仙题材，包含战斗、修炼、地图探索、装备制作、背包管理等系统。

## 功能特性

- **LLM 实时叙事** — 由大模型驱动剧情走向，每次游玩体验不同
- **流式输出** — WebSocket 逐字推送，沉浸式阅读体验
- **9 大插件系统** — 战斗、背包、地图、日历、角色、事件、修炼、制作、实体查询
- **多世界支持** — YAML 配置驱动，可创建任意题材的游戏世界
- **自动存档** — 游戏状态自动持久化，支持多存档槽位
- **记忆系统** — 长期记忆 + 角色记忆 + 对话摘要，让 LLM 保持上下文连贯
- **Debug 控制台** — 内置调试指令，方便开发和测试

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+（前端开发需要，纯玩家可选）

### 安装

```bash
git clone https://github.com/<你的用户名>/LingMo-Engine.git
cd LingMo-Engine
pip install -r requirements.txt
```

### 配置

```bash
# 复制配置模板
cp config.example.yaml config.yaml
```

编辑 `config.yaml`，填入你的 LLM API 信息：

```yaml
llm:
  provider: openai_compatible
  base_url: https://api.deepseek.com/v1    # 替换为你使用的 API 地址
  api_key: sk-your-api-key-here            # 替换为你的 API Key
  model: deepseek-v4-pro                   # 替换为你使用的模型名称
```

支持所有 OpenAI 兼容的 API 服务（DeepSeek、OpenAI、Ollama、vLLM 等）。

### 启动

```bash
python main.py
```

浏览器访问 `http://localhost:8000` 即可开始游戏。

## 项目结构

```
LingMo-Engine/
├── main.py                     # 入口
├── config.example.yaml         # 配置模板
├── requirements.txt            # Python 依赖
├── lingmo_engine/
│   ├── core/                   # 核心引擎（GameMaster、插件框架、状态管理）
│   ├── llm/                    # LLM 服务层（OpenAI 兼容协议）
│   ├── plugins/                # 插件实现（战斗、背包、地图等）
│   ├── services/               # 公共服务
│   ├── memory/                 # 记忆系统
│   ├── character_creation/     # 角色创建流程
│   ├── web/                    # Web 服务端 + 前端页面
│   ├── worlds/                 # 游戏世界配置
│   │   ├── wuji_world/         # 无极（修仙世界）
│   │   ├── ashenveil_world/    # 灰幕世界
│   │   └── template_world/     # 世界模板
│   └── tests/                  # 测试
└── docs/                       # 文档
```

## 创建自定义世界

参考 `lingmo_engine/worlds/template_world/` 目录结构，或在 `lingmo_engine/worlds/` 下新建世界文件夹。世界配置完全由 YAML 定义，无需修改引擎代码。

详细的世界制作文档请参考各世界目录下的 `docs/` 文件夹。

## 技术栈

- **后端**：Python + FastAPI + WebSocket
- **前端**：原生 HTML/CSS/JavaScript
- **AI**：OpenAI 兼容协议（支持 DeepSeek、OpenAI、Ollama 等）
- **数据**：YAML 配置 + JSON 存档

## 许可证

[MIT License](LICENSE)
