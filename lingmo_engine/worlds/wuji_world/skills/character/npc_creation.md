---
name: npc_creation
description: 创建完整 NPC 的分步引导流程
type: guided_workflow
priority: 10
checklist:
  - 创建角色骨架（基本信息 + 基准属性）
  - 审阅并微调属性值（可选）
  - 查询/创建技能并分配
  - 查询/生成装备并分配
  - 最终确认
---

# NPC 创建引导

当剧情需要引入新角色时，请严格按以下步骤执行。每步只做一件事，不要一次完成所有内容。

> **前置工具依赖**：本流程使用以下工具（需对应插件已加载）：
> - `create_character` / `update_character_field` — character 插件（必需）
> - `query_entity` — entity_query 插件（可选，缺失时跳过查询直接创建）
> - `create_ability` — combat 插件（可选，用于创建新技能）
> - `generate_equipment` — crafting 插件（可选，用于生成新装备）

## 先天属性说明

属性代表角色的**先天资质**（类似现实中的智力、体格），与修炼境界无关。以普通人 50 为基准：
- 30~60：大多数人的正常范围
- 60~80：资质出众
- 80~90：罕见天才（凡人也可能有）
- 90~100：万中无一的绝世资质

凡人也可能有极高属性，修士属性未必高于凡人。境界通过系数增幅属性，而非属性本身代表实力。

---

## □ Step 1：创建角色骨架

调用 `create_character`，只需提供以下信息：

**必填：**
- `name`：角色姓名
- `char_type`：`npc`（统一为持久角色，自动保存到存档）
- `level`：境界阶位（0~13）
- `background`：背景故事
- `personality`：性格描述

**属性：** 填写基准值即可（参考上方先天属性说明）。

**不要填写 abilities 和 equipment**，留空后续步骤补充：
```yaml
abilities: []
equipment: {}
```

调用后记住返回的 **角色 ID**，后续步骤需要。

---

## □ Step 2：审阅属性（可跳过）

审阅 Step 1 返回的属性值。如需微调个别属性（例如某个角色特别强壮）：
- 调用 `update_character_field(character_id=角色ID, field="attrs.属性名", value="新值", reason="微调原因")`

如属性无特殊需求，**直接跳过此步**。

---

## □ Step 3：分配技能

为角色分配合适的技能组合。对每个技能重复以下流程：

**先查再建再配：**
1. `query_entity(name="技能名", entity_type="ability")` → 查找已有技能
2. 找到 → 直接获取技能 ID
3. 未找到 → 调用 `create_ability` 创建新技能，获取返回的技能 ID
4. `update_character_field(character_id=角色ID, field="abilities", value="+技能ID", reason="分配技能")` → 将技能分配给角色

重复直到技能搭配完整。一般 2~4 个技能即可。

---

## □ Step 4：分配装备

为角色分配合适的装备。对每件装备重复以下流程：

**先查再建再配：**
1. `query_entity(name="装备名", entity_type="item")` → 查找已有装备
2. 找到 → 直接获取装备 ID
3. 未找到 → 调用 `generate_equipment` 生成新装备，获取返回的装备 ID
4. `update_character_field(character_id=角色ID, field="equipment", value='{"部位ID": "装备ID"}', reason="分配装备")` → 将装备分配给角色

装备部位：life_treasure（法宝）、clothing（服饰）、accessory（配饰）、mount（坐骑）。
示例：`value='{"life_treasure": "飞剑", "clothing": "青布道袍"}'`

---

## □ Step 5：最终确认

- 检查角色是否完整（有属性、有技能、有装备）
- 如果是战斗场景的敌人，应使用 `spawn_hostiles`（模板生成）或 `spawn_npcs`（已有 NPC 对战）而非本流程
- 创建完成后在后续叙事中自然引入该角色
