"""
Bi-temporal Entity-Causal Graph (BEC-Graph) - 双时态实体因果图谱引擎
基于 SQLite 构建的高性能实体时序知识图谱，支持任意章节快照时空回溯、因果不变式断言与关系生命周期追踪。
"""

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from src.novel_factory.schemas.character import CharacterProgression
from src.novel_factory.schemas.entity import EntityRelation, LoreEntry, StandardRelations


class CausalViolationError(Exception):
    """因果断言冲突异常（例如死人说话、使用未拥有的物品等）"""
    pass


class BECGraph:
    """双时态实体因果图谱管理器 (SQLite 实现)"""

    def __init__(self, db_path: Optional[str] = ":memory:"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        """初始化关系与实体存储表结构"""
        with self.conn:
            # 1. 实体主表 (包含生命周期)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    entity_id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    is_alive INTEGER DEFAULT 1,
                    created_chapter INTEGER NOT NULL,
                    invalidated_chapter INTEGER DEFAULT 999999,
                    current_payload_json TEXT NOT NULL,
                    metadata_json TEXT DEFAULT '{}'
                )
            """)
            # 2. 时序属性快照表 (记录每一章的状态突变)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS entity_progression_history (
                    entity_id TEXT NOT NULL,
                    chapter_index INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (entity_id, chapter_index),
                    FOREIGN KEY (entity_id) REFERENCES entities(entity_id)
                )
            """)
            # 3. 双时态实体关系边表 (带生效区间与证据链)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS entity_relations (
                    source_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    valid_from_chapter INTEGER NOT NULL,
                    valid_to_chapter INTEGER DEFAULT 999999,
                    provenance_chapter INTEGER NOT NULL,
                    intensity REAL DEFAULT 1.0,
                    evidence TEXT DEFAULT '',
                    metadata_json TEXT DEFAULT '{}',
                    PRIMARY KEY (source_id, relation_type, target_id, valid_from_chapter)
                )
            """)
            # 4. 因果约束规则表 (Causal Invariant DAG)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS causal_invariants (
                    invariant_id TEXT PRIMARY KEY,
                    rule_type TEXT NOT NULL, -- REQUIRE_RELATION | PROHIBIT_RELATION | REQUIRE_ALIVE
                    source_id TEXT NOT NULL,
                    expected_relation TEXT,
                    target_id TEXT,
                    error_message TEXT NOT NULL
                )
            """)
            # 索引
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_relations_temporal 
                ON entity_relations (source_id, valid_from_chapter, valid_to_chapter)
            """)
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_relations_target
                ON entity_relations (target_id, valid_from_chapter, valid_to_chapter)
            """)

    def register_entity(
        self,
        entity_id: str,
        entity_type: str,
        name: str,
        created_chapter: int = 1,
        initial_payload: Optional[Dict[str, Any]] = None,
        is_alive: bool = True
    ) -> None:
        """注册一个全新实体节点"""
        payload_str = json.dumps(initial_payload or {}, ensure_ascii=False)
        with self.conn:
            self.conn.execute("""
                INSERT OR REPLACE INTO entities 
                (entity_id, entity_type, name, is_alive, created_chapter, current_payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (entity_id, entity_type, name, 1 if is_alive else 0, created_chapter, payload_str))
            
            # 同时记录历史
            self.conn.execute("""
                INSERT OR REPLACE INTO entity_progression_history
                (entity_id, chapter_index, payload_json)
                VALUES (?, ?, ?)
            """, (entity_id, created_chapter, payload_str))

    def update_entity_progression(
        self,
        entity_id: str,
        chapter_index: int,
        new_payload: Dict[str, Any],
        is_alive: Optional[bool] = None
    ) -> None:
        """记录实体在特定章节的状态突变"""
        payload_str = json.dumps(new_payload, ensure_ascii=False)
        with self.conn:
            # 插入历史表
            self.conn.execute("""
                INSERT OR REPLACE INTO entity_progression_history
                (entity_id, chapter_index, payload_json)
                VALUES (?, ?, ?)
            """, (entity_id, chapter_index, payload_str))
            
            # 更新主表当前状态
            alive_clause = ""
            params: List[Any] = [payload_str]
            if is_alive is not None:
                alive_clause = ", is_alive = ?"
                params.append(1 if is_alive else 0)
            params.append(entity_id)
            
            self.conn.execute(f"""
                UPDATE entities 
                SET current_payload_json = ? {alive_clause}
                WHERE entity_id = ?
            """, params)

    def add_relation(self, relation: EntityRelation) -> None:
        """添加或更新一条带有效区间的时序关系边"""
        metadata_str = json.dumps(relation.metadata, ensure_ascii=False)
        with self.conn:
            self.conn.execute("""
                INSERT OR REPLACE INTO entity_relations
                (source_id, relation_type, target_id, valid_from_chapter, 
                 valid_to_chapter, provenance_chapter, intensity, evidence, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                relation.source_id,
                relation.relation_type,
                relation.target_id,
                relation.valid_from_chapter,
                relation.valid_to_chapter,
                relation.provenance_chapter,
                relation.intensity,
                relation.evidence,
                metadata_str
            ))

    def invalidate_relation(
        self,
        source_id: str,
        relation_type: str,
        target_id: str,
        cutoff_chapter: int
    ) -> bool:
        """将某条关系在特定章节后标记为失效 (valid_to_chapter = cutoff_chapter)"""
        with self.conn:
            cur = self.conn.execute("""
                UPDATE entity_relations
                SET valid_to_chapter = ?
                WHERE source_id = ? AND relation_type = ? AND target_id = ?
                  AND valid_from_chapter <= ? AND valid_to_chapter > ?
            """, (cutoff_chapter, source_id, relation_type, target_id, cutoff_chapter, cutoff_chapter))
            return cur.rowcount > 0

    def get_entity_state_at(self, entity_id: str, chapter: int) -> Optional[Dict[str, Any]]:
        """时空回溯：查询任意实体在第 N 章时的精确状态"""
        row = self.conn.execute("""
            SELECT payload_json FROM entity_progression_history
            WHERE entity_id = ? AND chapter_index <= ?
            ORDER BY chapter_index DESC LIMIT 1
        """, (entity_id, chapter)).fetchone()

        if row:
            return json.loads(row["payload_json"])
        return None

    def list_entities(
        self,
        entity_type: Optional[str] = None,
        alive_only: bool = False
    ) -> List[Dict[str, Any]]:
        """列出图谱中已注册的全部实体（用于在场纪律检查与重名冲突扫描）"""
        sql = "SELECT entity_id, entity_type, name, is_alive, created_chapter FROM entities"
        conds, params = [], []
        if entity_type:
            conds.append("entity_type = ?")
            params.append(entity_type)
        if alive_only:
            conds.append("is_alive = 1")
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        rows = self.conn.execute(sql, params).fetchall()
        return [
            {
                "entity_id": r[0],
                "entity_type": r[1],
                "name": r[2],
                "is_alive": bool(r[3]),
                "created_chapter": r[4],
            }
            for r in rows
        ]

    def get_active_relations_at(
        self,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        chapter: int = 1
    ) -> List[EntityRelation]:
        """查询在指定章节真实有效的实体关系集合"""
        clauses = ["valid_from_chapter <= ? AND valid_to_chapter >= ?"]
        params: List[Any] = [chapter, chapter]

        if source_id:
            clauses.append("source_id = ?")
            params.append(source_id)
        if target_id:
            clauses.append("target_id = ?")
            params.append(target_id)

        sql = f"SELECT * FROM entity_relations WHERE {' AND '.join(clauses)}"
        rows = self.conn.execute(sql, params).fetchall()

        results = []
        for r in rows:
            results.append(
                EntityRelation(
                    source_id=r["source_id"],
                    relation_type=r["relation_type"],
                    target_id=r["target_id"],
                    valid_from_chapter=r["valid_from_chapter"],
                    valid_to_chapter=r["valid_to_chapter"],
                    provenance_chapter=r["provenance_chapter"],
                    intensity=r["intensity"],
                    evidence=r["evidence"],
                    metadata=json.loads(r["metadata_json"] or "{}")
                )
            )
        return results

    def verify_action_causality(
        self,
        actor_id: str,
        action: str,
        target_id: Optional[str],
        chapter: int
    ) -> Tuple[bool, Optional[str]]:
        """
        因果硬不变式校验器：
        在下发生成前，从图论上判定行动在物理或逻辑上是否可能。
        例如：
        - 死亡实体不可作为施动者行动 (Zero-Zombie Invariant)
        - 使用道具前，必须具备 POSSESSES 关系且道具未失效
        """
        # 1. 存活性检查
        actor_row = self.conn.execute(
            "SELECT is_alive, name FROM entities WHERE entity_id = ?",
            (actor_id,)
        ).fetchone()

        if not actor_row:
            return False, f"施动实体不存在: {actor_id}"

        if actor_row["is_alive"] == 0:
            return False, f"因果悖论：实体 [{actor_row['name']}] 已死亡，无法在第 {chapter} 章执行 [{action}]"

        # 2. 装备持有性检查
        if action in ("USE_ITEM", "WIELD", "CONSUME", "EQUIP") and target_id:
            active_possession = self.get_active_relations_at(
                source_id=actor_id,
                target_id=target_id,
                chapter=chapter
            )
            has_item = any(r.relation_type == StandardRelations.POSSESSES for r in active_possession)
            if not has_item:
                target_name = target_id
                target_row = self.conn.execute("SELECT name FROM entities WHERE entity_id = ?", (target_id,)).fetchone()
                if target_row:
                    target_name = target_row["name"]
                return False, f"因果悖论：实体 [{actor_row['name']}] 在第 {chapter} 章并未持有 [{target_name}]，无法使用"

        return True, None

    def close(self):
        self.conn.close()
