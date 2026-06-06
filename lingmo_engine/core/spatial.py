"""空间矢量计算 - 八方位、距离、可见性"""
from __future__ import annotations

import math


class SpatialCalc:
    """纯数学工具类，无地图依赖。"""

    DIRECTIONS = ["正北", "东北", "正东", "东南", "正南", "西南", "正西", "西北"]

    @staticmethod
    def bearing(src: tuple[float, float], dst: tuple[float, float]) -> str:
        """计算 src->dst 的八方位。

        坐标系：x 正方向为东，y 正方向为北。返回原地/八方位字符串。
        """
        dx = dst[0] - src[0]
        dy = dst[1] - src[1]
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            return "原地"
        # atan2(dx, dy) 以正北为 0 度，顺时针为正
        angle = math.degrees(math.atan2(dx, dy)) % 360
        idx = round(angle / 45) % 8
        return SpatialCalc.DIRECTIONS[idx]

    @staticmethod
    def distance(src: tuple[float, float], dst: tuple[float, float]) -> float:
        """欧几里得距离（坐标单位）。"""
        return math.hypot(dst[0] - src[0], dst[1] - src[1])

    @staticmethod
    def to_li(coord_distance: float, scale: float) -> float:
        """坐标距离 -> 里。"""
        return coord_distance * scale

    @staticmethod
    def is_visible(
        src_center: tuple[float, float],
        src_radius: float,
        dst_center: tuple[float, float],
        scale: float,
        multiplier: float,
    ) -> bool:
        """判断目标是否在可视范围内。范围 = src_radius * multiplier * scale（里）。"""
        range_li = src_radius * multiplier * scale
        dist_li = SpatialCalc.to_li(
            SpatialCalc.distance(src_center, dst_center), scale
        )
        return dist_li <= range_li
