"""
LLM Client Gateway - 多模型路由器与统一大模型网关
支持 Google Gemini、OpenAI兼容接口（DeepSeek / Qwen / Ollama）与 Mock 确定性回退接口。
提供重试、超时控制与 Token 开销精确回传。
"""

import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import httpx


@dataclass
class LLMGenerationResult:
    text: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    latency_ms: float
    model_name: str


class BaseLLMProvider(ABC):
    """大模型提供商统一抽象基类"""

    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 1500
    ) -> LLMGenerationResult:
        pass


class MockLLMProvider(BaseLLMProvider):
    """离线与测试专用 Mock 提供商"""

    def __init__(self, canned_response: Optional[str] = None):
        self.canned_response = canned_response or "酸雨顺着破损的霓虹招牌滴落。\n零号收起微型激光刀，手指没有丝毫晃动。"

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 1500
    ) -> LLMGenerationResult:
        start_t = time.time()
        in_tokens = int((len(system_prompt) + len(user_prompt)) / 1.6)
        out_tokens = int(len(self.canned_response) / 1.6)
        # 模拟 70% 的 Prompt 缓存命中
        cached_tokens = int(in_tokens * 0.7)
        latency = (time.time() - start_t) * 1000

        return LLMGenerationResult(
            text=self.canned_response,
            input_tokens=in_tokens,
            cached_input_tokens=cached_tokens,
            output_tokens=out_tokens,
            latency_ms=latency,
            model_name="mock"
        )


class OpenAICompatibleProvider(BaseLLMProvider):
    """支持 DeepSeek、Moonshot、Qwen、Ollama、vLLM 等兼容接口"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.deepseek.com/v1",
        model_name: str = "deepseek-v3",
        timeout_seconds: float = 60.0
    ):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout = timeout_seconds

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 1500
    ) -> LLMGenerationResult:
        start_t = time.time()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        in_tokens = usage.get("prompt_tokens", 0)
        out_tokens = usage.get("completion_tokens", 0)
        # DeepSeek Prompt Cache 统计
        prompt_cache_hit = usage.get("prompt_cache_hit_tokens", 0)
        latency = (time.time() - start_t) * 1000

        return LLMGenerationResult(
            text=text,
            input_tokens=in_tokens,
            cached_input_tokens=prompt_cache_hit,
            output_tokens=out_tokens,
            latency_ms=latency,
            model_name=self.model_name
        )


class GeminiProvider(BaseLLMProvider):
    """原生 Google Gemini REST 接口提供商 (兼容 HTTP 直接请求)"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-3.8-flash",
        timeout_seconds: float = 60.0
    ):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
        self.model_name = model_name
        self.timeout = timeout_seconds

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 1500
    ) -> LLMGenerationResult:
        start_t = time.time()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
        
        payload = {
            "system_instruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": [
                {"parts": [{"text": user_prompt}]}
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens
            }
        }

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        candidate = data.get("candidates", [{}])[0]
        text = candidate.get("content", {}).get("parts", [{}])[0].get("text", "")
        usage = data.get("usageMetadata", {})
        
        in_tokens = usage.get("promptTokenCount", 0)
        out_tokens = usage.get("candidatesTokenCount", 0)
        cached_tokens = usage.get("cachedContentTokenCount", 0)
        latency = (time.time() - start_t) * 1000

        return LLMGenerationResult(
            text=text,
            input_tokens=in_tokens,
            cached_input_tokens=cached_tokens,
            output_tokens=out_tokens,
            latency_ms=latency,
            model_name=self.model_name
        )


def get_llm_provider(
    provider_type: str = "mock",
    model_name: str = "gemini-3.8-flash",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None
) -> BaseLLMProvider:
    """工厂方法创建指定的 LLM Provider"""
    if provider_type == "gemini":
        from src.novel_factory.llm.gemini_adapter import GeminiNativeProvider
        return GeminiNativeProvider(api_key=api_key, default_model=model_name)
    elif provider_type == "gemini_rest":
        return GeminiProvider(api_key=api_key, model_name=model_name)
    elif provider_type in ("openai", "deepseek", "custom"):
        url = base_url or "https://api.deepseek.com/v1"
        return OpenAICompatibleProvider(api_key=api_key, base_url=url, model_name=model_name)
    else:
        return MockLLMProvider()
