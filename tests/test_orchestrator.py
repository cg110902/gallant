"""
Tests for Novel Factory Orchestrator - 状态机编排与端到端质检修补闭环测试
"""

from src.novel_factory.orchestrator import NovelFactoryOrchestrator
from src.novel_factory.schemas.beat import BeatContract, CameraAngle, PacingType
from src.novel_factory.schemas.commit import StateDelta
from src.novel_factory.schemas.entity import LoreEntry


def test_orchestrator_auto_patch_on_lint_failure():
    """测试生产节拍时遇到机械质检失败，自动触发局部微创 Patch 并在达到合格后返回"""
    call_count = 0

    def flaky_writer(sys_p: str, user_p: str) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # 第一次调用：返回带有 AI 典型说教的劣质文本
            return (
                "零号收起短刀。\n"
                "这一幕让他深深明白，弱肉强食才是永恒的真理。\n"
                "暗巷尽头恢复了死寂。"
            )
        else:
            # 第二次微创修补调用：成功清洗违规说教
            return (
                "零号收起短刀，将刀刃上的机油擦在死者衣角。\n"
                "暗巷尽头只剩下排气管道沉闷的轰鸣声。"
            )

    orchestrator = NovelFactoryOrchestrator(llm_worker=flaky_writer)

    beat = BeatContract(
        beat_id="ch01_beat01",
        chapter_index=1,
        beat_index=1,
        target_words=500,
        pacing_type=PacingType.BUILD_UP,
        characters_present=[],
        location_id="loc_alley"
    )

    result = orchestrator.produce_beat(
        chapter_index=1,
        scene_beat=beat,
        lore_entries=[]
    )

    # 必须执行了 1 次局部打补丁并成功洗掉说教
    assert result.patch_count == 1
    assert result.qc_passed is True
    assert "深深明白" not in result.prose
    assert "擦在死者衣角" in result.prose
    orchestrator.close()


def test_orchestrator_chapter_production_and_state_sync():
    """测试整章生产与图谱同步推进"""
    def clean_writer(sys_p: str, user_p: str) -> str:
        return "雨水倾盆而下。\n黑色轿车在街角骤停。\n探员推门走入夜色之中。"

    orchestrator = NovelFactoryOrchestrator(llm_worker=clean_writer)

    # 注册角色
    orchestrator.graph.register_entity("char_detective", "CHARACTER", "探员", created_chapter=1, initial_payload={"power": 100})

    b1 = BeatContract(beat_id="b1", chapter_index=1, beat_index=1, target_words=500, pacing_type=PacingType.BUILD_UP, characters_present=["char_detective"], location_id="loc_street")
    b2 = BeatContract(beat_id="b2", chapter_index=1, beat_index=2, target_words=500, pacing_type=PacingType.CLIFFHANGER_HOOK, characters_present=["char_detective"], location_id="loc_street")

    delta = StateDelta(
        chapter_index=1,
        entity_mutations={"char_detective": {"power": 180}}
    )

    ch_res = orchestrator.produce_chapter(
        chapter_index=1,
        title="第一章 雨夜伏击",
        beat_contracts=[b1, b2],
        lore_entries=[],
        state_delta=delta
    )

    assert ch_res.chapter_index == 1
    assert ch_res.commit.commit_id is not None
    assert len(ch_res.beat_results) == 2

    # 验证图谱已同步突变
    state = orchestrator.graph.get_entity_state_at("char_detective", 1)
    assert state["power"] == 180

    orchestrator.close()
