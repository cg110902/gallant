"""
LLM Judge & Semantic Verification Mesh - 独立盲测模型裁判系统
利用大模型裁判对正文进行无偏见双盲语义断言与工业级质检：
1. 后置因果契约达成断言 (Post-conditions Fulfillment)；
2. 社会性围观机位冲击度评估 (Reaction Cam Impact)；
3. 展现而不说教纯度评估 (Show, Don't Tell)；
4. 章末悬念留存与钩子强度评估 (Cliffhanger Strength)；
5. 输出标准化 JSON 评审决策与定向微创修补建议。
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from src.novel_factory.llm.client import BaseLLMProvider, LLMGenerationResult
from src.novel_factory.schemas.beat_contract import BeatContract, PacingType


class JudgeEvaluation(BaseModel):
    """大模型裁判评审决策结构"""
    passed: bool
    overall_score: float = Field(ge=0.0, le=10.0, description="综合得分 0~10 分")
    post_conditions_fulfilled: Dict[str, bool] = Field(default_factory=dict)
    reaction_cam_score: float = Field(default=8.0, ge=0.0, le=10.0)
    show_dont_tell_score: float = Field(default=8.0, ge=0.0, le=10.0)
    cliffhanger_score: float = Field(default=8.0, ge=0.0, le=10.0)
    violations_detected: List[str] = Field(default_factory=list)
    critique: str = ""
    suggested_patch_instructions: List[str] = Field(default_factory=list)


class LLMJudge:
    """独立模型裁判引擎"""

    def __init__(
        self,
        min_pass_score: float = 7.5,
        enforce_all_postconditions: bool = True
    ):
        self.min_pass_score = min_pass_score
        self.enforce_all_postconditions = enforce_all_postconditions

    def build_judge_prompt(self, beat: BeatContract, prose: str) -> Tuple[str, str]:
        """
        构建双盲客观评审裁判 Prompt
        """
        system_prompt = """你是一名极其严苛的商业网文总编与因果逻辑裁判官。
你的职责是对输入的单节拍草稿进行客观双盲质检，绝不迎合讨好，必须找出所有偷工减料与逻辑违规。
你必须严格以合法的 JSON 格式输出评估报告，严禁包含任何前缀或解释性文本。"""

        posts_str = "\n".join([f"- {p}" for p in beat.post_conditions]) or "（无特殊后置状态）"
        prohibits_str = "\n".join([f"- {pb}" for pb in beat.strict_prohibitions]) or "（无显式禁止项）"
        micros_str = "\n".join([f"- [{m.event_id}]: {m.description}" for m in beat.micro_events]) or "（无微事件清单）"

        user_prompt = f"""【当前分镜节拍契约 (Beat Contract)】:
- 节拍编号: {beat.beat_id}
- 节奏类型: {beat.pacing_type.value}
- 必须包含在场角色: {', '.join(beat.characters_present)}
- 必须达成的后置契约:
{posts_str}
- 离散微事件清单:
{micros_str}
- 严格禁止项 (Prohibitions):
{prohibits_str}

【待评测草稿正文】:
\"\"\"
{prose}
\"\"\"

【评审要求】:
1. 逐条核验上述“必须达成的后置契约”，返回布尔值字典；
2. 检查是否有不在场角色非法开口或行动；
3. 检查是否有段末作者说教或“这一幕让他明白”等议论文句子 (Show Don't Tell)；
4. 若为 CATHARSIS_PAYOFF，评估围观者震惊反应 (Reaction Cam) 是否到位；
5. 若为 CLIFFHANGER_HOOK，评估章末悬念是否具有强烈翻页拉力；
6. 综合评分 (0~10分) 以及是否准予放行 (passed)。

【必须以如下 JSON 格式输出】:
{{
  "passed": true,
  "overall_score": 8.5,
  "post_conditions_fulfilled": {{}},
  "reaction_cam_score": 8.0,
  "show_dont_tell_score": 9.0,
  "cliffhanger_score": 8.5,
  "violations_detected": [],
  "critique": "简明评审意见",
  "suggested_patch_instructions": []
}}"""

        return system_prompt, user_prompt

    def parse_judge_response(self, raw_response: str) -> JudgeEvaluation:
        """从模型返回文本中提取并解析合法 JSON"""
        # 剥离 markdown ```json ... ``` 包裹
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw_response.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)

        # 尝试正则截取第一个 JSON 块
        json_match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
        if json_match:
            cleaned = json_match.group(1)

        data = json.loads(cleaned)
        return JudgeEvaluation(**data)

    def evaluate_beat(
        self,
        beat: BeatContract,
        prose: str,
        provider: BaseLLMProvider
    ) -> JudgeEvaluation:
        """
        调用真实或 Mock LLM Provider 进行节拍盲测评审
        """
        sys_p, user_p = self.build_judge_prompt(beat, prose)
        res: LLMGenerationResult = provider.generate(
            system_prompt=sys_p,
            user_prompt=user_p,
            temperature=0.2,  # 低温保真
            max_tokens=1000
        )
        try:
            evaluation = self.parse_judge_response(res.text)
        except Exception as e:
            # 解析容错兜底
            evaluation = JudgeEvaluation(
                passed=False,
                overall_score=0.0,
                critique=f"裁判模型返回 JSON 解析异常: {e}\n原始返回: {res.text[:200]}",
                violations_detected=["JUDGE_JSON_PARSE_ERROR"]
            )

        # 校验硬规则：如果强制要求后置条件全达成，检查布尔字典
        if self.enforce_all_postconditions and evaluation.post_conditions_fulfilled:
            all_posts_done = all(evaluation.post_conditions_fulfilled.values())
            if not all_posts_done:
                evaluation.passed = False
                evaluation.violations_detected.append("UNFULFILLED_POST_CONDITIONS")

        if evaluation.overall_score < self.min_pass_score:
            evaluation.passed = False

        return evaluation
