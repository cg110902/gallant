"""
Production Runtime Layer - 生产运行时层

长篇生产是一个跑数小时到数天的长事务。进程会崩、API 会限流、预算会耗尽、
人类作者会在半夜叫停。没有断点续产能力的流水线，在真实生产中是不可用的。

本层提供：
- ProductionJournal: 生产日志与断点快照（崩溃后从最后一个完好章节继续）
- ResumableProducer: 可恢复的批量章节生产驱动器（含重试、限流退避与 HITL 挂起）
"""

from .resume import (
    ChapterJobState,
    JobStatus,
    ProductionJournal,
    ProductionRunSummary,
    ResumableProducer,
)

__all__ = [
    "ChapterJobState",
    "JobStatus",
    "ProductionJournal",
    "ProductionRunSummary",
    "ResumableProducer",
]
