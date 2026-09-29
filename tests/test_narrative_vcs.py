"""
Tests for Narrative VCS - 剧情版本控制与时空回滚测试
"""

import pytest
from src.novel_factory.core.event_store import EventStore
from src.novel_factory.core.events import Event, EventType
from src.novel_factory.codex.progression_engine import ProgressionEngine, ProgressionDelta, ProgressionType
from src.novel_factory.graph.bec_graph import BECGraph
from src.novel_factory.schemas.commit import StateDelta
from src.novel_factory.schemas.entity import EntityRelation, StandardRelations
from src.novel_factory.vcs.repository import NarrativeRepository, VCSRollbackError


@pytest.fixture
def vcs_repo():
    graph = BECGraph(":memory:")
    # 注册测试实体
    graph.register_entity("char_hero", "CHARACTER", "主角", created_chapter=1, initial_payload={"power": 100})
    event_store = EventStore(db_path=":memory:")
    prog_engine = ProgressionEngine()

    repo = NarrativeRepository(
        db_path=":memory:",
        graph=graph,
        event_store=event_store,
        progression_engine=prog_engine
    )
    yield repo
    repo.close()


def test_linear_commit_chain_and_head_tracking(vcs_repo: NarrativeRepository):
    """测试线性提交链、父哈希继承与 HEAD 推进"""
    # 提交第 1 章
    delta_1 = StateDelta(
        chapter_index=1,
        entity_mutations={"char_hero": {"power": 120}}
    )
    c1 = vcs_repo.commit_chapter(1, "第1章 危机", "第一章正文...", delta_1)

    assert c1.parent_commit_id is None
    assert vcs_repo.get_head_commit().commit_id == c1.commit_id

    # 提交第 2 章
    delta_2 = StateDelta(
        chapter_index=2,
        entity_mutations={"char_hero": {"power": 200}}
    )
    c2 = vcs_repo.commit_chapter(2, "第2章 突破", "第二章正文...", delta_2)

    assert c2.parent_commit_id == c1.commit_id
    assert vcs_repo.get_head_commit().commit_id == c2.commit_id

    log = vcs_repo.get_commit_log()
    assert len(log) == 2
    assert log[0]["title"] == "第1章 危机"
    assert log[1]["title"] == "第2章 突破"


def test_rollback_resets_vcs_graph_events_and_progression(vcs_repo: NarrativeRepository):
    """测试时空回滚：剧情回滚同时联动重置 BECGraph、EventStore 与 ProgressionEngine"""
    # 向 EventStore 写入 1-3 章事件
    vcs_repo.event_store.append_event(Event(
        event_id="e1", chapter_index=1, event_type=EventType.ENTITY_SPAWNED, entity_id="char_hero"
    ))
    vcs_repo.event_store.append_event(Event(
        event_id="e2", chapter_index=2, event_type=EventType.ATTRIBUTE_CHANGED, entity_id="char_hero", payload={"realm": "淬体"}
    ))
    vcs_repo.event_store.append_event(Event(
        event_id="e3", chapter_index=3, event_type=EventType.ATTRIBUTE_CHANGED, entity_id="char_hero", payload={"realm": "崩坏神级"}
    ))

    # 向 ProgressionEngine 写入增量
    vcs_repo.progression_engine.register_delta(ProgressionDelta(
        delta_id="p1", entity_id="char_hero", progression_type=ProgressionType.REPLACEMENT, effective_chapter=1, field_path="rank", value=1
    ))
    vcs_repo.progression_engine.register_delta(ProgressionDelta(
        delta_id="p2", entity_id="char_hero", progression_type=ProgressionType.REPLACEMENT, effective_chapter=2, field_path="rank", value=2
    ))
    vcs_repo.progression_engine.register_delta(ProgressionDelta(
        delta_id="p3", entity_id="char_hero", progression_type=ProgressionType.REPLACEMENT, effective_chapter=3, field_path="rank", value=999
    ))

    # 提交第 1~3 章
    vcs_repo.commit_chapter(1, "第1章", "正文1", StateDelta(chapter_index=1, entity_mutations={"char_hero": {"power": 100}}))
    vcs_repo.commit_chapter(2, "第2章", "正文2", StateDelta(chapter_index=2, entity_mutations={"char_hero": {"power": 250}}))
    vcs_repo.commit_chapter(3, "第3章 失误章", "正文3", StateDelta(chapter_index=3, entity_mutations={"char_hero": {"power": 99999}}))

    # 执行时空物理回滚到第 2 章末尾
    vcs_repo.checkout_chapter(target_chapter_index=2)

    # 1. 验证 HEAD 游标重置到第 2 章
    head = vcs_repo.get_head_commit()
    assert head.chapter_index == 2

    # 2. 验证 BECGraph 回滚
    state_ch3_after = vcs_repo.graph.get_entity_state_at("char_hero", 3)
    assert state_ch3_after["power"] == 250

    # 3. 验证 EventStore 回滚
    events_remaining = vcs_repo.event_store.get_events()
    assert len(events_remaining) == 2
    assert all(ev.chapter_index <= 2 for ev in events_remaining)

    # 4. 验证 ProgressionEngine 回滚
    deltas = vcs_repo.progression_engine.get_deltas_for_entity("char_hero")
    assert len(deltas) == 2
    assert all(d.effective_chapter <= 2 for d in deltas)


def test_branching_timeline_fork_and_diff(vcs_repo: NarrativeRepository):
    """测试剧情分叉、多分支探索与分支差分对比 (Branch Diff)"""
    vcs_repo.commit_chapter(1, "第1章", "正文1", StateDelta(chapter_index=1))
    vcs_repo.commit_chapter(2, "第2章", "正文2", StateDelta(chapter_index=2))

    # 开辟暗黑向分支 'branch_dark'
    vcs_repo.create_branch("branch_dark")
    assert vcs_repo.current_branch == "branch_dark"

    # 在暗黑分支提交第 3 章
    c3_dark = vcs_repo.commit_chapter(3, "第3章 暗黑路线", "黑化正文3", StateDelta(chapter_index=3))
    assert c3_dark.branch_name == "branch_dark"

    # 切换回主干 main 分支
    vcs_repo.switch_branch("main")
    main_head = vcs_repo.get_head_commit()
    assert main_head.chapter_index == 2

    # 主干分支提交正常的第 3 章与第 4 章
    c3_normal = vcs_repo.commit_chapter(3, "第3章 正统路线", "光明正文3", StateDelta(chapter_index=3))
    vcs_repo.commit_chapter(4, "第4章 扬帆起航", "正文4", StateDelta(chapter_index=4))

    # 对比两个分支差异
    diff = vcs_repo.diff_branches("main", "branch_dark")
    assert diff["divergent_chapters"] == [3]  # 第 3 章发生分歧
    assert diff["unique_to_a"] == [4]        # main 领先拥有第 4 章


def test_create_tag_milestone(vcs_repo: NarrativeRepository):
    """测试打里程碑标签功能"""
    c1 = vcs_repo.commit_chapter(1, "第1章", "正文1", StateDelta(chapter_index=1))
    vcs_repo.create_tag("v1.0-genesis", commit_id=c1.commit_id, message="第一章定稿")

    tags = vcs_repo.conn.execute("SELECT * FROM tags").fetchall()
    assert len(tags) == 1
    assert tags[0]["tag_name"] == "v1.0-genesis"
