"""
Tests for Narrative VCS - 剧情版本控制与时空回滚测试
"""

import pytest
from src.novel_factory.graph.bec_graph import BECGraph
from src.novel_factory.schemas.commit import StateDelta
from src.novel_factory.schemas.entity import EntityRelation, StandardRelations
from src.novel_factory.vcs.repository import NarrativeRepository, VCSRollbackError


@pytest.fixture
def vcs_repo():
    graph = BECGraph(":memory:")
    # 注册测试实体
    graph.register_entity("char_hero", "CHARACTER", "主角", created_chapter=1, initial_payload={"power": 100})
    repo = NarrativeRepository(db_path=":memory:", graph=graph)
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


def test_rollback_resets_both_vcs_and_graph(vcs_repo: NarrativeRepository):
    """测试时空回滚：剧情回滚同时重置实体因果图谱状态"""
    # 提交第 1 章
    vcs_repo.commit_chapter(1, "第1章", "正文1", StateDelta(chapter_index=1, entity_mutations={"char_hero": {"power": 100}}))
    # 提交第 2 章
    vcs_repo.commit_chapter(2, "第2章", "正文2", StateDelta(chapter_index=2, entity_mutations={"char_hero": {"power": 250}}))
    # 提交第 3 章 (出现剧情失误，战力膨胀到 99999)
    vcs_repo.commit_chapter(3, "第3章 失误章", "正文3", StateDelta(chapter_index=3, entity_mutations={"char_hero": {"power": 99999}}))

    # 验证回滚前第 3 章图谱状态
    state_ch3_before = vcs_repo.graph.get_entity_state_at("char_hero", 3)
    assert state_ch3_before["power"] == 99999

    # 执行时空回滚到第 2 章末尾
    vcs_repo.checkout_chapter(target_chapter_index=2)

    # 1. 验证 HEAD 游标重置到第 2 章
    head = vcs_repo.get_head_commit()
    assert head.chapter_index == 2

    # 2. 验证提交日志中第 3 章已被抹除
    log = vcs_repo.get_commit_log()
    assert len(log) == 2
    assert all(entry["chapter_index"] <= 2 for entry in log)

    # 3. 验证 BECGraph 数据库中大于第 2 章的历史状态已被干净回滚
    state_ch3_after = vcs_repo.graph.get_entity_state_at("char_hero", 3)
    # 因为第 3 章被回滚删除了，查第 3 章时应自然回退拿到第 2 章的真实状态 (250)
    assert state_ch3_after["power"] == 250


def test_branching_and_timeline_fork(vcs_repo: NarrativeRepository):
    """测试剧情分叉与多分支探索"""
    vcs_repo.commit_chapter(1, "第1章", "正文1", StateDelta(chapter_index=1))
    vcs_repo.commit_chapter(2, "第2章", "正文2", StateDelta(chapter_index=2))

    # 在第 2 章末尾开辟一个实验性暗黑向分支 'branch_dark'
    vcs_repo.create_branch("branch_dark")
    assert vcs_repo.current_branch == "branch_dark"

    # 在暗黑分支提交第 3 章
    c3_dark = vcs_repo.commit_chapter(3, "第3章 暗黑路线", "黑化正文3", StateDelta(chapter_index=3))
    assert c3_dark.branch_name == "branch_dark"

    # 切换回主干 main 分支
    vcs_repo.switch_branch("main")
    main_head = vcs_repo.get_head_commit()
    assert main_head.chapter_index == 2

    # 主干分支提交正常的第 3 章
    c3_normal = vcs_repo.commit_chapter(3, "第3章 正统路线", "光明正文3", StateDelta(chapter_index=3))
    assert c3_normal.branch_name == "main"
    assert c3_normal.commit_id != c3_dark.commit_id
