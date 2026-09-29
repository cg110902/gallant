"""
Trope Cooldown - 网文套路疲劳防御与冷却定时器引擎
防止连载过程中频繁重复同质化桥段（如短时间内多次遭遇退婚、拍卖会截胡、密林截杀等），强制触发套路反转。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class TropeDefinition:
    trope_id: str
    name: str
    cooldown_chapters: int
    inversion_recommendations: List[str] = field(default_factory=list)


class TropeCooldownTracker:
    """套路冷却与反转调度器"""

    def __init__(self, custom_tropes: Optional[List[TropeDefinition]] = None):
        self.tropes: Dict[str, TropeDefinition] = {}
        # 记录 trope_id -> 上次引爆章节
        self.last_triggered_chapter: Dict[str, int] = {}

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
            return True, 0, []

        remaining = defn.cooldown_chapters - elapsed
        return False, remaining, defn.inversion_recommendations

    def record_trope_use(self, trope_id: str, chapter_index: int) -> None:
        """登记某套路在特定章节被触发"""
        self.last_triggered_chapter[trope_id] = chapter_index
