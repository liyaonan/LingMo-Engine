"""物品类继承体系：Item基类 + EquipmentItem/ConsumableItem/MaterialItem子类。"""

from __future__ import annotations

from dataclasses import dataclass, field, fields


def _filter_dataclass_fields(cls, data: dict) -> dict:
    """过滤字典，仅保留 dataclass 的字段，防止意外关键字导致构造崩溃。"""
    valid_keys = {f.name for f in fields(cls)}
    return {k: v for k, v in data.items() if k in valid_keys}


@dataclass
class Cost:
    """使用代价"""
    resource: str    # mp / hp / gold / 世界自定义属性
    amount: int      # 消耗量


@dataclass
class Effect:
    """使用效果 — 与技能效果字段统一，可直接传入 resolve_effect"""
    type: str                       # damage / fixed_damage / heal / buff / debuff
    target: str = "self"            # self / enemy / all_enemy / all_ally
    power: float = 1.0              # 倍率（伤害/治疗用）
    value: float = 0                # 固定值（fixed_damage / 固定治疗 / 突破加成）
    scale_stat: str | None = None   # 基于哪个属性缩放
    stat: str | None = None         # buff 目标属性 / heal 目标属性（默认 hp）
    modifier: float | None = None   # buff 百分比修改
    element: str | None = None      # 元素类型（单元素，旧格式）
    elements: list[dict] | None = None  # 多元素复合（新格式）
    duration: int = 0               # >0 时创建持久 buff
    status: str | None = None       # frozen / stunned / ...
    count: int | None = None        # 驱散/治疗数量（dispel / cure_status）
    chance: float | None = None     # 触发概率（stun）
    ratio: float | None = None      # 吸血比例（lifesteal）
    mode: str | None = None         # 驱散模式（dispel: all / buff / debuff）
    name: str | None = None         # 效果显示名（如 stun 的"业火缠身"）

    DEFAULT_STAT = {"buff": "force", "debuff": "tenacity"}

    def __post_init__(self):
        if self.stat is None and self.type in self.DEFAULT_STAT:
            self.stat = self.DEFAULT_STAT[self.type]


@dataclass
class BuffDef:
    """被动效果定义"""
    id: str
    type: str              # stat_mod / regen / immunity / on_hit / ...
    params: dict = field(default_factory=dict)
    duration: int | str = "permanent"  # 持续回合数 | "permanent"


class Item:
    """物品基类"""

    def __init__(self, data: dict):
        self.id: str = data["id"]
        self.name: str = data.get("name", "")
        self.category: str = data.get("category", "material")
        self.rarity: int = data.get("rarity", 0)
        self.description: str = data.get("description", "")
        self.sell_price: int = data.get("sell_price", 0)
        self.quest_flag: str | None = data.get("quest_flag")
        self.is_key_item: bool = data.get("is_key_item", False)
        self.icon: str = data.get("icon", "")
        self.tags: list[str] = data.get("tags", [])

    @property
    def is_equipment(self) -> bool:
        return False

    @property
    def is_consumable(self) -> bool:
        return False

    @property
    def is_material(self) -> bool:
        return False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "rarity": self.rarity,
            "description": self.description,
            "sell_price": self.sell_price,
            "quest_flag": self.quest_flag,
            "is_key_item": self.is_key_item,
            "icon": self.icon,
            "is_equipment": self.is_equipment,
            "is_consumable": self.is_consumable,
            "is_material": self.is_material,
            "tags": self.tags,
        }


class EquipmentItem(Item):
    """装备物品"""

    def __init__(self, data: dict):
        super().__init__(data)
        self.equip_slot: str = data.get("equip_slot", "")
        self.stat_bonus: dict[str, int] = data.get("stat_bonus", {})
        self.narrative_effects: dict[str, str] = data.get("narrative_effects", {})
        self.buffs: list[BuffDef] = [
            BuffDef(**_filter_dataclass_fields(BuffDef, b)) for b in data.get("buffs", [])
        ]
        self.abilities: list[str] = data.get("abilities", data.get("skills", []))
        self.equip_requirements: dict[str, list[str]] = data.get("equip_requirements", {})

    @property
    def is_equipment(self) -> bool:
        return True

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "equip_slot": self.equip_slot,
            "stat_bonus": self.stat_bonus,
            "narrative_effects": self.narrative_effects,
            "buffs": [{"id": b.id, "type": b.type, "params": b.params, "duration": b.duration} for b in self.buffs],
            "abilities": self.abilities,
            "equip_requirements": self.equip_requirements,
        })
        return d


class ConsumableItem(Item):
    """消耗品"""

    def __init__(self, data: dict):
        super().__init__(data)
        self.costs: list[Cost] = [
            Cost(**_filter_dataclass_fields(Cost, c)) for c in data.get("costs", [])
        ]
        self.effects: list[Effect] = [
            Effect(**_filter_dataclass_fields(Effect, e)) for e in data.get("effects", [])
        ]
        self.combat_only: bool = data.get("combat_only", False)
        self.creator_stats: dict[str, int] = data.get("creator_stats", {})

    @property
    def is_consumable(self) -> bool:
        return True

    def to_dict(self) -> dict:
        d = super().to_dict()

        def _effect_to_dict(e: Effect) -> dict:
            ed: dict = {
                "type": e.type,
                "target": e.target,
            }
            if e.power != 1.0:
                ed["power"] = e.power
            if e.value:
                ed["value"] = e.value
            if e.scale_stat:
                ed["scale_stat"] = e.scale_stat
            if e.stat:
                ed["stat"] = e.stat
            if e.modifier is not None:
                ed["modifier"] = e.modifier
            if e.element:
                ed["element"] = e.element
            if e.elements:
                ed["elements"] = e.elements
            if e.duration:
                ed["duration"] = e.duration
            if e.status:
                ed["status"] = e.status
            if e.count is not None:
                ed["count"] = e.count
            if e.chance is not None:
                ed["chance"] = e.chance
            if e.ratio is not None:
                ed["ratio"] = e.ratio
            if e.mode is not None:
                ed["mode"] = e.mode
            if e.name:
                ed["name"] = e.name
            return ed

        d.update({
            "costs": [{"resource": c.resource, "amount": c.amount} for c in self.costs],
            "effects": [_effect_to_dict(e) for e in self.effects],
            "combat_only": self.combat_only,
            "creator_stats": self.creator_stats,
        })
        return d


class MaterialItem(Item):
    """材料/一般物品"""

    def __init__(self, data: dict):
        super().__init__(data)
        self.material_type: str = data.get("material_type", "")
        self.stackable: bool = data.get("stackable", True)
        self.quest_id: str | None = data.get("quest_id")

    @property
    def is_material(self) -> bool:
        return True

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "material_type": self.material_type,
            "stackable": self.stackable,
            "quest_id": self.quest_id,
        })
        return d


class ItemSystem:
    """物品系统：加载、查询、分类、稀有度"""

    _pricing_fn = None

    def __init__(self):
        self._items: dict[str, Item] = {}
        self._categories: list[dict] = []
        self._rarities: list[dict] = []

    @classmethod
    def set_pricing_fn(cls, fn) -> None:
        """注入世界定价函数，替代硬编码导入。"""
        cls._pricing_fn = fn

    def load_items(self, raw_items: list[dict]) -> None:
        """从 YAML 原始数据加载物品"""
        self._items.clear()
        for data in raw_items:
            # sell_price: auto → 通过定价引擎自动计算
            if data.get("sell_price") == "auto":
                data["sell_price"] = self._resolve_auto_price(data)
            category = data.get("category", "material")
            if category == "equipment":
                item = EquipmentItem(data)
            elif category == "consumable":
                item = ConsumableItem(data)
            else:
                item = MaterialItem(data)
            self._items[item.id] = item

    @classmethod
    def _resolve_auto_price(cls, data: dict) -> int:
        """解析 sell_price: auto，调用世界定价引擎。"""
        if cls._pricing_fn is not None:
            return cls._pricing_fn(data)
        # 向后兼容：无定价函数时尝试默认世界
        try:
            from lingmo_engine.worlds.wuji_world.pricing import calc_price
            spirit = data.get("spirit_power", 0)
            rarity = data.get("rarity", 0)
            if spirit <= 0:
                return 0
            return calc_price(spirit, rarity)
        except ImportError:
            return 0

    def load_categories(self, raw: dict) -> None:
        self._categories = raw.get("categories", [])

    def load_rarities(self, raw: dict) -> None:
        self._rarities = raw.get("rarities", [])

    def get_item(self, item_id: str) -> Item | None:
        return self._items.get(item_id)

    def get_item_by_name(self, name: str) -> Item | None:
        """根据物品名称查找物品（精确匹配）。"""
        for item in self._items.values():
            if item.name == name:
                return item
        return None

    def get_items_by_category(self, category: str) -> list[Item]:
        return [i for i in self._items.values() if i.category == category]

    def get_all_items(self) -> list[Item]:
        return list(self._items.values())

    def get_categories(self) -> list[dict]:
        return self._categories

    def get_rarities(self) -> list[dict]:
        return self._rarities

    def get_rarity_info(self, rarity: int) -> dict:
        """根据稀有度数值匹配稀有度层级"""
        for r in self._rarities:
            if r["min"] <= rarity <= r["max"]:
                return r
        return {"id": "common", "name": "普通", "color": "#a0a0a0"}

    def register_item(self, item: Item) -> None:
        """动态注册物品（自定义消耗品等）。"""
        self._items[item.id] = item

    def get_items_for_slot(self, slot_id: str, inventory: list[dict]) -> list[Item]:
        """获取背包中可装备到指定槽位的物品"""
        result = []
        for entry in inventory:
            item = self._items.get(entry["item_id"])
            if item and item.is_equipment and item.equip_slot == slot_id:
                result.append(item)
        return result

    def get_items_by_tag(self, tag: str) -> list[Item]:
        """按标签查询物品"""
        return [i for i in self._items.values() if tag in i.tags]
