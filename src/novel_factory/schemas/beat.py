"""
Beat Contract Schema - ACL 2023 DOC 细粒度节拍契约与分镜机位规范
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class PacingType(str, Enum):
    BUILD_UP = "BUILD_UP"                # 铺垫/压制（制造憋屈或危机，张力提升）
    COGNITIVE_GAP = "COGNITIVE_GAP"      # 认知差放大（信息不对称，反派自大误判）
    CATHARSIS_PAYOFF = "CATHARSIS_PAYOFF"# 爽点爆发/打脸（极致反转与社会性释放）
    CLIFFHANGER_HOOK = "CLIFFHANGER_HOOK"# 悬念钩子（高潮切断，驱动阅读下一章）


class CameraAngle(str, Enum):
    POV = "POV"                  # 主视角内省与视线
    CLOSE_UP = "CLOSE_UP"        # 微动作/剑刃/伤口/微表情特写
    PANORAMIC = "PANORAMIC"      # 环境氛围/压抑天色/战场全景
    REACTION_CAM = "REACTION_CAM"# 围观视角震惊反馈（网文爽感核心灵魂）


class MicroEvent(BaseModel):
    """微事件单元 - 彻底杜绝空洞注水与模型流口水"""
    event_id: str
    description: str = Field(description="具体物理事件描述，严禁抽象概括")
    must_accomplish: bool = True
    completed: bool = False


class BeatContract(BaseModel):
    """单分镜节拍执行契约 (DOC Controller 强制核验基准)"""
    beat_id: str = Field(description="全局节拍ID，如 ch01_beat02")
    chapter_index: int
    beat_index: int = Field(description="当前章内部节拍序号 (1~4)")
    target_words: int = Field(default=700, ge=100, le=4000, description="目标字数区间")
    word_tolerance_ratio: float = Field(
        default=0.25, ge=0.0, le=1.0,
        description="字数契约允许的上下浮动比例，超出即判定交付违约"
    )
    pacing_type: PacingType
    
    # 视听与镜头机位约束
    required_camera_angles: List[CameraAngle] = Field(
        default_factory=lambda: [CameraAngle.POV, CameraAngle.CLOSE_UP, CameraAngle.REACTION_CAM],
        description="必须覆盖的镜头机位"
    )
    
    # 物理在场实体
    characters_present: List[str] = Field(
        description="在场角色ID列表，不在场角色严禁有动作或台词"
    )
    location_id: str = Field(description="发生地节点ID")
    scene_atmosphere: str = Field(default="", description="光线、天气、气味、声音")
    
    # 细粒度因果断言契约 (Invariants)
    pre_conditions: List[str] = Field(
        default_factory=list,
        description="前置剧情状态依赖（例如：赵无极出掌未收回）"
    )
    post_conditions: List[str] = Field(
        default_factory=list,
        description="执行后必须达成的状态变化（例如：寒霜剑出鞘、赵无极右臂经脉被废）"
    )
    micro_events: List[MicroEvent] = Field(
        default_factory=list,
        description="必须推进的离散微事件清单，事件全部完成即截断生成"
    )
    strict_prohibitions: List[str] = Field(
        default_factory=list,
        description="本节拍绝对禁止发生的情节或对话（例如：禁止主角解释自己的招式）"
    )
    
    zero_moralizer_enforced: bool = Field(
        default=True,
        description="是否强制开启零议论反说教检查"
    )


class BeatOutput(BaseModel):
    """节拍渲染产出与质检结果"""
    beat_id: str
    prose: str = Field(description="实际生成的正文文本")
    actual_words: int
    qc_passed: bool = False
    patch_iteration: int = 0
    feedback_notes: List[str] = Field(default_factory=list)
