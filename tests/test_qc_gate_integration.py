"""
质检闸门集成测试 - 回归此前「质检说通过、其实是垃圾」的全部已知漏洞

这些用例是本项目的安全网：它们断言的是【必须失败】的场景。
如果有人放宽了闸门，这些测试会立刻变红。
"""

import pytest

from src.novel_factory.orchestrator import NovelFactoryOrchestrator
from src.novel_factory.qc.compliance_scanner import ComplianceAction, ComplianceScanner
from src.novel_factory.schemas.beat import BeatContract, CameraAngle, MicroEvent, PacingType
from src.novel_factory.schemas.commit import StateDelta


GARBAGE = "他笑了笑。\n他笑了笑。\n他笑了笑。"

GOOD_PROSE = (
    "酸雨泼在青石地面上，腐蚀出白色的泡沫。\n"
    "他的指尖压在解码器边缘，指节泛白。\n"
    "巷口的流浪汉抬起头，瞳孔骤然收缩，连滚带爬地躲开。\n"
    "他心里飞快盘算着退路。\n"
    "远处的霓虹在雨幕里扭曲成一片血红。"
)


def _beat(chapter=1, **kwargs) -> BeatContract:
    defaults = dict(
        beat_id=f"ch{chapter:02d}_b01",
        chapter_index=chapter,
        beat_index=1,
        target_words=1200,
        pacing_type=PacingType.BUILD_UP,
        required_camera_angles=[CameraAngle.POV],
        characters_present=[],
        location_id="loc_1",
    )
    defaults.update(kwargs)
    return BeatContract(**defaults)


# ---------- 漏洞 1：字数契约形同虚设 ----------

def test_regression_17_word_garbage_must_not_pass():
    """
    历史漏洞：契约要求 1200 字，交付 17 字，系统判定「质检通过=True」。
    现在必须被拦截。
    """
    orch = NovelFactoryOrchestrator(db_path=":memory:", llm_worker=lambda s, u: GARBAGE)
    result = orch.produce_beat(1, _beat(), lore_entries=[])

    assert result.qc_passed is False
    assert result.contract_report is not None
    assert "WORD_COUNT_UNDER_DELIVERY" in [b.clause for b in result.contract_report.breaches]
    orch.close()


def test_regression_chapter_gate_rejects_garbage():
    """章级放行同样必须拒绝"""
    orch = NovelFactoryOrchestrator(db_path=":memory:", llm_worker=lambda s, u: GARBAGE)
    res = orch.produce_chapter(
        chapter_index=1, title="第一章", beat_contracts=[_beat()],
        lore_entries=[], state_delta=StateDelta(chapter_index=1),
    )
    assert res.qc_passed is False
    assert res.blockers
    assert res.commit.qc_metrics["chapter_qc_passed"] is False
    orch.close()


# ---------- 漏洞 2：SimHash 告警但不阻断 ----------

def test_regression_identical_chapters_must_be_blocked():
    """
    历史漏洞：三章一字不差，simhash 检出告警，但 qc_passed 依然为 True。
    现在雷同必须否决整章。
    """
    long_prose = GOOD_PROSE * 8  # 超过短文本可靠长度门限
    orch = NovelFactoryOrchestrator(
        db_path=":memory:", llm_worker=lambda s, u: long_prose, enforce_governance=False
    )
    orch.contract_auditor.enforce_word_count = False
    orch.contract_auditor.enforce_camera_coverage = False

    r1 = orch.produce_chapter(1, "第一章", [_beat(1)], [], StateDelta(chapter_index=1))
    r2 = orch.produce_chapter(2, "第二章", [_beat(2)], [], StateDelta(chapter_index=2))

    assert len(r2.simhash_duplicates) >= 1
    assert r2.qc_passed is False
    assert any("雷同" in b for b in r2.blockers)
    orch.close()


# ---------- 漏洞 3：未注册实体绕过不变量 ----------

def test_regression_ghost_character_cannot_bypass_invariants():
    """
    历史漏洞：orchestrator 用 `if actor_id in snap.entities` 包住不变量检查，
    于是用一个未注册的幽灵角色就能绕开「死人不能出场」这条核心军规。
    """
    orch = NovelFactoryOrchestrator(db_path=":memory:", llm_worker=lambda s, u: GOOD_PROSE)
    beat = _beat(characters_present=["ghost_不存在的人"])
    result = orch.produce_beat(1, beat, lore_entries=[])

    assert result.invariant_report is not None
    assert "ENTITY_NOT_FOUND" in [v.rule_name for v in result.invariant_report.violations]
    assert result.qc_passed is False
    orch.close()


def test_all_present_characters_are_checked_not_just_the_first():
    """历史缺陷：只断言 characters_present[0]，其余角色不受任何约束"""
    orch = NovelFactoryOrchestrator(db_path=":memory:", llm_worker=lambda s, u: GOOD_PROSE)
    orch.register_entity("char_ok", "CHARACTER", "张三", created_chapter=1)

    beat = _beat(characters_present=["char_ok", "ghost_幽灵"])
    result = orch.produce_beat(1, beat, lore_entries=[])
    violations = [v for v in result.invariant_report.violations if v.rule_name == "ENTITY_NOT_FOUND"]
    assert len(violations) == 1
    assert "ghost_幽灵" in violations[0].entity_ids
    orch.close()


def test_registered_entity_passes_invariant_check():
    """统一注册入口必须同时写入图谱与事件库，否则合法角色会被误判不存在"""
    orch = NovelFactoryOrchestrator(db_path=":memory:", llm_worker=lambda s, u: GOOD_PROSE)
    orch.register_entity("char_a", "CHARACTER", "零号", created_chapter=1)

    result = orch.produce_beat(1, _beat(characters_present=["char_a"]), lore_entries=[])
    assert "ENTITY_NOT_FOUND" not in [v.rule_name for v in result.invariant_report.violations]
    orch.close()


def test_strict_mode_can_be_relaxed_explicitly():
    """允许显式放宽，但必须是有意为之，不能是默认行为"""
    orch = NovelFactoryOrchestrator(
        db_path=":memory:", llm_worker=lambda s, u: GOOD_PROSE,
        strict_unregistered_entities=False,
    )
    result = orch.produce_beat(1, _beat(characters_present=["ghost"]), lore_entries=[])
    assert "ENTITY_NOT_FOUND" not in [v.rule_name for v in result.invariant_report.violations]
    orch.close()


# ---------- 漏洞 4：自然语言前置条件被误判为 DAG 节点缺失 ----------

def test_prose_preconditions_are_not_treated_as_dag_nodes():
    """
    历史缺陷：pre_conditions 是自然语言剧情描述，却被整体当作因果 DAG 节点 ID，
    导致每个正常节拍都误报 PREREQUISITE_NODE_NOT_FOUND。
    """
    orch = NovelFactoryOrchestrator(db_path=":memory:", llm_worker=lambda s, u: GOOD_PROSE)
    orch.register_entity("char_a", "CHARACTER", "零号", created_chapter=1)

    beat = _beat(characters_present=["char_a"], pre_conditions=["酸雨后巷遭遇围堵"])
    result = orch.produce_beat(1, beat, lore_entries=[])
    rules = [v.rule_name for v in result.invariant_report.violations]
    assert "PREREQUISITE_NODE_NOT_FOUND" not in rules
    orch.close()


# ---------- 漏洞 5：成本恒为 0 ----------

def test_cost_is_actually_accounted():
    """成本必须被真实核算到厘以下，不能因四舍五入恒显示 ¥0.0"""
    orch = NovelFactoryOrchestrator(db_path=":memory:", llm_worker=lambda s, u: GOOD_PROSE)
    orch.produce_beat(1, _beat(), lore_entries=[])
    summary = orch.cost_auditor.audit_chapter(1)
    assert summary.total_cost_cny > 0
    assert summary.total_input_tokens > 0
    orch.close()


# ---------- 过审风控 ----------

def test_compliance_blocking_term_fails_the_gate():
    scanner = ComplianceScanner(rules={
        "categories": [
            {"name": "TEST_REDLINE", "action": "BLOCK", "terms": ["违禁内容"],
             "suggestion": "必须删除"}
        ]
    })
    report = scanner.scan("这里出现了违禁内容。")
    assert report.passed is False
    assert report.blocking_hits[0].action == ComplianceAction.BLOCK


def test_compliance_detects_evasion_by_separators():
    """对抗插入分隔符的简单绕写"""
    scanner = ComplianceScanner(rules={
        "categories": [{"name": "T", "action": "BLOCK", "terms": ["违禁内容"]}]
    })
    assert scanner.scan("违 禁 内 容").passed is False
    assert scanner.scan("违-禁-内-容").passed is False


def test_compliance_review_level_does_not_block_by_default():
    scanner = ComplianceScanner(rules={
        "categories": [{"name": "T", "action": "REVIEW", "terms": ["敏感描写"]}]
    })
    assert scanner.scan("这是敏感描写。").passed is True
    assert scanner.scan("这是敏感描写。", block_on_review=True).passed is False


def test_default_compliance_pack_loads():
    scanner = ComplianceScanner.from_default_pack()
    assert scanner.categories  # 词库文件必须存在且可解析


def test_compliance_blocks_chapter_commit():
    orch = NovelFactoryOrchestrator(
        db_path=":memory:",
        llm_worker=lambda s, u: GOOD_PROSE + "\n那是一份制毒配方。",
        enforce_governance=False,
    )
    orch.contract_auditor.enforce_word_count = False
    orch.contract_auditor.enforce_camera_coverage = False
    res = orch.produce_chapter(1, "第一章", [_beat()], [], StateDelta(chapter_index=1))
    assert res.qc_passed is False
    assert any("风控" in b for b in res.blockers)
    orch.close()


# ---------- 治理闸门 ----------

def test_governance_blocks_dead_hook_chapter():
    """章末钩子失效必须能否决整章（可配置）"""
    flat_ending = GOOD_PROSE * 6 + "\n他回到家，安然入睡，一切都平静下来。"
    orch = NovelFactoryOrchestrator(
        db_path=":memory:", llm_worker=lambda s, u: flat_ending, enforce_governance=True
    )
    orch.contract_auditor.enforce_word_count = False
    orch.contract_auditor.enforce_camera_coverage = False
    res = orch.produce_chapter(1, "第一章", [_beat()], [], StateDelta(chapter_index=1))
    assert res.governance is not None
    assert res.governance.hook.passed is False
    assert any("钩子" in b for b in res.blockers)
    orch.close()


def test_governance_can_be_disabled():
    orch = NovelFactoryOrchestrator(
        db_path=":memory:", llm_worker=lambda s, u: GOOD_PROSE * 6, enforce_governance=False
    )
    orch.contract_auditor.enforce_word_count = False
    orch.contract_auditor.enforce_camera_coverage = False
    res = orch.produce_chapter(1, "第一章", [_beat()], [], StateDelta(chapter_index=1))
    assert not any("钩子" in b for b in res.blockers)
    orch.close()


def test_governance_directives_are_injected_into_prompt():
    """事前预防：治理指令必须真的进入 Writer Prompt，而不只是事后审计"""
    captured = {}

    def spy_writer(sys_p: str, user_p: str) -> str:
        captured.setdefault("first", user_p)   # 只看首次生成，后续为补丁 Prompt
        captured["last"] = user_p
        return GOOD_PROSE

    orch = NovelFactoryOrchestrator(db_path=":memory:", llm_worker=spy_writer)
    orch.foreshadow_ledger.plant(
        "fs_x", "主角颈后的胎记", planted_chapter=1, keywords=["胎记"]
    )
    for ch in range(1, 8):
        orch.payoff_meter.record_chapter(ch, valence=None, text="他被羞辱，跪在地上吐血，无人相信。")

    orch.produce_beat(8, _beat(chapter=8), lore_entries=[])
    assert "长程治理强制指令" in captured["first"]
    orch.close()


def test_persona_and_time_anchor_reach_the_prompt():
    captured = {}

    def spy_writer(sys_p: str, user_p: str) -> str:
        captured.setdefault("first", user_p)
        captured["last"] = user_p
        return GOOD_PROSE

    from src.novel_factory.consistency.persona import PersonaProfile, SpeechRegister

    orch = NovelFactoryOrchestrator(db_path=":memory:", llm_worker=spy_writer)
    orch.register_entity("char_a", "CHARACTER", "零号", created_chapter=1)
    orch.persona_registry.register_profile(PersonaProfile(
        entity_id="char_a", name="零号", register=SpeechRegister.TECHNICAL,
        self_reference="我", verbal_tics=["按协议来说"],
    ))
    orch.calendar.anchor_chapter(1, start_minutes=0, elapsed_minutes=120)

    orch.produce_beat(1, _beat(characters_present=["char_a"]), lore_entries=[])
    assert "人设声纹约束" in captured["first"]
    assert "故事内时间" in captured["first"]
    # 补丁 Prompt 同样必须携带这些约束，否则修补过程会重新引入 OOC
    assert "人设声纹约束" in captured["last"]
    assert "故事内时间" in captured["last"]
    orch.close()


# ---------- 漏洞 6：重跑章节撞事件唯一约束 ----------

def test_reproducing_a_chapter_is_idempotent():
    """
    历史缺陷：章节因质检驳回被重跑时，事件写入撞 event_id 唯一约束直接崩溃，
    导致断点续产在真实长跑中必然失败。
    """
    orch = NovelFactoryOrchestrator(
        db_path=":memory:", llm_worker=lambda s, u: GOOD_PROSE, enforce_governance=False
    )
    orch.contract_auditor.enforce_word_count = False
    orch.contract_auditor.enforce_camera_coverage = False

    delta = StateDelta(chapter_index=1, entity_mutations={"char_a": {"power_rating": 200.0}})
    orch.produce_chapter(1, "第一章", [_beat()], [], delta)
    # 同一章再生产一次不得抛异常
    orch.produce_chapter(1, "第一章", [_beat()], [], delta)
    orch.close()


def test_re_registering_entity_is_idempotent():
    """断点续产重启后会重放角色注册，必须幂等"""
    orch = NovelFactoryOrchestrator(db_path=":memory:", llm_worker=lambda s, u: GOOD_PROSE)
    orch.register_entity("char_a", "CHARACTER", "零号", created_chapter=1)
    orch.register_entity("char_a", "CHARACTER", "零号", created_chapter=1)
    assert len(orch.graph.list_entities(entity_type="CHARACTER")) == 1
    orch.close()
