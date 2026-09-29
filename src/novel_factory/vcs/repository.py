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

from src.novel_factory.core.db import connect as db_connect
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
        self.conn = db_connect(db_path)
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
                    qc_metrics_json TEXT DEFAULT '{}',
                    is_orphaned INTEGER NOT NULL DEFAULT 0
                )
            """)
            # 对既有数据库做无损迁移（早期版本没有 is_orphaned 列）
            cols = {r[1] for r in self.conn.execute("PRAGMA table_info(commits)").fetchall()}
            if "is_orphaned" not in cols:
                self.conn.execute(
                    "ALTER TABLE commits ADD COLUMN is_orphaned INTEGER NOT NULL DEFAULT 0"
                )
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_commits_branch_chapter
                ON commits (branch_name, chapter_index, is_orphaned)
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
            "SELECT * FROM commits WHERE commit_id = ? AND is_orphaned = 0",
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
        # 同一章被重新生产时（质检驳回后重跑、人工接管后重写），必须【取代】
        # 旧版本而不是再追加一条。否则导出的稿件里会出现同一章的多个版本。
        superseded = self.conn.execute("""
            SELECT commit_id, parent_commit_id FROM commits
            WHERE branch_name = ? AND chapter_index = ? AND is_orphaned = 0
            ORDER BY created_at DESC LIMIT 1
        """, (self.current_branch, chapter_index)).fetchone()

        if superseded:
            # 新版本继承被取代版本的父节点，保持祖先链连续
            parent_id = superseded["parent_commit_id"]
        else:
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

        # commit_id 由内容哈希导出：内容与父节点完全一致时就是同一个提交，
        # 重新生产出一模一样的章节应当是幂等无操作，而不是撞唯一约束崩溃。
        existing = self.conn.execute(
            "SELECT commit_id FROM commits WHERE commit_id = ?", (commit.commit_id,)
        ).fetchone()
        if existing:
            with self.conn:
                self.conn.execute(
                    "UPDATE commits SET is_orphaned = 0 WHERE commit_id = ?",
                    (commit.commit_id,)
                )
                self.conn.execute(
                    "UPDATE branches SET head_commit_id = ? WHERE branch_name = ? "
                    "AND (head_commit_id IS NULL OR head_commit_id = ?)",
                    (commit.commit_id, self.current_branch,
                     superseded["commit_id"] if superseded else commit.commit_id)
                )
            return commit

        with self.conn:
            # 0. 旧版本降级为可恢复的历史版本
            if superseded:
                self.conn.execute(
                    "UPDATE commits SET is_orphaned = 1 WHERE commit_id = ?",
                    (superseded["commit_id"],)
                )
                # 后继章节的父指针改挂到新版本，避免祖先链断裂
                self.conn.execute(
                    "UPDATE commits SET parent_commit_id = ? "
                    "WHERE parent_commit_id = ? AND commit_id != ?",
                    (commit.commit_id, superseded["commit_id"], commit.commit_id)
                )

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

            # 2. 推进 HEAD：仅当新章节确实位于分支末端，或它取代的正是当前 HEAD。
            #    重产历史中间某一章时，HEAD 不应被拉回到那一章。
            cur_head = self.conn.execute(
                "SELECT head_commit_id FROM branches WHERE branch_name = ?",
                (self.current_branch,)
            ).fetchone()
            head_id = cur_head["head_commit_id"] if cur_head else None
            head_chapter = -1
            if head_id:
                hrow = self.conn.execute(
                    "SELECT chapter_index FROM commits WHERE commit_id = ?", (head_id,)
                ).fetchone()
                head_chapter = hrow["chapter_index"] if hrow else -1

            replaces_head = bool(superseded) and head_id == superseded["commit_id"]
            if replaces_head or chapter_index >= head_chapter:
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

    def checkout_chapter(
        self,
        target_chapter_index: int,
        hard: bool = False
    ) -> bool:
        """
        一键时空回滚：将当前分支回滚到第 target_chapter_index 章末尾状态。

        默认为【非破坏性】回滚（等价于 git reset + reflog 保留）：
        被回退掉的章节标记为 orphaned 而非物理删除，可通过
        `list_orphaned_commits()` 查看、`restore_orphaned_commit()` 恢复。

        早期实现直接 DELETE 后续提交，一次误操作即永久丢稿；
        长篇创作中回滚是高频操作，不可逆的回滚是不可接受的。

        hard=True 时才真正物理删除（不可恢复）。
        """
        row = self.conn.execute("""
            SELECT * FROM commits
            WHERE branch_name = ? AND chapter_index = ? AND is_orphaned = 0
            ORDER BY created_at DESC LIMIT 1
        """, (self.current_branch, target_chapter_index)).fetchone()

        if not row:
            raise VCSRollbackError(
                f"在分支 [{self.current_branch}] 中未找到第 {target_chapter_index} 章的提交记录"
            )

        target_commit_id = row["commit_id"]

        with self.conn:
            self.conn.execute("""
                UPDATE branches SET head_commit_id = ? WHERE branch_name = ?
            """, (target_commit_id, self.current_branch))

            if hard:
                self.conn.execute("""
                    DELETE FROM commits
                    WHERE branch_name = ? AND chapter_index > ?
                """, (self.current_branch, target_chapter_index))
            else:
                self.conn.execute("""
                    UPDATE commits SET is_orphaned = 1
                    WHERE branch_name = ? AND chapter_index > ? AND is_orphaned = 0
                """, (self.current_branch, target_chapter_index))

        self._materialize_world_to(target_chapter_index)
        return True

    def list_orphaned_commits(self, branch_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出被回滚掉但仍可恢复的提交（reflog 视图）"""
        branch = branch_name or self.current_branch
        rows = self.conn.execute("""
            SELECT commit_id, chapter_index, title, word_count, created_at
            FROM commits WHERE branch_name = ? AND is_orphaned = 1
            ORDER BY chapter_index ASC
        """, (branch,)).fetchall()
        return [dict(r) for r in rows]

    def restore_orphaned_commit(self, commit_id: str) -> bool:
        """
        撤销回滚：把提交重新挂回分支，并连带恢复它与当前 HEAD 之间的整段链条。

        只恢复单个提交是不够的——它的父节点若仍是孤立状态，
        祖先链就断在那里。实测中回滚 10 章后恢复最后一章，
        可见章节从 20 章直接塌缩到 1 章。
        """
        row = self.conn.execute(
            "SELECT * FROM commits WHERE commit_id = ? AND is_orphaned = 1", (commit_id,)
        ).fetchone()
        if not row:
            return False

        branch = row["branch_name"]
        target_chapter = row["chapter_index"]
        with self.conn:
            # 恢复该章及其之前所有被同一次回滚标记为孤立的提交，保证链条连续
            self.conn.execute(
                "UPDATE commits SET is_orphaned = 0 "
                "WHERE branch_name = ? AND is_orphaned = 1 AND chapter_index <= ?",
                (branch, target_chapter)
            )
            self.conn.execute(
                "UPDATE branches SET head_commit_id = ? WHERE branch_name = ?",
                (commit_id, branch)
            )
        self.rebuild_world_from_history(branch)
        return True

    def restore_all_orphaned(self, branch_name: Optional[str] = None) -> int:
        """完全撤销回滚：恢复该分支上全部孤立提交，返回恢复条数"""
        branch = branch_name or self.current_branch
        orphans = self.list_orphaned_commits(branch)
        if not orphans:
            return 0
        last = max(orphans, key=lambda o: o["chapter_index"])
        self.restore_orphaned_commit(last["commit_id"])
        return len(orphans)

    def _materialize_world_to(self, chapter_index: int) -> None:
        """把图谱/事件库/演进引擎同步到指定章节末尾状态"""
        with self.graph.conn:
            self.graph.conn.execute(
                "DELETE FROM entity_progression_history WHERE chapter_index > ?",
                (chapter_index,)
            )
            self.graph.conn.execute(
                "DELETE FROM entity_relations WHERE valid_from_chapter > ?",
                (chapter_index,)
            )
            self.graph.conn.execute(
                "UPDATE entity_relations SET valid_to_chapter = 999999 "
                "WHERE valid_to_chapter > ? AND valid_from_chapter <= ?",
                (chapter_index, chapter_index)
            )
        if self.event_store:
            self.event_store.truncate_after_chapter(chapter_index)
        if self.progression_engine:
            self.progression_engine.truncate_deltas_after_chapter(chapter_index)

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

    def switch_branch(self, branch_name: str, rebuild_world: bool = True) -> None:
        """
        切换工作分支，并按目标分支的提交链重建世界状态。

        早期实现只改了一个字符串变量，图谱与事件库仍停留在上一个分支的状态，
        于是切回 main 之后还能看到 alt 分支的战力数值——跨分支状态污染。
        """
        b_row = self.conn.execute(
            "SELECT branch_name FROM branches WHERE branch_name = ?",
            (branch_name,)
        ).fetchone()
        if not b_row:
            raise VCSRollbackError(f"目标分支不存在: {branch_name}")
        self.current_branch = branch_name
        if rebuild_world:
            self.rebuild_world_from_history(branch_name)

    def rebuild_world_from_history(self, branch_name: Optional[str] = None) -> int:
        """
        以提交链为唯一事实来源，重放 state_delta 重建 BEC 图谱状态。

        提交记录是不可变的事实来源，因此任何时候都可以据此确定性地
        重算世界状态——这比"就地增量修补"要可靠得多。
        返回重放的提交数。
        """
        chain = self.get_commit_history_chain(branch_name or self.current_branch)
        chain.sort(key=lambda r: r["chapter_index"])
        head_chapter = chain[-1]["chapter_index"] if chain else 0

        # 先清空该章之后的残留，再从头重放
        self._materialize_world_to(head_chapter)
        with self.graph.conn:
            self.graph.conn.execute("DELETE FROM entity_progression_history")
            self.graph.conn.execute("DELETE FROM entity_relations")

        for row in chain:
            delta = StateDelta(**json.loads(row["state_delta_json"]))
            for entity_id, mut in delta.entity_mutations.items():
                self.graph.update_entity_progression(
                    entity_id=entity_id,
                    chapter_index=row["chapter_index"],
                    new_payload=mut
                )
            for rel in delta.relations_added:
                self.graph.add_relation(rel)
        return len(chain)

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

    def get_commit_log(self, limit: int = 20, branch_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取分支的提交日志。

        必须沿 parent_commit_id 祖先链回溯，而不是简单地按 branch_name 过滤：
        从 main 分叉出的 alt 分支同样"拥有"分叉点之前的全部章节，
        按 branch_name 过滤会让新分支看起来像是从第 N 章凭空开始。
        """
        chain = self.get_commit_history_chain(branch_name or self.current_branch)
        chain.sort(key=lambda r: r["chapter_index"])
        keys = ("commit_id", "parent_commit_id", "chapter_index", "title",
                "word_count", "created_at")
        return [{k: r[k] for k in keys} for r in chain[:limit]]

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
            row = self.conn.execute(
                "SELECT * FROM commits WHERE commit_id = ? AND is_orphaned = 0", (cur_id,)
            ).fetchone()
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
