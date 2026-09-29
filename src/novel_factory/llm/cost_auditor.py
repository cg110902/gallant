"""
Cost Auditor & Financial Circuit Breaker - Token 经济学与财务断路器
工业级生产中针对每一厘钱的精确审计与商业 ROI 保障：
1. 厘级精度 Token 成本核算（包含输入、上下文缓存折扣与输出）；
2. 单章财务硬断路器 (Chapter Financial Circuit Breaker)：成本超过阈值 (如 ¥0.40) 立即冻结作业；
3. 全书总投资额度警戒与软警报机制；
4. Prompt Caching 商业节约率真实分析报告。
"""

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from src.novel_factory.llm.cost_tracker import DEFAULT_PRICING_TABLE, ModelPricing, TokenUsageRecord


class FinancialAlertLevel(str, Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"    # 达到预算 80%
    CIRCUIT_TRIPPED = "CIRCUIT_TRIPPED"  # 超出硬阈值，立即熔断


class FinancialCircuitBreakerError(Exception):
    """单章或全书财务预算超限硬熔断异常"""
    pass


class ChapterCostSummary(BaseModel):
    chapter_index: int
    total_input_tokens: int = 0
    total_cached_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_cny: float = 0.0
    cache_hit_rate: float = 0.0
    cny_saved_by_caching: float = 0.0
    is_budget_exceeded: bool = False
    alert_level: FinancialAlertLevel = FinancialAlertLevel.NORMAL


class BookCostSummary(BaseModel):
    total_chapters_recorded: int = 0
    total_cost_cny: float = 0.0
    avg_cost_per_chapter: float = 0.0
    total_tokens_consumed: int = 0
    total_cny_saved_by_caching: float = 0.0
    roi_cost_efficiency_score: float = 100.0


class CostAuditor:
    """工业级财务审计与断路熔断器"""

    def __init__(
        self,
        pricing_table: Optional[Dict[str, ModelPricing]] = None,
        max_cost_per_chapter_cny: float = 0.40,  # 单章硬上限 ¥0.40
        max_total_budget_cny: float = 120.00,    # 全书总预算 ¥120.00
        soft_warning_ratio: float = 0.80
    ):
        self.pricing = pricing_table or dict(DEFAULT_PRICING_TABLE)
        self.max_cost_per_chapter = max_cost_per_chapter_cny
        self.max_total_budget = max_total_budget_cny
        self.soft_warning_ratio = soft_warning_ratio
        
        # 记录调用流水
        self.records: List[TokenUsageRecord] = []
        # chapter_index -> records
        self._chapter_records: Dict[int, List[TokenUsageRecord]] = defaultdict(list)

    def calculate_cost(
        self,
        model_name: str,
        input_tokens: int,
        cached_input_tokens: int,
        output_tokens: int
    ) -> Tuple[float, float]:
        """
        计算单次调用的实际成本与通过 Prompt Cache 节约的成本 (CNY)
        返回: (实际产生费用, 节省的费用)
        """
        pricing = self.pricing.get(model_name, self.pricing.get("mock", ModelPricing("mock", 0, 0, 0)))
        
        uncached_input = max(0, input_tokens - cached_input_tokens)
        cost_uncached = (uncached_input / 1_000_000.0) * pricing.price_per_1m_input
        cost_cached = (cached_input_tokens / 1_000_000.0) * pricing.price_per_1m_cached_input
        cost_output = (output_tokens / 1_000_000.0) * pricing.price_per_1m_output

        actual_cost = cost_uncached + cost_cached + cost_output

        # 估算如果没有缓存所需支付的费用
        full_price_cost = (input_tokens / 1_000_000.0) * pricing.price_per_1m_input + cost_output
        saved_cny = max(0.0, full_price_cost - actual_cost)

        return round(actual_cost, 5), round(saved_cny, 5)

    def pre_check_budget(
        self,
        chapter_index: int,
        estimated_input_tokens: int,
        estimated_output_tokens: int,
        model_name: str
    ) -> None:
        """
        前置预算安全哨兵：在发起网络调用前预判是否会穿透单章或全书预算
        """
        predicted_cost, _ = self.calculate_cost(
            model_name=model_name,
            input_tokens=estimated_input_tokens,
            cached_input_tokens=0,
            output_tokens=estimated_output_tokens
        )
        current_ch_summary = self.audit_chapter(chapter_index)
        if current_ch_summary.total_cost_cny + predicted_cost > self.max_cost_per_chapter:
            exceeded_by = (current_ch_summary.total_cost_cny + predicted_cost) - self.max_cost_per_chapter
            raise FinancialCircuitBreakerError(
                f"单章财务熔断：第 {chapter_index} 章预计将累计消耗 ¥{current_ch_summary.total_cost_cny + predicted_cost:.4f}，"
                f"超出硬上限 ¥{self.max_cost_per_chapter:.2f} (超额 ¥{exceeded_by:.4f})，已主动拦截下发！"
            )

        total_spent = sum(r.calculated_cost_cny for r in self.records)
        if total_spent + predicted_cost > self.max_total_budget:
            raise FinancialCircuitBreakerError(
                f"全书财务总预算熔断：全书累计消耗 ¥{total_spent + predicted_cost:.2f} 将超出设定总投资限额 ¥{self.max_total_budget:.2f}！"
            )

    def record_usage(
        self,
        chapter_index: int,
        beat_id: str,
        model_name: str,
        input_tokens: int,
        cached_input_tokens: int = 0,
        output_tokens: int = 0
    ) -> TokenUsageRecord:
        """
        登记真实调用开销并触发即时审计
        """
        cost_cny, _ = self.calculate_cost(
            model_name=model_name,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens
        )

        rec = TokenUsageRecord(
            chapter_index=chapter_index,
            beat_id=beat_id,
            model_name=model_name,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            calculated_cost_cny=cost_cny
        )
        self.records.append(rec)
        self._chapter_records[chapter_index].append(rec)

        # 检查是否即时超标
        ch_summary = self.audit_chapter(chapter_index)
        if ch_summary.is_budget_exceeded:
            raise FinancialCircuitBreakerError(
                f"第 {chapter_index} 章累计消耗 ¥{ch_summary.total_cost_cny:.4f} 击穿硬断路器阈值 ¥{self.max_cost_per_chapter:.2f}！"
            )

        return rec

    def audit_chapter(self, chapter_index: int) -> ChapterCostSummary:
        """审计单章成本明细与缓存效益"""
        records = self._chapter_records.get(chapter_index, [])
        if not records:
            return ChapterCostSummary(chapter_index=chapter_index)

        tot_in = sum(r.input_tokens for r in records)
        tot_cached = sum(r.cached_input_tokens for r in records)
        tot_out = sum(r.output_tokens for r in records)
        tot_cost = sum(r.calculated_cost_cny for r in records)

        hit_rate = (tot_cached / max(1, tot_in))
        saved_cny = 0.0
        for r in records:
            _, saved = self.calculate_cost(r.model_name, r.input_tokens, r.cached_input_tokens, r.output_tokens)
            saved_cny += saved

        alert = FinancialAlertLevel.NORMAL
        if tot_cost >= self.max_cost_per_chapter:
            alert = FinancialCircuitBreakerLevel = FinancialAlertLevel.CIRCUIT_TRIPPED
        elif tot_cost >= self.max_cost_per_chapter * self.soft_warning_ratio:
            alert = FinancialAlertLevel.WARNING

        return ChapterCostSummary(
            chapter_index=chapter_index,
            total_input_tokens=tot_in,
            total_cached_tokens=tot_cached,
            total_output_tokens=tot_out,
            total_cost_cny=round(tot_cost, 4),
            cache_hit_rate=round(hit_rate, 4),
            cny_saved_by_caching=round(saved_cny, 4),
            is_budget_exceeded=(tot_cost > self.max_cost_per_chapter),
            alert_level=alert
        )

    def audit_book_total(self) -> BookCostSummary:
        """审计全书累计开销与商业效益"""
        if not self.records:
            return BookCostSummary()

        chapters = len(self._chapter_records)
        tot_cost = sum(r.calculated_cost_cny for r in self.records)
        tot_tokens = sum(r.input_tokens + r.output_tokens for r in self.records)
        
        tot_saved = 0.0
        for r in self.records:
            _, s = self.calculate_cost(r.model_name, r.input_tokens, r.cached_input_tokens, r.output_tokens)
            tot_saved += s

        avg_cost = tot_cost / max(1, chapters)

        return BookCostSummary(
            total_chapters_recorded=chapters,
            total_cost_cny=round(tot_cost, 2),
            avg_cost_per_chapter=round(avg_cost, 4),
            total_tokens_consumed=tot_tokens,
            total_cny_saved_by_caching=round(tot_saved, 2)
        )
