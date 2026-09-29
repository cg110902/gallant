"""
Thread Scheduler - 多线叙事调度器与支线断更预警

长篇一旦铺开多条线（主线复仇 / 感情线 / 势力经营 / 宿敌线 / 悬疑线），
最常见的失控是：
  某条线写嗨了连写二十章，另一条线断更八十章，读者早已忘光；
  配角 POV 占比失衡，主角连续多章不出场；
  卷末要收束的线，到卷末才发现有三条根本没铺到位。

本模块把每条故事线当作需要被调度的「进程」来管理：
优先级、时间片（章数配额）、饥饿检测（断更预警）、卷末收束就绪度检查。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple


class ThreadPriority(str, Enum):
    MAIN = "MAIN"              # 主线：必须高频推进
    SECONDARY = "SECONDARY"    # 重要支线
    ROMANCE = "ROMANCE"        # 感情线
    BACKGROUND = "BACKGROUND"  # 背景/世界观线
    COMEDY_RELIEF = "COMEDY_RELIEF"  # 调剂线


class ThreadStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"        # 有意休眠
    STARVED = "STARVED"        # 意外断更（饥饿）
    CLOSED = "CLOSED"


# 各优先级的默认最长断更容忍章数
DEFAULT_MAX_GAP: Dict[ThreadPriority, int] = {
    ThreadPriority.MAIN: 3,
    ThreadPriority.SECONDARY: 15,
    ThreadPriority.ROMANCE: 20,
    ThreadPriority.BACKGROUND: 40,
    ThreadPriority.COMEDY_RELIEF: 25,
}

# 各优先级的目标章数占比
DEFAULT_QUOTA: Dict[ThreadPriority, float] = {
    ThreadPriority.MAIN: 0.55,
    ThreadPriority.SECONDARY: 0.20,
    ThreadPriority.ROMANCE: 0.12,
    ThreadPriority.BACKGROUND: 0.08,
    ThreadPriority.COMEDY_RELIEF: 0.05,
}


@dataclass
class StoryThread:
    thread_id: str
    title: str
    priority: ThreadPriority = ThreadPriority.SECONDARY
    status: ThreadStatus = ThreadStatus.ACTIVE
    introduced_chapter: int = 1
    last_advanced_chapter: int = 1
    advance_count: int = 0
    max_gap_chapters: Optional[int] = None
    must_close_by_chapter: Optional[int] = None
    pov_entity_id: Optional[str] = None
    summary: str = ""

    @property
    def effective_max_gap(self) -> int:
        return self.max_gap_chapters or DEFAULT_MAX_GAP[self.priority]


@dataclass
class ThreadScheduleReport:
    chapter_index: int
    passed: bool = True
    starved: List[Tuple[StoryThread, int]] = field(default_factory=list)
    due_to_close: List[StoryThread] = field(default_factory=list)
    quota_deviations: Dict[str, float] = field(default_factory=dict)
    pov_distribution: Dict[str, int] = field(default_factory=dict)
    directives: List[str] = field(default_factory=list)
    alerts: List[str] = field(default_factory=list)

    def format_summary(self) -> str:
        lines = [
            f"[多线调度] 第{self.chapter_index}章 {'OK' if self.passed else 'ALERT'}"
        ]
        for t, gap in self.starved:
            lines.append(
                f"  - [断更] 「{t.title}」({t.priority.value}) 已 {gap} 章未推进，"
                f"容忍上限 {t.effective_max_gap} 章"
            )
        for t in self.due_to_close:
            lines.append(
                f"  - [待收束] 「{t.title}」承诺在第 {t.must_close_by_chapter} 章前收束，尚未关闭"
            )
        for a in self.alerts:
            lines.append(f"  - {a}")
        return "\n".join(lines)


class ThreadScheduler:
    """多线叙事调度器"""

    def __init__(self, quota_tolerance: float = 0.15):
        self.threads: Dict[str, StoryThread] = {}
        # chapter_index -> [thread_id]
        self.chapter_allocation: Dict[int, List[str]] = {}
        self.quota_tolerance = quota_tolerance

    # ---------- 注册与推进 ----------

    def register_thread(self, thread: StoryThread) -> None:
        self.threads[thread.thread_id] = thread

    def advance(self, thread_id: str, chapter_index: int) -> bool:
        """登记某章推进了某条线"""
        t = self.threads.get(thread_id)
        if not t:
            return False
        t.last_advanced_chapter = chapter_index
        t.advance_count += 1
        if t.status == ThreadStatus.STARVED:
            t.status = ThreadStatus.ACTIVE
        self.chapter_allocation.setdefault(chapter_index, [])
        if thread_id not in self.chapter_allocation[chapter_index]:
            self.chapter_allocation[chapter_index].append(thread_id)
        return True

    def close_thread(self, thread_id: str, chapter_index: int) -> bool:
        t = self.threads.get(thread_id)
        if not t:
            return False
        t.status = ThreadStatus.CLOSED
        t.last_advanced_chapter = chapter_index
        return True

    def set_dormant(self, thread_id: str) -> bool:
        """显式休眠：有意的长期不提，不计入断更告警"""
        t = self.threads.get(thread_id)
        if not t:
            return False
        t.status = ThreadStatus.DORMANT
        return True

    # ---------- 检查 ----------

    def check(self, chapter_index: int, close_warning_window: int = 10) -> ThreadScheduleReport:
        report = ThreadScheduleReport(chapter_index=chapter_index)

        for t in self.threads.values():
            if t.status in (ThreadStatus.CLOSED, ThreadStatus.DORMANT):
                continue
            if t.introduced_chapter > chapter_index:
                continue
            gap = chapter_index - t.last_advanced_chapter
            if gap > t.effective_max_gap:
                t.status = ThreadStatus.STARVED
                report.starved.append((t, gap))
                report.directives.append(
                    f"【支线续更】「{t.title}」已断更 {gap} 章，读者记忆正在流失。"
                    f"本章需以至少一个场景推进该线，或通过角色对话/信件/回忆自然带出其最新进展。"
                )
            if (
                t.must_close_by_chapter is not None
                and t.must_close_by_chapter - chapter_index <= close_warning_window
            ):
                report.due_to_close.append(t)
                report.directives.append(
                    f"【收束倒计时】「{t.title}」须在第 {t.must_close_by_chapter} 章前收束，"
                    f"仅剩 {t.must_close_by_chapter - chapter_index} 章，请加速推进其结局。"
                )

        # 配额偏离分析
        total_slots = sum(len(v) for v in self.chapter_allocation.values())
        if total_slots > 0:
            by_priority: Dict[ThreadPriority, int] = {}
            for tids in self.chapter_allocation.values():
                for tid in tids:
                    t = self.threads.get(tid)
                    if t:
                        by_priority[t.priority] = by_priority.get(t.priority, 0) + 1
            for prio, target in DEFAULT_QUOTA.items():
                actual = by_priority.get(prio, 0) / total_slots
                dev = round(actual - target, 3)
                report.quota_deviations[prio.value] = dev
                if prio == ThreadPriority.MAIN and actual < target - self.quota_tolerance:
                    report.alerts.append(
                        f"主线占比过低：主线仅占 {actual:.0%}（目标 {target:.0%}），"
                        f"读者会觉得「跑题了」，请压缩支线篇幅。"
                    )
                elif actual > target + self.quota_tolerance * 2 and prio != ThreadPriority.MAIN:
                    report.alerts.append(
                        f"{prio.value} 线占比 {actual:.0%} 显著超出目标 {target:.0%}，"
                        f"正在挤占主线推进空间。"
                    )

        # POV 分布
        for tids in self.chapter_allocation.values():
            for tid in tids:
                t = self.threads.get(tid)
                if t and t.pov_entity_id:
                    report.pov_distribution[t.pov_entity_id] = (
                        report.pov_distribution.get(t.pov_entity_id, 0) + 1
                    )

        report.passed = not report.starved and not report.alerts
        return report

    def suggest_threads_for_chapter(
        self, chapter_index: int, slots: int = 2
    ) -> List[StoryThread]:
        """
        为下一章推荐应当推进的线：
        按 (饥饿程度 × 优先级权重) 排序，主线始终优先保底。
        """
        prio_weight = {
            ThreadPriority.MAIN: 3.0,
            ThreadPriority.SECONDARY: 1.6,
            ThreadPriority.ROMANCE: 1.3,
            ThreadPriority.BACKGROUND: 0.8,
            ThreadPriority.COMEDY_RELIEF: 0.6,
        }
        candidates = [
            t for t in self.threads.values()
            if t.status in (ThreadStatus.ACTIVE, ThreadStatus.STARVED)
            and t.introduced_chapter <= chapter_index
        ]

        def urgency(t: StoryThread) -> float:
            gap = chapter_index - t.last_advanced_chapter
            base = (gap / max(1, t.effective_max_gap)) * prio_weight[t.priority]
            if t.must_close_by_chapter:
                remaining = max(1, t.must_close_by_chapter - chapter_index)
                base += 10.0 / remaining
            return base

        return sorted(candidates, key=urgency, reverse=True)[:slots]

    def render_gantt(self, from_chapter: int, to_chapter: int) -> str:
        """渲染多线推进甘特图，终端巡检用"""
        if not self.threads:
            return "(暂无故事线)"
        rows = []
        span = range(from_chapter, to_chapter + 1)
        for t in self.threads.values():
            cells = "".join(
                "█" if t.thread_id in self.chapter_allocation.get(c, []) else "·"
                for c in span
            )
            rows.append(f"{t.title[:10]:<12}|{cells}")
        rows.append(f"{'':<12} 第{from_chapter}章 → 第{to_chapter}章")
        return "\n".join(rows)
