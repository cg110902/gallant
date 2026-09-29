"""
Repetition Detector - 配置驱动的通用套路去重与流口水退化监控引擎 (Configuration-Driven)
核心代码仅维护字符串与词频算法，所有阈值、停用词与题材敏感动词表全部由 YAML 配置文件决定。
"""

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import jieba
import yaml


@dataclass
class DroolingIncident:
    """流口水死循环异常捕获"""
    repeated_phrase: str
    repetition_count: int
    char_length: int
    sample_context: str


@dataclass
class RepetitionAnalysisReport:
    is_drooling: bool
    ttr_diversity_score: float     # Type-Token Ratio 词汇丰富度 (0.0 ~ 1.0)
    high_frequency_phrases: List[Tuple[str, int]]
    drooling_incidents: List[DroolingIncident] = field(default_factory=list)
    suggested_ban_list_for_next_chapter: List[str] = field(default_factory=list)

    def is_healthy(self, min_ttr: float = 0.35) -> bool:
        """判定文本是否未陷入流口水或词汇极度退化"""
        return (not self.is_drooling) and (self.ttr_diversity_score >= min_ttr)


class RepetitionDetector:
    """配置驱动的跨章去重与模型退化监控引擎"""

    DEFAULT_STOP_WORDS: Set[str] = {
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
        "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有",
        "看", "好", "自己", "这", "那", "他", "她", "它", "之", "与", "及", "而"
    }

    def __init__(
        self,
        config_source: Optional[Union[str, Path, Dict[str, Any]]] = None,
        min_loop_phrase_length: int = 5,
        min_loop_repetitions: int = 2,
        ttr_warning_threshold: float = 0.35,
        fatigue_saturation_count: int = 12
    ):
        self.min_loop_len = min_loop_phrase_length
        self.min_loop_reps = min_loop_repetitions
        self.ttr_warning_threshold = ttr_warning_threshold
        self.fatigue_saturation_count = fatigue_saturation_count
        self.stop_words: Set[str] = set(self.DEFAULT_STOP_WORDS)
        self.monitored_fatigue_words: List[str] = []

        if config_source:
            self.load_config(config_source)
        else:
            default_cfg = Path(__file__).resolve().parents[3] / "configs" / "rules" / "repetition.yaml"
            if default_cfg.exists():
                self.load_config(default_cfg)

    def load_config(self, source: Union[str, Path, Dict[str, Any]]) -> None:
        """从 YAML 或字典加载阈值与监控词库"""
        if isinstance(source, (str, Path)):
            with open(source, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        else:
            data = source

        drool = data.get("drooling_detection", {})
        self.min_loop_len = drool.get("min_loop_phrase_length", self.min_loop_len)
        self.min_loop_reps = drool.get("min_loop_repetitions", self.min_loop_reps)

        lex = data.get("lexical_diversity", {})
        self.ttr_warning_threshold = lex.get("ttr_warning_threshold", self.ttr_warning_threshold)

        fatigue = data.get("cross_chapter_fatigue", {})
        self.fatigue_saturation_count = fatigue.get("fatigue_saturation_count", self.fatigue_saturation_count)
        self.monitored_fatigue_words = fatigue.get("fatigue_monitored_action_verbs", [])

    def detect_streaming_drooling(self, stream_buffer: str) -> Optional[DroolingIncident]:
        """
        流式生成时实时检测死循环复读（流口水）
        基于滑动后缀模式识别
        """
        if len(stream_buffer) < self.min_loop_len * self.min_loop_reps:
            return None

        max_check_len = min(40, len(stream_buffer) // self.min_loop_reps)
        for pattern_len in range(self.min_loop_len, max_check_len + 1):
            pattern = stream_buffer[-pattern_len:]
            count = 0
            idx = len(stream_buffer)
            while idx >= pattern_len and stream_buffer[idx - pattern_len:idx] == pattern:
                count += 1
                idx -= pattern_len

            if count >= self.min_loop_reps:
                return DroolingIncident(
                    repeated_phrase=pattern,
                    repetition_count=count,
                    char_length=pattern_len,
                    sample_context=stream_buffer[-pattern_len * (count + 1):]
                )

        return None

    def analyze_lexical_diversity(self, text: str) -> Tuple[float, List[Tuple[str, int]]]:
        """计算词汇丰富度 (TTR) 与高频突异词"""
        words = [w for w in jieba.cut(text) if len(w) > 1 and w not in self.stop_words]
        if not words:
            return 1.0, []

        total_words = len(words)
        unique_words = set(words)
        ttr = len(unique_words) / total_words

        counter = Counter(words)
        high_freq = [(word, freq) for word, freq in counter.most_common(15) if freq >= 4]

        return ttr, high_freq

    def inspect_chapter(
        self,
        current_text: str,
        recent_chapters_text: Optional[List[str]] = None
    ) -> RepetitionAnalysisReport:
        """
        综合分析单章退化情况并提取跨章疲劳词
        """
        drooling_incidents: List[DroolingIncident] = []
        for i in range(len(current_text) - 40):
            sub = current_text[i:i + 120]
            incident = self.detect_streaming_drooling(sub)
            if incident and incident.repetition_count >= 3:
                drooling_incidents.append(incident)
                break

        ttr, high_freq = self.analyze_lexical_diversity(current_text)

        # 跨章疲劳词提取（基于配置文件中指定的监控词库动态比对）
        ban_list: List[str] = []
        if recent_chapters_text:
            history_counter: Counter = Counter()
            for hist_text in recent_chapters_text:
                h_words = [w for w in jieba.cut(hist_text) if len(w) > 1 and w not in self.stop_words]
                history_counter.update(h_words)

            target_words = self.monitored_fatigue_words or [w for w, _ in history_counter.most_common(50)]
            for word in target_words:
                if history_counter[word] >= self.fatigue_saturation_count:
                    ban_list.append(word)

        return RepetitionAnalysisReport(
            is_drooling=len(drooling_incidents) > 0,
            ttr_diversity_score=ttr,
            high_frequency_phrases=high_freq,
            drooling_incidents=drooling_incidents,
            suggested_ban_list_for_next_chapter=ban_list
        )
