from pathlib import Path
import yaml


class CultivationSchema:
    """封装 cultivation.yaml，提供结构化查询接口"""

    def __init__(self, world_dir: str) -> None:
        path = Path(world_dir) / "cultivation.yaml"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                self._raw = yaml.safe_load(f) or {}
        else:
            self._raw = {}

    def get_stage(self, stage_id: str) -> dict | None:
        for s in self._raw.get("stages", []):
            if s["id"] == stage_id:
                return s
        return None

    def get_next_stage(self, stage_id: str) -> dict | None:
        stage = self.get_stage(stage_id)
        if not stage or not stage.get("breakthrough_to"):
            return None
        return self.get_stage(stage["breakthrough_to"])

    def get_root_quality(self, root_ids: list[str]) -> dict:
        n = len(root_ids)
        return self._raw.get("spiritual_roots", {}).get("count_to_quality", {}).get(n, {})

    def get_path(self, path_id: str) -> dict | None:
        return self._raw.get("cultivation_paths", {}).get(path_id)

    def get_breakthrough_rule(self, from_id: str, to_id: str) -> dict | None:
        key = f"{from_id}_to_{to_id}"
        return self._raw.get("breakthrough_rules", {}).get("per_transition", {}).get(key)

    def get_breakthrough_modifiers(self) -> list[dict]:
        return self._raw.get("breakthrough_rules", {}).get("general", {}).get("modifier_sources", [])

    def is_valid_root(self, root_id: str) -> bool:
        basics = {e["id"] for e in self._raw.get("spiritual_roots", {}).get("basic_elements", [])}
        variants = {e["id"] for e in self._raw.get("spiritual_roots", {}).get("variant_elements", [])}
        return root_id in basics or root_id in variants

    def is_generating(self, source: str, target: str) -> bool:
        chain = self._raw.get("element_interactions", {}).get("generation_chain", [])
        for i, e in enumerate(chain):
            if e == source and chain[(i + 1) % len(chain)] == target:
                return True
        return False

    def is_conquering(self, source: str, target: str) -> bool:
        cmap = self._raw.get("element_interactions", {}).get("conquer_map", {})
        return cmap.get(source) == target

    def get_qi_level(self, density: float) -> dict:
        levels = self._raw.get("qi_density_levels", [])
        for level in levels:
            lo, hi = level["range"]
            if lo <= density <= hi:
                return level
        # 负数或超范围值回退到最低档（depleted）
        return levels[0] if levels else {}

    def get_realm(self, realm_id: str) -> dict | None:
        for r in self._raw.get("realms", []):
            if r["id"] == realm_id:
                return r
        return None

    def get_generation_bonus(self) -> float:
        return self._raw.get("element_interactions", {}).get("generation_bonus", 0.25)

    def get_conquer_bonus(self) -> float:
        return self._raw.get("element_interactions", {}).get("conquer_bonus", 0.30)

    def get_base_absorption(self) -> float:
        """获取固定基础灵气吸收率（灵力/天）。"""
        table = self._raw.get("base_absorption", {})
        return table.get("base", 0.025)

    def get_root_power(self, quality_key: str) -> float:
        """获取灵根资质系数。quality_key: heavenly/upper/middle/lower/waste。"""
        table = self._raw.get("root_power", {})
        return table.get(quality_key, 0.6)

    def get_root_speed_modifier(self, quality_key: str) -> float:
        """兼容旧调用——返回 root_power 值。"""
        return self.get_root_power(quality_key)

    def get_cultivation_method(self, method_id: str) -> dict:
        """获取修炼方式配置。"""
        methods = self._raw.get("cultivation_methods", {})
        return methods.get(method_id, {})

    def get_spirit_stone_rate(self) -> int:
        """获取灵石→灵力兑换率（多少下品灵石=1灵力）。"""
        conv = self._raw.get("spirit_stone_conversion", {})
        return conv.get("rate", 100)

    def get_pill(self, pill_id: str) -> dict | None:
        """获取丹药配置。"""
        for pill in self._raw.get("pills", []):
            if pill["id"] == pill_id:
                return pill
        return None

    def get_breakthrough_method(self, method_id: str) -> dict | None:
        """获取突破方式配置。"""
        methods = self._raw.get("breakthrough_methods", {})
        return methods.get(method_id)

    def get_breakthrough_params(self) -> dict:
        """获取突破成功率计算参数。"""
        return self._raw.get("breakthrough_params", {})

    def get_breakthrough_results(self) -> dict:
        """获取突破结果配置（成功/失败的惩罚和奖励）。"""
        return self._raw.get("breakthrough_results", {})

    def get_root_quality_key(self, root_ids: list[str]) -> str:
        """根据灵根数量返回品质键名。"""
        n = len(root_ids)
        mapping = {1: "heavenly", 2: "upper", 3: "middle", 4: "lower", 5: "waste"}
        return mapping.get(n, "waste")

    def calculate_daily_sp(self, stage_id: str, root_ids: list[str],
                           qi_density: float, method_id: str = "meditation") -> float:
        """计算每日灵力产出。

        公式: base_rate × root_power × (1 + (qi_mult - 1) × root_power) × method_mult
        """
        base = self.get_base_absorption()
        quality_key = self.get_root_quality_key(root_ids)
        root_power = self.get_root_power(quality_key)
        qi_level = self.get_qi_level(qi_density)
        qi_mult = qi_level.get("cultivation_speed_mult", 1.0)
        effective_qi = 1.0 + (qi_mult - 1.0) * root_power
        method = self.get_cultivation_method(method_id)
        method_mult = method.get("speed_mult", 1.0)
        return base * root_power * effective_qi * method_mult

    def get_breakthrough_cooldown_days(self, from_stage_order: int) -> int:
        """获取突破冷却天数。"""
        tiers = self._raw.get("breakthrough_cooldown", {}).get("major", [])
        for tier in tiers:
            if tier["min_order"] <= from_stage_order <= tier["max_order"]:
                return tier["days"]
        return 365

    def compute_substage(self, stage_id: str, spiritual_power: float) -> str:
        """根据境界 ID 和灵力计算小境界。"""
        from lingmo_engine.plugins.cultivation.field_normalizer import (
            CultivationFieldNormalizer,
        )
        stage = self.get_stage(stage_id)
        if not stage:
            return "1"
        return CultivationFieldNormalizer.compute_substage_from_stage(
            stage, spiritual_power
        )

    def get_dao_rhyme_threshold(self, stage_order: int) -> int:
        """获取指定境界阶位的道韵突破门槛。"""
        thresholds = self._raw.get("dao_rhyme", {}).get("thresholds", {})
        return thresholds.get(stage_order, 0)

    def get_dao_rhyme_config(self) -> dict:
        """获取道韵系统配置。"""
        return self._raw.get("dao_rhyme", {})

    def get_grant_cap(self, stage_order: int) -> int:
        """获取指定境界阶位的单次道韵授予上限。"""
        threshold = self.get_dao_rhyme_threshold(stage_order)
        ratio = self._raw.get("dao_rhyme", {}).get("grant_cap_ratio", 0.15)
        return max(1, int(threshold * ratio))

    @property
    def raw(self) -> dict:
        return self._raw
