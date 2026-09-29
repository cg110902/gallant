"""
Outline Store - 全书大纲持久化与层级完整性校验

此前的缺口：DOCOutliner 只活在内存里。进程一退出，主线、分卷与章节规划
全部蒸发；`produce` 命令只能生成「第 N 章」这种没有剧情的占位章节。
一个没有大纲的生产流水线，产出的只能是文本噪声。

本模块提供：
1. 大纲的 YAML 持久化（人类可读可手改，这是作者真正会编辑的文件）；
2. 四级层级完整性校验：主线 → 分卷 → 章节 → 节拍
   （分卷区间是否连续无缝隙、章节是否落在所属分卷内、是否超出全书规模）；
3. 脚手架生成：一条命令产出可直接编辑的大纲模板。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml

from src.novel_factory.controller.doc_outliner import DOCOutliner
from src.novel_factory.schemas.beat_contract import (
    ArcStatus,
    ChapterOutline,
    MasterArcOutline,
    VolumeOutline,
)


# 脚手架占位文案：残留即说明该字段根本没被作者填写过
PLACEHOLDER_MARKERS = ("在此填写", "待命名", "待定", "TODO", "TBD")


def _is_placeholder(text: str) -> bool:
    t = (text or "").strip()
    return (not t) or any(m in t for m in PLACEHOLDER_MARKERS)


@dataclass
class CastMember:
    """开书前必须存在的世界实体（角色/道具/地点/势力）"""
    entity_id: str
    name: str
    entity_type: str = "CHARACTER"
    created_chapter: int = 1
    is_alive: bool = True
    payload: Dict[str, Any] = field(default_factory=dict)
    aliases: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id, "name": self.name,
            "entity_type": self.entity_type, "created_chapter": self.created_chapter,
            "is_alive": self.is_alive, "payload": self.payload, "aliases": self.aliases,
        }


@dataclass
class OutlineValidationIssue:
    severity: str          # ERROR / WARNING
    scope: str             # ARC / VOLUME / CHAPTER
    message: str
    ref: str = ""


@dataclass
class OutlineValidationReport:
    passed: bool = True
    issues: List[OutlineValidationIssue] = field(default_factory=list)
    total_volumes: int = 0
    total_chapters: int = 0
    planned_chapters: int = 0
    coverage_ratio: float = 0.0

    @property
    def errors(self) -> List[OutlineValidationIssue]:
        return [i for i in self.issues if i.severity == "ERROR"]

    def format_summary(self) -> str:
        head = (
            f"[大纲校验] {'PASS' if self.passed else 'FAIL'} | "
            f"分卷 {self.total_volumes} | 已规划章节 {self.total_chapters}/"
            f"{self.planned_chapters} (覆盖率 {self.coverage_ratio:.0%})"
        )
        lines = [head]
        for i in self.issues:
            lines.append(f"  - [{i.severity}] {i.scope} {i.ref}: {i.message}")
        return "\n".join(lines)


class OutlineStore:
    """全书大纲的加载、保存与校验"""

    def __init__(self, outliner: Optional[DOCOutliner] = None):
        self.outliner = outliner or DOCOutliner()
        # 开书演员表与全局设定词条：没有它们，大纲里写的角色在图谱中并不存在，
        # 每一章都会被"未注册实体"拦死，生产永远无法通过质检。
        self.cast: Dict[str, CastMember] = {}
        self.lore: List[Dict[str, Any]] = []

    def add_cast(self, member: CastMember) -> None:
        self.cast[member.entity_id] = member

    # ---------- 持久化 ----------

    def save(self, path: Union[str, Path]) -> Path:
        """以 YAML 落盘（作者会直接手改这个文件，所以不用 JSON）"""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = self.outliner.to_dict()
        data["cast"] = [c.to_dict() for c in self.cast.values()]
        data["lore"] = list(self.lore)
        p.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100),
            encoding="utf-8",
        )
        return p

    def load(self, path: Union[str, Path]) -> DOCOutliner:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"大纲文件不存在: {p}")
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        self.cast = {
            c["entity_id"]: CastMember(**c) for c in (data.pop("cast", None) or [])
        }
        self.lore = list(data.pop("lore", None) or [])
        # to_dict 的键是 int，经 YAML 往返后可能变成 str，这里统一回正
        for key in ("volumes", "chapters"):
            if isinstance(data.get(key), dict):
                data[key] = {int(k): v for k, v in data[key].items()}
        self.outliner = DOCOutliner.from_dict(data)
        return self.outliner

    # ---------- 校验 ----------

    def validate(self) -> OutlineValidationReport:
        """四级层级完整性校验"""
        o = self.outliner
        report = OutlineValidationReport(
            total_volumes=len(o.volumes),
            total_chapters=len(o.chapters),
        )

        if o.master_arc is None:
            report.issues.append(OutlineValidationIssue(
                "ERROR", "ARC", "缺少全书主线大纲 (MasterArcOutline)，无法确定全书规模与终点"
            ))
            report.passed = False
            return report

        planned = o.master_arc.target_total_chapters
        report.planned_chapters = planned
        report.coverage_ratio = len(o.chapters) / planned if planned else 0.0

        if _is_placeholder(o.master_arc.protagonist_ultimate_goal):
            report.issues.append(OutlineValidationIssue(
                "ERROR", "ARC",
                "主角终极目标为空或仍是脚手架占位文案——没有目标就没有主线",
                o.master_arc.arc_id
            ))
        if _is_placeholder(o.master_arc.core_theme):
            report.issues.append(OutlineValidationIssue(
                "WARNING", "ARC", "全书母题仍是占位文案", o.master_arc.arc_id
            ))

        # 分卷：区间必须合法、连续、不重叠
        vols = sorted(o.volumes.values(), key=lambda v: v.chapter_start)
        prev_end = 0
        for v in vols:
            ref = f"卷{v.volume_index}「{v.title}」"
            if v.chapter_end < v.chapter_start:
                report.issues.append(OutlineValidationIssue(
                    "ERROR", "VOLUME",
                    f"章节区间倒置: {v.chapter_start} ~ {v.chapter_end}", ref
                ))
            if prev_end and v.chapter_start <= prev_end:
                report.issues.append(OutlineValidationIssue(
                    "ERROR", "VOLUME",
                    f"与上一卷章节区间重叠（上一卷止于第 {prev_end} 章，本卷起于第 {v.chapter_start} 章）",
                    ref
                ))
            elif prev_end and v.chapter_start > prev_end + 1:
                report.issues.append(OutlineValidationIssue(
                    "WARNING", "VOLUME",
                    f"与上一卷之间存在第 {prev_end + 1} ~ {v.chapter_start - 1} 章的规划空洞",
                    ref
                ))
            if v.chapter_end > planned:
                report.issues.append(OutlineValidationIssue(
                    "WARNING", "VOLUME",
                    f"本卷结束于第 {v.chapter_end} 章，超出全书规划的 {planned} 章", ref
                ))
            if _is_placeholder(v.core_crisis):
                report.issues.append(OutlineValidationIssue(
                    "ERROR", "VOLUME",
                    "本卷核心危机未填写（仍是占位文案），卷内必然散架", ref
                ))
            if _is_placeholder(v.title):
                report.issues.append(OutlineValidationIssue(
                    "WARNING", "VOLUME", "卷标题仍未命名", ref
                ))
            prev_end = max(prev_end, v.chapter_end)

        # 章节：必须落在某一分卷内，且关键字段齐备
        for idx in sorted(o.chapters):
            ch = o.chapters[idx]
            ref = f"第{idx}章"
            if vols and not any(v.chapter_start <= idx <= v.chapter_end for v in vols):
                report.issues.append(OutlineValidationIssue(
                    "ERROR", "CHAPTER", "该章不属于任何已定义的分卷", ref
                ))
            if idx > planned:
                report.issues.append(OutlineValidationIssue(
                    "WARNING", "CHAPTER", f"章号超出全书规划的 {planned} 章", ref
                ))
            if _is_placeholder(ch.core_conflict):
                report.issues.append(OutlineValidationIssue(
                    "ERROR", "CHAPTER",
                    "核心冲突未填写（仍是占位文案）——没有冲突的章节等于注水", ref
                ))
            if _is_placeholder(ch.expected_cliffhanger):
                report.issues.append(OutlineValidationIssue(
                    "WARNING", "CHAPTER", "未规划章末钩子，追读率会受损", ref
                ))
            if not ch.key_characters:
                report.issues.append(OutlineValidationIssue(
                    "WARNING", "CHAPTER", "未指定关键角色", ref
                ))
            for cid in ch.key_characters:
                if self.cast and cid not in self.cast:
                    report.issues.append(OutlineValidationIssue(
                        "ERROR", "CHAPTER",
                        f"关键角色 [{cid}] 不在演员表 cast 中，开书时不会被注册进图谱，"
                        f"该章必然被『未注册实体』拦截", ref
                    ))

        if not self.cast:
            report.issues.append(OutlineValidationIssue(
                "ERROR", "ARC",
                "演员表 cast 为空：大纲里写的角色不会存在于世界图谱，生产必然全线驳回"
            ))

        report.passed = not report.errors
        return report

    # ---------- 脚手架 ----------

    def bootstrap_world(self, orchestrator: Any) -> int:
        """把演员表与全局设定灌入世界图谱，返回注册的实体数"""
        count = 0
        for m in self.cast.values():
            orchestrator.register_entity(
                entity_id=m.entity_id, entity_type=m.entity_type, name=m.name,
                created_chapter=m.created_chapter, initial_payload=m.payload,
                is_alive=m.is_alive,
            )
            count += 1
        return count

    def lore_entries(self) -> List[Any]:
        """把 YAML 中的设定词条转为 LoreEntry 对象"""
        from src.novel_factory.schemas.entity import LoreEntry
        out = []
        for raw in self.lore:
            try:
                out.append(LoreEntry(**raw))
            except Exception:
                continue
        return out

    @staticmethod
    def scaffold(
        title: str = "未命名作品",
        total_chapters: int = 300,
        volumes: int = 4,
        chapters_per_volume_sample: int = 2,
    ) -> "OutlineStore":
        """生成一份结构完整、可直接编辑的大纲模板（含演员表与设定词条）"""
        o = DOCOutliner()
        o.set_master_arc(MasterArcOutline(
            arc_id="arc_main",
            title=title,
            core_theme="在此填写全书母题，例如：被规则碾碎的人如何重新定义规则",
            protagonist_ultimate_goal="在此填写主角的终极目标（必填，否则主线不成立）",
            world_setting_summary="在此用三到五句话概括世界观基线",
            target_total_chapters=total_chapters,
            status=ArcStatus.PLANNED,
        ))

        span = max(1, total_chapters // max(1, volumes))
        for vi in range(1, volumes + 1):
            start = (vi - 1) * span + 1
            end = total_chapters if vi == volumes else vi * span
            o.add_volume(VolumeOutline(
                volume_index=vi,
                volume_id=f"vol_{vi:02d}",
                title=f"第{vi}卷 待命名",
                core_crisis="在此填写本卷的核心危机（必须是主角无法回避的）",
                climax_milestone_id=f"milestone_v{vi}",
                chapter_start=start,
                chapter_end=end,
                key_antagonists=[],
                key_rewards=[],
            ))
            for offset in range(chapters_per_volume_sample):
                ci = start + offset
                if ci > end:
                    break
                o.add_chapter(ChapterOutline(
                    chapter_index=ci,
                    title=f"第 {ci} 章 待命名",
                    core_conflict="在此填写本章核心冲突（必填）",
                    expected_cliffhanger="在此填写章末钩子",
                    location_id="loc_待定",
                    key_characters=["char_protagonist"],
                    planned_beats_count=4,
                ))

        store = OutlineStore(o)
        store.add_cast(CastMember(
            entity_id="char_protagonist", name="待命名主角",
            entity_type="CHARACTER", created_chapter=1,
            payload={"tier_or_rank": "待定", "power_rating": 100.0},
        ))
        store.add_cast(CastMember(
            entity_id="char_antagonist", name="待命名反派",
            entity_type="CHARACTER", created_chapter=1,
            payload={"tier_or_rank": "待定", "power_rating": 300.0},
        ))
        store.lore = [{
            "entry_id": "lore_world_baseline",
            "entity_type": "SYSTEM_RULE",
            "name": "世界基线法则",
            "content": "在此填写一条全局常驻的世界设定",
            "is_global": True,
            "valid_from_chapter": 1,
        }]
        return store

    # ---------- 生产计划 ----------

    def chapter_plan(self, chapter_index: int) -> Optional[Dict[str, Any]]:
        """
        把章节大纲翻译为生产参数。返回 None 表示该章尚未规划，
        调用方应当拒绝生产而不是拿占位内容硬产。
        """
        ch = self.outliner.get_chapter(chapter_index)
        if ch is None:
            return None
        volume = next(
            (v for v in self.outliner.volumes.values()
             if v.chapter_start <= chapter_index <= v.chapter_end),
            None,
        )
        return {
            "title": ch.title,
            "core_conflict": ch.core_conflict,
            "expected_cliffhanger": ch.expected_cliffhanger,
            "location_id": ch.location_id,
            "key_characters": list(ch.key_characters),
            "planned_beats_count": ch.planned_beats_count,
            "volume_title": volume.title if volume else "",
            "volume_crisis": volume.core_crisis if volume else "",
        }

    def unplanned_chapters(self, start: int, end: int) -> List[int]:
        """返回区间内尚未规划大纲的章号"""
        return [c for c in range(start, end + 1) if self.outliner.get_chapter(c) is None]
