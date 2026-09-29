"""
Tests for Commercial Viability Layer - 网文商业性引擎
章末钩子 / 爽点密度 / 升级节奏 / 多线调度
"""

import pytest

from src.novel_factory.commerce.hook_enforcer import HookEnforcer, HookStrength, HookType
from src.novel_factory.commerce.payoff_density import (
    EmotionValence,
    PayoffDensityMeter,
)
from src.novel_factory.commerce.power_curve import CurveShape, PowerCurveGuard
from src.novel_factory.commerce.thread_scheduler import (
    StoryThread,
    ThreadPriority,
    ThreadScheduler,
    ThreadStatus,
)
from src.novel_factory.schemas.beat import PacingType


# ==================== 章末钩子 ====================

def test_closing_ending_is_dead_hook():
    """收束性结尾 = 主动放读者走"""
    enforcer = HookEnforcer()
    ev = enforcer.evaluate(1, "战斗结束了。\n他转身离开，一切都平静下来。\n这一夜格外平静。")
    assert ev.strength == HookStrength.DEAD
    assert ev.passed is False
    assert ev.anti_hook_hits
    assert "改写最后" in ev.repair_hint


def test_moralizing_tail_is_killed():
    """说教式收尾是网文大忌，直接判死"""
    enforcer = HookEnforcer()
    ev = enforcer.evaluate(
        1,
        "刀锋停在喉前。\n一道陌生的身影缓缓走出。\n他终于懂得，人生就是一场修行。"
    )
    assert ev.strength == HookStrength.DEAD
    assert any("说教" in r for r in ev.reasons)


def test_strong_cliffhanger_is_recognized():
    enforcer = HookEnforcer()
    ev = enforcer.evaluate(
        1,
        "他反手将匕首抵住对方咽喉。\n然而就在这时，身后传来第二个脚步声。\n"
        "「原来你一直都是他们的人？」"
    )
    assert ev.strength in (HookStrength.SOLID, HookStrength.STRONG)
    assert ev.passed is True
    assert HookType.CLIFFHANGER_DANGER in ev.hook_types or HookType.REVERSAL in ev.hook_types


def test_dialogue_ending_punctuation_is_seen_through_quotes():
    """以台词收尾时，闭合引号不得掩盖真正的句末标点"""
    enforcer = HookEnforcer()
    with_quote = enforcer.evaluate(1, "身影走出。\n「你以为你杀的真是他？」")
    without_quote = enforcer.evaluate(2, "身影走出。\n你以为你杀的真是他？")
    assert with_quote.score == pytest.approx(without_quote.score)


def test_weak_streak_triggers_trend_alert():
    """连续平淡是一种慢性死亡，必须被趋势分析捕捉"""
    enforcer = HookEnforcer(weak_streak_alert_threshold=3)
    for ch in range(1, 6):
        enforcer.evaluate(ch, "他回到家，安然入睡。\n一切都平静下来。")
    trend = enforcer.analyze_trend(window=5)
    assert trend.weak_streak >= 3
    assert trend.alerts


def test_empty_chapter_tail_is_handled():
    enforcer = HookEnforcer()
    ev = enforcer.evaluate(1, "   \n\n  ")
    assert ev.strength == HookStrength.DEAD
    assert ev.repair_hint


# ==================== 爽点密度 ====================

def test_long_suppression_streak_forces_payoff():
    """连续憋屈超限 = 弃书风险，必须强制爆发"""
    meter = PayoffDensityMeter(max_suppression_streak=5)
    for ch in range(1, 8):
        meter.record_chapter(ch, valence=EmotionValence.SUPPRESSION)

    report = meter.analyze(7)
    assert report.passed is False
    assert report.suppression_streak == 7
    assert any("强制爆发" in d for d in report.directives)
    assert meter.suggest_next_valence(7) == EmotionValence.PAYOFF


def test_too_many_payoffs_triggers_resistance():
    """一路平推，爽感边际效用归零"""
    meter = PayoffDensityMeter(max_payoff_streak=4)
    for ch in range(1, 6):
        meter.record_chapter(ch, valence=EmotionValence.PAYOFF)

    report = meter.analyze(5)
    assert report.payoff_streak >= 4
    assert any("引入阻力" in d for d in report.directives)
    assert meter.suggest_next_valence(5) == EmotionValence.SUPPRESSION


def test_healthy_rhythm_passes():
    meter = PayoffDensityMeter()
    pattern = [
        EmotionValence.SUPPRESSION, EmotionValence.TENSION,
        EmotionValence.SUPPRESSION, EmotionValence.PAYOFF,
        EmotionValence.NEUTRAL, EmotionValence.TENSION,
        EmotionValence.PAYOFF,
    ]
    for i, v in enumerate(pattern, start=1):
        meter.record_chapter(i, valence=v)
    assert meter.analyze(7).passed is True


def test_valence_auto_classified_from_text():
    meter = PayoffDensityMeter()
    beat = meter.record_chapter(1, text="全场寂静，所有人倒吸一口凉气，那名长老当众跪地求饶，被狠狠打脸。")
    assert beat.valence in (EmotionValence.PAYOFF, EmotionValence.TRIUMPH)

    beat2 = meter.record_chapter(2, text="他被赶出家族，跪在地上吐血，无人相信他，只剩下屈辱与嘲讽。")
    assert beat2.valence == EmotionValence.SUPPRESSION


def test_valence_derived_from_pacing_type():
    meter = PayoffDensityMeter()
    b = meter.record_chapter(1, pacing_type=PacingType.CATHARSIS_PAYOFF)
    assert b.valence == EmotionValence.PAYOFF


def test_curve_rendering_is_stable():
    meter = PayoffDensityMeter()
    for ch in range(1, 6):
        meter.record_chapter(ch, valence=EmotionValence.TENSION)
    curve = meter.render_curve(width=10)
    assert "紧张" in curve and "█" in curve


# ==================== 升级节奏 ====================

def test_power_spike_is_error():
    """一章内战力暴涨 8 倍 = 境界体系崩坏"""
    guard = PowerCurveGuard()
    guard.set_protagonist("mc")
    guard.record(1, "mc", 100)
    guard.record(2, "mc", 900)

    report = guard.check(2)
    assert report.passed is False
    assert any(v.violation_type == "POWER_SPIKE" for v in report.violations)


def test_steady_growth_passes():
    guard = PowerCurveGuard(max_growth_ratio_per_chapter=0.35)
    guard.set_protagonist("mc")
    guard.record(1, "mc", 100)
    guard.record(2, "mc", 120)
    assert guard.check(2).passed is True


def test_no_credible_threat_is_error():
    """再无对手 = 故事张力归零"""
    guard = PowerCurveGuard()
    guard.set_protagonist("mc")
    guard.register_antagonist("boss")
    guard.record(1, "mc", 1000)
    guard.record(1, "boss", 200)

    report = guard.check(1)
    assert report.passed is False
    assert report.threat_ratio < 0.7
    assert any(v.violation_type == "NO_CREDIBLE_THREAT" for v in report.violations)


def test_tier_inflation_is_flagged():
    """境界通货膨胀：一个境界只待了几章"""
    guard = PowerCurveGuard(min_chapters_per_tier=15)
    guard.set_protagonist("mc")
    guard.record(1, "mc", 100, tier_id="TIER_1")
    guard.record(5, "mc", 130, tier_id="TIER_2")

    report = guard.check(5)
    assert any(v.violation_type == "TIER_INFLATION" for v in report.violations)


def test_ideal_curve_and_deviation():
    guard = PowerCurveGuard(target_shape=CurveShape.LINEAR)
    guard.set_protagonist("mc")
    mid = guard.ideal_power_at(50, start_power=0, end_power=1000, total_chapters=100)
    assert mid == pytest.approx(500, abs=1)

    guard.record(50, "mc", 750)
    dev = guard.deviation_from_ideal(50, 0, 1000, 100)
    assert dev > 0.4  # 明显超前


def test_power_lookup_is_temporal():
    guard = PowerCurveGuard()
    guard.record(1, "mc", 100)
    guard.record(10, "mc", 300)
    assert guard.get_power_at("mc", 5) == 100
    assert guard.get_power_at("mc", 20) == 300
    assert guard.get_power_at("unknown", 5) is None


# ==================== 多线调度 ====================

def _scheduler() -> ThreadScheduler:
    s = ThreadScheduler()
    s.register_thread(StoryThread(
        thread_id="t_main", title="复仇主线", priority=ThreadPriority.MAIN,
        introduced_chapter=1, last_advanced_chapter=1,
    ))
    s.register_thread(StoryThread(
        thread_id="t_romance", title="感情线", priority=ThreadPriority.ROMANCE,
        introduced_chapter=1, last_advanced_chapter=1,
    ))
    return s


def test_starved_thread_is_detected():
    """支线断更八十章，读者早忘光了"""
    s = _scheduler()
    report = s.check(chapter_index=40)
    starved_ids = [t.thread_id for t, _ in report.starved]
    assert "t_main" in starved_ids
    assert "t_romance" in starved_ids
    assert any("支线续更" in d for d in report.directives)


def test_advancing_thread_clears_starvation():
    s = _scheduler()
    for ch in range(1, 41):
        s.advance("t_main", ch)
        if ch % 10 == 0:
            s.advance("t_romance", ch)
    report = s.check(chapter_index=40)
    assert not [t for t, _ in report.starved if t.thread_id == "t_main"]


def test_dormant_thread_is_not_flagged():
    """显式休眠是有意为之，不应告警"""
    s = _scheduler()
    s.set_dormant("t_romance")
    report = s.check(chapter_index=100)
    assert "t_romance" not in [t.thread_id for t, _ in report.starved]


def test_close_deadline_warning():
    s = ThreadScheduler()
    s.register_thread(StoryThread(
        thread_id="t_arc", title="本卷谜题", priority=ThreadPriority.SECONDARY,
        introduced_chapter=1, last_advanced_chapter=38, must_close_by_chapter=45,
    ))
    report = s.check(chapter_index=40, close_warning_window=10)
    assert any(t.thread_id == "t_arc" for t in report.due_to_close)
    assert any("收束倒计时" in d for d in report.directives)


def test_closed_thread_is_ignored():
    s = _scheduler()
    s.close_thread("t_romance", 20)
    report = s.check(chapter_index=100)
    assert "t_romance" not in [t.thread_id for t, _ in report.starved]
    assert s.threads["t_romance"].status == ThreadStatus.CLOSED


def test_thread_suggestion_prioritizes_urgency():
    s = _scheduler()
    s.advance("t_main", 39)  # 主线刚推进
    suggestions = s.suggest_threads_for_chapter(40, slots=1)
    assert suggestions[0].thread_id == "t_romance"  # 感情线更饥饿


def test_gantt_rendering():
    s = _scheduler()
    s.advance("t_main", 1)
    s.advance("t_main", 3)
    gantt = s.render_gantt(1, 5)
    assert "复仇主线" in gantt and "█" in gantt


# ==================== 与生产链路的自动接线 ====================

def test_power_samples_are_auto_recorded_from_state_delta():
    """
    升级节奏守门员必须自动从章节 StateDelta 获取战力样本；
    否则它永远看不到数据，等于形同虚设。
    """
    from src.novel_factory.orchestrator import NovelFactoryOrchestrator
    from src.novel_factory.schemas.beat import BeatContract, CameraAngle
    from src.novel_factory.schemas.commit import StateDelta

    prose = (
        "他的指尖压在刀刃上，指节泛白。\n"
        "远处的长街在雨里扭曲成一片模糊。\n"
        "他心里飞快盘算着退路。\n"
        "围观的人群同时倒吸一口凉气。\n"
    ) * 5

    orch = NovelFactoryOrchestrator(
        db_path=":memory:", llm_worker=lambda s, u: prose, enforce_governance=False
    )
    orch.contract_auditor.enforce_word_count = False
    orch.power_guard.set_protagonist("char_a")
    orch.register_entity("char_a", "CHARACTER", "零号", created_chapter=1)

    for ch, power in ((1, 100.0), (2, 130.0)):
        beat = BeatContract(
            beat_id=f"ch{ch}_b1", chapter_index=ch, beat_index=1, target_words=300,
            pacing_type=PacingType.BUILD_UP, required_camera_angles=[CameraAngle.POV],
            characters_present=["char_a"], location_id="loc",
        )
        orch.produce_chapter(
            ch, f"第{ch}章", [beat], [],
            StateDelta(chapter_index=ch, entity_mutations={"char_a": {"power_rating": power}}),
        )

    assert orch.power_guard.get_power_at("char_a", 1) == 100.0
    assert orch.power_guard.get_power_at("char_a", 2) == 130.0
    assert orch.power_guard.check(2).protagonist_power == 130.0
    orch.close()


def test_power_spike_via_state_delta_is_caught_by_governance():
    """通过正常生产链路造成的战力暴涨，也必须被治理闸门拦下"""
    from src.novel_factory.orchestrator import NovelFactoryOrchestrator
    from src.novel_factory.schemas.beat import BeatContract, CameraAngle
    from src.novel_factory.schemas.commit import StateDelta

    prose = (
        "他的指尖压在刀刃上，指节泛白。\n"
        "远处的长街在雨里扭曲成一片模糊。\n"
        "刀锋已经抵住了他的咽喉。\n"
    ) * 6

    orch = NovelFactoryOrchestrator(
        db_path=":memory:", llm_worker=lambda s, u: prose, enforce_governance=True
    )
    orch.contract_auditor.enforce_word_count = False
    orch.contract_auditor.enforce_camera_coverage = False
    orch.power_guard.set_protagonist("char_a")
    orch.register_entity("char_a", "CHARACTER", "零号", created_chapter=1)

    for ch, power in ((1, 100.0), (2, 5000.0)):
        beat = BeatContract(
            beat_id=f"ch{ch}_b1", chapter_index=ch, beat_index=1, target_words=300,
            pacing_type=PacingType.BUILD_UP, required_camera_angles=[CameraAngle.POV],
            characters_present=["char_a"], location_id="loc",
        )
        res = orch.produce_chapter(
            ch, f"第{ch}章", [beat], [],
            StateDelta(chapter_index=ch, entity_mutations={"char_a": {"power_rating": power}}),
        )

    assert res.governance.power.passed is False
    assert any("升级节奏" in b for b in res.blockers)
    orch.close()
