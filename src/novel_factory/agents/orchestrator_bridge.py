"""
Subagent Coordination Bus - Antigravity 专职子智能体协同总线
实现 Antigravity 原生子智能体三权分立与闭环作业：
1. novel_director: 负责大纲解耦下发、DOC 细粒度规划与因果前置断言；
2. novel_writer: 负责单节拍上下文隔离纯正文渲染（视听机位与高密度微事件）；
3. novel_judge: 负责独立客观盲测评审与后置条件验收；
4. 协同控制中枢: 自动化驱动 Writer -> Linter -> Patch -> Judge 流水线闭环。
"""

from enum import Enum
import logging
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from src.novel_factory.controller.doc_outliner import DOCOutliner
from src.novel_factory.llm.client import BaseLLMProvider, LLMGenerationResult
from src.novel_factory.pipeline.local_patcher import LocalPatcher, PatchResult
from src.novel_factory.qc.llm_judge import JudgeEvaluation, LLMJudge
from src.novel_factory.qc.mechanical_linter import LintReport, MechanicalLinter
from src.novel_factory.schemas.beat_contract import BeatContract, BeatOutput, ChapterOutline

logger = logging.getLogger(__name__)


class SubagentRole(str, Enum):
    DIRECTOR = "novel_director"
    WRITER = "novel_writer"
    JUDGE = "novel_judge"


class SubagentTaskPayload(BaseModel):
    """派发给特定子智能体的任务信封"""
    role: SubagentRole
    task_type: str  # PLAN_CHAPTER, DRAFT_BEAT, EVALUATE_BEAT, LOCAL_PATCH
    chapter_index: int
    beat_id: Optional[str] = None
    input_context: str
    constraints: List[str] = Field(default_factory=list)
    system_prompt: str
    user_prompt: str


class SubagentCoordinationBus:
    """Antigravity 多智能体协作总线"""

    def __init__(
        self,
        outliner: Optional[DOCOutliner] = None,
        linter: Optional[MechanicalLinter] = None,
        patcher: Optional[LocalPatcher] = None,
        judge: Optional[LLMJudge] = None
    ):
        self.outliner = outliner or DOCOutliner()
        self.linter = linter or MechanicalLinter()
        self.patcher = patcher or LocalPatcher()
        self.judge = judge or LLMJudge()

    def prepare_director_task(
        self,
        chapter_index: int,
        chapter_goal: str,
        active_characters: List[str]
    ) -> SubagentTaskPayload:
        """为 novel_director 生成大纲规划任务"""
        sys_p = "你是一名顶尖网文商业总导演 (novel_director)。你的任务是将章节目标分解为符合 ACL 2023 DOC 规范的标准节拍契约。"
        usr_p = f"""【第 {chapter_index} 章大纲规划任务】
核心目标: {chapter_goal}
主要出场角色: {', '.join(active_characters)}
请生成包含 4 个节拍 (BUILD_UP, COGNITIVE_GAP, CATHARSIS_PAYOFF, CLIFFHANGER_HOOK) 的完整计划。"""

        return SubagentTaskPayload(
            role=SubagentRole.DIRECTOR,
            task_type="PLAN_CHAPTER",
            chapter_index=chapter_index,
            input_context=chapter_goal,
            system_prompt=sys_p,
            user_prompt=usr_p
        )

    def prepare_writer_task(
        self,
        beat: BeatContract,
        assembled_context: str
    ) -> SubagentTaskPayload:
        """为 novel_writer 组装带机位与零说教约束的渲染任务"""
        sys_p = """你是一名专注于视听沉浸与短句节奏的主笔作家 (novel_writer)。
硬性准则：
1. 绝对不要在段落结尾出现‘这让他深深明白……’等说明文说教；
2. 严格按给定的镜头机位运镜（POV、特写、群众围观视角）；
3. 单段不超过 3 句话，关键重击与反转单独成行；
4. 严禁任何前言或解释，直接输出小说正文。"""

        events_str = "\n".join([f"- {m.description}" for m in beat.micro_events])
        cams_str = ", ".join([c.value for c in beat.required_camera_angles])
        prohibits_str = "\n".join([f"- {p}" for p in beat.strict_prohibitions]) or "无"

        usr_p = f"""【节拍创作指令: {beat.beat_id}】
时空背景与世界知识:
{assembled_context}

节奏模式: {beat.pacing_type.value}
目标字数: {beat.target_words} 字
必须覆盖机位: {cams_str}
在场角色: {', '.join(beat.characters_present)}
环境氛围: {beat.scene_atmosphere}

【必须推进完成的微事件清单】:
{events_str}

【绝对禁止项】:
{prohibits_str}

请直接输出正文："""

        return SubagentTaskPayload(
            role=SubagentRole.WRITER,
            task_type="DRAFT_BEAT",
            chapter_index=beat.chapter_index,
            beat_id=beat.beat_id,
            input_context=assembled_context,
            system_prompt=sys_p,
            user_prompt=usr_p
        )

    def execute_beat_collaboration_loop(
        self,
        beat: BeatContract,
        assembled_context: str,
        writer_provider: BaseLLMProvider,
        judge_provider: BaseLLMProvider,
        max_patch_attempts: int = 2
    ) -> BeatOutput:
        """
        核心协同环：
        Writer 生成 -> 机械质检 -> (若违规: Local Patcher 局部微创修补) -> LLM Judge 盲测验收
        """
        # 1. 调度 novel_writer 渲染第一稿
        writer_task = self.prepare_writer_task(beat, assembled_context)
        gen_res: LLMGenerationResult = writer_provider.generate(
            system_prompt=writer_task.system_prompt,
            user_prompt=writer_task.user_prompt,
            temperature=0.7,
            max_tokens=beat.target_words + 300
        )
        current_prose = gen_res.text.strip()
        current_patch_iter = 0
        feedback_history = []

        # 2. 机械化质检与 AST 剪枝
        cleaned_prose, pruned_count = self.linter.prune_tail_moralizers(current_prose)
        if pruned_count > 0:
            current_prose = cleaned_prose
            feedback_history.append(f"AST 语法树自动剪除了 {pruned_count} 处段尾说教")

        lint_report: LintReport = self.linter.lint_text(current_prose)

        # 3. 若机械质检未通过，触发局部微创补丁循环
        while not lint_report.passed and current_patch_iter < max_patch_attempts:
            current_patch_iter += 1
            feedback_history.append(f"机械质检未通过 (得分 {lint_report.score:.1f})，触发第 {current_patch_iter} 轮局部修补")

            violation_msgs = [f"Line {v.line_number}: {v.message} ({v.matched_text})" for v in lint_report.violations]
            patch_prompt = self.patcher.generate_patch_prompt(
                target_beat_id=beat.beat_id,
                original_beat_text=current_prose,
                violation_messages=violation_msgs,
                preceding_context=assembled_context[:200],
                post_condition_reminders=beat.post_conditions
            )

            patch_res = writer_provider.generate(
                system_prompt="你是一名局部文本无损清洗专家，只修补违规语句，保持上下文完好。",
                user_prompt=patch_prompt,
                temperature=0.4,
                max_tokens=beat.target_words + 200
            )
            current_prose = patch_res.text.strip()
            # 重新质检
            lint_report = self.linter.lint_text(current_prose)

        # 4. 调度 novel_judge 进行最终盲测审校
        judge_eval: JudgeEvaluation = self.judge.evaluate_beat(beat, current_prose, judge_provider)
        final_passed = lint_report.passed and judge_eval.passed

        if not judge_eval.passed:
            feedback_history.append(f"LLM 裁判扣分未通过: {judge_eval.critique}")

        return BeatOutput(
            beat_id=beat.beat_id,
            prose=current_prose,
            actual_words=len(current_prose),
            qc_passed=final_passed,
            patch_iteration=current_patch_iter,
            feedback_notes=feedback_history
        )
