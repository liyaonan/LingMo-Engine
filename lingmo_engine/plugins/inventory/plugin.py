"""InventoryPlugin — 背包/装备插件入口。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TypedDict, NotRequired

from lingmo_engine.core.base_plugin import BasePlugin
from lingmo_engine.core.events import PluginEvent, PluginName
from lingmo_engine.core.message_bus import MessageEvent
from lingmo_engine.core.types import ToolDefinition, ToolParameter, ModuleResult
from lingmo_engine.core.utils import generate_id, find_entity, add_item_to_character
from lingmo_engine.plugins.inventory.items import Effect, ItemSystem
from lingmo_engine.plugins.inventory.equipment import EquipmentSystem


class InventoryPluginState(TypedDict):
    """背包插件状态 schema。"""
    inventory: NotRequired[list[dict]]
    equipment: NotRequired[dict]
    player: NotRequired[dict]

logger = logging.getLogger(__name__)


class InventoryPlugin(BasePlugin):
    """背包/装备插件"""

    name = PluginName.INVENTORY
    depends_on: list[str] = []

    def __init__(self):
        super().__init__()
        self.item_system = ItemSystem()
        self.equipment_system = EquipmentSystem(self.item_system)
        self._inventory_dirty = False

    _loaded: bool = False
    _game_state = None

    def on_load(self) -> None:
        """从世界数据初始化物品/装备系统（仅执行一次）"""
        if self._loaded:
            return
        self._loaded = True

        world = self.world
        if world is None:
            logger.warning("InventoryPlugin: world not set, skip loading")
            return

        raw_items = getattr(world, "items", {})
        if raw_items:
            items_list = list(raw_items.values()) if isinstance(raw_items, dict) else raw_items
            self.item_system.load_items(items_list)

        world_dir = getattr(world, "_world_dir", None)
        if world_dir:
            import yaml
            for name, loader in [
                ("items/equip_slots.yaml", self.equipment_system.load_slots),
                ("items/item_categories.yaml", self.item_system.load_categories),
                ("items/item_rarities.yaml", self.item_system.load_rarities),
                ("items/equip_stats.yaml", self.equipment_system.load_equip_config),
            ]:
                path = Path(world_dir) / name
                if path.exists():
                    with open(path, "r", encoding="utf-8") as f:
                        loader(yaml.safe_load(f) or {})

        # 加载特殊道具（剧情关键道具）
        special_items = getattr(world, "special_items", [])
        if special_items:
            for item_data in special_items:
                category = item_data.get("category", "material")
                if category == "equipment":
                    from lingmo_engine.plugins.inventory.items import EquipmentItem
                    item = EquipmentItem(item_data)
                elif category == "consumable":
                    from lingmo_engine.plugins.inventory.items import ConsumableItem
                    item = ConsumableItem(item_data)
                else:
                    from lingmo_engine.plugins.inventory.items import MaterialItem
                    item = MaterialItem(item_data)
                self.item_system.register_item(item)
            logger.info("InventoryPlugin: 已加载 %d 个特殊道具", len(special_items))

        # 通过 EventBus 注册接口，供 CombatPlugin 解耦调用
        if self._bus:
            self._bus.handle(PluginEvent.EQUIPMENT_GET_BONUS, self._handle_get_combat_equipment)
            self._bus.handle(PluginEvent.EQUIPMENT_GET_NARRATIVE, self._handle_get_narrative_effects)
            self._bus.handle(PluginEvent.EQUIPMENT_GET_SYSTEM, self._handle_get_equipment_system)
            self._bus.handle(PluginEvent.ITEMS_GET_SYSTEM, self._handle_get_item_system)
            self._bus.handle(PluginEvent.ITEMS_GET, self._handle_get_item)
            self._bus.handle(PluginEvent.INVENTORY_AUTO_PUSH, self._handle_auto_push)
            # 注册 EventBus handler（替代 call_plugin 的跨插件调用）
            self._bus.handle(PluginEvent.INVENTORY_REMOVE_ITEM, self._handle_remove_item_event)
            self._bus.handle(PluginEvent.INVENTORY_REGISTER_AND_ADD, self._handle_register_and_add_event)
            self._bus.handle(PluginEvent.INVENTORY_REGISTER_ONLY, self._handle_register_only_event)
            self._bus.handle(PluginEvent.INVENTORY_GET_INVENTORY, self._handle_get_inventory_event)

        # 监听 LLM 循环完成，标记背包数据需要刷新
        mb = self.message_bus
        if mb:
            mb.subscribe(MessageEvent.LLM_LOOP_COMPLETE, self._on_llm_loop_complete)

        logger.info("InventoryPlugin loaded: %d items, %d slots, %d rarities",
                    len(self.item_system.get_all_items()),
                    len(self.equipment_system.get_slots()),
                    len(self.item_system.get_rarities()))

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="get_inventory",
                description="查看玩家背包中的物品和当前装备情况",
                parameters=[],
            ),
            ToolDefinition(
                name="use_item",
                description=(
                    "使用背包中的消耗品。"
                    "仅限非战斗场景使用；"
                    "combat_only 物品（如战斗药水、符箓）不可在此调用。"
                    "使用前应先调用 get_inventory 确认物品存在且可用。"
                ),
                parameters=[
                    ToolParameter(
                        name="item_id",
                        type="string",
                        description="要使用的物品ID（从 get_inventory 返回的 id 字段获取）",
                        required=True,
                    ),
                    ToolParameter(
                        name="target",
                        type="string",
                        description="目标名称（可选，部分物品需要指定目标）",
                        required=False,
                    ),
                ],
            ),
            ToolDefinition(
                name="add_item",
                description=(
                    "向玩家背包添加物品。用于剧情中获得物品的场景，"
                    "例如探索宝箱、NPC赠予、战斗掉落等。"
                    "物品必须在世界物品表中已定义。"
                ),
                parameters=[
                    ToolParameter(
                        name="item_id",
                        type="string",
                        description="物品ID（对应世界物品表中的 id）",
                        required=True,
                    ),
                    ToolParameter(
                        name="quantity",
                        type="integer",
                        description="数量，默认为1",
                        required=False,
                    ),
                    ToolParameter(
                        name="reason",
                        type="string",
                        description="获得物品的剧情原因",
                        required=True,
                    ),
                ],
            ),
            ToolDefinition(
                name="remove_item",
                description=(
                    "从玩家背包移除物品。用于剧情中失去物品的场景，"
                    "例如物品被偷、献给NPC、交易消耗等。"
                    "不可移除关键物品（is_key_item）。"
                ),
                parameters=[
                    ToolParameter(
                        name="item_id",
                        type="string",
                        description="要移除的物品ID",
                        required=True,
                    ),
                    ToolParameter(
                        name="quantity",
                        type="integer",
                        description="移除数量，默认为1",
                        required=False,
                    ),
                    ToolParameter(
                        name="reason",
                        type="string",
                        description="失去物品的剧情原因",
                        required=True,
                    ),
                ],
            ),
            ToolDefinition(
                name="add_item_by_data",
                description=(
                    "向玩家背包添加已存在于世界物品表中的物品。"
                    "通过 item_id 或 name 定位物品，如需查询可用物品请先使用 query_entity（entity_type=item）。"
                ),
                parameters=[
                    ToolParameter(
                        name="item_data",
                        type="object",
                        description=(
                            "物品定位数据。支持:\n"
                            "  item_id: 物品ID（优先匹配）\n"
                            "  name: 物品名称（模糊匹配）\n"
                            "  quantity: 数量（默认1）\n"
                            "物品必须已在世界物品表中定义。"
                        ),
                        required=True,
                    ),
                ],
            ),
            ToolDefinition(
                name="create_quest_prop",
                description=(
                    "创建任务/剧情道具。"
                    "只需提供 name、summary 和 description，系统自动设为关键物品（不可丢弃）。"
                    "用于任务信物、密函、特殊钥匙等剧情相关物品。"
                    "可通过 for_entity 参数在创建后立即添加到目标角色背包。"
                ),
                parameters=[
                    ToolParameter(
                        name="name",
                        type="string",
                        description="道具名称",
                        required=True,
                    ),
                    ToolParameter(
                        name="summary",
                        type="string",
                        description="简报（不超过30字，突出核心用途）",
                        required=True,
                    ),
                    ToolParameter(
                        name="description",
                        type="string",
                        description="完整描述",
                        required=True,
                    ),
                    ToolParameter(
                        name="reason",
                        type="string",
                        description="获得该道具的剧情原因",
                        required=True,
                    ),
                    ToolParameter(
                        name="for_entity",
                        type="string",
                        description=(
                            "可选，创建后自动将道具添加到目标角色背包。"
                            "支持: \"player\"(玩家)、角色ID、角色名称。"
                            "不传则只创建定义。"
                        ),
                        required=False,
                    ),
                    ToolParameter(
                        name="quantity",
                        type="integer",
                        description="添加数量（默认1）",
                        required=False,
                    ),
                ],
            ),
        ]

    def set_game_state(self, state):
        """注入 GameState 引用（由 PluginRegistry 自动调用）。"""
        self._game_state = state

    def _get_game_state(self):
        """获取 GameState 引用。"""
        return self._game_state

    def execute_tool(self, tool_name: str, params: dict) -> ModuleResult:
        """执行LLM工具调用"""
        self.on_load()

        if tool_name == "get_inventory":
            gs = self._get_game_state()
            if gs is None:
                return ModuleResult(success=False, log="GameState 不可用，无法查询背包")
            full = self._get_full_state(gs)
            # 从 WebSocket 响应格式提取 LLM 需要的数据
            return ModuleResult(
                success=True,
                log="背包已查询",
                data={
                    "player_name": full["player_name"],
                    "gold": full["gold"],
                    "inventory": full["inventory"],
                    "equipment": full["equipment"],
                },
            )

        if tool_name == "use_item":
            gs = self._get_game_state()
            if gs is None:
                return ModuleResult(success=False, log="GameState 不可用，无法使用物品")
            item_id = params.get("item_id", "")
            target = params.get("target")
            result = self._use_item(item_id, target, gs)
            return ModuleResult(
                success=result.get("success", False),
                log=result.get("message", ""),
            )

        if tool_name == "add_item":
            gs = self._get_game_state()
            if gs is None:
                return ModuleResult(success=False, log="GameState 不可用")
            return self._add_item(
                params.get("item_id", ""),
                params.get("quantity", 1),
                params.get("reason", ""),
                gs,
            )

        if tool_name == "remove_item":
            gs = self._get_game_state()
            if gs is None:
                return ModuleResult(success=False, log="GameState 不可用")
            return self._remove_item(
                params.get("item_id", ""),
                params.get("quantity", 1),
                params.get("reason", ""),
                gs,
            )

        if tool_name == "add_item_by_data":
            gs = self._get_game_state()
            if gs is None:
                return ModuleResult(success=False, log="GameState 不可用")
            return self._add_item_by_data(params, gs)

        if tool_name == "create_quest_prop":
            gs = self._get_game_state()
            if gs is None:
                return ModuleResult(success=False, log="GameState 不可用")
            return self._create_quest_prop(params, gs)

        if tool_name == "register_and_add_item":
            gs = self._get_game_state()
            if gs is None:
                return ModuleResult(success=False, log="GameState 不可用")
            return self._register_and_add_item(params, gs)

        if tool_name == "register_item_only":
            gs = self._get_game_state()
            if gs is None:
                return ModuleResult(success=False, log="GameState 不可用")
            return self._register_item_only(params, gs)

        return ModuleResult(success=False, log=f"未知工具: {tool_name}")

    def handle_websocket(self, message: dict, game_state: object) -> dict | None:
        """处理 WebSocket 消息"""
        self.on_load()
        msg_type = message.get("type", "")

        if msg_type == "inventory_open":
            return self._get_full_state(game_state)

        if msg_type == "inventory_action":
            return self._handle_action(message, game_state)

        return None

    # ---- 事件驱动的状态推送 ----

    def _on_llm_loop_complete(self, event, message=None, **kwargs) -> None:
        """LLM 循环结束标记脏位，等待 collect_auto_push 收集。"""
        self._inventory_dirty = True

    def _handle_auto_push(self, game_state=None):
        """EventBus 请求处理器：脏位为 True 时返回完整背包状态。"""
        if not self._inventory_dirty or game_state is None:
            return None
        self._inventory_dirty = False
        return self._get_full_state(game_state)

    # ---- Helpers ----

    def _get_full_state(self, game_state) -> dict:
        player = game_state.get_player()
        player_name = player.name
        gold = player.attrs.get("gold", 0)
        inventory = list(player.inventory)
        equipment = dict(player.equipment)

        # 如果没有装备数据，用槽位初始化
        if not equipment:
            slots = self.equipment_system.get_slots()
            equipment = {s["id"]: None for s in slots}
            game_state.set_equipment(equipment)

        # 展开背包物品为完整详情
        vs_table = self.world.get_effect_value_scale() if self.world else None
        cf = self.world.get_combat_functions() if self.world else {}

        def _amplify(creator_attrs: dict) -> dict:
            level = creator_attrs.get("level", 0)
            l2s = cf.get("level_to_stage")
            gsm = cf.get("get_stage_mult")
            mult = 1.0
            if l2s and gsm:
                stage_id = l2s(level)
                mult = gsm(stage_id) if stage_id else 1.0
            result = dict(creator_attrs)
            if mult > 1.0:
                for key in ("force", "tenacity", "agility"):
                    if key in result:
                        result[key] = int(result[key] * mult)
            return result

        expanded_inventory = []
        for entry in inventory:
            item = self.item_system.get_item(entry["item_id"])
            if item is None:
                logger.warning("背包物品 %s 未在 ItemSystem 中找到，跳过", entry["item_id"])
                continue
            d = item.to_dict()
            # 对消耗品的 fixed_damage/fixed_dot 预计算增幅显示值
            if item.is_consumable and vs_table:
                # 通过 EventBus 调用 compute_display_value，避免直接导入 combat.resolver
                for ed in d.get("effects", []):
                    if ed.get("type") in ("fixed_damage", "fixed_dot") and ed.get("value"):
                        creator = getattr(item, 'creator_stats', {})
                        if creator:
                            result = self._bus.request(
                                PluginEvent.COMBAT_COMPUTE_DISPLAY_VALUE,
                                ed["value"], ed.get("scale_stat"),
                                ed.get("power", 1.0), creator,
                                vs_table, _amplify,
                            ) if self._bus else None
                            if result is not None:
                                ed["display_value"] = result
            d["quantity"] = entry["quantity"]
            d["rarity_info"] = self.item_system.get_rarity_info(item.rarity)
            expanded_inventory.append(d)

        return {
            "type": "inventory_state",
            "player_name": player_name,
            "gold": gold,
            "inventory": expanded_inventory,
            "equipment": self.equipment_system.get_equipment_snapshot(equipment),
            "categories": self.item_system.get_categories(),
            "rarities": self.item_system.get_rarities(),
            "slots": self.equipment_system.get_slots(),
        }

    def _handle_action(self, message: dict, game_state) -> dict:
        action = message.get("action", "")
        player = game_state.get_player()
        equipment = player.equipment
        inventory = player.inventory
        player_dict = {"abilities": player.abilities}

        if action == "equip":
            item_id = message.get("item_id", "")
            slot_id = message.get("slot_id", "")
            # 提取角色字段用于装备条件检查（从 extra 动态读取，避免硬编码字段名）
            character_data = dict(player.extra)
            result = self.equipment_system.equip(
                item_id, slot_id, equipment, inventory,
                character_data=character_data,
            )
            if result["success"]:
                self._save_equipment(game_state, equipment)
                changes = result.get("changes", {})
                # 被替换的旧装备：记录技能变化
                removed_item = changes.get("removed") or {}
                removed_abilities = removed_item.get("abilities", []) if removed_item else []
                # 新装备携带技能：标记通知前端刷新
                equipped_item = changes.get("equipped", {})
                equipped_abilities = equipped_item.get("abilities", []) if equipped_item else []
                if equipped_abilities or removed_abilities:
                    result["abilities_changed"] = True
            return {"type": "inventory_action_result", **result}

        if action == "unequip":
            slot_id = message.get("slot_id", "")
            native_abilities = player_dict.get("abilities", [])
            result = self.equipment_system.unequip(slot_id, equipment, native_abilities)
            if result["success"]:
                self._save_equipment(game_state, equipment)
                # 装备技能变化：标记通知前端刷新
                abilities_removed = result.get("changes", {}).get("abilities_removed", [])
                if abilities_removed:
                    result["abilities_changed"] = True
            return {"type": "inventory_action_result", **result}

        if action == "use":
            item_id = message.get("item_id", "")
            return self._use_item(item_id, None, game_state)

        if action == "drop":
            item_id = message.get("item_id", "")
            quantity = message.get("quantity", 1)
            item = self.item_system.get_item(item_id)
            if item and item.is_key_item:
                return {"type": "inventory_action_result", "success": False, "message": "关键物品不可丢弃"}
            ok = game_state.remove_player_item(item_id, quantity)
            return {"type": "inventory_action_result", "success": ok, "message": "已丢弃" if ok else "数量不足"}

        return {"type": "inventory_action_result", "success": False, "message": f"未知操作: {action}"}

    def _add_item(self, item_id: str, quantity: int, reason: str, game_state) -> ModuleResult:
        """向玩家背包添加物品。"""
        if quantity <= 0:
            return ModuleResult(success=False, log="数量必须大于0")
        item = self.item_system.get_item(item_id)
        if item is None:
            registered = list(self.item_system._items.keys())[:10]
            logger.warning(
                "add_item: 物品 %r 未在 ItemSystem 中找到（已注册 %d 个: %s）",
                item_id, len(self.item_system._items), registered,
            )
            return ModuleResult(success=False, log=f"物品 {item_id} 不存在于世界物品表")
        game_state.add_player_item(item_id, quantity)
        return ModuleResult(
            success=True,
            log=f"获得 {item.name} ×{quantity}（{reason}）",
        )

    def _remove_item(self, item_id: str, quantity: int, reason: str, game_state) -> ModuleResult:
        """从玩家背包移除物品。"""
        if quantity <= 0:
            return ModuleResult(success=False, log="数量必须大于0")
        item = self.item_system.get_item(item_id)
        if item is None:
            return ModuleResult(success=False, log=f"物品 {item_id} 不存在")
        if item.is_key_item:
            return ModuleResult(success=False, log=f"{item.name} 是关键物品，不可移除")
        ok = game_state.remove_player_item(item_id, quantity)
        if not ok:
            return ModuleResult(success=False, log=f"背包中 {item.name} 数量不足")
        return ModuleResult(success=True, log=f"失去 {item.name} ×{quantity}（{reason}）")

    @staticmethod
    def _save_equipment(game_state, equipment) -> None:
        """保存装备状态（set_equipment 直接写入 CharacterManager）。"""
        game_state.set_equipment(equipment)

    def _use_item(self, item_id: str, target: str | None, game_state) -> dict:
        item = self.item_system.get_item(item_id)
        if item is None:
            return {"type": "inventory_action_result", "success": False, "message": f"物品 {item_id} 不存在"}

        if not item.is_consumable:
            return {"type": "inventory_action_result", "success": False, "message": "该物品不可使用"}

        if item.combat_only:
            return {"type": "inventory_action_result", "success": False, "message": "该物品只能在战斗中使用"}

        # 检查玩家是否拥有该物品
        if not any(e["item_id"] == item_id for e in game_state.get_player().inventory):
            return {"type": "inventory_action_result", "success": False, "message": f"背包中没有 {item.name}"}

        # 检查代价（直接从 CharacterManager 读取）
        player_attrs = game_state.get_player().attrs
        for cost in item.costs:
            if cost.amount <= 0:
                continue
            current = player_attrs.get(cost.resource, 0)
            if current < cost.amount:
                return {
                    "type": "inventory_action_result",
                    "success": False,
                    "message": f"{cost.resource} 不足（需要{cost.amount}，当前{current}）",
                }

        # 记录效果前的属性快照
        snapshot = dict(player_attrs)

        # 扣除代价
        for cost in item.costs:
            if cost.amount > 0:
                player_attrs[cost.resource] = player_attrs.get(cost.resource, 0) - cost.amount

        # 执行效果
        creator_stats = getattr(item, "creator_stats", {})
        for effect in item.effects:
            self._apply_effect(effect, player_attrs, creator_stats)

        # 消耗物品
        game_state.remove_player_item(item_id, 1)

        # 构建效果描述
        changes = []
        for key, new_val in player_attrs.items():
            old_val = snapshot.get(key, 0)
            diff = new_val - old_val
            if diff != 0:
                changes.append(f"{key}: {old_val}→{new_val}({diff:+d})")

        message = f"使用了 {item.name}"
        if changes:
            message += "（" + "，".join(changes) + "）"

        return {
            "type": "inventory_action_result",
            "success": True,
            "message": message,
        }

    def _apply_effect(self, effect, player: dict, creator_stats: dict | None = None) -> None:
        """执行单个效果（非战斗）"""
        final_value = effect.value
        if effect.scale_stat:
            if creator_stats and effect.scale_stat in creator_stats:
                stat_val = creator_stats[effect.scale_stat]
            else:
                stat_val = player.get(effect.scale_stat, 50)
            final_value += int(stat_val * effect.power)
        elif effect.modifier is not None and effect.stat:
            stat_val = player.get(effect.stat, 0)
            final_value += int(stat_val * effect.modifier)

        if effect.type == "heal":
            stat = effect.stat or "hp"
            max_stat = player.get(f"max_{stat}", player.get(stat, 0))
            player[stat] = min(player.get(stat, 0) + final_value, max_stat)
        elif effect.type in ("buff", "debuff"):
            stat = effect.stat or Effect.DEFAULT_STAT.get(effect.type)
            if stat:
                player[stat] = player.get(stat, 0) + final_value

    def get_combat_equipment(self, game_state) -> dict:
        """供 CombatPlugin 调用的接口（接受 GameState 或 dict）"""
        self.on_load()
        data = game_state if isinstance(game_state, dict) else game_state.get_data_copy()
        equipment = data.get("equipment", {})
        if not equipment:
            return {"stat_bonus": {}, "buffs": [], "abilities": []}
        # 提取先天属性用于叠加上限计算
        innate_attrs = None
        if not isinstance(game_state, dict):
            player = game_state.get_player()
            if player and self.world:
                schema = self.world.get_character_schema()
                attrs_schema = schema.get("attributes", {})
                if attrs_schema:
                    innate_attrs = {
                        k: v for k, v in player.attrs.items()
                        if attrs_schema.get(k, {}).get("innate", False)
                    }
        # 叙事模式下跳过 stat_bonus 累加
        stat_bonus_mode = "full"
        equip_config = self.equipment_system._equip_config
        if equip_config:
            formula = equip_config.get("equip_formula", {})
            if formula.get("mode") == "narrative":
                stat_bonus_mode = "none"
        return self.equipment_system.get_combat_equipment(
            equipment, innate_attrs=innate_attrs, stat_bonus_mode=stat_bonus_mode,
        )

    def _handle_get_combat_equipment(self, game_state: dict) -> dict:
        """EventBus 处理器：响应 equipment:get_bonus 请求。"""
        return self.get_combat_equipment(game_state)

    def _handle_get_narrative_effects(self, equipment: dict) -> list[dict]:
        """EventBus 处理器：响应 equipment:get_narrative 请求。"""
        self.on_load()
        if not equipment:
            return []
        return self.equipment_system.get_narrative_effects(equipment)

    def _handle_get_item_system(self) -> "ItemSystem":
        """EventBus 处理器：返回 ItemSystem 实例（单一数据源）。

        CombatPlugin 启动时调用一次，之后本地引用，避免每次查询走 EventBus。
        """
        self.on_load()
        return self.item_system

    def _handle_get_equipment_system(self):
        """EventBus 处理器：返回 EquipmentSystem 实例（单一数据源）。"""
        self.on_load()
        return self.equipment_system

    def _handle_get_item(self, item_id: str):
        """EventBus 处理器：按 ID 查询单个物品（用于偶尔的按需查询）。"""
        self.on_load()
        return self.item_system.get_item(item_id)

    # ── EventBus handler（替代 call_plugin 的跨插件调用） ──

    def _handle_remove_item_event(self, **kwargs):
        """EventBus handler：移除物品。"""
        item_id = kwargs.get("item_id")
        count = kwargs.get("count", 1)
        return self.execute_tool("remove_item", {"item_id": item_id, "count": count})

    def _handle_register_and_add_event(self, **kwargs):
        """EventBus handler：注册并添加物品。"""
        return self.execute_tool("register_and_add_item", kwargs)

    def _handle_register_only_event(self, **kwargs):
        """EventBus handler：仅注册物品。"""
        return self.execute_tool("register_item_only", kwargs)

    def _handle_get_inventory_event(self, **kwargs):
        """EventBus handler：查询背包。"""
        return self.execute_tool("get_inventory", {})

    def _add_item_by_data(self, params: dict, game_state) -> ModuleResult:
        """查找世界物品表中已有物品并添加到背包。"""
        self.on_load()

        item_data = params.get("item_data")
        if not item_data or not isinstance(item_data, dict):
            return ModuleResult(success=False, log="item_data 必须为非空字典")

        # 尝试通过 item_id 精确匹配
        item_id = item_data.get("item_id") or item_data.get("id")
        item = None
        if item_id:
            item = self.item_system.get_item(item_id)

        # 精确匹配失败，尝试通过 name 匹配
        if item is None and item_data.get("name"):
            name = item_data["name"]
            for candidate in self.item_system.get_all_items():
                if candidate.name == name:
                    item = candidate
                    break

        if item is None:
            return ModuleResult(
                success=False,
                log=f"物品不存在于世界物品表中（id={item_id}, name={item_data.get('name', '')}）。请先使用 query_entity 查询可用物品。",
            )

        quantity = item_data.get("quantity", 1)
        if quantity <= 0:
            return ModuleResult(success=False, log="数量必须大于0")

        game_state.add_player_item(item.id, quantity)

        return ModuleResult(
            success=True,
            log=f"添加 {item.name} ×{quantity} 到背包",
            data={
                "item": {
                    "id": item.id,
                    "name": item.name,
                    "category": item.category,
                    "rarity": item.rarity,
                },
                "player_updates": {
                    "loot": [{"item_id": item.id, "quantity": quantity}],
                },
            },
        )

    def _register_and_add_item(self, params: dict, game_state) -> ModuleResult:
        """动态创建物品、注册到 ItemSystem 并添加到背包（仅供内部插件调用）。"""
        from lingmo_engine.plugins.inventory.items import (
            MaterialItem,
            ConsumableItem,
            EquipmentItem,
        )

        self.on_load()

        item_data = params.get("item_data")
        if not item_data or not isinstance(item_data, dict):
            return ModuleResult(success=False, log="item_data 必须为非空字典")

        if not item_data.get("name"):
            return ModuleResult(success=False, log="item_data 必须包含 name 字段")

        # 自动生成 id
        if not item_data.get("id"):
            item_data["id"] = generate_id("item")

        # 根据 category 创建对应类型的 Item
        category = item_data.get("category", "material")
        if category == "equipment":
            item = EquipmentItem(item_data)
        elif category == "consumable":
            item = ConsumableItem(item_data)
        else:
            item_data.setdefault("category", "material")
            item = MaterialItem(item_data)

        # 注册到 ItemSystem
        self.item_system.register_item(item)

        # 持久化到注册表
        game_state.add_registry_item(item.id, item.to_dict())

        # 添加到玩家背包
        quantity = item_data.get("quantity", 1)
        game_state.add_player_item(item.id, quantity)

        return ModuleResult(
            success=True,
            log=f"注册并添加 {item.name} ×{quantity} 到背包",
            data={
                "item": {
                    "id": item.id,
                    "name": item.name,
                    "category": item.category,
                    "rarity": item.rarity,
                },
                "player_updates": {
                    "loot": [{"item_id": item.id, "quantity": quantity}],
                },
            },
        )

    def _register_item_only(self, params: dict, game_state) -> ModuleResult:
        """动态创建物品并注册到 ItemSystem，不添加到背包（供其他插件调用）。"""
        from lingmo_engine.plugins.inventory.items import (
            MaterialItem,
            ConsumableItem,
            EquipmentItem,
        )

        self.on_load()

        item_data = params.get("item_data")
        if not item_data or not isinstance(item_data, dict):
            return ModuleResult(success=False, log="item_data 必须为非空字典")

        if not item_data.get("name"):
            return ModuleResult(success=False, log="item_data 必须包含 name 字段")

        if not item_data.get("id"):
            item_data["id"] = generate_id("item")

        category = item_data.get("category", "material")
        if category == "equipment":
            item = EquipmentItem(item_data)
        elif category == "consumable":
            item = ConsumableItem(item_data)
        else:
            item_data.setdefault("category", "material")
            item = MaterialItem(item_data)

        self.item_system.register_item(item)
        game_state.add_registry_item(item.id, item.to_dict())

        return ModuleResult(
            success=True,
            log=f"注册物品 {item.name}",
            data={
                "item": {
                    "id": item.id,
                    "name": item.name,
                    "category": item.category,
                    "rarity": item.rarity,
                },
            },
        )

    def _create_quest_prop(self, params: dict, game_state) -> ModuleResult:
        """创建任务道具（轻量物品，只有 name/summary/description）。"""
        from lingmo_engine.plugins.inventory.items import MaterialItem

        self.on_load()

        name = params.get("name", "").strip()
        summary = params.get("summary", "").strip()
        description = params.get("description", "").strip()
        reason = params.get("reason", "").strip()

        if not name:
            return ModuleResult(success=False, log="name 不能为空")
        if not summary:
            return ModuleResult(success=False, log="summary 不能为空")
        if not description:
            return ModuleResult(success=False, log="description 不能为空")

        item_id = generate_id("qp")

        item_data = {
            "id": item_id,
            "name": name,
            "category": "quest_prop",
            "description": description,
            "is_key_item": True,
            "stackable": False,
            "rarity": 0,
            "sell_price": 0,
            "tags": ["任务道具"],
        }

        item = MaterialItem(item_data)
        self.item_system.register_item(item)
        game_state.add_registry_item(item.id, item.to_dict())

        result_data = {
            "item": {
                "id": item.id,
                "name": item.name,
                "category": item.category,
                "summary": summary,
                "is_key_item": True,
            },
        }
        log = f"创建任务道具「{name}」（{reason}）"

        # for_entity: 创建后立即添加到目标角色背包
        for_entity = params.get("for_entity")
        if for_entity and game_state:
            quantity = params.get("quantity", 1)
            char = find_entity(game_state.character_manager, for_entity)
            if char:
                add_item_to_character(char, item.id, quantity)
                result_data["assigned_to"] = char.name
                log += f"\n已添加 {quantity}x 到「{char.name}」背包"
            else:
                log += f"\n⚠ 未找到角色「{for_entity}」，道具仅创建定义"

        return ModuleResult(
            success=True,
            log=log,
            data=result_data,
        )

    def restore_registries(self, game_state) -> None:
        """从 GameState 注册表恢复 LLM 生成的物品到 ItemSystem（存档加载后调用）。"""
        from lingmo_engine.plugins.inventory.items import (
            MaterialItem,
            ConsumableItem,
            EquipmentItem,
        )

        self.on_load()
        registry_items = game_state.get_all_registry_items()
        restored = 0
        for item_id, item_data in registry_items.items():
            # 跳过已存在的世界物品
            if self.item_system.get_item(item_id):
                continue
            category = item_data.get("category", "material")
            if category == "equipment":
                item = EquipmentItem(item_data)
            elif category == "consumable":
                item = ConsumableItem(item_data)
            else:
                item = MaterialItem(item_data)
            self.item_system.register_item(item)
            restored += 1
        if restored:
            logger.info("从注册表恢复 %d 个物品到 ItemSystem", restored)
        self._inventory_dirty = True

