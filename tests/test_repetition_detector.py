"""
Tests for Repetition Detector - 通用跨章去重与流口水检测测试
"""

from src.novel_factory.qc.repetition_detector import RepetitionDetector


def test_streaming_drooling_loop_detection():
    """测试流式死循环复读（流口水）即时捕获"""
    detector = RepetitionDetector(min_loop_phrase_length=6, min_loop_repetitions=2)

    repeating_phrase = "刺耳的警报声撕裂了整座大厦"
    drooling_buffer = (
        "防护门瞬间落下，火花迸溅。"
        + repeating_phrase
        + repeating_phrase
        + repeating_phrase
    )

    incident = detector.detect_streaming_drooling(drooling_buffer)
    assert incident is not None
    assert incident.repetition_count >= 2
    assert repeating_phrase in incident.repeated_phrase


def test_normal_streaming_no_drooling():
    """测试正常流畅叙事不误报流口水"""
    detector = RepetitionDetector()
    normal_buffer = (
        "探员收起证件，踩灭了地上的烟头。"
        "现场的勘验报告显示，被害人离开前曾接听过一通长达五分钟的加密通话。"
        "窗台上的雨水还未风干，嫌疑人显然刚离开不久。"
    )

    incident = detector.detect_streaming_drooling(normal_buffer)
    assert incident is None


def test_lexical_diversity_analysis():
    """测试通用词汇丰富度 (TTR) 计算"""
    detector = RepetitionDetector()

    poor_text = "车辆向前开。车辆又向前开。车辆再次向前开。红灯停。红灯又停。红灯再次停。"
    ttr_poor, _ = detector.analyze_lexical_diversity(poor_text)

    rich_text = (
        "黑色轿车疾驰在盘山公路上，车轮碾过碎石溅起水雾。"
        "仪表盘上的红光闪烁不定，对讲机里传来断断续续的电流杂音。"
        "副驾驶座上的青年压低帽檐，目光紧紧锁死前方弯道的反光镜。"
    )
    ttr_rich, _ = detector.analyze_lexical_diversity(rich_text)

    assert ttr_rich > ttr_poor


def test_cross_chapter_fatigue_and_ban_list_from_config():
    """测试跨章高频词疲劳检测与动态禁令词提取"""
    # 模拟用户配置中监控的通用疲劳动词
    custom_cfg = {
        "cross_chapter_fatigue": {
            "fatigue_saturation_count": 8,
            "fatigue_monitored_action_verbs": ["拔枪", "低喝", "咆哮", "猛踩油门"]
        }
    }
    detector = RepetitionDetector(config_source=custom_cfg)

    ch1 = "警官拔枪射击，低喝道。副手拔枪掩护。" * 4
    ch2 = "歹徒猛踩油门，狂徒低喝。警官再次拔枪。" * 4

    current_ch = "雨夜中，警车在路口停稳。"
    report = detector.inspect_chapter(
        current_text=current_ch,
        recent_chapters_text=[ch1, ch2]
    )

    assert len(report.suggested_ban_list_for_next_chapter) > 0
    assert "拔枪" in report.suggested_ban_list_for_next_chapter or "低喝" in report.suggested_ban_list_for_next_chapter
