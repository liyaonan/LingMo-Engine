"""PromptComposer — 管理 worlds/{world}/prompts/ 目录中的提示词文件。

按文件名前缀自动分组:
- head_*.md      -> self.head_prompt (拼入 system message [0])
- tail_*.md      -> self.tail_condensed (追加在历史之后，利用 recency effect)
- usertail_*.md  -> self.user_tail (以()包裹追加到最后一条 user message)
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class PromptComposer:
    """管理 worlds/{world}/prompts/ 目录中的提示词文件。"""

    def __init__(self, world_dir: str | Path, style: str = "carefree") -> None:
        self._world_dir = Path(world_dir)
        self._style = style
        self._head_prompt: str = ""
        self._tail_condensed: str = ""
        self._cot_thinking_guide: str = ""
        self._user_tail: str = ""
        self._load()

    def _load(self) -> None:
        prompts_dir = self._world_dir / "prompts"
        if prompts_dir.is_dir():
            self._load_from_prompts_dir(prompts_dir)
        else:
            logger.warning("prompts/ 目录不存在: %s", self._world_dir)
            self._head_prompt = ""
            self._tail_condensed = ""
            self._cot_thinking_guide = ""
            self._user_tail = ""

    def _load_from_prompts_dir(self, prompts_dir: Path) -> None:
        head_files = sorted(prompts_dir.glob("head_*.md"))
        head_parts: list[str] = []
        for f in head_files:
            fname = f.name
            # head_04 风格切换
            if fname == "head_04_writing_style.md" and self._style == "dark":
                continue
            if fname == "head_04_writing_style_dark.md" and self._style != "dark":
                continue
            try:
                text = f.read_text(encoding="utf-8").strip()
                if text:
                    head_parts.append(text)
            except Exception:
                logger.warning("读取提示词文件失败: %s", f)

        self._head_prompt = "\n\n".join(head_parts)

        tail_files = sorted(prompts_dir.glob("tail_*.md"))
        if tail_files:
            tail_parts: list[str] = []
            for f in tail_files:
                try:
                    text = f.read_text(encoding="utf-8").strip()
                    if text:
                        tail_parts.append(text)
                except Exception:
                    logger.warning("读取尾锚点文件失败: %s", f)
            self._tail_condensed = "\n\n".join(tail_parts)

        # 🆕 加载 COT 思考引导文件
        cot_files = sorted(prompts_dir.glob("cot_*.md"))
        if cot_files:
            cot_parts: list[str] = []
            for f in cot_files:
                try:
                    text = f.read_text(encoding="utf-8").strip()
                    if text:
                        cot_parts.append(text)
                except Exception:
                    logger.warning("读取 COT 引导文件失败: %s", f)
            self._cot_thinking_guide = "\n\n".join(cot_parts)

        # 加载 usertail 文件
        usertail_files = sorted(prompts_dir.glob("usertail_*.md"))
        if usertail_files:
            usertail_parts: list[str] = []
            for f in usertail_files:
                try:
                    text = f.read_text(encoding="utf-8").strip()
                    if text:
                        usertail_parts.append(text)
                except Exception:
                    logger.warning("读取 usertail 文件失败: %s", f)
            self._user_tail = "\n".join(usertail_parts)

        logger.info(
            "PromptComposer 已加载: %d 个 head 文件, %d 个 tail 文件, "
            "%d 个 cot 文件, %d 个 usertail 文件 (来源: %s, 风格: %s)",
            len(head_files), len(tail_files), len(cot_files),
            len(usertail_files), prompts_dir, self._style,
        )

    @property
    def head_prompt(self) -> str:
        """静态 HEAD 锚点 — 拼入 system message [0]。"""
        return self._head_prompt

    @property
    def tail_condensed(self) -> str:
        """结尾浓缩提醒 — 追加在历史之后，利用 recency effect。"""
        return self._tail_condensed

    @property
    def cot_thinking_guide(self) -> str:
        """COT 思考引导 — 在角色记忆与动态状态之间注入。"""
        return self._cot_thinking_guide

    @property
    def user_tail(self) -> str:
        """用户消息尾缀 — 以()包裹追加到最后一条 user message。"""
        return self._user_tail

    def reload(self) -> None:
        """重新扫描 prompts/ 目录（例如世界切换时调用）。"""
        self._head_prompt = ""
        self._tail_condensed = ""
        self._cot_thinking_guide = ""
        self._user_tail = ""
        self._load()

    def set_style(self, style: str) -> None:
        """切换叙事风格并重新加载 head_04。"""
        if style == self._style:
            return
        self._style = style
        self._head_prompt = ""
        self._tail_condensed = ""
        self._cot_thinking_guide = ""
        self._user_tail = ""
        self._load()
