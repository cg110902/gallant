"""
Narrative VCS Repository - 剧情版本控制与时空回滚仓库 (Git-DAG for Stories)
管理章节提交历史、分支分叉 (Branching)、剧情回滚 (Rollback) 与实体因果图谱/事件库同步回溯。
特性：
1. SHA-256 校验和原子提交；
2. 一键时空物理回滚 (checkout_chapter)：同步联动 BECGraph, EventStore 与 ProgressionEngine；
3. 多剧情分支探索 (Branching: 如主线正道 vs 实验性黑化线)；
4. 分支差分对比 (Branch Diff) 与里程碑标签 (Tagging)。
"""

import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from src.novel_factory.core.event_store import EventStore
from src.novel_factory.codex.progression_engine import ProgressionEngine
from src.novel_factory.graph.bec_graph import BECGraph
from src.novel_factory.schemas.commit import StateDelta, StoryCommit


class VCSRollbackError(Exception):
    """回滚或分支切换异常"""
    pass


class NarrativeRepository:
    """剧情版本控制仓库"""

    def __init__(
        self,
        db_path: Optional[str] = ":memory:",
        graph: Optional[BECGraph] = None,
        event_store: Optional[EventStore] = None,
        progression_engine: Optional[ProgressionEngine] = None
    ):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.graph = graph or BECGraph(":memory:")
        self.event_store = event_store
        self.progression_engine = progression_engine
        self.current_branch: str = "main"
        self._init_tables()

    def _init_tables(self):
        """初始化提交记录表、分支表与标签表"""
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS commits (
                    commit_id TEXT PRIMARY KEY,
                    parent_commit_id TEXT,
                    branch_name TEXT NOT NULL,
                    chapter_index INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    full_prose TEXT NOT NULL,
                    word_count INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    state_delta_json TEXT NOT NULL,
                    qc_metrics_json TEXT DEFAULT '{}'
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS branches (
                    branch_name TEXT PRIMARY KEY,
                    head_commit_id TEXT,
                    created_at REAL NOT NULL
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS tags (
                    tag_name TEXT PRIMARY KEY,
                    commit_id TEXT NOT NULL,
                    message TEXT DEFAULT '',
                    created_at REAL NOT NULL
                )
            """)
            # 默认建立 main 分支
            self.conn.execute("""
                INSERT OR IGNORE INTO branches (branch_name, head_commit_id, created_at)
                VALUES ('main', NULL, 0)
            """)

    def get_head_commit(self, branch_name: Optional[str] = None) -> Optional[StoryCommit]:
        """获取当前分支或指定分支的最新 HEAD 提交"""
        branch = branch_name or self.current_branch
        b_row = self.conn.execute(
            "SELECT head_commit_id FROM branches WHERE branch_name = ?",
            (branch,)
        ).fetchone()

        if not b_row or not b_row["head_commit_id"]:
            return None

        c_row = self.conn.execute(
            "SELECT * FROM commits WHERE commit_id = ?",
            (b_row["head_commit_id"],)
        ).fetchone()

        if not c_row:
            return None

        delta_dict = json.loads(c_row["state_delta_json"])
        return StoryCommit(
            commit_id=c_row["commit_id"],
            parent_commit_id=c_row["parent_commit_id"],
            branch_name=c_row["branch_name"],
            chapter_index=c_row["chapter_index"],
            title=c_row["title"],
            full_prose=c_row["full_prose"],
            word_count=c_row["word_count"],
            created_at=c_row["created_at"],
            state_delta=StateDelta(**delta_dict),
            qc_metrics=json.loads(c_row["qc_metrics_json"] or "{}")
        )

    def commit_chapter(
        self,
        chapter_index: int,
        title: str,
        full_prose: str,
        state_delta: StateDelta,
        qc_metrics: Optional[Dict[str, Any]] = None
    ) -> StoryCommit:
        """
        原子提交一个新章节并同步突变实体图谱
        """
        head = self.get_head_commit()
        parent_id = head.commit_id if head else None

        commit = StoryCommit.create(
            chapter_index=chapter_index,
            title=title,
            full_prose=full_prose,
            state_delta=state_delta,
            parent_commit_id=parent_id,
            branch_name=self.current_branch,
            qc_metrics=qc_metrics
        )

        with self.conn:
            # 1. 存储提交记录
            self.conn.execute("""
                INSERT INTO commits (
                    commit_id, parent_commit_id, branch_name, chapter_index,
                    title, full_prose, word_count, created_at, state_delta_json, qc_metrics_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                commit.commit_id,
                commit.parent_commit_id,
                commit.branch_name,
                commit.chapter_index,
                commit.title,
                commit.full_prose,
                commit.word_count,
                commit.created_at,
                json.dumps(state_delta.model_dump(), ensure_ascii=False),
                json.dumps(qc_metrics or {}, ensure_ascii=False)
            ))

            # 2. 推进当前分支 HEAD 游标
            self.conn.execute("""
                UPDATE branches SET head_commit_id = ? WHERE branch_name = ?
            """, (commit.commit_id, self.current_branch))

        # 3. 将 state_delta 事实变动同步写入 BECGraph
        for entity_id, mut in state_delta.entity_mutations.items():
            self.graph.update_entity_progression(
                entity_id=entity_id,
                chapter_index=chapter_index,
                new_payload=mut
            )
        for rel in state_delta.relations_added:
            self.graph.add_relation(rel)

        return commit

    def checkout_chapter(self, target_chapter_index: int) -> bool:
        """
        一键时空回滚：
        将当前分支状态精准回滚到第 target_chapter_index 章末尾状态
        并同步联动物理回滚：
        1. commits 历史游标回退
        2. BECGraph 关系与属性回退
        3. EventStore 不可变事件日志截断
        4. ProgressionEngine 实体演进增量截断
        """
        # 寻找目标章节对应的 Commit
        row = self.conn.execute("""
            SELECT * FROM commits
            WHERE branch_name = ? AND chapter_index = ?
            ORDER BY created_at DESC LIMIT 1
        """, (self.current_branch, target_chapter_index)).fetchone()

        if not row:
            raise VCSRollbackError(
                f"在分支 [{self.current_branch}] 中未找到第 {target_chapter_index} 章的提交记录"
            )

        target_commit_id = row["commit_id"]

        with self.conn:
            # 更新分支 HEAD 指针
            self.conn.execute("""
                UPDATE branches SET head_commit_id = ? WHERE branch_name = ?
            """, (target_commit_id, self.current_branch))

            # 标记目标章节之后的孤立提交
            self.conn.execute("""
                DELETE FROM commits
                WHERE branch_name = ? AND chapter_index > ?
            """, (self.current_branch, target_chapter_index))

        # 1. 同步回滚 BECGraph (物理删除大于 target_chapter_index 的时序历史)
        with self.graph.conn:
            self.graph.conn.execute(
                "DELETE FROM entity_progression_history WHERE chapter_index > ?",
                (target_chapter_index,)
            )
            self.graph.conn.execute(
                "DELETE FROM entity_relations WHERE valid_from_chapter > ?",
                (target_chapter_index,)
            )
            self.graph.conn.execute(
                "UPDATE entity_relations SET valid_to_chapter = 999999 WHERE valid_to_chapter > ? AND valid_from_chapter <= ?",
                (target_chapter_index, target_chapter_index)
            )

        # 2. 联动回滚 EventStore
        if self.event_store:
            self.event_store.truncate_after_chapter(target_chapter_index)

        # 3. 联动回滚 ProgressionEngine
        if self.progression_engine:
            self.progression_engine.truncate_deltas_after_chapter(target_chapter_index)

        return True

    def create_branch(self, new_branch_name: str) -> None:
        """从当前 HEAD 分叉出全新剧情探索分支"""
        head = self.get_head_commit()
        head_id = head.commit_id if head else None
        with self.conn:
            self.conn.execute("""
                INSERT OR REPLACE INTO branches (branch_name, head_commit_id, created_at)
                VALUES (?, ?, ?)
            """, (new_branch_name, head_id, time.time()))
        self.current_branch = new_branch_name

    def switch_branch(self, branch_name: str) -> None:
        """切换工作分支"""
        b_row = self.conn.execute(
            "SELECT branch_name FROM branches WHERE branch_name = ?",
            (branch_name,)
        ).fetchone()
        if not b_row:
            raise VCSRollbackError(f"目标分支不存在: {branch_name}")
        self.current_branch = branch_name

    def list_branches(self) -> List[Dict[str, Any]]:
        """列出所有分支信息"""
        rows = self.conn.execute("SELECT branch_name, head_commit_id, created_at FROM branches").fetchall()
        return [dict(r) for r in rows]

    def create_tag(self, tag_name: str, commit_id: Optional[str] = None, message: str = "") -> None:
        """为特定提交打上里程碑标签 (如 v1.0_vol1_climax)"""
        target_id = commit_id
        if not target_id:
            head = self.get_head_commit()
            if not head:
                raise VCSRollbackError("当前分支没有任何提交，无法打标签")
            target_id = head.commit_id

        with self.conn:
            self.conn.execute("""
                INSERT OR REPLACE INTO tags (tag_name, commit_id, message, created_at)
                VALUES (?, ?, ?, ?)
            """, (tag_name, target_id, message, time.time()))

    def get_commit_log(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取当前分支提交日志链"""
        rows = self.conn.execute("""
            SELECT commit_id, parent_commit_id, chapter_index, title, word_count, created_at
            FROM commits
            WHERE branch_name = ?
            ORDER BY chapter_index ASC LIMIT ?
        """, (self.current_branch, limit)).fetchall()

        return [dict(r) for r in rows]

    def get_commit_history_chain(self, branch_name: str) -> List[Dict[str, Any]]:
        """沿着 parent_commit_id 追溯分支的完整祖先链 (Git-DAG 拓扑)"""
        b_row = self.conn.execute(
            "SELECT head_commit_id FROM branches WHERE branch_name = ?",
            (branch_name,)
        ).fetchone()
        if not b_row or not b_row["head_commit_id"]:
            return []

        chain = []
        cur_id = b_row["head_commit_id"]
        while cur_id:
            row = self.conn.execute("SELECT * FROM commits WHERE commit_id = ?", (cur_id,)).fetchone()
            if not row:
                break
            chain.append(dict(row))
            cur_id = row["parent_commit_id"]
        return chain

    def diff_branches(self, branch_a: str, branch_b: str) -> Dict[str, Any]:
        """对比两个分支的真实 DAG 提交差异"""
        chain_a = self.get_commit_history_chain(branch_a)
        chain_b = self.get_commit_history_chain(branch_b)

        a_map = {r["chapter_index"]: r["commit_id"] for r in chain_a}
        b_map = {r["chapter_index"]: r["commit_id"] for r in chain_b}

        common_chapters = sorted(set(a_map.keys()) & set(b_map.keys()))
        divergent_chapters = [ch for ch in common_chapters if a_map[ch] != b_map[ch]]
        unique_to_a = sorted(set(a_map.keys()) - set(b_map.keys()))
        unique_to_b = sorted(set(b_map.keys()) - set(a_map.keys()))

        return {
            "branch_a": branch_a,
            "branch_b": branch_b,
            "divergent_chapters": divergent_chapters,
            "unique_to_a": unique_to_a,
            "unique_to_b": unique_to_b
        }

    def close(self):
        self.conn.close()
        self.graph.close()
        if self.event_store:
            self.event_store.close()
