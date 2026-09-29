"""
Narrative VCS Repository - 剧情版本控制与时空回滚仓库 (Git for Stories)
管理章节提交历史、分支分叉 (Branching)、剧情回滚 (Rollback) 与实体因果图谱同步恢复。
"""

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from src.novel_factory.graph.bec_graph import BECGraph
from src.novel_factory.schemas.commit import StateDelta, StoryCommit


class VCSRollbackError(Exception):
    """回滚或分支切换异常"""
    pass


class NarrativeRepository:
    """剧情版本控制仓库"""

    def __init__(self, db_path: Optional[str] = ":memory:", graph: Optional[BECGraph] = None):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.graph = graph or BECGraph(":memory:")
        self.current_branch: str = "main"
        self._init_tables()

    def _init_tables(self):
        """初始化提交记录表与分支游标表"""
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
        并同步重置 BECGraph 中的实体与关系
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

        # 同步回滚 BECGraph (物理删除大于 target_chapter_index 的时序历史)
        with self.graph.conn:
            self.graph.conn.execute(
                "DELETE FROM entity_progression_history WHERE chapter_index > ?",
                (target_chapter_index,)
            )
            self.graph.conn.execute(
                "DELETE FROM entity_relations WHERE valid_from_chapter > ?",
                (target_chapter_index,)
            )
            # 恢复失效区间的截止值
            self.graph.conn.execute(
                "UPDATE entity_relations SET valid_to_chapter = 999999 WHERE valid_to_chapter > ? AND valid_from_chapter <= ?",
                (target_chapter_index, target_chapter_index)
            )

        return True

    def create_branch(self, new_branch_name: str) -> None:
        """从当前 HEAD 分叉出全新剧情探索分支"""
        head = self.get_head_commit()
        head_id = head.commit_id if head else None
        with self.conn:
            self.conn.execute("""
                INSERT OR REPLACE INTO branches (branch_name, head_commit_id, created_at)
                VALUES (?, ?, strftime('%s', 'now'))
            """, (new_branch_name, head_id))
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

    def get_commit_log(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取当前分支提交日志链"""
        rows = self.conn.execute("""
            SELECT commit_id, parent_commit_id, chapter_index, title, word_count, created_at
            FROM commits
            WHERE branch_name = ?
            ORDER BY chapter_index ASC LIMIT ?
        """, (self.current_branch, limit)).fetchall()

        return [dict(r) for r in rows]

    def close(self):
        self.conn.close()
        self.graph.close()
