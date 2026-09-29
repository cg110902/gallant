"""
Tests for Beat Contract Delivery Auditor - 节拍契约交付履约审计

重点验证「质检说通过、其实是垃圾」这一类漏洞被真正堵死。
"""

import pytest

from src.novel_factory.qc.contract_auditor import (
    BeatContractAuditor,
    ContractBreachSeverity,
    count_chinese_words,
)
from src.novel_factory.schemas.beat import BeatContract, CameraAngle, MicroEvent, PacingType


def _beat(**kwargs) -> BeatContract:
    defaults = dict(
        beat_id="ch01_b01",
        chapter_index=1,
        beat_index=1,
        target_words=700,
        pacing_type=PacingType.BUILD_UP,
        required_camera_angles=[CameraAngle.POV],
        characters_present=["char_a"],
        location_id="loc_1",
    )
    defaults.update(kwargs)
    return BeatContract(**defaults)


# ---------- 字数统计口径 ----------

def test_word_count_matches_platform_convention():
    """中文字数统计需对齐平台口径：不计空白，连续英数串折算为 1 字"""
    assert count_chinese_words("他笑了笑。") == 5
    assert count_chinese_words("  他笑了笑。  \n\n") == 5
    assert count_chinese_words("代号 Zero 出手了") == 6  # 代/号/Zero/出/手/了
    assert count_chinese_words("") == 0


# ---------- 字数契约（核心漏洞） ----------

def test_severe_under_delivery_is_fatal():
    """契约 1200 字却只交付 17 字，必须判定为致命违约——这是此前被放行的漏洞"""
    auditor = BeatContractAuditor()
    report = auditor.audit(_beat(target_words=1200), "他笑了笑。\n他笑了笑。\n他笑了笑。")

    assert report.passed is False
    clauses = [b.clause for b in report.breaches]
    assert "WORD_COUNT_UNDER_DELIVERY" in clauses
    breach = next(b for b in report.breaches if b.clause == "WORD_COUNT_UNDER_DELIVERY")
    assert breach.severity == ContractBreachSeverity.FATAL
    assert report.word_compliance_ratio < 0.05
    # 必须产出可下发的定向修复指令
    assert any("补足" in hint for hint in report.repair_instructions())


def test_mild_under_delivery_is_major_not_fatal():
    """轻度不足（>50% 但低于容差下限）应为 MAJOR，可通过打补丁挽救"""
    auditor = BeatContractAuditor(enforce_camera_coverage=False)
    prose = "刀锋停在喉前。" * 40  # 280 字
    report = auditor.audit(_beat(target_words=500, word_tolerance_ratio=0.2), prose)

    breach = next(b for b in report.breaches if b.clause == "WORD_COUNT_UNDER_DELIVERY")
    assert breach.severity == ContractBreachSeverity.MAJOR


def test_over_delivery_is_flagged():
    """超额注水同样违约"""
    auditor = BeatContractAuditor(enforce_camera_coverage=False)
    report = auditor.audit(_beat(target_words=300, word_tolerance_ratio=0.2), "雨。" * 500)
    assert "WORD_COUNT_OVER_DELIVERY" in [b.clause for b in report.breaches]


def test_compliant_word_count_passes():
    auditor = BeatContractAuditor(enforce_camera_coverage=False)
    prose = "他握紧刀柄。" * 100  # 600 字
    report = auditor.audit(_beat(target_words=600), prose)
    assert not [b for b in report.breaches if b.clause.startswith("WORD_COUNT")]


# ---------- 微事件三档判定 ----------

def test_missing_micro_event_is_fatal():
    auditor = BeatContractAuditor(enforce_word_count=False, enforce_camera_coverage=False)
    beat = _beat(micro_events=[
        MicroEvent(event_id="e1", description="主角斩断了对手的右臂")
    ])
    report = auditor.audit(beat, "他站在原地，看着远处的灯火，什么也没做。")

    assert report.passed is False
    assert "MICRO_EVENT_NOT_ADVANCED" in [b.clause for b in report.breaches]
    assert "e1" in report.missing_micro_events


def test_fulfilled_micro_event_passes():
    auditor = BeatContractAuditor(enforce_word_count=False, enforce_camera_coverage=False)
    beat = _beat(micro_events=[
        MicroEvent(event_id="e1", description="主角斩断了对手的右臂")
    ])
    report = auditor.audit(beat, "刀光一闪，主角斩断了对手的右臂，血溅三尺。")
    assert "e1" in report.fulfilled_micro_events
    assert report.passed is True


def test_ambiguous_micro_event_is_downgraded_not_fatal():
    """
    灰色地带不应致命：机械关键词匹配判不准语义，
    过度自信会导致无限返工，应降级为 MINOR 并移交语义裁判。
    """
    auditor = BeatContractAuditor(enforce_word_count=False, enforce_camera_coverage=False)
    beat = _beat(micro_events=[
        MicroEvent(event_id="e1", description="诱敌进入变电箱陷阱并强行反黑")
    ])
    prose = "他把解码器插进变电箱的接口，屏幕跳出一行乱码。对方一步步走进了巷子。"
    report = auditor.audit(beat, prose)

    clauses = [b.clause for b in report.breaches]
    assert "MICRO_EVENT_NOT_ADVANCED" not in clauses
    if "MICRO_EVENT_AMBIGUOUS" in clauses:
        b = next(x for x in report.breaches if x.clause == "MICRO_EVENT_AMBIGUOUS")
        assert b.severity == ContractBreachSeverity.MINOR
        assert report.passed is True  # MINOR 不阻断


# ---------- 镜头机位 ----------

def test_camera_coverage_insufficient_is_detected():
    auditor = BeatContractAuditor(enforce_word_count=False)
    beat = _beat(required_camera_angles=[
        CameraAngle.POV, CameraAngle.CLOSE_UP, CameraAngle.REACTION_CAM
    ])
    report = auditor.audit(beat, "天色阴沉，远处传来雷声。")
    assert "CAMERA_COVERAGE_INSUFFICIENT" in [b.clause for b in report.breaches]


def test_camera_coverage_detected_from_signatures():
    auditor = BeatContractAuditor(enforce_word_count=False)
    beat = _beat(required_camera_angles=[CameraAngle.CLOSE_UP, CameraAngle.REACTION_CAM])
    prose = "他的指尖压在刀刃上，渗出一丝血珠。围观的人群同时倒吸一口凉气。"
    report = auditor.audit(beat, prose)
    assert "CLOSE_UP" in report.covered_camera_angles
    assert "REACTION_CAM" in report.covered_camera_angles
    assert "CAMERA_COVERAGE_INSUFFICIENT" not in [b.clause for b in report.breaches]


# ---------- 禁忌与在场纪律 ----------

def test_strict_prohibition_violation_is_fatal():
    auditor = BeatContractAuditor(enforce_word_count=False, enforce_camera_coverage=False)
    beat = _beat(strict_prohibitions=["主角解释自己的招式原理"])
    prose = "主角解释自己的招式原理，说这是家传绝学。"
    report = auditor.audit(beat, prose)
    breach = next(b for b in report.breaches if b.clause == "STRICT_PROHIBITION_VIOLATED")
    assert breach.severity == ContractBreachSeverity.FATAL


def test_absent_character_intrusion_is_detected():
    """幽灵串场：未在场角色不得在本拍说话或行动"""
    auditor = BeatContractAuditor(enforce_word_count=False, enforce_camera_coverage=False)
    beat = _beat(characters_present=["char_a"])
    report = auditor.audit(
        beat,
        "李长风冷笑一声，转身离去。",
        known_character_names={"char_a": "张三", "char_b": "李长风"},
    )
    assert "ABSENT_CHARACTER_INTRUSION" in [b.clause for b in report.breaches]
    assert report.passed is False


def test_present_character_is_not_flagged():
    auditor = BeatContractAuditor(enforce_word_count=False, enforce_camera_coverage=False)
    beat = _beat(characters_present=["char_a", "char_b"])
    report = auditor.audit(
        beat,
        "李长风冷笑一声，转身离去。",
        known_character_names={"char_a": "张三", "char_b": "李长风"},
    )
    assert "ABSENT_CHARACTER_INTRUSION" not in [b.clause for b in report.breaches]


# ---------- 后置状态 ----------

def test_unmet_post_condition_is_detected():
    auditor = BeatContractAuditor(enforce_word_count=False, enforce_camera_coverage=False)
    beat = _beat(post_conditions=["寒霜剑出鞘"])
    report = auditor.audit(beat, "他抱着手站在门口，一句话也没说。")
    assert "POST_CONDITION_UNMET" in [b.clause for b in report.breaches]
