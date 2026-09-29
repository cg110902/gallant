"""
Novel Factory Orchestrator - 工业级中控状态机编排引擎
统一整合配置挂载、双时态图谱、Codex装配、节拍渲染、双轨质检、局部Patch修补与Narrative VCS原子提交。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import yaml

from src.novel_factory.codex.codex_assembler import CodexAssembler
from src.novel_factory.codex.trope_cooldown import TropeCooldownTracker
from src.novel_factory.graph.bec_graph import BECGraph
from src.novel_factory.pipeline.beat_renderer import BeatRenderer
from src.novel_factory.pipeline.local_patcher import ChapterBeatSegment, LocalPatcher
from src.novel_factory.qc.mechanical_linter import LintReport, MechanicalLinter
from src.novel_factory.qc.repetition_detector import RepetitionAnalysisReport, RepetitionDetector
from src.novel_factory.export.manuscript_exporter import ManuscriptExporter
from src.novel_factory.llm.cost_tracker import CostTracker
from src.novel_factory.schemas.beat import BeatContract, BeatOutput
from src.novel_factory.schemas.commit import StateDelta, StoryCommit
from src.novel_factory.schemas.entity import LoreEntry
from src.novel_factory.vcs.repository import NarrativeRepository


@dataclass
class BeatProductionResult:
    beat_id: str
    prose: str
    qc_passed: bool
    lint_report: LintReport
    patch_count: int
    feedback_history: List[str]


@dataclass
class ChapterProductionResult:
    chapter_index: int
    title: str
    full_prose: str
    commit: StoryCommit
    beat_results: List[BeatProductionResult]
    repetition_report: RepetitionAnalysisReport


class NovelFactoryOrchestrator:
    """工厂流水线总编排器"""

    def __init__(
        self,
        project_config_path: Optional[str] = None,
        db_path: Optional[str] = ":memory:",
        llm_worker: Optional[Callable[[str, str], str]] = None
    ):
        self.config = {}
        if project_config_path and Path(project_config_path).exists():
            with open(project_config_path, "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f) or {}

        # 1. 初始化核心图谱与版本库
        self.graph = BECGraph(db_path=db_path)
        self.repo = NarrativeRepository(db_path=db_path, graph=self.graph)

        # 2. 初始化质检引擎 (自动挂载配置)
        qc_cfg = self.config.get("qc_pipeline", {})
        rule_packs = qc_cfg.get("rule_packs", [])
        self.linter = MechanicalLinter(rule_configs=rule_packs if rule_packs else None)
        
        rep_rules = qc_cfg.get("repetition_rules")
        self.rep_detector = RepetitionDetector(config_source=rep_rules)

        # 3. 初始化编译与渲染组件
        self.codex_assembler = CodexAssembler(max_token_budget=3500)
        self.trope_tracker = TropeCooldownTracker()
        self.patcher = LocalPatcher()
        self.renderer = BeatRenderer()

        # 4. 初始化成本追踪与全渠道导出器
        self.cost_tracker = CostTracker()
        self.exporter = ManuscriptExporter(repo=self.repo, graph=self.graph)

        # 5. LLM 生成接口（支持传入真实 API 或 Mock 回调）
        self.llm_worker = llm_worker or self._default_mock_worker

    def _default_mock_worker(self, system_prompt: str, user_prompt: str) -> str:
        """默认回退生成器（用于离线测试与基准验证）"""
        return "酸雨顺着破损的霓虹招牌滴落。\n零号收起微型激光刀，手指没有丝毫晃动。\n暗巷尽头的脚步声戛然而止。"

    def produce_beat(
        self,
        chapter_index: int,
        scene_beat: BeatContract,
        lore_entries: List[LoreEntry],
        preceding_text_buffer: str = "",
        max_patch_retries: int = 3
    ) -> BeatProductionResult:
        """
        生产单个分镜节拍：
        Codex编译 -> 初稿生成 -> 机械质检 -> (不合格则原位打补丁重绘) -> 输出达标文本
        """
        # A. 确定性装配上下文
        assembled = self.codex_assembler.assemble(
            chapter_index=chapter_index,
            scene_beat=scene_beat,
            graph=self.graph,
            lore_entries=lore_entries,
            recent_text_buffer=preceding_text_buffer
        )

        # B. 编译 Prompt 并下发给 Worker
        prompts = self.renderer.compile_writer_prompt(
            assembled_context=assembled,
            scene_beat=scene_beat
        )
        current_prose = self.llm_worker(prompts["system_prompt"], prompts["user_prompt"])
        
        # C. 首次质检
        lint_report = self.linter.lint_text(current_prose)
        patch_count = 0
        feedback_history: List[str] = []

        # D. 局部微创 Patch 循环
        while not lint_report.passed and patch_count < max_patch_retries:
            patch_count += 1
            violations_msgs = [f"{v.rule_id}: {v.message}" for v in lint_report.violations]
            feedback_history.append(f"第 {patch_count} 次打补丁: 发现违规 {len(violations_msgs)} 处")

            patch_prompt = self.patcher.generate_patch_prompt(
                target_beat_id=scene_beat.beat_id,
                original_beat_text=current_prose,
                violation_messages=violations_msgs,
                preceding_context=preceding_text_buffer,
                post_condition_reminders=scene_beat.post_conditions
            )

            # 下发微创修复
            patched_prose = self.llm_worker(prompts["system_prompt"], patch_prompt)
            current_prose = patched_prose
            lint_report = self.linter.lint_text(current_prose)

        # 记录 Token 审计与成本核算
        self.cost_tracker.record_usage(
            chapter_index=chapter_index,
            beat_id=scene_beat.beat_id,
            model_name="gemini-1.5-flash",
            input_tokens=assembled.estimated_tokens,
            cached_input_tokens=int(assembled.estimated_tokens * 0.75),
            output_tokens=max(1, len(current_prose) // 2)
        )

        return BeatProductionResult(
            beat_id=scene_beat.beat_id,
            prose=current_prose,
            qc_passed=lint_report.passed,
            lint_report=lint_report,
            patch_count=patch_count,
            feedback_history=feedback_history
        )

    def produce_chapter(
        self,
        chapter_index: int,
        title: str,
        beat_contracts: List[BeatContract],
        lore_entries: List[LoreEntry],
        state_delta: StateDelta
    ) -> ChapterProductionResult:
        """
        生产整章节：
        逐拍推进 -> 局部缝合 -> 跨章疲劳词检测 -> Narrative VCS 原子提交
        """
        segments: List[ChapterBeatSegment] = []
        beat_results: List[BeatProductionResult] = []
        rolling_buffer = ""

        # 逐拍生产
        for idx, contract in enumerate(beat_contracts, start=1):
            b_res = self.produce_beat(
                chapter_index=chapter_index,
                scene_beat=contract,
                lore_entries=lore_entries,
                preceding_text_buffer=rolling_buffer
            )
            beat_results.append(b_res)
            segments.append(ChapterBeatSegment(contract.beat_id, idx, b_res.prose))
            rolling_buffer += "\n\n" + b_res.prose

        # 组装带锚点正文与纯净正文
        anchored_full = self.patcher.format_segmented_chapter(segments)
        clean_full_prose = self.patcher.render_clean_prose(anchored_full)

        # 获取历史章节文本用于跨章疲劳词检查
        history_commits = self.repo.get_commit_log(limit=5)
        history_texts = [c.get("full_prose", "") for c in history_commits if "full_prose" in c]

        rep_report = self.rep_detector.inspect_chapter(
            current_text=clean_full_prose,
            recent_chapters_text=history_texts
        )

        # 获取本章财务成本核算
        cost_summary = self.cost_tracker.get_chapter_cost_summary(chapter_index)

        # 原子提交至 Narrative VCS 并同步推进 BEC-Graph
        commit = self.repo.commit_chapter(
            chapter_index=chapter_index,
            title=title,
            full_prose=clean_full_prose,
            state_delta=state_delta,
            qc_metrics={
                "all_beats_passed": all(b.qc_passed for b in beat_results),
                "total_patches": sum(b.patch_count for b in beat_results),
                "ttr_score": rep_report.ttr_diversity_score,
                "cost_summary": cost_summary
            }
        )

        return ChapterProductionResult(
            chapter_index=chapter_index,
            title=title,
            full_prose=clean_full_prose,
            commit=commit,
            beat_results=beat_results,
            repetition_report=rep_report
        )

    def close(self):
        self.repo.close()
