# World Building Guide / 世界观开发指南

This document explains how to create custom game worlds for LingMo Engine.

本文档介绍如何为 LingMo Engine 创建自定义游戏世界。

---

## Table of Contents / 目录

- [Overview / 概述](#overview--概述)
- [Quick Start: Create from Template / 快速开始：从模板创建](#quick-start-create-from-template--快速开始从模板创建)
- [Directory Structure / 目录结构](#directory-structure--目录结构)
- [Core Configuration Files / 核心配置文件](#core-configuration-files--核心配置文件)
  - [setting.yaml — World Settings / 世界设定](#settingyaml--world-settings--世界设定)
  - [calendar.yaml — Calendar System / 日历系统](#calendaryaml--calendar-system--日历系统)
  - [characters/ — Character System / 角色系统](#characters--character-system--角色系统)
  - [abilities/ — Ability System / 技能系统](#abilities--ability-system--技能系统)
  - [items/ — Item System / 物品系统](#items--item-system--物品系统)
  - [maps/ — Map System / 地图系统](#maps--map-system--地图系统)
  - [events/ — Event System / 事件系统](#events--event-system--事件系统)
  - [skills/ — Character Skills / 角色技能](#skills--character-skills--角色技能)
  - [prompts/ — Prompt Customization / 提示词定制](#prompts--prompt-customization--提示词定制)
- [Custom Extensions / 自定义扩展](#custom-extensions--自定义扩展)
  - [combat.py — Combat Formulas / 战斗公式](#combatpy--combat-formulas--战斗公式)
  - [pricing.py — Pricing Formulas / 定价公式](#pricingpy--pricing-formulas--定价公式)
  - [creation_hook.py — Character Creation Hook / 角色创建钩子](#creation_hookpy--character-creation-hook--角色创建钩子)
  - [cultivation.yaml — Cultivation System / 修炼系统](#cultivationyaml--cultivation-system--修炼系统)
  - [effect_affixes.yaml — Effect Affixes / 效果词条](#effect_affixesyaml--effect-affixes--效果词条)
- [Theme Customization / 主题定制](#theme-customization--主题定制)
- [Character Creation Page / 角色创建页面](#character-creation-page--角色创建页面)
- [World Loading Flow / 世界加载流程](#world-loading-flow--世界加载流程)
- [From Template to Full World / 从模板到完整世界](#from-template-to-full-world--从模板到完整世界)

---

## Overview / 概述

Worlds in LingMo Engine are defined entirely by **YAML configuration + optional Python scripts** — no engine code modification required. The engine provides a Schema-Driven loading mechanism:

LingMo Engine 的世界完全由 **YAML 配置 + 可选 Python 脚本** 定义，无需修改引擎代码。引擎提供了一套 Schema-Driven 的加载机制：

- YAML defines data (attributes, items, abilities, maps...)
- Engine code auto-generates behavior from schemas (tool registration, attribute calculation, frontend rendering)
- Python files provide complex logic that can't be expressed in YAML (damage formulas, pricing algorithms, creation hooks)

- YAML 定义数据（属性、物品、技能、地图...）
- 引擎代码根据 Schema 自动生成行为（工具注册、属性计算、前端渲染）
- Python 文件提供不可 YAML 化的复杂逻辑（伤害公式、定价算法、角色创建钩子）

**Bundled example worlds / 内置示例世界：**

| World / 世界 | Path / 路径 | Description / 说明 |
|------|------|------|
| Template World | `worlds/template_world/` | Minimal template, generic fantasy / 最小模板，通用奇幻题材 |
| Wuji World | `worlds/wuji_world/` | Full example: xianxia world with all systems / 完整修仙世界 |
| Ashenveil World | `worlds/ashenveil_world/` | Second example world / 第二个示例世界 |

---

## Quick Start: Create from Template / 快速开始：从模板创建

### 1. Copy Template / 复制模板

```bash
cp -r lingmo_engine/worlds/template_world lingmo_engine/worlds/my_world
```

### 2. Edit World Settings / 修改世界设定

Edit `setting.yaml`:

```yaml
world:
  name: "My World / 我的世界"
  description: "A custom game world / 一个自定义的游戏世界"
  version: "0.1"
```

### 3. Update Config Reference / 修改配置引用

Edit `config.yaml`:

```yaml
world: lingmo_engine/worlds/my_world
```

### 4. Launch & Test / 启动测试

```bash
python main.py
```

---

## Directory Structure / 目录结构

A fully-featured world directory:

一个完整世界的目录结构：

```
my_world/
├── setting.yaml                  # [Required] World core settings / [必需] 世界核心设定
├── calendar.yaml                 # [Optional] Calendar system / [可选] 日历系统
├── cultivation.yaml              # [Optional] Cultivation/growth system / [可选] 修炼系统
├── pricing.yaml                  # [Optional] Economy system / [可选] 经济系统
├── effect_affixes.yaml           # [Optional] Unified effect affixes / [可选] 统一效果词条
├── combat.py                     # [Optional] Custom combat formulas / [可选] 自定义战斗公式
├── pricing.py                    # [Optional] Custom pricing formulas / [可选] 定价公式
├── creation_hook.py              # [Optional] Post-creation hook / [可选] 角色创建后处理
├── panel_config.yaml             # [Optional] UI panel config / [可选] UI 面板配置
│
├── characters/                   # Character system / 角色系统
│   ├── character_schema.yaml     # Character attribute definitions / 角色属性定义
│   ├── _tags.yaml                # Character tag groups / 角色标签分组
│   ├── preset_templates.yaml     # Preset character templates / 预设角色模板
│   └── fixed/                    # Fixed characters (NPCs/monsters) / 固定角色
│       └── npc_0.yaml
│
├── character_creation/           # Character creation flow / 角色创建流程
│   ├── character_creation.yaml   # Creation config (routes/templates/forms) / 创建配置
│   └── creation.html             # Creation page UI / 创建页面
│
├── abilities/                    # Ability system / 技能系统
│   ├── _templates.yaml           # Effect templates/budget tables / 效果模板/预算表
│   ├── _tags.yaml                # Ability tag groups / 技能标签分组
│   ├── ability_categories.yaml   # Ability categories / 技能分类
│   ├── ability_rarities.yaml     # Rarity tiers / 稀有度层级
│   ├── preset_abilities.yaml     # Preset abilities / 预设技能
│   └── basic.yaml                # Basic abilities / 基础技能
│
├── items/                        # Item system / 物品系统
│   ├── _templates.yaml           # Consumable effect templates / 消耗品效果模板
│   ├── _tags.yaml                # Item tag groups / 物品标签分组
│   ├── item_categories.yaml      # Item categories / 物品分类
│   ├── item_rarities.yaml        # Rarity tiers / 稀有度层级
│   ├── equip_slots.yaml          # Equipment slots / 装备槽位
│   ├── equip_stats.yaml          # Equipment stat mapping / 装备属性映射
│   ├── crafting.yaml             # Crafting recipes / 制作配方
│   ├── special_items.yaml        # Plot-critical items / 剧情道具
│   ├── preset_consumables.yaml   # Preset consumables / 预设消耗品
│   ├── preset_equipment.yaml     # Preset equipment / 预设装备
│   └── basic.yaml                # Basic items / 基础物品
│
├── maps/                         # Map system / 地图系统
│   └── world.yaml                # Map node definitions / 地图节点定义
│
├── events/                       # Event system / 事件系统
│   ├── generation.yaml           # Event generation rules / 事件生成规则
│   └── examples/                 # Event examples / 事件示例
│
├── skills/                       # Character skills (injected into LLM) / 角色技能
│   ├── __global__.yaml           # Global skill config / 全局技能配置
│   └── character/                # Character-specific skills / 角色专属技能
│
├── prompts/                      # LLM prompt customization / 提示词定制
│   ├── head_01_writing_style.md  # Writing style / 写作风格
│   ├── head_02_constraints.md    # Constraints / 约束规则
│   └── tail_condensed.md         # Tail condensed prompt / 尾部压缩提示
│
├── factions/                     # [Optional] Faction system / [可选] 势力系统
│   └── faction_schema.yaml
│
├── schemas/                      # [Optional] Schema extensions / [可选] Schema 扩展
│   └── level_colors.yaml
│
├── theme/                        # [Optional] UI theme / [可选] UI 主题
│   ├── theme.css
│   ├── fonts/
│   └── images/
│
└── docs/                         # [Optional] World documentation / [可选] 世界文档
```

YAML files starting with `_` are config files (`_templates.yaml`, `_tags.yaml`) and are not loaded as content data.

以 `_` 开头的 YAML 文件是配置文件（`_templates.yaml`、`_tags.yaml`），不会被当作内容数据加载。

---

## Core Configuration Files / 核心配置文件

### setting.yaml — World Settings / 世界设定

The only **required** file. Defines basic world info and global parameters for all systems.

唯一**必需**的文件。定义世界基本信息和各系统的全局参数。

```yaml
# World metadata / 世界元数据
world:
  name: "World Name"                  # Displayed in UI title / 显示在 UI 标题
  description: "World description"     # Visible to LLM / LLM 可见
  version: "0.1"

# Entity query configuration / 实体查询配置
entity_query:
  fuzzy_threshold: 5                   # Max fuzzy search results / 模糊搜索最大返回数
  cache_size: 30                       # Entity cache size / 实体缓存大小
  type_thresholds:                     # Per-type thresholds / 按类型阈值
    ability: 3
    item: 5
    character: 3

# Map configuration / 地图配置
map:
  hierarchy: ["Realm", "Domain", "State", "Town,Dungeon,Instance", "Building,Facility"]
                                       # Level names (top to bottom) / 层级名称
  scale: 10                            # Map scale factor / 地图缩放基数
  visibility_multiplier: 4             # Visibility range multiplier / 可见范围倍率
  independent_roots: true              # Independent coordinate systems per root / 独立坐标系

# UI text labels (for frontend localization) / UI 文本标签（前端本地化）
ui_labels:
  hp: "HP"
  mp: "MP"
  level: "Level"
  spiritual_power: "Mana"
  element: "Element"
  equip_requirements: "Requirements"
  character: "Character"
  save: "Save"
  settings: "Settings"
  combat: "Combat"
  abilities: "Abilities"
  inventory: "Inventory"
  event: "Events"
  crafting: "Crafting"
```

### calendar.yaml — Calendar System / 日历系统

Defines the in-game time system. If absent, the calendar plugin uses defaults.

定义游戏内时间系统。不存在此文件则日历插件使用默认配置。

```yaml
type: default
days_per_month: 30                     # Days per month / 每月天数
months_per_year: 12                    # Months per year / 每年月数

month_names:                           # Month display names / 月份名称列表
  - "January"
  - "February"
  # ... total: months_per_year

time_of_day_options:                   # Time periods in a day / 一天中的时段
  - "Dawn"
  - "Morning"
  - "Midday"
  - "Afternoon"
  - "Dusk"
  - "Night"
  - "Late Night"

# Initial date / 初始日期
start_year: 1
start_month: 1
start_day: 1
start_time_of_day: "Morning"
```

### characters/ — Character System / 角色系统

#### character_schema.yaml — Character Attribute Definitions / 角色属性定义

Defines all character attributes and fields. This is the single source of truth for the combat system, frontend panels, and LLM tools.

定义角色的所有属性和字段。这是战斗系统、前端面板、LLM 工具的统一数据来源。

```yaml
attributes:
  # ── Health/Resource Pools / 生命/资源池 ──
  vitality:
    type: int
    default: 100
    label: "HP"                        # Display label / 显示标签
    combat_type: pool                  # Combat type: pool / resource / pool_max
    pair: max_vitality                 # Paired attribute (pools must specify max)
    show_in_status_bar: true           # Show in status bar / 状态栏显示
    core: true                         # Core attribute (non-removable) / 核心属性
    innate: true                       # Innate attribute (not growable via tools) / 先天属性
    validation:
      hard_cap: 999                    # Hard maximum / 硬上限
      hard_min: 0                      # Hard minimum / 硬下限

  max_vitality:
    type: int
    default: 100
    label: "Max HP"
    combat_type: pool_max
    pair: vitality
    core: true
    innate: true

  # ── Combat Attributes / 战斗属性 ──
  force:
    type: int
    default: 10
    label: "Strength"
    combat_role: attack                # Combat role: attack / defense / speed
    show_in_radar: true                # Show in radar chart / 雷达图显示
    innate: true

  tenacity:
    type: int
    default: 10
    label: "Defense"
    combat_role: defense
    show_in_radar: true
    innate: true

  agility:
    type: int
    default: 10
    label: "Speed"
    combat_role: speed
    show_in_radar: true
    innate: true

  # ── Special Attributes / 特殊属性 ──
  spiritual_power:
    type: int
    default: 0
    label: "Mana"
    combat_type: resource
    display_section: cultivation       # Frontend display section / 前端显示分区

# Character fields (non-numeric) / 角色字段（非数值型）
fields:
  name:
    type: str
    default: ""
    label: "Name"
    required: true
    core: true

  char_type:
    type: str
    default: "npc"
    label: "Type"
    enum: ["player", "npc", "monster", "pet"]
    core: true

  level:
    type: int
    default: 1
    label: "Level"
    core: true

  personality:
    type: str
    default: ""
    label: "Personality"

  cultivation_path:
    type: str
    default: ""
    label: "Path"

# Status bar display order / 状态栏显示顺序
status_bar_order:
  - vitality
  - spiritual_power
  - force
  - tenacity
  - agility

# Element system (optional) / 元素系统（可选）
elements:
  types: ["Fire", "Water", "Earth", "Wind", "Lightning"]
  interactions:
    strong_against:                    # Elemental advantage / 元素克制
      - ["Fire", "Wind"]
      - ["Water", "Fire"]
    weak_against:                      # Elemental disadvantage / 元素劣势
      - ["Fire", "Water"]
      - ["Wind", "Earth"]

# LLM visibility control (optional) / LLM 可见性控制（可选）
llm_visibility:
  hidden_attributes:                   # Attributes hidden from LLM / LLM 不可见的属性
    - karma
  hidden_fields:                       # Fields hidden from LLM / LLM 不可见的字段
    - internal_notes
```

**Key concepts / 关键概念：**

| Field / 字段 | Description / 说明 |
|------|------|
| `combat_role` | Marks attribute's combat role (`attack`/`defense`/`speed`), auto-read by combat system / 战斗角色 |
| `combat_type` | Marks combat type (`pool`/`pool_max`/`resource`), determines HP/MP bar display / 战斗类型 |
| `innate` | Innate attribute, LLM should not modify via tools / 先天属性，LLM 不应修改 |
| `core` | Core attribute, affects save compatibility / 核心属性，影响存档兼容性 |

#### _tags.yaml — Character Tag Groups / 角色标签分组

```yaml
tag_groups:
  - id: race
    name: "Race"
    tags: ["Human", "Elf", "Dwarf", "Orc"]
  - id: class
    name: "Class"
    tags: ["Warrior", "Mage", "Rogue", "Cleric"]
```

#### preset_templates.yaml — Preset Character Templates / 预设角色模板

Used by the debug command `/debug spawn` to dynamically generate temporary characters:

用于 debug 命令 `/debug spawn` 动态生成临时角色：

```yaml
templates:
  - id: human_warrior
    name: "Human Warrior"
    char_type: npc
    base_level: 1
    aptitude_range: [0.3, 0.8]
    base_attrs:
      force: 15
      tenacity: 12
      agility: 8
    tag_bias:
      race: Human
      class: Warrior

  - id: wolf_monster
    name: "Dire Wolf"
    char_type: monster
    base_level: 1
    aptitude_range: [0.2, 0.6]
    base_attrs:
      force: 10
      tenacity: 8
      agility: 14
```

#### fixed/ — Fixed Characters / 固定角色

Each YAML file defines one fixed character (NPC, monster, etc.), auto-loaded at startup:

每个 YAML 文件定义一个固定角色（NPC、怪物等），引擎启动时自动加载：

```yaml
# characters/fixed/guard_captain.yaml
id: guard_captain
name: "Captain Iron"
char_type: npc
level: 5
personality: "Righteous, stern, dutiful"
force: 25
tenacity: 22
agility: 15
vitality: 150
max_vitality: 150
abilities:
  - heavy_slash
  - shield_bash
location: "Capital·Barracks"
```

### abilities/ — Ability System / 技能系统

#### _templates.yaml — Effect Templates & Budget / 效果模板与预算

Defines ability effect templates, level budgets, and scaling tables:

```yaml
# Effect templates / 效果模板
__templates__:
  damage:
    description: "Deal damage to target"
    combat: true
    base: {power: 2.0}
    stack_increment: {power: 0.25}
  buff:
    description: "Increase target attribute"
    combat: true
    base: {modifier: 0.1, duration: 2}
    stack_increment: {modifier: 0.05}
    default_stat: "force"
  heal:
    description: "Restore target health"
    combat: true
    base: {power: 1.5}
    stack_increment: {power: 0.2}

# Level budget table (available points per level) / 等级预算表
__budget__:
  1: {total: 5, offense: 3, defense: 2}
  5: {total: 8, offense: 5, defense: 3}
  10: {total: 12, offense: 8, defense: 4}

# Cost scaling table / 消耗缩放表
__cost_scale__:
  stamina: {base: 5, per_level: 1.2}

# Value scaling table / 数值增幅表
__value_scale__:
  power: {base: 1.0, per_level: 1.15}

# Legal tag combinations / 合法标签组合
__legal_tags__:
  - ["melee", "physical"]
  - ["ranged", "physical"]
  - ["melee", "fire"]
  - ["ranged", "ice"]
  - ["healing"]

# Exclusion rules / 互斥规则
__exclusions__:
  - ["damage", "heal"]
  - ["buff", "debuff"]

# Status effect definitions / 状态效果定义
__statuses__:
  stunned: "Character is stunned, skips next turn"
  bleeding: "Character is bleeding, loses HP each turn"
```

#### _tags.yaml — Ability Tag Groups / 技能标签分组

```yaml
tag_groups:
  - id: range
    name: "Range"
    tags: ["melee", "ranged", "aoe"]
  - id: element
    name: "Element"
    tags: ["physical", "fire", "ice", "lightning"]

tag_cost_map:
  aoe: {stamina: 3}                   # AOE tag costs extra 3 stamina
  fire: {mana: 2}                      # Fire tag costs extra 2 mana
```

#### ability_categories.yaml — Ability Categories / 技能分类

```yaml
categories:
  - id: attack
    name: "Attack"
    tab_order: 1
  - id: defense
    name: "Defense"
    tab_order: 2
  - id: support
    name: "Support"
    tab_order: 3
  - id: ultimate
    name: "Ultimate"
    tab_order: 4
    combat_bonus: "damage * 1.5"       # Category bonus rule / 分类加成规则
```

#### ability_rarities.yaml — Rarity Tiers / 稀有度层级

```yaml
rarities:
  - id: common
    name: "Common"
    min: 1
    max: 25
    color: "#9e9e9e"
    affix_count: 1                      # Random affix count / 随机词条数
    max_stack: 3                        # Max affix stack / 词条最大叠加层数
  - id: rare
    name: "Rare"
    min: 26
    max: 50
    color: "#2196f3"
    affix_count: 2
    max_stack: 5
    guarantee: 1                        # Guaranteed 1 high-tier affix / 保底高级词条数
  - id: epic
    name: "Epic"
    min: 51
    max: 75
    color: "#9c27b0"
    affix_count: 3
    max_stack: 8
    guarantee: 2
  - id: legendary
    name: "Legendary"
    min: 76
    max: 100
    color: "#ff9800"
    affix_count: 4
    max_stack: 12
    guarantee: 3
```

#### Ability Content Files / 技能内容文件

YAML files not starting with `_` are ability content. Supports flat lists and nested groups:

非 `_` 开头的 YAML 文件是技能内容，支持扁平列表和嵌套分组：

```yaml
# basic.yaml
basic_attacks:
  - id: basic_attack
    name: "Basic Attack"
    summary: "Basic physical attack"
    category: attack
    description: "A standard weapon attack"
    rarity: 10
    rarity_tier: common
    costs:
      - resource: stamina
        amount: 2
    cooldown: 0
    effects:
      - type: damage
        value: 10
        target: enemy
    tags:
      - melee
      - physical

  - id: heavy_slash
    name: "Heavy Slash"
    summary: "A powerful charged strike"
    category: attack
    rarity: 30
    rarity_tier: rare
    costs:
      - resource: stamina
        amount: 8
    cooldown: 2
    effects:
      - type: damage
        value: 25
        target: enemy
      - type: debuff
        stat: defense
        modifier: -0.2
        duration: 2
        target: enemy
    tags:
      - melee
      - physical
```

### items/ — Item System / 物品系统

The item system mirrors the ability system structure, using the same `_templates` / `_tags` / `categories` / `rarities` pattern.

物品系统的结构与技能系统对称，使用相同的配置模式。

#### equip_slots.yaml — Equipment Slots / 装备槽位

```yaml
slots:
  - id: weapon
    name: "Weapon"
    icon: "⚔"
    weight: 1.0                        # Weight (affects equipment score) / 权重
  - id: armor
    name: "Armor"
    icon: "🛡"
    weight: 1.0
  - id: accessory
    name: "Accessory"
    icon: "💍"
    weight: 0.5
```

#### equip_stats.yaml — Equipment Stat Mapping / 装备属性映射

```yaml
# Which equipment types can affect which character attributes
# 定义哪些装备类型可以影响哪些角色属性
weapon:
  - force
armor:
  - tenacity
  - max_vitality
accessory:
  - agility
  - spiritual_power
```

#### crafting.yaml — Crafting Recipes / 制作配方

```yaml
crafting:
  categories:
    - id: weapon
      name: "Weapon Smithing"
    - id: potion
      name: "Alchemy"

  recipes:
    - id: iron_sword
      name: "Iron Sword"
      category: weapon
      materials:
        - id: iron_ore
          amount: 3
        - id: wood
          amount: 1
      result:
        type: equipment
        template: "iron_sword_template"
```

#### Item Content Files / 物品内容文件

```yaml
# basic.yaml
items:
  - id: health_potion
    name: "Health Potion"
    summary: "Restores a small amount of HP"
    description: "A red liquid with a faint herbal scent"
    category: consumable
    rarity: 15
    rarity_tier: common
    effects:
      - type: heal
        value: 30
    tags:
      - potion
      - healing

  - id: iron_sword
    name: "Iron Sword"
    summary: "A standard iron sword"
    description: "A plain but sturdy iron sword"
    category: equipment
    rarity: 20
    rarity_tier: common
    slot: weapon
    stats:
      force: 5
    tags:
      - sword
      - metal
```

### maps/ — Map System / 地图系统

Maps use a node tree structure. Each node has a level determined by `setting.yaml`'s `map.hierarchy`.

地图使用节点树结构，每个节点有层级（由 `setting.yaml` 的 `map.hierarchy` 决定）。

```yaml
# maps/world.yaml
type: default
start_node: human_realm

nodes:
  # ── Level 0: Realm ──
  - id: human_realm
    name: "Human Realm"
    description: "The land where mortals dwell"
    level: 0
    parent_id: null
    children_ids: [east_domain, west_domain]
    connection_ids: []

  # ── Level 1: Domain ──
  - id: east_domain
    name: "Eastern Domain"
    description: "The spirit-rich eastern lands"
    level: 1
    parent_id: human_realm
    children_ids: [cloud_state]
    connection_ids: [west_domain]

  # ── Level 2: State ──
  - id: cloud_state
    name: "Cloud State"
    description: "Mountains wreathed in mist"
    level: 2
    parent_id: east_domain
    children_ids: [cloud_city]
    connection_ids: []

  # ── Level 3: Town ──
  - id: cloud_city
    name: "Cloud City"
    description: "The largest city in the Eastern Domain"
    level: 3
    parent_id: cloud_state
    children_ids: [tavern, market]
    connection_ids: []
    center: [400, 300]                 # Map coordinates (pixels) / 地图坐标（像素）
    radius: 40                         # Display radius / 显示半径
    type: "Town"                       # Location type / 地点类型

  # ── Level 4: Building ──
  - id: tavern
    name: "Drunk Immortal Tavern"
    description: "A tavern known for its gossip"
    level: 4
    parent_id: cloud_city
    children_ids: []
    connection_ids: [market]
    center: [380, 280]
    radius: 15
    type: "Building"
```

**Node fields / 节点字段：**

| Field / 字段 | Type / 类型 | Description / 说明 |
|------|------|------|
| `id` | `str` | Unique identifier / 唯一标识 |
| `name` | `str` | Display name / 显示名称 |
| `description` | `str` | Location description (visible to LLM) / 地点描述 |
| `level` | `int` | Depth level (0 = root) / 层级深度 |
| `parent_id` | `str/null` | Parent node ID / 父节点 ID |
| `children_ids` | `list[str]` | Child node IDs / 子节点 ID 列表 |
| `connection_ids` | `list[str]` | Same-level connected neighbors / 同层邻居节点 |
| `center` | `[x, y]` | Map coordinates (required for leaf nodes) / 地图坐标 |
| `radius` | `int` | Display radius (leaf nodes) / 显示半径 |
| `type` | `str` | Location type label / 地点类型标签 |

### events/ — Event System / 事件系统

#### generation.yaml — Event Generation Rules / 事件生成规则

```yaml
# Event types and templates / 事件类型和模板
event_types:
  - id: random_encounter
    name: "Random Encounter"
    description: "People or events encountered during travel"
    probability: 0.3
    trigger_conditions:
      - "Player moves to a new location"

  - id: discovery
    name: "Discovery"
    description: "Hidden treasure or secrets found"
    probability: 0.15
    trigger_conditions:
      - "Player is exploring"

# Variable pools / 事件变量池
variable_pools:
  npcs: ["Mysterious Elder", "Wounded Traveler", "Suspicious Merchant"]
  locations: ["Abandoned Cave", "Hidden Passage", "Ancient Battlefield"]
  rewards: ["Gold Coins", "Pills", "Torn Manual"]
```

### skills/ — Character Skills / 角色技能

Character skills are game rules/knowledge injected into the LLM prompt:

角色技能是注入到 LLM 提示词中的游戏规则/知识：

```yaml
# skills/__global__.yaml
base_skills: []                        # Always injected / 始终注入

dynamic_skills:
  combat_start:                        # Injected on combat start / 战斗开始时注入
    - "combat_rules"
  exploration:                         # Injected during exploration / 探索时注入
    - "survival_rules"

available_skills: {}                   # On-demand skills / 按需加载
```

### prompts/ — Prompt Customization / 提示词定制

Customize the LLM's writing style and behavioral constraints. Files prefixed with `head_` are sorted by filename and prepended to the system prompt.

自定义 LLM 的写作风格和行为约束。文件名以 `head_` 开头的会按文件名排序拼接到系统提示词头部。

```
prompts/
├── head_01_writing_style.md    # Writing style / 写作风格指引
├── head_02_constraints.md      # Behavioral constraints / 行为约束
└── tail_condensed.md           # Tail condensed prompt / 尾部压缩提示
```

Example `head_01_writing_style.md`:

```markdown
## Writing Style

- Third-person omniscient narration
- Classical wuxia/literary prose style
- Avoid modern slang and internet terminology
- Use Chinese quotation marks 「」 for dialogue
- Combat scenes: fast-paced, continuous flow
```

---

## Custom Extensions / 自定义扩展

### combat.py — Combat Formulas / 战斗公式

Place `combat.py` in the world directory to override default combat damage calculations.

在世界目录下放置 `combat.py` 可覆盖默认的战斗伤害计算公式。

```python
"""Custom combat formulas / 自定义战斗公式"""


def calculate_damage(attacker_attrs: dict, defender_attrs: dict,
                     base_damage: int, **kwargs) -> int:
    """Calculate final damage.

    Args:
        attacker_attrs: Attacker attributes {force, tenacity, agility, ...}
        defender_attrs: Defender attributes
        base_damage: Skill base damage
    Returns:
        Final damage value (non-negative integer)
    """
    attack = attacker_attrs.get("force", 10)
    defense = defender_attrs.get("tenacity", 10)
    # Non-linear damage formula / 非线性伤害公式
    damage = attack * attack / (attack + defense * 6) + base_damage
    return max(1, int(damage))


def get_stage_mult(stage_id: str) -> float:
    """Return combat multiplier for cultivation stage / 返回境界战斗系数。"""
    stage_multipliers = {
        "beginner": 1.0,
        "intermediate": 1.5,
        "advanced": 2.5,
        "master": 4.0,
    }
    return stage_multipliers.get(stage_id, 1.0)
```

The engine loads this via `world.get_world_module("combat")` on demand. Only public functions are used. Function signatures are flexible — the caller (CombatPlugin) passes args by convention.

引擎通过 `world.get_world_module("combat")` 按需加载，只使用模块中的公开函数。

### pricing.py — Pricing Formulas / 定价公式

```python
"""Custom pricing formulas / 自定义定价公式"""


def calc_price(rarity: int, level: int, **kwargs) -> int:
    """Calculate item sell price / 计算物品售价。"""
    base = 10 * level
    rarity_mult = 1 + (rarity / 100) ** 1.5
    return int(base * rarity_mult)
```

### creation_hook.py — Character Creation Hook / 角色创建钩子

Custom logic executed after character creation:

角色创建完成后执行的自定义逻辑：

```python
"""Post-creation processing / 角色创建后处理。"""


def on_character_created(route_id, character, character_manager, game_state, world):
    """Called after character creation.

    Args:
        route_id: Selected route ID
        character: Newly created character object
        character_manager: Character manager
        game_state: Game state
        world: World instance
    """
    # Set initial location / 设置初始位置
    character.location = get_start_location(route_id)

    # Remove NPC selected as player character / 移除已被选为玩家角色的 NPC
    if route_id == "protagonist_a":
        character_manager.remove("npc_protagonist_a")

    # Set NPC starting locations / 设置 NPC 初始位置
    for npc in character_manager.get_all_npcs():
        if hasattr(npc, 'default_location'):
            npc.location = npc.default_location


def get_start_location(route_id: str) -> str:
    """Return starting location based on route / 根据路线返回初始位置。"""
    locations = {
        "protagonist_a": "cloud_city",
        "protagonist_b": "sand_state",
    }
    return locations.get(route_id, "cloud_city")
```

### cultivation.yaml — Cultivation System / 修炼系统

Defines cultivation/growth progression. This is a world extension file auto-loaded from `_world_extensions`:

定义修炼/成长体系。这是一个世界扩展文件，引擎自动加载：

```yaml
# Realm/stage system / 境界/阶级系统
realms:
  - id: mortal
    name: "Mortal"
    order: 1
    base_qi_density: 0.1
    max_stage: 3
  - id: spirit
    name: "Spirit Realm"
    order: 2
    base_qi_density: 1.0
    max_stage: 6

# Cultivation stages / 修炼阶段
stages:
  - id: qi_refining
    name: "Qi Refining"
    realm: mortal
    order: 1
    sp_range: [0, 100]
    lifespan: 120
    power_multiplier: 1.0
    combat_mult: 1.0

  - id: foundation
    name: "Foundation Building"
    realm: mortal
    order: 2
    sp_range: [100, 500]
    lifespan: 200
    power_multiplier: 2.0
    combat_mult: 1.5

# Cultivation paths / 修炼道路
cultivation_paths:
  - id: sword
    name: "Sword Path"
    primary_attr: "force"
    resource_focus: "spiritual_power"
    model: "warrior"
    tag_rules:
      - tags: ["sword"]
        bonus: 1.2

  - id: formation
    name: "Formation Path"
    primary_attr: "divine_sense"
    resource_focus: "spiritual_power"
    model: "mage"
    tag_rules:
      - tags: ["formation"]
        bonus: 1.3

# Breakthrough rules / 突破规则
breakthrough_rules:
  min_sp_ratio: 1.0                   # SP must reach stage cap / 灵力必须达到阶段上限
  success_rate_base: 0.8
  fail_penalty: "sp_loss_10%"
```

### effect_affixes.yaml — Effect Affixes / 效果词条

Unified effect affix definitions shared by the ability and item systems:

统一效果词条定义，被技能和物品系统共享：

```yaml
effect_affixes:
  damage:
    description: "Deal damage"
    combat: true
    base: {power: 2.0}
    stack_increment: {power: 0.25}
    auto_cost:
      formula: "max(2, floor(power * power * 0.4))"
    auto_cooldown: "max(0, floor(power) - 1)"

  buff:
    description: "Increase attribute"
    combat: true
    base: {modifier: 0.1, duration: 2}
    stack_increment: {modifier: 0.05}
    default_stat: "force"
    default_duration: 2

  debuff:
    description: "Decrease attribute"
    combat: true
    base: {modifier: -0.1, duration: 2}
    stack_increment: {modifier: -0.05}
    default_stat: "tenacity"

  heal:
    description: "Restore health"
    combat: true
    base: {power: 1.5}
    stack_increment: {power: 0.2}

  shield:
    description: "Create shield"
    combat: true
    base: {amount: 10, duration: 2}
    stack_increment: {amount: 5}

  dispel:
    description: "Dispel effects"
    combat: true
    base: {count: 1}
    stack_increment: {count: 0.5}

  lifesteal:
    description: "Steal life"
    combat: true
    base: {ratio: 0.1}
    stack_increment: {ratio: 0.05}

# Exclusion rules / 互斥规则
__exclusions__:
  - ["buff", "debuff"]

# Cost scaling / 消耗缩放
__cost_scale__:
  stamina: {base: 3, per_power: 1.5}

# Value scaling / 数值增幅
__value_scale__:
  power: {base: 1.0, per_level: 1.1}
```

---

## Theme Customization / 主题定制

### theme/ Directory / theme 目录

```
theme/
├── theme.css          # Custom CSS / 自定义 CSS
├── fonts/             # Custom fonts / 自定义字体
│   └── custom.woff2
└── images/            # Custom images / 自定义图片
    └── bg.png
```

`theme.css` is auto-mounted by GameServer at `/static/theme/theme.css` and prioritized by the frontend.

`theme.css` 会由 GameServer 自动挂载，前端优先加载。

```css
/* theme.css example */
:root {
  --bg-primary: #1a1a2e;
  --text-primary: #e0e0e0;
  --accent-color: #e94560;
}

.narrative-text {
  font-family: "CustomFont", serif;
  line-height: 1.8;
}
```

---

## Character Creation Page / 角色创建页面

### character_creation/ Directory / character_creation 目录

```
character_creation/
├── character_creation.yaml    # Creation config / 创建流程配置
└── creation.html              # Creation page HTML / 创建页面
```

#### character_creation.yaml

```yaml
title: "Create Your Character"

# Route selection / 路线选择
routes:
  - id: warrior_path
    title: "Path of the Warrior"
    subtitle: "Conquer through strength"
    description: "Train your body, overcome all through pure martial power"
    locked: false
    template_id: "warrior_template"
    narrative_badge: "W"
    narrative_text:
      - "You were strong from childhood"
      - "Taken in by the martial arts master"
    narrative_highlights: ["Martial Hall", "Way of Power"]
    narrative_meta: "Combat-focused start"

  - id: mage_path
    title: "Path of the Sage"
    subtitle: "Commune with spiritual energy"
    description: "Sense the world's spiritual energy, begin your cultivation"
    locked: false
    template_id: "mage_template"
    narrative_badge: "S"
    narrative_text:
      - "Your talent was discovered early"
      - "A passing cultivator sensed your spiritual roots"
    narrative_highlights: ["Spiritual Roots", "Celestial Fate"]
    narrative_meta: "Magic-focused start"

# Character templates / 角色模板
templates:
  - id: warrior_template
    name: "Warrior"
    apply:
      level: 1
      attrs:
        force: 18
        tenacity: 16
        agility: 12
        vitality: 120
        max_vitality: 120
      abilities: [basic_attack, heavy_slash]
    opening_text: "You stand before the martial hall, ready to begin your journey"

  - id: mage_template
    name: "Sage"
    apply:
      level: 1
      attrs:
        force: 10
        tenacity: 10
        agility: 12
        spiritual_power: 50
        vitality: 80
        max_vitality: 80
      abilities: [basic_attack, fireball]
    opening_text: "You sit cross-legged, beginning to sense the world's spiritual energy"

# Form fields / 表单字段
fields:
  - key: name
    label: "Character Name"
    type: text
    required: true
  - key: gender
    label: "Gender"
    type: select
    options:
      - value: male
        label: "Male"
      - value: female
        label: "Female"
  - key: background
    label: "Background"
    type: textarea
    required: false
    placeholder: "Describe your character's backstory (optional)"
```

#### creation.html

Custom HTML template for the character creation page. Auto-loaded by the engine.

自定义角色创建页面的 HTML 模板，引擎会自动加载。

---

## World Loading Flow / 世界加载流程

The world loading order during engine startup (`GameWorld.load()`):

引擎启动时的世界加载顺序：

```
 1. setting.yaml                → world.setting
 2. items/*.yaml                 → world.items (auto-scan, skip _ prefix and config files)
 3. abilities/*.yaml             → world.abilities (auto-scan, skip _ prefix and config files)
 4. abilities/_templates.yaml    → world.ability_templates/budget/cost_scale/...
 5. effect_affixes.yaml          → world.effect_affixes/exclusions/...
 6. abilities/_tags.yaml         → world.ability_tag_groups/tag_cost_map
 7. characters/character_schema.yaml → world.attributes/fields/elements/...
 8. characters/_tags.yaml        → world.character_tag_groups
 9. characters/fixed/            → world._char_manager (auto-scan all YAML)
10. items/equip_slots.yaml       → world.equip_slots
11. items/item_categories.yaml   → world.item_categories
12. items/item_rarities.yaml     → world.item_rarities
13. items/_templates.yaml        → world.consumable_templates/budget/...
14. items/_tags.yaml             → world.item_tag_groups
15. items/special_items.yaml     → world.special_items
16. items/preset_equipment.yaml  → world.special_items (appended)
17. abilities/ability_categories.yaml → world.ability_categories
18. abilities/ability_rarities.yaml → world.ability_rarities
19. cultivation.yaml             → world._world_extensions["cultivation"]
20. calendar.yaml                → world._calendar_config
21. character_creation/character_creation.yaml → world._creation_config
```

Custom Python modules (`combat.py`, `pricing.py`, `creation_hook.py`) are loaded on demand, not in this flow.

自定义 Python 模块按需加载，不在此流程中。

### Auto-Scan Rules / 自动扫描规则

- YAML files in `items/` and `abilities/` are automatically scanned
- Files starting with `_` are config files (`_templates.yaml`, `_tags.yaml`), not loaded as content
- Named config files are also skipped (e.g. `item_categories.yaml`, `equip_slots.yaml`)
- Content entries are registered by `id` field as unique keys in dictionaries

- `items/` 和 `abilities/` 目录下的 YAML 文件会被自动扫描
- 以 `_` 开头的文件是配置文件，不被当作内容
- 命名的配置文件也被跳过（如 `item_categories.yaml`、`equip_slots.yaml`）
- 内容文件中的条目通过 `id` 字段作为唯一标识注册

---

## From Template to Full World / 从模板到完整世界

### Template World (Minimal) / Template World（最小世界）

`template_world` provides the minimum viable configuration:

- Generic fantasy attributes (HP/MP/Strength/Defense/Speed)
- Basic abilities and items
- Simple map
- Character creation page
- No cultivation, economy, or element system

### Wuji World (Full Example) / Wuji World（完整示例）

`wuji_world` showcases the engine's full capabilities:

- 14 cultivation realms + 11 cultivation paths
- Five-element interaction system
- Non-linear combat damage formula
- Complete economy/pricing system
- 7 effect affix types
- Tag-driven ability/item generation
- Multi-route character creation
- Custom theme and fonts
- Rich NPC, event, and map data

### Recommended Development Path / 建议的开发路径

1. Copy base structure from `template_world` / 从 `template_world` 复制基础结构
2. Modify `setting.yaml` and `character_schema.yaml` to establish base attributes / 修改基本属性
3. Add basic abilities and items / 添加基础技能和物品
4. Build the map / 构建地图
5. Write prompts (`prompts/`) to set the writing style / 编写提示词定调风格
6. Add `combat.py` for custom combat formulas (optional) / 自定义战斗公式（可选）
7. Add world extension systems (`cultivation.yaml`, etc., optional) / 世界扩展（可选）
8. Add `theme/` to customize UI appearance (optional) / UI 主题（可选）
9. Add character creation page (optional) / 角色创建页面（可选）
10. Reference `wuji_world` to gradually enrich content / 参考 `wuji_world` 丰富内容
