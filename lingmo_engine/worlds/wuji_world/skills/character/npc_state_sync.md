---
name: npc_state_sync
description: NPC 状态同步指南 — 引导 AI 在 NPC 登场前同步状态并根据剧情调整
type: generation
priority: 20
---

# NPC 状态同步

当叙事中已有 NPC 重新登场时，**必须按以下两步操作**：

## Step 1：调用 sync_npc_state 获取基准值

以下场景**必须**在 NPC 登场前调用 `sync_npc_state(character_id=角色ID)`：

- 场景切换后 NPC 再次出现
- 时间推进后与已有 NPC 互动
- 故事线回归，涉及之前已创建的 NPC

系统会自动计算离场期间的基准状态变化（灵力增长、体力恢复、突破冷却衰减），并返回变更摘要。

不需要调用的场景：
- 刚创建的新 NPC（状态已是最新）
- NPC 在同一场景内连续互动（无时间推进）
- 临时角色（monster 等）

## Step 2：根据剧情需要调整

`sync_npc_state` 仅计算**正常情况下的基准变化**。你需要根据 NPC 离场期间的剧情发展，使用 `update_character_field` 对结果进行调整。

**常见调整场景：**

| 剧情情况 | 建议调整 |
|---|---|
| NPC 离场期间遭遇重创/中毒 | 降低 vitality，不要恢复满 |
| NPC 被困/受刑 | 降低 vitality、stamina，可能扣减灵力 |
| NPC 获得奇遇/秘宝 | 额外增加 spiritual_power |
| NPC 突破瓶颈 | 增加 level（通过 update_character_field） |
| NPC 疯狂修炼 | 增加额外 spiritual_power |
| NPC 离场期间生病 | 降低 vitality，不恢复满 |
| NPC 一直正常生活 | 无需调整，基准值即可 |

**调整示例：**
```
# NPC 离场30天，但期间被敌人俘虏受刑
sync_npc_state(character_id=5)          # 先同步基准值
update_character_field(character_id=5, field="attrs.vitality", value="30", reason="被俘期间受刑，生机未恢复")
update_character_field(character_id=5, field="attrs.stamina", value="20", reason="长期困顿，体力衰退")
```

## Step 3：寿命判定（时间跨度超寿命时必须执行）

各境界寿命上限：

| 境界 | 寿命 |
|---|---|
| 凡人 | 100 |
| 练气期 | 200 |
| 筑基期 | 400 |
| 金丹期 | 900 |
| 元婴期 | 1,900 |
| 化神期 | 4,900 |
| 炼虚期 | 14,900 |
| 合体期 | 44,900 |
| 大乘期 | 144,900 |
| 渡劫期及以上 | ∞ |

当离场天数 **超过** NPC 当前境界的寿命上限时，必须从以下两种结局中选择一种：

### 结局 A：寿终正寝，角色退场

NPC 寿元耗尽，自然死亡。这为剧情增添了沧桑感和时间流逝的实感。

```
sync_npc_state(character_id=5)
update_character_field(character_id=5, field="is_alive", value="false", reason="寿元耗尽，坐化于洞府之中")
```

在叙事中自然描述 NPC 已故的消息（如其他角色提及、发现遗物、看到荒废的居所等）。

### 结局 B：增补奇遇，合理化登场

为 NPC 编织一段合理的奇遇来解释其存活，使其继续参与剧情。奇遇必须与世界观设定自洽。

**合理的奇遇示例：**
- 偶得延寿丹药（如造化丹、寿元果）
- 遭遇仙人点化，突破至更高境界（延寿）
- 误入秘境，秘境中时间流速极慢
- 被高人封印保全，刚刚解封
- 修炼了某种延寿秘法

选择此结局时，需要同时调整 NPC 状态以配合奇遇：

```
sync_npc_state(character_id=5)
# 示例：NPC 因仙人点化突破到元婴期，寿元大幅延长
update_character_field(character_id=5, field="level", value="5", reason="闭关百年，受仙人点化突破至元婴期，寿元延展")
```

## 注意事项

- 每个 NPC 一次登场只需同步一次
- 系统自动判断是否需要更新（经过天数 ≤ 0 时直接跳过，误调用无副作用）
- 凡人/无灵根 NPC 只会恢复体力，不会增长灵力
- 如果基准值已符合剧情预期，无需额外调整
- 寿命判定基于境界寿命上限，非 `lifespan_remaining` 属性
