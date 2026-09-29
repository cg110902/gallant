"""
Tests for Long-Range Consistency Layer - 长程一致性层
伏笔台账 / 故事日历 / 人设指纹 / 命名冲突
"""

import pytest

from src.novel_factory.consistency.foreshadowing import (
    ForeshadowLedger,
    ForeshadowStatus,
    ForeshadowWeight,
)
from src.novel_factory.consistency.name_collision import NameCollisionDetector
from src.novel_factory.consistency.persona import (
    AddressRule,
    PersonaProfile,
    PersonaRegistry,
    SpeechRegister,
)
from src.novel_factory.consistency.timeline import (
    MINUTES_PER_DAY,
    StoryCalendar,
    StoryInstant,
    TimeOfDay,
    parse_duration_to_minutes,
)


# ==================== 伏笔台账 ====================

def test_foreshadow_overdue_is_detected():
    """埋了忘收——长篇最致命的读者背叛"""
    ledger = ForeshadowLedger()
    ledger.plant(
        foreshadow_id="fs_1", summary="主角颈后的神秘胎记",
        planted_chapter=1, weight=ForeshadowWeight.DETAIL,  # 窗口 25 章
        keywords=["胎记"],
    )
    ok_report = ledger.audit_chapter(20)
    assert not ok_report.overdue

    late_report = ledger.audit_chapter(40)
    assert len(late_report.overdue) == 1
    assert late_report.overdue[0].foreshadow_id == "fs_1"
    assert late_report.healthy is False
    assert any("必须回收伏笔" in d for d in late_report.to_writer_directives())
    ledger.close()


def test_foreshadow_payoff_clears_the_ledger():
    ledger = ForeshadowLedger()
    ledger.plant("fs_1", "神秘胎记", planted_chapter=1, keywords=["胎记"])
    assert ledger.pay_off("fs_1", chapter_index=10, evidence="揭示为皇族印记")

    rec = ledger.get("fs_1")
    assert rec.status == ForeshadowStatus.PAID_OFF
    assert rec.paid_off_chapter == 10
    assert ledger.list_open() == []
    assert ledger.audit_chapter(100).overdue == []
    ledger.close()


def test_foreshadow_memory_staleness_triggers_reminder():
    """收得太晚等于没收：读者早忘了，必须提前复述保鲜"""
    ledger = ForeshadowLedger()
    ledger.plant(
        "fs_main", "主角身世之谜", planted_chapter=1,
        weight=ForeshadowWeight.MAIN_LINE, keywords=["身世"],
    )
    report = ledger.audit_chapter(100)  # 保鲜期 60 章
    assert len(report.stale) == 1
    assert any("复述提醒" in d for d in report.to_writer_directives())
    ledger.close()


def test_foreshadow_auto_reinforce_from_text():
    ledger = ForeshadowLedger()
    ledger.plant("fs_1", "那把断剑", planted_chapter=1, keywords=["断剑"])
    n = ledger.auto_reinforce_from_text(30, "他又想起了那把断剑。")
    assert n == 1
    assert ledger.get("fs_1").last_mentioned_chapter == 30
    ledger.close()


def test_unplanted_payoff_is_detected():
    """收了没埋：突然掏出一个从没提过的救命道具"""
    ledger = ForeshadowLedger()
    ledger.plant("fs_1", "断剑", planted_chapter=1, keywords=["断剑"])
    report = ledger.audit_chapter(
        10,
        chapter_text="危急关头，他掏出了九转还魂丹。",
        declared_payoff_keywords=["九转还魂丹"],
    )
    assert "九转还魂丹" in report.unplanted_payoffs
    assert report.healthy is False
    ledger.close()


# ==================== 故事日历 ====================

@pytest.mark.parametrize("text,expected", [
    ("三日后", 3 * MINUTES_PER_DAY),
    ("次日清晨", MINUTES_PER_DAY),
    ("一炷香之后", 30),
    ("过了两个月", 60 * MINUTES_PER_DAY),
    ("十五天后", 15 * MINUTES_PER_DAY),
])
def test_duration_parsing(text, expected):
    assert parse_duration_to_minutes(text) == expected


def test_story_instant_derives_time_and_season():
    inst = StoryInstant(10 * MINUTES_PER_DAY + 20 * 60)  # 第10天 20:00
    assert inst.day == 10
    assert inst.hour == 20
    assert inst.time_of_day == TimeOfDay.NIGHT


def test_timeline_backwards_travel_is_error():
    """时序倒流：第 N 章的起点早于第 N-1 章的终点"""
    cal = StoryCalendar()
    cal.anchor_chapter(1, start_minutes=0, elapsed_minutes=MINUTES_PER_DAY)
    cal.anchor_chapter(2, start_minutes=120)  # 明显早于第1章结束

    report = cal.check_chapter(2)
    assert report.passed is False
    assert any(c.conflict_type == "TIME_TRAVEL_BACKWARDS" for c in report.conflicts)


def test_implausible_recovery_is_detected():
    """昨夜重伤，今晨龙精虎猛"""
    cal = StoryCalendar()
    cal.anchor_chapter(1, start_minutes=0, elapsed_minutes=60)
    cal.record_injury("char_a", chapter_index=1, injury_level="SEVERE")  # 需 30 天
    cal.anchor_chapter(2, start_minutes=MINUTES_PER_DAY)  # 仅过一天

    report = cal.check_chapter(2, acting_entities=["char_a"])
    assert report.passed is False
    assert any(c.conflict_type == "IMPLAUSIBLE_RECOVERY" for c in report.conflicts)


def test_recovery_after_enough_time_passes():
    cal = StoryCalendar()
    cal.anchor_chapter(1, start_minutes=0, elapsed_minutes=60)
    cal.record_injury("char_a", chapter_index=1, injury_level="MINOR")  # 需 12 小时
    cal.anchor_chapter(2, start_minutes=2 * MINUTES_PER_DAY)

    report = cal.check_chapter(2, acting_entities=["char_a"])
    assert report.passed is True


def test_overdue_appointment_is_detected():
    """第 30 章说三天后大比，第 60 章还没开打"""
    cal = StoryCalendar()
    cal.anchor_chapter(1, start_minutes=0, elapsed_minutes=60)
    cal.record_appointment("ev_duel", due_instant_minutes=3 * MINUTES_PER_DAY, description="城门大比")
    cal.anchor_chapter(2, start_minutes=30 * MINUTES_PER_DAY)

    report = cal.check_chapter(2)
    assert any(c.conflict_type == "APPOINTMENT_OVERDUE" for c in report.conflicts)
    assert cal.resolve_appointment("ev_duel") is True


def test_chapter_auto_chains_from_declared_text():
    cal = StoryCalendar()
    cal.anchor_chapter(1, start_minutes=0, elapsed_minutes=120)
    a2 = cal.anchor_chapter(2, declared_text="三日后", elapsed_minutes=60)
    assert a2.start.absolute_minutes == 120 + 3 * MINUTES_PER_DAY


# ==================== 人设一致性 ====================

def _registry() -> PersonaRegistry:
    reg = PersonaRegistry()
    reg.register_profile(PersonaProfile(
        entity_id="char_wu", name="莽夫王五",
        register=SpeechRegister.VULGAR,
        self_reference="老子",
        verbal_tics=["俺寻思"],
        forbidden_vocabulary=["综上所述"],
        tic_min_frequency_chapters=10,
    ))
    reg.register_profile(PersonaProfile(
        entity_id="char_master", name="玄清真人",
        register=SpeechRegister.ARCHAIC, self_reference="贫道",
    ))
    return reg


def test_register_drift_is_detected():
    """粗鄙武夫突然开始用书面语"""
    reg = _registry()
    report = reg.check_chapter(
        1, "莽夫王五挠了挠头。\n「综上所述，此事诚如君言。」",
        present_entities=["char_wu"],
    )
    types = [v.violation_type for v in report.violations]
    assert "REGISTER_DRIFT" in types or "FORBIDDEN_VOCABULARY" in types


def test_forbidden_vocabulary_is_error():
    reg = _registry()
    report = reg.check_chapter(
        1, "莽夫王五说：「综上所述，我们该走了。」", present_entities=["char_wu"]
    )
    assert report.passed is False
    assert any(v.violation_type == "FORBIDDEN_VOCABULARY" for v in report.violations)


def test_knowledge_boundary_breach_is_detected():
    """信息穿越：角色说出他此刻不该知道的事"""
    reg = PersonaRegistry()
    reg.register_profile(PersonaProfile(
        entity_id="char_a", name="张三",
        knowledge_boundary=["师父是被掌门所杀"],
    ))
    report = reg.check_chapter(
        5, "张三冷冷道：「我早知道师父是被掌门所杀。」", present_entities=["char_a"]
    )
    assert report.passed is False
    assert any(v.violation_type == "KNOWLEDGE_BOUNDARY_BREACH" for v in report.violations)


def test_address_rule_violation_is_detected():
    """属下当面直呼主角名讳"""
    reg = PersonaRegistry()
    reg.register_profile(PersonaProfile(entity_id="char_sub", name="小七"))
    reg.register_profile(PersonaProfile(entity_id="char_boss", name="陈无涯"))
    reg.register_address(AddressRule(
        speaker_id="char_sub", target_id="char_boss",
        face_to_face="主上", forbidden=["陈无涯", "老陈"],
    ))
    report = reg.check_chapter(1, "小七拱手：「陈无涯，属下有话要说。」")
    assert report.passed is False
    v = next(v for v in report.violations if v.violation_type == "ADDRESS_RULE_VIOLATION")
    assert "主上" in v.repair_hint


def test_address_rule_evolves_with_chapters():
    """关系演变：称谓可以随剧情改变，旧规则不应在新章节生效"""
    reg = PersonaRegistry()
    reg.register_profile(PersonaProfile(entity_id="a", name="小七"))
    reg.register_profile(PersonaProfile(entity_id="b", name="陈无涯"))
    reg.register_address(AddressRule(
        speaker_id="a", target_id="b", face_to_face="主上",
        forbidden=["陈无涯"], valid_from_chapter=1, valid_to_chapter=50,
    ))
    assert reg.get_address("a", "b", chapter_index=10) == "主上"
    assert reg.get_address("a", "b", chapter_index=80) is None

    report_late = reg.check_chapter(80, "小七笑道：「陈无涯，好久不见。」")
    assert report_late.passed is True


def test_persona_context_block_is_injectable():
    reg = _registry()
    block = reg.build_context_block(1, ["char_wu", "char_master"])
    assert "人设声纹约束" in block
    assert "老子" in block and "贫道" in block


# ==================== 命名冲突 ====================

def test_identical_names_are_fatal():
    d = NameCollisionDetector()
    report = d.check(["林动", "林动"], entity_ids=["c1", "c2"])
    assert report.passed is False
    assert any(c.collision_type == "IDENTICAL" for c in report.collisions)


def test_glyph_similar_names_are_flagged():
    d = NameCollisionDetector()
    report = d.check(["陈天雄", "陈天豪"])
    assert any(c.collision_type == "GLYPH_SIMILAR" for c in report.collisions)


def test_phonetic_similar_names_are_flagged():
    d = NameCollisionDetector()
    report = d.check(["林薇", "林蔚"])
    assert any(c.collision_type == "PHONETIC_SIMILAR" for c in report.collisions)


def test_surname_overload_is_flagged():
    d = NameCollisionDetector()
    names = ["叶凡", "叶辰", "叶轩", "叶枫", "苏沐", "秦岚", "楚河", "白起"]
    report = d.check(names)
    assert any(c.collision_type == "SURNAME_OVERLOAD" for c in report.collisions)


def test_compound_surname_is_parsed():
    d = NameCollisionDetector()
    assert d.extract_surname("欧阳修") == "欧阳"
    assert d.extract_surname("林动") == "林"


def test_new_name_admission_check():
    d = NameCollisionDetector()
    existing = ["林动", "苏沐", "秦岚"]
    ok, collisions = d.check_new_name("林动", existing)
    assert ok is False
    ok2, _ = d.check_new_name("赵青崖", existing)
    assert ok2 is True


def test_distinct_names_pass_cleanly():
    d = NameCollisionDetector()
    report = d.check(["林动", "苏沐", "秦岚", "楚河"])
    assert report.passed is True
    assert report.collisions == []
