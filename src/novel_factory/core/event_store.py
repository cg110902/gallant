"""
Event Store - 基于 SQLite 的工业级不可变事件溯源存储引擎
支持 WAL 高性能事务追加写、时序事件流重放、快照物化 (Checkpoints) 与跨章节状态重建。
"""

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from src.novel_factory.core.events import Event, EventType


@dataclass
class WorldSnapshot:
    """指定章节时空点物化的世界完整快照"""
    chapter_index: int
    last_sequence_num: int
    entities: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    relations: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    plot_threads: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chapter_index": self.chapter_index,
            "last_sequence_num": self.last_sequence_num,
            "entities": self.entities,
            "relations": self.relations,
            "plot_threads": self.plot_threads
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorldSnapshot":
        return cls(
            chapter_index=data["chapter_index"],
            last_sequence_num=data["last_sequence_num"],
            entities=data.get("entities", {}),
            relations=data.get("relations", {}),
            plot_threads=data.get("plot_threads", {})
        )


class EventStore:
    """事件溯源存储引擎"""

    def __init__(self, db_path: Optional[str] = ":memory:"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        """初始化事件追加日志与快照表"""
        with self.conn:
            # 启用 WAL 模式提高吞吐并发（如果是文件数据库）
            if self.db_path and self.db_path != ":memory:":
                try:
                    self.conn.execute("PRAGMA journal_mode=WAL;")
                except Exception:
                    pass

            # 1. 核心不可变事件表 (Append-Only Event Log)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS event_log (
                    sequence_num INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE NOT NULL,
                    chapter_index INTEGER NOT NULL,
                    beat_id TEXT,
                    timestamp REAL NOT NULL,
                    event_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    target_entity_id TEXT,
                    payload_json TEXT NOT NULL,
                    provenance_text TEXT DEFAULT ''
                )
            """)

            # 2. 定期快照检查点表 (Snapshots Checkpoints)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    chapter_index INTEGER PRIMARY KEY,
                    last_sequence_num INTEGER NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)

            # 索引
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_event_chapter 
                ON event_log (chapter_index, sequence_num)
            """)
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_event_entity 
                ON event_log (entity_id, sequence_num)
            """)

    def append_event(self, event: Event, idempotent: bool = False) -> Event:
        """
        追加单个不可变事件。

        idempotent=True 时对已存在的 event_id 静默忽略，用于断点续产等
        会重放同一批初始化事件的场景（例如角色注册）。
        """
        verb = "INSERT OR IGNORE INTO" if idempotent else "INSERT INTO"
        with self.conn:
            cur = self.conn.execute(f"""
                {verb} event_log (
                    event_id, chapter_index, beat_id, timestamp,
                    event_type, entity_id, target_entity_id, payload_json, provenance_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event.event_id,
                event.chapter_index,
                event.beat_id,
                event.timestamp,
                event.event_type.value,
                event.entity_id,
                event.target_entity_id,
                json.dumps(event.payload, ensure_ascii=False),
                event.provenance_text
            ))
            seq_num = cur.lastrowid
            event.sequence_num = seq_num
            return event

    def append_batch(self, events: List[Event]) -> List[Event]:
        """原子事务批量追加事件"""
        results = []
        with self.conn:
            for ev in events:
                cur = self.conn.execute("""
                    INSERT INTO event_log (
                        event_id, chapter_index, beat_id, timestamp,
                        event_type, entity_id, target_entity_id, payload_json, provenance_text
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ev.event_id,
                    ev.chapter_index,
                    ev.beat_id,
                    ev.timestamp,
                    ev.event_type.value,
                    ev.entity_id,
                    ev.target_entity_id,
                    json.dumps(ev.payload, ensure_ascii=False),
                    ev.provenance_text
                ))
                ev.sequence_num = cur.lastrowid
                results.append(ev)
        return results

    def get_events(
        self,
        chapter_min: int = 1,
        chapter_max: int = 999999,
        entity_id: Optional[str] = None,
        event_type: Optional[EventType] = None
    ) -> List[Event]:
        """条件检索历史事件流"""
        clauses = ["chapter_index >= ? AND chapter_index <= ?"]
        params: List[Any] = [chapter_min, chapter_max]

        if entity_id:
            clauses.append("(entity_id = ? OR target_entity_id = ?)")
            params.extend([entity_id, entity_id])
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type.value)

        sql = f"SELECT * FROM event_log WHERE {' AND '.join(clauses)} ORDER BY sequence_num ASC"
        rows = self.conn.execute(sql, params).fetchall()

        events = []
        for r in rows:
            events.append(Event(
                event_id=r["event_id"],
                sequence_num=r["sequence_num"],
                chapter_index=r["chapter_index"],
                beat_id=r["beat_id"],
                timestamp=r["timestamp"],
                event_type=EventType(r["event_type"]),
                entity_id=r["entity_id"],
                target_entity_id=r["target_entity_id"],
                payload=json.loads(r["payload_json"]),
                provenance_text=r["provenance_text"] or ""
            ))
        return events

    def materialize_world_at(self, chapter_index: int) -> WorldSnapshot:
        """
        核心重放引擎 (Event Replay)：
        重放从创世（或最近检查点）到目标章节的所有领域事件，精确物化世界状态
        """
        # 1. 尝试寻找 <= chapter_index 的最近快照
        chk_row = self.conn.execute("""
            SELECT * FROM checkpoints 
            WHERE chapter_index <= ? 
            ORDER BY chapter_index DESC LIMIT 1
        """, (chapter_index,)).fetchone()

        if chk_row:
            snap = WorldSnapshot.from_dict(json.loads(chk_row["snapshot_json"]))
            min_seq = snap.last_sequence_num + 1
        else:
            snap = WorldSnapshot(chapter_index=chapter_index, last_sequence_num=0)
            min_seq = 1

        # 2. 拉取增量事件流
        rows = self.conn.execute("""
            SELECT * FROM event_log
            WHERE sequence_num >= ? AND chapter_index <= ?
            ORDER BY sequence_num ASC
        """, (min_seq, chapter_index)).fetchall()

        # 3. 逐个重放事件变迁
        for r in rows:
            ev_type = EventType(r["event_type"])
            src_id = r["entity_id"]
            tgt_id = r["target_entity_id"]
            payload = json.loads(r["payload_json"])
            seq = r["sequence_num"]
            snap.last_sequence_num = seq

            # A. 实体诞生
            if ev_type == EventType.ENTITY_SPAWNED:
                snap.entities[src_id] = {
                    "entity_id": src_id,
                    "entity_type": payload.get("entity_type", "GENERIC"),
                    "name": payload.get("name", src_id),
                    "is_alive": True,
                    "attributes": payload.get("attributes", {}),
                    "inventory": payload.get("inventory", []),
                    "created_at_chapter": r["chapter_index"]
                }

            # B. 实体属性变动
            elif ev_type == EventType.ATTRIBUTE_CHANGED:
                if src_id in snap.entities:
                    snap.entities[src_id]["attributes"].update(payload)

            # C. 获得道具
            elif ev_type == EventType.ITEM_ACQUIRED:
                if src_id in snap.entities:
                    snap.entities[src_id]["inventory"].append(payload)

            # D. 道具流转（转赠/夺取）
            elif ev_type == EventType.ITEM_TRANSFERRED:
                item_id = payload.get("item_id")
                # 从源实体移除
                if src_id in snap.entities:
                    snap.entities[src_id]["inventory"] = [
                        item for item in snap.entities[src_id]["inventory"]
                        if item.get("item_id") != item_id
                    ]
                # 放入目标实体
                if tgt_id and tgt_id in snap.entities:
                    snap.entities[tgt_id]["inventory"].append(payload)

            # E. 道具销毁
            elif ev_type == EventType.ITEM_DESTROYED:
                item_id = payload.get("item_id")
                if src_id in snap.entities:
                    snap.entities[src_id]["inventory"] = [
                        item for item in snap.entities[src_id]["inventory"]
                        if item.get("item_id") != item_id
                    ]

            # F. 关系建立
            elif ev_type == EventType.RELATION_FORMED:
                rel_type = payload.get("relation_type", "GENERIC_RELATION")
                key = f"{src_id}:{rel_type}:{tgt_id}"
                snap.relations[key] = {
                    "source_id": src_id,
                    "relation_type": rel_type,
                    "target_id": tgt_id,
                    "intensity": payload.get("intensity", 1.0),
                    "established_at_chapter": r["chapter_index"],
                    "metadata": payload.get("metadata", {})
                }

            # G. 关系解除
            elif ev_type == EventType.RELATION_TERMINATED:
                rel_type = payload.get("relation_type", "GENERIC_RELATION")
                key = f"{src_id}:{rel_type}:{tgt_id}"
                snap.relations.pop(key, None)

            # H. 实体死亡
            elif ev_type == EventType.ENTITY_KILLED:
                if src_id in snap.entities:
                    snap.entities[src_id]["is_alive"] = False
                    snap.entities[src_id]["killer_id"] = tgt_id
                    snap.entities[src_id]["killed_at_chapter"] = r["chapter_index"]

            # I. 伏笔埋设
            elif ev_type == EventType.PLOT_THREAD_OPENED:
                thread_id = payload.get("thread_id", src_id)
                snap.plot_threads[thread_id] = {
                    "thread_id": thread_id,
                    "name": payload.get("name", ""),
                    "status": "OPEN",
                    "opened_at_chapter": r["chapter_index"]
                }

            # J. 伏笔闭环
            elif ev_type == EventType.PLOT_THREAD_RESOLVED:
                thread_id = payload.get("thread_id", src_id)
                if thread_id in snap.plot_threads:
                    snap.plot_threads[thread_id]["status"] = "RESOLVED"
                    snap.plot_threads[thread_id]["resolved_at_chapter"] = r["chapter_index"]

        snap.chapter_index = chapter_index
        return snap

    def save_checkpoint(self, chapter_index: int) -> WorldSnapshot:
        """为特定章节物化并固化快照检查点"""
        snap = self.materialize_world_at(chapter_index)
        with self.conn:
            self.conn.execute("""
                INSERT OR REPLACE INTO checkpoints
                (chapter_index, last_sequence_num, snapshot_json, created_at)
                VALUES (?, ?, ?, ?)
            """, (
                chapter_index,
                snap.last_sequence_num,
                json.dumps(snap.to_dict(), ensure_ascii=False),
                time.time()
            ))
        return snap

    def truncate_after_chapter(self, target_chapter_index: int) -> int:
        """
        物理回滚截断：
        删除所有在 target_chapter_index 之后产生的事件与快照
        """
        with self.conn:
            cur1 = self.conn.execute(
                "DELETE FROM event_log WHERE chapter_index > ?",
                (target_chapter_index,)
            )
            deleted_events = cur1.rowcount
            self.conn.execute(
                "DELETE FROM checkpoints WHERE chapter_index > ?",
                (target_chapter_index,)
            )
            return deleted_events

    def close(self):
        self.conn.close()
