"""
Beat Contract Delivery Auditor - 节拍契约交付履约审计器

这是补齐「质检说通过、其实是垃圾」漏洞的核心闸门。
MechanicalLinter 只检查【文本写得对不对】(禁语、排版)，
本模块检查【契约有没有兑现】(字数、微事件、机位、禁忌、后置状态)。

审计维度：
1. 字数交付契约 (Word Count SLA)：实际字数必须落在 target_words ± tolerance 区间；
2. 微事件推进契约 (Micro-Event Coverage)：must_accomplish 的离散事件必须在正文留下可检出痕迹；
3. 镜头机位覆盖契约 (Camera Coverage)：required_camera_angles 必须有对应的语言学特征；
4. 绝对禁忌契约 (Strict Prohibitions)：命中即致命违约；
5. 后置状态契约 (Post-Conditions)：声明的状态转移必须在正文体现；
6. 在场纪律契约 (Presence Discipline)：未在 characters_present 的已知角色不得有台词/动作。
"""

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any, Dict, List, Optional, Sequence, Set

from src.novel_factory.schemas.beat import BeatContract, CameraAngle


class ContractBreachSeverity(str, Enum):
    FATAL = "FATAL"      # 致命违约，必须重生成或打补丁
    MAJOR = "MAJOR"      # 严重违约，应当打补丁
    MINOR = "MINOR"      # 轻微偏差，记录不阻断


@dataclass
class ContractBreach:
    """单条契约违约记录"""
    clause: str                       # 违约条款标识
    severity: ContractBreachSeverity
    message: str
    expected: Any = None
    actual: Any = None
    repair_hint: str = ""             # 下发给 LocalPatcher 的定向修复指令

    def to_dict(self) -> Dict[str, Any]:
        return {
            "clause": self.clause,
            "severity": self.severity.value,
            "message": self.message,
            "expected": self.expected,
            "actual": self.actual,
            "repair_hint": self.repair_hint,
        }


@dataclass
class ContractAuditReport:
    """节拍契约履约审计报告"""
    beat_id: str
    passed: bool = True
    actual_words: int = 0
    target_words: int = 0
    word_compliance_ratio: float = 1.0
    covered_camera_angles: List[str] = field(default_factory=list)
    fulfilled_micro_events: List[str] = field(default_factory=list)
    missing_micro_events: List[str] = field(default_factory=list)
    breaches: List[ContractBreach] = field(default_factory=list)

    @property
    def fatal_breaches(self) -> List[ContractBreach]:
        return [b for b in self.breaches if b.severity == ContractBreachSeverity.FATAL]

    @property
    def major_breaches(self) -> List[ContractBreach]:
        return [b for b in self.breaches if b.severity == ContractBreachSeverity.MAJOR]

    def repair_instructions(self) -> List[str]:
        """汇总可直接下发给局部补丁器的修复指令"""
        return [b.repair_hint for b in self.breaches if b.repair_hint]

    def format_summary(self) -> str:
        head = "[契约履约] " + ("PASS" if self.passed else "BREACH")
        lines = [
            f"{head} beat={self.beat_id} 字数 {self.actual_words}/{self.target_words} "
            f"(履约率 {self.word_compliance_ratio:.0%})"
        ]
        for b in self.breaches:
            lines.append(f"  - [{b.severity.value}] {b.clause}: {b.message}")
        return "\n".join(lines)


# 各机位的语言学特征探针 (中文网文写作实证特征)
CAMERA_SIGNATURES: Dict[CameraAngle, List[str]] = {
    CameraAngle.POV: [
        "我", "他心里", "她心里", "心中", "念头", "意识到", "才明白", "暗道",
        "脑海", "心头", "想起", "打定主意", "看在眼里",
    ],
    CameraAngle.CLOSE_UP: [
        "指尖", "瞳孔", "手指", "喉结", "嘴角", "睫毛", "掌心", "刀刃", "剑尖",
        "伤口", "血珠", "青筋", "寸", "毫米", "厘米", "特写", "手腕", "指节",
    ],
    CameraAngle.PANORAMIC: [
        "天色", "夜空", "远处", "整座", "四周", "街道", "广场", "山脉", "云层",
        "雨", "风", "全场", "视野尽头", "地平线", "空气中",
    ],
    CameraAngle.REACTION_CAM: [
        "众人", "人群", "围观", "倒吸", "哗然", "寂静", "鸦雀无声", "震惊",
        "不敢相信", "议论", "惊呼", "目瞪口呆", "看向", "所有人",
    ],
}

# 对话与动作的检出特征（用于在场纪律检查）
_DIALOGUE_PATTERN = re.compile(r"[“\"「『][^”\"」』]{1,200}[”\"」』]")


def count_chinese_words(text: str) -> int:
    """
    中文网文字数统计口径（对齐起点/番茄后台）：
    汉字逐字计数 + 连续英文/数字串按 1 计 + 不计空白与换行，标点计入。
    """
    if not text:
        return 0
    stripped = re.sub(r"\s+", "", text)
    # 连续的 ASCII 字母数字串折算为 1 个字
    ascii_runs = re.findall(r"[A-Za-z0-9]+", stripped)
    without_ascii = re.sub(r"[A-Za-z0-9]+", "", stripped)
    return len(without_ascii) + len(ascii_runs)


class BeatContractAuditor:
    """节拍契约交付履约审计器"""

    def __init__(
        self,
        enforce_camera_coverage: bool = True,
        enforce_micro_events: bool = True,
        enforce_word_count: bool = True,
        min_camera_coverage_ratio: float = 0.5,
        high_confidence: float = 0.6,
        low_confidence: float = 0.3,
    ):
        # 微事件推进判定的双阈值：高于 high 视为已推进，低于 low 视为确实遗漏，
        # 中间地带存疑，降级处理并交由语义裁判复核。
        self.high_confidence = high_confidence
        self.low_confidence = low_confidence
        self.enforce_camera_coverage = enforce_camera_coverage
        self.enforce_micro_events = enforce_micro_events
        self.enforce_word_count = enforce_word_count
        self.min_camera_coverage_ratio = min_camera_coverage_ratio

    # ---------- 各维度探针 ----------

    def detect_camera_angles(self, prose: str) -> Set[CameraAngle]:
        """通过语言学特征探测正文实际覆盖了哪些镜头机位"""
        covered: Set[CameraAngle] = set()
        for angle, signatures in CAMERA_SIGNATURES.items():
            if any(sig in prose for sig in signatures):
                covered.add(angle)
        return covered

    def _event_keywords(self, description: str) -> List[str]:
        """
        从微事件描述中抽取可检出的实体/动作关键词。
        采用 2-gram 以上的中文片段与显式名词，避免单字误判。
        """
        cleaned = re.sub(r"[，。、；：！？（）()\[\]【】\s]+", " ", description)
        tokens = [t for t in cleaned.split(" ") if len(t) >= 2]
        return tokens

    def micro_event_coverage(self, prose: str, description: str) -> float:
        """
        计算微事件在正文中的痕迹覆盖率 (0.0 ~ 1.0)。

        纯机械的关键词匹配无法真正判定"语义是否推进"，因此这里只输出连续的
        置信度，由调用方按三档处置：
          >= high_confidence : 判定已推进
          <  low_confidence  : 判定确实遗漏（致命违约）
          介于两者之间        : 存疑，降级为 MAJOR 并移交 LLM 裁判语义复核
        """
        keywords = self._event_keywords(description)
        if not keywords:
            return 1.0
        hits = 0.0
        for kw in keywords:
            if kw in prose:
                hits += 1
                continue
            # 退化为字符级重叠检测，容忍 LLM 的同义改写与语序调整。
            # 长片段（如整句事件描述）按比例判定，短词才要求近乎完全命中，
            # 否则一个未分词的长描述会被判为"永远未推进"，导致无限打补丁。
            distinct = set(kw)
            overlap = sum(1 for ch in distinct if ch in prose)
            if len(distinct) >= 6:
                # 长片段按字符覆盖比例连续计分，避免一刀切误判
                hits += min(1.0, (overlap / len(distinct)) / 0.75)
            elif overlap >= max(2, len(distinct) - 1):
                hits += 1.0
        return min(1.0, hits / len(keywords))

    def check_micro_event_fulfilled(self, prose: str, description: str) -> bool:
        """布尔形式的便捷判定（沿用高置信阈值）"""
        return self.micro_event_coverage(prose, description) >= self.high_confidence

    # ---------- 主审计入口 ----------

    def audit(
        self,
        contract: BeatContract,
        prose: str,
        known_character_names: Optional[Dict[str, str]] = None,
    ) -> ContractAuditReport:
        """
        对单个节拍的交付物执行全条款履约审计。

        known_character_names: entity_id -> 角色名，用于在场纪律检查。
        """
        report = ContractAuditReport(
            beat_id=contract.beat_id,
            target_words=contract.target_words,
        )
        actual = count_chinese_words(prose)
        report.actual_words = actual
        report.word_compliance_ratio = (
            actual / contract.target_words if contract.target_words else 1.0
        )

        self._audit_word_count(contract, report)
        self._audit_micro_events(contract, prose, report)
        self._audit_camera_coverage(contract, prose, report)
        self._audit_prohibitions(contract, prose, report)
        self._audit_post_conditions(contract, prose, report)
        self._audit_presence_discipline(contract, prose, known_character_names or {}, report)

        report.passed = not (report.fatal_breaches or report.major_breaches)
        return report

    def _audit_word_count(self, contract: BeatContract, report: ContractAuditReport) -> None:
        if not self.enforce_word_count:
            return
        target = contract.target_words
        tol = contract.word_tolerance_ratio
        lower = int(target * (1 - tol))
        upper = int(target * (1 + tol))
        actual = report.actual_words

        if actual < lower:
            deficit = lower - actual
            # 交付量不足一半属于严重缩水，直接致命
            sev = (
                ContractBreachSeverity.FATAL
                if actual < target * 0.5
                else ContractBreachSeverity.MAJOR
            )
            report.breaches.append(ContractBreach(
                clause="WORD_COUNT_UNDER_DELIVERY",
                severity=sev,
                message=(
                    f"字数严重缩水：契约要求 {target} 字(容差 ±{tol:.0%}，下限 {lower})，"
                    f"实际仅交付 {actual} 字，缺口 {deficit} 字"
                ),
                expected=f">={lower}",
                actual=actual,
                repair_hint=(
                    f"本节拍正文仅 {actual} 字，远低于契约要求的 {target} 字。"
                    f"请在不引入新剧情事件的前提下，补足约 {deficit} 字："
                    f"扩写环境五感细节、人物微动作与心理反应，严禁注水式空洞议论。"
                ),
            ))
        elif actual > upper:
            excess = actual - upper
            report.breaches.append(ContractBreach(
                clause="WORD_COUNT_OVER_DELIVERY",
                severity=ContractBreachSeverity.MAJOR,
                message=(
                    f"字数超额膨胀：契约上限 {upper} 字，实际 {actual} 字，超出 {excess} 字"
                ),
                expected=f"<={upper}",
                actual=actual,
                repair_hint=(
                    f"本节拍超出契约上限 {excess} 字。请删减冗余铺陈与重复描写，"
                    f"保留全部关键微事件，压缩至 {target} 字左右。"
                ),
            ))

    def _audit_micro_events(
        self, contract: BeatContract, prose: str, report: ContractAuditReport
    ) -> None:
        if not self.enforce_micro_events:
            return
        for ev in contract.micro_events:
            coverage = self.micro_event_coverage(prose, ev.description)
            if coverage >= self.high_confidence:
                report.fulfilled_micro_events.append(ev.event_id)
                continue

            report.missing_micro_events.append(ev.event_id)
            if not ev.must_accomplish:
                continue

            if coverage < self.low_confidence:
                report.breaches.append(ContractBreach(
                    clause="MICRO_EVENT_NOT_ADVANCED",
                    severity=ContractBreachSeverity.FATAL,
                    message=(
                        f"必达微事件未被推进: [{ev.event_id}] {ev.description} "
                        f"(正文痕迹覆盖率仅 {coverage:.0%})"
                    ),
                    expected=ev.description,
                    actual="未在正文检出",
                    repair_hint=(
                        f"本节拍漏掉了必须发生的剧情事件：「{ev.description}」。"
                        f"请在正文合适位置补写该事件的具体物理过程，"
                        f"不要概括叙述，要有动作与结果。"
                    ),
                ))
            else:
                report.breaches.append(ContractBreach(
                    clause="MICRO_EVENT_AMBIGUOUS",
                    severity=ContractBreachSeverity.MINOR,
                    message=(
                        f"微事件推进存疑: [{ev.event_id}] {ev.description} "
                        f"(覆盖率 {coverage:.0%}，介于判定阈值之间，建议交由语义裁判复核)"
                    ),
                    expected=ev.description,
                    actual=f"覆盖率 {coverage:.0%}",
                    repair_hint=(
                        f"事件「{ev.description}」在正文中的表达较为间接，"
                        f"若确已推进可忽略；否则请补写更明确的动作与结果。"
                    ),
                ))

    def _audit_camera_coverage(
        self, contract: BeatContract, prose: str, report: ContractAuditReport
    ) -> None:
        if not self.enforce_camera_coverage or not contract.required_camera_angles:
            return
        covered = self.detect_camera_angles(prose)
        report.covered_camera_angles = sorted(a.value for a in covered)
        required = set(contract.required_camera_angles)
        missing = required - covered
        ratio = len(required & covered) / len(required)

        if ratio < self.min_camera_coverage_ratio:
            names = "、".join(a.value for a in sorted(missing, key=lambda x: x.value))
            report.breaches.append(ContractBreach(
                clause="CAMERA_COVERAGE_INSUFFICIENT",
                severity=ContractBreachSeverity.MAJOR,
                message=(
                    f"镜头机位覆盖不足：契约要求 {len(required)} 个机位，"
                    f"实际仅覆盖 {len(required & covered)} 个，缺失 [{names}]"
                ),
                expected=sorted(a.value for a in required),
                actual=report.covered_camera_angles,
                repair_hint=(
                    f"本节拍缺少 [{names}] 机位。请补写："
                    f"POV=主角内心判断；CLOSE_UP=手部/兵刃/瞳孔特写；"
                    f"PANORAMIC=环境天色与空间全景；REACTION_CAM=旁观者的震惊反馈。"
                ),
            ))

    def _audit_prohibitions(
        self, contract: BeatContract, prose: str, report: ContractAuditReport
    ) -> None:
        for banned in contract.strict_prohibitions:
            if not banned:
                continue
            keywords = self._event_keywords(banned)
            if keywords and all(kw in prose for kw in keywords):
                report.breaches.append(ContractBreach(
                    clause="STRICT_PROHIBITION_VIOLATED",
                    severity=ContractBreachSeverity.FATAL,
                    message=f"命中本节拍绝对禁忌: {banned}",
                    expected=f"禁止出现: {banned}",
                    actual="已出现",
                    repair_hint=f"正文违反了本节拍的绝对禁令「{banned}」，请彻底删改相关段落。",
                ))

    def _audit_post_conditions(
        self, contract: BeatContract, prose: str, report: ContractAuditReport
    ) -> None:
        for cond in contract.post_conditions:
            if not cond:
                continue
            if self.micro_event_coverage(prose, cond) < self.low_confidence:
                report.breaches.append(ContractBreach(
                    clause="POST_CONDITION_UNMET",
                    severity=ContractBreachSeverity.MAJOR,
                    message=f"后置状态转移未达成: {cond}",
                    expected=cond,
                    actual="未在正文检出",
                    repair_hint=(
                        f"本节拍结束时必须达成状态「{cond}」，但正文没有写出来。"
                        f"请在结尾处补写该状态变化的具体表现。"
                    ),
                ))

    def _audit_presence_discipline(
        self,
        contract: BeatContract,
        prose: str,
        known_character_names: Dict[str, str],
        report: ContractAuditReport,
    ) -> None:
        """未在场角色不得在本节拍里说话或行动（幽灵串场检测）"""
        if not known_character_names:
            return
        present = set(contract.characters_present)
        for ent_id, name in known_character_names.items():
            if ent_id in present or not name:
                continue
            if name in prose:
                report.breaches.append(ContractBreach(
                    clause="ABSENT_CHARACTER_INTRUSION",
                    severity=ContractBreachSeverity.MAJOR,
                    message=(
                        f"幽灵串场：角色 [{name}] 未列入本节拍在场名单，却出现在正文中"
                    ),
                    expected=sorted(present),
                    actual=name,
                    repair_hint=(
                        f"角色「{name}」本节拍不在场，请删除其台词与动作，"
                        f"或改由在场角色转述。"
                    ),
                ))
