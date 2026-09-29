import json
import pytest
from src.novel_factory.agents.orchestrator_bridge import (
    SubagentCoordinationBus,
    SubagentRole,
)
from src.novel_factory.llm.client import BaseLLMProvider, LLMGenerationResult
from src.novel_factory.schemas.beat_contract import (
    BeatContract,
    CameraAngle,
    MicroEvent,
    PacingType,
)


class MultiTurnMockProvider(BaseLLMProvider):
    """支持多轮应答的 Mock Provider"""
    def __init__(self, responses: list):
        self.responses = responses
        self.turn = 0

    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.7, max_tokens: int = 1500) -> LLMGenerationResult:
        resp = self.responses[min(self.turn, len(self.responses) - 1)]
        self.turn += 1
        return LLMGenerationResult(
            text=resp,
            input_tokens=150,
            cached_input_tokens=100,
            output_tokens=len(resp),
            latency_ms=10.0,
            model_name="multi-turn-mock"
        )


@pytest.fixture
def test_beat():
    return BeatContract(
        beat_id="ch01_b01",
        chapter_index=1,
        beat_index=1,
        target_words=500,
        pacing_type=PacingType.BUILD_UP,
        required_camera_angles=[CameraAngle.POV, CameraAngle.CLOSE_UP],
        characters_present=["char_lin_dong"],
        location_id="loc_yard",
        post_conditions=["练拳汗透衣背"],
        micro_events=[MicroEvent(event_id="e1", description="一遍又一遍练习通背拳")]
    )


def test_prepare_subagent_payloads(test_beat):
    """测试协同总线向 director 与 writer 分派的信封格式"""
    bus = SubagentCoordinationBus()
    
    dir_task = bus.prepare_director_task(
        chapter_index=1,
        chapter_goal="展现底层不屈与神秘奇遇开端",
        active_characters=["char_lin_dong"]
    )
    assert dir_task.role == SubagentRole.DIRECTOR
    assert "ACL 2023 DOC" in dir_task.system_prompt
    
    writer_task = bus.prepare_writer_task(test_beat, "【背景】：大雨滂沱")
    assert writer_task.role == SubagentRole.WRITER
    assert "ch01_b01" in writer_task.user_prompt
    assert "POV" in writer_task.user_prompt


def test_coordination_loop_clean_success(test_beat):
    """测试顺畅流转：Writer 产出干净正文 -> Linter 通过 -> Judge 通过"""
    bus = SubagentCoordinationBus()
    
    clean_prose = (
        "雨水冲刷着青石板。\n"
        "林动右臂骤然一沉，通背拳破空呼啸。\n"
        "汗水早已彻底湿透了衣背，练拳汗透衣背，但他没有半分停歇。"
    )
    writer_mock = MultiTurnMockProvider([clean_prose])
    
    judge_json = json.dumps({
        "passed": True,
        "overall_score": 8.8,
        "post_conditions_fulfilled": {"练拳汗透衣背": True},
        "critique": "动作到位",
        "violations_detected": []
    })
    judge_mock = MultiTurnMockProvider([judge_json])

    output = bus.execute_beat_collaboration_loop(
        beat=test_beat,
        assembled_context="青阳镇后山",
        writer_provider=writer_mock,
        judge_provider=judge_mock
    )

    assert output.qc_passed is True
    assert output.patch_iteration == 0
    assert "练拳汗透衣背" in output.prose


def test_coordination_loop_with_moralizer_pruning(test_beat):
    """测试说教修剪：Writer 夹带了段尾说教，总线 AST 自动剪枝后放行"""
    bus = SubagentCoordinationBus()
    
    slop_prose = (
        "雨水冲刷着青石板，林动出拳沉稳，练拳汗透衣背。\n"
        "这一幕让他深深明白唯有实力才是活下去的真理。"
    )
    writer_mock = MultiTurnMockProvider([slop_prose])
    
    judge_json = json.dumps({
        "passed": True,
        "overall_score": 8.0,
        "post_conditions_fulfilled": {"练拳汗透衣背": True},
        "critique": "合格",
        "violations_detected": []
    })
    judge_mock = MultiTurnMockProvider([judge_json])

    output = bus.execute_beat_collaboration_loop(
        beat=test_beat,
        assembled_context="青阳镇后山",
        writer_provider=writer_mock,
        judge_provider=judge_mock
    )

    assert output.qc_passed is True
    # 验证段尾说教已被剪除
    assert "这一幕让他深深明白" not in output.prose
    assert any("AST 语法树自动剪除" in note for note in output.feedback_notes)
