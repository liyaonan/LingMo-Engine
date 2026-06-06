"""战斗实体定义。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ActiveBuff:
    """持久效果（挂在 Combatant.buffs 上）"""
    id: str
    name: str
    remaining: int              # 剩余回合数
    caster_name: str            # 施放者名（日志用）
    effect: dict                # 原始 effect 定义，tick 时重新计算


@dataclass
class TargetDelta:
    """单次效果对单个目标的属性变化记录"""
    target_name: str
    stat: str
    delta: int
    new_value: int
    is_pursuit: bool = False
    name: str = ""


@dataclass
class Combatant:
    """战斗参与者"""
    name: str
    hp: int
    max_hp: int
    level: int = 1
    is_player: bool = False
    attrs: dict[str, int] = field(default_factory=dict)
    abilities: list[str] = field(default_factory=list)
    buffs: list[ActiveBuff] = field(default_factory=list)
    items: list[dict] = field(default_factory=list)
    cooldowns: dict[str, int] = field(default_factory=dict)
    defending: bool = False
    shield: int = 0
    loot_table: list[dict] = field(default_factory=list)
    equipment_abilities: list[str] = field(default_factory=list)
    # 通用扩展字段（修仙世界传入 cultivation_stage/path/spiritual_roots 等，非修仙世界留空）
    extra: dict[str, object] = field(default_factory=dict)
    side: str = "player"            # "player" | "ally" | "enemy"
    is_ai_controlled: bool = False  # AI 自动行动标记

    @property
    def is_alive(self) -> bool:
        return self.hp > 0


def combatant_from_character(c, is_player: bool = False,
                             attrs_schema: dict | None = None,
                             side: str = "player") -> "Combatant":
    """从 Character 构造战斗 Combatant（schema 驱动）。"""
    # 从 schema 找到 health pool 属性名
    hp_key = "hp"
    if attrs_schema:
        for name, defn in attrs_schema.items():
            if defn.get("combat_type") == "pool" and defn.get("core"):
                pair = defn.get("pair", "")
                if pair:
                    hp_key = name
                    break

    hp = c.attrs.get(hp_key, 1)
    max_hp = c.attrs.get(f"max_{hp_key}", hp)
    # 优先用 schema pair 字段获取 max key
    if attrs_schema and hp_key in attrs_schema:
        pair = attrs_schema[hp_key].get("pair", "")
        if pair:
            max_hp = c.attrs.get(pair, hp)

    # 排除 hp pool 对（已在 Combatant 独立字段中）
    max_key = attrs_schema[hp_key].get("pair", f"max_{hp_key}") if attrs_schema else f"max_{hp_key}"
    exclude_keys = {hp_key, max_key}

    # 仅保留有战斗意义的属性
    if attrs_schema:
        _keep_keys = set()
        for name, defn in attrs_schema.items():
            if defn.get("combat_type") or defn.get("combat_role"):
                _keep_keys.add(name)
        for name in list(_keep_keys):
            pair = attrs_schema[name].get("pair", "")
            if pair:
                _keep_keys.add(pair)
        combat_attrs = {
            k: v for k, v in c.attrs.items()
            if (k in _keep_keys or k not in attrs_schema) and k not in exclude_keys
        }
    else:
        combat_attrs = {
            k: v for k, v in c.attrs.items()
            if k not in exclude_keys
        }
    return Combatant(
        name=c.name,
        hp=hp,
        max_hp=max_hp,
        level=c.level,
        is_player=is_player,
        attrs=combat_attrs,
        abilities=list(c.abilities),
        loot_table=list(c.loot_table) if c.loot_table else [],
        extra=dict(c.extra),
        side=side,
        is_ai_controlled=(side == "ally" and not is_player),
    )
