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
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
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
from src.novel_factory.commerce.hook_enforcer import HookEnforcer, HookEvaluation
from src.novel_factory.commerce.payoff_density import DensityReport, EmotionValence, PayoffDensityMeter
from src.novel_factory.commerce.power_curve import PowerCurveGuard, PowerCurveReport
from src.novel_factory.commerce.thread_scheduler import ThreadScheduleReport, ThreadScheduler
from src.novel_factory.config.loader import ProjectConfigLoader
from src.novel_factory.consistency.foreshadowing import ForeshadowLedger, ForeshadowReport
from src.novel_factory.consistency.name_collision import NameCollisionDetector, NameCollisionReport
from src.novel_factory.consistency.persona import PersonaRegistry, PersonaReport
from src.novel_factory.consistency.timeline import StoryCalendar, TimelineReport
from src.novel_factory.config.schemas import ProjectConfig
from src.novel_factory.graph.causal_dag import CausalDAG
from src.novel_factory.graph.invariant_checker import InvariantChecker, InvariantReport, InvariantViolation, ProposedAction
from src.novel_factory.llm.client import BaseLLMProvider, MockLLMProvider, get_llm_provider
from src.novel_factory.llm.cost_auditor import ChapterCostSummary, CostAuditor, FinancialCircuitBreakerError
from src.novel_factory.llm.client import LLMGenerationResult
from src.novel_factory.llm.cost_tracker import CostTracker
from src.novel_factory.pipeline.beat_renderer import BeatRenderer
from src.novel_factory.pipeline.local_patcher import ChapterBeatSegment, LocalPatcher, PatchResult
from src.novel_factory.pipeline.stream_monitor import StreamMonitor
from src.novel_factory.qc.llm_judge import JudgeEvaluation, LLMJudge
from src.novel_factory.qc.compliance_scanner import ComplianceReport, ComplianceScanner
from src.novel_factory.qc.contract_auditor import BeatContractAuditor, ContractAuditReport
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
    contract_report: Optional[ContractAuditReport] = None
    compliance_report: Optional[ComplianceReport] = None


@dataclass
class ChapterGovernanceReport:
    """章级长程治理综合报告（一致性层 + 商业性层）"""
    chapter_index: int
    foreshadow: Optional[ForeshadowReport] = None
    timeline: Optional[TimelineReport] = None
    persona: Optional[PersonaReport] = None
    names: Optional[NameCollisionReport] = None
    hook: Optional[HookEvaluation] = None
    density: Optional[DensityReport] = None
    power: Optional[PowerCurveReport] = None
    threads: Optional[ThreadScheduleReport] = None

    @property
    def blocking_issues(self) -> List[str]:
        """会否决整章的硬问题"""
        issues: List[str] = []
        if self.foreshadow and self.foreshadow.overdue:
            issues.append(f"伏笔超期未回收 {len(self.foreshadow.overdue)} 条")
        if self.foreshadow and self.foreshadow.unplanted_payoffs:
            issues.append(f"凭空回收(未埋先收) {len(self.foreshadow.unplanted_payoffs)} 处")
        if self.timeline and not self.timeline.passed:
            issues.append(f"时间线矛盾 {len(self.timeline.errors)} 处")
        if self.persona and not self.persona.passed:
            issues.append(f"人设一致性违规 {len(self.persona.errors)} 处")
        if self.names and not self.names.passed:
            issues.append(f"角色命名冲突 {len(self.names.errors)} 处")
        if self.hook and not self.hook.passed:
            issues.append(f"章末钩子不合格 ({self.hook.strength.value})")
        if self.power and not self.power.passed:
            issues.append(f"升级节奏失控 {len(self.power.errors)} 处")
        return issues

    @property
    def advisory_issues(self) -> List[str]:
        """不否决但需要关注的软问题"""
        out: List[str] = []
        if self.density and self.density.alerts:
            out.extend(self.density.alerts)
        if self.threads and self.threads.starved:
            out.extend(
                f"支线「{t.title}」已断更 {g} 章" for t, g in self.threads.starved
            )
        if self.foreshadow and self.foreshadow.stale:
            out.append(f"伏笔记忆过期 {len(self.foreshadow.stale)} 条，建议本章复述")
        return out

    def format_summary(self) -> str:
        parts = [f"===== 第{self.chapter_index}章 长程治理报告 ====="]
        for r in (self.foreshadow, self.timeline, self.persona, self.names,
                  self.hook, self.density, self.power, self.threads):
            if r is not None:
                parts.append(r.format_summary())
        return "\n".join(parts)


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
    qc_passed: bool = True
    blockers: List[str] = field(default_factory=list)
    compliance_report: Optional[ComplianceReport] = None
    governance: Optional[ChapterGovernanceReport] = None


class NovelFactoryOrchestrator:
    """工业小说工厂全链路总编排中枢"""

    def __init__(
        self,
        project_config_path: Optional[str] = None,
        db_path: Optional[str] = ":memory:",
        llm_worker: Optional[Callable[[str, str], str]] = None,
        llm_provider: Optional[BaseLLMProvider] = None,
        max_cost_per_chapter: float = 0.40,
        strict_unregistered_entities: bool = True,
        max_simhash_incidents_per_chapter: int = 0,
        enforce_governance: bool = True
    ):
        # 长程治理闸门（伏笔超期/时间线矛盾/人设崩坏/钩子失效 是否否决整章）
        self.enforce_governance = enforce_governance
        # 严格模式：正文中出现未在 BEC 图谱注册的角色即判定违规（防幽灵串场绕过不变量）
        self.strict_unregistered_entities = strict_unregistered_entities
        self.generation_temperature: float = 0.85
        self.generation_max_tokens: int = 2048
        # 单章允许的跨章雷同告警上限，超出即判定本章不合格
        self.max_simhash_incidents_per_chapter = max_simhash_incidents_per_chapter
        self.config_loader = ProjectConfigLoader()
        self.project_config: Optional[ProjectConfig] = None
        self.config: Dict[str, Any] = {}
        if project_config_path and Path(project_config_path).exists():
            try:
                self.project_config = self.config_loader.load_project_master(project_config_path)
                with open(project_config_path, "r", encoding="utf-8") as f:
                    self.config = yaml.safe_load(f) or {}
            except Exception:
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
        # 6.1 节拍契约交付履约审计器（字数/微事件/机位/禁忌硬闸门）
        ca_cfg = self.config.get("contract_audit", {}) or {}
        self.contract_auditor = BeatContractAuditor(
            enforce_word_count=ca_cfg.get("enforce_word_count", True),
            enforce_micro_events=ca_cfg.get("enforce_micro_events", True),
            enforce_camera_coverage=ca_cfg.get("enforce_camera_coverage", True),
            min_camera_coverage_ratio=ca_cfg.get("min_camera_coverage_ratio", 0.5),
            high_confidence=ca_cfg.get("micro_event_high_confidence", 0.6),
            low_confidence=ca_cfg.get("micro_event_low_confidence", 0.3),
        )
        # 6.2 敏感词与过审风控
        self.compliance_scanner = ComplianceScanner.from_default_pack(
            qc_cfg.get("compliance_pack") or "configs/rules/compliance.yaml"
        )

        # 6.3 治理闸门参数（声明式覆盖构造参数）
        gov_cfg = self.config.get("governance", {}) or {}
        if "enforce" in gov_cfg:
            self.enforce_governance = bool(gov_cfg["enforce"])
        if "strict_unregistered_entities" in gov_cfg:
            self.strict_unregistered_entities = bool(gov_cfg["strict_unregistered_entities"])
        if "max_simhash_incidents_per_chapter" in gov_cfg:
            self.max_simhash_incidents_per_chapter = int(
                gov_cfg["max_simhash_incidents_per_chapter"]
            )
        self.foreshadow_due_soon_window = int(gov_cfg.get("foreshadow_due_soon_window", 10))
        self.hook_min_acceptable_score = float(gov_cfg.get("hook_min_acceptable_score", 5.0))

        # 6.5. 声明式题材法则动态注入 (Domain/Genre Rules Injection)
        if self.project_config and self.project_config.genre:
            # A. 题材套路与陈腐网络词动态追加到 Linter
            if self.project_config.genre.genre_banned_cliches:
                self.linter.add_banned_phrases(self.project_config.genre.genre_banned_cliches)

            # B. 战力标尺越阶不可逆天道硬不变式
            if self.project_config.genre.power_scale:
                scale = self.project_config.genre.power_scale

                def power_tier_invariant(snap: WorldSnapshot, action: ProposedAction, report: InvariantReport) -> None:
                    if action.action_type in ("MELEE_ATTACK", "DUEL", "COMBAT_KILL") and action.target_id:
                        actor_ent = snap.entities.get(action.actor_id)
                        target_ent = snap.entities.get(action.target_id)
                        if actor_ent and target_ent:
                            a_tier = actor_ent.get("tier_id")
                            t_tier = target_ent.get("tier_id")
                            if a_tier and t_tier:
                                a_idx = scale.get_tier_index(a_tier)
                                t_idx = scale.get_tier_index(t_tier)
                                if a_idx is not None and t_idx is not None:
                                    if (t_idx - a_idx) > scale.max_cross_tier_gap:
                                        report.violations.append(InvariantViolation(
                                            rule_name="POWER_SCALE_OVERPOWERED_GAP",
                                            severity="ERROR",
                                            message=f"战力法则越阶不可逆：[{action.actor_id}] (位阶 {a_tier}) 企图逆伐超高位阶目标 [{action.target_id}] (位阶 {t_tier})，阶差超出最大容限 {scale.max_cross_tier_gap}",
                                            entity_ids=[action.actor_id, action.target_id],
                                            chapter_index=report.chapter_index,
                                            beat_id=report.beat_id
                                        ))

                self.invariant_checker.register_custom_rule(power_tier_invariant)

        # 7. 财务审计与商业断路器
        effective_limit = max_cost_per_chapter
        if self.project_config and self.project_config.models:
            effective_limit = self.project_config.models.cost_limit_per_chapter_cny
        self.cost_auditor = CostAuditor(max_cost_per_chapter_cny=effective_limit)
        self.cost_tracker = CostTracker()  # 兼容原型调用

        # 8. 智能体总线与人机断点
        self.subagent_bus = SubagentCoordinationBus(
            outliner=self.doc_outliner,
            linter=self.linter,
            patcher=self.patcher,
            judge=self.llm_judge
        )
        self.hitl_manager = HITLBreakpointManager()

        # 8.5 长程一致性层 (P1)：伏笔台账 / 故事日历 / 人设指纹 / 命名冲突
        self.foreshadow_ledger = ForeshadowLedger(db_path=db_path)
        self.calendar = StoryCalendar()
        self.persona_registry = PersonaRegistry()
        self.name_detector = NameCollisionDetector()

        # 8.6 商业性引擎 (P2)：章末钩子 / 爽点密度 / 升级节奏 / 多线调度
        self.hook_enforcer = HookEnforcer(
            min_acceptable_score=self.hook_min_acceptable_score
        )
        self.payoff_meter = PayoffDensityMeter()
        self.power_guard = PowerCurveGuard()
        self.thread_scheduler = ThreadScheduler()

        # 9. 全渠道导出器
        self.exporter = ManuscriptExporter(repo=self.repo, graph=self.graph)

        # 10. LLM 生成调用钩子
        #     优先使用真实 Provider（可回传真实 token 用量用于财务审计）；
        #     否则退化为纯文本 callable，token 数按字符估算。
        self.llm_provider: Optional[BaseLLMProvider] = llm_provider
        self._last_usage: Optional[LLMGenerationResult] = None
        if llm_worker is not None:
            self.llm_worker = llm_worker
        elif llm_provider is not None:
            self.llm_worker = self._provider_worker
        else:
            self.llm_worker = self._default_mock_worker

    @classmethod
    def from_project_config(
        cls,
        config_path: Optional[Union[str, Path]] = "project.yaml",
        db_path: Optional[str] = ":memory:",
        llm_worker: Optional[Callable[[str, str], str]] = None
    ) -> "NovelFactoryOrchestrator":
        """从 project.yaml 声明式工程规范快速实例化小说工厂编排引擎"""
        return cls(
            project_config_path=str(config_path) if config_path else None,
            db_path=db_path,
            llm_worker=llm_worker
        )

    def _provider_worker(self, system_prompt: str, user_prompt: str) -> str:
        """通过真实 LLM Provider 生成，并缓存本次调用的真实 token 用量"""
        result = self.llm_provider.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=self.generation_temperature,
            max_tokens=self.generation_max_tokens
        )
        self._last_usage = result
        return result.text

    @classmethod
    def from_provider(
        cls,
        provider_type: str = "mock",
        model_name: str = "gemini-3.8-flash",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        config_path: Optional[Union[str, Path]] = "project.yaml",
        db_path: Optional[str] = ":memory:",
        **kwargs: Any
    ) -> "NovelFactoryOrchestrator":
        """以真实大模型供应商装配生产线（gemini / gemini_rest / deepseek / openai / mock）"""
        provider = get_llm_provider(
            provider_type=provider_type,
            model_name=model_name,
            api_key=api_key,
            base_url=base_url
        )
        return cls(
            project_config_path=str(config_path) if config_path and Path(config_path).exists() else None,
            db_path=db_path,
            llm_provider=provider,
            **kwargs
        )

    def _default_mock_worker(self, system_prompt: str, user_prompt: str) -> str:
        """默认回退生成器"""
        return "酸雨顺着破损的霓虹招牌滴落。\n零号收起微型激光刀，手指没有丝毫晃动。\n暗巷尽头的脚步声戛然而止。"

    def register_entity(
        self,
        entity_id: str,
        entity_type: str,
        name: str,
        created_chapter: int = 1,
        initial_payload: Optional[Dict[str, Any]] = None,
        is_alive: bool = True
    ) -> None:
        """
        统一实体注册入口：同时写入 BEC 时态图谱与事件溯源库。

        此前两者各写各的，导致在图谱里注册过的角色在 WorldSnapshot 中依然
        "不存在"，不变量检查被迫误报 ENTITY_NOT_FOUND。
        """
        self.graph.register_entity(
            entity_id=entity_id,
            entity_type=entity_type,
            name=name,
            created_chapter=created_chapter,
            initial_payload=initial_payload,
            is_alive=is_alive
        )
        # 断点续产重启后会重新注册同一批角色，故 spawn 事件必须幂等，
        # 否则第二次启动就会因 event_id 唯一约束直接崩溃。
        self.event_store.append_event(Event(
            event_id=f"spawn_{entity_id}_ch{created_chapter}",
            chapter_index=created_chapter,
            event_type=EventType.ENTITY_SPAWNED,
            entity_id=entity_id,
            payload={
                "name": name,
                "entity_type": entity_type,
                "is_alive": is_alive,
                **(initial_payload or {})
            }
        ), idempotent=True)

    def _known_character_names(self) -> Dict[str, str]:
        """读取图谱中全部角色实体的 id->名字 映射，供在场纪律检查使用"""
        try:
            return {
                e["entity_id"]: e["name"]
                for e in self.graph.list_entities(entity_type="CHARACTER")
            }
        except Exception:
            return {}

    # ================= 长程治理 (Long-Range Governance) =================

    def collect_governance_directives(
        self,
        chapter_index: int,
        present_entities: Optional[List[str]] = None
    ) -> List[str]:
        """
        在生产【之前】收集所有长程引擎的强制指令，注入 Writer Prompt。
        这是"事前预防"，与事后审计共同构成闭环 —— 只审计不预防等于永远在返工。
        """
        directives: List[str] = []

        # 伏笔：该回收的 / 该复述的
        fs_report = self.foreshadow_ledger.audit_chapter(
            chapter_index, due_soon_window=self.foreshadow_due_soon_window
        )
        directives.extend(fs_report.to_writer_directives())

        # 爽点密度：该爆发还是该憋
        density = self.payoff_meter.analyze(max(1, chapter_index - 1))
        directives.extend(density.directives)

        # 支线调度：该续更哪条线
        thread_rep = self.thread_scheduler.check(max(1, chapter_index - 1))
        directives.extend(thread_rep.directives)

        return directives

    def audit_chapter_governance(
        self,
        chapter_index: int,
        chapter_text: str,
        present_entities: Optional[List[str]] = None,
        declared_payoff_keywords: Optional[List[str]] = None
    ) -> ChapterGovernanceReport:
        """章节落地后的长程治理全面审计"""
        report = ChapterGovernanceReport(chapter_index=chapter_index)
        entities = present_entities or []

        # 1. 伏笔：先按正文自动刷新记忆时钟，再审计
        self.foreshadow_ledger.auto_reinforce_from_text(chapter_index, chapter_text)
        report.foreshadow = self.foreshadow_ledger.audit_chapter(
            chapter_index=chapter_index,
            due_soon_window=self.foreshadow_due_soon_window,
            chapter_text=chapter_text,
            declared_payoff_keywords=declared_payoff_keywords
        )

        # 2. 时间线
        report.timeline = self.calendar.check_chapter(chapter_index, acting_entities=entities)

        # 3. 人设一致性
        report.persona = self.persona_registry.check_chapter(
            chapter_index=chapter_index, text=chapter_text, present_entities=entities or None
        )

        # 4. 命名冲突（全书角色名全量扫描）
        try:
            roster = self.graph.list_entities(entity_type="CHARACTER")
            if roster:
                report.names = self.name_detector.check(
                    names=[e["name"] for e in roster],
                    entity_ids=[e["entity_id"] for e in roster]
                )
        except Exception:
            pass

        # 5. 章末钩子
        report.hook = self.hook_enforcer.evaluate(chapter_index, chapter_text)

        # 6. 爽点密度（先登记本章情绪，再分析）
        self.payoff_meter.record_chapter(chapter_index, text=chapter_text)
        report.density = self.payoff_meter.analyze(chapter_index)

        # 7. 升级节奏
        report.power = self.power_guard.check(chapter_index)

        # 8. 多线调度
        report.threads = self.thread_scheduler.check(chapter_index)

        return report

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
        #    注意：必须对【全部】在场角色逐一断言，且绝不因实体未注册而跳过检查，
        #    否则「死人不能出场」这条核心军规可被一个未注册的幽灵角色直接绕开。
        snap = self.event_store.materialize_world_at(chapter_index)
        inv_report = InvariantReport(passed=True, chapter_index=chapter_index, beat_id=scene_beat.beat_id)
        # pre_conditions 是自然语言描述，只有其中真正注册为因果 DAG 节点的才作为
        # 拓扑前置断言；否则会把普通剧情描述误判为"因果节点缺失"。
        dag_prereqs = [
            pc for pc in scene_beat.pre_conditions
            if self.causal_dag.get_node(pc) is not None
        ]
        for actor_id in scene_beat.characters_present:
            inv_action = ProposedAction(
                actor_id=actor_id,
                action_type="GENERIC_ACTION",
                location_id=scene_beat.location_id,
                required_prerequisites=dag_prereqs
            )
            single_report = self.invariant_checker.check_action(
                snapshot=snap,
                action=inv_action,
                chapter_index=chapter_index,
                beat_id=scene_beat.beat_id
            )
            inv_report.violations.extend(single_report.violations)

        if self.strict_unregistered_entities is False:
            inv_report.violations = [
                v for v in inv_report.violations if v.rule_name != "ENTITY_NOT_FOUND"
            ]
        inv_report.passed = not inv_report.has_fatal_errors
        if not inv_report.passed:
            err_msg = "; ".join(v.message for v in inv_report.violations)
            feedback_history.append(f"因果不变式拦截: {err_msg}")

        # 2. 财务预算前置哨兵（预判 2000 输入 + 800 输出 Token 是否超标）
        writer_model = "gemini-3.8-flash"
        if self.project_config and self.project_config.models:
            writer_model = self.project_config.models.writer_agent

        try:
            self.cost_auditor.pre_check_budget(
                chapter_index=chapter_index,
                estimated_input_tokens=2000,
                estimated_output_tokens=scene_beat.target_words,
                model_name=writer_model
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
        governance_directives = self.collect_governance_directives(
            chapter_index=chapter_index,
            present_entities=list(scene_beat.characters_present)
        )
        prompts = self.renderer.compile_writer_prompt(
            assembled_context=assembled,
            scene_beat=scene_beat,
            dynamic_ban_list=[
                r.word for r in self.fatigue_matrix.get_dynamic_ban_list(chapter_index)
            ] or None,
            governance_directives=governance_directives or None,
            persona_block=self.persona_registry.build_context_block(
                chapter_index, scene_beat.characters_present
            ),
            time_anchor_line=self.calendar.build_context_line(chapter_index)
        )
        current_prose = self.llm_worker(prompts["system_prompt"], prompts["user_prompt"])

        # 4.5. 流式防流口水与退化截断 (Stream Degeneration & Anti-Drooling Breaker)
        self.stream_monitor.reset()
        for ch in current_prose:
            stream_res = self.stream_monitor.feed_chunk(ch)
            if stream_res.is_aborted:
                current_prose = self.stream_monitor.get_clean_text()
                feedback_history.append(f"防流口水截断生效: {stream_res.abort_reason}")
                break

        # 5. 双闸门质检：机械文本规则 (Lint) + 节拍契约履约 (Contract)
        known_names = self._known_character_names()
        lint_report = self.linter.lint_text(current_prose)
        contract_report = self.contract_auditor.audit(
            contract=scene_beat, prose=current_prose, known_character_names=known_names
        )
        patch_count = 0

        # 6. 局部微创 Patch 循环：任一闸门未过即定向修补
        while (not lint_report.passed or not contract_report.passed) and patch_count < max_patch_retries:
            patch_count += 1
            violations_msgs = [f"{v.rule_id}: {v.message}" for v in lint_report.violations]
            violations_msgs.extend(contract_report.repair_instructions())
            feedback_history.append(
                f"第 {patch_count} 次打补丁: 文本违规 {len(lint_report.violations)} 处, "
                f"契约违约 {len(contract_report.breaches)} 处"
            )

            patch_prompt = self.patcher.generate_patch_prompt(
                target_beat_id=scene_beat.beat_id,
                original_beat_text=current_prose,
                violation_messages=violations_msgs,
                preceding_context=preceding_text_buffer,
                post_condition_reminders=scene_beat.post_conditions,
                persona_block=self.persona_registry.build_context_block(
                    chapter_index, scene_beat.characters_present
                ),
                time_anchor_line=self.calendar.build_context_line(chapter_index),
                target_words=scene_beat.target_words
            )

            patched_prose = self.llm_worker(prompts["system_prompt"], patch_prompt)
            current_prose = patched_prose
            lint_report = self.linter.lint_text(current_prose)
            contract_report = self.contract_auditor.audit(
                contract=scene_beat, prose=current_prose, known_character_names=known_names
            )

        if not contract_report.passed:
            feedback_history.append(
                f"契约履约仍未达标(已重试 {patch_count} 次): " + contract_report.format_summary()
            )

        # 7. AST 语法树尾部兜底修剪
        cleaned_prose, pruned_count = self.linter.prune_tail_moralizers(current_prose)
        if pruned_count > 0:
            current_prose = cleaned_prose
            feedback_history.append(f"AST 语法树兜底剪除 {pruned_count} 处段尾说教")
            lint_report = self.linter.lint_text(current_prose)
            contract_report = self.contract_auditor.audit(
                contract=scene_beat, prose=current_prose, known_character_names=known_names
            )

        # 7.5 过审风控扫描（硬红线命中即判定本节拍不合格）
        compliance_report = self.compliance_scanner.scan(current_prose)
        if not compliance_report.passed:
            feedback_history.append("过审风控拦截: " + compliance_report.format_summary())

        # 7. 可选 LLM 盲测裁判评估
        judge_eval: Optional[JudgeEvaluation] = None
        if enable_llm_judge:
            judge_eval = self.llm_judge.evaluate_beat(
                beat=scene_beat,
                prose=current_prose,
                provider=MockLLMProvider()
            )

        # 8. 财务精确入账：有真实 Provider 回传用量时以真实值为准，否则按字符估算
        if self._last_usage is not None:
            in_tokens = self._last_usage.input_tokens
            cached_tokens = self._last_usage.cached_input_tokens
            out_tokens = self._last_usage.output_tokens
            writer_model = self._last_usage.model_name or writer_model
        else:
            out_tokens = max(1, len(current_prose) // 2)
            in_tokens = assembled.estimated_tokens
            cached_tokens = int(in_tokens * 0.75)
        
        try:
            self.cost_auditor.record_usage(
                chapter_index=chapter_index,
                beat_id=scene_beat.beat_id,
                model_name=writer_model,
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
            model_name=writer_model,
            input_tokens=in_tokens,
            cached_input_tokens=cached_tokens,
            output_tokens=out_tokens
        )

        # 9. 综合裁定：四道闸门全过才算合格（此前只看 lint，导致 17 字垃圾也能"通过"）
        qc_passed = (
            lint_report.passed
            and contract_report.passed
            and inv_report.passed
            and compliance_report.passed
        )

        return BeatProductionResult(
            beat_id=scene_beat.beat_id,
            prose=current_prose,
            qc_passed=qc_passed,
            lint_report=lint_report,
            patch_count=patch_count,
            feedback_history=feedback_history,
            invariant_report=inv_report,
            judge_evaluation=judge_eval,
            contract_report=contract_report,
            compliance_report=compliance_report
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

        # ===== 章级综合放行闸门 =====
        # 此前 simhash 告警只被"记录"而从不否决，导致三章一字不差也能全部 [OK]。
        chapter_blockers: List[str] = []
        if len(sim_incidents) > self.max_simhash_incidents_per_chapter:
            worst = max(sim_incidents, key=lambda i: getattr(i, "similarity", 0.0))
            chapter_blockers.append(
                f"跨章语义雷同超限：检出 {len(sim_incidents)} 处(上限 "
                f"{self.max_simhash_incidents_per_chapter})，最高相似度 "
                f"{getattr(worst, 'similarity', 0.0):.2%}"
            )
        failed_beats = [b.beat_id for b in beat_results if not b.qc_passed]
        if failed_beats:
            chapter_blockers.append(f"存在未通过质检的节拍: {', '.join(failed_beats)}")

        chapter_compliance = self.compliance_scanner.scan(clean_full_prose)
        if not chapter_compliance.passed:
            chapter_blockers.append(
                f"过审风控红线：{len(chapter_compliance.blocking_hits)} 处硬拦截"
            )

        # 将本章的战力/境界变动自动登记到升级节奏守门员，
        # 否则 PowerCurveGuard 永远看不到数据，等于形同虚设。
        for ent_id, mut in state_delta.entity_mutations.items():
            rating = mut.get("power_rating")
            tier = mut.get("tier_id") or mut.get("tier_or_rank")
            if rating is not None or tier is not None:
                if rating is None:
                    rating = self.power_guard.get_power_at(ent_id, chapter_index) or 0.0
                self.power_guard.record(
                    chapter_index=chapter_index,
                    entity_id=ent_id,
                    power_rating=float(rating),
                    tier_id=str(tier) if tier else None,
                )

        # 长程治理审计（一致性 + 商业性）
        present_entities = sorted({
            e for c in beat_contracts for e in c.characters_present
        })
        governance = self.audit_chapter_governance(
            chapter_index=chapter_index,
            chapter_text=clean_full_prose,
            present_entities=present_entities
        )
        if self.enforce_governance:
            chapter_blockers.extend(governance.blocking_issues)

        chapter_qc_passed = not chapter_blockers

        # 原子提交至 Narrative VCS (会自动同步驱动 BECGraph, EventStore 与 ProgressionEngine 回滚/推进)
        commit = self.repo.commit_chapter(
            chapter_index=chapter_index,
            title=title,
            full_prose=clean_full_prose,
            state_delta=state_delta,
            qc_metrics={
                "all_beats_passed": all(b.qc_passed for b in beat_results),
                "chapter_qc_passed": chapter_qc_passed,
                "chapter_blockers": chapter_blockers,
                "total_patches": sum(b.patch_count for b in beat_results),
                "ttr_score": rep_report.ttr_diversity_score,
                "simhash_incident_count": len(sim_incidents),
                "compliance_blocking_hits": len(chapter_compliance.blocking_hits),
                "hook_strength": governance.hook.strength.value if governance.hook else None,
                "hook_score": governance.hook.score if governance.hook else 0.0,
                "open_foreshadows": governance.foreshadow.open_count if governance.foreshadow else 0,
                "contract_word_compliance": round(
                    sum(
                        b.contract_report.word_compliance_ratio
                        for b in beat_results if b.contract_report
                    ) / max(1, len([b for b in beat_results if b.contract_report])),
                    3
                ),
                "total_cost_cny": cost_summary.total_cost_cny,
                "cache_hit_rate": cost_summary.cache_hit_rate
            }
        )

        # 同步向 EventStore 写入不可变领域事件
        # 章节可能因质检驳回而被重跑，事件写入必须幂等，
        # 否则第二次生产同一章会直接撞 event_id 唯一约束而崩溃。
        for ent_id, mut in state_delta.entity_mutations.items():
            self.event_store.append_event(Event(
                event_id=f"ch{chapter_index}_{ent_id}_mut",
                chapter_index=chapter_index,
                event_type=EventType.ATTRIBUTE_CHANGED,
                entity_id=ent_id,
                payload=mut
            ), idempotent=True)
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
            cost_summary=cost_summary,
            qc_passed=chapter_qc_passed,
            blockers=chapter_blockers,
            compliance_report=chapter_compliance,
            governance=governance
        )

    def close(self):
        self.repo.close()
