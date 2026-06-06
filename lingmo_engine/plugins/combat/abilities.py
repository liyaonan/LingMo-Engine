# lingmo_engine/plugins/combat/abilities.py

"""技能系统 - 技能定义加载、冷却管理、多资源消耗检查"""

from typing import Optional


class AbilitySystem:
    """技能系统：从世界配置加载技能，管理冷却和多资源消耗检查"""

    def __init__(self, abilities_data: list[dict], custom_abilities: dict | None = None):
        self._abilities: dict[str, dict] = {}
        for ability in abilities_data:
            self._abilities[ability["id"]] = ability
        self._custom_abilities: dict[str, dict] = custom_abilities or {}

    def get_ability(self, ability_id: str) -> Optional[dict]:
        """获取技能定义（custom_abilities 优先，world.abilities 兜底）"""
        ability = self._custom_abilities.get(ability_id)
        if ability is not None:
            return ability
        return self._abilities.get(ability_id)

    def set_custom_abilities(self, custom_abilities: dict) -> None:
        """更新自定义技能引用（战斗开始时调用，确保 AbilitySystem 可见最新 custom_abilities）。"""
        self._custom_abilities = custom_abilities or {}

    def get_all_abilities(self) -> list[dict]:
        """获取所有技能（固定 + 生成）"""
        combined = list(self._abilities.values())
        combined.extend(self._custom_abilities.values())
        return combined

    def get_player_available_abilities(
        self, player_ability_ids: list[str],
        attrs: dict[str, int],
        hp: int,
        cooldowns: dict[str, int],
        level: int = 1,
        scale_func: object = None,
    ) -> list[dict]:
        """获取玩家当前可用的技能列表（已学且资源足够且未冷却）

        返回的技能附带展开后的 scaled_costs（供前端显示）。
        """
        available = []
        for ability_id in player_ability_ids:
            ability = self.get_ability(ability_id)
            if ability is None:
                continue
            if cooldowns.get(ability_id, 0) > 0:
                continue
            if not self._check_costs(ability, attrs, hp, level, scale_func):
                continue
            # 展开消耗（浅拷贝 + 替换 costs）
            expanded = self._expand_costs(ability, level, scale_func)
            available.append(expanded)
        return available

    def can_use(
        self, ability_id: str,
        attrs: dict[str, int],
        hp: int,
        cooldowns: dict[str, int],
        level: int = 1,
        scale_func=None,
    ) -> tuple[bool, str]:
        """检查是否可使用技能，返回(可用, 原因)"""
        ability = self.get_ability(ability_id)
        if ability is None:
            return False, "技能不存在"
        if cooldowns.get(ability_id, 0) > 0:
            return False, "技能冷却中"
        if not self._check_costs(ability, attrs, hp, level, scale_func):
            return False, "资源不足"
        return True, ""

    def _check_costs(self, ability: dict, attrs: dict[str, int], hp: int,
                     level: int = 1, scale_func=None) -> bool:
        """检查技能的所有 costs 是否满足（含等级缩放）"""
        for cost in ability.get("costs", []):
            resource = cost["resource"]
            base = cost.get("amount", 0)
            if base <= 0:
                continue
            actual = scale_func(base, level) if scale_func else base
            if resource == "hp":
                if hp < actual:
                    return False
            else:
                if attrs.get(resource, 0) < actual:
                    return False
        return True

    def _expand_costs(self, ability: dict, level: int, scale_func) -> dict:
        """返回技能浅拷贝，costs 替换为缩放后的值。"""
        expanded_costs = []
        for cost in ability.get("costs", []):
            base = cost.get("amount", 0)
            actual = scale_func(base, level) if scale_func else base
            expanded_costs.append({
                "resource": cost["resource"],
                "amount": max(1, actual) if base > 0 else 0,
            })
        return {**ability, "costs": expanded_costs, "effects": [dict(e) for e in ability.get("effects", [])]}

    def get_ability_target_type(self, ability_id: str) -> str:
        """获取技能目标类型（从第一个 effect 的 target 推导）"""
        ability = self.get_ability(ability_id)
        if ability is None:
            return "enemy"
        effects = ability.get("effects", [])
        return effects[0].get("target", "enemy") if effects else "enemy"

    def is_self_target(self, ability_id: str) -> bool:
        """技能是否以自身为目标"""
        return self.get_ability_target_type(ability_id) == "self"
