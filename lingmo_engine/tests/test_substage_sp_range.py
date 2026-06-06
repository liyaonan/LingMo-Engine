"""compute_sp_range_for_substage 及 substage_hint 集成测试。"""
import math

import pytest

from lingmo_engine.core.character import Character
from lingmo_engine.plugins.cultivation.field_normalizer import (
    CultivationFieldNormalizer,
)


# ── 测试用境界配置 ──

FOUNDATION_STAGE = {
    "id": "foundation",
    "name": "筑基期",
    "sp_range": [200, 600],
    "sub_stages": ["early", "middle", "late"],
    "sub_labels_cn": {"early": "初期", "middle": "中期", "late": "后期", "consummate": "圆满"},
}

QI_STAGE = {
    "id": "qi_condensation",
    "name": "练气期",
    "sp_range": [75, 200],
    "sub_stages": [1, 2, 3, 4, 5, 6, 7, 8, 9],
    "sub_label": "层",
}

MORTAL_STAGE = {
    "id": "mortal",
    "name": "凡人",
    "sp_range": [0, 75],
    "sub_stages": [1],
    "sub_label": "级",
}

DALUO_STAGE = {
    "id": "daluo_golden_immortal",
    "name": "大罗金仙",
    "sp_range": [10000000, None],
    "sub_stages": [1],
}

GOLDEN_CORE_STAGE = {
    "id": "golden_core",
    "name": "金丹期",
    "sp_range": [600, 2000],
    "sub_stages": ["early", "middle", "late"],
    "sub_labels_cn": {"early": "初期", "middle": "中期", "late": "后期"},
}


class TestComputeSpRangeForSubstage:
    """compute_sp_range_for_substage 静态方法测试。"""

    def test_named_early(self):
        result = CultivationFieldNormalizer.compute_sp_range_for_substage(
            FOUNDATION_STAGE, "early",
        )
        assert result == (200, 333)

    def test_named_middle(self):
        result = CultivationFieldNormalizer.compute_sp_range_for_substage(
            FOUNDATION_STAGE, "middle",
        )
        assert result == (334, 466)

    def test_named_late(self):
        result = CultivationFieldNormalizer.compute_sp_range_for_substage(
            FOUNDATION_STAGE, "late",
        )
        assert result == (467, 599)

    def test_numeric_tier1(self):
        result = CultivationFieldNormalizer.compute_sp_range_for_substage(
            QI_STAGE, "1",
        )
        assert result == (75, 88)

    def test_numeric_tier5(self):
        result = CultivationFieldNormalizer.compute_sp_range_for_substage(
            QI_STAGE, "5",
        )
        assert result == (131, 144)

    def test_numeric_tier9(self):
        result = CultivationFieldNormalizer.compute_sp_range_for_substage(
            QI_STAGE, "9",
        )
        assert result == (187, 199)

    def test_single_substage(self):
        result = CultivationFieldNormalizer.compute_sp_range_for_substage(
            MORTAL_STAGE, "1",
        )
        assert result == (0, 74)

    def test_null_max_returns_none(self):
        result = CultivationFieldNormalizer.compute_sp_range_for_substage(
            DALUO_STAGE, "1",
        )
        assert result is None

    def test_unknown_substage_returns_none(self):
        result = CultivationFieldNormalizer.compute_sp_range_for_substage(
            FOUNDATION_STAGE, "xxx",
        )
        assert result is None

    def test_missing_sp_range_returns_none(self):
        stage = {"sub_stages": ["early", "middle", "late"]}
        result = CultivationFieldNormalizer.compute_sp_range_for_substage(
            stage, "early",
        )
        assert result is None

    def test_empty_sp_range_returns_none(self):
        stage = {"sub_stages": ["early", "middle", "late"], "sp_range": []}
        result = CultivationFieldNormalizer.compute_sp_range_for_substage(
            stage, "early",
        )
        assert result is None

    def test_lo_never_exceeds_hi(self):
        """即使极窄范围也保证 lo <= hi。"""
        stage = {
            "sub_stages": ["early", "middle", "late"],
            "sp_range": [100, 101],
        }
        result = CultivationFieldNormalizer.compute_sp_range_for_substage(
            stage, "early",
        )
        assert result is not None
        lo, hi = result
        assert lo <= hi

    def test_large_range_golden_core(self):
        result = CultivationFieldNormalizer.compute_sp_range_for_substage(
            GOLDEN_CORE_STAGE, "late",
        )
        assert result is not None
        lo, hi = result
        assert lo == 1534
        assert hi == 1999


class TestSpRangeRoundtrip:
    """验证反向计算与正向计算的往返一致性。"""

    @pytest.mark.parametrize("stage,sub_id", [
        (FOUNDATION_STAGE, "early"),
        (FOUNDATION_STAGE, "middle"),
        (FOUNDATION_STAGE, "late"),
        (QI_STAGE, "1"),
        (QI_STAGE, "5"),
        (QI_STAGE, "9"),
        (GOLDEN_CORE_STAGE, "early"),
        (GOLDEN_CORE_STAGE, "middle"),
        (GOLDEN_CORE_STAGE, "late"),
    ])
    def test_boundary_values_roundtrip(self, stage, sub_id):
        """区间边界值通过正向计算应返回相同的 substage ID。"""
        lo, hi = CultivationFieldNormalizer.compute_sp_range_for_substage(
            stage, sub_id,
        )
        # 下界
        fwd_lo = CultivationFieldNormalizer.compute_substage_from_stage(
            stage, lo,
        )
        assert fwd_lo == sub_id, f"sp={lo} -> {fwd_lo}, expected {sub_id}"
        # 上界
        fwd_hi = CultivationFieldNormalizer.compute_substage_from_stage(
            stage, hi,
        )
        assert fwd_hi == sub_id, f"sp={hi} -> {fwd_hi}, expected {sub_id}"
