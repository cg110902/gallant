"""
LLM Module - 大模型驱动、网关路由器与财务审计
"""

from .client import (
    BaseLLMProvider,
    GeminiProvider,
    LLMGenerationResult,
    MockLLMProvider,
    OpenAICompatibleProvider,
    get_llm_provider,
)
from .cost_tracker import CostTracker, ModelPricing, TokenUsageRecord
from .cost_auditor import (
    BookCostSummary,
    ChapterCostSummary,
    CostAuditor,
    FinancialAlertLevel,
    FinancialCircuitBreakerError,
)
from .gateway import (
    CircuitState,
    GatewayCircuitError,
    GatewayConfig,
    ModelGateway,
)

__all__ = [
    "BaseLLMProvider",
    "MockLLMProvider",
    "OpenAICompatibleProvider",
    "GeminiProvider",
    "LLMGenerationResult",
    "get_llm_provider",
    "CostTracker",
    "ModelPricing",
    "TokenUsageRecord",
    "CostAuditor",
    "ChapterCostSummary",
    "BookCostSummary",
    "FinancialAlertLevel",
    "FinancialCircuitBreakerError",
    "CircuitState",
    "GatewayCircuitError",
    "GatewayConfig",
    "ModelGateway",
]
