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
    # 本用例使用短样本验证固定阈值下的指纹逻辑本身，
    # 故关闭"短文本不可靠"长度门限与自适应基线校准
    index = CrossChapterDedupIndex(
        chapter_dup_distance_threshold=15, min_reliable_length=0, adaptive_baseline=False
    )

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


def test_short_text_dedup_is_suppressed():
    """短文本特征稀疏，SimHash 结论不可靠，必须抑制以避免大量误报"""
    index = CrossChapterDedupIndex(
        chapter_dup_distance_threshold=18, min_reliable_length=500, adaptive_baseline=False
    )

    short_a = "他握紧了剑，向前踏出一步。"
    short_b = "他攥住了刀，往前迈了一步。"
    index.index_chapter(1, short_a)

    # 两段极短且题材相近的文本不得被判定为跨章雷同
    assert index.check_chapter_duplicate(2, short_b, lookback_chapters=10) == []

    # 但达到可靠长度后，真正的雷同仍须被检出
    long_a = short_a * 40
    long_b = short_a * 40
    index2 = CrossChapterDedupIndex(
        chapter_dup_distance_threshold=18, min_reliable_length=500, adaptive_baseline=False
    )
    index2.index_chapter(1, long_a)
    assert len(index2.check_chapter_duplicate(2, long_b, lookback_chapters=10)) >= 1


def test_adaptive_baseline_tolerates_same_book_style():
    """
    同一本书的章节天然共享人物、场景与文风，基线相似度本就很高。
    固定绝对阈值会把正常章节全部误杀——自适应基线必须容忍这种"正常相似"。
    """
    import random

    rng = random.Random(7)
    who = ["零号", "陈九", "苏漓", "白鹭"]
    place = ["长街", "码头", "钟楼", "雾巷"]
    act = ["握紧了刀", "退后半步", "抬眼看去", "压低声音"]

    def chapter(i):
        return "".join(
            f"{rng.choice(who)}在{rng.choice(place)}{rng.choice(act)}。"
            f"空气里浮着铁锈味，远处传来汽笛。第{i}章的风格延续着前文。"
            for _ in range(30)
        )

    index = CrossChapterDedupIndex(min_reliable_length=200, adaptive_baseline=True)
    flagged = 0
    for ch in range(1, 21):
        text = chapter(ch)
        if index.check_chapter_duplicate(ch, text, lookback_chapters=15):
            flagged += 1
        index.index_chapter(ch, text)

    # 允许零星告警，但绝不能像固定阈值那样把几乎每一章都判为雷同
    assert flagged <= 4, f"自适应基线误报过多: {flagged}/20 章"
    assert index.current_baseline() is not None


def test_adaptive_baseline_still_catches_real_copy():
    """基线自适应不得放过真正的近似复制"""
    base = "他握紧了刀，向前踏出一步。夜色沉下来，远处传来汽笛。" * 30

    index = CrossChapterDedupIndex(min_reliable_length=200, adaptive_baseline=True)
    # 先喂入若干风格接近但内容不同的章节，建立基线
    for ch in range(1, 8):
        index.index_chapter(ch, base.replace("刀", f"刃{ch}").replace("汽笛", f"钟声{ch}"))
        index.check_chapter_duplicate(ch, base.replace("刀", f"刃{ch}"), lookback_chapters=15)

    # 第 9 章几乎逐字复制第 8 章
    dup = base.replace("刀", "刃7").replace("汽笛", "钟声7")
    index.index_chapter(8, dup)
    incidents = index.check_chapter_duplicate(9, dup, lookback_chapters=15)
    assert len(incidents) >= 1
    assert max(i.similarity for i in incidents) >= 0.95


def test_baseline_sample_window_is_bounded():
    """相似度样本必须有界，且基线只反映近期文风"""
    index = CrossChapterDedupIndex(min_reliable_length=100, baseline_sample_window=50)
    text = "他握紧了刀，向前踏出一步。夜色沉下来，远处传来汽笛。" * 10
    for ch in range(1, 60):
        index.check_chapter_duplicate(ch, text + str(ch), lookback_chapters=15)
        index.index_chapter(ch, text + str(ch))
    assert len(index._similarity_samples) <= 50
