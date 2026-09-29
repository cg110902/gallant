"""
Power Curve Guard - 升级节奏守门员与战力膨胀约束器

「战力崩坏」是长篇仙侠/玄幻/系统流最常见的结构性死因：
  前 50 章一个境界打三十章，第 80 章开始一章一个境界；
  主角战力指数爆炸后，所有既有反派全部失去威胁，故事失去张力；
  越阶战斗毫无节制，境界体系沦为数字游戏。

本模块把「升级」当作一条必须被工程约束的曲线来管理：
1. 单章/单卷战力增幅上限（防跳跃式暴涨）；
2. 境界停留时长下限（防境界通货膨胀）；
3. 与反派战力的相对差值监控（防"再无对手"）；
4. 理想成长曲线拟合与偏离度预警。
"""

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple


class CurveShape(str, Enum):
    LINEAR = "LINEAR"              # 线性：稳健但后期乏力
    EXPONENTIAL = "EXPONENTIAL"    # 指数：爽但极易崩坏
    STAIRCASE = "STAIRCASE"        # 阶梯：网文主流（长憋+突破）
    LOGARITHMIC = "LOGARITHMIC"    # 对数：前期快后期慢


@dataclass
class PowerSample:
    """某章某实体的战力采样点"""
    chapter_index: int
    entity_id: str
    power_rating: float
    tier_id: Optional[str] = None
    note: str = ""


@dataclass
class PowerCurveViolation:
    violation_type: str
    severity: str           # ERROR / WARNING
    chapter_index: int
    entity_id: str
    message: str
    suggestion: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PowerCurveReport:
    chapter_index: int
    passed: bool = True
    violations: List[PowerCurveViolation] = field(default_factory=list)
    protagonist_power: float = 0.0
    strongest_antagonist_power: float = 0.0
    threat_ratio: float = 1.0        # 反派/主角 战力比，<1 表示再无对手
    growth_rate_per_chapter: float = 0.0

    @property
    def errors(self) -> List[PowerCurveViolation]:
        return [v for v in self.violations if v.severity == "ERROR"]

    def format_summary(self) -> str:
        lines = [
            f"[升级节奏] 第{self.chapter_index}章 {'OK' if self.passed else 'ALERT'} | "
            f"主角战力 {self.protagonist_power:.0f} | "
            f"最强反派 {self.strongest_antagonist_power:.0f} | "
            f"威胁比 {self.threat_ratio:.2f}"
        ]
        for v in self.violations:
            lines.append(f"  - [{v.severity}] {v.violation_type}: {v.message}")
        return "\n".join(lines)


class PowerCurveGuard:
    """升级节奏守门员"""

    def __init__(
        self,
        max_growth_ratio_per_chapter: float = 0.35,   # 单章战力增幅上限 35%
        max_growth_ratio_per_10_chapters: float = 3.0,  # 十章内最多涨 3 倍
        min_chapters_per_tier: int = 15,               # 每个境界至少停留 15 章
        min_threat_ratio: float = 0.7,                 # 反派战力至少为主角的 70%
        target_shape: CurveShape = CurveShape.STAIRCASE,
    ):
        self.max_growth_per_chapter = max_growth_ratio_per_chapter
        self.max_growth_per_10 = max_growth_ratio_per_10_chapters
        self.min_chapters_per_tier = min_chapters_per_tier
        self.min_threat_ratio = min_threat_ratio
        self.target_shape = target_shape

        # entity_id -> [samples]
        self.samples: Dict[str, List[PowerSample]] = {}
        self.protagonist_id: Optional[str] = None
        self.antagonist_ids: List[str] = []

    # ---------- 配置 ----------

    def set_protagonist(self, entity_id: str) -> None:
        self.protagonist_id = entity_id

    def register_antagonist(self, entity_id: str) -> None:
        if entity_id not in self.antagonist_ids:
            self.antagonist_ids.append(entity_id)

    # ---------- 采样 ----------

    def record(
        self,
        chapter_index: int,
        entity_id: str,
        power_rating: float,
        tier_id: Optional[str] = None,
        note: str = "",
    ) -> PowerSample:
        s = PowerSample(
            chapter_index=chapter_index,
            entity_id=entity_id,
            power_rating=power_rating,
            tier_id=tier_id,
            note=note,
        )
        self.samples.setdefault(entity_id, []).append(s)
        self.samples[entity_id].sort(key=lambda x: x.chapter_index)
        return s

    def get_power_at(self, entity_id: str, chapter_index: int) -> Optional[float]:
        hist = [s for s in self.samples.get(entity_id, []) if s.chapter_index <= chapter_index]
        return hist[-1].power_rating if hist else None

    # ---------- 校验 ----------

    def check(self, chapter_index: int) -> PowerCurveReport:
        report = PowerCurveReport(chapter_index=chapter_index)
        pid = self.protagonist_id
        if not pid or pid not in self.samples:
            return report

        hist = [s for s in self.samples[pid] if s.chapter_index <= chapter_index]
        if not hist:
            return report

        current = hist[-1]
        report.protagonist_power = current.power_rating

        # 1. 单章暴涨检测
        if len(hist) >= 2:
            prev = hist[-2]
            span = max(1, current.chapter_index - prev.chapter_index)
            if prev.power_rating > 0:
                total_growth = (current.power_rating - prev.power_rating) / prev.power_rating
                per_chapter = total_growth / span
                report.growth_rate_per_chapter = round(per_chapter, 4)
                if per_chapter > self.max_growth_per_chapter:
                    report.violations.append(PowerCurveViolation(
                        violation_type="POWER_SPIKE",
                        severity="ERROR",
                        chapter_index=chapter_index,
                        entity_id=pid,
                        message=(
                            f"战力跳跃式暴涨：{span} 章内从 {prev.power_rating:.0f} 涨到 "
                            f"{current.power_rating:.0f}（折合单章 +{per_chapter:.0%}，"
                            f"上限 +{self.max_growth_per_chapter:.0%}）"
                        ),
                        suggestion=(
                            "请为这次提升补充足够的代价与铺垫（重伤、耗尽资源、透支寿元），"
                            "或把增幅拆分到后续数章逐步兑现。"
                        ),
                        details={"growth_per_chapter": per_chapter},
                    ))

        # 2. 十章窗口累计膨胀
        window_start = chapter_index - 10
        past = [s for s in hist if s.chapter_index <= window_start]
        if past and past[-1].power_rating > 0:
            ratio = current.power_rating / past[-1].power_rating
            if ratio > self.max_growth_per_10:
                report.violations.append(PowerCurveViolation(
                    violation_type="DECADE_INFLATION",
                    severity="WARNING",
                    chapter_index=chapter_index,
                    entity_id=pid,
                    message=(
                        f"十章内战力膨胀 {ratio:.1f} 倍（上限 {self.max_growth_per_10} 倍），"
                        f"境界体系正在通货膨胀"
                    ),
                    suggestion="建议插入一个平台期：用支线、感情线或势力经营消化成长。",
                    details={"ratio": ratio},
                ))

        # 3. 境界停留时长
        tier_violation = self._check_tier_dwell(hist, chapter_index, pid)
        if tier_violation:
            report.violations.append(tier_violation)

        # 4. 威胁度：还有没有对手
        #    注意区分"反派很弱"与"反派没有数据"——后者是采样缺失，
        #    据此报"再无对手"是误报。实测中它会在每一章都刷一条 ERROR。
        strongest = 0.0
        sampled_antagonists = 0
        for aid in self.antagonist_ids:
            p = self.get_power_at(aid, chapter_index)
            if p is not None:
                sampled_antagonists += 1
                strongest = max(strongest, p)
        report.strongest_antagonist_power = strongest

        if self.antagonist_ids and sampled_antagonists == 0:
            report.threat_ratio = 1.0
            report.violations.append(PowerCurveViolation(
                violation_type="ANTAGONIST_POWER_UNSAMPLED",
                severity="WARNING",
                chapter_index=chapter_index,
                entity_id=pid,
                message=(
                    f"已登记 {len(self.antagonist_ids)} 名反派，但均无战力采样，"
                    f"无法评估威胁度。请在 StateDelta 中同步登记反派战力。"
                ),
                suggestion="为反派实体补充 power_rating 变更，否则升级节奏无从校验。",
            ))
        elif report.protagonist_power > 0 and sampled_antagonists > 0:
            report.threat_ratio = round(strongest / report.protagonist_power, 3)
            if report.threat_ratio < self.min_threat_ratio:
                report.violations.append(PowerCurveViolation(
                    violation_type="NO_CREDIBLE_THREAT",
                    severity="ERROR",
                    chapter_index=chapter_index,
                    entity_id=pid,
                    message=(
                        f"再无对手：当前最强反派战力仅为主角的 {report.threat_ratio:.0%}"
                        f"（警戒线 {self.min_threat_ratio:.0%}），故事张力正在归零"
                    ),
                    suggestion=(
                        "必须尽快引入更高层级的敌人、揭示隐藏势力，"
                        "或给主角施加非战力型困境（阵营、情感、规则、时限）。"
                    ),
                    details={"threat_ratio": report.threat_ratio},
                ))

        report.passed = not report.errors
        return report

    def _check_tier_dwell(
        self, hist: List[PowerSample], chapter_index: int, entity_id: str
    ) -> Optional[PowerCurveViolation]:
        """检查境界停留是否过短（境界通胀）"""
        tiers: List[Tuple[str, int]] = []
        for s in hist:
            if s.tier_id and (not tiers or tiers[-1][0] != s.tier_id):
                tiers.append((s.tier_id, s.chapter_index))
        if len(tiers) < 2:
            return None
        prev_tier, prev_ch = tiers[-2]
        cur_tier, cur_ch = tiers[-1]
        dwell = cur_ch - prev_ch
        if dwell < self.min_chapters_per_tier:
            return PowerCurveViolation(
                violation_type="TIER_INFLATION",
                severity="WARNING",
                chapter_index=chapter_index,
                entity_id=entity_id,
                message=(
                    f"境界通货膨胀：在 [{prev_tier}] 仅停留 {dwell} 章即突破至 [{cur_tier}]，"
                    f"低于设定下限 {self.min_chapters_per_tier} 章"
                ),
                suggestion=(
                    "升级过快会让此前所有铺垫贬值。建议延长本境界的历练篇幅，"
                    "或将突破改为不完全突破（瓶颈、伪境界、借力临时提升）。"
                ),
                details={"dwell_chapters": dwell},
            )
        return None

    # ---------- 规划 ----------

    def ideal_power_at(
        self, chapter_index: int, start_power: float, end_power: float, total_chapters: int
    ) -> float:
        """按目标曲线形状计算某章的理想战力值，供导演做升级排期"""
        if total_chapters <= 0:
            return start_power
        t = max(0.0, min(1.0, chapter_index / total_chapters))
        if self.target_shape == CurveShape.LINEAR:
            f = t
        elif self.target_shape == CurveShape.EXPONENTIAL:
            f = t ** 2.2
        elif self.target_shape == CurveShape.LOGARITHMIC:
            f = math.log1p(9 * t) / math.log(10)
        else:  # STAIRCASE：网文主流，长憋后突破
            steps = 8
            f = math.floor(t * steps) / steps
            f += (t * steps - math.floor(t * steps)) ** 3 / steps
        return start_power + (end_power - start_power) * f

    def deviation_from_ideal(
        self, chapter_index: int, start_power: float, end_power: float, total_chapters: int
    ) -> float:
        """当前战力相对理想曲线的偏离比例（正数=超前，负数=滞后）"""
        if not self.protagonist_id:
            return 0.0
        actual = self.get_power_at(self.protagonist_id, chapter_index)
        if actual is None:
            return 0.0
        ideal = self.ideal_power_at(chapter_index, start_power, end_power, total_chapters)
        if ideal <= 0:
            return 0.0
        return round((actual - ideal) / ideal, 4)
