from __future__ import annotations


class ConfigService:
    """配置服务 — 封装 LLM 配置相关操作。"""

    def __init__(self, gm, config):
        self._gm = gm
        self._config = config

    def reload_llm(self, provider=None, fast_provider=None) -> None:
        """重新加载 LLM 配置"""
        self._gm.reload_llm(provider, fast_provider=fast_provider)

    def is_busy(self) -> bool:
        """LLM 是否繁忙"""
        return self._gm.llm_handler.is_busy

    async def test_llm(self, mode: str = "strong"):
        """测试 LLM 连接"""
        return await self._gm.llm_handler.request(
            [{"role": "user", "content": "Hi"}], mode=mode
        )

    def get_model(self) -> str:
        """获取当前模型名称"""
        return self._config.llm.model

    async def request_llm(self, messages: list, mode: str = "strong"):
        """直接请求 LLM（用于连接测试）"""
        return await self._gm.llm_handler.request(messages, mode=mode)
