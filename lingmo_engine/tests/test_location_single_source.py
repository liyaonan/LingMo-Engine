"""位置单一数据源测试"""
import json
from pathlib import Path
from unittest.mock import MagicMock

from lingmo_engine.core.game_state import GameState
from lingmo_engine.core.character_manager import CharacterManager
from lingmo_engine.core.character import Character, CharacterType


def test_default_state_no_location_fields():
    """_default_state 不再包含 location 和 current_node_id"""
    gs = GameState(Path("/tmp/test_no_loc"))
    data = gs._default_state()
    assert "location" not in data
    assert "current_node_id" not in data
    # 确认其他字段仍在
    assert "flags" in data
    assert "scene_enemies" in data
    assert "game_time" in data
    assert "plugins" in data
    assert "player_id" in data


def test_save_no_location_in_state_json(tmp_path):
    """save() 后 state.json 不应包含 location 或 current_node_id"""
    gs = GameState(tmp_path)
    cm = CharacterManager()
    player = Character(id=0, name="测试", char_type=CharacterType.PLAYER, location="仙界/天枢域/天枢仙城")
    cm._characters[0] = player
    gs.character_manager = cm

    gs.save()

    state_file = tmp_path / "state.json"
    assert state_file.exists()
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert "location" not in data
    assert "current_node_id" not in data


from lingmo_engine.plugins.map.plugin import MapPlugin
from lingmo_engine.core.map import MapNode, DefaultMap


def _make_map_plugin_with_map():
    """创建一个有地图实例的 MapPlugin 用于测试"""
    plugin = MapPlugin()
    nodes = [
        MapNode(id="root", name="仙界"),
        MapNode(id="domain1", name="天枢域", parent_id="root"),
        MapNode(id="city1", name="天枢仙城", parent_id="domain1"),
    ]
    plugin._map = DefaultMap(nodes=nodes, start_node_id="root")
    plugin._map.sync_parent_child()
    plugin._state = {}
    plugin._map_config = {"hierarchy": ["界", "域", "州", "城"]}
    return plugin


def test_execute_set_location_returns_full_path():
    """_execute_set_location 返回完整斜杠路径到 player_updates"""
    plugin = _make_map_plugin_with_map()

    result = plugin._execute_set_location({"path": "仙界/天枢域/天枢仙城"})

    assert result.success
    assert result.data["state_updates"]["current_node_id"] == "city1"
    assert result.data["player_updates"]["location"] == "仙界/天枢域/天枢仙城"


def test_execute_set_location_rejects_empty_path():
    """空路径被拒绝"""
    plugin = _make_map_plugin_with_map()
    result = plugin._execute_set_location({"path": ""})
    assert not result.success
    assert "空" in result.log


def test_execute_set_location_rejects_blank_segments():
    """含空白段的路径被拒绝"""
    plugin = _make_map_plugin_with_map()
    result = plugin._execute_set_location({"path": "仙界//天枢域"})
    assert not result.success
    assert "空白" in result.log


def test_execute_set_location_rejects_insufficient_depth():
    """路径深度不足时被拒绝（仅对有新增节点时生效）"""
    plugin = _make_map_plugin_with_map()
    # 仙界已存在，仅传入根节点层级1 — 没有新增部分，深度校验不触发
    result = plugin._execute_set_location({"path": "仙界"})
    assert result.success  # 已存在节点，深度校验不触发


def test_execute_set_location_new_node_insufficient_depth():
    """新增节点但路径深度不足时被拒绝"""
    plugin = _make_map_plugin_with_map()
    # "仙界" 是根节点，"新区域" 不存在需要创建，但 hierarchy 要求 4 层而只传了 2 层
    result = plugin._execute_set_location({"path": "仙界/新区域"})
    assert not result.success
    assert "深度不足" in result.log


def test_apply_result_player_updates_location(tmp_path):
    """ToolExecutor.apply_result 将 player_updates.location 写入 Character.location"""
    from lingmo_engine.core.gamemaster.tool_executor import ToolExecutor
    from lingmo_engine.core.types import ModuleResult

    # 构建 mock GameMaster
    gs = GameState(tmp_path)
    cm = CharacterManager()
    player = Character(id=0, name="测试", char_type=CharacterType.PLAYER, location="旧位置")
    cm._characters[0] = player
    gs.character_manager = cm

    gm = MagicMock()
    gm.state = gs

    executor = ToolExecutor(gm)

    result = ModuleResult(
        success=True,
        data={
            "player_updates": {
                "location": "仙界/天枢域/天枢仙城",
            },
        },
    )
    executor.apply_result(result)

    assert player.location == "仙界/天枢域/天枢仙城"


def test_map_node_is_facility():
    """MapNode.is_facility 识别 facility: 前缀"""
    fac_node = MapNode(id="f1", name="拍卖行", type="facility:拍卖行")
    area_node = MapNode(id="a1", name="灵墟城", type="城")
    empty_node = MapNode(id="e1", name="未知地", type="")

    assert fac_node.is_facility is True
    assert area_node.is_facility is False
    assert empty_node.is_facility is False


def test_default_map_get_facility_children():
    """DefaultMap.get_facility_children 返回设施子节点"""
    nodes = [
        MapNode(id="city", name="灵墟城"),
        MapNode(id="fac1", name="拍卖行", type="facility:拍卖行", parent_id="city"),
        MapNode(id="fac2", name="炼丹阁", type="facility:工坊", parent_id="city"),
        MapNode(id="area1", name="东城区", type="区", parent_id="city"),
    ]
    m = DefaultMap(nodes=nodes, start_node_id="city")
    m.sync_parent_child()

    facilities = m.get_facility_children("city")
    assert len(facilities) == 2
    names = {f.name for f in facilities}
    assert names == {"拍卖行", "炼丹阁"}


def test_default_map_get_area_children():
    """DefaultMap.get_area_children 返回区域子节点（非设施）"""
    nodes = [
        MapNode(id="city", name="灵墟城"),
        MapNode(id="fac1", name="拍卖行", type="facility:拍卖行", parent_id="city"),
        MapNode(id="area1", name="东城区", type="区", parent_id="city"),
    ]
    m = DefaultMap(nodes=nodes, start_node_id="city")
    m.sync_parent_child()

    areas = m.get_area_children("city")
    assert len(areas) == 1
    assert areas[0].name == "东城区"


def test_get_leaf_nodes_exclude_facilities():
    """get_leaf_nodes(include_facilities=False) 排除设施节点"""
    nodes = [
        MapNode(id="city", name="灵墟城", center=(100, 100), radius=30),
        MapNode(id="fac1", name="拍卖行", type="facility:拍卖行", parent_id="city"),
        MapNode(id="area1", name="东城区", parent_id="city", center=(120, 120), radius=10),
    ]
    m = DefaultMap(nodes=nodes, start_node_id="city")
    m.sync_parent_child()

    all_leaves = m.get_leaf_nodes()
    assert len(all_leaves) == 2

    non_fac_leaves = m.get_leaf_nodes(include_facilities=False)
    assert len(non_fac_leaves) == 1
    assert non_fac_leaves[0].name == "东城区"


def test_generate_slug_id_with_prefix():
    """_generate_slug_id 支持 prefix 参数"""
    m = DefaultMap(nodes=[], start_node_id="")
    slug = m._generate_slug_id("拍卖行", prefix="facility_")
    assert slug.startswith("facility_")
    assert len(slug) > len("facility_")


def test_inflate_facilities_to_nodes():
    """加载时设施膨胀为子节点"""
    plugin = MapPlugin()
    nodes = [
        MapNode(id="city", name="灵墟城", facilities=[
            {"name": "拍卖行", "type": "拍卖行", "description": "交易灵物"},
            {"name": "炼丹阁", "type": "工坊", "description": "丹药炼制"},
        ]),
    ]
    plugin._map = DefaultMap(nodes=nodes, start_node_id="city")
    plugin._map.sync_parent_child()
    plugin._state = {}
    plugin._map_config = {}

    # 执行膨胀
    plugin._inflate_facilities_to_nodes()

    # 父节点的 facilities 应被清空
    city = plugin._map._nodes["city"]
    assert city.facilities == []

    # 应有 2 个设施子节点
    fac_children = plugin._map.get_facility_children("city")
    assert len(fac_children) == 2
    names = {f.name for f in fac_children}
    assert names == {"拍卖行", "炼丹阁"}

    # 设施节点 is_facility 为 True
    for f in fac_children:
        assert f.is_facility is True
        assert f.type.startswith("facility:")

    # 设施节点无坐标
    for f in fac_children:
        assert f.center is None
        assert f.radius == 0.0

    # 区域子节点不受影响
    area_children = plugin._map.get_area_children("city")
    assert len(area_children) == 0  # 只有设施，没有区域子节点


def test_inflate_facilities_string_format():
    """兼容 ashenvail_world 的字符串格式设施"""
    plugin = MapPlugin()
    nodes = [
        MapNode(id="village", name="村庄", facilities=["inn", "shop"]),
    ]
    plugin._map = DefaultMap(nodes=nodes, start_node_id="village")
    plugin._map.sync_parent_child()
    plugin._state = {}
    plugin._map_config = {}

    plugin._inflate_facilities_to_nodes()

    fac_children = plugin._map.get_facility_children("village")
    assert len(fac_children) == 2
    names = {f.name for f in fac_children}
    assert names == {"inn", "shop"}


def test_inflate_facilities_no_duplicate():
    """膨胀时如果已有同名子节点，不创建重复"""
    plugin = MapPlugin()
    nodes = [
        MapNode(id="city", name="灵墟城", facilities=[
            {"name": "拍卖行", "type": "拍卖行", "description": "交易灵物"},
        ]),
        # 已有一个同名的区域子节点
        MapNode(id="pai_mai_hang", name="拍卖行", parent_id="city"),
    ]
    plugin._map = DefaultMap(nodes=nodes, start_node_id="city")
    plugin._map.sync_parent_child()
    plugin._state = {}
    plugin._map_config = {}

    plugin._inflate_facilities_to_nodes()

    # 不应有重复的拍卖行节点
    all_children = plugin._map.get_children("city")
    pmh_nodes = [c for c in all_children if c.name == "拍卖行"]
    assert len(pmh_nodes) == 1


def test_set_location_creates_facility_node():
    """set_location + type 创建设施子节点"""
    plugin = MapPlugin()
    nodes = [
        MapNode(id="city", name="灵墟城"),
    ]
    plugin._map = DefaultMap(nodes=nodes, start_node_id="city")
    plugin._map.sync_parent_child()
    plugin._state = {}
    plugin._map_dir = None  # 不测试持久化
    plugin._map_config = {}

    result = plugin.execute_tool("set_location", {
        "path": "灵墟城/拍卖行",
        "type": "facility:拍卖行",
        "description": "交易灵物",
    })

    assert result.success
    fac_children = plugin._map.get_facility_children("city")
    assert len(fac_children) == 1
    fac = fac_children[0]
    assert fac.name == "拍卖行"
    assert fac.type == "facility:拍卖行"
    assert fac.description == "交易灵物"
    assert fac.is_facility is True
