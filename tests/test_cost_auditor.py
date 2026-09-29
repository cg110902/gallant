import pytest
from src.novel_factory.llm.cost_auditor import (
    BookCostSummary,
    ChapterCostSummary,
    CostAuditor,
    FinancialAlertLevel,
    FinancialCircuitBreakerError,
)
from src.novel_factory.llm.cost_tracker import ModelPricing


@pytest.fixture
def custom_auditor():
    pricing = {
        "test-model": ModelPricing(
            model_name="test-model",
            price_per_1m_input=2.00,          # 2元 / 1M input
            price_per_1m_cached_input=0.20,   # 0.2元 / 1M cached input (90% discount)
            price_per_1m_output=8.00          # 8元 / 1M output
        )
    }
    return CostAuditor(
        pricing_table=pricing,
        max_cost_per_chapter_cny=0.40,
        max_total_budget_cny=10.00
    )


def test_calculate_cost_with_caching_discount(custom_auditor: CostAuditor):
    """测试带 Prompt Cache 折扣的厘级成本计算"""
    # 10,000 input tokens (其中 8,000 命中缓存), 1,000 output tokens
    # uncached input: 2000 tokens = 2000 * 2.0 / 1M = 0.0040 元
    # cached input: 8000 tokens = 8000 * 0.2 / 1M = 0.0016 元
    # output: 1000 tokens = 1000 * 8.0 / 1M = 0.0080 元
    # 实际总计: 0.0040 + 0.0016 + 0.0080 = 0.0136 元
    # 如果全量未命中: 10000 * 2.0 / 1M + 0.0080 = 0.0280 元
    # 节省: 0.0280 - 0.0136 = 0.0144 元
    actual_cost, saved = custom_auditor.calculate_cost(
        model_name="test-model",
        input_tokens=10000,
        cached_input_tokens=8000,
        output_tokens=1000
    )

    assert pytest.approx(actual_cost, 0.0001) == 0.0136
    assert pytest.approx(saved, 0.0001) == 0.0144


def test_chapter_financial_circuit_breaker(custom_auditor: CostAuditor):
    """测试单章费用超标 (¥0.40) 时触发财务硬熔断"""
    # 正常消耗: 登记 0.30 元开销 (占 75%，处于 NORMAL 状态)
    # output: 37500 tokens * 8.0 / 1M = 0.30 元
    custom_auditor.record_usage(
        chapter_index=1,
        beat_id="b1",
        model_name="test-model",
        input_tokens=0,
        cached_input_tokens=0,
        output_tokens=37500
    )
    s1 = custom_auditor.audit_chapter(1)
    assert s1.alert_level == FinancialAlertLevel.NORMAL
    assert s1.is_budget_exceeded is False

    # 尝试预判：如果再发一个需要 ¥0.15 的请求，将达到 ¥0.45，超出 ¥0.40 预算 -> 前置断言熔断
    with pytest.raises(FinancialCircuitBreakerError) as exc_info:
        custom_auditor.pre_check_budget(
            chapter_index=1,
            estimated_input_tokens=0,
            estimated_output_tokens=20000,  # 20000 * 8 / 1M = 0.16元
            model_name="test-model"
        )
    assert "单章财务熔断" in str(exc_info.value)

    # 如果强行写入导致超标，也会立即抛出断路器异常
    with pytest.raises(FinancialCircuitBreakerError):
        custom_auditor.record_usage(
            chapter_index=1,
            beat_id="b2",
            model_name="test-model",
            input_tokens=0,
            output_tokens=20000
        )


def test_soft_alert_threshold(custom_auditor: CostAuditor):
    """测试达到预算 80% 时触发软预警 (WARNING)"""
    # 消耗 0.34 元 (0.34 / 0.40 = 85% >= 80% soft_warning_ratio)
    # output: 42500 tokens * 8.0 / 1M = 0.34 元
    custom_auditor.record_usage(
        chapter_index=2,
        beat_id="b1",
        model_name="test-model",
        input_tokens=0,
        output_tokens=42500
    )
    s2 = custom_auditor.audit_chapter(2)
    assert s2.alert_level == FinancialAlertLevel.WARNING
    assert s2.is_budget_exceeded is False


def test_book_total_audit(custom_auditor: CostAuditor):
    """测试全书多章聚合统计与平均每章成本核算"""
    # 第 1 章: 0.10 元
    custom_auditor.record_usage(1, "b1", "test-model", 0, 0, 12500)
    # 第 2 章: 0.10 元
    custom_auditor.record_usage(2, "b1", "test-model", 0, 0, 12500)

    summary = custom_auditor.audit_book_total()
    assert summary.total_chapters_recorded == 2
    assert pytest.approx(summary.total_cost_cny, 0.01) == 0.20
    assert pytest.approx(summary.avg_cost_per_chapter, 0.01) == 0.10
