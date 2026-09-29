"""
Tests for Resumable Production Runtime - 断点续产运行时

长篇生产是数小时到数天的长事务，崩溃恢复能力是生产可用性的前提。
"""

import json
from pathlib import Path

import pytest

from src.novel_factory.llm.cost_auditor import FinancialCircuitBreakerError
from src.novel_factory.runtime.resume import (
    ChapterJobState,
    JobStatus,
    ProductionJournal,
    ResumableProducer,
)


class _FakeCommit:
    def __init__(self, ch):
        self.commit_id = f"sha_{ch}"
        self.word_count = 2000
        self.chapter_index = ch


class _FakeCostSummary:
    total_cost_cny = 0.12


class _FakeResult:
    def __init__(self, ch, qc_passed=True, blockers=None):
        self.commit = _FakeCommit(ch)
        self.cost_summary = _FakeCostSummary()
        self.qc_passed = qc_passed
        self.blockers = blockers or []


class _FakeOrchestrator:
    """可编程失败行为的假编排器"""

    def __init__(self, fail_on=None, raise_times=0, qc_fail_on=None, budget_on=None):
        self.fail_on = set(fail_on or [])
        self.qc_fail_on = set(qc_fail_on or [])
        self.budget_on = set(budget_on or [])
        self.raise_times = raise_times
        self.calls = []
        self._transient_count = {}

    def produce_chapter(self, chapter_index, **kwargs):
        self.calls.append(chapter_index)
        if chapter_index in self.budget_on:
            raise FinancialCircuitBreakerError(f"第 {chapter_index} 章预算击穿")
        if chapter_index in self.fail_on:
            n = self._transient_count.get(chapter_index, 0)
            if n < self.raise_times:
                self._transient_count[chapter_index] = n + 1
                raise RuntimeError("模拟 API 限流")
        return _FakeResult(chapter_index, qc_passed=chapter_index not in self.qc_fail_on)


def _plan(ch):
    return {"title": f"第{ch}章", "beat_contracts": [], "lore_entries": [], "state_delta": None}


# ---------- 日志持久化 ----------

def test_journal_roundtrip(tmp_path: Path):
    jp = tmp_path / "j.json"
    j = ProductionJournal(jp)
    j.mark(1, status=JobStatus.COMPLETED, word_count=2000, cost_cny=0.1)
    j.mark(2, status=JobStatus.FAILED, error="boom")

    reloaded = ProductionJournal(jp)
    assert reloaded.get(1).status == JobStatus.COMPLETED
    assert reloaded.get(1).word_count == 2000
    assert reloaded.get(2).error == "boom"


def test_journal_is_human_readable(tmp_path: Path):
    """日志必须是人类可读可手改的 JSON，便于人工介入"""
    jp = tmp_path / "j.json"
    j = ProductionJournal(jp)
    j.mark(1, status=JobStatus.COMPLETED)
    data = json.loads(jp.read_text(encoding="utf-8"))
    assert data["jobs"]["1"]["status"] == "COMPLETED"
    assert "updated_at" in data["metadata"]


def test_corrupt_journal_does_not_crash(tmp_path: Path):
    jp = tmp_path / "j.json"
    jp.write_text("{ this is not json", encoding="utf-8")
    j = ProductionJournal(jp)
    assert j.jobs == {}


# ---------- 断点续产 ----------

def test_resume_skips_completed_chapters(tmp_path: Path):
    """核心能力：重启后从第一个未完成章节继续，不重复烧钱"""
    jp = tmp_path / "j.json"
    j = ProductionJournal(jp)
    for ch in (1, 2, 3):
        j.mark(ch, status=JobStatus.COMPLETED)

    orch = _FakeOrchestrator()
    producer = ResumableProducer(orch, journal_path=jp)
    assert producer.resume_point([1, 2, 3, 4, 5]) == 4

    producer.run([1, 2, 3, 4, 5], _plan)
    assert orch.calls == [4, 5]  # 1~3 被跳过


def test_run_is_idempotent(tmp_path: Path):
    jp = tmp_path / "j.json"
    orch = _FakeOrchestrator()
    producer = ResumableProducer(orch, journal_path=jp)

    producer.run([1, 2, 3], _plan)
    assert orch.calls == [1, 2, 3]
    producer.run([1, 2, 3], _plan)   # 第二次应全部跳过
    assert orch.calls == [1, 2, 3]


def test_transient_failure_is_retried(tmp_path: Path):
    """网络/限流等瞬时故障应自动退避重试"""
    orch = _FakeOrchestrator(fail_on=[2], raise_times=2)
    producer = ResumableProducer(
        orch, journal_path=tmp_path / "j.json",
        max_attempts_per_chapter=3, retry_backoff_seconds=0,
    )
    summary = producer.run([1, 2, 3], _plan)
    assert summary.completed == 3
    assert orch.calls.count(2) == 3


def test_permanent_failure_is_recorded(tmp_path: Path):
    orch = _FakeOrchestrator(fail_on=[2], raise_times=99)
    producer = ResumableProducer(
        orch, journal_path=tmp_path / "j.json",
        max_attempts_per_chapter=2, retry_backoff_seconds=0,
    )
    summary = producer.run([1, 2, 3], _plan)
    assert summary.failed == 1
    assert producer.journal.get(2).status == JobStatus.FAILED
    assert "模拟 API 限流" in producer.journal.get(2).error


def test_qc_rejection_is_distinct_from_failure(tmp_path: Path):
    """质检驳回不是系统故障，必须区分统计"""
    orch = _FakeOrchestrator(qc_fail_on=[2])
    producer = ResumableProducer(orch, journal_path=tmp_path / "j.json")
    summary = producer.run([1, 2, 3], _plan)
    assert summary.qc_rejected == 1
    assert summary.failed == 0
    assert producer.journal.get(2).status == JobStatus.QC_REJECTED


def test_financial_breaker_suspends_the_run(tmp_path: Path):
    """预算熔断必须挂起而非继续烧钱"""
    orch = _FakeOrchestrator(budget_on=[3])
    producer = ResumableProducer(
        orch, journal_path=tmp_path / "j.json", retry_backoff_seconds=0
    )
    summary = producer.run([1, 2, 3, 4, 5], _plan)

    assert producer.journal.get(3).status == JobStatus.SUSPENDED
    assert summary.suspended == 1
    assert 4 not in orch.calls and 5 not in orch.calls  # 熔断后不再继续


def test_suspended_chapter_requires_manual_reset(tmp_path: Path):
    """挂起是人类决策点，不得被自动绕过"""
    jp = tmp_path / "j.json"
    orch = _FakeOrchestrator(budget_on=[2])
    producer = ResumableProducer(orch, journal_path=jp, retry_backoff_seconds=0)
    producer.run([1, 2, 3], _plan)

    orch.calls.clear()
    orch.budget_on = set()
    producer.run([1, 2, 3], _plan)
    assert orch.calls == []  # 仍然挂起，不自动继续

    producer.journal.reset_chapter(2)
    producer.run([1, 2, 3], _plan)
    assert orch.calls == [2, 3]


def test_stop_after_limits_batch_size(tmp_path: Path):
    orch = _FakeOrchestrator()
    producer = ResumableProducer(orch, journal_path=tmp_path / "j.json")
    producer.run([1, 2, 3, 4, 5], _plan, stop_after=2)
    assert orch.calls == [1, 2]


def test_summary_aggregates_cost_and_words(tmp_path: Path):
    orch = _FakeOrchestrator()
    producer = ResumableProducer(orch, journal_path=tmp_path / "j.json")
    summary = producer.run([1, 2, 3], _plan)
    assert summary.completed == 3
    assert summary.total_words == 6000
    assert summary.total_cost_cny == pytest.approx(0.36)
    assert "批次生产摘要" in summary.format_summary()


def test_progress_callback_is_invoked(tmp_path: Path):
    seen = []
    orch = _FakeOrchestrator()
    producer = ResumableProducer(
        orch, journal_path=tmp_path / "j.json",
        progress_callback=lambda ch, job: seen.append((ch, job.status)),
    )
    producer.run([1, 2], _plan)
    assert [c for c, _ in seen] == [1, 2]
    assert all(st == JobStatus.COMPLETED for _, st in seen)
