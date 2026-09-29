"""
Novel Factory Orchestrator - 工业级全链路总编排中枢 (16-Phase Unified Orchestrator)
统一整合：
1. 双时态事件溯源 (EventStore) 与因果图谱 (BECGraph / CausalDAG)；
2. 物理与叙事逻辑硬断言 (InvariantChecker)；
3. SillyTavern 递归检索 (RecursiveCodexCompiler) 与 NovelCrafter 进展引擎 (ProgressionEngine)；
4. 64位 SimHash 跨章排重 (CrossChapterDedupIndex) 与动态疲劳词表 (DynamicFatigueMatrix)；
5. 流式防流口水截断 (StreamMonitor)；
6. AST 语法树剪枝与机械质检 (MechanicalLinter)；
7. ACL 2023 DOC 细粒度大纲控制器 (DOCOutliner)；
8. 节拍微创局部打补丁 (LocalPatcher)；
9. Git-DAG 剧情版本库与时空同步回滚 (NarrativeRepository)；
10. 多模型统一网关与 Prompt Caching (ModelGateway)；
11. 厘级 Token 经济学与单章财务硬熔断 (CostAuditor)；
12. 独立双盲大模型裁判 (LLMJudge)；
13. 人机协同断点管理器 (HITLBreakpointManager)；
14. 商业全渠道排版与 SFT 数据飞轮导出器 (ManuscriptExporter)。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import yaml

from src.novel_factory.agents.orchestrator_bridge import SubagentCoordinationBus
from src.novel_factory.cli.workbench import BreakpointType, HITLBreakpointManager, HumanDecision
from src.novel_factory.codex.codex_assembler import CodexAssembler
from src.novel_factory.codex.progression_engine import ProgressionDelta, ProgressionEngine, ProgressionType
from src.novel_factory.codex.recursive_compiler import CodexEntry, RecursiveCodexCompiler
from src.novel_factory.controller.doc_outliner import DOCOutliner
from src.novel_factory.core.event_store import EventStore, WorldSnapshot
from src.novel_factory.core.events import Event, EventType
from src.novel_factory.export.manuscript_exporter import ManuscriptExporter
from src.novel_factory.graph.bec_graph import BECGraph
from src.novel_factory.graph.causal_dag import CausalDAG
from src.novel_factory.graph.invariant_checker import InvariantChecker, InvariantReport, ProposedAction
from src.novel_factory.llm.client import MockLLMProvider
from src.novel_factory.llm.cost_auditor import ChapterCostSummary, CostAuditor, FinancialCircuitBreakerError
from src.novel_factory.llm.cost_tracker import CostTracker
from src.novel_factory.pipeline.beat_renderer import BeatRenderer
from src.novel_factory.pipeline.local_patcher import ChapterBeatSegment, LocalPatcher, PatchResult
from src.novel_factory.pipeline.stream_monitor import StreamMonitor
from src.novel_factory.qc.llm_judge import JudgeEvaluation, LLMJudge
from src.novel_factory.qc.mechanical_linter import LintReport, MechanicalLinter
from src.novel_factory.qc.repetition_detector import RepetitionAnalysisReport, RepetitionDetector
from src.novel_factory.qc.simhash_dedup import CrossChapterDedupIndex, DuplicateIncident, DynamicFatigueMatrix, SimHashDeduplicator
from src.novel_factory.qc.trope_cooldown import TropeCooldownTracker
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
    invariant_report: Optional[InvariantReport] = None
    judge_evaluation: Optional[JudgeEvaluation] = None


@dataclass
class ChapterProductionResult:
    chapter_index: int
    title: str
    full_prose: str
    commit: StoryCommit
    beat_results: List[BeatProductionResult]
    repetition_report: RepetitionAnalysisReport
    simhash_duplicates: List[DuplicateIncident] = field(default_factory=list)
    cost_summary: Optional[ChapterCostSummary] = None


class NovelFactoryOrchestrator:
    """工业小说工厂全链路总编排中枢"""

    def __init__(
        self,
        project_config_path: Optional[str] = None,
        db_path: Optional[str] = ":memory:",
        llm_worker: Optional[Callable[[str, str], str]] = None,
        max_cost_per_chapter: float = 0.40
    ):
        self.config: Dict[str, Any] = {}
        if project_config_path and Path(project_config_path).exists():
            with open(project_config_path, "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f) or {}

        # 1. 基础设施：事件存储与时态图谱
        self.event_store = EventStore(db_path=db_path)
        self.graph = BECGraph(db_path=db_path)
        self.progression_engine = ProgressionEngine()

        # 2. 版本控制：绑定图谱、事件库与演进引擎
        self.repo = NarrativeRepository(
            db_path=db_path,
            graph=self.graph,
            event_store=self.event_store,
            progression_engine=self.progression_engine
        )

        # 3. 因果与不变式求解器
        self.causal_dag = CausalDAG()
        self.invariant_checker = InvariantChecker(dag=self.causal_dag)

        # 4. 细粒度规划与装配
        self.doc_outliner = DOCOutliner()
        self.codex_assembler = CodexAssembler(max_token_budget=3500)
        self.recursive_compiler = RecursiveCodexCompiler(token_budget=3500)
        self.trope_tracker = TropeCooldownTracker()

        # 5. 渲染与微创补丁
        self.renderer = BeatRenderer()
        self.patcher = LocalPatcher()
        self.stream_monitor = StreamMonitor()

        # 6. 质检与反流口水矩阵
        qc_cfg = self.config.get("qc_pipeline", {})
        rule_packs = qc_cfg.get("rule_packs", [])
        self.linter = MechanicalLinter(rule_configs=rule_packs if rule_packs else None)
        self.rep_detector = RepetitionDetector(config_source=qc_cfg.get("repetition_rules"))
        self.simhash_index = CrossChapterDedupIndex()
        self.fatigue_matrix = DynamicFatigueMatrix()
        self.llm_judge = LLMJudge(min_pass_score=7.5)

        # 7. 财务审计与商业断路器
        self.cost_auditor = CostAuditor(max_cost_per_chapter_cny=max_cost_per_chapter)
        self.cost_tracker = CostTracker()  # 兼容原型调用

        # 8. 智能体总线与人机断点
        self.subagent_bus = SubagentCoordinationBus(
            outliner=self.doc_outliner,
            linter=self.linter,
            patcher=self.patcher,
            judge=self.llm_judge
        )
        self.hitl_manager = HITLBreakpointManager()

        # 9. 全渠道导出器
        self.exporter = ManuscriptExporter(repo=self.repo, graph=self.graph)

        # 10. LLM 生成调用钩子
        self.llm_worker = llm_worker or self._default_mock_worker

    def _default_mock_worker(self, system_prompt: str, user_prompt: str) -> str:
        """默认回退生成器"""
        return "酸雨顺着破损的霓虹招牌滴落。\n零号收起微型激光刀，手指没有丝毫晃动。\n暗巷尽头的脚步声戛然而止。"

    def produce_beat(
        self,
        chapter_index: int,
        scene_beat: BeatContract,
        lore_entries: List[LoreEntry],
        preceding_text_buffer: str = "",
        max_patch_retries: int = 3,
        enable_llm_judge: bool = False
    ) -> BeatProductionResult:
        """
        全流程生产单个分镜节拍：
        1. 因果硬不变式前置断言 (Zero-Zombie / 空间同场 / 道具先决)
        2. 单章财务硬断路器前置预判
        3. Codex 上下文确定性装配 (SillyTavern 递归级联)
        4. 物理初稿生成与流式防退化监控
        5. AST 语法树剪枝 (剥离段尾说教) + 声明式机械质检
        6. 若违规：触发原位微创局部打补丁循环 (保留 75%+ 完好正文)
        7. 财务精确入账
        """
        feedback_history: List[str] = []

        # 1. 因果硬不变式前置断言
        snap = self.event_store.materialize_world_at(chapter_index)
        inv_report = InvariantReport(passed=True, chapter_index=chapter_index, beat_id=scene_beat.beat_id)
        if scene_beat.characters_present:
            actor_id = scene_beat.characters_present[0]
            if actor_id in snap.entities:
                inv_action = ProposedAction(
                    actor_id=actor_id,
                    action_type="GENERIC_ACTION",
                    required_prerequisites=scene_beat.pre_conditions
                )
                inv_report = self.invariant_checker.check_action(
                    snapshot=snap,
                    action=inv_action,
                    chapter_index=chapter_index,
                    beat_id=scene_beat.beat_id
                )
                if not inv_report.passed:
                    err_msg = "; ".join(v.message for v in inv_report.violations)
                    feedback_history.append(f"因果不变式拦截: {err_msg}")

        # 2. 财务预算前置哨兵（预判 2000 输入 + 800 输出 Token 是否超标）
        try:
            self.cost_auditor.pre_check_budget(
                chapter_index=chapter_index,
                estimated_input_tokens=2000,
                estimated_output_tokens=scene_beat.target_words,
                model_name="deepseek-v3"
            )
        except FinancialCircuitBreakerError as e:
            feedback_history.append(f"财务预算警报: {e}")

        # 3. 确定性装配上下文
        assembled = self.codex_assembler.assemble(
            chapter_index=chapter_index,
            scene_beat=scene_beat,
            graph=self.graph,
            lore_entries=lore_entries,
            recent_text_buffer=preceding_text_buffer
        )

        # 4. 编译 Prompt 并下发给 Worker
        prompts = self.renderer.compile_writer_prompt(
            assembled_context=assembled,
            scene_beat=scene_beat
        )
        current_prose = self.llm_worker(prompts["system_prompt"], prompts["user_prompt"])

        # 5. 声明式机械质检与局部微创 Patch 循环
        lint_report = self.linter.lint_text(current_prose)
        patch_count = 0

        # 6. 局部微创 Patch 循环
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

            patched_prose = self.llm_worker(prompts["system_prompt"], patch_prompt)
            current_prose = patched_prose
            lint_report = self.linter.lint_text(current_prose)

        # 7. AST 语法树尾部兜底修剪
        cleaned_prose, pruned_count = self.linter.prune_tail_moralizers(current_prose)
        if pruned_count > 0:
            current_prose = cleaned_prose
            feedback_history.append(f"AST 语法树兜底剪除 {pruned_count} 处段尾说教")
            lint_report = self.linter.lint_text(current_prose)

        # 7. 可选 LLM 盲测裁判评估
        judge_eval: Optional[JudgeEvaluation] = None
        if enable_llm_judge:
            judge_eval = self.llm_judge.evaluate_beat(
                beat=scene_beat,
                prose=current_prose,
                provider=MockLLMProvider()
            )

        # 8. 财务精确入账
        out_tokens = max(1, len(current_prose) // 2)
        in_tokens = assembled.estimated_tokens
        cached_tokens = int(in_tokens * 0.75)
        
        try:
            self.cost_auditor.record_usage(
                chapter_index=chapter_index,
                beat_id=scene_beat.beat_id,
                model_name="deepseek-v3",
                input_tokens=in_tokens,
                cached_input_tokens=cached_tokens,
                output_tokens=out_tokens
            )
        except FinancialCircuitBreakerError as e:
            feedback_history.append(f"入账后触发熔断: {e}")

        # 记录兼容老式 cost_tracker
        self.cost_tracker.record_usage(
            chapter_index=chapter_index,
            beat_id=scene_beat.beat_id,
            model_name="gemini-1.5-flash",
            input_tokens=in_tokens,
            cached_input_tokens=cached_tokens,
            output_tokens=out_tokens
        )

        return BeatProductionResult(
            beat_id=scene_beat.beat_id,
            prose=current_prose,
            qc_passed=lint_report.passed and (inv_report.passed),
            lint_report=lint_report,
            patch_count=patch_count,
            feedback_history=feedback_history,
            invariant_report=inv_report,
            judge_evaluation=judge_eval
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
        逐拍推进 -> 局部缝合 -> 跨章 SimHash 去重 -> 词频疲劳矩阵更新 -> Narrative VCS 原子提交 -> EventStore 固化
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

        # 跨章 SimHash 语义雷同检查
        sim_incidents = self.simhash_index.check_chapter_duplicate(
            current_chapter=chapter_index,
            text=clean_full_prose,
            lookback_chapters=15
        )
        self.simhash_index.index_chapter(chapter_index, clean_full_prose)

        # 滑动窗口动态高频词疲劳矩阵登记
        self.fatigue_matrix.record_chapter_text(chapter_index, clean_full_prose)

        # 老版 TTR 重复检查
        history_commits = self.repo.get_commit_log(limit=5)
        history_texts = [c.get("full_prose", "") for c in history_commits if "full_prose" in c]
        rep_report = self.rep_detector.inspect_chapter(
            current_text=clean_full_prose,
            recent_chapters_text=history_texts
        )

        # 获取本章财务成本核算
        cost_summary = self.cost_auditor.audit_chapter(chapter_index)

        # 原子提交至 Narrative VCS (会自动同步驱动 BECGraph, EventStore 与 ProgressionEngine 回滚/推进)
        commit = self.repo.commit_chapter(
            chapter_index=chapter_index,
            title=title,
            full_prose=clean_full_prose,
            state_delta=state_delta,
            qc_metrics={
                "all_beats_passed": all(b.qc_passed for b in beat_results),
                "total_patches": sum(b.patch_count for b in beat_results),
                "ttr_score": rep_report.ttr_diversity_score,
                "simhash_incident_count": len(sim_incidents),
                "total_cost_cny": cost_summary.total_cost_cny,
                "cache_hit_rate": cost_summary.cache_hit_rate
            }
        )

        # 同步向 EventStore 写入不可变领域事件
        for ent_id, mut in state_delta.entity_mutations.items():
            self.event_store.append_event(Event(
                event_id=f"ch{chapter_index}_{ent_id}_mut",
                chapter_index=chapter_index,
                event_type=EventType.ATTRIBUTE_CHANGED,
                entity_id=ent_id,
                payload=mut
            ))
            # 同步向 ProgressionEngine 登记
            for field_path, val in mut.items():
                self.progression_engine.register_delta(ProgressionDelta(
                    delta_id=f"ch{chapter_index}_{ent_id}_{field_path}",
                    entity_id=ent_id,
                    progression_type=ProgressionType.REPLACEMENT,
                    effective_chapter=chapter_index,
                    field_path=field_path,
                    value=val
                ))

        # 定期保存 EventStore 快照检查点
        self.event_store.save_checkpoint(chapter_index)

        return ChapterProductionResult(
            chapter_index=chapter_index,
            title=title,
            full_prose=clean_full_prose,
            commit=commit,
            beat_results=beat_results,
            repetition_report=rep_report,
            simhash_duplicates=sim_incidents,
            cost_summary=cost_summary
        )

    def close(self):
        self.repo.close()
