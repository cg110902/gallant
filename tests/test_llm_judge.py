import json
import pytest
from src.novel_factory.llm.client import BaseLLMProvider, LLMGenerationResult
from src.novel_factory.qc.llm_judge import JudgeEvaluation, LLMJudge
from src.novel_factory.schemas.beat_contract import (
    BeatContract,
    CameraAngle,
    MicroEvent,
    PacingType,
)


class MockJudgeProvider(BaseLLMProvider):
    """用于测试裁判裁决的响应驱动"""
    def __init__(self, response_json_dict: dict):
        self.response_dict = response_json_dict

    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.7, max_tokens: int = 1500) -> LLMGenerationResult:
        return LLMGenerationResult(
            text=f"```json\n{json.dumps(self.response_dict, ensure_ascii=False)}\n```",
            input_tokens=200,
            cached_input_tokens=100,
            output_tokens=150,
            latency_ms=15.0,
            model_name="mock-judge"
        )


@pytest.fixture
def sample_beat():
    return BeatContract(
        beat_id="ch01_b03",
        chapter_index=1,
        beat_index=3,
        target_words=700,
        pacing_type=PacingType.CATHARSIS_PAYOFF,
        required_camera_angles=[CameraAngle.CLOSE_UP, CameraAngle.REACTION_CAM],
        characters_present=["char_lin_dong", "char_lin_shan"],
        location_id="loc_training_ground",
        post_conditions=["通背九响震退林山", "石池微光未暴露"],
        strict_prohibitions=["主角解释石符奥秘"],
        micro_events=[
            MicroEvent(event_id="e1", description="通背拳轰出九响"),
            MicroEvent(event_id="e2", description="林山当场吐血败退")
        ]
    )


def test_build_judge_prompt(sample_beat):
    """测试裁判 Prompt 生成完整性与契约注入"""
    judge = LLMJudge()
    sys_p, user_p = judge.build_judge_prompt(sample_beat, "林动出拳...")

    assert "因果逻辑裁判官" in sys_p
    assert "ch01_b03" in user_p
    assert "通背九响震退林山" in user_p
    assert "主角解释石符奥秘" in user_p


def test_parse_judge_response_markdown_fences():
    """测试解析 Markdown 包裹的 JSON 响应"""
    judge = LLMJudge()
    raw = """
```json
{
  "passed": true,
  "overall_score": 8.8,
  "post_conditions_fulfilled": {"通背九响震退林山": true, "石池微光未暴露": true},
  "reaction_cam_score": 9.0,
  "show_dont_tell_score": 8.5,
  "cliffhanger_score": 8.0,
  "violations_detected": [],
  "critique": "节奏凌厉，打脸与社会性围观极为充实",
  "suggested_patch_instructions": []
}
```
"""
    eval_res = judge.parse_judge_response(raw)
    assert eval_res.passed is True
    assert eval_res.overall_score == 8.8
    assert eval_res.post_conditions_fulfilled["通背九响震退林山"] is True


def test_evaluate_beat_pass(sample_beat):
    """测试裁判评估通过流程"""
    judge = LLMJudge(min_pass_score=7.5)
    provider = MockJudgeProvider({
        "passed": True,
        "overall_score": 8.5,
        "post_conditions_fulfilled": {"通背九响震退林山": True, "石池微光未暴露": True},
        "reaction_cam_score": 8.5,
        "show_dont_tell_score": 8.5,
        "cliffhanger_score": 8.0,
        "violations_detected": [],
        "critique": "合格",
        "suggested_patch_instructions": []
    })

    result = judge.evaluate_beat(sample_beat, "合格正文...", provider)
    assert result.passed is True
    assert result.overall_score >= 7.5


def test_evaluate_beat_postcondition_missing_fails(sample_beat):
    """测试必须的后置契约未满足时强制裁定失败"""
    judge = LLMJudge(min_pass_score=7.0, enforce_all_postconditions=True)
    provider = MockJudgeProvider({
        "passed": True,  # 即使模型自身打了 pass，但后置条件漏项，裁判引擎必须硬覆盖为 False
        "overall_score": 7.2,
        "post_conditions_fulfilled": {"通背九响震退林山": True, "石池微光未暴露": False},
        "reaction_cam_score": 7.0,
        "show_dont_tell_score": 7.0,
        "cliffhanger_score": 7.0,
        "violations_detected": [],
        "critique": "石池微光未在正文中体现",
        "suggested_patch_instructions": ["在段尾增加石池微弱光泽描写"]
    })

    result = judge.evaluate_beat(sample_beat, "残缺正文...", provider)
    assert result.passed is False
    assert "UNFULFILLED_POST_CONDITIONS" in result.violations_detected
