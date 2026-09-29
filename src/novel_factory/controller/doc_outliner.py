"""
DOC Outliner & Controller - ACL 2023 Detailed Outline Control 细粒度规划控制器
将生成与规划完全解耦，提供主线 -> 分卷 -> 章节 -> 节拍的四级雪花式下发与执行期契约断言。
"""

from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from src.novel_factory.core.event_store import WorldSnapshot
from src.novel_factory.graph.causal_dag import CausalDAG, NodeStatus
from src.novel_factory.schemas.beat_contract import (
    ArcStatus,
    BeatContract,
    CameraAngle,
    ChapterOutline,
    MasterArcOutline,
    MicroEvent,
    PacingType,
    VolumeOutline,
)


class ContractValidationError(Exception):
    """节拍契约不合法异常"""
    pass


class DOCOutliner:
    """DOC 细粒度大纲规划与契约控制器"""

    def __init__(
        self,
        min_beat_words: int = 100,
        max_beat_words: int = 4000
    ):
        # 字数合规区间必须与 BeatContract schema 及 pacing 配置保持一致，
        # 早期硬编码的 [400, 1200] 会把合法的长节拍误判为违规。
        self.min_beat_words = min_beat_words
        self.max_beat_words = max_beat_words
        self.master_arc: Optional[MasterArcOutline] = None
        self.volumes: Dict[int, VolumeOutline] = {}
        self.chapters: Dict[int, ChapterOutline] = {}

    def set_master_arc(self, arc: MasterArcOutline) -> None:
        """设置全书宏观主线规划"""
        self.master_arc = arc

    def add_volume(self, volume: VolumeOutline) -> None:
        """注册分卷大纲"""
        self.volumes[volume.volume_index] = volume

    def add_chapter(self, chapter: ChapterOutline) -> None:
        """注册或更新单章大纲"""
        self.chapters[chapter.chapter_index] = chapter

    def get_chapter(self, chapter_index: int) -> Optional[ChapterOutline]:
        """获取指定章节大纲"""
        return self.chapters.get(chapter_index)

    def auto_decompose_chapter_beats(
        self,
        chapter_index: int,
        default_location: str = "DEFAULT_SCENE",
        characters: Optional[List[str]] = None
    ) -> List[BeatContract]:
        """
        标准四联节拍雪花分解器 (Snowflake 4-Beat Decomposition)：
        若章节尚未手动切分分镜，自动生成符合网文爽感心流的 4 级节拍：
        1. BUILD_UP (铺垫/压制)
        2. COGNITIVE_GAP (认知差拉大)
        3. CATHARSIS_PAYOFF (爽点爆发/打脸)
        4. CLIFFHANGER_HOOK (悬念钩子)
        """
        chapter = self.chapters.get(chapter_index)
        chars = characters or (chapter.key_characters if chapter else ["PROTAGONIST"])
        loc = chapter.location_id if chapter else default_location

        beats = [
            BeatContract(
                beat_id=f"ch{chapter_index:03d}_b1",
                chapter_index=chapter_index,
                beat_index=1,
                target_words=700,
                pacing_type=PacingType.BUILD_UP,
                required_camera_angles=[CameraAngle.POV, CameraAngle.PANORAMIC],
                characters_present=chars,
                location_id=loc,
                scene_atmosphere="山雨欲来，压抑阴沉",
                micro_events=[
                    MicroEvent(event_id="e1", description="展示当前困境与外部强敌迫近的声势")
                ]
            ),
            BeatContract(
                beat_id=f"ch{chapter_index:03d}_b2",
                chapter_index=chapter_index,
                beat_index=2,
                target_words=700,
                pacing_type=PacingType.COGNITIVE_GAP,
                required_camera_angles=[CameraAngle.CLOSE_UP, CameraAngle.POV],
                characters_present=chars,
                location_id=loc,
                scene_atmosphere="剑拔弩张，冷嘲热讽",
                micro_events=[
                    MicroEvent(event_id="e2", description="反派误判主角底牌，言语狂妄自大"),
                    MicroEvent(event_id="e3", description="主角暗中调动底牌，蓄势待发")
                ]
            ),
            BeatContract(
                beat_id=f"ch{chapter_index:03d}_b3",
                chapter_index=chapter_index,
                beat_index=3,
                target_words=800,
                pacing_type=PacingType.CATHARSIS_PAYOFF,
                required_camera_angles=[CameraAngle.CLOSE_UP, CameraAngle.REACTION_CAM],
                characters_present=chars,
                location_id=loc,
                scene_atmosphere="气浪轰鸣，雷霆万钧",
                micro_events=[
                    MicroEvent(event_id="e4", description="雷霆出手一招破局，逆转碾压"),
                    MicroEvent(event_id="e5", description="围观者瞠目结舌，全场陷入死寂")
                ]
            ),
            BeatContract(
                beat_id=f"ch{chapter_index:03d}_b4",
                chapter_index=chapter_index,
                beat_index=4,
                target_words=600,
                pacing_type=PacingType.CLIFFHANGER_HOOK,
                required_camera_angles=[CameraAngle.POV, CameraAngle.PANORAMIC],
                characters_present=chars,
                location_id=loc,
                scene_atmosphere="暗流涌动，悬念未决",
                micro_events=[
                    MicroEvent(event_id="e6", description="战后清点或发现更深层的诡异暗号/神秘来客")
                ]
            )
        ]

        if chapter:
            chapter.beats = beats
        return beats

    def validate_beat_contract(
        self,
        beat: BeatContract,
        world_snapshot: Optional[WorldSnapshot] = None,
        dag: Optional[CausalDAG] = None
    ) -> List[str]:
        """
        节拍契约严格前置断言：
        1. 检查字数区间是否在合法工业范围 [400, 1200]；
        2. 检查必须声明至少 1 个在场角色；
        3. 检查在场角色在当前时空快照中是否真实存活；
        4. 检查是否覆盖了必需的镜头机位；
        5. 检查微事件清单是否有效；
        6. 检查 DAG 前置依赖是否达成。
        """
        errors = []

        # 1. 字数区间
        if not (self.min_beat_words <= beat.target_words <= self.max_beat_words):
            errors.append(
                f"节拍 [{beat.beat_id}] 目标字数 {beat.target_words} 超出合规区间 "
                f"[{self.min_beat_words}, {self.max_beat_words}]"
            )

        # 2. 在场角色合法性
        if not beat.characters_present:
            errors.append(f"节拍 [{beat.beat_id}] 严禁在场角色为空")

        # 3. 快照存活状态断言
        if world_snapshot:
            for char_id in beat.characters_present:
                ent = world_snapshot.entities.get(char_id)
                if ent and not ent.get("is_alive", True):
                    errors.append(f"因果悖论：角色 [{char_id}] 在当前时空已死亡，严禁作为在场角色参与节拍 [{beat.beat_id}]")

        # 4. 镜头机位约束
        if not beat.required_camera_angles:
            errors.append(f"节拍 [{beat.beat_id}] 必须指定至少一种视听镜头机位")

        # 5. 微事件约束
        if not beat.micro_events:
            errors.append(f"节拍 [{beat.beat_id}] 必须包含至少 1 个离散微事件清单，严禁空洞生成")

        # 6. DAG 前置约束
        if dag:
            for prereq in beat.pre_conditions:
                node = dag.get_node(prereq)
                if node and node.status != NodeStatus.FULFILLED:
                    errors.append(f"DAG 前置未达成：节拍依赖的前置事件 [{prereq}] 尚未 FULFILLED")

        return errors

    def verify_beat_postconditions(
        self,
        beat: BeatContract,
        prose_text: str
    ) -> Tuple[bool, List[str]]:
        """
        后置断言核验器 (Post-condition Verifier)：
        检查渲染产出的正文中是否包含了必须达成的关键要素或关键词
        """
        unfulfilled = []
        for post in beat.post_conditions:
            # 简单包含性检查或规则判定
            if post not in prose_text:
                unfulfilled.append(f"后置状态要素未在文本中体现: [{post}]")

        passed = len(unfulfilled) == 0
        return passed, unfulfilled

    def to_dict(self) -> Dict[str, Any]:
        """全案大纲序列化导出"""
        # mode="json" 才能把枚举与嵌套模型降为原生标量，
        # 否则 YAML 序列化会直接抛 RepresenterError。
        return {
            "master_arc": self.master_arc.model_dump(mode="json") if self.master_arc else None,
            "volumes": {k: v.model_dump(mode="json") for k, v in self.volumes.items()},
            "chapters": {k: v.model_dump(mode="json") for k, v in self.chapters.items()}
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DOCOutliner":
        """反序列化构建规划控制器"""
        outliner = cls()
        if data.get("master_arc"):
            outliner.set_master_arc(MasterArcOutline(**data["master_arc"]))
        for k, v in data.get("volumes", {}).items():
            outliner.add_volume(VolumeOutline(**v))
        for k, v in data.get("chapters", {}).items():
            outliner.add_chapter(ChapterOutline(**v))
        return outliner
