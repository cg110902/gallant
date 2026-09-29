import pytest
from src.novel_factory.qc.simhash_dedup import (
    SimHashDeduplicator,
    CrossChapterDedupIndex,
    DynamicFatigueMatrix,
)
from src.novel_factory.qc.trope_cooldown import (
    HalfLifeFatigueTracker,
    TropeDefinition,
    TropeCooldownTracker,
)


def test_simhash_distance_and_similarity():
    """验证 64 位 SimHash 汉明距离计算与局部敏感性"""
    sim = SimHashDeduplicator()
    
    text_a = "青阳镇后山，林动深吸一口气，周身淡青色元力翻涌，通背拳破空呼啸而出，拳风凌厉霸道，震碎数片落叶。"
    # text_b 与 text_a 结构高度相似，仅微调修饰词
    text_b = "青阳镇后山，林动深吸了一口气，周身青色元力狂涌，通背拳破空呼啸打出，拳风极为凌厉霸道，打碎数片落叶。"
    # text_c 是完全不相干的星际科幻描述
    text_c = "曲率引擎在深空银河边缘以第三宇宙速度过载轰鸣，引力波雷达捕捉到极其微弱的中子脉冲信号。"

    hash_a = sim.compute_simhash(text_a)
    hash_b = sim.compute_simhash(text_b)
    hash_c = sim.compute_simhash(text_c)

    dist_ab = sim.hamming_distance(hash_a, hash_b)
    dist_ac = sim.hamming_distance(hash_a, hash_c)

    # 局部高度相似文本汉明距离显著小于完全异构文本
    assert dist_ab < dist_ac
    assert dist_ab <= 18
    assert dist_ac >= 25
    assert sim.similarity(hash_a, hash_b) >= 0.70


def test_cross_chapter_dedup_index():
    """验证跨章节索引库排查雷同章节与走位"""
    index = CrossChapterDedupIndex(chapter_dup_distance_threshold=15)

    ch1_text = "青阳镇后山，少年林动独自在瀑布下承受水流冲刷，汗水与血水交织，他咬牙坚守，只为在家族大比一鸣惊人。"
    index.index_chapter(1, ch1_text)

    # 第 5 章文本结构雷同抄袭第 1 章
    ch5_dup_text = "青阳镇后山，少年林动一人在瀑布下忍受水流冲刷，汗水血水混杂，他紧咬牙关，只为在家族大比拔得头筹。"
    incidents = index.check_chapter_duplicate(5, ch5_dup_text, lookback_chapters=10)
    assert len(incidents) >= 1
    assert incidents[0].matched_chapter == 1
    assert incidents[0].hamming_distance <= 15

    # 第 5 章正常文本则不应误报
    ch5_fresh_text = "黑风寨深处，刀光剑影伴随着撕心裂肺的惨叫，林动目光沉静，手持长枪刺入寨主咽喉，鲜血喷溅。"
    incidents_fresh = index.check_chapter_duplicate(5, ch5_fresh_text, lookback_chapters=10)
    assert len(incidents_fresh) == 0


def test_dynamic_fatigue_matrix_ban_list():
    """验证近 5 章高频动词/神态泛滥触发 Dynamic Ban-List 及同义词下发"""
    matrix = DynamicFatigueMatrix(window_size=5, phrase_max_frequency_in_window=3)

    # 在第 1 到 4 章频繁使用 "倒吸一口凉气"
    matrix.record_chapter_text(1, "众弟子倒吸一口凉气。")
    matrix.record_chapter_text(2, "大长老也是倒吸一口凉气。")
    matrix.record_chapter_text(3, "全场众人齐齐倒吸一口凉气，气氛凝固。")
    matrix.record_chapter_text(4, "林琅天眼神一凝。")

    # 准备生成第 5 章时查询动态禁词表
    ban_list = matrix.get_dynamic_ban_list(5)
    ban_words = [b.word for b in ban_list]

    assert "倒吸一口凉气" in ban_words
    
    ban_item = next(b for b in ban_list if b.word == "倒吸一口凉气")
    assert ban_item.frequency_in_window == 3
    # 必须下发替换同义词建议，如 "瞳孔微缩", "呼吸一滞"
    assert len(ban_item.recommended_alternatives) > 0
    assert "呼吸一滞" in ban_item.recommended_alternatives


def test_half_life_decay_tracker():
    """验证半衰期疲劳衰减积分数学模型"""
    trope = TropeDefinition(
        trope_id="AUCTION_HEIST",
        name="拍卖会截胡",
        cooldown_chapters=20,
        half_life_chapters=5.0,  # 5 章衰减一半
        base_fatigue_penalty=1.0
    )
    tracker = HalfLifeFatigueTracker(fatigue_threshold=0.3)

    # 第 1 章使用套路，疲劳分 = 1.0
    score1 = tracker.record_usage(trope, chapter_index=1)
    assert pytest.approx(score1, 0.01) == 1.0

    # 第 6 章（过去 5 章 = 1 个半衰期）：残余疲劳分应当约为 0.5
    score6 = tracker.get_fatigue_score(trope, current_chapter=6)
    assert pytest.approx(score6, 0.05) == 0.5
    in_fatigue_6, _ = tracker.is_in_fatigue(trope, 6)
    assert in_fatigue_6 is True  # 0.5 >= 0.3 阈值

    # 第 11 章（过去 10 章 = 2 个半衰期）：残余疲劳分应当约为 0.25
    score11 = tracker.get_fatigue_score(trope, current_chapter=11)
    assert pytest.approx(score11, 0.05) == 0.25
    in_fatigue_11, _ = tracker.is_in_fatigue(trope, 11)
    assert in_fatigue_11 is False  # 0.25 < 0.3 阈值，疲劳解除
