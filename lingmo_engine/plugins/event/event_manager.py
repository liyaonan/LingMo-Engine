"""EventManager — 事件 CRUD、工具构建、摘要提取、文件持久化。"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from pathlib import Path

from lingmo_engine.core.types import DisplayType, ModuleResult, ToolDefinition, ToolParameter
from lingmo_engine.plugins.event.types import EventRecord

logger = logging.getLogger(__name__)

PROGRESS_HEADING = "## 当前进展"


class EventManager:
    """管理事件注册表，提供 CRUD、LLM 工具构建、摘要提取、存档序列化。"""

    def __init__(self):
        self._events: dict[str, EventRecord] = {}
        self._slot_dir: Path | None = None
        self._template_md: str = ""
        self._generation_md: str = ""
        self._examples: list[str] = []
        self._progress_heading: str = PROGRESS_HEADING
        self._player_hidden_headings: set[str] = {"各方动机", "发展大纲"}

    # ── 配置加载 ──

    def load_world_config(self, events_dir: Path) -> None:
        """加载 World 事件配置：模板、指引、示例。"""
        template_path = events_dir / "_template.md"
        if template_path.exists():
            self._template_md = template_path.read_text(encoding="utf-8")
            logger.info("EventManager: 加载模板 %s", template_path)

        gen_path = events_dir / "generation.md"
        if gen_path.exists():
            self._generation_md = gen_path.read_text(encoding="utf-8")
            logger.info("EventManager: 加载生成指引 %s", gen_path)

        examples_dir = events_dir / "examples"
        if examples_dir.is_dir():
            for md_file in sorted(examples_dir.glob("*.md")):
                self._examples.append(md_file.read_text(encoding="utf-8"))
            logger.info("EventManager: 加载 %d 个示例", len(self._examples))

        # 从模板中检测进展段落标题 + 推导隐藏段落
        if self._template_md:
            heading_set: set[str] = set()
            for line in self._template_md.splitlines():
                line = line.strip()
                if line.startswith("## "):
                    heading = line[3:].strip()
                    heading_set.add(heading)
                    if "进展" in heading:
                        self._progress_heading = line
            # 从 generation.md 中检测哪些标题标记为 GM 不向玩家展示
            if self._generation_md and heading_set:
                derived_hidden: set[str] = set()
                for heading in heading_set:
                    for gen_line in self._generation_md.splitlines():
                        if heading in gen_line and (
                            "不向玩家展示" in gen_line
                            or "GM 参考" in gen_line
                            or "GM 专用" in gen_line
                        ):
                            derived_hidden.add(heading)
                            break
                if derived_hidden:
                    self._player_hidden_headings = derived_hidden
                    logger.info(
                        "EventManager: 从 generation.md 推导隐藏段落: %s",
                        derived_hidden,
                    )

    # ── 文件持久化 ──

    def set_slot_dir(self, slot_dir: Path) -> None:
        """设置存档根目录，确保 event 子目录存在。"""
        self._slot_dir = slot_dir
        (slot_dir / "event").mkdir(parents=True, exist_ok=True)

    @property
    def has_slot_dir(self) -> bool:
        return self._slot_dir is not None

    def _event_dir(self) -> Path | None:
        if self._slot_dir is None:
            return None
        return self._slot_dir / "event"

    def _save_event_file(self, record: EventRecord) -> None:
        """将单个事件原子写入独立 JSON 文件（tempfile + os.replace）。"""
        event_dir = self._event_dir()
        if event_dir is None:
            return
        event_dir.mkdir(parents=True, exist_ok=True)
        path = event_dir / f"{record.event_id}.json"
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(event_dir))
        fd_closed = False
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(record.to_dict(), f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            fd_closed = True
            os.replace(tmp_path, str(path))
        except Exception:
            if not fd_closed:
                try:
                    os.close(tmp_fd)
                except OSError:
                    pass
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    # ── LLM 工具 ──

    def build_tools(self) -> list[ToolDefinition]:
        """构建三个事件管理工具。"""
        return [
            ToolDefinition(
                name="create_event",
                description="创建一个新的世界动态事件，编写完整的剧情计划。"
                            "在剧情自然需要一个新事件时调用。",
                parameters=[
                    ToolParameter(
                        name="title", type="string",
                        description="事件标题，简洁有力",
                        required=True,
                    ),
                    ToolParameter(
                        name="plan_md", type="string",
                        description=f"完整的事件计划 Markdown。模板格式：\n{self._template_md}",
                        required=True,
                    ),
                ],
                plugin_name="events",
            ),
            ToolDefinition(
                name="update_event",
                description="全量替换已有事件的 Markdown 计划，或标记事件完成/恢复。"
                            "用于剧情重大转向时调用。",
                parameters=[
                    ToolParameter(
                        name="event_id", type="string",
                        description="要更新的事件 ID",
                        required=True,
                    ),
                    ToolParameter(
                        name="plan_md", type="string",
                        description="完整的新 Markdown 计划（替换原内容）",
                        required=False,
                    ),
                    ToolParameter(
                        name="status", type="string",
                        description="事件状态：'active' 或 'completed'",
                        required=False,
                        enum=["active", "completed"],
                    ),
                ],
                plugin_name="events",
            ),
            ToolDefinition(
                name="append_event_progress",
                description="向已创建事件的当前进展段落追加新内容。"
                            "仅用于已在 create_event 中创建的事件。"
                            "叙述完与该事件相关的剧情后调用，追加新进展。",
                parameters=[
                    ToolParameter(
                        name="event_id", type="string",
                        description="要追加进展的事件 ID",
                        required=True,
                    ),
                    ToolParameter(
                        name="progress", type="string",
                        description="新增的进展内容，追加到当前进展段落后",
                        required=True,
                    ),
                ],
                plugin_name="events",
            ),
        ]

    def build_system_prompt_fragment(self) -> str:
        """构建注入 LLM 系统提示的事件生成指引。"""
        parts = []
        if self._generation_md:
            parts.append("## 事件生成指引\n" + self._generation_md)
        if self._template_md:
            parts.append("## 事件 Markdown 模板（新事件请严格按此格式编写）\n"
                         "```markdown\n" + self._template_md + "\n```")
        if self._examples:
            lines = ["## 事件格式参考示例",
                     "**注意：以下仅为格式示例，并非当前活跃事件。"
                     "如需创建类似事件，请调用 create_event 工具。**"]
            for i, example in enumerate(self._examples, 1):
                lines.append(f"### 示例 {i}\n```markdown\n{example}\n```")
            parts.append("\n".join(lines))
        return "\n\n".join(parts)

    # ── 工具执行 ──

    def execute_tool(self, tool_name: str, params: dict,
                     game_time: str = "") -> ModuleResult:
        """分发工具调用。"""
        if tool_name == "create_event":
            return self._create(params, game_time)
        if tool_name == "update_event":
            return self._update(params, game_time)
        if tool_name == "append_event_progress":
            return self._append(params, game_time)
        return ModuleResult(success=False, log=f"未知事件工具: {tool_name}")

    def _create(self, params: dict, game_time: str) -> ModuleResult:
        title = params.get("title", "")
        plan_md = params.get("plan_md", "")
        if not title or not plan_md:
            return ModuleResult(success=False, log="title 和 plan_md 为必填参数")

        event_id = f"evt_{uuid.uuid4().hex[:8]}"
        record = EventRecord(
            event_id=event_id,
            title=title,
            status="active",
            plan_md=plan_md,
            created_at=game_time,
            updated_at=game_time,
        )
        self._events[event_id] = record
        self._save_event_file(record)
        logger.info("EventManager: 创建事件 [%s] %s", event_id, title)
        return ModuleResult(
            success=True,
            log=f"事件「{title}」已创建 ({event_id})",
            data={"event_id": event_id, "title": title},
            display_type=DisplayType.SYSTEM,
        )

    def _update(self, params: dict, game_time: str) -> ModuleResult:
        event_id = params.get("event_id", "")
        record = self._events.get(event_id)
        if record is None:
            return ModuleResult(success=False, log=f"事件 {event_id} 不存在")

        if "plan_md" in params and params["plan_md"]:
            record.plan_md = params["plan_md"]
        if "status" in params and params["status"]:
            record.status = params["status"]
        record.updated_at = game_time
        self._save_event_file(record)

        logger.info("EventManager: 更新事件 [%s] status=%s",
                    event_id, record.status)
        return ModuleResult(
            success=True,
            log=f"事件「{record.title}」已更新",
            data={"event_id": event_id, "status": record.status},
            display_type=DisplayType.SYSTEM,
        )

    def _append(self, params: dict, game_time: str) -> ModuleResult:
        event_id = params.get("event_id", "")
        progress = params.get("progress", "")
        record = self._events.get(event_id)
        if record is None:
            return ModuleResult(success=False, log=f"事件 {event_id} 不存在")
        if not progress:
            return ModuleResult(success=False, log="progress 不能为空")

        # 插入到进展标题之后，而非文档末尾
        heading = self._progress_heading
        if heading in record.plan_md:
            idx = record.plan_md.rfind(heading)
            insert_point = record.plan_md.find("\n", idx)
            if insert_point != -1:
                record.plan_md = (
                    record.plan_md[:insert_point + 1]
                    + progress + "\n"
                    + record.plan_md[insert_point + 1:]
                )
            else:
                record.plan_md += f"\n{progress}"
        else:
            record.plan_md += f"\n\n{heading}\n{progress}"
        record.updated_at = game_time
        self._save_event_file(record)
        logger.info("EventManager: 追加进展 [%s]", event_id)
        return ModuleResult(
            success=True,
            log=f"已追加「{record.title}」的进展",
            data={"event_id": event_id},
            display_type=DisplayType.SYSTEM,
        )

    # ── 摘要 ──

    def get_summaries(self) -> str:
        """返回所有活跃事件摘要，用于注入 LLM 上下文。"""
        active = [r for r in self._events.values() if r.status == "active"]
        if not active:
            return (
                "[当前世界事件] 暂无活跃事件。如果剧情发展需要，可调用 "
                "create_event 工具创建新事件。"
            )

        lines = ["[当前世界事件]"]
        for r in active:
            progress = self._extract_progress(r.plan_md)
            lines.append(
                f"- **{r.title}** ({r.event_id}): {progress}"
            )
        return "\n".join(lines)

    def _extract_progress(self, plan_md: str) -> str:
        """从 plan_md 中提取当前进展段落的内容。"""
        in_section = False
        lines = []
        for line in plan_md.splitlines():
            if line.strip().startswith("## ") and "进展" in line:
                in_section = True
                continue
            if in_section:
                if line.strip().startswith("## "):
                    break
                stripped = line.strip()
                if stripped:
                    lines.append(stripped)
        if not lines:
            return "（暂无进展）"
        result = " ".join(lines)
        return result[:200] if len(result) > 200 else result

    # ── 查询 ──

    def list_events(self) -> list[dict]:
        """返回前端事件列表数据。player_view 仅含背景和进展，过滤 GM 情报。"""
        return [
            {
                "event_id": r.event_id,
                "title": r.title,
                "status": r.status,
                "player_view": self._extract_player_view(r.plan_md),
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            for r in self._events.values()
        ]

    def _extract_player_view(self, plan_md: str) -> str:
        """从 plan_md 中提取玩家可见段落，过滤 GM 情报。
        隐藏段落集由 load_world_config 从 generation.md 推导。"""
        hidden = self._player_hidden_headings
        in_section = None  # None=不在任何段落, True=在可见段落, False=在隐藏段落
        sections: list[str] = []

        for line in plan_md.splitlines():
            stripped = line.strip()
            if stripped.startswith("## "):
                heading = stripped[3:].strip()
                in_section = heading not in hidden
                if in_section:
                    sections.append(line)
                continue
            if in_section:
                sections.append(line)

        result = "\n".join(sections).strip()
        return result if result else plan_md  # 兜底：无识别段落时返回原文

    def get_event_count(self) -> int:
        return len(self._events)

    # ── 存档序列化 ──

    # ── 存档序列化 ──

    def load_from_files(self) -> None:
        """从 event/ 目录加载事件文件（SelfPersistable 主路径）。"""
        self._events.clear()
        event_dir = self._event_dir()
        if event_dir is None or not event_dir.exists():
            return
        for path in event_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                record = EventRecord.from_dict(data)
                self._events[record.event_id] = record
            except Exception as e:
                logger.warning("加载事件文件失败 %s: %s", path, e)

    def migrate_from_state(self, state: dict) -> None:
        """从旧的 state.json 内嵌格式迁移到独立文件。"""
        self._migrate_from_dict(state)

    def _migrate_from_dict(self, state: dict) -> None:
        """从旧的 state.json 内嵌格式迁移到独立文件。

        支持两种调用方式传入的 state dict：
        - load_state_to_all_plugins: 完整 state.json，嵌套路径 plugins.events.event_records
        - load_all_state: 插件子节，顶层 event_records
        """
        event_dir = self._event_dir()
        if event_dir is None:
            return

        # 已迁移过则跳过
        if (event_dir / ".migrated").exists():
            return

        records = state.get("event_records", [])
        if not records:
            plugins_data = state.get("plugins", {})
            events_data = plugins_data.get("events", {})
            records = events_data.get("event_records", [])
        if not records:
            return

        migrated = 0
        for data in records:
            if isinstance(data, dict):
                record = EventRecord.from_dict(data)
                self._save_event_file(record)
                migrated += 1

        if migrated > 0:
            # 写入迁移标记，防止重复迁移
            (event_dir / ".migrated").write_text(
                f"migrated={migrated}", encoding="utf-8"
            )
            logger.info("EventManager: 从旧格式迁移 %d 个事件到独立文件", migrated)
