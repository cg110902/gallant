"""
Cost Tracker - Token 经济学与商业毛利核算引擎
支持精确到厘的单章/全书成本计算，原生统计 Prompt Caching 节约率，并提供预算超额断路器。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ModelPricing:
    model_name: str
    price_per_1m_input: float          # 人民币 (¥) / 100万 输入 Token
    price_per_1m_cached_input: float   # 命中缓存时的优惠价
    price_per_1m_output: float         # 人民币 (¥) / 100万 输出 Token


# 常用主流模型定价库 (截至2025/2026公开商业价，折合人民币CNY)
DEFAULT_PRICING_TABLE: Dict[str, ModelPricing] = {
    "gemini-1.5-flash": ModelPricing(
        model_name="gemini-1.5-flash",
        price_per_1m_input=0.55,
        price_per_1m_cached_input=0.14,
        price_per_1m_output=2.20
    ),
    "gemini-1.5-pro": ModelPricing(
        model_name="gemini-1.5-pro",
        price_per_1m_input=8.75,
        price_per_1m_cached_input=2.20,
        price_per_1m_output=35.00
    ),
    "deepseek-v3": ModelPricing(
        model_name="deepseek-v3",
        price_per_1m_input=1.00,
        price_per_1m_cached_input=0.10,
        price_per_1m_output=2.00
    ),
    "mock": ModelPricing(
        model_name="mock",
        price_per_1m_input=0.0,
        price_per_1m_cached_input=0.0,
        price_per_1m_output=0.0
    )
}


@dataclass
class TokenUsageRecord:
    chapter_index: int
    beat_id: str
    model_name: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    calculated_cost_cny: float


class CostTracker:
    """流水线成本审计器"""

    def __init__(
        self,
        pricing_table: Optional[Dict[str, ModelPricing]] = None,
        max_cost_per_chapter_cny: float = 0.50  # 单章成本上限（超过则熔断告警）
    ):
        self.pricing = pricing_table or dict(DEFAULT_PRICING_TABLE)
        self.max_cost_per_chapter = max_cost_per_chapter_cny
        self.records: List[TokenUsageRecord] = []

    def record_usage(
        self,
        chapter_index: int,
        beat_id: str,
        model_name: str,
        input_tokens: int,
        cached_input_tokens: int = 0,
        output_tokens: int = 0
    ) -> TokenUsageRecord:
        """记录单次调用消耗并计算成本"""
        pricing = self.pricing.get(model_name, self.pricing["mock"])

        uncached_input = max(0, input_tokens - cached_input_tokens)
        cost_uncached = (uncached_input / 1_000_000) * pricing.price_per_1m_input
        cost_cached = (cached_input_tokens / 1_000_000) * pricing.price_per_1m_cached_input
        cost_output = (output_tokens / 1_000_000) * pricing.price_per_1m_output
        total_cost = cost_uncached + cost_cached + cost_output

        record = TokenUsageRecord(
            chapter_index=chapter_index,
            beat_id=beat_id,
            model_name=model_name,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            calculated_cost_cny=total_cost
        )
        self.records.append(record)
        return record

    def get_chapter_cost_summary(self, chapter_index: int) -> Dict[str, Any]:
        """获取指定章节的消耗汇总"""
        ch_records = [r for r in self.records if r.chapter_index == chapter_index]
        total_in = sum(r.input_tokens for r in ch_records)
        total_cached = sum(r.cached_input_tokens for r in ch_records)
        total_out = sum(r.output_tokens for r in ch_records)
        total_cost = sum(r.calculated_cost_cny for r in ch_records)

        cache_ratio = (total_cached / total_in * 100) if total_in > 0 else 0.0
        is_exceeded = total_cost > self.max_cost_per_chapter

        return {
            "chapter_index": chapter_index,
            "calls_count": len(ch_records),
            "total_input_tokens": total_in,
            "cached_input_tokens": total_cached,
            "cache_hit_rate": f"{cache_ratio:.1f}%",
            "total_output_tokens": total_out,
            "total_cost_cny": round(total_cost, 4),
            "is_budget_exceeded": is_exceeded
        }

    def get_total_manuscript_cost(self) -> float:
        """获取整部作品累计消耗金额 (CNY)"""
        return sum(r.calculated_cost_cny for r in self.records)
