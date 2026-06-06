"""通用物品定价引擎 — 基础价值为基准，稀有度加成封顶。"""


class PriceEngine:
    """通用定价引擎，接受配置字典，不含世界观硬编码。

    公式: 价格 = 基础价值 × base_ratio × (1 + rarity / 100 × rarity_max_bonus)
    """

    def __init__(self, config: dict) -> None:
        self._ratio = config.get("base_ratio", config.get("spirit_to_stone_ratio", 1.0))
        self._max_bonus = config.get("rarity_max_bonus", 0.5)

    def calc_price(self, base_value: int, rarity: int) -> int:
        """根据基础价值和稀有度计算价格。"""
        bonus = rarity / 100.0 * self._max_bonus
        return max(1, int(base_value * self._ratio * (1 + bonus)))

    def calc_item_price(self, item: dict) -> int:
        """从物品字典自动提取基础价值和稀有度计算价格。

        无基础价值的物品回退到 sell_price。
        """
        base_value = item.get("base_value", item.get("spirit_power", 0))
        rarity = item.get("rarity", 0)
        if base_value <= 0:
            return item.get("sell_price", 0)
        return self.calc_price(base_value, rarity)