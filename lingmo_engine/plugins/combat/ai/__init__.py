"""敌人AI策略系统"""

from abc import ABC, abstractmethod
from lingmo_engine.plugins.combat.engine import Combatant


class EnemyAIStrategy(ABC):
    """敌人AI策略抽象接口"""

    @abstractmethod
    def choose_action(
        self,
        enemy: Combatant,
        player: Combatant,
        allies: list[Combatant],
        ability_system=None,
        attrs_schema: dict | None = None,
    ) -> dict:
        """根据当前战场状态选择行动

        Args:
            enemy: 当前行动的敌人
            player: 玩家
            allies: 所有存活友方
            ability_system: AbilitySystem 实例，用于查询技能详情
            attrs_schema: combat_role 属性映射，用于按 role 查找属性名

        Returns:
            dict: {"type": "attack"|"ability"|"item"|"defend",
                   "ability_id": str (可选),
                   "item_id": str (可选),
                   "target_index": int (可选)}
        """
        ...
