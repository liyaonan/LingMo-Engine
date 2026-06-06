"""道韵系统 — 对天地大道的感悟深度"""


def check_breakthrough_eligibility(
    current_rhyme: int, threshold: int, schema
) -> dict:
    """检查道韵是否满足突破条件。

    Returns:
        dict: {eligible, enlightenment, low_rhyme, reason}
    """
    config = schema.get_dao_rhyme_config()
    enlightenment_ratio = config.get("enlightenment_ratio", 1.5)
    low_ratio = config.get("low_rhyme_ratio", 0.3)

    if current_rhyme < threshold:
        return {
            "eligible": False,
            "enlightenment": False,
            "low_rhyme": current_rhyme < threshold * low_ratio,
            "reason": f"道韵未至（{current_rhyme}/{threshold}），尚需更多感悟",
        }

    return {
        "eligible": True,
        "enlightenment": current_rhyme >= threshold * enlightenment_ratio,
        "low_rhyme": False,
        "reason": "",
    }


def apply_rhyme_modifier(
    success_rate: float, tribulation_mult: float,
    enlightenment: bool, low_rhyme: bool,
    method: str = "natural",
) -> tuple[float, float]:
    """根据道韵状态修正突破成功率和天劫强度。

    Args:
        method: 突破方式，"reckless" 强行突破时低道韵会受额外惩罚。

    Returns:
        (modified_rate, modified_tribulation_mult)
    """
    if enlightenment:
        return min(1.0, success_rate * 1.5), tribulation_mult * 0.5

    if low_rhyme and method == "reckless":
        return success_rate * 0.3, tribulation_mult * 2.0

    return success_rate, tribulation_mult


def grant_dao_rhyme(
    current_rhyme: int, amount: int, stage_order: int, schema,
) -> dict:
    """授予道韵，受单次上限约束。

    Returns:
        dict: {granted, new_rhyme, cap, threshold}
    """
    if amount <= 0:
        return {"granted": 0, "new_rhyme": current_rhyme,
                "cap": 0, "threshold": 0}

    cap = schema.get_grant_cap(stage_order)
    threshold = schema.get_dao_rhyme_threshold(stage_order)
    actual = min(amount, cap)
    new_rhyme = current_rhyme + actual

    return {"granted": actual, "new_rhyme": new_rhyme,
            "cap": cap, "threshold": threshold}
