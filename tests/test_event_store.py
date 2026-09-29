import os
import tempfile
import pytest
from src.novel_factory.core.events import Event, EventType
from src.novel_factory.core.event_store import EventStore, WorldSnapshot


@pytest.fixture
def mem_store():
    store = EventStore(db_path=":memory:")
    yield store
    store.close()


@pytest.fixture
def disk_store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_path = f.name
    store = EventStore(db_path=temp_path)
    yield store
    store.close()
    if os.path.exists(temp_path):
        os.remove(temp_path)


def test_event_append_and_sequence(mem_store):
    """验证事件追加与严格单调自增序号"""
    e1 = Event(
        event_id="ev_001",
        chapter_index=1,
        event_type=EventType.ENTITY_SPAWNED,
        entity_id="char_lin_dong",
        payload={"name": "林动", "entity_type": "PROTAGONIST", "attributes": {"realm": "淬体一重"}}
    )
    e2 = Event(
        event_id="ev_002",
        chapter_index=1,
        event_type=EventType.ITEM_ACQUIRED,
        entity_id="char_lin_dong",
        payload={"item_id": "stone_amulet", "name": "神秘石符"}
    )
    
    res1 = mem_store.append_event(e1)
    res2 = mem_store.append_event(e2)
    
    assert res1.sequence_num == 1
    assert res2.sequence_num == 2


def test_batch_append_and_query(mem_store):
    """验证批量原子追加与条件过滤"""
    events = [
        Event(
            event_id=f"ev_batch_{i}",
            chapter_index=i // 2 + 1,
            event_type=EventType.ATTRIBUTE_CHANGED if i % 2 == 0 else EventType.RELATION_FORMED,
            entity_id="char_lin_dong",
            target_entity_id="char_diao" if i % 2 != 0 else None,
            payload={"step": i}
        )
        for i in range(10)
    ]
    appended = mem_store.append_batch(events)
    assert len(appended) == 10
    assert appended[-1].sequence_num == 10
    
    # 检索过滤
    ch1_events = mem_store.get_events(chapter_min=1, chapter_max=1)
    assert len(ch1_events) == 2
    
    rel_events = mem_store.get_events(event_type=EventType.RELATION_FORMED)
    assert len(rel_events) == 5


def test_world_materialization_lifecycle(mem_store):
    """
    全生命周期时空物化测试：
    1. 实体诞生
    2. 属性提升
    3. 获得道具
    4. 转移道具给目标
    5. 建立关系
    6. 伏笔埋设与闭环
    7. 击杀与死亡
    """
    events = [
        # Chapter 1: 林动与貂爷登场
        Event(
            event_id="e1",
            chapter_index=1,
            event_type=EventType.ENTITY_SPAWNED,
            entity_id="char_lin",
            payload={"name": "林动", "attributes": {"realm": "淬体一重"}}
        ),
        Event(
            event_id="e2",
            chapter_index=1,
            event_type=EventType.ENTITY_SPAWNED,
            entity_id="char_diao",
            payload={"name": "小貂", "attributes": {"form": "妖灵"}}
        ),
        # Chapter 1: 获得石符
        Event(
            event_id="e3",
            chapter_index=1,
            event_type=EventType.ITEM_ACQUIRED,
            entity_id="char_lin",
            payload={"item_id": "stone_amulet", "name": "神秘石符", "tier": "天宝"}
        ),
        # Chapter 2: 建立伙伴契约
        Event(
            event_id="e4",
            chapter_index=2,
            event_type=EventType.RELATION_FORMED,
            entity_id="char_lin",
            target_entity_id="char_diao",
            payload={"relation_type": "ALLY", "intensity": 0.8}
        ),
        # Chapter 2: 埋设伏笔
        Event(
            event_id="e5",
            chapter_index=2,
            event_type=EventType.PLOT_THREAD_OPENED,
            entity_id="thread_ancestor_symbol",
            payload={"name": "寻找吞噬祖符", "scope": "MAIN_ARC"}
        ),
        # Chapter 3: 石符借予小貂温养
        Event(
            event_id="e6",
            chapter_index=3,
            event_type=EventType.ITEM_TRANSFERRED,
            entity_id="char_lin",
            target_entity_id="char_diao",
            payload={"item_id": "stone_amulet", "name": "神秘石符", "tier": "天宝"}
        ),
        # Chapter 3: 林动境界突破
        Event(
            event_id="e7",
            chapter_index=3,
            event_type=EventType.ATTRIBUTE_CHANGED,
            entity_id="char_lin",
            payload={"realm": "地元境初期"}
        ),
        # Chapter 4: 伏笔解决
        Event(
            event_id="e8",
            chapter_index=4,
            event_type=EventType.PLOT_THREAD_RESOLVED,
            entity_id="thread_ancestor_symbol",
            payload={"thread_id": "thread_ancestor_symbol"}
        ),
        # Chapter 4: 反派登场被斩杀
        Event(
            event_id="e9",
            chapter_index=4,
            event_type=EventType.ENTITY_SPAWNED,
            entity_id="char_villain",
            payload={"name": "黑风寨主", "attributes": {"realm": "地元境"}}
        ),
        Event(
            event_id="e10",
            chapter_index=4,
            event_type=EventType.ENTITY_KILLED,
            entity_id="char_villain",
            target_entity_id="char_lin",
            payload={"cause": "一拳轰碎心脉"}
        ),
    ]
    mem_store.append_batch(events)

    # 1. 验证 Chapter 1 状态
    snap_ch1 = mem_store.materialize_world_at(1)
    assert "char_lin" in snap_ch1.entities
    assert snap_ch1.entities["char_lin"]["attributes"]["realm"] == "淬体一重"
    assert len(snap_ch1.entities["char_lin"]["inventory"]) == 1
    assert snap_ch1.entities["char_lin"]["inventory"][0]["item_id"] == "stone_amulet"
    assert len(snap_ch1.entities["char_diao"]["inventory"]) == 0
    assert len(snap_ch1.relations) == 0

    # 2. 验证 Chapter 3 状态（石符已转移，境界提升）
    snap_ch3 = mem_store.materialize_world_at(3)
    assert snap_ch3.entities["char_lin"]["attributes"]["realm"] == "地元境初期"
    # 林动的石符已移出
    assert len(snap_ch3.entities["char_lin"]["inventory"]) == 0
    # 小貂获得石符
    assert len(snap_ch3.entities["char_diao"]["inventory"]) == 1
    assert snap_ch3.entities["char_diao"]["inventory"][0]["item_id"] == "stone_amulet"
    # 关系存在
    assert "char_lin:ALLY:char_diao" in snap_ch3.relations
    # 伏笔处于 OPEN 状态
    assert snap_ch3.plot_threads["thread_ancestor_symbol"]["status"] == "OPEN"

    # 3. 验证 Chapter 4 状态（伏笔闭环，反派死亡）
    snap_ch4 = mem_store.materialize_world_at(4)
    assert snap_ch4.plot_threads["thread_ancestor_symbol"]["status"] == "RESOLVED"
    assert snap_ch4.entities["char_villain"]["is_alive"] is False
    assert snap_ch4.entities["char_villain"]["killer_id"] == "char_lin"


def test_checkpoints_acceleration(mem_store):
    """验证快照持久化检查点与增量重放"""
    # 写入 50 个事件跨越 10 章
    events = []
    for ch in range(1, 11):
        events.append(Event(
            event_id=f"ch_{ch}_spawn",
            chapter_index=ch,
            event_type=EventType.ENTITY_SPAWNED,
            entity_id=f"mob_{ch}",
            payload={"name": f"野怪_{ch}"}
        ))
    mem_store.append_batch(events)

    # 在第 5 章保存快照检查点
    snap5 = mem_store.save_checkpoint(5)
    assert snap5.chapter_index == 5
    assert len(snap5.entities) == 5

    # 重新物化第 8 章，应当利用第 5 章快照并只重放 6..8 章
    snap8 = mem_store.materialize_world_at(8)
    assert len(snap8.entities) == 8
    assert "mob_5" in snap8.entities
    assert "mob_8" in snap8.entities
    assert "mob_9" not in snap8.entities


def test_rollback_and_truncation(mem_store):
    """验证剧情物理回滚截断功能"""
    events = [
        Event(
            event_id=f"ev_ch_{ch}",
            chapter_index=ch,
            event_type=EventType.ENTITY_SPAWNED,
            entity_id=f"entity_{ch}",
            payload={"name": f"人物_{ch}"}
        )
        for ch in range(1, 6)
    ]
    mem_store.append_batch(events)
    mem_store.save_checkpoint(3)
    mem_store.save_checkpoint(5)

    # 确认第 5 章有 5 个实体
    assert len(mem_store.materialize_world_at(5).entities) == 5

    # 执行物理回滚到第 3 章
    deleted_count = mem_store.truncate_after_chapter(3)
    assert deleted_count == 2  # 删除了 ch4 和 ch5 的 2 个事件

    # 再次查询第 5 章状态，只能物化出到第 3 章的状态
    snap_after_rollback = mem_store.materialize_world_at(5)
    assert len(snap_after_rollback.entities) == 3
    assert "entity_4" not in snap_after_rollback.entities
    assert "entity_5" not in snap_after_rollback.entities

    # 快照表里第 5 章的快照也被删除
    cur = mem_store.conn.execute("SELECT chapter_index FROM checkpoints").fetchall()
    checkpoint_chs = [r["chapter_index"] for r in cur]
    assert 5 not in checkpoint_chs
    assert 3 in checkpoint_chs


def test_disk_store_persistence(disk_store):
    """验证磁盘 SQLite 文件的持久性与重载"""
    event = Event(
        event_id="disk_ev_1",
        chapter_index=1,
        event_type=EventType.ENTITY_SPAWNED,
        entity_id="hero",
        payload={"name": "叶凡"}
    )
    disk_store.append_event(event)
    disk_store.save_checkpoint(1)
    
    # 用同一路径打开新 Store
    store2 = EventStore(db_path=disk_store.db_path)
    snap = store2.materialize_world_at(1)
    assert "hero" in snap.entities
    assert snap.entities["hero"]["name"] == "叶凡"
    store2.close()
