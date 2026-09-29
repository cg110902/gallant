"""
版本库数据完整性回归测试

长篇创作中回滚是高频操作。这些用例锁死三个曾经真实存在的数据事故：
1. 回滚直接物理删除后续提交 —— 一次误操作永久丢稿；
2. 新分支看不到分叉点之前的历史 —— 日志像是从第 N 章凭空开始；
3. 切换分支不重建世界状态 —— 切回 main 仍能看到另一分支的战力数值。
"""

import pytest

from src.novel_factory.graph.bec_graph import UnknownEntityError
from src.novel_factory.orchestrator import NovelFactoryOrchestrator
from src.novel_factory.schemas.commit import StateDelta
from src.novel_factory.vcs.repository import VCSRollbackError


@pytest.fixture
def orch():
    o = NovelFactoryOrchestrator(db_path=":memory:", llm_worker=lambda s, u: "正文")
    o.register_entity("c1", "CHARACTER", "甲", created_chapter=1)
    yield o
    o.close()


def _commit(o, ch, title, power):
    return o.repo.commit_chapter(
        ch, title, "正文内容" * 30,
        StateDelta(chapter_index=ch, entity_mutations={"c1": {"power_rating": power}}),
        {},
    )


# ---------- 非破坏性回滚 ----------

def test_rollback_does_not_destroy_commits(orch):
    for ch in (1, 2, 3):
        _commit(orch, ch, f"主线{ch}", ch * 100.0)

    orch.repo.checkout_chapter(2)
    assert [c["title"] for c in orch.repo.get_commit_log()] == ["主线1", "主线2"]

    orphans = orch.repo.list_orphaned_commits()
    assert len(orphans) == 1
    assert orphans[0]["chapter_index"] == 3


def test_orphaned_commit_can_be_restored(orch):
    for ch in (1, 2, 3):
        _commit(orch, ch, f"主线{ch}", ch * 100.0)
    orch.repo.checkout_chapter(2)

    orphan_id = orch.repo.list_orphaned_commits()[0]["commit_id"]
    assert orch.repo.restore_orphaned_commit(orphan_id) is True

    assert [c["title"] for c in orch.repo.get_commit_log()] == ["主线1", "主线2", "主线3"]
    assert orch.repo.get_head_commit().chapter_index == 3
    assert orch.repo.list_orphaned_commits() == []


def test_hard_rollback_is_opt_in_and_destructive(orch):
    for ch in (1, 2, 3):
        _commit(orch, ch, f"主线{ch}", ch * 100.0)

    orch.repo.checkout_chapter(2, hard=True)
    assert orch.repo.list_orphaned_commits() == []  # 真删了，无法恢复
    assert [c["title"] for c in orch.repo.get_commit_log()] == ["主线1", "主线2"]


def test_rollback_to_missing_chapter_raises(orch):
    _commit(orch, 1, "主线1", 100.0)
    with pytest.raises(VCSRollbackError):
        orch.repo.checkout_chapter(99)


def test_rollback_syncs_world_state(orch):
    for ch in (1, 2, 3):
        _commit(orch, ch, f"主线{ch}", ch * 100.0)
    assert orch.graph.get_entity_state_at("c1", 3)["power_rating"] == 300.0

    orch.repo.checkout_chapter(2)
    assert orch.graph.get_entity_state_at("c1", 3)["power_rating"] == 200.0


# ---------- 分支 ----------

def test_branch_inherits_ancestor_history(orch):
    for ch in (1, 2, 3):
        _commit(orch, ch, f"主线{ch}", ch * 100.0)
    orch.repo.checkout_chapter(2)
    orch.repo.create_branch("alt")
    _commit(orch, 3, "alt第三章", 9999.0)

    titles = [c["title"] for c in orch.repo.get_commit_log()]
    assert titles == ["主线1", "主线2", "alt第三章"], "新分支必须继承分叉点之前的历史"


def test_branch_switch_rebuilds_world_state(orch):
    for ch in (1, 2, 3):
        _commit(orch, ch, f"主线{ch}", ch * 100.0)
    orch.repo.checkout_chapter(2)
    orch.repo.create_branch("alt")
    _commit(orch, 3, "alt第三章", 9999.0)
    assert orch.graph.get_entity_state_at("c1", 3)["power_rating"] == 9999.0

    orch.repo.switch_branch("main")
    assert orch.graph.get_entity_state_at("c1", 3)["power_rating"] == 200.0, \
        "切回 main 后不得再看到 alt 分支的状态"

    orch.repo.switch_branch("alt")
    assert orch.graph.get_entity_state_at("c1", 3)["power_rating"] == 9999.0, \
        "切回 alt 必须恢复该分支的状态"


def test_switch_to_unknown_branch_raises(orch):
    with pytest.raises(VCSRollbackError):
        orch.repo.switch_branch("does-not-exist")


def test_rebuild_world_is_deterministic(orch):
    for ch in (1, 2, 3):
        _commit(orch, ch, f"主线{ch}", ch * 100.0)
    before = orch.graph.get_entity_state_at("c1", 3)["power_rating"]
    orch.repo.rebuild_world_from_history("main")
    orch.repo.rebuild_world_from_history("main")
    assert orch.graph.get_entity_state_at("c1", 3)["power_rating"] == before


# ---------- 实体完整性 ----------

def test_progression_for_unregistered_entity_is_rejected(orch):
    """
    此前外键约束未开启，为不存在的实体写成长历史会静默产生孤儿数据，
    而这正是幽灵角色绕过一致性检查的入口。
    """
    with pytest.raises(UnknownEntityError) as exc:
        orch.graph.update_entity_progression("ghost_不存在", 1, {"power_rating": 1.0})
    assert "register_entity" in str(exc.value)


def test_commit_with_unknown_entity_surfaces_clear_error(orch):
    with pytest.raises(UnknownEntityError):
        orch.repo.commit_chapter(
            1, "第一章", "正文" * 30,
            StateDelta(chapter_index=1, entity_mutations={"ghost": {"power_rating": 1.0}}),
            {},
        )


# ---------- 资源管理 ----------

def test_close_releases_all_connections():
    """此前只关了 repo，伏笔台账连接被泄漏"""
    import sqlite3

    o = NovelFactoryOrchestrator(db_path=":memory:", llm_worker=lambda s, u: "x")
    o.close()
    for conn in (o.repo.conn, o.graph.conn, o.event_store.conn, o.foreshadow_ledger.conn):
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")


def test_orchestrator_supports_context_manager():
    import sqlite3

    with NovelFactoryOrchestrator(db_path=":memory:", llm_worker=lambda s, u: "x") as o:
        assert o.repo is not None
    with pytest.raises(sqlite3.ProgrammingError):
        o.repo.conn.execute("SELECT 1")


def test_file_db_enables_wal(tmp_path):
    """文件库必须启用 WAL，否则多连接并发写会频繁撞锁"""
    db = str(tmp_path / "n.db")
    o = NovelFactoryOrchestrator(db_path=db, llm_worker=lambda s, u: "x")
    mode = o.repo.conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
    timeout = o.repo.conn.execute("PRAGMA busy_timeout").fetchone()[0]
    assert timeout >= 1000
    o.close()


def test_persisted_db_survives_reopen(tmp_path):
    db = str(tmp_path / "n.db")
    o = NovelFactoryOrchestrator(db_path=db, llm_worker=lambda s, u: "x")
    o.register_entity("c1", "CHARACTER", "甲", created_chapter=1)
    _commit(o, 1, "第一章", 100.0)
    o.foreshadow_ledger.plant("fs1", "断剑之谜", planted_chapter=1, keywords=["断剑"])
    o.close()

    o2 = NovelFactoryOrchestrator(db_path=db, llm_worker=lambda s, u: "x")
    assert o2.repo.get_head_commit().title == "第一章"
    assert [e["name"] for e in o2.graph.list_entities()] == ["甲"]
    assert [f.foreshadow_id for f in o2.foreshadow_ledger.list_open()] == ["fs1"]
    o2.close()


# ---------- 重复生产 ----------

def test_reproducing_chapter_supersedes_instead_of_duplicating(orch):
    """
    质检驳回后重跑同一章，此前会再追加一条提交，
    导出的稿件里就出现了同一章的多个版本。
    """
    for ch in (1, 2, 3):
        _commit(orch, ch, f"第{ch}章", ch * 100.0)

    orch.repo.commit_chapter(
        2, "第2章-改写", "改写后的正文" * 30,
        StateDelta(chapter_index=2, entity_mutations={"c1": {"power_rating": 250.0}}), {},
    )

    log = orch.repo.get_commit_log(50)
    assert [c["chapter_index"] for c in log] == [1, 2, 3], "章节不得重复出现"
    assert [c["title"] for c in log] == ["第1章", "第2章-改写", "第3章"]

    orphans = orch.repo.list_orphaned_commits()
    assert [(o["chapter_index"], o["title"]) for o in orphans] == [(2, "第2章")], \
        "被取代的旧版本仍应可恢复"


def test_reproducing_identical_content_is_idempotent(orch):
    """内容完全一致 = 同一个提交，重产应是无操作而不是撞唯一约束"""
    c1 = _commit(orch, 1, "第一章", 100.0)
    c2 = _commit(orch, 1, "第一章", 100.0)
    assert c1.commit_id == c2.commit_id
    assert len(orch.repo.get_commit_log(50)) == 1
    assert orch.repo.list_orphaned_commits() == []


def test_reproducing_middle_chapter_keeps_head_at_tail(orch):
    for ch in (1, 2, 3):
        _commit(orch, ch, f"第{ch}章", ch * 100.0)
    orch.repo.commit_chapter(
        2, "第2章-改写", "改写" * 40,
        StateDelta(chapter_index=2, entity_mutations={"c1": {"power_rating": 250.0}}), {},
    )
    assert orch.repo.get_head_commit().chapter_index == 3, "重产中间章不应把 HEAD 拉回去"


def test_exporter_sees_no_duplicate_chapters(orch):
    for ch in (1, 2):
        _commit(orch, ch, f"第{ch}章", ch * 100.0)
    for _ in range(3):
        orch.repo.commit_chapter(
            2, "第2章-再改", "再改" * 40,
            StateDelta(chapter_index=2, entity_mutations={"c1": {"power_rating": 260.0}}), {},
        )
    chapters = orch.exporter.get_all_chapters()
    assert [c["chapter_index"] for c in chapters] == [1, 2]


def test_restoring_a_multi_chapter_rollback_keeps_the_chain_intact(orch):
    """
    实测发现：回滚 10 章后恢复最后一条孤立提交，
    可见章节从 20 章塌缩到 1 章——被恢复提交的父节点仍是孤立状态，祖先链断了。
    恢复必须连带补齐整段链条。
    """
    for ch in range(1, 21):
        _commit(orch, ch, f"第{ch}章", ch * 10.0)
    assert len(orch.repo.get_commit_log(99)) == 20

    orch.repo.checkout_chapter(10)
    assert len(orch.repo.get_commit_log(99)) == 10
    orphans = orch.repo.list_orphaned_commits()
    assert len(orphans) == 10

    last_orphan = max(orphans, key=lambda o: o["chapter_index"])
    assert orch.repo.restore_orphaned_commit(last_orphan["commit_id"]) is True

    log = orch.repo.get_commit_log(99)
    assert [c["chapter_index"] for c in log] == list(range(1, 21)), \
        "恢复后祖先链必须连续，不能只剩被恢复的那一章"
    assert orch.repo.list_orphaned_commits() == []


def test_partial_restore_stops_at_requested_chapter(orch):
    """只想撤销一半回滚时，恢复到指定章为止"""
    for ch in range(1, 11):
        _commit(orch, ch, f"第{ch}章", ch * 10.0)
    orch.repo.checkout_chapter(4)

    orphans = orch.repo.list_orphaned_commits()
    target = next(o for o in orphans if o["chapter_index"] == 7)
    orch.repo.restore_orphaned_commit(target["commit_id"])

    log = orch.repo.get_commit_log(99)
    assert [c["chapter_index"] for c in log] == [1, 2, 3, 4, 5, 6, 7]
    assert [o["chapter_index"] for o in orch.repo.list_orphaned_commits()] == [8, 9, 10]


def test_restore_all_orphaned_undoes_the_rollback(orch):
    for ch in range(1, 11):
        _commit(orch, ch, f"第{ch}章", ch * 10.0)
    orch.repo.checkout_chapter(3)
    assert orch.repo.restore_all_orphaned() == 7
    assert len(orch.repo.get_commit_log(99)) == 10


def test_restore_rebuilds_world_state(orch):
    for ch in range(1, 11):
        _commit(orch, ch, f"第{ch}章", ch * 10.0)
    orch.repo.checkout_chapter(5)
    assert orch.graph.get_entity_state_at("c1", 10)["power_rating"] == 50.0

    orch.repo.restore_all_orphaned()
    assert orch.graph.get_entity_state_at("c1", 10)["power_rating"] == 100.0
