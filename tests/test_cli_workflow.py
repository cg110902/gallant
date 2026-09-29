import os
import tempfile
from pathlib import Path
import pytest
from src.novel_factory.cli.workbench import (
    BreakpointType,
    HITLBreakpointManager,
    HumanDecision,
    WorkbenchDashboard,
)
from src.novel_factory.graph.bec_graph import BECGraph
from src.novel_factory.schemas.commit import StateDelta
from src.novel_factory.vcs.repository import NarrativeRepository


@pytest.fixture
def temp_state_file():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    yield Path(path)
    if os.path.exists(path):
        os.remove(path)


def test_hitl_breakpoint_lifecycle(temp_state_file: Path):
    """测试人机协同断点触发、持久化保存与恢复决策解决"""
    manager = HITLBreakpointManager(state_file_path=temp_state_file)

    # 1. 触发大纲审批断点
    manager.trigger_breakpoint(
        b_type=BreakpointType.OUTLINE_REVIEW,
        chapter_index=5,
        prompt_message="请作者审批第 5 章分镜规划",
        context_data={"planned_beats": 4}
    )

    assert manager.current_state.is_paused is True
    assert manager.current_state.active_breakpoint == BreakpointType.OUTLINE_REVIEW
    assert temp_state_file.exists()

    # 2. 模拟进程重启，从文件恢复断点现场
    new_manager = HITLBreakpointManager(state_file_path=temp_state_file)
    restored_state = new_manager.load_state()
    assert restored_state.is_paused is True
    assert restored_state.chapter_index == 5
    assert restored_state.prompt_message == "请作者审批第 5 章分镜规划"

    # 3. 人类作者批准通过
    resolution = new_manager.resolve_breakpoint(
        decision=HumanDecision.APPROVE,
        modified_data={"author_notes": "大纲无误，准予渲染"}
    )
    assert resolution["decision"] == "APPROVE"
    assert new_manager.current_state.is_paused is False


def test_workbench_dashboard_rendering():
    """测试 Rich 终端工作台概览与角色花名册渲染"""
    graph = BECGraph(":memory:")
    graph.register_entity(
        entity_id="char_lin",
        entity_type="PROTAGONIST",
        name="林动",
        created_chapter=1,
        initial_payload={"realm": "地元境初期"}
    )
    repo = NarrativeRepository(db_path=":memory:", graph=graph)
    repo.commit_chapter(1, "大荒崛起", "正文...", StateDelta(chapter_index=1))

    dashboard = WorkbenchDashboard()
    overview_table = dashboard.render_overview(repo, graph)
    assert overview_table.title is not None
    assert "大荒崛起" in str(overview_table.columns[1]._cells)

    roster_table = dashboard.render_entity_roster(graph, current_chapter=1)
    assert "char_lin" in str(roster_table.columns[0]._cells)
    assert "地元境初期" in str(roster_table.columns[4]._cells)

    repo.close()
