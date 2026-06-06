"""LLM 角色创建功能测试。"""
import yaml
from pathlib import Path

import pytest

from lingmo_engine.core.character import Character, CharacterType
from lingmo_engine.core.character_manager import CharacterManager
from lingmo_engine.core.events import EventBus, PluginEvent


class TestCharacterTemporary:
    """Character.temporary 字段测试。"""

    def test_default_temporary_is_false(self):
        c = Character(id=1, name="test", char_type=CharacterType.NPC)
        assert c.temporary is False

    def test_monster_temporary(self):
        c = Character(id=2, name="wolf", char_type=CharacterType.MONSTER, temporary=True)
        assert c.temporary is True

    def test_to_dict_includes_temporary(self):
        c = Character(id=1, name="test", char_type=CharacterType.NPC, temporary=False)
        d = c.to_dict()
        assert "temporary" in d
        assert d["temporary"] is False

    def test_to_dict_temporary_true(self):
        c = Character(id=2, name="wolf", char_type=CharacterType.MONSTER, temporary=True)
        d = c.to_dict()
        assert d["temporary"] is True

    def test_from_dict_restores_temporary(self):
        data = {"id": 2, "name": "wolf", "char_type": "monster", "temporary": True}
        c = Character.from_dict(data)
        assert c.temporary is True

    def test_from_dict_missing_temporary_defaults_false(self):
        data = {"id": 1, "name": "test", "char_type": "npc"}
        c = Character.from_dict(data)
        assert c.temporary is False


class TestCharacterManagerNPC:
    """CharacterManager NPC 文件和临时角色管理。"""

    def _make_npc_dir(self, tmp_path: Path) -> Path:
        npc_dir = tmp_path / "npcs"
        npc_dir.mkdir()
        return npc_dir

    def _write_npc_file(self, npc_dir: Path, char_id: int, name: str):
        data = {
            "id": char_id,
            "name": name,
            "char_type": "npc",
            "temporary": False,
            "attrs": {"vitality": 100},
        }
        (npc_dir / f"npc_{char_id}.yaml").write_text(
            yaml.dump(data, allow_unicode=True), encoding="utf-8"
        )

    def test_load_npc_dir(self, tmp_path):
        npc_dir = self._make_npc_dir(tmp_path)
        self._write_npc_file(npc_dir, 1, "商人甲")
        self._write_npc_file(npc_dir, 2, "道士乙")

        cm = CharacterManager()
        cm.add_character(Character(id=0, name="玩家", char_type=CharacterType.PLAYER))
        cm.load_npc_dir(npc_dir)

        assert cm.get(1) is not None
        assert cm.get(1).name == "商人甲"
        assert cm.get(2) is not None
        assert cm.get(2).name == "道士乙"

    def test_load_npc_dir_empty(self, tmp_path):
        npc_dir = self._make_npc_dir(tmp_path)
        cm = CharacterManager()
        cm.load_npc_dir(npc_dir)
        assert cm.count() == 0

    def test_load_npc_dir_missing(self, tmp_path):
        cm = CharacterManager()
        cm.load_npc_dir(tmp_path / "nonexistent")
        assert cm.count() == 0

    def test_cleanup_temporary(self):
        cm = CharacterManager()
        cm.add_character(Character(id=0, name="玩家", char_type=CharacterType.PLAYER))
        cm.add_character(Character(id=1, name="妖狼", char_type=CharacterType.MONSTER, temporary=True))
        cm.add_character(Character(id=2, name="商人", char_type=CharacterType.NPC, temporary=False))
        cm.add_character(Character(id=3, name="邪修", char_type=CharacterType.MONSTER, temporary=True))

        removed = cm.cleanup_temporary([1, 2, 3])
        assert removed == [1, 3]
        assert cm.get(1) is None
        assert cm.get(2) is not None
        assert cm.get(3) is None

    def test_cleanup_temporary_empty_ids(self):
        cm = CharacterManager()
        cm.add_character(Character(id=0, name="玩家", char_type=CharacterType.PLAYER))
        cm.add_character(Character(id=1, name="妖狼", char_type=CharacterType.MONSTER, temporary=True))

        removed = cm.cleanup_temporary([])
        assert removed == []
        assert cm.get(1) is not None


class TestCharacterManagerNPCFiles:
    """CharacterManager NPC 文件读写。"""

    def test_save_npc_file(self, tmp_path):
        npc_dir = tmp_path / "npcs"
        npc_dir.mkdir()
        cm = CharacterManager()
        c = Character(id=5, name="白云道人", char_type=CharacterType.NPC, attrs={"vitality": 200})
        cm.save_npc_file(c, npc_dir)

        path = npc_dir / "npc_5.yaml"
        assert path.exists()
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["name"] == "白云道人"
        assert data["temporary"] is False

    def test_delete_npc_file(self, tmp_path):
        npc_dir = tmp_path / "npcs"
        npc_dir.mkdir()
        path = npc_dir / "npc_3.yaml"
        path.write_text("test", encoding="utf-8")
        assert path.exists()

        cm = CharacterManager()
        cm.delete_npc_file(3, npc_dir)
        assert not path.exists()

    def test_delete_npc_file_not_exists(self, tmp_path):
        npc_dir = tmp_path / "npcs"
        npc_dir.mkdir()
        cm = CharacterManager()
        cm.delete_npc_file(999, npc_dir)


from unittest.mock import MagicMock, patch
from lingmo_engine.plugins.character.character_generator import CharacterGenerator
from lingmo_engine.plugins.character.attribute_validator import AttributeValidator


class TestProcessAbilities:
    """abilities 处理逻辑测试。"""

    def test_string_reference_kept(self):
        gen = CharacterGenerator()
        gen._custom_abilities = {"御剑术": {"id": "a1", "name": "御剑术"}}
        skill_names = gen._process_abilities(["御剑术"])
        assert skill_names == ["御剑术"]

    def test_string_reference_not_found_skipped(self):
        gen = CharacterGenerator()
        gen._custom_abilities = {}
        skill_names = gen._process_abilities(["不存在的技能"])
        assert skill_names == []

    def test_object_ability_generates(self):
        gen = CharacterGenerator()
        gen._custom_abilities = {}
        gen._world = None
        ability_input = {
            "name": "烈焰掌",
            "description": "火球攻击",
            "level": 2,
            "rarity": 40,
            "effect_slots": [{"type": "damage", "weight": 2}],
        }
        ability_result = {
            "id": "ability_test123",
            "name": "烈焰掌",
            "effects": [{"type": "damage", "power": 1.5}],
        }
        with patch.object(gen, "_generate_ability", return_value=ability_result):
            skill_names = gen._process_abilities([ability_input])

        assert skill_names == ["ability_test123"]
        assert "ability_test123" in gen._custom_abilities

    def test_mixed_abilities(self):
        gen = CharacterGenerator()
        gen._custom_abilities = {"御剑术": {"id": "a1", "name": "御剑术"}}
        gen._world = None
        ability_input = {
            "name": "冰封",
            "level": 3,
            "rarity": 60,
            "effect_slots": [{"type": "damage", "weight": 1}],
        }
        ability_result = {
            "id": "ability_test456",
            "name": "冰封",
            "effects": [{"type": "damage", "power": 2.0}],
        }
        with patch.object(gen, "_generate_ability", return_value=ability_result):
            skill_names = gen._process_abilities(["御剑术", ability_input])

        assert skill_names == ["御剑术", "ability_test456"]

    def test_empty_abilities(self):
        gen = CharacterGenerator()
        skill_names = gen._process_abilities([])
        assert skill_names == []

    def test_none_abilities(self):
        gen = CharacterGenerator()
        skill_names = gen._process_abilities(None)
        assert skill_names == []


class TestTemporaryDefault:
    """char_type → temporary 默认值测试。"""

    def test_monster_defaults_temporary(self):
        gen = CharacterGenerator()
        data = {"char_type": "monster", "name": "wolf", "attrs": {}}
        gen._apply_temporary_default(data)
        assert data["temporary"] is True

    def test_npc_defaults_not_temporary(self):
        gen = CharacterGenerator()
        data = {"char_type": "npc", "name": "商人", "attrs": {}}
        gen._apply_temporary_default(data)
        assert data["temporary"] is False

    def test_explicit_temporary_not_overridden(self):
        gen = CharacterGenerator()
        data = {"char_type": "monster", "name": "驯服兽", "temporary": False, "attrs": {}}
        gen._apply_temporary_default(data)
        assert data["temporary"] is False

    def test_missing_char_type_defaults_not_temporary(self):
        gen = CharacterGenerator()
        data = {"name": "unknown", "attrs": {}}
        gen._apply_temporary_default(data)
        assert data["temporary"] is False


# ── 补充测试：集成/事件/边界用例 ──


class TestCreateCharacterIntegration:
    """_create_character 完整流程集成测试。"""

    def _make_cm(self):
        cm = CharacterManager()
        cm.add_character(Character(id=0, name="玩家", char_type=CharacterType.PLAYER))
        return cm

    def test_monster_abilities_to_skills(self):
        gen = CharacterGenerator()
        gen._game_state = None
        cm = self._make_cm()
        validator = AttributeValidator()

        char_yaml = """
name: 火眼妖狼
char_type: monster
level: 3
attrs: {vitality: 80, max_vitality: 80, force: 15, tenacity: 5, agility: 12}
abilities:
  - name: "烈焰撕咬"
    level: 2
    rarity: 30
    effect_slots:
      - {type: damage, weight: 2, element: fire}
personality: "凶猛嗜血"
tags: ["妖兽", "火"]
"""
        ability_result = {
            "id": "ability_wolf001",
            "name": "烈焰撕咬",
            "effects": [{"type": "damage", "power": 1.5}],
        }
        with patch.object(gen, "_generate_ability", return_value=ability_result):
            result = gen._create_character(
                {"char_yaml": char_yaml, "story_context": "遭遇战"},
                cm, validator, None,
            )

        assert result.success
        char = cm.get(1)
        assert char is not None
        assert char.temporary is True
        assert "ability_wolf001" in char.abilities
        assert char.name == "火眼妖狼"

    def test_npc_no_abilities(self):
        gen = CharacterGenerator()
        gen._game_state = MagicMock()
        gen._game_state.slot_dir = Path("/tmp/test_slot")
        cm = self._make_cm()
        validator = AttributeValidator()

        char_yaml = """
name: 白云道人
char_type: npc
level: 8
attrs: {vitality: 200, max_vitality: 200, force: 30, tenacity: 20, agility: 15}
personality: "沉稳睿智"
tags: ["修仙者"]
"""
        result = gen._create_character(
            {"char_yaml": char_yaml, "story_context": "剧情需要"},
            cm, validator, None,
        )

        assert result.success
        char = cm.get(1)
        assert char is not None
        assert char.temporary is False
        assert char.name == "白云道人"

    def test_npc_triggers_save_file(self, tmp_path):
        gen = CharacterGenerator()
        gs = MagicMock()
        gs.slot_dir = tmp_path
        gen._game_state = gs
        cm = self._make_cm()
        validator = AttributeValidator()

        char_yaml = """
name: 铁匠
char_type: npc
level: 2
attrs: {vitality: 50, max_vitality: 50}
"""
        gen._create_character(
            {"char_yaml": char_yaml, "story_context": "test"},
            cm, validator, None,
        )

        npc_file = tmp_path / "npcs" / "npc_1.yaml"
        assert npc_file.exists()
        data = yaml.safe_load(npc_file.read_text(encoding="utf-8"))
        assert data["name"] == "铁匠"

    def test_temporary_monster_no_save_file(self, tmp_path):
        gen = CharacterGenerator()
        gs = MagicMock()
        gs.slot_dir = tmp_path
        gen._game_state = gs
        cm = self._make_cm()
        validator = AttributeValidator()

        char_yaml = """
name: 小妖
char_type: monster
level: 1
attrs: {vitality: 30, max_vitality: 30}
"""
        gen._create_character(
            {"char_yaml": char_yaml, "story_context": "test"},
            cm, validator, None,
        )

        npc_dir = tmp_path / "npcs"
        if npc_dir.exists():
            assert list(npc_dir.glob("*.yaml")) == []


class TestUpdateCharacterWithAbilities:
    """_update_character 中 abilities 处理测试。"""

    def _make_cm(self):
        cm = CharacterManager()
        cm.add_character(Character(id=0, name="玩家", char_type=CharacterType.PLAYER))
        cm.add_character(Character(id=5, name="道士", char_type=CharacterType.NPC,
                                   attrs={"vitality": 100}, temporary=False))
        return cm

    def test_update_with_abilities(self):
        gen = CharacterGenerator()
        gen._game_state = None
        cm = self._make_cm()
        validator = AttributeValidator()

        char_yaml = """
name: 道士
char_type: npc
level: 5
attrs: {vitality: 150, max_vitality: 150}
abilities:
  - name: "御剑术"
    level: 3
    rarity: 50
    effect_slots:
      - {type: damage, weight: 2}
"""
        ability_result = {
            "id": "ability_update001",
            "name": "御剑术",
            "effects": [{"type": "damage", "power": 2.0}],
        }
        with patch.object(gen, "_generate_ability", return_value=ability_result):
            result = gen._update_character(
                {"character_id": 5, "char_yaml": char_yaml, "reason": "升级"},
                cm, validator, None,
            )

        assert result.success
        char = cm.get(5)
        assert "ability_update001" in char.abilities
        assert char.level == 5


class TestListCharactersLifecycle:
    """list_characters 输出临时/持久标记测试。"""

    def test_output_contains_lifecycle_markers(self):
        gen = CharacterGenerator()
        cm = CharacterManager()
        cm.add_character(Character(id=0, name="玩家", char_type=CharacterType.PLAYER))
        cm.add_character(Character(id=1, name="妖狼", char_type=CharacterType.MONSTER, temporary=True))
        cm.add_character(Character(id=2, name="商人", char_type=CharacterType.NPC, temporary=False))

        result = gen._list_characters({}, cm)
        assert result.success
        assert "monster·临时" in result.log
        assert "npc·持久" in result.log
        assert "player·持久" in result.log

    def test_output_empty_characters(self):
        gen = CharacterGenerator()
        cm = CharacterManager()
        result = gen._list_characters({}, cm)
        assert result.success
        assert result.data["count"] == 0


class TestGetCharacterSummaries:
    """get_character_summaries 临时/持久标记测试。"""

    def test_summary_contains_lifecycle(self):
        gen = CharacterGenerator()
        cm = CharacterManager()
        cm.add_character(Character(id=0, name="玩家", char_type=CharacterType.PLAYER))
        cm.add_character(Character(id=1, name="妖狼", char_type=CharacterType.MONSTER, temporary=True))
        cm.add_character(Character(id=2, name="道士", char_type=CharacterType.NPC, temporary=False))

        summary = gen.get_character_summaries(cm)
        assert "monster·临时" in summary
        assert "npc·持久" in summary

    def test_summary_no_characters(self):
        gen = CharacterGenerator()
        cm = None
        summary = gen.get_character_summaries(cm)
        assert summary == ""

    def test_summary_empty_manager(self):
        gen = CharacterGenerator()
        cm = CharacterManager()
        summary = gen.get_character_summaries(cm)
        assert "暂无角色" in summary


class TestCombatEndedCleanup:
    """COMBAT_ENDED 事件 → 临时角色清理测试。"""

    def test_cleanup_on_victory(self):
        from lingmo_engine.plugins.character.plugin import CharacterPlugin

        bus = EventBus()
        cm = CharacterManager()
        cm.add_character(Character(id=0, name="玩家", char_type=CharacterType.PLAYER))
        cm.add_character(Character(id=1, name="妖狼", char_type=CharacterType.MONSTER, temporary=True))
        cm.add_character(Character(id=2, name="商人", char_type=CharacterType.NPC, temporary=False))
        cm.set_event_bus(bus)

        plugin = CharacterPlugin()
        plugin._bus = bus
        plugin._get_character_manager = lambda: cm
        plugin._get_game_state = lambda: None
        bus.subscribe(PluginEvent.COMBAT_ENDED, plugin._on_combat_ended)

        bus.emit(PluginEvent.COMBAT_ENDED, {
            "phase": "victory",
            "participant_ids": [1, 2],
        })

        assert cm.get(1) is None  # 临时角色被清理
        assert cm.get(2) is not None  # NPC 保留

    def test_no_cleanup_on_defeat(self):
        from lingmo_engine.plugins.character.plugin import CharacterPlugin

        bus = EventBus()
        cm = CharacterManager()
        cm.add_character(Character(id=0, name="玩家", char_type=CharacterType.PLAYER))
        cm.add_character(Character(id=1, name="妖狼", char_type=CharacterType.MONSTER, temporary=True))
        cm.set_event_bus(bus)

        plugin = CharacterPlugin()
        plugin._bus = bus
        plugin._get_character_manager = lambda: cm
        plugin._get_game_state = lambda: None
        bus.subscribe(PluginEvent.COMBAT_ENDED, plugin._on_combat_ended)

        bus.emit(PluginEvent.COMBAT_ENDED, {
            "phase": "defeat",
            "participant_ids": [1],
        })

        assert cm.get(1) is not None  # 败北不清理

    def test_cleanup_on_flee(self):
        from lingmo_engine.plugins.character.plugin import CharacterPlugin

        bus = EventBus()
        cm = CharacterManager()
        cm.add_character(Character(id=0, name="玩家", char_type=CharacterType.PLAYER))
        cm.add_character(Character(id=1, name="邪修", char_type=CharacterType.MONSTER, temporary=True))
        cm.set_event_bus(bus)

        plugin = CharacterPlugin()
        plugin._bus = bus
        plugin._get_character_manager = lambda: cm
        plugin._get_game_state = lambda: None
        bus.subscribe(PluginEvent.COMBAT_ENDED, plugin._on_combat_ended)

        bus.emit(PluginEvent.COMBAT_ENDED, {
            "phase": "flee",
            "participant_ids": [1],
        })

        assert cm.get(1) is None  # 逃跑也清理


class TestTemporaryDefaultEdgeCases:
    """_apply_temporary_default 边界用例。"""

    def test_pet_defaults_not_temporary(self):
        gen = CharacterGenerator()
        data = {"char_type": "pet", "name": "灵猫", "attrs": {}}
        gen._apply_temporary_default(data)
        assert data["temporary"] is False

    def test_player_defaults_not_temporary(self):
        gen = CharacterGenerator()
        data = {"char_type": "player", "name": "主角", "attrs": {}}
        gen._apply_temporary_default(data)
        assert data["temporary"] is False

    def test_explicit_true_not_overridden(self):
        gen = CharacterGenerator()
        data = {"char_type": "npc", "name": "间谍", "temporary": True, "attrs": {}}
        gen._apply_temporary_default(data)
        assert data["temporary"] is True  # NPC 但显式设为临时


class TestProcessAbilitiesEdgeCases:
    """abilities 处理边界用例。"""

    def test_unsupported_type_skipped(self):
        gen = CharacterGenerator()
        skill_names = gen._process_abilities([123, None])
        assert skill_names == []

    def test_generate_ability_returns_none_skipped(self):
        gen = CharacterGenerator()
        gen._custom_abilities = {}
        with patch.object(gen, "_generate_ability", return_value=None):
            skill_names = gen._process_abilities([{"name": "失败技能"}])
        assert skill_names == []

    def test_string_reference_from_game_state(self):
        gen = CharacterGenerator()
        gen._custom_abilities = {}
        gs = MagicMock()
        gs.get_custom_ability.return_value = {"id": "a2", "name": "已有技能"}
        gen._game_state = gs

        skill_names = gen._process_abilities(["已有技能"])
        assert skill_names == ["已有技能"]
        gs.get_custom_ability.assert_called_once_with("已有技能")


class TestProcessAbilitiesFuzzyMatch:
    """模糊匹配测试：模拟 world.abilities 以 id 为 key、name 为显示名的场景。"""

    @staticmethod
    def _make_gen_with_world():
        gen = CharacterGenerator()
        gen._custom_abilities = {}
        gen._game_state = None
        gen._world = MagicMock()
        gen._world.abilities = {
            "ability_abc1": {"id": "ability_abc1", "name": "剑气纵横"},
            "ability_abc2": {"id": "ability_abc2", "name": "剑域·无锋"},
            "ability_abc3": {"id": "ability_abc3", "name": "大罗·终焉一剑"},
            "ability_abc4": {"id": "ability_abc4", "name": "法则剑·断因果"},
            "ability_abc5": {"id": "ability_abc5", "name": "万剑归宗"},
        }
        return gen

    def test_exact_name_match(self):
        """精确名称匹配应返回对应 ID。"""
        gen = self._make_gen_with_world()
        result = gen._process_abilities(["剑气纵横"])
        assert result == ["ability_abc1"]

    def test_exact_id_match(self):
        """精确 ID 匹配应直接返回。"""
        gen = self._make_gen_with_world()
        result = gen._process_abilities(["ability_abc1"])
        assert result == ["ability_abc1"]

    def test_fuzzy_remove_separator(self):
        """LLM 丢掉·分隔符时应模糊匹配成功。"""
        gen = self._make_gen_with_world()
        result = gen._process_abilities(["剑域无锋"])
        assert result == ["ability_abc2"]

    def test_fuzzy_partial_name(self):
        """LLM 省略前缀/后缀时应通过包含匹配命中。"""
        gen = self._make_gen_with_world()
        result = gen._process_abilities(["终焉一剑"])
        assert result == ["ability_abc3"]

    def test_fuzzy_no_match(self):
        """完全无关的名称不应误匹配。"""
        gen = self._make_gen_with_world()
        result = gen._process_abilities(["完全不存在的技能"])
        assert result == []

    def test_fuzzy_no_world(self):
        """无 world 时模糊匹配应跳过。"""
        gen = CharacterGenerator()
        gen._custom_abilities = {}
        gen._game_state = None
        gen._world = None
        result = gen._process_abilities(["剑气纵横"])
        assert result == []

    def test_mixed_exact_and_fuzzy(self):
        """精确匹配和模糊匹配混合使用。"""
        gen = self._make_gen_with_world()
        result = gen._process_abilities(["万剑归宗", "法则剑断因果"])
        assert result == ["ability_abc5", "ability_abc4"]
