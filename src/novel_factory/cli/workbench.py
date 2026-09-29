"""
Interactive Workbench & HITL System - 人机协同断点与工业工作台引擎
支持人类作者在关键创作节点进行精准干预与审批：
1. 断点管理 (Human-in-the-Loop Breakpoints)：大纲审批断点、卷终高潮批准、质检失败人工接管、财务预算追加；
2. 状态机持久化断点 (Pause/Resume State)：支持随时保存进度与断点重入；
3. 基于 Rich 终端渲染的实时仪表盘与图谱穿透探查器 (Dashboard & Graph Inspector)。
"""

from enum import Enum
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.novel_factory.graph.bec_graph import BECGraph
from src.novel_factory.vcs.repository import NarrativeRepository


class BreakpointType(str, Enum):
    OUTLINE_REVIEW = "OUTLINE_REVIEW"              # 大纲设计审核断点
    VOLUME_CLIMAX = "VOLUME_CLIMAX"                # 分卷核心高潮批准
    QC_FAILURE_TAKEOVER = "QC_FAILURE_TAKEOVER"    # 连续质检失败人工接管
    FINANCIAL_LIMIT_ALERT = "FINANCIAL_LIMIT_ALERT"  # 财务成本超标人审


class HumanDecision(str, Enum):
    APPROVE = "APPROVE"                          # 批准通过，继续自动流水线
    MODIFY_AND_PROCEED = "MODIFY_AND_PROCEED"    # 修改输入/正文后继续
    ROLLBACK = "ROLLBACK"                        # 拒绝并一键回滚到安全检查点
    MANUAL_TAKEOVER = "MANUAL_TAKEOVER"          # 人工作者手工录入正文覆盖


class HITLState(BaseModel):
    """断点暂停现场快照"""
    active_breakpoint: Optional[BreakpointType] = None
    chapter_index: int = 1
    beat_id: Optional[str] = None
    context_data: Dict[str, Any] = Field(default_factory=dict)
    prompt_message: str = ""
    is_paused: bool = False


class HITLBreakpointManager:
    """人机协同断点管理器"""

    def __init__(self, state_file_path: Optional[Path] = None):
        self.state_file = state_file_path or Path(".hitl_state.json")
        self.current_state = HITLState()

    def trigger_breakpoint(
        self,
        b_type: BreakpointType,
        chapter_index: int,
        prompt_message: str,
        context_data: Optional[Dict[str, Any]] = None,
        beat_id: Optional[str] = None
    ) -> None:
        """设置断点并挂起流水线"""
        self.current_state = HITLState(
            active_breakpoint=b_type,
            chapter_index=chapter_index,
            beat_id=beat_id,
            context_data=context_data or {},
            prompt_message=prompt_message,
            is_paused=True
        )
        self.save_state()

    def resolve_breakpoint(
        self,
        decision: HumanDecision,
        modified_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """人类决策解决断点并恢复作业"""
        if not self.current_state.is_paused:
            return {"status": "NOT_PAUSED"}

        res = {
            "decision": decision.value,
            "breakpoint": self.current_state.active_breakpoint.value if self.current_state.active_breakpoint else None,
            "chapter_index": self.current_state.chapter_index,
            "modified_data": modified_data or {}
        }

        # 清除断点
        self.current_state = HITLState(is_paused=False)
        self.save_state()
        return res

    def save_state(self) -> None:
        """持久化断点状态到磁盘"""
        with open(self.state_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(self.current_state.model_dump(), ensure_ascii=False, indent=2))

    def load_state(self) -> HITLState:
        """从磁盘恢复断点状态"""
        if self.state_file.exists():
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.current_state = HITLState(**data)
        return self.current_state


class WorkbenchDashboard:
    """基于 Rich 的可视化状态监视器"""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console(force_terminal=True, legacy_windows=False)

    def render_overview(
        self,
        repo: NarrativeRepository,
        graph: BECGraph
    ) -> Table:
        """渲染车间总体概览表"""
        table = Table(title="[bold cyan]Antigravity 小说制造车间实时状态[/bold cyan]", border_style="cyan")
        table.add_column("当前分支", style="green")
        table.add_column("最新已提章节", style="bold")
        table.add_column("总字数", justify="right")
        table.add_column("HEAD 提交校验和", style="dim")

        head = repo.get_head_commit()
        ch_str = f"第 {head.chapter_index} 章: {head.title}" if head else "(初始无提交)"
        words = str(head.word_count) if head else "0"
        cid = head.commit_id[:10] if head else "N/A"

        table.add_row(repo.current_branch, ch_str, words, cid)
        return table

    def render_entity_roster(self, graph: BECGraph, current_chapter: int = 1) -> Table:
        """渲染在场与存续角色花名册"""
        table = Table(title=f"[bold green]第 {current_chapter} 章世界实体时态快照[/bold green]", border_style="green")
        table.add_column("实体 ID", style="cyan")
        table.add_column("名称", style="bold")
        table.add_column("类型")
        table.add_column("存活状态")
        table.add_column("境界/战力")

        rows = graph.conn.execute("SELECT entity_id, name, entity_type, is_alive, current_payload_json FROM entities").fetchall()
        for r in rows:
            payload = json.loads(r["current_payload_json"] or "{}")
            tier = payload.get("realm") or payload.get("tier_or_rank") or "普通"
            alive_str = "[green]存活[/green]" if r["is_alive"] == 1 else "[red]已阵亡[/red]"
            table.add_row(r["entity_id"], r["name"], r["entity_type"], alive_str, str(tier))

        return table
