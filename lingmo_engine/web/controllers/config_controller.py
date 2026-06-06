"""配置控制器 - 处理LLM配置相关的WebSocket消息"""
from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket
from openai import OpenAI

from lingmo_engine.core.config import save_config, mask_api_key
from lingmo_engine.llm.openai_compatible import OpenAICompatibleProvider
from lingmo_engine.web.controllers.base_controller import BaseController

logger = logging.getLogger(__name__)


class ConfigController(BaseController):
    """处理LLM配置的读取、更新、测试、模型列表获取"""

    def __init__(self, *, services: dict, config=None):
        super().__init__(services=services, config=config)

    def get_handlers(self) -> dict:
        return {
            "config_get": self._handle_get,
            "config_update": self._handle_update,
            "config_test": self._handle_test,
            "config_models": self._handle_models,
        }

    async def _handle_get(self, ws: WebSocket, msg: dict) -> None:
        llm = self.config.llm
        llm_fast = self.config.llm_fast
        await ws.send_json({
            "type": "config_data",
            "data": {
                "provider": llm.provider,
                "base_url": llm.base_url,
                "api_key_masked": mask_api_key(llm.api_key),
                "model": llm.model,
                "temperature": llm.temperature,
                "max_tokens": llm.max_tokens,
                "stream_response": self.config.stream_response,
                "show_thinking": self.config.show_thinking,
                "llm_fast": {
                    "provider": llm_fast.provider,
                    "base_url": llm_fast.base_url,
                    "api_key_masked": mask_api_key(llm_fast.api_key),
                    "model": llm_fast.model,
                    "temperature": llm_fast.temperature,
                    "max_tokens": llm_fast.max_tokens,
                },
            },
        })

    async def _handle_update(self, ws: WebSocket, msg: dict) -> None:
        try:
            data = msg.get("data", {})
            llm = self.config.llm

            api_key = data.get("api_key", "")
            if not api_key or "****" in api_key:
                api_key = llm.api_key

            llm.provider = data.get("provider", llm.provider)
            llm.base_url = data.get("base_url", llm.base_url)
            llm.api_key = api_key
            llm.model = data.get("model", llm.model)
            llm.temperature = float(data.get("temperature", llm.temperature))
            llm.max_tokens = int(data.get("max_tokens", llm.max_tokens))

            if "stream_response" in data:
                self.config.stream_response = bool(data["stream_response"])

            if "show_thinking" in data:
                self.config.show_thinking = bool(data["show_thinking"])

            # 解析快推理配置
            llm_fast_data = data.get("llm_fast", {})
            if llm_fast_data:
                llm_fast = self.config.llm_fast
                fast_api_key = llm_fast_data.get("api_key", "")
                if not fast_api_key or "****" in fast_api_key:
                    fast_api_key = llm_fast.api_key
                llm_fast.provider = llm_fast_data.get("provider", llm_fast.provider)
                llm_fast.base_url = llm_fast_data.get("base_url", llm_fast.base_url)
                llm_fast.api_key = fast_api_key
                llm_fast.model = llm_fast_data.get("model", llm_fast.model)
                llm_fast.temperature = float(llm_fast_data.get("temperature", llm_fast.temperature))
                llm_fast.max_tokens = int(llm_fast_data.get("max_tokens", llm_fast.max_tokens))

            save_config(self.config)

            new_provider = OpenAICompatibleProvider(llm)
            fast_provider = None
            if self.config.llm_fast.api_key or self.config.llm_fast.model:
                fast_provider = OpenAICompatibleProvider(self.config.llm_fast)
            self.config_svc.reload_llm(new_provider, fast_provider=fast_provider)

            await ws.send_json({
                "type": "config_saved",
                "data": {"success": True, "message": "配置已保存并重新加载"},
            })
        except Exception as e:
            logger.exception("Config update failed")
            await ws.send_json({
                "type": "config_saved",
                "data": {"success": False, "message": str(e)},
            })

    async def _handle_test(self, ws: WebSocket, msg: dict) -> None:
        target = "strong"
        try:
            from lingmo_engine.llm.llm_handler import LLMBusyError
            target = msg.get("data", {}).get("target", "strong") if isinstance(msg.get("data"), dict) else "strong"
            mode = "fast" if target == "fast" else "strong"
            llm_cfg = self.config.llm_fast if target == "fast" else self.config.llm
            try:
                await self.config_svc.request_llm(
                    [{"role": "user", "content": "Hi"}], mode=mode
                )
            except LLMBusyError as e:
                await ws.send_json({
                    "type": "config_test_result",
                    "data": {"success": False, "message": str(e), "model_info": "", "target": target},
                })
                return
            await ws.send_json({
                "type": "config_test_result",
                "data": {"success": True, "message": "连接成功", "model_info": llm_cfg.model, "target": target},
            })
        except Exception as e:
            await ws.send_json({
                "type": "config_test_result",
                "data": {"success": False, "message": str(e), "model_info": "", "target": target},
            })

    async def _handle_models(self, ws: WebSocket, msg: dict) -> None:
        try:
            data = msg.get("data", {})
            target = data.get("target", "strong")
            llm_cfg = self.config.llm_fast if target == "fast" else self.config.llm

            api_key = data.get("api_key", "")
            if not api_key or "****" in api_key:
                api_key = llm_cfg.api_key
            base_url = data.get("base_url", "") or llm_cfg.base_url

            def _fetch():
                client = OpenAI(api_key=api_key, base_url=base_url or None)
                return [m.id for m in client.models.list().data]

            model_ids = await asyncio.to_thread(_fetch)
            model_ids.sort()

            await ws.send_json({
                "type": "config_models_result",
                "data": {"success": True, "models": model_ids, "target": target},
            })
        except Exception as e:
            await ws.send_json({
                "type": "config_models_result",
                "data": {"success": False, "models": [], "message": str(e), "target": target},
            })
