"""LLM 输出解析器 — 流式标签扫描与非流式标签提取。

从 GameMaster 中抽取，独立为可测试的纯解析模块。
"""

from __future__ import annotations


class NarrativeTagScanner:
    """流式输出直通扫描器 — 所有文本直接透传给前端。

    保留类结构以维持 llm_handler 接口兼容，
    内部简化为直接透传，不再过滤 <narrative> 标签。
    """

    def __init__(self) -> None:
        self._text = ""

    def feed(self, delta: str) -> list[str]:
        """喂入增量文本，直接返回 [delta] 透传。"""
        self._text += delta
        return [delta]

    def finalize(self) -> list[str]:
        """流结束时无剩余内容需要推送。"""
        return []

    @property
    def narrative_text(self) -> str:
        """获取全部文本（等同于 full_text）。"""
        return self._text


class TaggedOutputParser:
    """解析 LLM 文本输出中的标签化模块。

    与 NarrativeTagScanner 不同，此解析器对完整文本进行非流式解析。
    """

    TAGS = ["narrative"]

    def __init__(self) -> None:
        self._sections: dict[str, str] = {}

    def parse(self, text: str) -> dict[str, str]:
        """解析文本，返回 {tag_name: content} 字典。"""
        self._sections = {}
        for tag in self.TAGS:
            content = self._extract_tag(text, tag)
            self._sections[tag] = content
        return self._sections

    def get(self, tag: str) -> str:
        """获取指定标签的内容。"""
        return self._sections.get(tag, "")

    @staticmethod
    def _extract_tag(text: str, tag: str) -> str:
        """提取 <tag>...</tag> 之间的内容。"""
        open_tag = f"<{tag}>"
        close_tag = f"</{tag}>"
        start = text.find(open_tag)
        if start == -1:
            return ""
        start += len(open_tag)
        end = text.find(close_tag, start)
        if end == -1:
            return ""
        return text[start:end].strip()

