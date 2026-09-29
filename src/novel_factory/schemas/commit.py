"""
Story Commit Schema - 剧情版本控制与状态增量数据契约 (Narrative VCS)
"""

import hashlib
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from .entity import EntityRelation


class StateDelta(BaseModel):
    """单章引起的世界状态事实变动增量 (Git-like Patch)"""
    chapter_index: int
    entity_mutations: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="实体属性突变快照（如 {'char_lin_feng': {'combat_scale': 1500}}）"
    )
    relations_added: List[EntityRelation] = Field(default_factory=list)
    relations_invalidated: List[str] = Field(
        default_factory=list,
        description="本章失效的关系边签名"
    )
    plot_threads_triggered: List[str] = Field(default_factory=list)
    plot_threads_resolved: List[str] = Field(default_factory=list)


class StoryCommit(BaseModel):
    """章节原子提交节点 (支持一键时序回滚与分叉)"""
    commit_id: str = Field(description="当前提交的 SHA-256 哈希签名")
    parent_commit_id: Optional[str] = Field(default=None, description="前序父节点哈希")
    branch_name: str = Field(default="main", description="所属剧情分支名称")
    chapter_index: int
    title: str
    full_prose: str
    word_count: int
    created_at: float = Field(default_factory=time.time)
    
    # 状态增量与质检归档
    state_delta: StateDelta
    qc_metrics: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def create(
        cls,
        chapter_index: int,
        title: str,
        full_prose: str,
        state_delta: StateDelta,
        parent_commit_id: Optional[str] = None,
        branch_name: str = "main",
        qc_metrics: Optional[Dict[str, Any]] = None
    ) -> "StoryCommit":
        """生成带唯一密码学签名的章节 Commit"""
        hasher = hashlib.sha256()
        hasher.update(str(parent_commit_id).encode("utf-8"))
        hasher.update(str(chapter_index).encode("utf-8"))
        hasher.update(title.encode("utf-8"))
        hasher.update(full_prose.encode("utf-8"))
        commit_id = hasher.hexdigest()[:16]

        return cls(
            commit_id=commit_id,
            parent_commit_id=parent_commit_id,
            branch_name=branch_name,
            chapter_index=chapter_index,
            title=title,
            full_prose=full_prose,
            word_count=len(full_prose),
            state_delta=state_delta,
            qc_metrics=qc_metrics or {}
        )
