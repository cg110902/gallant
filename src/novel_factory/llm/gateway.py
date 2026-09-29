"""
Model Gateway & Provider Mesh - 工业级多模型网关与 Prompt Caching 优化器
支持 Google Gemini API, OpenAI 兼容生态 (DeepSeek-V3, Qwen, Moonshot, Ollama) 与本地微调端点：
1. 统一接口与流式透传 (Streaming Chunking)；
2. 指数退避重试与网络抖动自愈 (Exponential Backoff & Jitter)；
3. 熔断断路器 (Circuit Breaker)：连续报错自动冷却，防止级联雪崩；
4. Prompt Caching 结构化优化器：前置不可变世界观设定，最大化命中厂商前缀缓存 (节约 70%~90% 费用)。
"""

from enum import Enum
import json
import logging
import math
import os
import random
import time
from typing import Any, AsyncGenerator, Callable, Dict, Generator, List, Optional, Tuple
import httpx
from pydantic import BaseModel, Field

from src.novel_factory.llm.client import (
    BaseLLMProvider,
    GeminiProvider,
    LLMGenerationResult,
    MockLLMProvider,
    OpenAICompatibleProvider,
)
from src.novel_factory.pipeline.stream_monitor import StreamChunkResult, StreamMonitor

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "CLOSED"      # 正常工作状态
    OPEN = "OPEN"          # 熔断开启（拒绝外部流量）
    HALF_OPEN = "HALF_OPEN"  # 半开试探


class GatewayCircuitError(Exception):
    """网关熔断保护异常"""
    pass


class GatewayConfig(BaseModel):
    """模型网关配置参数"""
    provider_name: str = "openai_compatible"  # gemini, openai_compatible, mock
    model_name: str = "deepseek-chat"
    api_key: str = ""
    base_url: str = "https://api.deepseek.com/v1"
    temperature: float = 0.7
    max_tokens: int = 2000
    timeout_seconds: float = 60.0
    max_retries: int = 3
    retry_base_delay: float = 1.0
    circuit_failure_threshold: int = 4
    circuit_recovery_timeout: float = 30.0


class ModelGateway:
    """大模型高可用网关"""

    def __init__(self, config: Optional[GatewayConfig] = None):
        self.config = config or GatewayConfig()
        self.circuit_state = CircuitState.CLOSED
        self.consecutive_failures = 0
        self.last_failure_time = 0.0

        # 初始化底层驱动
        self.provider: BaseLLMProvider = self._build_provider()

    def _build_provider(self) -> BaseLLMProvider:
        """根据配置组装具体 Provider"""
        p_name = self.config.provider_name.lower()
        if p_name == "gemini":
            return GeminiProvider(
                api_key=self.config.api_key or os.environ.get("GEMINI_API_KEY"),
                model_name=self.config.model_name,
                timeout_seconds=self.config.timeout_seconds
            )
        elif p_name in ("openai", "deepseek", "openai_compatible", "qwen", "ollama"):
            return OpenAICompatibleProvider(
                api_key=self.config.api_key or os.environ.get("OPENAI_API_KEY"),
                base_url=self.config.base_url,
                model_name=self.config.model_name,
                timeout_seconds=self.config.timeout_seconds
            )
        else:
            return MockLLMProvider()

    def _check_circuit(self):
        """断路器状态机前置断言"""
        now = time.time()
        if self.circuit_state == CircuitState.OPEN:
            if now - self.last_failure_time >= self.config.circuit_recovery_timeout:
                logger.info("网关断路器进入 HALF_OPEN 试探恢复状态")
                self.circuit_state = CircuitState.HALF_OPEN
            else:
                remaining = self.config.circuit_recovery_timeout - (now - self.last_failure_time)
                raise GatewayCircuitError(f"网关已熔断，冷却中，剩余 {remaining:.1f} 秒")

    def _record_success(self):
        """成功后恢复闭合"""
        self.consecutive_failures = 0
        self.circuit_state = CircuitState.CLOSED

    def _record_failure(self):
        """失败累积与熔断判定"""
        self.consecutive_failures += 1
        self.last_failure_time = time.time()
        if self.consecutive_failures >= self.config.circuit_failure_threshold:
            self.circuit_state = CircuitState.OPEN
            logger.warning(f"网关连续失败 {self.consecutive_failures} 次，触发熔断 OPEN")

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> LLMGenerationResult:
        """
        带断路器与指数退避重试的同步生成接口
        """
        self._check_circuit()
        temp = temperature if temperature is not None else self.config.temperature
        tokens = max_tokens if max_tokens is not None else self.config.max_tokens

        last_exc: Optional[Exception] = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                result = self.provider.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=temp,
                    max_tokens=tokens
                )
                self._record_success()
                return result
            except Exception as e:
                last_exc = e
                logger.warning(f"网关调用失败 [尝试 {attempt}/{self.config.max_retries}]: {e}")
                if attempt < self.config.max_retries:
                    # 指数退避加抖动
                    delay = self.config.retry_base_delay * (2 ** (attempt - 1)) + random.uniform(0.1, 0.5)
                    time.sleep(delay)

        self._record_failure()
        raise RuntimeError(f"模型网关调用在重试 {self.config.max_retries} 次后彻底失败: {last_exc}") from last_exc

    def stream_generate_mock(
        self,
        chunks: List[str],
        stream_monitor: Optional[StreamMonitor] = None
    ) -> Generator[str, None, None]:
        """
        模拟流式推送与熔断挂接（用于单元测试与离线工作流）
        """
        monitor = stream_monitor or StreamMonitor()
        for chunk in chunks:
            res = monitor.feed_chunk(chunk)
            yield res.chunk_text
            if res.is_aborted:
                logger.info(f"流式监控截断: {res.abort_reason}")
                break

    @staticmethod
    def format_cache_optimized_prompt(
        immutable_codex: str,
        dynamic_task: str
    ) -> Tuple[str, str]:
        """
        Prompt Caching 结构化优化器：
        规范分流前缀：将不可变世界观设定、人物档案放入 system_prompt 置顶（最大化厂商KV Cache命中率），
        将动态变化的单章目标、节拍任务放入 user_prompt。
        """
        system = f"【不可变世界设定与剧情约束基石】\n{immutable_codex.strip()}"
        user = f"【当前单节拍动态创作任务】\n{dynamic_task.strip()}"
        return system, user
