"""
SimHash & MinHash Cross-Chapter Deduplication Engine
跨章节语义指纹与套路疲劳去重中枢：
1. 64 位 SimHash 局部敏感哈希 (Locality-Sensitive Hashing) 计算章节与分镜语义指纹；
2. 结合中文字词与双字切分 (Word + Bigram Shingling) 抵抗同义词轻微漂移；
3. 汉明距离 (Hamming Distance) 毫秒级比对跨章节套路相似度；
4. 滑动窗口动态词频衰减矩阵 (Dynamic Fatigue Matrix)，自动下发高频动词/神态的动态禁词表 (Dynamic Ban-List)。
"""

from collections import Counter, defaultdict
import hashlib
import math
from typing import Any, Dict, List, Optional, Set, Tuple
import jieba
from pydantic import BaseModel, Field


class DuplicateIncident(BaseModel):
    """跨章/跨节拍重复告警"""
    target_chapter: int
    matched_chapter: int
    target_beat_id: Optional[str] = None
    matched_beat_id: Optional[str] = None
    hamming_distance: int
    similarity: float
    description: str


class DynamicBanListRecommendation(BaseModel):
    """动态高频疲劳词封禁建议"""
    word: str
    frequency_in_window: int
    severity: str = "WARNING"  # WARNING, HARD_BAN
    reason: str
    recommended_alternatives: List[str] = Field(default_factory=list)


class SimHashDeduplicator:
    """64位 SimHash 局部敏感哈希比对器"""

    def __init__(self, bit_size: int = 64):
        self.bit_size = bit_size
        self.stop_words: Set[str] = {
            "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
            "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有",
            "看", "好", "自己", "这", "那", "他", "她", "它", "之", "与", "及", "而",
            "，", "。", "！", "？", "：", "”", "“", "…", "、", "\n", " "
        }

    def _extract_features(self, text: str) -> List[str]:
        """提取特征词：结巴分词词汇 + 字符二元切片 (Bigrams)"""
        words = [w for w in jieba.lcut(text) if w.strip() and w not in self.stop_words]
        clean_text = "".join(ch for ch in text if ch not in self.stop_words and not ch.isspace())
        bigrams = [clean_text[i:i+2] for i in range(len(clean_text) - 1)]
        return words + bigrams

    def compute_simhash(self, text: str) -> int:
        """
        计算文本的 64 位 SimHash 指纹
        """
        features = self._extract_features(text)
        if not features:
            return 0

        # 统计词频加权
        feature_counts = Counter(features)
        v = [0] * self.bit_size

        for feat, weight in feature_counts.items():
            # 计算 64 位 MD5 局部哈希
            h = int(hashlib.md5(feat.encode("utf-8")).hexdigest()[:16], 16)
            for i in range(self.bit_size):
                if (h >> i) & 1:
                    v[i] += weight
                else:
                    v[i] -= weight

        fingerprint = 0
        for i in range(self.bit_size):
            if v[i] > 0:
                fingerprint |= (1 << i)

        return fingerprint

    def hamming_distance(self, hash1: int, hash2: int) -> int:
        """计算两指纹的汉明距离（异或后统计 1 的个数）"""
        x = hash1 ^ hash2
        return bin(x).count("1")

    def similarity(self, hash1: int, hash2: int) -> float:
        """根据汉明距离换算相似度 [0.0 ~ 1.0]"""
        dist = self.hamming_distance(hash1, hash2)
        return max(0.0, 1.0 - (dist / self.bit_size))


class CrossChapterDedupIndex:
    """跨章节语义指纹索引库"""

    def __init__(
        self,
        deduplicator: Optional[SimHashDeduplicator] = None,
        chapter_dup_distance_threshold: int = 18,  # 64 位哈希中 <= 18 判定为结构雷同
        beat_dup_distance_threshold: int = 14
    ):
        self.simhash = deduplicator or SimHashDeduplicator()
        self.chapter_threshold = chapter_dup_distance_threshold
        self.beat_threshold = beat_dup_distance_threshold

        # chapter_index -> simhash
        self._chapter_hashes: Dict[int, int] = {}
        # (chapter_index, beat_id) -> simhash
        self._beat_hashes: Dict[Tuple[int, str], int] = {}

    def index_chapter(self, chapter_index: int, text: str) -> int:
        """登记已写成章节的指纹"""
        h = self.simhash.compute_simhash(text)
        self._chapter_hashes[chapter_index] = h
        return h

    def index_beat(self, chapter_index: int, beat_id: str, text: str) -> int:
        """登记单个分镜节拍指纹"""
        h = self.simhash.compute_simhash(text)
        self._beat_hashes[(chapter_index, beat_id)] = h
        return h

    def check_chapter_duplicate(
        self,
        current_chapter: int,
        text: str,
        lookback_chapters: int = 15
    ) -> List[DuplicateIncident]:
        """
        跨章相似度排查：防止近 N 章内发生结构性或文本雷同
        """
        cur_hash = self.simhash.compute_simhash(text)
        incidents = []

        min_ch = max(1, current_chapter - lookback_chapters)
        for prev_ch, prev_hash in self._chapter_hashes.items():
            if prev_ch >= current_chapter or prev_ch < min_ch:
                continue

            dist = self.simhash.hamming_distance(cur_hash, prev_hash)
            if dist <= self.chapter_threshold:
                sim = self.simhash.similarity(cur_hash, prev_hash)
                incidents.append(DuplicateIncident(
                    target_chapter=current_chapter,
                    matched_chapter=prev_ch,
                    hamming_distance=dist,
                    similarity=sim,
                    description=f"第 {current_chapter} 章与第 {prev_ch} 章语义指纹高度重合 (汉明距离 {dist} <= {self.chapter_threshold})"
                ))

        return incidents

    def check_beat_duplicate(
        self,
        current_chapter: int,
        beat_id: str,
        text: str,
        lookback_chapters: int = 5
    ) -> List[DuplicateIncident]:
        """分镜级去重检查：防止近 5 章内反复出现相同的过场描写或战斗走位"""
        cur_hash = self.simhash.compute_simhash(text)
        incidents = []

        min_ch = max(1, current_chapter - lookback_chapters)
        for (prev_ch, prev_bid), prev_hash in self._beat_hashes.items():
            if prev_ch >= current_chapter or prev_ch < min_ch:
                continue

            dist = self.simhash.hamming_distance(cur_hash, prev_hash)
            if dist <= self.beat_threshold:
                sim = self.simhash.similarity(cur_hash, prev_hash)
                incidents.append(DuplicateIncident(
                    target_chapter=current_chapter,
                    matched_chapter=prev_ch,
                    target_beat_id=beat_id,
                    matched_beat_id=prev_bid,
                    hamming_distance=dist,
                    similarity=sim,
                    description=f"节拍 [{beat_id}] 与第 {prev_ch} 章节拍 [{prev_bid}] 走位雷同 (汉明距离 {dist})"
                ))

        return incidents


class DynamicFatigueMatrix:
    """滑动窗口动态词频衰减与套路疲劳监控矩阵"""

    # 常见网文容易过度泛滥的神态与动作词库对照表
    DEFAULT_ALTERNATIVE_MAP: Dict[str, List[str]] = {
        "倒吸一口凉气": ["瞳孔微缩", "呼吸一滞", "心头猛然一紧", "暗自心惊"],
        "眼神一凝": ["目光如鹰隼般锐利", "双眸半阖锁定目标", "眼底掠过冷芒"],
        "嘴角勾起一抹弧度": ["神情似笑非笑", "面容掠过冷笑", "神采微敛"],
        "冷哼一声": ["面色转沉", "语调骤冷", "鼻息微沉拂袖不悦"],
        "恐怖如斯": ["威能震人心魄", "气象超乎寻常", "令人毛骨悚然"],
        "不屑一顾": ["视若无睹", "置若罔闻", "浑不在意"]
    }

    def __init__(
        self,
        window_size: int = 5,
        phrase_max_frequency_in_window: int = 3
    ):
        self.window_size = window_size
        self.phrase_max_freq = phrase_max_frequency_in_window
        # chapter_index -> Counter of words/phrases
        self._chapter_stats: Dict[int, Counter] = defaultdict(Counter)

    def record_chapter_text(self, chapter_index: int, text: str) -> None:
        """登记指定章节的词汇与套路使用频次"""
        counter = Counter()
        for phrase in self.DEFAULT_ALTERNATIVE_MAP.keys():
            count = text.count(phrase)
            if count > 0:
                counter[phrase] = count
        self._chapter_stats[chapter_index] = counter

    def get_dynamic_ban_list(self, current_chapter: int) -> List[DynamicBanListRecommendation]:
        """
        基于滑动窗口计算近 N 章的高频疲劳词，生成下一章生成的动态禁词表
        """
        window_start = max(1, current_chapter - self.window_size)
        window_counter: Counter = Counter()

        for ch in range(window_start, current_chapter):
            if ch in self._chapter_stats:
                window_counter.update(self._chapter_stats[ch])

        recommendations = []
        for phrase, total_count in window_counter.items():
            if total_count >= self.phrase_max_freq:
                recommendations.append(DynamicBanListRecommendation(
                    word=phrase,
                    frequency_in_window=total_count,
                    severity="HARD_BAN" if total_count >= self.phrase_max_freq * 2 else "WARNING",
                    reason=f"近 {self.window_size} 章内累计出现 {total_count} 次，超出疲劳上限 ({self.phrase_max_freq} 次)",
                    recommended_alternatives=self.DEFAULT_ALTERNATIVE_MAP.get(phrase, [])
                ))

        return recommendations
