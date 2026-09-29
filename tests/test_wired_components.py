"""
「已实例化但从未被调用」回归测试

审计发现 5 个组件被装配进编排器却从未被任何代码路径调用：
HITL 断点管理器、智能体总线、递归编译器、套路冷却追踪器、DOC 大纲控制器。
文档宣称它们存在，实际是死代码——与「质检永远通过」是同一类问题。

本测试确保它们真正参与生产，而不只是挂在 self 上。
"""

import pytest

from src.novel_factory.cli.workbench import BreakpointType, HumanDecision
from src.novel_factory.controller.outline_store import OutlineStore
from src.novel_factory.llm.client import BaseLLMProvider, LLMGenerationResult
from src.novel_factory.orchestrator import NovelFactoryOrchestrator
from src.novel_factory.schemas.beat import BeatContract, CameraAngle, MicroEvent, PacingType
from src.novel_factory.schemas.commit import StateDelta


PROSE = (
    "他的指尖压在刀刃上，指节泛白。\n"
    "远处的长街在雨里扭曲成一片模糊。\n"
    "他心里飞快盘算着退路。\n"
    "围观的人群同时倒吸一口凉气。\n"
) * 4


def _beat(ch=1, **kw) -> BeatContract:
    d = dict(
        beat_id=f"ch{ch:02d}_b01", chapter_index=ch, beat_index=1, target_words=300,
        pacing_type=PacingType.BUILD_UP, required_camera_angles=[CameraAngle.POV],
        characters_present=["char_a"], location_id="loc",
        micro_events=[MicroEvent(event_id=f"e{ch}", description="指尖压在刀刃上")],
    )
    d.update(kw)
    return BeatContract(**d)


def _orch(worker=None, **kw) -> NovelFactoryOrchestrator:
    o = NovelFactoryOrchestrator(
        db_path=":memory:", llm_worker=worker or (lambda s, u: PROSE),
        enforce_governance=False, **kw
    )
    o.contract_auditor.enforce_word_count = False
    o.contract_auditor.enforce_camera_coverage = False
    o.register_entity("char_a", "CHARACTER", "零号", created_chapter=1)
    return o


# ==================== 套路冷却 ====================

def test_trope_usage_is_auto_detected_and_recorded():
    o = _orch()
    text = "拍卖行的包厢里，起拍价被一路叫到天价，最终落槌。众人竞价激烈。"
    o.audit_chapter_governance(1, text, present_entities=["char_a"])
    assert o.trope_tracker.last_triggered_chapter.get("AUCTION_HEIST") == 1
    o.close()


def test_trope_on_cooldown_produces_writer_directive():
    o = _orch()
    o.trope_tracker.record_trope_use("AUCTION_HEIST", 10)
    directives = o.collect_governance_directives(12)
    assert any("套路冷却" in d and "拍卖" in d for d in directives)
    assert any("反转写法" in d for d in directives)
    o.close()


def test_trope_directive_disappears_after_cooldown():
    o = _orch()
    o.trope_tracker.record_trope_use("AUCTION_HEIST", 1)
    assert any("拍卖" in d for d in o.collect_governance_directives(5))
    assert not any("拍卖" in d for d in o.collect_governance_directives(200))
    o.close()


def test_trope_directives_reach_the_prompt():
    captured = {}

    def spy(sys_p, user_p):
        captured.setdefault("first", user_p)
        return PROSE

    o = _orch(worker=spy)
    o.trope_tracker.record_trope_use("FOREST_AMBUSH", 1)
    o.produce_beat(3, _beat(3), lore_entries=[])
    assert "套路冷却" in captured["first"]
    o.close()


# ==================== HITL 断点 ====================

def test_hitl_triggers_on_patch_exhaustion():
    """机器把补丁次数用光仍修不好时，必须交还给人而不是硬产"""
    o = NovelFactoryOrchestrator(
        db_path=":memory:", llm_worker=lambda s, u: "短。", enforce_governance=False
    )
    o.register_entity("char_a", "CHARACTER", "零号", created_chapter=1)
    o.produce_chapter(1, "第一章", [_beat()], [], StateDelta(chapter_index=1))

    assert o.is_paused is True
    state = o.hitl_manager.current_state
    assert state.active_breakpoint == BreakpointType.QC_FAILURE_TAKEOVER
    assert state.chapter_index == 1
    assert state.context_data["beat_ids"]
    o.close()


def test_hitl_can_be_disabled():
    o = NovelFactoryOrchestrator(
        db_path=":memory:", llm_worker=lambda s, u: "短。",
        enforce_governance=False, enable_hitl=False,
    )
    o.register_entity("char_a", "CHARACTER", "零号", created_chapter=1)
    o.produce_chapter(1, "第一章", [_beat()], [], StateDelta(chapter_index=1))
    assert o.is_paused is False
    o.close()


def test_hitl_not_triggered_on_clean_chapter():
    o = _orch()
    o.produce_chapter(1, "第一章", [_beat()], [], StateDelta(chapter_index=1))
    assert o.is_paused is False
    o.close()


def test_resolve_breakpoint_rollback_actually_rolls_back():
    """ROLLBACK 决策必须真的回滚，而不只是把状态标记改回去"""
    o = _orch()
    for ch in (1, 2):
        o.produce_chapter(ch, f"第{ch}章", [_beat(ch)], [], StateDelta(chapter_index=ch))
    assert o.repo.get_head_commit().chapter_index == 2

    o.hitl_manager.trigger_breakpoint(
        b_type=BreakpointType.QC_FAILURE_TAKEOVER, chapter_index=2,
        prompt_message="测试断点",
    )
    res = o.resolve_breakpoint(HumanDecision.ROLLBACK)
    assert res["rolled_back_to"] == 1
    assert o.repo.get_head_commit().chapter_index == 1
    assert o.is_paused is False
    o.close()


def test_hitl_financial_breakpoint_suspends_batch(tmp_path):
    """财务断点必须无条件挂起——预算是人的决定"""
    from src.novel_factory.runtime.resume import JobStatus, ResumableProducer

    o = _orch(max_cost_per_chapter=1e-9)  # 立刻进入预警
    producer = ResumableProducer(
        o, journal_path=tmp_path / "j.json", retry_backoff_seconds=0,
        suspend_on_qc_failure=False,
    )
    producer.run(
        [1, 2, 3],
        lambda ch: {"title": f"第{ch}章", "beat_contracts": [_beat(ch)],
                    "lore_entries": [], "state_delta": StateDelta(chapter_index=ch)},
    )
    statuses = {ch: j.status for ch, j in producer.journal.jobs.items()}
    assert JobStatus.SUSPENDED in statuses.values()
    o.close()


# ==================== ModelGateway（节拍级重试与熔断）====================

class _FlakyProvider(BaseLLMProvider):
    def __init__(self, fail_times: int):
        self.fail_times = fail_times
        self.calls = 0

    def generate(self, system_prompt, user_prompt, temperature=0.7, max_tokens=1500):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ConnectionError("模拟 429 限流")
        return LLMGenerationResult(
            text=PROSE, input_tokens=100, cached_input_tokens=50,
            output_tokens=200, latency_ms=1.0, model_name="mock",
        )


def test_gateway_retries_transient_failures_at_beat_level():
    """
    瞬时限流应在节拍级重试解决；若只有章级重试，
    一次 429 会导致整章重产，已写好的节拍要重新付费。
    """
    provider = _FlakyProvider(fail_times=2)
    o = NovelFactoryOrchestrator(
        db_path=":memory:", llm_provider=provider, enforce_governance=False
    )
    o.llm_gateway.config.retry_base_delay = 0
    o.contract_auditor.enforce_word_count = False
    o.contract_auditor.enforce_camera_coverage = False
    o.register_entity("char_a", "CHARACTER", "零号", created_chapter=1)

    result = o.produce_beat(1, _beat(), lore_entries=[])
    # 前两次调用被网关吞掉并自动重试，异常没有冒泡到章级
    assert provider.calls >= 3
    assert "指尖" in result.prose
    assert result.qc_passed is True
    o.close()


def test_gateway_records_real_token_usage():
    provider = _FlakyProvider(fail_times=0)
    o = NovelFactoryOrchestrator(
        db_path=":memory:", llm_provider=provider, enforce_governance=False
    )
    o.contract_auditor.enforce_word_count = False
    o.contract_auditor.enforce_camera_coverage = False
    o.register_entity("char_a", "CHARACTER", "零号", created_chapter=1)
    o.produce_beat(1, _beat(), lore_entries=[])

    summary = o.cost_auditor.audit_chapter(1)
    assert summary.total_input_tokens == 100
    assert summary.total_output_tokens == 200
    assert summary.total_cached_tokens == 50
    o.close()


def test_gateway_opens_circuit_after_repeated_failures():
    from src.novel_factory.llm.gateway import GatewayCircuitError

    provider = _FlakyProvider(fail_times=999)
    o = NovelFactoryOrchestrator(db_path=":memory:", llm_provider=provider)
    o.llm_gateway.config.retry_base_delay = 0
    o.llm_gateway.config.max_retries = 1
    o.llm_gateway.config.circuit_failure_threshold = 2

    for _ in range(2):
        with pytest.raises(RuntimeError):
            o.llm_gateway.generate("s", "u")
    with pytest.raises(GatewayCircuitError):
        o.llm_gateway.generate("s", "u")
    o.close()


# ==================== DOC 大纲控制器 ====================

def test_beat_contract_is_validated_before_spending_money():
    """契约本身写错了，应该在调用模型之前就发现"""
    o = _orch()
    bad = _beat(micro_events=[])  # 缺少微事件清单
    result = o.produce_beat(1, bad, lore_entries=[])
    assert any("契约前置校验" in f for f in result.feedback_history)
    o.close()


def test_outline_drives_chapter_title_and_beats(tmp_path):
    from src.novel_factory.schemas.beat_contract import (
        ChapterOutline, MasterArcOutline, VolumeOutline,
    )

    o = _orch()
    o.doc_outliner.set_master_arc(MasterArcOutline(
        arc_id="a", title="书名", core_theme="母题",
        protagonist_ultimate_goal="扳倒财团", world_setting_summary="世界",
        target_total_chapters=10,
    ))
    o.doc_outliner.add_volume(VolumeOutline(
        volume_index=1, volume_id="v1", title="第一卷", core_crisis="全城通缉",
        climax_milestone_id="m1", chapter_start=1, chapter_end=10,
    ))
    o.doc_outliner.add_chapter(ChapterOutline(
        chapter_index=1, title="第 1 章 破损的接口",
        core_conflict="零号在后巷被围堵", expected_cliffhanger="陌生身影走出",
        location_id="loc_alley", key_characters=["char_a"],
    ))

    plan = o.build_chapter_plan(1)
    assert plan["title"] == "第 1 章 破损的接口"
    assert all(b.location_id == "loc_alley" for b in plan["beat_contracts"])
    assert all("char_a" in b.characters_present for b in plan["beat_contracts"])
    # 大纲的冲突与钩子必须真正进入契约
    assert any("围堵" in e.description
               for b in plan["beat_contracts"] for e in b.micro_events)
    assert any("陌生身影走出" in pc for pc in plan["beat_contracts"][-1].post_conditions)
    o.close()


def test_unplanned_chapter_can_be_refused():
    o = _orch()
    with pytest.raises(ValueError) as exc:
        o.build_chapter_plan(42, require_outline=True)
    assert "尚未编写大纲" in str(exc.value)
    o.close()


def test_outline_roundtrip_survives_restart(tmp_path):
    """大纲必须持久化，否则重启后全书规划蒸发"""
    path = tmp_path / "outline.yaml"
    store = OutlineStore.scaffold(title="测试书", total_chapters=20, volumes=2)
    store.save(path)

    o = _orch()
    report = o.load_outline(path)
    assert o.doc_outliner.master_arc.title == "测试书"
    assert len(o.doc_outliner.volumes) == 2
    assert report.planned_chapters == 20
    # 演员表与全局设定必须一并往返
    assert "char_protagonist" in o.outline_store.cast
    assert o.outline_store.lore_entries()
    o.close()


def test_outline_cast_is_registered_into_graph(tmp_path):
    """
    大纲声明了角色，却没有任何环节把它们注册进图谱——
    这会让从大纲出发的生产每一章都被"未注册实体"拦死。
    """
    path = tmp_path / "outline.yaml"
    OutlineStore.scaffold(title="测试书", total_chapters=10, volumes=1).save(path)

    o = _orch()
    o.load_outline(path, bootstrap=True)
    ids = {e["entity_id"] for e in o.graph.list_entities()}
    assert {"char_protagonist", "char_antagonist"} <= ids
    o.close()


def test_outline_validation_rejects_characters_missing_from_cast(tmp_path):
    from src.novel_factory.schemas.beat_contract import ChapterOutline

    store = OutlineStore.scaffold(title="测试书", total_chapters=10, volumes=1)
    store.outliner.add_chapter(ChapterOutline(
        chapter_index=1, title="第一章", core_conflict="真实冲突",
        expected_cliffhanger="真实钩子", location_id="loc",
        key_characters=["char_不存在"],
    ))
    report = store.validate()
    assert any("不在演员表" in i.message for i in report.errors)


def test_outline_without_cast_is_rejected():
    from src.novel_factory.controller.doc_outliner import DOCOutliner
    from src.novel_factory.schemas.beat_contract import MasterArcOutline

    o = DOCOutliner()
    o.set_master_arc(MasterArcOutline(
        arc_id="a", title="书", core_theme="母题", protagonist_ultimate_goal="目标",
        world_setting_summary="世界", target_total_chapters=10,
    ))
    report = OutlineStore(o).validate()
    assert any("演员表 cast 为空" in i.message for i in report.errors)


# ==================== LLM 语义裁判（灰色地带升级）====================

class _ScriptedJudgeProvider(BaseLLMProvider):
    """按脚本返回裁判 JSON 的假 Provider"""

    def __init__(self, passed: bool, critique: str = ""):
        self.payload = (
            '{"passed": %s, "overall_score": %s, "critique": "%s", '
            '"violations_detected": [], "suggested_patch_instructions": []}'
            % ("true" if passed else "false", "8.5" if passed else "3.0", critique)
        )
        self.calls = 0

    def generate(self, system_prompt, user_prompt, temperature=0.7, max_tokens=1500):
        self.calls += 1
        return LLMGenerationResult(
            text=self.payload, input_tokens=10, cached_input_tokens=0,
            output_tokens=10, latency_ms=1.0, model_name="judge-mock",
        )


AMBIGUOUS_EVENT = "诱敌进入变电箱陷阱完成强行反黑操作"
AMBIGUOUS_PROSE = (
    "他把解码器插进变电箱的接口，指节因为用力而泛白。\n"
    "对方一步步走进巷子，战术灯扫过积水。\n"
    "屏幕上跳出一行陌生的乱码。\n"
    "他屏住呼吸，心里默数着秒数。\n"
) * 3


def _ambiguous_beat() -> BeatContract:
    return _beat(micro_events=[MicroEvent(event_id="amb", description=AMBIGUOUS_EVENT)])


def test_ambiguous_micro_event_is_escalated_to_judge():
    """机械层判不准的灰色地带，必须真的调用裁判——而不是只在文档里写"移交"" """
    judge = _ScriptedJudgeProvider(passed=True)
    o = NovelFactoryOrchestrator(
        db_path=":memory:", llm_worker=lambda s, u: AMBIGUOUS_PROSE,
        enforce_governance=False, judge_provider=judge,
    )
    o.contract_auditor.enforce_word_count = False
    o.contract_auditor.enforce_camera_coverage = False
    o.register_entity("char_a", "CHARACTER", "零号", created_chapter=1)

    result = o.produce_beat(1, _ambiguous_beat(), lore_entries=[])

    if result.contract_report.missing_micro_events:
        assert judge.calls >= 1, "存在存疑微事件时必须调用语义裁判"
        assert result.judge_evaluation is not None
    o.close()


def test_judge_can_clear_an_ambiguous_flag():
    judge = _ScriptedJudgeProvider(passed=True)
    o = NovelFactoryOrchestrator(
        db_path=":memory:", llm_worker=lambda s, u: AMBIGUOUS_PROSE,
        enforce_governance=False, judge_provider=judge,
    )
    o.contract_auditor.enforce_word_count = False
    o.contract_auditor.enforce_camera_coverage = False
    o.contract_auditor.high_confidence = 0.99   # 强制进入灰色地带
    o.contract_auditor.low_confidence = 0.01
    o.register_entity("char_a", "CHARACTER", "零号", created_chapter=1)

    result = o.produce_beat(1, _ambiguous_beat(), lore_entries=[])
    assert judge.calls >= 1
    assert "MICRO_EVENT_AMBIGUOUS" not in [b.clause for b in result.contract_report.breaches]
    assert any("存疑项已撤销" in f for f in result.feedback_history)
    o.close()


def test_judge_can_upgrade_an_ambiguous_flag_to_breach():
    judge = _ScriptedJudgeProvider(passed=False, critique="正文只写了插入解码器，没写反黑过程")
    o = NovelFactoryOrchestrator(
        db_path=":memory:", llm_worker=lambda s, u: AMBIGUOUS_PROSE,
        enforce_governance=False, judge_provider=judge,
    )
    o.contract_auditor.enforce_word_count = False
    o.contract_auditor.enforce_camera_coverage = False
    o.contract_auditor.high_confidence = 0.99
    o.contract_auditor.low_confidence = 0.01
    o.register_entity("char_a", "CHARACTER", "零号", created_chapter=1)

    result = o.produce_beat(1, _ambiguous_beat(), lore_entries=[], max_patch_retries=0)
    assert result.contract_report.passed is False
    assert result.qc_passed is False
    o.close()


def test_judge_failure_does_not_break_production():
    """裁判是增强手段，它自己挂掉不能拖垮生产"""
    class _BrokenJudge(BaseLLMProvider):
        def generate(self, system_prompt, user_prompt, temperature=0.7, max_tokens=1500):
            raise ConnectionError("裁判服务不可用")

    o = NovelFactoryOrchestrator(
        db_path=":memory:", llm_worker=lambda s, u: AMBIGUOUS_PROSE,
        enforce_governance=False, judge_provider=_BrokenJudge(),
    )
    o.contract_auditor.enforce_word_count = False
    o.contract_auditor.enforce_camera_coverage = False
    o.contract_auditor.high_confidence = 0.99
    o.contract_auditor.low_confidence = 0.01
    o.register_entity("char_a", "CHARACTER", "零号", created_chapter=1)

    result = o.produce_beat(1, _ambiguous_beat(), lore_entries=[], max_patch_retries=0)
    assert any("语义裁判调用失败" in f for f in result.feedback_history)
    o.close()


def test_escalation_can_be_disabled():
    judge = _ScriptedJudgeProvider(passed=True)
    o = NovelFactoryOrchestrator(
        db_path=":memory:", llm_worker=lambda s, u: AMBIGUOUS_PROSE,
        enforce_governance=False, judge_provider=judge,
        escalate_ambiguity_to_judge=False,
    )
    o.contract_auditor.enforce_word_count = False
    o.contract_auditor.enforce_camera_coverage = False
    o.contract_auditor.high_confidence = 0.99
    o.contract_auditor.low_confidence = 0.01
    o.register_entity("char_a", "CHARACTER", "零号", created_chapter=1)

    o.produce_beat(1, _ambiguous_beat(), lore_entries=[], max_patch_retries=0)
    assert judge.calls == 0
    o.close()


# ==================== 递归级联设定检索 ====================

def _lore(entry_id, name, content, primary=None, is_global=False):
    from src.novel_factory.schemas.entity import LoreEntry
    return LoreEntry(
        entry_id=entry_id, entity_type="SYSTEM_RULE", name=name, content=content,
        primary_keys=primary or [], is_global=is_global, valid_from_chapter=1,
    )


def test_recursive_cascade_pulls_in_chained_lore():
    """
    深度世界观是链式的：A 提到 B、B 又依赖 C。
    一层关键词匹配只能带出 A，递归级联必须把 B、C 一起带出来。
    """
    o = _orch()
    lores = [
        _lore("L_A", "荒坂财团", "荒坂财团掌控着夜之城的义体黑市。", primary=["荒坂"]),
        _lore("L_B", "义体黑市", "义体黑市由赛博巫医经营，交易不留记录。", primary=["义体黑市"]),
        _lore("L_C", "赛博巫医", "赛博巫医擅长非法神经接口改造。", primary=["赛博巫医"]),
        _lore("L_X", "远古龙族", "与本书主线完全无关的设定。", primary=["龙族"]),
    ]
    beat = _beat(micro_events=[MicroEvent(event_id="e", description="零号找上荒坂的人")])
    selected = o._recursive_select_lore(lores, 1, beat, recent_text="荒坂的人找上门")
    ids = {e.entry_id for e in selected}

    assert "L_A" in ids
    assert {"L_B", "L_C"} & ids, "链式依赖的设定必须被递归带出"
    assert "L_X" not in ids, "无关设定不应被注入，白白烧 token"
    o.close()


def test_global_lore_is_always_kept():
    o = _orch()
    lores = [_lore("L_G", "世界基线", "这是全局常驻法则。", is_global=True)]
    beat = _beat()
    selected = o._recursive_select_lore(lores, 1, beat, recent_text="完全无关的文本")
    assert [e.entry_id for e in selected] == ["L_G"]
    o.close()


def test_expired_lore_is_filtered_by_chapter():
    from src.novel_factory.schemas.entity import LoreEntry
    o = _orch()
    expired = LoreEntry(
        entry_id="L_OLD", entity_type="SYSTEM_RULE", name="旧法则", content="早已失效",
        is_global=True, valid_from_chapter=1, valid_to_chapter=5,
    )
    selected = o._recursive_select_lore([expired], 50, _beat(), recent_text="")
    assert selected == []
    o.close()


def test_lore_selection_failure_degrades_gracefully():
    """级联出错不能拖垮生产，应退化为全量注入"""
    o = _orch()
    lores = [_lore("L_A", "设定A", "内容")]

    class _Boom:
        def compile(self, **kwargs):
            raise RuntimeError("级联炸了")

    o.recursive_compiler = _Boom()
    selected = o._recursive_select_lore(lores, 1, _beat(), recent_text="x")
    assert [e.entry_id for e in selected] == ["L_A"]
    o.close()


# ==================== 智能体总线接口 ====================

def test_prepare_director_task_uses_live_world_state():
    o = _orch()
    o.register_entity("char_b", "CHARACTER", "荒坂猎犬", created_chapter=1)
    task = o.prepare_subagent_task("director", chapter_index=1, chapter_goal="零号被围堵")
    assert task.chapter_index == 1
    assert "零号被围堵" in task.user_prompt
    # 必须从世界快照取真实存活角色，而不是留空
    assert "零号" in task.user_prompt or "荒坂猎犬" in task.user_prompt
    o.close()


def test_prepare_writer_task_carries_assembled_context():
    o = _orch()
    task = o.prepare_subagent_task("writer", chapter_index=1, scene_beat=_beat())
    assert task.system_prompt and task.user_prompt
    assert "ch01_b01" in task.user_prompt
    o.close()


def test_prepare_writer_task_requires_beat():
    o = _orch()
    with pytest.raises(ValueError):
        o.prepare_subagent_task("writer", chapter_index=1)
    with pytest.raises(ValueError):
        o.prepare_subagent_task("unknown_role", chapter_index=1)
    o.close()


def test_lightweight_bus_loop_warns_about_missing_gates():
    """
    总线上的轻量协同环缺少契约/不变量/风控闸门，
    必须显式告警，避免有人在生产里误用它绕过全部质检。
    """
    from src.novel_factory.agents.orchestrator_bridge import SubagentCoordinationBus
    from src.novel_factory.llm.client import MockLLMProvider

    bus = SubagentCoordinationBus()
    with pytest.warns(UserWarning, match="缺少契约"):
        bus.execute_beat_collaboration_loop(
            beat=_beat(), assembled_context="上下文",
            writer_provider=MockLLMProvider(canned_response=PROSE),
            judge_provider=MockLLMProvider(canned_response='{"passed": true, "overall_score": 8}'),
            max_patch_attempts=0,
        )


class _GarbageJudge(BaseLLMProvider):
    """返回非 JSON 的裁判（模型跑偏 / 服务降级）"""
    def generate(self, system_prompt, user_prompt, temperature=0.7, max_tokens=1500):
        return LLMGenerationResult(
            text="酸雨顺着破损的霓虹招牌滴落。", input_tokens=5, cached_input_tokens=0,
            output_tokens=5, latency_ms=1.0, model_name="garbage",
        )


def test_unusable_judge_verdict_does_not_worsen_the_verdict():
    """
    裁判解析失败时必须维持「存疑」，绝不能升级为「确定违约」。
    否则一个坏掉的裁判比没有裁判更糟——这是 fail-open 而非 fail-closed 的场景。
    """
    o = NovelFactoryOrchestrator(
        db_path=":memory:", llm_worker=lambda s, u: AMBIGUOUS_PROSE,
        enforce_governance=False, judge_provider=_GarbageJudge(),
    )
    o.contract_auditor.enforce_word_count = False
    o.contract_auditor.enforce_camera_coverage = False
    o.contract_auditor.high_confidence = 0.99
    o.contract_auditor.low_confidence = 0.01
    o.register_entity("char_a", "CHARACTER", "零号", created_chapter=1)

    result = o.produce_beat(1, _ambiguous_beat(), lore_entries=[], max_patch_retries=0)

    assert result.judge_evaluation is not None
    assert result.judge_evaluation.verdict_available is False
    assert any("维持存疑" in f for f in result.feedback_history)
    # 存疑仍是 MINOR，不得阻断
    breaches = {b.clause: b.severity for b in result.contract_report.breaches}
    if "MICRO_EVENT_AMBIGUOUS" in breaches:
        assert breaches["MICRO_EVENT_AMBIGUOUS"].value == "MINOR"
    assert result.contract_report.passed is True
    o.close()


def test_no_judge_configured_means_no_escalation():
    """没有配置裁判时不应凭空造一个假裁判来做判决"""
    o = NovelFactoryOrchestrator(
        db_path=":memory:", llm_worker=lambda s, u: AMBIGUOUS_PROSE,
        enforce_governance=False,
    )
    o.contract_auditor.enforce_word_count = False
    o.contract_auditor.enforce_camera_coverage = False
    o.contract_auditor.high_confidence = 0.99
    o.contract_auditor.low_confidence = 0.01
    o.register_entity("char_a", "CHARACTER", "零号", created_chapter=1)

    result = o.produce_beat(1, _ambiguous_beat(), lore_entries=[], max_patch_retries=0)
    assert result.judge_evaluation is None
    assert result.contract_report.passed is True
    o.close()
