"""
生产安全性测试：并发写锁与财务熔断

这两类故障的共同点是【静默】：
- 并发写同一部作品，章节会从版本链上脱落而不报任何错；
- 全书总预算形同虚设，限额 ¥0.01 也能一路花到 ¥156。
静默的资损和丢稿，比直接崩溃危险得多。
"""

import pytest

from src.novel_factory.core.db import ConcurrentProductionError, ProductionLock
from src.novel_factory.llm.cost_auditor import CostAuditor, FinancialCircuitBreakerError
from src.novel_factory.orchestrator import NovelFactoryOrchestrator
from src.novel_factory.schemas.commit import StateDelta


# ==================== 财务熔断 ====================

def test_book_budget_breaker_actually_trips():
    """此前只有 pre_check 检查总预算，真实入账走 record_usage，于是总限额失效"""
    auditor = CostAuditor(max_cost_per_chapter_cny=1000.0, max_total_budget_cny=0.5)

    with pytest.raises(FinancialCircuitBreakerError) as exc:
        for ch in range(1, 50):
            auditor.record_usage(
                chapter_index=ch, beat_id="b", model_name="gemini-3.1-pro-preview",
                input_tokens=200_000, cached_input_tokens=0, output_tokens=50_000,
            )
    assert "全书财务总预算熔断" in str(exc.value)
    assert auditor.audit_book_total().total_cost_cny <= 5.0, "熔断后不得继续大额消耗"


def test_chapter_budget_breaker_still_works():
    auditor = CostAuditor(max_cost_per_chapter_cny=0.01, max_total_budget_cny=1000.0)
    with pytest.raises(FinancialCircuitBreakerError) as exc:
        auditor.record_usage(1, "b", "gemini-3.1-pro-preview", 200_000, 0, 50_000)
    assert "单章" in str(exc.value) or "击穿硬断路器" in str(exc.value)


def test_budget_within_limits_does_not_trip():
    auditor = CostAuditor(max_cost_per_chapter_cny=1.0, max_total_budget_cny=10.0)
    for ch in range(1, 6):
        auditor.record_usage(ch, "b", "gemini-3.8-flash", 2000, 1000, 800)
    assert auditor.audit_book_total().total_cost_cny > 0


# ==================== 并发写锁 ====================

def test_second_writer_is_refused(tmp_path):
    db = str(tmp_path / "book.db")
    o1 = NovelFactoryOrchestrator(
        db_path=db, llm_worker=lambda s, u: "x", acquire_write_lock=True
    )
    try:
        with pytest.raises(ConcurrentProductionError) as exc:
            ProductionLock(o1.repo.conn, owner="另一台机器").acquire()
        assert "并发写入" in str(exc.value)
    finally:
        o1.close()


def test_lock_is_released_on_close(tmp_path):
    db = str(tmp_path / "book.db")
    o1 = NovelFactoryOrchestrator(
        db_path=db, llm_worker=lambda s, u: "x", acquire_write_lock=True
    )
    o1.close()

    o2 = NovelFactoryOrchestrator(
        db_path=db, llm_worker=lambda s, u: "x", acquire_write_lock=True
    )
    assert o2.production_lock.held is True
    o2.close()


def test_stale_lock_can_be_taken_over(tmp_path):
    import sqlite3
    import time

    db = str(tmp_path / "book.db")
    o1 = NovelFactoryOrchestrator(
        db_path=db, llm_worker=lambda s, u: "x", acquire_write_lock=True
    )
    # 伪造一个来自已死进程的陈旧心跳
    with o1.repo.conn:
        o1.repo.conn.execute(
            "UPDATE production_lock SET heartbeat_at = ?, pid = ?",
            (time.time() - 10_000, 999_999),
        )
    lock = ProductionLock(o1.repo.conn, owner="接管者", stale_after_seconds=60)
    assert lock.acquire() is True
    o1.close()


def test_force_flag_overrides_live_lock(tmp_path):
    db = str(tmp_path / "book.db")
    o1 = NovelFactoryOrchestrator(
        db_path=db, llm_worker=lambda s, u: "x", acquire_write_lock=True
    )
    try:
        lock = ProductionLock(o1.repo.conn, owner="强行接管")
        assert lock.acquire(force=True) is True
    finally:
        o1.close()


def test_memory_db_does_not_take_lock():
    """内存库天然进程隔离，不需要也不应该加锁"""
    o = NovelFactoryOrchestrator(
        db_path=":memory:", llm_worker=lambda s, u: "x", acquire_write_lock=True
    )
    assert o.production_lock is None
    o.close()


def test_heartbeat_keeps_lock_fresh(tmp_path):
    db = str(tmp_path / "book.db")
    o = NovelFactoryOrchestrator(
        db_path=db, llm_worker=lambda s, u: "x", acquire_write_lock=True
    )
    before = o.repo.conn.execute(
        "SELECT heartbeat_at FROM production_lock WHERE lock_id='writer'"
    ).fetchone()[0]
    with o.repo.conn:
        o.repo.conn.execute(
            "UPDATE production_lock SET heartbeat_at = ?", (before - 100,)
        )
    o.production_lock.heartbeat()
    after = o.repo.conn.execute(
        "SELECT heartbeat_at FROM production_lock WHERE lock_id='writer'"
    ).fetchone()[0]
    assert after > before - 100
    o.close()


def test_lock_is_opt_in(tmp_path):
    """默认不加锁，避免读取类操作互相阻塞"""
    db = str(tmp_path / "book.db")
    o = NovelFactoryOrchestrator(db_path=db, llm_worker=lambda s, u: "x")
    assert o.production_lock is None
    o.close()
