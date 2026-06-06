"""灵力封存物品制作插件"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import random
from typing import Optional

import yaml

from lingmo_engine.core.base_plugin import BasePlugin
from lingmo_engine.core.events import PluginEvent
from lingmo_engine.core.types import ModuleResult, ToolDefinition, ToolParameter
from lingmo_engine.core.utils import find_entity, add_item_to_character, generate_id

from lingmo_engine.plugins.crafting.crafting_engine import CraftingEngine
from lingmo_engine.plugins.crafting.llm_crafter import (
    build_crafting_prompt,
    parse_llm_result,
    build_material_prompt,
    parse_material_result,
    build_equipment_prompt,
    parse_equipment_result,
)
from lingmo_engine.plugins.crafting.equipment_generator import EquipmentGenerator

logger = logging.getLogger(__name__)


class CraftingPlugin(BasePlugin):
    name = "crafting"
    version = "0.1.0"
    depends_on: list[str] = ["inventory"]

    _engine: Optional[CraftingEngine] = None
    _config_data: Optional[dict] = None
    _equip_gen: Optional[EquipmentGenerator] = None
    _llm_access = None
    _game_state = None

    def set_llm_access(self, access):
        """注入 LLMProviderAccess，替代 get_gamemaster()。"""
        self._llm_access = access

    def on_load(self) -> None:
        """加载制作配置。"""
        if self._engine is not None:
            return

        config = self._load_crafting_config()
        if config:
            self._config_data = config
            self._engine = CraftingEngine(config)
            logger.info("CraftingPlugin 加载完成，题材: %s", list(config.get("themes", {}).keys()))

            # 初始化装备生成器，传入 rarity_multiplier 避免硬编码
            equip_config = config.get("equipment", {})
            if equip_config:
                if "equip_budget" in config:
                    equip_config["equip_budget"] = config["equip_budget"]
                equip_config["rarity_multiplier"] = config.get("budget", {}).get("rarity_multiplier", [])
                self._equip_gen = EquipmentGenerator(equip_config)

            # 加载装备槽位
            slots = self._load_equip_slots()
            if slots:
                self._engine.load_equip_slots(slots)
        else:
            logger.warning("CraftingPlugin: 未找到 crafting.yaml 配置")

    def on_unload(self) -> None:
        self._engine = None
        self._config_data = None
        self._equip_gen = None

    def _build_slot_type_desc(self) -> str:
        """从装备槽位配置生成 slot_type 参数的描述。"""
        if not self._engine:
            return "装备部位"
        slots = self._engine.get_equip_slots()
        entries = [f"{s['id']}({s['name']})" for s in slots]
        return f"装备部位，可选值：{', '.join(entries)}"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="generate_material",
                description=(
                    "根据场景上下文动态生成修仙材料。"
                    "LLM 生成材料名称、稀有度、标签和描述，系统自动计算灵力值。"
                    "可通过 for_entity 参数在创建后立即添加到目标角色背包。"
                ),
                parameters=[
                    ToolParameter(
                        name="context",
                        type="string",
                        description="场景上下文描述，如'击杀了一头火狼妖王'",
                        required=True,
                    ),
                    ToolParameter(
                        name="count",
                        type="integer",
                        description="生成材料数量（1~3，默认1）",
                        required=False,
                    ),
                    ToolParameter(
                        name="quantity",
                        type="integer",
                        description="每种材料的添加数量（默认1）",
                        required=False,
                    ),
                    ToolParameter(
                        name="for_entity",
                        type="string",
                        description=(
                            "可选，创建后自动将材料添加到目标角色背包。"
                            "支持: \"player\"(玩家)、角色ID、角色名称。"
                            "不传则只创建定义。"
                        ),
                        required=False,
                    ),
                ],
            ),
            ToolDefinition(
                name="create_consumable",
                description=(
                    "创建消耗品。消耗品使用与技能相同的词条系统，根据稀有度自动决定词条数量和强度。"
                    "一次调用可批量创建多个消耗品。"
                    "可通过 for_entity 参数在创建后立即添加到目标角色背包。\n\n"
                ) + (self._build_create_consumable_hint() if self.world else ""),
                parameters=[
                    ToolParameter(
                        name="consumables",
                        type="array",
                        description=(
                            "消耗品列表。每项格式:\n"
                            '{\n'
                            '  "name": "物品名",\n'
                            '  "description": "物品描述",\n'
                            '  "rarity": 45,\n'
                            '  "tags": ["丹药", "治疗"],\n'
                            '  "combat_only": true,\n'
                            '  "quantity": 2,\n'
                            '  "creator_stats": {"level": 3, "force": 65, "tenacity": 50, "agility": 55},\n'
                            '  "affixes": [\n'
                            '    {"type": "damage|heal|buff|shield|dispel|lifesteal|fixed_damage|stun",\n'
                            '     "target": "enemy|self|all_enemy|all_ally"}\n'
                            '  ]\n'
                            '}\n'
                            "词条数量由稀有度决定(凡俗1条→大道4条)，不足系统随机补足，多余裁剪。效果数值由系统自动决定。\n"
                            "combat_only=true 时从战斗词条池选取，false 时从非战斗词条池(突破加成/经验提升/持续恢复等)选取。\n\n"
                            "creator_stats（制作者快照）:\n"
                            "  消耗品的效果威力取决于制作者而非使用者的实力。系统会在创建时快照制作者的属性，战斗中按此计算伤害/治疗/等级衰减。\n"
                            "  - level: 制作者等级，决定该物品对不同境界目标的衰减系数\n"
                            "  - force/tenacity/agility: 制作者的战斗属性\n"
                            "  若不传 creator_stats，系统默认使用玩家当前属性。"
                        ),
                        required=True,
                    ),
                    ToolParameter(
                        name="for_entity",
                        type="string",
                        description=(
                            "可选，创建后自动将消耗品添加到目标角色背包。"
                            "支持: \"player\"(玩家)、角色ID、角色名称。"
                            "不传则只创建定义。每种消耗品的数量取自其 quantity 字段。"
                        ),
                        required=False,
                    ),
                ],
            ),
            ToolDefinition(
                name="generate_equipment",
                description=(
                    "根据场景上下文动态生成装备。"
                    "LLM 生成装备名称、描述和标签，系统概率驱动计算属性加成。"
                    "可通过 for_entity 参数在创建后立即添加到目标角色背包。"
                ),
                parameters=[
                    ToolParameter(
                        name="slot_type",
                        type="string",
                        description=self._build_slot_type_desc(),
                        required=True,
                    ),
                    ToolParameter(
                        name="level",
                        type="integer",
                        description="装备等级（0~13，对应境界：0凡品/1练气/3金丹/6炼虚/9渡劫/13大罗）",
                        required=False,
                    ),
                    ToolParameter(
                        name="rarity",
                        type="integer",
                        description=(
                            "品质等级（0~100）。"
                            "请根据场景上下文主动传入合适的值："
                            "0~29 劣质（破损/杂兵掉落），"
                            "30~49 普通（常见物品/普通怪物），"
                            "50~69 优良（精英怪物/任务奖励），"
                            "70~84 稀有（boss掉落/秘境探索），"
                            "85~100 传说（远古遗物/天材地宝）。"
                            "未传则默认 30~70 随机。"
                        ),
                        required=False,
                    ),
                    ToolParameter(
                        name="context",
                        type="string",
                        description="场景描述，如'击败金丹期妖兽后掉落'",
                        required=False,
                    ),
                    ToolParameter(
                        name="for_entity",
                        type="string",
                        description=(
                            "可选，创建后自动将装备添加到目标角色背包。"
                            "支持: \"player\"(玩家)、角色ID、角色名称。"
                            "不传则只创建定义。"
                        ),
                        required=False,
                    ),
                ],
            ),
        ]

    def execute_tool(self, tool_name: str, params: dict) -> ModuleResult:
        handlers = {
            "generate_material": self._generate_material,
            "generate_equipment": self._generate_equipment,
            "create_consumable": self._create_consumable,
        }
        handler = handlers.get(tool_name)
        if handler is None:
            return ModuleResult(success=False, log=f"未知工具: {tool_name}")
        game_state = self._get_game_state()
        return handler(params, game_state)

    def handle_websocket(self, message: dict, game_state) -> dict | None:
        """处理 WebSocket 消息。"""
        self.on_load()
        msg_type = message.get("type", "")

        if msg_type == "crafting_open":
            return self._ws_crafting_open(game_state)

        if msg_type == "crafting_preview":
            return self._ws_crafting_preview(message, game_state)

        if msg_type == "crafting_execute":
            return self._ws_crafting_execute(message, game_state)

        return None

    def _ws_crafting_open(self, game_state) -> dict:
        """前端打开制作面板时调用，返回题材列表、角色技能和当前灵力。"""
        if not self._engine:
            return {"type": "crafting_state", "error": "制作系统未加载"}
        result = self._get_craftable_themes({}, game_state)
        spiritual_power = 0
        if game_state:
            player = game_state.get_player()
            if player:
                spiritual_power = getattr(player, "spiritual_power", 0)
        return {"type": "crafting_state", **result.data, "spiritual_power": spiritual_power,
                "equip_slots": self._engine.get_equip_slots()}

    def _ws_crafting_preview(self, message: dict, game_state) -> dict:
        """前端请求预览。"""
        params = {
            "theme": message.get("theme", ""),
            "material_ids": message.get("material_ids", []),
            "spiritual_power": message.get("spiritual_power", 0),
            "equip_slot": message.get("equip_slot", ""),
        }
        result = self._get_crafting_preview(params, game_state)
        return {"type": "crafting_preview_result", **result.data, "success": result.success, "log": result.log}

    def _ws_crafting_execute(self, message: dict, game_state) -> dict:
        """前端执行制作。"""
        params = {
            "theme": message.get("theme", ""),
            "material_ids": message.get("material_ids", []),
            "spiritual_power": message.get("spiritual_power", 0),
            "equip_slot": message.get("equip_slot", ""),
        }
        result = self._craft_item(params, game_state)
        return {"type": "crafting_result", "success": result.success, "log": result.log, "data": result.data}

    # ── 工具实现 ──────────────────────────

    def _get_craftable_themes(self, params: dict, game_state) -> ModuleResult:
        """获取可用题材列表。"""
        if not self._engine:
            return ModuleResult(success=False, log="制作系统未加载")

        themes = []
        for theme_name, theme_config in self._config_data.get("themes", {}).items():
            skill_name = theme_config.get("bonus_skill", "")
            themes.append({
                "name": theme_name,
                "bonus_skill": skill_name,
                "default_tags": theme_config.get("default_tags", []),
                "max_slots": self._config_data.get("sealing", {}).get("max_slots", 6),
            })

        player_skills = {}
        if game_state:
            player = game_state.get_player()
            if player:
                for theme_info in themes:
                    skill = theme_info["bonus_skill"]
                    val = getattr(player, skill, 0)
                    player_skills[skill] = val

        return ModuleResult(
            success=True,
            data={"themes": themes, "player_skills": player_skills},
        )

    def _get_crafting_preview(self, params: dict, game_state) -> ModuleResult:
        """预览炼制参数。"""
        if not self._engine:
            return ModuleResult(success=False, log="制作系统未加载")

        theme = params.get("theme", "")
        material_ids = params.get("material_ids", [])
        spiritual_power = params.get("spiritual_power", 0)

        materials = self._resolve_materials(material_ids, game_state)
        max_sp = self._engine.calc_max_spiritual_power(materials)

        ok, msg = self._engine.validate_input(theme, material_ids, spiritual_power, max_sp)
        if not ok:
            return ModuleResult(success=False, log=msg)

        skill_value = self._get_skill_value(theme, game_state)
        is_bonus = self._is_bonus_theme(theme, game_state)

        loss_rate = self._engine.calc_loss_rate(theme, skill_value, is_bonus)
        effective_power = self._engine.calc_effective_power(spiritual_power, loss_rate)
        level_info = self._engine.determine_level(effective_power)

        material_tags = list(set(
            tag for m in materials for tag in m.get("tags", [])
        ))

        return ModuleResult(
            success=True,
            data={
                "theme": theme,
                "loss_rate": round(loss_rate, 4),
                "loss_rate_percent": f"{loss_rate * 100:.1f}%",
                "effective_power": effective_power,
                "level": level_info,
                "material_tags": material_tags,
                "skill_used": self._engine.get_bonus_skill(theme),
                "skill_value": skill_value,
                "is_bonus": is_bonus,
                "max_spiritual_power": max_sp,
            },
        )

    def _craft_item(self, params: dict, game_state) -> ModuleResult:
        """执行物品制作。"""
        if not self._engine:
            return ModuleResult(success=False, log="制作系统未加载")

        theme = params.get("theme", "")
        material_ids = params.get("material_ids", [])
        spiritual_power = params.get("spiritual_power", 0)

        materials = self._resolve_materials(material_ids, game_state)
        max_sp = self._engine.calc_max_spiritual_power(materials)

        ok, msg = self._engine.validate_input(theme, material_ids, spiritual_power, max_sp)
        if not ok:
            return ModuleResult(success=False, log=msg)

        if not game_state:
            return ModuleResult(success=False, log="游戏状态不可用")

        player = game_state.get_player()
        current_sp = getattr(player, "spiritual_power", 0)
        if current_sp < spiritual_power:
            return ModuleResult(
                success=False,
                log=f"灵力不足: 当前 {current_sp}, 需要 {spiritual_power}",
            )

        current_ds = player.attrs.get("divine_sense", 0)
        if current_ds < spiritual_power:
            return ModuleResult(
                success=False,
                log=f"神识不足: 当前 {current_ds}, 需要 {spiritual_power}",
            )

        if len(material_ids) > 0 and len(materials) < len(material_ids):
            return ModuleResult(success=False, log="部分材料不在背包中")

        skill_value = self._get_skill_value(theme, game_state)
        is_bonus = self._is_bonus_theme(theme, game_state)
        loss_rate = self._engine.calc_loss_rate(theme, skill_value, is_bonus)
        effective_power = self._engine.calc_effective_power(spiritual_power, loss_rate)
        level_info = self._engine.determine_level(effective_power)
        rarity = self._engine.calc_quality(materials)
        default_tags = self._engine.get_default_tags(theme)

        equip_slot = params.get("equip_slot", "")
        is_equipment = theme == "法宝" and equip_slot

        # 记录创作者属性（炼制时快照）
        # level 由有效灵力查境界门槛表决定，非玩家当前等级
        creator_stats = {
            "level": level_info["level"],
            "force": player.attrs.get("force", 50),
            "tenacity": player.attrs.get("tenacity", 50),
            "agility": player.attrs.get("agility", 50),
        }

        # ── LLM 生成（在扣除资源之前） ──
        craft_warnings: list[str] = []

        if is_equipment and self._equip_gen:
            level = level_info["level"]
            stats = self._equip_gen.generate_stats(equip_slot, level, rarity, materials)
            ability_count = stats.get("ability_count", 0)
            llm_prompt = build_equipment_prompt(
                slot_type=equip_slot,
                slot_name=equip_slot,
                materials=materials,
                effective_power=effective_power,
                rarity=rarity,
                level_label=level_info["label"],
                ability_count=ability_count,
            )
            raw_result = self._call_llm(llm_prompt)
            item_spec = None
            if raw_result:
                item_spec = parse_equipment_result(raw_result)
            if item_spec is None:
                logger.warning("装备生成 LLM 失败")
                return ModuleResult(
                    success=False,
                    log="装备生成失败：LLM 未返回有效结果，请重新调用 craft_item 重试。",
                )
        else:
            llm_prompt = build_crafting_prompt(
                theme=theme,
                materials=materials,
                effective_power=effective_power,
                rarity=rarity,
                level_label=level_info["label"],
            )
            item_spec = self._call_llm_for_craft(llm_prompt, warnings=craft_warnings)
            if item_spec is None:
                logger.warning("LLM 炼制失败")
                return ModuleResult(
                    success=False,
                    log="炼制失败：LLM 未返回有效结果，请重试。",
                )

        # 确保 tags 合并
        merged_tags = list(set(default_tags + item_spec.get("tags", [])))
        item_spec["tags"] = merged_tags
        item_spec["rarity"] = rarity
        if not is_equipment:
            item_spec["creator_stats"] = creator_stats

        # ── LLM 成功后才扣除资源 ──
        # 扣除灵力
        setattr(player, "spiritual_power", current_sp - spiritual_power)
        # 扣除神识（等于封存灵力值）
        player.attrs["divine_sense"] = current_ds - spiritual_power
        # 扣除材料
        for mat_id in material_ids:
            remove_result = self.bus.request(
                PluginEvent.INVENTORY_REMOVE_ITEM,
                item_id=mat_id, count=1,
            )
            if remove_result is None or not getattr(remove_result, 'success', False):
                logger.warning("_craft_item: 材料移除失败: %s", mat_id)

        # ── 创建物品 ──
        if is_equipment and self._equip_gen:
            create_result = self._create_equipment_from_craft(
                equip_slot, materials, level_info["level"], rarity, level_info, default_tags, item_spec,
                stats=stats,
            )
        else:
            create_result = self._create_consumable_internal(item_spec, game_state)

        if not create_result.success:
            # 退还灵力、神识和材料
            self._refund_resources(player, current_sp, current_ds, material_ids)
            return ModuleResult(
                success=False,
                log=f"物品创建失败: {create_result.log}",
            )

        if is_equipment:
            created_data = create_result.data.get("item", {})
            created = [created_data] if created_data else []
        else:
            created = create_result.data.get("created_consumables", [])

        craft_log = (
            f"炼制成功: {created[0]['name'] if created else '未知'} "
            f"(品质:{rarity}, 等级:{level_info['label']}, "
            f"灵力:{effective_power}, 损耗:{loss_rate*100:.0f}%)"
        )
        # 收集子方法产生的 WARNING
        all_warnings: list[str] = []
        all_warnings.extend(craft_warnings)
        if is_equipment:
            equip_warnings = created[0].pop("_warnings", []) if created else []
            all_warnings.extend(equip_warnings)
        else:
            all_warnings.extend(create_result.data.get("_warnings", []))
        if all_warnings:
            craft_log += "\n⚠ 以下问题需要关注：\n" + "\n".join(all_warnings)

        # 定价
        price = self._calc_price(effective_power, rarity)

        return ModuleResult(
            success=True,
            data={
                "crafted_item": created[0] if created else None,
                "craft_summary": {
                    "theme": theme,
                    "loss_rate": round(loss_rate, 4),
                    "effective_power": effective_power,
                    "level": level_info,
                    "rarity": rarity,
                    "spiritual_power_consumed": spiritual_power,
                    "spirit_stone_price": price,
                    "materials_consumed": [m.get("name", mat_id) for m, mat_id in zip(materials, material_ids)],
                },
                "_events": [
                    ("item_crafted", {
                        "item": created[0] if created else None,
                        "summary": {
                            "theme": theme,
                            "rarity": rarity,
                            "effective_power": effective_power,
                            "level_label": level_info["label"],
                        },
                    }),
                ],
            },
            log=craft_log,
        )

    # ── 内部方法 ──────────────────────────

    def _refund_resources(self, player, original_sp: int, original_ds: int, material_ids: list[str]) -> None:
        """退还灵力、神识和材料（创建失败时调用）。"""
        setattr(player, "spiritual_power", original_sp)
        player.attrs["divine_sense"] = original_ds
        for mat_id in material_ids:
            add_item_to_character(player, mat_id, 1)
        logger.info("炼制失败，已退还灵力/神识/材料")

    def _register_equipment_abilities(
        self,
        llm_abilities: list[dict],
        level: int,
        rarity: int,
    ) -> tuple[list[str], list[str]]:
        """使用 EventBus 调用 affix_generate_ability 注册法宝技能。"""
        from lingmo_engine.core.events import PluginEvent

        if not llm_abilities:
            return [], []

        affix_defs = {}
        tag_cost_map = {}
        if self.world:
            affix_defs = self.world.get_effect_affixes()
            tag_cost_map = self.world.get_tag_cost_map()

        rarity_info = {"id": "common", "name": "灵韵", "affix_count": 1, "max_stack": 3, "guarantee": None}
        exclusions = []
        if self.world:
            rarity_info = self.world.get_ability_rarity_info(rarity)
            exclusions = self.world.get_effect_exclusions()

        ability_ids = []
        warnings: list[str] = []

        for abl in llm_abilities:
            abl_input = {
                "name": abl.get("name", "法宝技能"),
                "rarity": rarity,
                "category": abl.get("category", "attack"),
                "description": abl.get("description", ""),
                "tags": abl.get("tags", []),
                "affixes": abl.get("affixes", abl.get("effects", [])),
            }

            result = None
            if self._bus:
                result = self._bus.request(
                    PluginEvent.ABILITY_GENERATE,
                    abl_input, affix_defs, rarity_info,
                    tag_cost_map=tag_cost_map,
                    exclusions=exclusions,
                    warnings=warnings,
                )
            else:
                # EventBus 不可用：降级直接调用
                from lingmo_engine.plugins.combat.ability_generator import (
                    affix_generate_ability,
                )
                result = affix_generate_ability(
                    ability_input=abl_input,
                    affix_defs=affix_defs,
                    rarity_info=rarity_info,
                    tag_cost_map=tag_cost_map,
                    exclusions=exclusions,
                    warnings=warnings,
                )

            if result is None:
                msg = (
                    f"WARNING: 法宝技能 '{abl.get('name', '未知')}' 被系统拒绝"
                    "（超出预算或效果无效）。建议：降低技能等级或稀有度，"
                    "或减少 effect_slots 的 weight"
                )
                logger.warning(
                    "法宝技能被系统拒绝（超出预算或无效效果）: %s",
                    abl.get("name", "未知"),
                )
                warnings.append(msg)
                continue

            ability_ids.append(result["id"])

            # 通过 registry 直接持久化技能（不操控 combat 内部状态）
            game_state = self._get_game_state()
            if game_state:
                game_state.add_registry_ability(result["id"], result)

            # custom_abilities 已通过 GameState 注册表持久化，
            # CombatPlugin 运行时从注册表读取，无需直接操控其内部状态

        return ability_ids, warnings

    def _create_equipment_from_craft(
        self, slot_type: str, materials: list[dict],
        level: int, rarity: int, level_info: dict,
        default_tags: list[str], llm_spec: dict,
        stats: dict | None = None,
    ) -> ModuleResult:
        """从炼制流程创建装备物品。"""
        if stats is None:
            stats = self._equip_gen.generate_stats(slot_type, level, rarity, materials)
        merged_tags = list(set(default_tags + llm_spec.get("tags", [])))

        # 生成法宝技能
        ability_ids = []
        equip_warnings: list[str] = []
        if slot_type == "life_treasure" and llm_spec.get("abilities"):
            ability_ids, equip_warnings = self._register_equipment_abilities(
                llm_spec["abilities"], level, rarity,
            )

        equip_data = {
            "name": llm_spec.get("name", f"装备·{slot_type}"),
            "category": "equipment",
            "rarity": rarity,
            "description": llm_spec.get("description", ""),
            "equip_slot": slot_type,
            "stat_bonus": stats["stat_bonus"],
            "buffs": stats["buffs"],
            "abilities": ability_ids,
            "tags": merged_tags,
            "_warnings": equip_warnings,
        }

        # 灵石定价
        total_sp = sum(m.get("spirit_power", 0) for m in materials)
        equip_data["sell_price"] = self._calc_price(total_sp, rarity) if total_sp > 0 else 0

        return self.bus.request(
            PluginEvent.INVENTORY_REGISTER_AND_ADD,
            item_data=equip_data,
        )

    def _generate_equipment(self, params: dict, game_state) -> ModuleResult:
        """DM 场景生成装备。"""
        if not self._engine or not self._equip_gen:
            return ModuleResult(success=False, log="装备生成系统未加载")

        slot_type = params.get("slot_type", "")
        level = max(0, min(13, params.get("level", 0)))
        rarity_input = params.get("rarity")
        if rarity_input is not None:
            rarity = max(0, min(100, rarity_input))
        else:
            rarity = random.randint(30, 70)
        context = params.get("context", "")

        if not slot_type.strip():
            return ModuleResult(success=False, log="装备部位不能为空")

        if not game_state:
            return ModuleResult(success=False, log="游戏状态不可用")

        # 概率驱动生成属性
        stats = self._equip_gen.generate_stats(slot_type, level, rarity, seed=None)

        # 获取槽位名称
        slots = self._engine.get_equip_slots()
        slot_name = slot_type
        for s in slots:
            if s.get("id") == slot_type:
                slot_name = s.get("name", slot_type)
                break

        # 计算法宝技能数量
        ability_count = stats.get("ability_count", 0)

        # LLM 生成命名/描述/标签
        level_info = self._engine.get_level_info(level)
        prompt = build_equipment_prompt(
            slot_type=slot_type,
            slot_name=slot_name,
            materials=[],
            effective_power=level_info["representative_power"],
            rarity=rarity,
            level_label=level_info["label"],
            context=context,
            ability_count=ability_count,
        )
        raw_result = self._call_llm(prompt)

        llm_spec = None
        if raw_result:
            llm_spec = parse_equipment_result(raw_result)

        if llm_spec is None:
            logger.warning("装备生成 LLM 失败")
            return ModuleResult(
                success=False,
                log="装备生成失败：LLM 未返回有效结果，请重新调用 generate_equipment 重试。",
            )

        # 生成法宝技能
        ability_ids = []
        gen_warnings: list[str] = []
        if llm_spec.get("abilities"):
            ability_ids, gen_warnings = self._register_equipment_abilities(
                llm_spec["abilities"], level, rarity,
            )

        # 组装装备
        equip_data = {
            "name": llm_spec.get("name", f"{slot_name}·无名"),
            "category": "equipment",
            "rarity": rarity,
            "description": llm_spec.get("description", ""),
            "equip_slot": slot_type,
            "stat_bonus": stats["stat_bonus"],
            "buffs": stats["buffs"],
            "abilities": ability_ids,
            "tags": llm_spec.get("tags", []),
            "_warnings": gen_warnings,
        }

        # 注册装备定义（不自动添加到背包，由 LLM 决定分配）
        register_result = self.bus.request(
            PluginEvent.INVENTORY_REGISTER_ONLY,
            item_data=equip_data,
        )

        if not register_result.success:
            return ModuleResult(success=False, log=f"装备创建失败: {register_result.log}")

        item_data = register_result.data.get("item", {})

        log = f"生成装备: {item_data.get('name', '?')} (品质:{rarity}, 部位:{slot_name})"
        if gen_warnings:
            log += "\n⚠ 以下问题需要关注：\n" + "\n".join(gen_warnings)

        result_data = {
            "equipment": {
                "name": item_data.get("name", ""),
                "slot": slot_type,
                "rarity": rarity,
                "stat_bonus": stats["stat_bonus"],
                "abilities": ability_ids,
                "description": llm_spec.get("description", ""),
                "tags": llm_spec.get("tags", []),
                "item_id": item_data.get("id", ""),
            },
        }

        # for_entity: 创建后立即添加到目标角色背包
        for_entity = params.get("for_entity")
        if for_entity and game_state:
            char = find_entity(game_state.character_manager, for_entity)
            if char:
                add_item_to_character(char, item_data.get("id", ""), 1)
                result_data["assigned_to"] = char.name
                log += f"\n已添加到「{char.name}」背包"
            else:
                log += f"\n⚠ 未找到角色「{for_entity}」，装备仅创建定义"

        return ModuleResult(
            success=True,
            data=result_data,
            log=log,
        )

    def _load_crafting_config(self) -> Optional[dict]:
        """从世界目录加载 crafting.yaml。"""
        if not self.world:
            return None
        config_path = self.world.get_item_config_path("crafting.yaml")
        if not config_path:
            logger.warning("crafting.yaml 不存在")
            return None
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def set_game_state(self, state):
        """注入 GameState 引用（由 PluginRegistry 自动调用）。"""
        self._game_state = state

    def _get_game_state(self):
        return self._game_state

    def get_static_dir(self) -> str | None:
        d = os.path.join(os.path.dirname(__file__), "static")
        return d if os.path.isdir(d) else None

    def _get_skill_value(self, theme: str, game_state) -> int:
        """获取角色对应该题材的技能值。"""
        if not game_state:
            return 0
        player = game_state.get_player()
        if not player:
            return 0
        if not self._engine:
            return 0
        skill_name = self._engine.get_bonus_skill(theme)
        return int(getattr(player, skill_name, 0))

    def _is_bonus_theme(self, theme: str, game_state) -> bool:
        """判断当前角色的修行方向是否匹配题材（从配置读取映射）。"""
        if not game_state:
            return False
        player = game_state.get_player()
        if not player:
            return False

        if not self._engine:
            return False

        # 从 YAML 配置的 cultivation_path 字段读取
        theme_config = self._engine.get_theme_config(theme) or {}
        expected_path = theme_config.get("cultivation_path", "")
        player_path = getattr(player, "cultivation_path", "")
        return player_path == expected_path

    def _resolve_materials(self, material_ids: list[str], game_state) -> list[dict]:
        """解析材料ID为材料详情。"""
        if not game_state or not material_ids:
            return []

        result = self.bus.request(PluginEvent.INVENTORY_GET_INVENTORY)
        if not result.success:
            return []

        inventory = result.data.get("inventory", [])
        inv_map = {item.get("id"): item for item in inventory}

        materials = []
        for mid in material_ids:
            item = inv_map.get(mid)
            if item:
                materials.append({
                    "name": item.get("name", mid),
                    "rarity": item.get("rarity", 1),
                    "tags": item.get("tags", []),
                    "spirit_power": item.get("spirit_power", 0),
                })
        return materials

    def _call_llm(
        self,
        prompt: str,
        system_prompt: str = "你是修仙世界的炼器大师。只返回JSON，不要其他文字。",
        mode: str = "fast",
        thinking: bool | None = False,
    ) -> Optional[str]:
        """统一 LLM 调用入口。

        通过 LLMProviderAccess 直接调用 Provider，绕过 asyncio.Lock，
        避免 tool_executor 线程中死锁。
        """
        try:
            if not self._llm_access:
                return None

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ]

            response = self._llm_access.chat(messages, mode=mode, thinking=thinking)

            if hasattr(response, "full_text"):
                return response.full_text
            if hasattr(response, "text"):
                return response.text
            return str(response)

        except Exception as e:
            logger.error("LLM 调用失败: %s", e)
            return None

    def _call_llm_for_craft(self, prompt: str, warnings: list[str] | None = None) -> Optional[dict]:
        """调用 LLM 生成物品（消耗品路径，返回解析后的 dict）。"""
        raw_text = self._call_llm(
            prompt,
            system_prompt="你是修仙世界的炼器大师，负责根据材料和灵力参数生成物品信息。只返回JSON，不要其他文字。",
        )
        if raw_text is None:
            return None
        return parse_llm_result(raw_text, warnings=warnings)

    def _generate_material(self, params: dict, game_state) -> ModuleResult:
        """根据场景上下文 LLM 生成材料。"""
        if not self._engine:
            return ModuleResult(success=False, log="制作系统未加载")

        context = params.get("context", "")
        count = max(1, min(3, params.get("count", 1)))

        if not context.strip():
            return ModuleResult(success=False, log="场景上下文不能为空")

        if not game_state:
            return ModuleResult(success=False, log="游戏状态不可用")

        valid_tags = self._load_valid_tags()

        prompt = build_material_prompt(context, count, valid_tags)
        raw_result = self._call_llm_raw(prompt)

        if raw_result is not None and isinstance(raw_result, str):
            materials = parse_material_result(raw_result, valid_tags)
        else:
            materials = []

        if not materials:
            materials = [{
                "name": "灵气碎屑",
                "rarity": 1,
                "tags": [],
                "description": "散落的微弱灵气结晶",
            }]

        created = []
        for mat in materials[:count]:
            spirit_power = self._engine.calc_material_power(mat["rarity"])
            mat["spirit_power"] = spirit_power
            mat["category"] = "material"
            mat["stackable"] = True

            # 注册材料定义（不自动添加到背包，由 LLM 决定分配）
            add_result = self.bus.request(
                PluginEvent.INVENTORY_REGISTER_ONLY,
                item_data=mat,
            )

            if add_result.success:
                item_data = add_result.data.get("item", {})
                created.append({
                    "name": mat["name"],
                    "rarity": mat["rarity"],
                    "spirit_power": spirit_power,
                    "tags": mat["tags"],
                    "description": mat["description"],
                    "item_id": item_data.get("id", ""),
                })
            else:
                logger.warning("材料添加到背包失败: %s", add_result.log)

        if not created:
            return ModuleResult(success=False, log="材料生成失败")

        result_data = {"materials": created}
        log = f"生成 {len(created)} 个材料: {', '.join(m['name'] for m in created)}"

        # for_entity: 创建后立即添加到目标角色背包
        for_entity = params.get("for_entity")
        if for_entity and game_state:
            qty = params.get("quantity", 1)
            char = find_entity(game_state.character_manager, for_entity)
            if char:
                for m in created:
                    add_item_to_character(char, m["item_id"], qty)
                result_data["assigned_to"] = char.name
                log += f"\n已添加 {qty}x 到「{char.name}」背包"
            else:
                log += f"\n⚠ 未找到角色「{for_entity}」，材料仅创建定义"

        return ModuleResult(
            success=True,
            data=result_data,
            log=log,
        )

    def _call_llm_raw(self, prompt: str) -> Optional[str]:
        """调用 LLM 返回原始文本（材料生成路径）。"""
        return self._call_llm(
            prompt,
            system_prompt="你是修仙世界的天道。只返回JSON，不要其他文字。",
        )

    def _load_valid_tags(self) -> list[str]:
        """从 _tags.yaml 加载所有合法 tag。"""
        if not self.world:
            return []
        config_path = self.world.get_item_config_path("_tags.yaml")
        if not config_path:
            return []
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        tags = []
        for group in data.get("tag_groups", []):
            tags.extend(group.get("tags", []))
        return tags

    def _load_equip_slots(self) -> list[dict]:
        """从世界目录加载装备槽位定义。"""
        if not self.world:
            return []
        config_path = self.world.get_item_config_path("equip_slots.yaml")
        if not config_path:
            return []
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("slots", [])

    def _build_create_consumable_hint(self) -> str:
        """从世界配置动态生成 create_consumable 工具的提示文本。"""
        world = self.world
        if not world:
            return ""
        # 优先从统一词条定义读取
        affixes = world.get_effect_affixes()
        types = list(affixes.keys()) if affixes else list(world.get_consumable_templates().keys())
        lines = [
            "词条类型: " + " | ".join(types),
        ]
        # 稀有度→词条规则
        rarity_lines = []
        for r in world.item_rarities.get("rarities", []):
            name = r.get("name", "")
            count = r.get("affix_count", "?")
            guarantee = r.get("guarantee")
            g_str = f"，保底一条+{guarantee}" if guarantee else ""
            rarity_lines.append(f"  {name}({r['min']}-{r['max']}): {count}条词条{g_str}")
        if rarity_lines:
            lines.append("稀有度规则:\n" + "\n".join(rarity_lines))
        # 标签：优先使用分组格式
        item_tag_groups = world.get_item_tag_groups()
        if item_tag_groups:
            lines.append("合法标签:")
            for g in item_tag_groups:
                lines.append(f"  {g['name']}: {' | '.join(g['tags'])}")
        else:
            item_tags = world.get_consumable_legal_tags()
            if not item_tags:
                item_tags = world.ability_legal_tags
            tags_flat: list[str] = []
            for group in item_tags:
                tags_flat.extend(group)
            lines.append("合法标签: " + " ".join(tags_flat))
        # 互斥规则提示
        exclusions = world.get_consumable_exclusions()
        if not exclusions:
            exclusions = world.get_ability_exclusions()
        if exclusions:
            exc_strs = [" 和 ".join(g) for g in exclusions]
            lines.append("互斥规则: " + "、".join(exc_strs) + " 不能同时出现")
        return "\n".join(lines)

    def _create_consumable(self, params: dict, game_state) -> ModuleResult:
        """创建消耗品（LLM 工具入口）。"""
        self.on_load()

        world = self.world
        if not world:
            return ModuleResult(success=False, log="世界配置不可用")

        consumables_input = params.get("consumables", [])
        if not consumables_input:
            return ModuleResult(success=False, log="消耗品列表为空")

        created = []
        all_warnings: list[str] = []

        for spec in consumables_input:
            result = self._create_consumable_internal(spec, game_state)
            if result.success:
                created.extend(result.data.get("created_consumables", []))
                all_warnings.extend(result.data.get("_warnings", []))
            else:
                logger.warning("消耗品 '%s' 创建失败: %s", spec.get("name", "?"), result.log)

        if not created:
            return ModuleResult(success=False, log="没有有效的消耗品被创建")

        log = "创建 {} 个消耗品: {}".format(
            len(created),
            "、".join(c["name"] for c in created),
        )
        if all_warnings:
            log += "\n⚠ 以下问题需要关注：\n" + "\n".join(all_warnings)

        result_data: dict = {
            "created_consumables": created,
            "_warnings": all_warnings,
            "_events": [
                ("consumable_created", {
                    "consumables": created,
                }),
            ],
        }

        # for_entity: 创建后立即添加到目标角色背包
        for_entity = params.get("for_entity")
        if for_entity and game_state:
            char = find_entity(game_state.character_manager, for_entity)
            if char:
                for c in created:
                    add_item_to_character(char, c["item_id"], c["quantity"])
                result_data["assigned_to"] = char.name
                log += f"\n已添加到「{char.name}」背包"
            else:
                log += f"\n⚠ 未找到角色「{for_entity}」，消耗品仅创建定义"

        return ModuleResult(
            success=True,
            data=result_data,
            log=log,
        )

    def _create_consumable_internal(self, spec: dict, game_state) -> ModuleResult:
        """单个消耗品创建（供 _create_consumable 和 _craft_item 复用）。"""
        from lingmo_engine.core.events import PluginEvent

        world = self.world
        if not world:
            return ModuleResult(success=False, log="世界配置不可用")

        affix_defs = world.get_effect_affixes()
        tag_cost_map = world.get_tag_cost_map()

        warnings: list[str] = []
        rarity_int = spec.get("rarity", 25)
        rarity_info = world.get_consumable_rarity_info(rarity_int)
        combat_only = spec.get("combat_only", True)

        result = None
        if self._bus:
            result = self._bus.request(
                PluginEvent.ABILITY_GENERATE,
                spec, affix_defs, rarity_info,
                tag_cost_map=tag_cost_map,
                exclusions=world.get_effect_exclusions(),
                combat_only=combat_only,
                warnings=warnings,
            )
        else:
            # EventBus 不可用：降级直接调用
            from lingmo_engine.plugins.combat.ability_generator import (
                affix_generate_ability,
            )
            result = affix_generate_ability(
                spec, affix_defs, rarity_info,
                tag_cost_map=tag_cost_map,
                exclusions=world.get_effect_exclusions(),
                combat_only=combat_only,
                warnings=warnings,
            )
        if result is None:
            msg = (
                f"WARNING: 消耗品 '{spec.get('name', '?')}' 生成失败，已跳过。"
                "建议：检查消耗品的 level/rarity/effect_slots 是否合理"
            )
            logger.warning("消耗品 '%s' 生成失败，跳过", spec.get("name", "?"))
            return ModuleResult(
                success=False,
                log=msg,
                data={"_warnings": [msg]},
            )

        # 生成唯一物品 ID
        item_id = generate_id("consumable")

        # 构建消耗品数据
        player_level = 1
        if game_state:
            try:
                player_level = game_state.get_player().level
            except Exception:
                pass

        creator_stats_input = spec.get("creator_stats")
        if creator_stats_input and isinstance(creator_stats_input, dict):
            creator_stats = {
                k: int(v) for k, v in creator_stats_input.items()
                if k in ("level", "force", "tenacity", "agility")
            }
        else:
            creator_stats = {"level": player_level, "force": 50, "tenacity": 50, "agility": 50}

        quantity = spec.get("quantity", 1)

        item_data = {
            "id": item_id,
            "name": spec.get("name", ""),
            "category": "consumable",
            "rarity": rarity_int,
            "description": spec.get("description", ""),
            "sell_price": spec.get("sell_price", 0),
            "tags": spec.get("tags", []),
            "combat_only": spec.get("combat_only", True),
            "costs": [],
            "effects": result["effects"],
            "creator_stats": creator_stats,
            "quantity": quantity,
        }

        # 通过 inventory 插件注册物品定义
        register_result = self.bus.request(
            PluginEvent.INVENTORY_REGISTER_ONLY,
            item_data=item_data,
        )
        if not register_result.success:
            logger.warning("消耗品 '%s' 注册失败: %s", spec.get("name", "?"), register_result.log)
            return ModuleResult(success=False, log=register_result.log, data={"_warnings": []})

        return ModuleResult(
            success=True,
            data={
                "created_consumables": [{
                    "item_id": item_id,
                    "name": item_data["name"],
                    "quantity": quantity,
                    "rarity": rarity_int,
                    "rarity_name": rarity_info.get("name", "普通"),
                    "rarity_color": rarity_info.get("color", "#a0a0a0"),
                    "combat_only": item_data["combat_only"],
                    "effects": result["effects"],
                }],
                "_warnings": warnings,
            },
        )

    def _calc_price(self, spirit_power: int, rarity: int) -> int:
        """通过 world 公共接口计算定价，回退到简单公式。"""
        if self.world:
            try:
                return self.world.get_pricing_engine().calc_price(spirit_power, rarity)
            except Exception:
                pass
        return max(1, int(spirit_power * (1 + rarity / 200.0)))
