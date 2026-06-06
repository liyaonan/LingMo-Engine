"""事件系统单元测试（重构后）。"""
import pytest

from lingmo_engine.plugins.event.types import EventRecord
from lingmo_engine.plugins.event.event_manager import EventManager


class TestEventRecord:
    def test_defaults(self):
        r = EventRecord(event_id="evt_001", title="测试事件")
        assert r.event_id == "evt_001"
        assert r.title == "测试事件"
        assert r.status == "active"
        assert r.plan_md == ""
        assert r.created_at == ""
        assert r.updated_at == ""

    def test_to_dict(self):
        r = EventRecord(
            event_id="evt_001", title="测试",
            status="active", plan_md="# 标题\n## 当前进展\n玩家到达了村庄。",
            created_at="day1_month1_year1", updated_at="day2_month1_year1",
        )
        d = r.to_dict()
        assert d["event_id"] == "evt_001"
        assert d["title"] == "测试"
        assert d["status"] == "active"
        assert "当前进展" in d["plan_md"]

    def test_from_dict(self):
        data = {
            "event_id": "evt_002", "title": "外交事件",
            "status": "completed", "plan_md": "# 外交事件\n## 当前进展\n已完成。",
            "created_at": "day5_month2_year1",
            "updated_at": "day10_month2_year1",
        }
        r = EventRecord.from_dict(data)
        assert r.event_id == "evt_002"
        assert r.title == "外交事件"
        assert r.status == "completed"

    def test_roundtrip(self):
        r = EventRecord(
            event_id="evt_003", title="边境冲突",
            status="active",
            plan_md=(
                "# 边境冲突\n## 背景概述\n...\n## 各方动机\n..."
                "\n## 发展大纲\n...\n## 当前进展\n哨站发现异常。"
            ),
            created_at="day1_month1_year1", updated_at="day3_month1_year1",
        )
        restored = EventRecord.from_dict(r.to_dict())
        assert restored.event_id == r.event_id
        assert restored.title == r.title
        assert restored.status == r.status
        assert restored.plan_md == r.plan_md


class TestEventManagerCreate:
    def test_create_event(self):
        mgr = EventManager()
        result = mgr.execute_tool("create_event", {
            "title": "兽人入侵",
            "plan_md": "# 兽人入侵\n## 当前进展\n先遣队出现。",
        }, game_time="day1_month3_year1")
        assert result.success is True
        assert "兽人入侵" in result.log
        event_id = result.data["event_id"]
        assert event_id.startswith("evt_")
        assert mgr.get_event_count() == 1

    def test_create_event_missing_params(self):
        mgr = EventManager()
        result = mgr.execute_tool("create_event", {"title": "无计划"}, game_time="")
        assert result.success is False
        assert mgr.get_event_count() == 0

    def test_create_event_empty_params(self):
        mgr = EventManager()
        result = mgr.execute_tool("create_event", {}, game_time="")
        assert result.success is False


class TestEventManagerUpdate:
    def test_update_plan_md(self):
        mgr = EventManager()
        mgr._create(
            {"title": "测试", "plan_md": "# 旧计划"}, "day1",
        )
        event_id = list(mgr._events.keys())[0]
        result = mgr.execute_tool("update_event", {
            "event_id": event_id,
            "plan_md": "# 新计划\n## 当前进展\n已更新。",
        }, "day5")
        assert result.success is True
        assert mgr._events[event_id].plan_md == (
            "# 新计划\n## 当前进展\n已更新。"
        )

    def test_update_status(self):
        mgr = EventManager()
        mgr._create(
            {"title": "测试", "plan_md": "# T"}, "day1",
        )
        event_id = list(mgr._events.keys())[0]
        result = mgr.execute_tool("update_event", {
            "event_id": event_id, "status": "completed",
        }, "day5")
        assert result.success is True
        assert mgr._events[event_id].status == "completed"

    def test_update_nonexistent(self):
        mgr = EventManager()
        result = mgr.execute_tool("update_event", {
            "event_id": "evt_nonexistent", "status": "completed",
        }, "")
        assert result.success is False


class TestEventManagerAppend:
    def test_append_progress(self):
        mgr = EventManager()
        mgr._create({
            "title": "测试",
            "plan_md": (
                "# 测试\n## 背景概述\n...\n## 各方动机\n..."
                "\n## 发展大纲\n...\n## 当前进展\n玩家到达。"
            ),
        }, "day1")
        event_id = list(mgr._events.keys())[0]
        result = mgr.execute_tool("append_event_progress", {
            "event_id": event_id,
            "progress": "玩家进入神殿。",
        }, "day2")
        assert result.success is True
        assert "玩家进入神殿" in mgr._events[event_id].plan_md

    def test_append_nonexistent_event(self):
        mgr = EventManager()
        result = mgr.execute_tool("append_event_progress", {
            "event_id": "evt_nonexistent", "progress": "进展",
        }, "")
        assert result.success is False

    def test_append_empty_progress(self):
        mgr = EventManager()
        mgr._create(
            {"title": "测试", "plan_md": "# T\n## 当前进展\n..."}, "day1",
        )
        event_id = list(mgr._events.keys())[0]
        result = mgr.execute_tool("append_event_progress", {
            "event_id": event_id, "progress": "",
        }, "")
        assert result.success is False


class TestEventManagerSummaries:
    def test_summaries_active_only(self):
        mgr = EventManager()
        mgr._create({
            "title": "活跃事件",
            "plan_md": "# 活跃事件\n## 当前进展\n正在发生中。",
        }, "day1")
        mgr._create({
            "title": "已完成事件",
            "plan_md": "# 已完成事件\n## 当前进展\n已经结束。",
        }, "day1")
        event_ids = list(mgr._events.keys())
        mgr._update(
            {"event_id": event_ids[1], "status": "completed"}, "day2",
        )

        summary = mgr.get_summaries()
        assert "活跃事件" in summary
        assert "已完成事件" not in summary

    def test_summaries_empty(self):
        mgr = EventManager()
        summary = mgr.get_summaries()
        assert "暂无活跃事件" in summary
        assert "create_event" in summary

    def test_extract_progress_truncation(self):
        mgr = EventManager()
        long_text = "很长的文本" * 100
        mgr._create({
            "title": "长事件",
            "plan_md": f"# 长事件\n## 当前进展\n{long_text}",
        }, "day1")
        summary = mgr.get_summaries()
        assert len(summary) < 500

    def test_extract_progress_no_heading(self):
        mgr = EventManager()
        mgr._create({
            "title": "无进展标题",
            "plan_md": "# 无进展标题\n没有进展段落。",
        }, "day1")
        summary = mgr.get_summaries()
        assert "暂无进展" in summary


class TestEventManagerState:
    def test_load_from_files_empty(self):
        """无事件文件时 load_from_files 不报错。"""
        mgr = EventManager()
        mgr.load_from_files()
        assert mgr.get_event_count() == 0

    def test_file_persist_create(self, tmp_path):
        """创建事件后应写入独立 JSON 文件。"""
        mgr = EventManager()
        mgr.set_slot_dir(tmp_path)
        mgr._create({"title": "E1", "plan_md": "# E1"}, "day1")
        event_id = list(mgr._events.keys())[0]
        assert (tmp_path / "event" / f"{event_id}.json").exists()

    def test_file_persist_update(self, tmp_path):
        """更新事件后文件应同步更新。"""
        mgr = EventManager()
        mgr.set_slot_dir(tmp_path)
        mgr._create({"title": "E1", "plan_md": "# E1"}, "day1")
        event_id = list(mgr._events.keys())[0]
        mgr._update({"event_id": event_id, "status": "completed"}, "day2")
        import json
        data = json.loads((tmp_path / "event" / f"{event_id}.json").read_text("utf-8"))
        assert data["status"] == "completed"

    def test_load_state_from_files(self, tmp_path):
        """从 event/ 目录加载事件文件。"""
        mgr = EventManager()
        mgr.set_slot_dir(tmp_path)
        mgr._create({
            "title": "E1",
            "plan_md": "# E1\n## 当前进展\n进展A。",
        }, "day1")

        mgr2 = EventManager()
        mgr2.set_slot_dir(tmp_path)
        mgr2.load_from_files()
        assert mgr2.get_event_count() == 1
        summaries = mgr2.get_summaries()
        assert "E1" in summaries
        assert "进展A" in summaries

    def test_migrate_from_old_format(self, tmp_path):
        """从旧 state.json 字典格式迁移到独立文件。"""
        mgr = EventManager()
        mgr.set_slot_dir(tmp_path)
        old_state = {
            "event_records": [
                {
                    "event_id": "evt_001",
                    "title": "迁移事件",
                    "status": "active",
                    "plan_md": "# 迁移事件\n## 当前进展\n迁移测试。",
                    "created_at": "day1",
                    "updated_at": "day1",
                },
            ],
        }
        mgr.migrate_from_state(old_state)

        # 迁移后文件应存在
        assert (tmp_path / "event" / "evt_001.json").exists()
        assert (tmp_path / "event" / ".migrated").exists()
        mgr.load_from_files()
        assert mgr.get_event_count() == 1
        assert "迁移事件" in mgr.get_summaries()

    def test_migrate_not_repeated(self, tmp_path):
        """迁移标记存在时不应重复迁移。"""
        mgr = EventManager()
        mgr.set_slot_dir(tmp_path)
        old_state = {
            "event_records": [
                {
                    "event_id": "evt_001",
                    "title": "迁移事件",
                    "status": "active",
                    "plan_md": "# 迁移事件",
                    "created_at": "day1",
                    "updated_at": "day1",
                },
            ],
        }
        # 第一次迁移
        mgr.migrate_from_state(old_state)
        mgr.load_from_files()
        assert mgr.get_event_count() == 1

        # 修改 state 中的数据，第二次加载应跳过迁移
        old_state["event_records"][0]["title"] = "被篡改的标题"
        mgr2 = EventManager()
        mgr2.set_slot_dir(tmp_path)
        mgr2.migrate_from_state(old_state)
        mgr2.load_from_files()
        # 应加载的是原始迁移文件，而非被篡改的数据
        assert "迁移事件" in mgr2.get_summaries()
        assert "被篡改的标题" not in mgr2.get_summaries()


class TestEventManagerListEvents:
    def test_list_returns_frontend_data(self):
        mgr = EventManager()
        mgr._create({"title": "E1", "plan_md": "# E1"}, "day1")
        events = mgr.list_events()
        assert len(events) == 1
        assert events[0]["title"] == "E1"
        assert "player_view" in events[0]
        assert events[0]["status"] == "active"

    def test_player_view_filters_gm_sections(self):
        mgr = EventManager()
        view = mgr._extract_player_view("""# 测试事件

## 背景概述
事件起源于远古封印松动。

## 各方动机
- 反派：夺取力量
- 王国：维持平衡

## 发展大纲
1. 发现异常
2. 调查真相

## 当前进展
玩家抵达封印之地，发现守卫已被石化。""")
        assert "背景概述" in view
        assert "远古封印" in view
        assert "当前进展" in view
        assert "石化" in view
        assert "各方动机" not in view
        assert "夺取力量" not in view  # 隐藏段落的内容不应出现
        assert "发展大纲" not in view
        assert "调查真相" not in view

    def test_player_view_uses_configurable_hidden_set(self):
        mgr = EventManager()
        mgr._player_hidden_headings = {"动机分析"}
        view = mgr._extract_player_view("""# 测试

## 背景概述
事件背景。

## 动机分析
- 反派计划。
""")
        assert "背景概述" in view
        assert "动机分析" not in view


class TestEventManagerSystemPrompt:
    def test_examples_labeled_as_not_active(self):
        mgr = EventManager()
        mgr._template_md = (
            "# {title}\n## 背景概述\n## 当前进展\n"
        )
        mgr._examples = [
            "# 示例事件\n## 背景概述\n...\n## 当前进展\n玩家到达。",
        ]
        fragment = mgr.build_system_prompt_fragment()
        assert "并非当前活跃事件" in fragment
        assert "create_event" in fragment

    def test_generation_included(self):
        mgr = EventManager()
        mgr._generation_md = "使用中文编写"
        fragment = mgr.build_system_prompt_fragment()
        assert "使用中文编写" in fragment
