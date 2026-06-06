"""Skill 管理器 — 加载、缓存、分层组装、模板渲染"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from lingmo_engine.core.types import ToolDefinition, ToolParameter

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    """单个 Skill 的内存表示"""
    name: str
    description: str = ""
    type: str = "generation"
    trigger: str = ""
    priority: int = 100
    body: str = ""
    source_path: str = ""
    parameters: list[str] = field(default_factory=list)
    checklist: list[str] = field(default_factory=list)


class SkillManager:
    """Skill 管理器：扫描插件和世界的 Skill .md 文件，管理分层注入。

    使用方式:
        manager = SkillManager(world_dir, plugin_registry)
        base_prompt = manager.load_base_skills()
        rendered = manager.render_skill("skill_name", var1="value1")
    """

    def __init__(self, world_dir: str, plugin_registry) -> None:
        self._world_dir = world_dir
        self._registry = plugin_registry
        self._skills: dict[str, Skill] = {}
        self._base_skill_names: list[str] = []
        self._dynamic_skill_groups: dict[str, list[str]] = {}
        self._available_skills: dict[str, dict] = {}  # __global__.yaml 中的 available_skills

        self._scan_skills_dirs()
        self._load_config()

    # ── 公共接口 ──────────────────────────────────

    def load_base_skills(self) -> str:
        """组装所有 base skill 的合并 prompt 文本。"""
        skills = [self._skills[name] for name in self._base_skill_names if name in self._skills]
        return self._merge_skills(skills)

    def load_dynamic_skills(self, trigger: str) -> str:
        """按触发时机组装动态 prompt 文本。"""
        names = self._dynamic_skill_groups.get(trigger, [])
        skills = [self._skills[name] for name in names if name in self._skills]
        if not skills:
            logger.debug("No dynamic skills found for trigger: %s", trigger)
            return ""
        return self._merge_skills(skills)

    def render_skill(self, name: str, **vars) -> str:
        """加载单个 Skill 并用模板变量渲染。

        Args:
            name: Skill 名称
            **vars: 模板变量，替换 Skill body 中的 {{ var_name }}

        Returns:
            渲染后的 prompt 文本

        Raises:
            ValueError: Skill 不存在
        """
        skill = self._skills.get(name)
        if skill is None:
            raise ValueError(f"Skill not found: {name}")

        body = skill.body
        for key, value in vars.items():
            body = body.replace("{{ " + key + " }}", str(value))
        return body

    def get_skill(self, name: str) -> Skill | None:
        """根据名称获取 Skill 对象。"""
        return self._skills.get(name)

    def build_skill_tool_definition(self) -> ToolDefinition | None:
        """生成 use_skill 的 ToolDefinition，参数 name 带 enum 约束。

        仅在 available_skills 非空时返回定义，避免向 LLM 暴露空工具。
        """
        if not self._available_skills:
            return None

        skill_names = sorted(self._available_skills.keys())
        descriptions = []
        for name in skill_names:
            info = self._available_skills[name]
            desc = info.get("description", "")
            hint = info.get("trigger_hint", "")
            hint_text = f"（建议时机：{hint}）" if hint else ""
            descriptions.append(f"- {name}: {desc}{hint_text}")

        return ToolDefinition(
            name="use_skill",
            description=(
                "加载指定技能的详细生成指导。"
                "当你需要某个领域的具体操作指南时调用此函数。\n"
                "可用技能：\n" + "\n".join(descriptions)
            ),
            parameters=[
                ToolParameter(
                    name="name",
                    type="string",
                    description="要加载的技能名称",
                    required=True,
                    enum=skill_names,
                ),
                ToolParameter(
                    name="args",
                    type="object",
                    description="传递给技能模板的变量（可选，键值对）",
                    required=False,
                ),
            ],
            plugin_name="skill_manager",
        )

    def execute_use_skill(self, name: str, args: dict | None = None) -> dict:
        """响应 use_skill 函数调用，返回渲染后的技能内容。

        Returns:
            dict: {"content": "渲染后的技能正文"}，或技能不存在时的错误提示
        """
        try:
            skill_body = self.render_skill(name, **(args or {}))
        except ValueError:
            logger.warning("use_skill 调用了不存在的技能: %s", name)
            return {"content": f"[技能 '{name}' 不存在，可用的技能: {', '.join(sorted(self._available_skills.keys()))}]"}
        return {"content": skill_body}

    def reload(self) -> None:
        """重新扫描并加载所有 Skill（切换世界时调用）。"""
        self._skills.clear()
        self._base_skill_names.clear()
        self._dynamic_skill_groups.clear()
        self._available_skills.clear()
        self._scan_skills_dirs()
        self._load_config()
        logger.info("SkillManager reloaded: %d skills", len(self._skills))

    # ── 内部方法 ──────────────────────────────────

    def _scan_skills_dirs(self) -> None:
        """扫描插件和世界的 skills/ 目录，加载所有 .md 文件。"""
        # 1) 扫描插件自带 Skill
        if self._registry:
            for dir_path in self._registry.get_all_skill_dirs():
                self._load_from_dir(dir_path)

        # 2) 扫描世界 Skill（覆盖同名）
        if self._world_dir:
            world_skills_dir = Path(self._world_dir) / "skills"
            if world_skills_dir.is_dir():
                self._load_from_dir(str(world_skills_dir), override=True)

    def _load_from_dir(self, dir_path: str, override: bool = False) -> None:
        """递归扫描目录，加载所有 .md 文件。"""
        for root, _dirs, files in os.walk(dir_path):
            for fname in files:
                if fname.endswith(".md"):
                    skill = self._load_skill_file(os.path.join(root, fname))
                    if skill is None:
                        continue
                    if skill.name in self._skills and not override:
                        logger.debug("Skipping duplicate skill: %s (from %s)", skill.name, skill.source_path)
                        continue
                    self._skills[skill.name] = skill

    def _load_skill_file(self, path: str) -> Skill | None:
        """读取单个 .md 文件，解析 YAML frontmatter + Markdown 正文。"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            logger.warning("Failed to read skill file: %s", path)
            return None

        # 解析 YAML frontmatter（--- 开头）
        fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
        if not fm_match:
            logger.warning("Skill file missing frontmatter: %s", path)
            return None

        try:
            meta = yaml.safe_load(fm_match.group(1))
        except yaml.YAMLError as e:
            logger.warning("Failed to parse frontmatter in %s: %s", path, e)
            return None

        body = content[fm_match.end():].strip()

        skill = Skill(
            name=meta.get("name", ""),
            description=meta.get("description", ""),
            type=meta.get("type", "generation"),
            trigger=meta.get("trigger", ""),
            priority=meta.get("priority", 100),
            body=body,
            source_path=path,
            parameters=meta.get("parameters") or [],
            checklist=meta.get("checklist") or [],
        )

        if not skill.name:
            logger.warning("Skill missing name in frontmatter: %s", path)
            return None

        logger.debug("Loaded skill: %s (trigger=%s, priority=%d) from %s",
                     skill.name, skill.trigger, skill.priority, path)
        return skill

    def _load_config(self) -> None:
        """读取世界 Skills 目录下的 __global__.yaml 配置。"""
        if not self._world_dir:
            return

        config_path = Path(self._world_dir) / "skills" / "__global__.yaml"
        if not config_path.exists():
            logger.info("No __global__.yaml found, all skills default to base")
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning("Failed to load __global__.yaml: %s", e)
            return

        self._base_skill_names = config.get("base_skills", [])
        self._dynamic_skill_groups = config.get("dynamic_skills", {})
        self._available_skills = config.get("available_skills", {})

        logger.info("Skill config loaded: %d base, %d dynamic groups, %d available",
                     len(self._base_skill_names), len(self._dynamic_skill_groups),
                     len(self._available_skills))

    @staticmethod
    def _merge_skills(skills: list[Skill]) -> str:
        """按 priority 排序后拼接为完整 prompt 文本。"""
        sorted_skills = sorted(skills, key=lambda s: s.priority)
        parts = []
        for skill in sorted_skills:
            parts.append(skill.body)
        return "\n\n".join(parts)
