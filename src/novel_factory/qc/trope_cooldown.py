"""
Trope Cooldown & Fatigue Half-Life Engine
套路冷却定时器与半衰期衰减模型：
1. 离散章节冷却拦截 (Discrete Cooldown)；
2. 连续指数半衰期疲劳衰减积分 (Continuous Half-Life Fatigue Decay)；
3. 动态反转注入机制 (Trope Inversion Suggestions)。
"""

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class TropeDefinition:
    trope_id: str
    name: str
    cooldown_chapters: int
    half_life_chapters: float = 8.0  # 半衰期（章节数），疲劳度衰减一半所需章节
    base_fatigue_penalty: float = 1.0
    inversion_recommendations: List[str] = field(default_factory=list)


class HalfLifeFatigueTracker:
    """半衰期疲劳衰减积分模型"""

    def __init__(self, fatigue_threshold: float = 0.3):
        self.fatigue_threshold = fatigue_threshold
        # trope_id -> (last_chapter, accumulated_fatigue)
        self._state: Dict[str, Tuple[int, float]] = {}

    def get_fatigue_score(self, trope: TropeDefinition, current_chapter: int) -> float:
        """
        计算当前章节目标套路的累计残余疲劳度：
        S(t) = S_prev * 2 ^ (- (current_chapter - last_chapter) / half_life)
        """
        if trope.trope_id not in self._state:
            return 0.0

        last_ch, prev_fatigue = self._state[trope.trope_id]
        if current_chapter <= last_ch:
            return prev_fatigue

        elapsed = current_chapter - last_ch
        decay_factor = math.pow(0.5, elapsed / trope.half_life_chapters)
        return prev_fatigue * decay_factor

    def record_usage(self, trope: TropeDefinition, chapter_index: int) -> float:
        """登记套路使用并增加疲劳积分"""
        current_score = self.get_fatigue_score(trope, chapter_index)
        new_score = current_score + trope.base_fatigue_penalty
        self._state[trope.trope_id] = (chapter_index, new_score)
        return new_score

    def is_in_fatigue(self, trope: TropeDefinition, current_chapter: int) -> Tuple[bool, float]:
        """断言当前套路是否处于疲劳抑制期"""
        score = self.get_fatigue_score(trope, current_chapter)
        return score >= self.fatigue_threshold, score


class TropeCooldownTracker:
    """综合套路冷却与反转调度器"""

    def __init__(self, custom_tropes: Optional[List[TropeDefinition]] = None):
        self.tropes: Dict[str, TropeDefinition] = {}
        self.last_triggered_chapter: Dict[str, int] = {}
        self.half_life_tracker = HalfLifeFatigueTracker()

        if custom_tropes:
            for t in custom_tropes:
                self.tropes[t.trope_id] = t
        else:
            self._init_default_tropes()

    def _init_default_tropes(self):
        """初始化通用常见网文/叙事套路及反转建议"""
        defaults = [
            TropeDefinition(
                trope_id="AUCTION_HEIST",
                name="拍卖会竞价挑衅与暗中截胡",
                cooldown_chapters=25,
                half_life_chapters=10.0,
                inversion_recommendations=[
                    "主角主动做局抬价坑杀对手，自身根本不买",
                    "拍卖品其实是烫手山芋，反派得手后立刻引来第三方巨擘围剿",
                    "主角直接与幕后拍卖行进行合谋做庄"
                ]
            ),
            TropeDefinition(
                trope_id="FOREST_AMBUSH",
                name="密林/荒野反杀截道者",
                cooldown_chapters=15,
                half_life_chapters=6.0,
                inversion_recommendations=[
                    "主角早已布置阵法守株待兔，伪装成猎物的猎人",
                    "截道者发现主角身份后当场反水纳头便拜",
                    "第三方天灾突然降临，双方被迫联手抗险"
                ]
            ),
            TropeDefinition(
                trope_id="BETRAYAL_FRAME",
                name="同门/同僚构陷与宗门问责",
                cooldown_chapters=20,
                half_life_chapters=8.0,
                inversion_recommendations=[
                    "主角预判了构陷，提前留存物证直接在公堂反向将死诬告者",
                    "最高裁决者早已洞悉一切，暗中借主角之手清除宗门毒瘤"
                ]
            )
        ]
        for t in defaults:
            self.tropes[t.trope_id] = t

    def check_availability(
        self,
        trope_id: str,
        current_chapter: Optional[int] = None,
        chapter_index: Optional[int] = None
    ) -> Tuple[bool, int, List[str]]:
        """
        检查指定套路在当前章节是否可用
        返回: (is_available, remaining_cooldown, inversion_suggestions)
        """
        target_ch = current_chapter if current_chapter is not None else (chapter_index if chapter_index is not None else 1)
        if trope_id not in self.tropes:
            return True, 0, []

        defn = self.tropes[trope_id]
        last_ch = self.last_triggered_chapter.get(trope_id, -999)
        elapsed = target_ch - last_ch

        if elapsed >= defn.cooldown_chapters:
            # 再检查半衰期疲劳
            in_fatigue, _ = self.half_life_tracker.is_in_fatigue(defn, target_ch)
            if not in_fatigue:
                return True, 0, []

        remaining = max(1, defn.cooldown_chapters - elapsed)
        return False, remaining, defn.inversion_recommendations

    def record_trope_use(self, trope_id: str, chapter_index: int) -> None:
        """登记某套路在特定章节被触发"""
        self.last_triggered_chapter[trope_id] = chapter_index
        if trope_id in self.tropes:
            self.half_life_tracker.record_usage(self.tropes[trope_id], chapter_index)
