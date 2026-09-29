"""
Beat Contract & Hierarchical DOC Schema (ACL 2023 Detailed Outline Control)
四级雪花式规划契约体系：
Level 1: MasterArcOutline (全书宏观大纲)
Level 2: VolumeOutline (分卷危机与卷终高潮)
Level 3: ChapterOutline (单章主线冲突与悬念节奏)
Level 4: BeatContract (600~800字节拍微观执行契约，带机位、在场角色与离散微事件清单)
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.novel_factory.schemas.beat import (
    BeatContract,
    BeatOutput,
    CameraAngle,
    MicroEvent,
    PacingType,
)


class ArcStatus(str, Enum):
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    ABANDONED = "ABANDONED"


class MasterArcOutline(BaseModel):
    """Level 1: 全书宏观主线大纲"""
    arc_id: str
    title: str
    core_theme: str
    protagonist_ultimate_goal: str
    world_setting_summary: str
    target_total_chapters: int = 100
    status: ArcStatus = ArcStatus.PLANNED
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VolumeOutline(BaseModel):
    """Level 2: 分卷危机大纲"""
    volume_index: int
    volume_id: str
    title: str
    core_crisis: str
    climax_milestone_id: str
    chapter_start: int
    chapter_end: int
    key_antagonists: List[str] = Field(default_factory=list)
    key_rewards: List[str] = Field(default_factory=list)
    status: ArcStatus = ArcStatus.PLANNED


class ChapterOutline(BaseModel):
    """Level 3: 单章规划大纲"""
    chapter_index: int
    title: str
    core_conflict: str
    expected_cliffhanger: str
    location_id: str
    key_characters: List[str] = Field(default_factory=list)
    planned_beats_count: int = 4
    beats: List[BeatContract] = Field(default_factory=list)
    status: ArcStatus = ArcStatus.PLANNED


__all__ = [
    "PacingType",
    "CameraAngle",
    "MicroEvent",
    "BeatContract",
    "BeatOutput",
    "ArcStatus",
    "MasterArcOutline",
    "VolumeOutline",
    "ChapterOutline",
]
