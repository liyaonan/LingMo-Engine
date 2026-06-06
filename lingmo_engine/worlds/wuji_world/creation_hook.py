"""无极世界 — 角色创建钩子。

选中主角后：
1. 移除其 NPC 版本（避免同时作为玩家和 NPC 存在）
2. 设置其余两位 NPC 的开场地点
3. 灵界篇时调整小萤为灵界未遇姬瑶的状态
"""


# 路线 ID → 对应的主角 NPC 预留 ID（characters.yaml 中定义）
_ROUTE_NPC_MAP: dict[str, int] = {
    "mortal_realm": 1,
    "spirit_realm": 2,
    "immortal_realm": 3,
}

# NPC ID → 开场地点（地图节点 ID）
# 人界主角(1)：刚入宗门 → 剑峰（天道剑宗山门）
# 灵界主角(2)：带妖族幼童坠落人界 → 青石镇（偏僻小镇，便于隐藏）
# 仙界主角(3)：面临金仙劫 → 苍冥蛮荒深处
_NPC_START_LOCATIONS: dict[int, str] = {
    1: "qingshi_town",
    2: "qingshi_town",
    3: "cangming_domain",
}

# 小萤灵界版差量（灵界篇开场时覆写）
_XIAOYING_SPIRIT_REALM_OVERRIDES: dict = {
    "location": "fuli_city",
    "background": (
        "灵界落尘域浮黎城中流浪的狐妖孤儿。血统极低（一尾狐族，妖族最底层），父母不详。"
        "从小翻找残羹冷炙为生，无人教她说话或修炼。天感觉醒极早（约三岁），"
        "从那时起世界变得'很吵'——天道信息流持续涌入幼小意识，正常语言被挤压到无法组织。"
        "浮黎城灵气浓郁，天感噪音震耳欲聋，她几乎无法入睡。"
        "沉默寡言，在浮黎城街巷间翻找食物、躲避修士和妖兽。"
    ),
    "current_affairs": ["在浮黎城街巷间翻找食物", "躲避修士和妖兽", "天感噪音让她难以入睡"],
    "clothing": "不知从哪捡来的破旧灰袍，大了三号，袖子和下摆卷了好几道。赤脚，脚底磨出厚茧。头发蓬乱，没有发簪。",
}


def on_character_created(route_id, character, character_manager, game_state, world):
    """角色创建完成后的世界级处理。"""
    _remove_selected_protagonist_npc(route_id, character_manager)
    _set_npc_start_locations(character_manager)
    if route_id == "spirit_realm":
        _set_xiaoying_spirit_realm_state(character_manager)


def _remove_selected_protagonist_npc(route_id: str, character_manager) -> None:
    """移除被选中为主角的 NPC。"""
    npc_id = _ROUTE_NPC_MAP.get(route_id)
    if npc_id is not None and npc_id in character_manager._characters:
        del character_manager._characters[npc_id]


def _set_npc_start_locations(character_manager) -> None:
    """设置保留 NPC 的开场地点。"""
    for npc_id, location in _NPC_START_LOCATIONS.items():
        if npc_id in character_manager._characters:
            character_manager.update_location(npc_id, location)


def _set_xiaoying_spirit_realm_state(character_manager) -> None:
    """灵界篇开场时，将小萤设为灵界未遇姬瑶的状态。"""
    xiaoying = character_manager._characters.get(17)
    if xiaoying is None:
        return
    for field, value in _XIAOYING_SPIRIT_REALM_OVERRIDES.items():
        if field == "location":
            character_manager.update_location(xiaoying.id, value)
        else:
            setattr(xiaoying, field, value)
    # 清除与姬瑶的关系（尚未相遇）
    xiaoying.relationships = {}
    # 移除姬瑶买的草编发簪
    xiaoying.inventory = [
        item for item in xiaoying.inventory
        if item.get("item_id") != "eq_xiaoying_hairpin"
    ]
    xiaoying.equipment["accessory"] = None
