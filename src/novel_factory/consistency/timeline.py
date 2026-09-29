"""
Story Calendar - 故事内绝对时钟与时间线一致性引擎

长篇网文最常见的隐性崩坏：
  第 30 章说「三天后大比开始」，第 35 章主角还在闭关修炼了一个月；
  昨夜受的重伤，第二天清晨已生龙活虎；
  人物年龄、季节、月相互相打架。

本模块给故事装一个【绝对时钟】：每一章绑定一个故事内时刻 (StoryInstant)，
以「分钟」为最小整数单位做绝对纪年，从而把模糊的自然语言时间表述
（次日、三天后、一炷香、翌年开春）编译为可机械比对的数值，
并对时序倒流、时长矛盾、伤愈过快、承诺逾期做硬检测。
"""

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any, Dict, List, Optional, Tuple

MINUTES_PER_HOUR = 60
MINUTES_PER_DAY = 24 * 60
MINUTES_PER_MONTH = 30 * MINUTES_PER_DAY
MINUTES_PER_YEAR = 365 * MINUTES_PER_DAY


class Season(str, Enum):
    SPRING = "SPRING"
    SUMMER = "SUMMER"
    AUTUMN = "AUTUMN"
    WINTER = "WINTER"


class TimeOfDay(str, Enum):
    DAWN = "DAWN"          # 拂晓 05-07
    MORNING = "MORNING"    # 上午 07-11
    NOON = "NOON"          # 正午 11-13
    AFTERNOON = "AFTERNOON"  # 午后 13-17
    DUSK = "DUSK"          # 黄昏 17-19
    NIGHT = "NIGHT"        # 夜晚 19-23
    MIDNIGHT = "MIDNIGHT"  # 子夜 23-05


# 中文自然语言时间增量 -> 分钟数
DURATION_LEXICON: List[Tuple[str, int]] = [
    ("一炷香", 30),
    ("一盏茶", 15),
    ("半个时辰", 60),
    ("一个时辰", 120),
    ("片刻", 5),
    ("须臾", 2),
    ("眨眼", 0),
    ("翌日", MINUTES_PER_DAY),
    ("次日", MINUTES_PER_DAY),
    ("第二天", MINUTES_PER_DAY),
    ("隔日", MINUTES_PER_DAY),
    ("当夜", 6 * MINUTES_PER_HOUR),
    ("三日后", 3 * MINUTES_PER_DAY),
    ("七日后", 7 * MINUTES_PER_DAY),
    ("半月后", 15 * MINUTES_PER_DAY),
    ("一月后", MINUTES_PER_MONTH),
    ("翌年", MINUTES_PER_YEAR),
    ("一年后", MINUTES_PER_YEAR),
    ("三年后", 3 * MINUTES_PER_YEAR),
]

_CN_NUM = {
    "零": 0, "一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "百": 100, "半": 0.5,
}

_UNIT_MINUTES = {
    "分钟": 1, "刻钟": 15, "小时": 60, "时辰": 120,
    "天": MINUTES_PER_DAY, "日": MINUTES_PER_DAY, "夜": MINUTES_PER_DAY,
    "周": 7 * MINUTES_PER_DAY, "星期": 7 * MINUTES_PER_DAY,
    "月": MINUTES_PER_MONTH, "年": MINUTES_PER_YEAR, "载": MINUTES_PER_YEAR,
}

# 允许数词与单位之间夹量词/程度词：两「个」月、三「来」天、五「多」年
_DURATION_RE = re.compile(
    r"([0-9]+|[零一两二三四五六七八九十百半]+)\s*[个来多余]?\s*"
    r"(分钟|刻钟|小时|时辰|天|日|夜|周|星期|月|年|载)(?:之?后)?"
)


def parse_cn_number(token: str) -> float:
    """解析中文数字（覆盖网文常见的 一/两/三/十/二十/半 等写法）"""
    if token.isdigit():
        return float(token)
    if token == "半":
        return 0.5
    if token == "十":
        return 10.0
    total = 0.0
    if "十" in token:
        left, _, right = token.partition("十")
        tens = _CN_NUM.get(left, 1) if left else 1
        ones = _CN_NUM.get(right, 0) if right else 0
        return float(tens * 10 + ones)
    for ch in token:
        total += _CN_NUM.get(ch, 0)
    return float(total) if total else 0.0


def parse_duration_to_minutes(text: str) -> Optional[int]:
    """
    将自然语言时间表述编译为分钟数。无法解析时返回 None。
    优先匹配固定词典，再退化到 <数词><单位> 的通用模式。
    """
    for phrase, minutes in DURATION_LEXICON:
        if phrase in text:
            return minutes
    m = _DURATION_RE.search(text)
    if m:
        num = parse_cn_number(m.group(1))
        unit = _UNIT_MINUTES.get(m.group(2), 0)
        return int(num * unit)
    return None


@dataclass
class StoryInstant:
    """故事内绝对时刻（以开篇为 0 点的分钟数）"""
    absolute_minutes: int = 0

    @property
    def day(self) -> int:
        return self.absolute_minutes // MINUTES_PER_DAY

    @property
    def hour(self) -> int:
        return (self.absolute_minutes % MINUTES_PER_DAY) // MINUTES_PER_HOUR

    @property
    def minute(self) -> int:
        return self.absolute_minutes % MINUTES_PER_HOUR

    @property
    def year(self) -> int:
        return self.absolute_minutes // MINUTES_PER_YEAR

    @property
    def time_of_day(self) -> TimeOfDay:
        h = self.hour
        if 5 <= h < 7:
            return TimeOfDay.DAWN
        if 7 <= h < 11:
            return TimeOfDay.MORNING
        if 11 <= h < 13:
            return TimeOfDay.NOON
        if 13 <= h < 17:
            return TimeOfDay.AFTERNOON
        if 17 <= h < 19:
            return TimeOfDay.DUSK
        if 19 <= h < 23:
            return TimeOfDay.NIGHT
        return TimeOfDay.MIDNIGHT

    @property
    def season(self) -> Season:
        day_of_year = (self.absolute_minutes % MINUTES_PER_YEAR) // MINUTES_PER_DAY
        if day_of_year < 90:
            return Season.SPRING
        if day_of_year < 181:
            return Season.SUMMER
        if day_of_year < 273:
            return Season.AUTUMN
        return Season.WINTER

    def describe(self) -> str:
        return (
            f"开篇后第 {self.day} 天 {self.hour:02d}:{self.minute:02d} "
            f"({self.time_of_day.value} / {self.season.value})"
        )

    def __add__(self, minutes: int) -> "StoryInstant":
        return StoryInstant(self.absolute_minutes + minutes)


@dataclass
class TimeAnchor:
    """章节时间锚点"""
    chapter_index: int
    start: StoryInstant
    end: StoryInstant
    declared_text: str = ""       # 原文中的时间表述
    location_id: str = ""

    @property
    def elapsed_minutes(self) -> int:
        return self.end.absolute_minutes - self.start.absolute_minutes


@dataclass
class TimelineConflict:
    conflict_type: str
    severity: str           # ERROR / WARNING
    chapter_index: int
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TimelineReport:
    passed: bool = True
    conflicts: List[TimelineConflict] = field(default_factory=list)

    @property
    def errors(self) -> List[TimelineConflict]:
        return [c for c in self.conflicts if c.severity == "ERROR"]

    def format_summary(self) -> str:
        if not self.conflicts:
            return "[时间线] PASS 未检出时序矛盾"
        lines = [f"[时间线] {'PASS' if self.passed else 'FAIL'} 检出 {len(self.conflicts)} 处矛盾"]
        for c in self.conflicts:
            lines.append(f"  - [{c.severity}] 第{c.chapter_index}章 {c.conflict_type}: {c.message}")
        return "\n".join(lines)


@dataclass
class HealingRule:
    """伤势恢复的最小生理时长约束（防「昨夜重伤今晨龙精虎猛」）"""
    injury_level: str
    min_recovery_minutes: int


DEFAULT_HEALING_RULES: Dict[str, int] = {
    "MINOR": 12 * MINUTES_PER_HOUR,        # 轻伤：半天
    "MODERATE": 5 * MINUTES_PER_DAY,       # 中伤：五天
    "SEVERE": 30 * MINUTES_PER_DAY,        # 重伤：一个月
    "CRIPPLING": 180 * MINUTES_PER_DAY,    # 濒死/残废：半年
}


class StoryCalendar:
    """故事内绝对时钟与时间线一致性检查器"""

    def __init__(self, healing_rules: Optional[Dict[str, int]] = None):
        self.anchors: Dict[int, TimeAnchor] = {}
        self.healing_rules = dict(healing_rules or DEFAULT_HEALING_RULES)
        # entity_id -> (受伤时刻, 伤势等级)
        self._injuries: Dict[str, Tuple[StoryInstant, str]] = {}
        # 约定事件: event_id -> (承诺发生时刻, 描述)
        self._appointments: Dict[str, Tuple[StoryInstant, str]] = {}

    # ---------- 章节锚定 ----------

    def anchor_chapter(
        self,
        chapter_index: int,
        start_minutes: Optional[int] = None,
        elapsed_minutes: int = 0,
        declared_text: str = "",
        location_id: str = "",
    ) -> TimeAnchor:
        """
        为章节锚定故事内时间。
        start_minutes 省略时，自动接续上一章结束时刻；
        declared_text 中若含可解析的时间跳跃表述，将自动叠加为章前间隔。
        """
        if start_minutes is None:
            prev = self.anchors.get(chapter_index - 1)
            base = prev.end.absolute_minutes if prev else 0
            gap = parse_duration_to_minutes(declared_text) if declared_text else None
            start_minutes = base + (gap or 0)

        anchor = TimeAnchor(
            chapter_index=chapter_index,
            start=StoryInstant(start_minutes),
            end=StoryInstant(start_minutes + max(0, elapsed_minutes)),
            declared_text=declared_text,
            location_id=location_id,
        )
        self.anchors[chapter_index] = anchor
        return anchor

    def get_instant(self, chapter_index: int) -> Optional[StoryInstant]:
        a = self.anchors.get(chapter_index)
        return a.start if a else None

    # ---------- 生理与约定登记 ----------

    def record_injury(self, entity_id: str, chapter_index: int, injury_level: str) -> None:
        """登记角色受伤，用于后续恢复速度校验"""
        anchor = self.anchors.get(chapter_index)
        instant = anchor.end if anchor else StoryInstant(0)
        self._injuries[entity_id] = (instant, injury_level.upper())

    def record_appointment(
        self, event_id: str, due_instant_minutes: int, description: str = ""
    ) -> None:
        """登记剧情承诺（如『三日后城门决战』），到期未发生即告警"""
        self._appointments[event_id] = (StoryInstant(due_instant_minutes), description)

    def resolve_appointment(self, event_id: str) -> bool:
        return self._appointments.pop(event_id, None) is not None

    # ---------- 检查 ----------

    def check_chapter(
        self,
        chapter_index: int,
        acting_entities: Optional[List[str]] = None,
        max_unexplained_gap_days: int = 365,
    ) -> TimelineReport:
        """对单章做时间线一致性检查"""
        report = TimelineReport()
        anchor = self.anchors.get(chapter_index)
        if not anchor:
            return report

        prev = self.anchors.get(chapter_index - 1)

        # 1. 时序倒流检测
        if prev and anchor.start.absolute_minutes < prev.end.absolute_minutes:
            back = prev.end.absolute_minutes - anchor.start.absolute_minutes
            report.conflicts.append(TimelineConflict(
                conflict_type="TIME_TRAVEL_BACKWARDS",
                severity="ERROR",
                chapter_index=chapter_index,
                message=(
                    f"时序倒流：本章起始时刻早于上一章结束时刻 {back} 分钟"
                    f"（{back / MINUTES_PER_DAY:.1f} 天）。若为有意的插叙，请显式标注 FLASHBACK。"
                ),
                details={"backwards_minutes": back},
            ))

        # 2. 无解释的超长时间跳跃
        if prev:
            gap = anchor.start.absolute_minutes - prev.end.absolute_minutes
            if gap > max_unexplained_gap_days * MINUTES_PER_DAY:
                report.conflicts.append(TimelineConflict(
                    conflict_type="UNEXPLAINED_TIME_SKIP",
                    severity="WARNING",
                    chapter_index=chapter_index,
                    message=(
                        f"时间跳跃 {gap / MINUTES_PER_DAY:.0f} 天缺乏叙事交代，"
                        f"读者会脱节，建议补一段过渡说明这段时间主角在做什么。"
                    ),
                    details={"gap_days": gap / MINUTES_PER_DAY},
                ))

        # 3. 伤愈过快检测
        for ent in (acting_entities or []):
            injured = self._injuries.get(ent)
            if not injured:
                continue
            hurt_at, level = injured
            required = self.healing_rules.get(level, 0)
            elapsed = anchor.start.absolute_minutes - hurt_at.absolute_minutes
            if 0 <= elapsed < required:
                report.conflicts.append(TimelineConflict(
                    conflict_type="IMPLAUSIBLE_RECOVERY",
                    severity="ERROR",
                    chapter_index=chapter_index,
                    message=(
                        f"伤愈速度违背设定：[{ent}] 的 {level} 级伤势仅过去 "
                        f"{elapsed / MINUTES_PER_DAY:.1f} 天便恢复行动，"
                        f"设定要求至少 {required / MINUTES_PER_DAY:.1f} 天。"
                        f"请改为带伤作战、使用疗伤资源，或推迟本章时间。"
                    ),
                    details={"entity_id": ent, "elapsed_days": elapsed / MINUTES_PER_DAY},
                ))

        # 4. 剧情承诺逾期检测
        for eid, (due, desc) in list(self._appointments.items()):
            if anchor.start.absolute_minutes > due.absolute_minutes:
                overdue_days = (anchor.start.absolute_minutes - due.absolute_minutes) / MINUTES_PER_DAY
                report.conflicts.append(TimelineConflict(
                    conflict_type="APPOINTMENT_OVERDUE",
                    severity="ERROR",
                    chapter_index=chapter_index,
                    message=(
                        f"剧情约定逾期：「{desc or eid}」应在故事时间 "
                        f"{due.describe()} 发生，现已逾期 {overdue_days:.1f} 天仍未兑现。"
                    ),
                    details={"event_id": eid, "overdue_days": overdue_days},
                ))

        report.passed = not report.errors
        return report

    def extract_time_expressions(self, text: str) -> List[Tuple[str, int]]:
        """从正文中抽取所有可解析的时间表述及其分钟增量（供导演自动锚定）"""
        found: List[Tuple[str, int]] = []
        for phrase, minutes in DURATION_LEXICON:
            if phrase in text:
                found.append((phrase, minutes))
        for m in _DURATION_RE.finditer(text):
            num = parse_cn_number(m.group(1))
            unit = _UNIT_MINUTES.get(m.group(2), 0)
            found.append((m.group(0), int(num * unit)))
        return found

    def build_context_line(self, chapter_index: int) -> str:
        """生成注入 Writer Prompt 的时间锚点提示行"""
        inst = self.get_instant(chapter_index)
        if not inst:
            return ""
        return (
            f"【故事内时间】当前为{inst.describe()}。"
            f"本章所有时间表述必须与此一致，严禁出现与季节、昼夜矛盾的描写。"
        )
