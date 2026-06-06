"""角色创建系统测试（单页表单模式）。"""
from pathlib import Path
import tempfile
import yaml

from lingmo_engine.core.character import Character, CharacterType
from lingmo_engine.character_creation.schema import (
    CreationConfig, CharacterTemplate, TemplateApply,
    FormField, FormFieldOption, load_creation_config,
)


class TestTemplateApply:
    def test_defaults(self):
        a = TemplateApply()
        assert a.attrs == {}
        assert a.abilities == []
        assert a.location == ""
        assert a.background == ""
        assert a.opening_text == ""
        assert a.personality == ""

    def test_with_data(self):
        a = TemplateApply(
            level=5,
            attrs={"force": 35, "tenacity": 20},
            abilities=["slash", "war_cry"],
            inventory=[{"item_id": "iron_sword", "quantity": 1}],
            equipment={"weapon": "iron_sword"},
            faction="冒险者",
            location="village",
            personality="勇敢的战士",
            tags=["战士", "勇敢"],
            background="{player_name}的传奇故事",
            opening_text="你来到了{location}...",
        )
        assert a.level == 5
        assert a.attrs["force"] == 35
        assert len(a.abilities) == 2
        assert a.background == "{player_name}的传奇故事"
        assert a.opening_text == "你来到了{location}..."
        assert a.tags == ["战士", "勇敢"]


class TestLoadCreationConfig:
    def test_new_format(self):
        yaml_data = {
            "title": "创建角色",
            "templates": [
                {
                    "id": "warrior",
                    "name": "战士",
                    "description": "近战专家",
                    "apply": {
                        "level": 1,
                        "attrs": {"force": 30, "tenacity": 15},
                        "abilities": ["slash"],
                        "location": "village",
                        "personality": "勇敢的战士",
                        "tags": ["战士", "勇敢"],
                        "background": "{player_name}的背景故事",
                        "opening_text": "{player_name}来到了{location}",
                    },
                },
            ],
            "fields": [
                {
                    "key": "name",
                    "label": "角色姓名",
                    "type": "text",
                    "required": True,
                    "placeholder": "输入姓名",
                },
                {
                    "key": "gender",
                    "label": "性别",
                    "type": "select",
                    "required": False,
                    "options": [
                        {"value": "male", "label": "男"},
                        {"value": "female", "label": "女"},
                    ],
                },
                {
                    "key": "background",
                    "label": "背景故事",
                    "type": "textarea",
                    "required": False,
                    "rows": 8,
                },
            ],
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            yaml.dump(yaml_data, f, allow_unicode=True)
            tmp_path = f.name

        try:
            config = load_creation_config(Path(tmp_path))
            assert config is not None
            assert config.title == "创建角色"
            assert len(config.templates) == 1
            assert len(config.fields) == 3

            t = config.templates[0]
            assert t.id == "warrior"
            assert t.name == "战士"
            assert t.apply.attrs["force"] == 30
            assert t.apply.location == "village"
            assert t.apply.background == "{player_name}的背景故事"
            assert t.apply.opening_text == "{player_name}来到了{location}"
            assert t.apply.tags == ["战士", "勇敢"]

            f1 = config.fields[0]
            assert f1.key == "name"
            assert f1.required is True

            f2 = config.fields[1]
            assert f2.key == "gender"
            assert f2.type == "select"
            assert len(f2.options) == 2
            assert f2.options[0].value == "male"

            f3 = config.fields[2]
            assert f3.key == "background"
            assert f3.type == "textarea"
            assert f3.rows == 8
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_missing_file_returns_none(self):
        config = load_creation_config(Path("/nonexistent/path.yaml"))
        assert config is None

    def test_empty_templates(self):
        yaml_data = {"title": "测试", "templates": [], "fields": []}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            yaml.dump(yaml_data, f, allow_unicode=True)
            tmp_path = f.name

        try:
            config = load_creation_config(Path(tmp_path))
            assert config is not None
            assert config.templates == []
            assert config.fields == []
        finally:
            Path(tmp_path).unlink(missing_ok=True)


# ── Engine 测试辅助 ──

def _make_engine(config=None):
    """创建最小化的 CreationEngine 供测试使用。"""
    from lingmo_engine.core.character_manager import CharacterManager
    from lingmo_engine.core.game_state import GameState

    cm = CharacterManager()
    cm.add_character(Character(id=0, name="占位", char_type=CharacterType.PLAYER))

    save_dir = Path(tempfile.mkdtemp())
    state = GameState(save_dir)
    state.character_manager = cm

    class DummyWorld:
        setting = {"world": {"name": "测试世界"}}

    from lingmo_engine.character_creation.engine import CreationEngine
    return CreationEngine(
        config=config,
        world=DummyWorld(),
        character_manager=cm,
        game_state=state,
    )


def _make_test_config():
    """创建一个最小测试配置（1个模板 + 2个字段）。"""
    return CreationConfig(
        title="测试",
        templates=[
            CharacterTemplate(
                id="warrior",
                name="战士",
                description="近战专家",
                apply=TemplateApply(
                    level=5,
                    attrs={"force": 30, "tenacity": 15},
                    abilities=["slash"],
                    inventory=[{"item_id": "sword", "quantity": 1}],
                    location="village",
                    faction="冒险者",
                    personality="勇敢的战士",
                    tags=["战士", "勇敢"],
                    background="{player_name}曾是骑士侍从，在{location}磨练剑术。",
                    opening_text="{player_name}来到了{location}，冒险即将开始...",
                ),
            ),
        ],
        fields=[
            FormField(key="name", label="角色姓名", type="text", required=True),
            FormField(key="gender", label="性别", type="select", required=False,
                      options=[FormFieldOption(value="male", label="男")]),
            FormField(key="background", label="背景故事", type="textarea", required=False, rows=8),
        ],
    )


# ── Engine 测试 ──

class TestCreationEngineInterpolate:
    def test_substitutes_known_variables(self):
        engine = _make_engine(_make_test_config())
        char = Character(id=0, name="测试角色", char_type=CharacterType.PLAYER,
                         attrs={"force": 30, "tenacity": 10}, abilities=["slash", "fireball"])
        vars_dict = engine._build_vars_dict(char, {"player_name": "测试角色"})
        result = engine.interpolate(
            "你是{player_name}，ATK={force}，技能={all_skills}。世界={world_name}",
            vars_dict,
        )
        assert "测试角色" in result
        assert "ATK=30" in result
        assert "slash, fireball" in result
        assert "测试世界" in result

    def test_missing_variable_returns_empty(self):
        engine = _make_engine(_make_test_config())
        result = engine.interpolate("你好{unknown_var}世界", {"player_name": "测试"})
        assert "你好世界" in result


class TestCreationEngineCreateCharacter:
    def test_basic_creation(self):
        engine = _make_engine(_make_test_config())
        char = engine.create_character("warrior", {"name": "亚瑟"})
        assert char is not None
        assert char.name == "亚瑟"
        assert char.id == 0
        assert char.char_type == CharacterType.PLAYER

    def test_applies_template_data(self):
        engine = _make_engine(_make_test_config())
        char = engine.create_character("warrior", {"name": "亚瑟"})
        assert char.level == 5
        assert char.attrs["force"] == 30
        assert char.attrs["tenacity"] == 15
        assert "slash" in char.abilities
        assert char.location == "village"
        assert char.faction == "冒险者"
        assert "战士" in char.tags
        assert "勇敢" in char.tags

    def test_fields_override_template(self):
        engine = _make_engine(_make_test_config())
        char = engine.create_character("warrior", {
            "name": "亚瑟",
            "background": "自定义背景故事",
        })
        assert char.background == "自定义背景故事"

    def test_extra_fields_stored(self):
        engine = _make_engine(_make_test_config())
        char = engine.create_character("warrior", {
            "name": "亚瑟",
            "gender": "male",
        })
        assert char.gender == "male"

    def test_interpolates_background(self):
        engine = _make_engine(_make_test_config())
        char = engine.create_character("warrior", {"name": "亚瑟"})
        assert "亚瑟" in char.background
        assert "village" in char.background  # location 被插值
        assert "{player_name}" not in char.background

    def test_interpolates_opening_text(self):
        engine = _make_engine(_make_test_config())
        engine.create_character("warrior", {"name": "亚瑟"})
        opening = engine.get_opening_text()
        assert "亚瑟" in opening
        assert "village" in opening
        assert "{player_name}" not in opening

    def test_required_field_validation(self):
        engine = _make_engine(_make_test_config())
        try:
            engine.create_character("warrior", {"name": ""})
            assert False, "应抛出 ValueError"
        except ValueError as e:
            assert "角色姓名" in str(e)

    def test_invalid_template_raises(self):
        engine = _make_engine(_make_test_config())
        try:
            engine.create_character("nonexistent", {"name": "测试"})
            assert False, "应抛出 ValueError"
        except ValueError as e:
            assert "无效的模板 ID" in str(e)

    def test_creates_player_character(self):
        engine = _make_engine(_make_test_config())
        char = engine.create_character("warrior", {"name": "亚瑟"})
        assert char.id == 0
        assert char.char_type == CharacterType.PLAYER
        # 确认写入了 CharacterManager
        assert engine.character_manager.player.name == "亚瑟"


class TestCharacterExtraField:
    def test_extra_in_to_dict(self):
        char = Character(id=0, name="测试", char_type=CharacterType.PLAYER,
                         extra={"gender": "male", "age": "25"})
        d = char.to_dict()
        assert d["extra"] == {"gender": "male", "age": "25"}

    def test_extra_from_dict(self):
        data = {"id": 0, "name": "测试", "char_type": "player",
                "extra": {"gender": "female"}}
        char = Character.from_dict(data)
        assert char.extra["gender"] == "female"

    def test_extra_roundtrip(self):
        char = Character(id=0, name="测试", char_type=CharacterType.PLAYER,
                         extra={"gender": "male", "age": "25"})
        restored = Character.from_dict(char.to_dict())
        assert restored.extra == {"gender": "male", "age": "25"}

    def test_extra_default_empty(self):
        char = Character(id=0, name="测试", char_type=CharacterType.PLAYER)
        assert char.extra == {}


class TestFullCreationFlow:
    def test_get_config_data_then_create_character(self):
        config = _make_test_config()
        engine = _make_engine(config)

        # Step 1: 获取配置数据
        data = engine.get_config_data()
        assert data["title"] == "测试"
        assert len(data["templates"]) == 1
        assert data["templates"][0]["id"] == "warrior"
        assert data["templates"][0]["apply"]["level"] == 5
        assert len(data["fields"]) == 3

        # Step 2: 创建角色
        char = engine.create_character("warrior", {
            "name": "亚瑟",
            "gender": "male",
            "background": "自定义背景",
        })
        assert char.name == "亚瑟"
        assert char.level == 5
        assert char.gender == "male"
        assert char.background == "自定义背景"  # 用户编辑覆盖了模板插值

    def test_template_without_edit_gets_interpolated(self):
        """玩家未编辑背景时，背景应被自动插值。"""
        config = _make_test_config()
        engine = _make_engine(config)

        # 只提供 name，不覆盖 background
        char = engine.create_character("warrior", {"name": "亚瑟"})
        assert "{player_name}" not in char.background
        assert "亚瑟" in char.background
        assert "village" in char.background


class TestRouteConfig:
    def test_routes_loaded_from_yaml(self):
        yaml_data = {
            "title": "测试",
            "templates": [],
            "fields": [],
            "routes": [
                {
                    "id": "test_route",
                    "title": "测试路线",
                    "subtitle": "副标题",
                    "chapter": "第一章",
                    "description": "路线描述",
                    "locked": False,
                    "template_id": "test_tmpl",
                    "narrative_badge": "徽章",
                    "narrative_text": ["第一行", "第二行"],
                    "narrative_highlights": ["关键词"],
                    "narrative_meta": "元数据",
                },
            ],
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            yaml.dump(yaml_data, f, allow_unicode=True)
            tmp_path = f.name
        try:
            config = load_creation_config(Path(tmp_path))
            assert len(config.routes) == 1
            r = config.routes[0]
            assert r.id == "test_route"
            assert r.title == "测试路线"
            assert r.locked is False
            assert r.template_id == "test_tmpl"
            assert r.narrative_text == ["第一行", "第二行"]
            assert r.narrative_highlights == ["关键词"]
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_routes_default_empty(self):
        yaml_data = {"title": "测试", "templates": [], "fields": []}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            yaml.dump(yaml_data, f, allow_unicode=True)
            tmp_path = f.name
        try:
            config = load_creation_config(Path(tmp_path))
            assert config.routes == []
        finally:
            Path(tmp_path).unlink(missing_ok=True)


class TestCultivationFields:
    def test_cultivation_fields_mapped_to_character(self):
        config = CreationConfig(
            title="仙界",
            templates=[
                CharacterTemplate(
                    id="xianjie_daluo",
                    name="大罗金仙",
                    apply=TemplateApply(
                        level=13,
                        attrs={"force": 95},
                        location="immortal_realm",
                        background="背景",
                        opening_text="开场白",
                        # 修炼字段通过 world_fields 传递，写入 char.extra
                        world_fields={
                            "cultivation_stage": "daluo_golden_immortal",
                            "cultivation_path": "none",
                            "spiritual_roots": [],
                        },
                    ),
                ),
            ],
            fields=[FormField(key="name", label="真名", type="text", required=True)],
        )
        engine = _make_engine(config)
        char = engine.create_character("xianjie_daluo", {"name": "测试仙"})

        assert char.extra.get("cultivation_stage") == "daluo_golden_immortal"
        assert char.extra.get("cultivation_path") == "none"
        assert char.level == 13
        assert char.name == "测试仙"

    def test_get_routes_data(self):
        from lingmo_engine.character_creation.schema import RouteConfig
        config = CreationConfig(
            title="测试",
            templates=[],
            fields=[],
            routes=[
                RouteConfig(
                    id="xianjie",
                    title="仙界篇",
                    subtitle="大罗金仙",
                    locked=False,
                    template_id="xianjie_daluo",
                    narrative_text=["行1", "行2"],
                ),
            ],
        )
        engine = _make_engine(config)
        routes = engine.get_routes_data()
        assert len(routes) == 1
        assert routes[0]["id"] == "xianjie"
        assert routes[0]["locked"] is False
        assert routes[0]["narrative_text"] == ["行1", "行2"]

    def test_config_data_includes_routes(self):
        from lingmo_engine.character_creation.schema import RouteConfig
        config = CreationConfig(
            title="测试",
            templates=[],
            fields=[],
            routes=[RouteConfig(id="r1", title="路线1")],
        )
        engine = _make_engine(config)
        data = engine.get_config_data()
        assert "routes" in data
        assert len(data["routes"]) == 1
        assert data["routes"][0]["title"] == "路线1"
