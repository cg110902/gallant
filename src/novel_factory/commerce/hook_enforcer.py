"""
Chapter Hook Enforcer - 章末钩子强制器

网文的追读率几乎完全由「章末最后三行」决定。一章写得再好，
结尾平淡收束（"他转身离开了房间。"）就等于主动放读者走。

本模块对每章结尾做机械评级：
1. 识别钩子类型（悬念/危机/信息炸弹/反转/承诺/情绪）；
2. 评定钩子强度（DEAD / WEAK / SOLID / STRONG）；
3. 检测反钩子特征（收束性收尾、总结陈词、抒情议论）；
4. 对连续弱钩子做趋势告警；
5. 输出可直接下发的改写指令。
"""

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple


class HookType(str, Enum):
    CLIFFHANGER_DANGER = "CLIFFHANGER_DANGER"      # 危机悬置：刀已架在脖子上
    INFORMATION_BOMB = "INFORMATION_BOMB"          # 信息炸弹：身世/真相揭露一角
    REVERSAL = "REVERSAL"                          # 反转：局势瞬间翻转
    UNANSWERED_QUESTION = "UNANSWERED_QUESTION"    # 悬问：抛出问题不作答
    PROMISE = "PROMISE"                            # 承诺：预告即将到来的大事
    EMOTIONAL_SPIKE = "EMOTIONAL_SPIKE"            # 情绪尖峰：极致愤怒/心碎/狂喜
    NEW_ENTRANT = "NEW_ENTRANT"                    # 新角色/新势力破门而入
    NONE = "NONE"


class HookStrength(str, Enum):
    DEAD = "DEAD"        # 完全收束，读者会关书
    WEAK = "WEAK"        # 有一点余味，不足以驱动追读
    SOLID = "SOLID"      # 合格钩子
    STRONG = "STRONG"    # 强钩子，适合卷末/高潮章


# 钩子类型的语言学特征探针
HOOK_SIGNATURES: Dict[HookType, List[str]] = {
    HookType.CLIFFHANGER_DANGER: [
        "架在", "抵住", "扣动", "举起", "逼近", "已经来不及", "退无可退",
        "下一刻", "千钧一发", "就在这时", "轰然", "锁定", "瞄准", "破空",
    ],
    HookType.INFORMATION_BOMB: [
        "竟然是", "原来", "真相", "身世", "真正的", "从来不是", "一直都是",
        "秘密", "真名", "根本不是", "另有其人", "才是", "还活着", "并没有死",
        "你杀的", "本该", "早就死了", "没有死", "没死", "活着回来", "另一个人",
    ],
    HookType.REVERSAL: [
        "然而", "可是就在", "却在此时", "反手", "早已", "布局", "中计",
        "翻转", "逆转", "反而", "根本没有",
    ],
    HookType.UNANSWERED_QUESTION: [
        "是谁", "为什么", "怎么会", "难道", "究竟", "到底", "何人", "什么东西",
        "你以为", "真的是", "不是吗", "会是",
    ],
    HookType.PROMISE: [
        "三天后", "明日", "即将", "就要", "马上", "倒计时", "大战一触即发",
        "约定", "等着", "不死不休", "必将",
    ],
    HookType.EMOTIONAL_SPIKE: [
        "眼眶", "颤抖", "嘶吼", "怒吼", "咬碎", "拳头攥", "血泪", "疯了",
        "杀意", "恨不得",
    ],
    HookType.NEW_ENTRANT: [
        "一道身影", "一个声音", "陌生", "不速之客", "推门而入", "拦住去路",
        "缓缓走出", "从天而降", "现身", "不该出现", "门开了", "走了进来",
        "出现在门口", "本不该",
    ],
}

# 反钩子：收束性结尾特征，命中即降级
ANTI_HOOK_SIGNATURES: List[str] = [
    "终于结束了", "一切都平静下来", "松了一口气", "沉沉睡去", "画上了句号",
    "尘埃落定", "从此", "再也没有", "圆满", "回到了", "转身离开", "安然入睡",
    "这一夜格外平静", "故事就这样",
]

# 章末台词：以角色的话收尾是最常见的断章手法
_DIALOGUE_TAIL_RE = re.compile(r"[“「『\"][^”」』\"]{2,120}[”」』\"]\s*$")

# 说教型收尾：网文读者最反感，强制判 DEAD
MORALIZING_TAILS: List[str] = [
    "他明白了", "他终于懂得", "这让他深深", "人生就是", "或许这就是",
    "世间万物", "道理", "领悟到", "正如那句话",
]


@dataclass
class HookEvaluation:
    chapter_index: int
    strength: HookStrength = HookStrength.DEAD
    hook_types: List[HookType] = field(default_factory=list)
    score: float = 0.0                      # 0~10
    tail_text: str = ""
    anti_hook_hits: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    repair_hint: str = ""

    @property
    def passed(self) -> bool:
        return self.strength in (HookStrength.SOLID, HookStrength.STRONG)

    def format_summary(self) -> str:
        types = "、".join(t.value for t in self.hook_types) or "无"
        return (
            f"[章末钩子] 第{self.chapter_index}章 {self.strength.value} "
            f"(评分 {self.score:.1f}/10, 类型: {types})"
        )


@dataclass
class HookTrendReport:
    """连续章节的钩子趋势"""
    window_start: int
    window_end: int
    avg_score: float
    weak_streak: int = 0
    alerts: List[str] = field(default_factory=list)


class HookEnforcer:
    """章末钩子强制器"""

    def __init__(
        self,
        tail_lines: int = 3,
        min_acceptable_score: float = 5.0,
        weak_streak_alert_threshold: int = 3,
    ):
        self.tail_lines = tail_lines
        self.min_acceptable_score = min_acceptable_score
        self.weak_streak_alert_threshold = weak_streak_alert_threshold
        self._history: Dict[int, HookEvaluation] = {}

    # ---------- 核心评估 ----------

    def extract_tail(self, chapter_text: str) -> str:
        """提取章末有效行（忽略空行）"""
        lines = [ln.strip() for ln in chapter_text.strip().split("\n") if ln.strip()]
        return "\n".join(lines[-self.tail_lines:]) if lines else ""

    def evaluate(self, chapter_index: int, chapter_text: str) -> HookEvaluation:
        """评估单章章末钩子"""
        tail = self.extract_tail(chapter_text)
        ev = HookEvaluation(chapter_index=chapter_index, tail_text=tail)

        if not tail:
            ev.reasons.append("章末内容为空")
            ev.repair_hint = "本章没有结尾内容，必须补写一个钩子收尾。"
            self._history[chapter_index] = ev
            return ev

        # 1. 识别钩子类型
        score = 0.0
        for htype, sigs in HOOK_SIGNATURES.items():
            if any(s in tail for s in sigs):
                ev.hook_types.append(htype)

        # 类型加权。
        # 标定原则：【单独一个强钩子就应当及格】。
        # 早期权重最高只有 4.0，而及格线是 5.0，于是"刀锋已经抵住咽喉"
        # 这种教科书级危机钩子单独出现时永远判不及格——这是标定错误，
        # 而不是内容问题。现将三类主力钩子提到及格线之上。
        weights = {
            HookType.CLIFFHANGER_DANGER: 5.0,
            HookType.REVERSAL: 4.5,
            HookType.INFORMATION_BOMB: 4.5,
            HookType.NEW_ENTRANT: 4.0,
            HookType.UNANSWERED_QUESTION: 3.0,
            HookType.PROMISE: 2.0,
            HookType.EMOTIONAL_SPIKE: 1.5,
        }
        for t in ev.hook_types:
            score += weights.get(t, 0.0)
        score = min(score, 9.0)

        # 2. 结构性钩子识别
        #    纯关键词匹配会漏掉大量真实钩子。实测中
        #    「你以为你杀的真是他？」这种教科书级反转被判 0 分——
        #    因为它不含任何关键词。悬念是由【句式结构】承载的，不只是词汇。
        last_line = tail.split("\n")[-1]
        # 以台词收尾时，闭合引号会掩盖真正的句末标点，须先剥离
        core_last = last_line.rstrip("”」』\"'）)")
        is_dialogue_end = bool(_DIALOGUE_TAIL_RE.search(last_line))

        if core_last.endswith(("？", "?")):
            # 章末抛出一个未解答的问题，本身就是悬问型钩子
            if HookType.UNANSWERED_QUESTION not in ev.hook_types:
                ev.hook_types.append(HookType.UNANSWERED_QUESTION)
                score += 3.0
            ev.reasons.append("以疑问句收尾，抛出未解答的问题")
        elif core_last.endswith(("！", "!")):
            score += 0.8
            ev.reasons.append("以感叹收尾，情绪外扩")

        if core_last.endswith(("……", "…", "—", "——")):
            if HookType.UNANSWERED_QUESTION not in ev.hook_types:
                ev.hook_types.append(HookType.UNANSWERED_QUESTION)
                score += 1.5
            ev.reasons.append("以省略/破折收尾，留白悬置")

        if is_dialogue_end:
            # 把最后一句留给角色说，是网文最常见的断章手法
            score += 1.5
            ev.reasons.append("以未作答的台词收尾，断章张力足")

        if len(last_line) <= 25:
            score += 1.0
            ev.reasons.append("结尾为短促独立行，节奏干脆")

        score = min(score, 9.5)

        # 3. 反钩子扣分
        for anti in ANTI_HOOK_SIGNATURES:
            if anti in tail:
                ev.anti_hook_hits.append(anti)
                score -= 3.0
        # 4. 说教收尾：直接判死
        moralizing = [m for m in MORALIZING_TAILS if m in tail]
        if moralizing:
            ev.anti_hook_hits.extend(moralizing)
            score = min(score, 1.0)
            ev.reasons.append("检出说教式收尾，网文大忌")

        ev.score = max(0.0, min(10.0, score))

        # 5. 定级
        if ev.score >= 7.5:
            ev.strength = HookStrength.STRONG
        elif ev.score >= self.min_acceptable_score:
            ev.strength = HookStrength.SOLID
        elif ev.score >= 2.5:
            ev.strength = HookStrength.WEAK
        else:
            ev.strength = HookStrength.DEAD

        if not ev.passed:
            ev.repair_hint = self._build_repair_hint(ev)

        self._history[chapter_index] = ev
        return ev

    def _build_repair_hint(self, ev: HookEvaluation) -> str:
        parts = [
            f"本章章末钩子评级为 {ev.strength.value}（{ev.score:.1f}/10），追读率会显著受损。"
        ]
        if ev.anti_hook_hits:
            parts.append(
                f"请先删除收束性/说教性结尾：{'、'.join(ev.anti_hook_hits[:3])}。"
            )
        parts.append(
            "请改写最后 2~3 行，任选一种强钩子："
            "(a) 危机悬置——把致命威胁停在动作发生的前一瞬；"
            "(b) 信息炸弹——抛出一句颠覆此前认知的话；"
            "(c) 新角色破门——让一个未知者在最后一行现身；"
            "(d) 反转——揭示主角/反派早有后手。"
            "最后一行必须是 25 字以内的独立短句。"
        )
        return "".join(parts)

    # ---------- 趋势分析 ----------

    def analyze_trend(self, window: int = 10) -> HookTrendReport:
        """分析最近若干章的钩子趋势，捕捉"连续平淡"这种慢性死亡"""
        if not self._history:
            return HookTrendReport(window_start=0, window_end=0, avg_score=0.0)

        chapters = sorted(self._history.keys())[-window:]
        evals = [self._history[c] for c in chapters]
        avg = sum(e.score for e in evals) / len(evals)

        report = HookTrendReport(
            window_start=chapters[0],
            window_end=chapters[-1],
            avg_score=round(avg, 2),
        )

        streak = 0
        for e in reversed(evals):
            if not e.passed:
                streak += 1
            else:
                break
        report.weak_streak = streak

        if streak >= self.weak_streak_alert_threshold:
            report.alerts.append(
                f"连续 {streak} 章钩子不合格，读者流失风险极高，"
                f"建议立即插入一个强冲突事件重启节奏。"
            )
        if avg < self.min_acceptable_score:
            report.alerts.append(
                f"近 {len(evals)} 章平均钩子强度仅 {avg:.1f}，低于合格线 "
                f"{self.min_acceptable_score}，整体追读驱动力不足。"
            )
        return report

    def get_history(self) -> Dict[int, HookEvaluation]:
        return dict(self._history)
