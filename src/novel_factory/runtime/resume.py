"""
Resumable Production Runtime - 断点续产运行时

真实的长篇生产会持续数小时至数天，中途必然遇到：
  进程被杀 / API 限流 / 预算熔断 / 质检连续失败 / 人类作者喊停。

本模块把「生产 N 章」建模为一个可持久化、可恢复、可人工介入的长事务：
1. ProductionJournal —— 以 JSON 日志落盘每章的生产状态与失败原因；
2. 幂等恢复 —— 重启后自动跳过已完成章节，从第一个未完成章节续跑；
3. 指数退避重试 —— 对瞬时故障（网络/限流）自动重试；
4. HITL 挂起 —— 连续质检失败或财务熔断时挂起并写入断点，等待人工决策；
5. 运行摘要 —— 产出可审计的批次报告（成功/失败/跳过/成本/耗时）。
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
import json
from pathlib import Path
import time
import traceback
from typing import Any, Callable, Dict, List, Optional, Sequence

from src.novel_factory.llm.cost_auditor import FinancialCircuitBreakerError


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    QC_REJECTED = "QC_REJECTED"      # 生产完成但质检未放行
    SUSPENDED = "SUSPENDED"          # 挂起等待人工决策
    SKIPPED = "SKIPPED"


@dataclass
class ChapterJobState:
    chapter_index: int
    status: JobStatus = JobStatus.PENDING
    attempts: int = 0
    commit_id: Optional[str] = None
    word_count: int = 0
    cost_cny: float = 0.0
    blockers: List[str] = field(default_factory=list)
    error: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ChapterJobState":
        d = dict(d)
        d["status"] = JobStatus(d.get("status", "PENDING"))
        return cls(**d)


@dataclass
class ProductionRunSummary:
    total: int = 0
    completed: int = 0
    failed: int = 0
    qc_rejected: int = 0
    suspended: int = 0
    skipped: int = 0
    total_cost_cny: float = 0.0
    total_words: int = 0
    elapsed_seconds: float = 0.0

    def format_summary(self) -> str:
        return (
            f"===== 批次生产摘要 =====\n"
            f"计划章节: {self.total} | 成功: {self.completed} | 质检驳回: {self.qc_rejected} | "
            f"失败: {self.failed} | 挂起: {self.suspended} | 跳过: {self.skipped}\n"
            f"总字数: {self.total_words:,} | 总成本: ¥{self.total_cost_cny:.4f} | "
            f"耗时: {self.elapsed_seconds:.1f}s"
        )


class ProductionJournal:
    """生产日志与断点快照（JSON 落盘，人类可读可手改）"""

    def __init__(self, journal_path: Optional[Path] = None):
        self.path = Path(journal_path or ".production_journal.json")
        self.jobs: Dict[int, ChapterJobState] = {}
        self.metadata: Dict[str, Any] = {}
        if self.path.exists():
            self.load()

    def load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        self.metadata = data.get("metadata", {})
        self.jobs = {
            int(k): ChapterJobState.from_dict(v)
            for k, v in data.get("jobs", {}).items()
        }

    def save(self) -> None:
        payload = {
            "metadata": {**self.metadata, "updated_at": datetime.now().isoformat(timespec="seconds")},
            "jobs": {str(k): v.to_dict() for k, v in sorted(self.jobs.items())},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def get(self, chapter_index: int) -> ChapterJobState:
        if chapter_index not in self.jobs:
            self.jobs[chapter_index] = ChapterJobState(chapter_index=chapter_index)
        return self.jobs[chapter_index]

    def mark(self, chapter_index: int, **updates: Any) -> ChapterJobState:
        job = self.get(chapter_index)
        for k, v in updates.items():
            setattr(job, k, v)
        self.save()
        return job

    def is_done(self, chapter_index: int) -> bool:
        return self.get(chapter_index).status == JobStatus.COMPLETED

    def next_pending_chapter(self, planned: Sequence[int]) -> Optional[int]:
        """返回第一个尚未完成的章节号（断点续产入口）"""
        for c in planned:
            if not self.is_done(c):
                return c
        return None

    def reset_chapter(self, chapter_index: int) -> None:
        """重置某章状态以便重跑（人工介入后使用）"""
        self.jobs[chapter_index] = ChapterJobState(chapter_index=chapter_index)
        self.save()

    def summary(self) -> ProductionRunSummary:
        s = ProductionRunSummary(total=len(self.jobs))
        for j in self.jobs.values():
            if j.status == JobStatus.COMPLETED:
                s.completed += 1
            elif j.status == JobStatus.FAILED:
                s.failed += 1
            elif j.status == JobStatus.QC_REJECTED:
                s.qc_rejected += 1
            elif j.status == JobStatus.SUSPENDED:
                s.suspended += 1
            elif j.status == JobStatus.SKIPPED:
                s.skipped += 1
            s.total_cost_cny += j.cost_cny
            s.total_words += j.word_count
        return s


class ResumableProducer:
    """
    可恢复的批量章节生产驱动器。

    使用方式：
        producer = ResumableProducer(orchestrator, journal_path="run.json")
        summary = producer.run(
            chapter_indices=range(1, 101),
            plan_provider=my_plan_fn,     # 章号 -> 生产参数
        )
    中断后以完全相同的参数再次调用 run()，即可从断点继续。
    """

    def __init__(
        self,
        orchestrator: Any,
        journal_path: Optional[Path] = None,
        max_attempts_per_chapter: int = 3,
        retry_backoff_seconds: float = 2.0,
        suspend_on_qc_failure: bool = False,
        stop_on_financial_breaker: bool = True,
        progress_callback: Optional[Callable[[int, ChapterJobState], None]] = None,
    ):
        self.orch = orchestrator
        self.journal = ProductionJournal(journal_path)
        self.max_attempts = max_attempts_per_chapter
        self.backoff = retry_backoff_seconds
        self.suspend_on_qc_failure = suspend_on_qc_failure
        self.stop_on_financial_breaker = stop_on_financial_breaker
        self.progress_callback = progress_callback

    def run(
        self,
        chapter_indices: Sequence[int],
        plan_provider: Callable[[int], Dict[str, Any]],
        stop_after: Optional[int] = None,
    ) -> ProductionRunSummary:
        """
        批量生产章节。

        plan_provider(chapter_index) 须返回 produce_chapter 所需的 kwargs：
            {"title": ..., "beat_contracts": [...], "lore_entries": [...], "state_delta": ...}
        """
        started = time.time()
        produced_this_run = 0
        planned = list(chapter_indices)
        self.journal.metadata.setdefault("planned_range", [planned[0], planned[-1]] if planned else [])

        for ch in planned:
            job = self.journal.get(ch)

            if job.status == JobStatus.COMPLETED:
                continue
            if job.status == JobStatus.SUSPENDED:
                # 挂起的章节需要人工 reset 后才继续，避免自动绕过人类决策
                break

            if stop_after is not None and produced_this_run >= stop_after:
                break

            self.journal.mark(
                ch, status=JobStatus.RUNNING,
                started_at=datetime.now().isoformat(timespec="seconds")
            )

            success = False
            last_error = ""
            for attempt in range(1, self.max_attempts + 1):
                job.attempts = attempt
                try:
                    plan = plan_provider(ch)
                    result = self.orch.produce_chapter(chapter_index=ch, **plan)
                    qc_ok = getattr(result, "qc_passed", True)
                    self.journal.mark(
                        ch,
                        status=JobStatus.COMPLETED if qc_ok else JobStatus.QC_REJECTED,
                        commit_id=result.commit.commit_id,
                        word_count=result.commit.word_count,
                        cost_cny=(result.cost_summary.total_cost_cny if result.cost_summary else 0.0),
                        blockers=list(getattr(result, "blockers", [])),
                        error="",
                        finished_at=datetime.now().isoformat(timespec="seconds"),
                    )
                    success = True
                    produced_this_run += 1
                    break

                except FinancialCircuitBreakerError as e:
                    last_error = f"财务熔断: {e}"
                    self.journal.mark(
                        ch, status=JobStatus.SUSPENDED, error=last_error,
                        finished_at=datetime.now().isoformat(timespec="seconds")
                    )
                    if self.stop_on_financial_breaker:
                        break
                except Exception as e:  # 瞬时故障：网络、限流、模型异常
                    last_error = f"{type(e).__name__}: {e}"
                    if attempt < self.max_attempts:
                        time.sleep(self.backoff * (2 ** (attempt - 1)))
                        continue
                    self.journal.mark(
                        ch, status=JobStatus.FAILED, error=last_error,
                        finished_at=datetime.now().isoformat(timespec="seconds")
                    )

            current = self.journal.get(ch)
            if self.progress_callback:
                self.progress_callback(ch, current)

            if current.status == JobStatus.SUSPENDED:
                break
            if (
                not success
                and self.suspend_on_qc_failure
                and current.status in (JobStatus.FAILED, JobStatus.QC_REJECTED)
            ):
                self.journal.mark(ch, status=JobStatus.SUSPENDED)
                break

        summary = self.journal.summary()
        summary.elapsed_seconds = round(time.time() - started, 2)
        return summary

    def resume_point(self, chapter_indices: Sequence[int]) -> Optional[int]:
        """查询下次将从哪一章继续"""
        return self.journal.next_pending_chapter(list(chapter_indices))
