# Debug 控制台指令参考

## 启用

`config.yaml` 中设置 `debug: true`，重启游戏。

## 指令列表

所有指令在游戏动作输入框中输入，以 `/debug` 开头。

### 物品操作

```
/debug add_item <物品ID> [数量]
/debug remove_item <物品ID> [数量]
/debug list items
```

**示例：**
```
/debug add_item health_potion 3
/debug add_item iron_sword
/debug remove_item health_potion
/debug remove_item health_potion 2
/debug list items
```

> 物品 ID 由世界配置（`worlds/<世界>/items/`）定义，使用 `/debug list items` 可查看当前世界所有可用物品。

### 战斗 — 固定 NPC

```
/debug combat <NPC名称或ID>
```

与 `characters/fixed/` 中定义的固定角色战斗。

**示例：**
```
/debug combat 1
/debug combat 林立
/debug list enemies
/debug list npcs
```

> `/debug combat` 会弹出遭遇卡片，点击卡片进入战斗。
> 使用 `/debug list enemies` 查看固定怪物，`/debug list npcs` 查看固定 NPC。

### 战斗 — 模板临时敌人

```
/debug spawn <模板ID> [等级] [数量] [资质]
```

根据 `characters/preset_templates.yaml` 中的模板动态生成临时敌人。资质范围 0~1（0.3=愚钝，0.5=普通，0.8=优秀，0.95=天才）。

**示例：**
```
/debug spawn beast_monster
/debug spawn beast_monster 3
/debug spawn demon_cultivator 5 2
/debug spawn beast_monster 5 3 0.8
/debug list templates
```

| 模板 ID | 名称 | 类型 |
|---------|------|------|
| `human_cultivator` | 人族修士 | NPC |
| `beast_monster` | 妖兽 | Monster |
| `demon_cultivator` | 邪修 | NPC |
| `spirit_beast` | 灵兽 | Pet |
| `artifact_spirit` | 器灵 | NPC |

> 模板敌人在战斗结束后自动清理。使用 `/debug list templates` 查看完整列表。

### 属性修改

```
/debug set <属性> <值>
```

可用属性由世界配置 `characters/character_schema.yaml` 中的 `attributes` 动态生成，不含 `read_only` 的属性均可设置。使用 `/debug set` 不带参数可查看完整列表。

常用兼容别名（自动映射到实际字段）：

| 别名 | 实际字段 | 说明 |
|------|----------|------|
| `hp` | `vitality` | 生机 |
| `max_hp` | `max_vitality` | 最大生机 |
| `mp` | `spiritual_power` | 灵力 |
| `attack` | `force` | 劲骨 |
| `defense` | `tenacity` | 根骨 |
| `speed` | `agility` | 灵动 |
| `exp` | `cultivation_exp` | 修为 |
| `gold` | `spirit_stones` | 灵石 |

也可以直接使用 schema 中的实际字段名：
```
/debug set vitality 999
/debug set enlightenment 90
/debug set sword_intent 30
/debug set talisman_mastery 50
/debug set karma -5
/debug set spirit_stones 5000
```

**示例：**
```
/debug set hp 999
/debug set level 10
/debug set gold 5000
/debug set attack 50
```

### 修炼机缘

```
/debug cultivate [灵气加成倍率]
/debug cultivate [灵气加成倍率] [描述文字]
```

调出修炼机缘卡片，点击卡片进入修炼面板。灵气加成倍率默认 1.0。

**示例：**
```
/debug cultivate
/debug cultivate 1.5
/debug cultivate 2.0 你在一处灵脉交汇处找到了隐蔽的修炼洞府
```

> 自动读取玩家当前境界、灵力、道韵等状态。

### 消息调试（LLM 交互日志）

```
/debug msg <子命令> [参数]
```

| 子命令 | 用法 | 说明 |
|--------|------|------|
| `list` | `/debug msg list [n]` | 列出最近 n 条消息（默认 20） |
| `show` | `/debug msg show <ID或序号>` | 显示消息完整内容 |
| `meta` | `/debug msg meta <ID或序号>` | 显示消息元数据（模型、Tokens、耗时等） |
| `prompt` | `/debug msg prompt <ID或序号>` | 显示发送给 LLM 的原始 prompt |
| `search` | `/debug msg search <关键词>` | 搜索包含关键词的消息 |
| `stats` | `/debug msg stats` | 消息统计信息（总数、Tokens 按角色分组） |
| `edit` | `/debug msg edit <ID> <新内容>` | 编辑消息内容 |
| `delete` | `/debug msg delete <ID或序号>` | 删除消息 |
| `export` | `/debug msg export` | 显示当前会话消息文件路径 |

**示例：**
```
/debug msg list 10
/debug msg show msg_123
/debug msg meta msg_123
/debug msg prompt msg_123
/debug msg search 战斗
/debug msg stats
/debug msg edit msg_123 新内容
/debug msg delete msg_123
/debug msg export
```

> 消息 ID 支持前缀匹配。序号从 1 开始，按消息存储顺序编号。

### 调试面板

```
/debug panel
```

在前端打开/关闭可视化调试面板，可查看所有 WebSocket 消息、搜索过滤、查看消息详情和元数据。

### 查看帮助

```
/debug
```
