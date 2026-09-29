"""
Payoff Density Meter - 爽点密度曲线与情绪配比引擎

网文的本质是情绪过山车。两种典型死法：
  「憋太久」—— 连续二十章主角被压制、被误解、被羞辱，读者弃书；
  「爽麻了」—— 一路平推无阻力，爽点边际效用归零，同样弃书。

本模块把每章编码为一个情绪节拍（憋屈值 / 爆发值），
绘制全书爽点密度曲线，并给出硬性调度建议：
何时必须给一个爆发，何时应该继续压制蓄力。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.novel_factory.schemas.beat import PacingType


class EmotionValence(str, Enum):
    SUPPRESSION = "SUPPRESSION"    # 憋屈/压制/受挫
    TENSION = "TENSION"            # 紧张/危机（中性偏负）
    NEUTRAL = "NEUTRAL"            # 过渡/日常/信息铺陈
    PAYOFF = "PAYOFF"              # 爽点爆发/打脸/翻盘
    TRIUMPH = "TRIUMPH"            # 大高潮/卷终狂欢


# 各情绪的数值编码：负为憋，正为爽
VALENCE_SCORE: Dict[EmotionValence, float] = {
    EmotionValence.SUPPRESSION: -2.0,
    EmotionValence.TENSION: -0.5,
    EmotionValence.NEUTRAL: 0.0,
    EmotionValence.PAYOFF: 2.5,
    EmotionValence.TRIUMPH: 4.0,
}

# 由节拍类型推导默认情绪
PACING_TO_VALENCE: Dict[PacingType, EmotionValence] = {
    PacingType.BUILD_UP: EmotionValence.SUPPRESSION,
    PacingType.COGNITIVE_GAP: EmotionValence.TENSION,
    PacingType.CATHARSIS_PAYOFF: EmotionValence.PAYOFF,
    PacingType.CLIFFHANGER_HOOK: EmotionValence.TENSION,
}

# 爽点的语言学特征探针
PAYOFF_SIGNATURES: List[str] = [
    "打脸", "跪下", "认输", "不敢相信", "倒吸一口凉气", "全场寂静", "哗然",
    "跪地求饶", "反杀", "碾压", "一击", "秒杀", "震惊", "刮目相看",
    "原来他才是", "身份曝光", "当众", "扬眉吐气", "狠狠",
]
SUPPRESSION_SIGNATURES: List[str] = [
    "羞辱", "冷笑着离开", "无能为力", "咬牙忍下", "被赶出", "废物", "嘲讽",
    "跪在地上", "吐血", "重伤", "无人相信", "孤立无援", "绝望", "屈辱",
]


@dataclass
class ChapterEmotionBeat:
    chapter_index: int
    valence: EmotionValence
    intensity: float = 1.0        # 强度系数
    detected_payoff_hits: int = 0
    detected_suppression_hits: int = 0
    note: str = ""

    @property
    def score(self) -> float:
        return VALENCE_SCORE[self.valence] * self.intensity


@dataclass
class DensityReport:
    chapter_index: int
    passed: bool = True
    rolling_score: float = 0.0
    chapters_since_last_payoff: int = 0
    suppression_streak: int = 0
    payoff_streak: int = 0
    alerts: List[str] = field(default_factory=list)
    directives: List[str] = field(default_factory=list)

    def format_summary(self) -> str:
        lines = [
            f"[爽点密度] 第{self.chapter_index}章 {'OK' if self.passed else 'ALERT'} | "
            f"滚动情绪值 {self.rolling_score:+.1f} | "
            f"距上次爆发 {self.chapters_since_last_payoff} 章"
        ]
        for a in self.alerts:
            lines.append(f"  - {a}")
        return "\n".join(lines)


class PayoffDensityMeter:
    """爽点密度曲线引擎"""

    def __init__(
        self,
        max_suppression_streak: int = 5,
        max_chapters_without_payoff: int = 8,
        max_payoff_streak: int = 4,
        rolling_window: int = 10,
        min_rolling_score: float = -6.0,
    ):
        self.max_suppression_streak = max_suppression_streak
        self.max_chapters_without_payoff = max_chapters_without_payoff
        self.max_payoff_streak = max_payoff_streak
        self.rolling_window = rolling_window
        self.min_rolling_score = min_rolling_score
        self.beats: Dict[int, ChapterEmotionBeat] = {}

    # ---------- 录入 ----------

    def classify_text(self, text: str) -> Tuple[EmotionValence, int, int]:
        """从正文自动判定章节情绪极性"""
        pay = sum(1 for s in PAYOFF_SIGNATURES if s in text)
        sup = sum(1 for s in SUPPRESSION_SIGNATURES if s in text)
        if pay == 0 and sup == 0:
            return EmotionValence.NEUTRAL, pay, sup
        if pay >= sup * 2 and pay >= 3:
            return EmotionValence.TRIUMPH, pay, sup
        if pay > sup:
            return EmotionValence.PAYOFF, pay, sup
        if sup > pay * 2:
            return EmotionValence.SUPPRESSION, pay, sup
        return EmotionValence.TENSION, pay, sup

    def record_chapter(
        self,
        chapter_index: int,
        text: Optional[str] = None,
        valence: Optional[EmotionValence] = None,
        pacing_type: Optional[PacingType] = None,
        intensity: float = 1.0,
        note: str = "",
    ) -> ChapterEmotionBeat:
        """
        登记一章的情绪节拍。
        优先级：显式 valence > 正文自动判定 > 节拍类型推导。
        """
        pay_hits = sup_hits = 0
        if valence is None:
            if text:
                valence, pay_hits, sup_hits = self.classify_text(text)
            elif pacing_type is not None:
                valence = PACING_TO_VALENCE.get(pacing_type, EmotionValence.NEUTRAL)
            else:
                valence = EmotionValence.NEUTRAL

        beat = ChapterEmotionBeat(
            chapter_index=chapter_index,
            valence=valence,
            intensity=intensity,
            detected_payoff_hits=pay_hits,
            detected_suppression_hits=sup_hits,
            note=note,
        )
        self.beats[chapter_index] = beat
        return beat

    # ---------- 分析 ----------

    def _ordered(self, up_to: Optional[int] = None) -> List[ChapterEmotionBeat]:
        keys = sorted(self.beats.keys())
        if up_to is not None:
            keys = [k for k in keys if k <= up_to]
        return [self.beats[k] for k in keys]

    def analyze(self, chapter_index: int) -> DensityReport:
        """以指定章为当前点，分析爽点密度健康度"""
        report = DensityReport(chapter_index=chapter_index)
        history = self._ordered(up_to=chapter_index)
        if not history:
            return report

        window = history[-self.rolling_window:]
        report.rolling_score = round(sum(b.score for b in window), 2)

        # 距上一次爆发多久
        since = 0
        for b in reversed(history):
            if b.valence in (EmotionValence.PAYOFF, EmotionValence.TRIUMPH):
                break
            since += 1
        report.chapters_since_last_payoff = since

        # 连续憋屈 / 连续爆发
        sup_streak = 0
        for b in reversed(history):
            if b.valence == EmotionValence.SUPPRESSION:
                sup_streak += 1
            else:
                break
        report.suppression_streak = sup_streak

        pay_streak = 0
        for b in reversed(history):
            if b.valence in (EmotionValence.PAYOFF, EmotionValence.TRIUMPH):
                pay_streak += 1
            else:
                break
        report.payoff_streak = pay_streak

        # 告警判定
        if sup_streak >= self.max_suppression_streak:
            report.alerts.append(
                f"连续 {sup_streak} 章处于压制/憋屈状态（上限 {self.max_suppression_streak}），"
                f"读者忍耐阈值已被击穿，弃书风险极高。"
            )
            report.directives.append(
                "【强制爆发】本章必须安排一次明确的爽点兑现：当众打脸、实力曝光或反杀成功，"
                "且必须有旁观者的震惊反馈镜头，让憋了多章的情绪一次性释放。"
            )
        if since >= self.max_chapters_without_payoff:
            report.alerts.append(
                f"已 {since} 章没有任何爽点兑现（上限 {self.max_chapters_without_payoff}）。"
            )
            report.directives.append(
                "【补充小爽点】即使主线仍在蓄力，本章也应给一个中小型兑现（打脸配角、"
                "获得关键资源、能力小突破），维持读者的正反馈。"
            )
        if pay_streak >= self.max_payoff_streak:
            report.alerts.append(
                f"连续 {pay_streak} 章都是爽点爆发，爽感边际效用递减，读者会疲劳。"
            )
            report.directives.append(
                "【引入阻力】本章应当引入一个主角无法立刻解决的新阻力或代价，"
                "重新建立张力，避免无脑平推。"
            )
        if report.rolling_score < self.min_rolling_score:
            report.alerts.append(
                f"近 {len(window)} 章滚动情绪值 {report.rolling_score:+.1f}，"
                f"低于警戒线 {self.min_rolling_score}，全书基调过于压抑。"
            )

        report.passed = not report.alerts
        return report

    def render_curve(self, width: int = 60) -> str:
        """以 ASCII 折线渲染爽点密度曲线，便于终端巡检"""
        history = self._ordered()
        if not history:
            return "(暂无数据)"
        rows = []
        levels = [
            (EmotionValence.TRIUMPH, "狂欢"),
            (EmotionValence.PAYOFF, "爆发"),
            (EmotionValence.NEUTRAL, "过渡"),
            (EmotionValence.TENSION, "紧张"),
            (EmotionValence.SUPPRESSION, "憋屈"),
        ]
        shown = history[-width:]
        for val, label in levels:
            line = "".join("█" if b.valence == val else "·" for b in shown)
            rows.append(f"{label} |{line}")
        start = shown[0].chapter_index
        end = shown[-1].chapter_index
        rows.append(f"     第{start}章 {'-' * max(0, len(shown) - 12)} 第{end}章")
        return "\n".join(rows)

    def suggest_next_valence(self, chapter_index: int) -> EmotionValence:
        """给导演智能体的下一章情绪建议"""
        rep = self.analyze(chapter_index)
        if rep.suppression_streak >= self.max_suppression_streak - 1:
            return EmotionValence.PAYOFF
        if rep.chapters_since_last_payoff >= self.max_chapters_without_payoff - 1:
            return EmotionValence.PAYOFF
        if rep.payoff_streak >= self.max_payoff_streak - 1:
            return EmotionValence.SUPPRESSION
        return EmotionValence.TENSION
