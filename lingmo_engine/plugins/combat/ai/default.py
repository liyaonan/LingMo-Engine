"""默认敌人AI策略：HP低用药 → 技能 → 普攻"""

import random
from lingmo_engine.plugins.combat.ai import EnemyAIStrategy
from lingmo_engine.plugins.combat.engine import Combatant


class DefaultAIStrategy(EnemyAIStrategy):
    """内置默认AI策略

    优先级：
    1. HP低于30%且有恢复物品 → 使用物品
    2. 有可用技能（冷却完毕且MP足够）→ 随机释放
    3. 默认普攻
    """

    def choose_action(
        self,
        enemy: Combatant,
        player: Combatant,
        allies: list[Combatant],
        ability_system=None,
        attrs_schema: dict | None = None,
    ) -> dict:
        hp_ratio = enemy.hp / enemy.max_hp if enemy.max_hp > 0 else 1.0

        if hp_ratio < 0.3 and enemy.items:
            heal_items = [
                item for item in enemy.items
                if any(e.get("type") == "heal" for e in item.get("effects", []))
            ]
            if heal_items:
                return {"type": "item", "item_id": heal_items[0]["id"]}

        available_abilities = []
        for ability_id in enemy.abilities:
            ability_data = ability_system.get_ability(ability_id) if ability_system else None
            if ability_data is None:
                continue
            if enemy.cooldowns.get(ability_id, 0) > 0:
                continue
            # 检查所有 costs
            can_afford = True
            for cost in ability_data.get("costs", []):
                resource = cost["resource"]
                amount = cost.get("amount", 0)
                if resource == "hp":
                    if enemy.hp < amount:
                        can_afford = False
                        break
                else:
                    if enemy.attrs.get(resource, 0) < amount:
                        can_afford = False
                        break
            if can_afford:
                available_abilities.append((ability_id, ability_data))

        if available_abilities:
            ability_id, ability_data = random.choice(available_abilities)
            action = {"type": "ability", "ability_id": ability_id}
            effects = ability_data.get("effects", [])
            if effects and effects[0].get("target") in ("enemy", "all_enemy"):
                action["target_index"] = 0
            return action

        return {"type": "attack", "target_index": 0}
