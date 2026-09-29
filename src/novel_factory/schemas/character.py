"""
Character Schema - 通用全题材角色实体与语言指纹数据契约 (Domain-Agnostic)
严禁硬编码任何单一题材（如玄幻修真）的专有词汇，完全通过元数据与配置驱动
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CharacterRole(str, Enum):
    PROTAGONIST = "PROTAGONIST"      # 主角
    CORE_SUPPORT = "CORE_SUPPORT"    # 核心配角/搭档
    ANTAGONIST = "ANTAGONIST"        # 反派/对手
    RECURRING = "RECURRING"          # 常驻NPC/组织成员
    MOB = "MOB"                      # 龙套/垫脚石/背景板


class SentenceRhythm(str, Enum):
    PUNCHY_SHORT = "PUNCHY_SHORT"    # 短促断句流（压迫感强、冷酷利落）
    BALANCED = "BALANCED"            # 均衡流（沉稳老练、中立叙述）
    RAPID_AGGRESSIVE = "RAPID_AGGRESSIVE" # 连珠攻击流（狂妄急躁、挑衅攻击）
    SCHOLARLY = "SCHOLARLY"          # 文绉温吞流（智囊、学术型、幕后指使）
    CASUAL_COLLOQUIAL = "CASUAL_COLLOQUIAL" # 口语市井流（接地气、轻浮或幽默）


class VoiceFingerprint(BaseModel):
    """通用角色语言指纹 - 杜绝千人一面与无机质客服式对话"""
    rhythm: SentenceRhythm = SentenceRhythm.PUNCHY_SHORT
    max_sentence_length: int = Field(default=15, description="单句最大字数限制")
    sample_dialogues: List[str] = Field(
        default_factory=list,
        description="角色典型台词样本，作为 Few-shot 语言指纹锚点"
    )
    catchphrases: List[str] = Field(default_factory=list, description="口癖或高频词")
    forbidden_words: List[str] = Field(
        default_factory=list,
        description="角色绝对禁止使用的词汇（如冷酷型角色严禁使用‘请教’、‘哀求’）"
    )
    tone_descriptors: List[str] = Field(
        default_factory=lambda: ["冷淡", "平缓", "少感叹句"],
        description="语气修饰标签"
    )


class Ability(BaseModel):
    """通用技能/能力/专长（修仙功法、赛博黑客程序、刑侦侧写、现代商业技能通用）"""
    ability_id: str
    name: str
    tier_label: str = Field(description="品阶或熟练度等级（如：大师级、S级、初级）")
    numeric_mastery: float = Field(default=1.0, description="量化掌握度 0.0~1.0")
    description: str = ""
    properties: Dict[str, Any] = Field(default_factory=dict)


class GenericItem(BaseModel):
    """通用装备/道具/物证/资产"""
    item_id: str
    name: str
    quantity: int = 1
    durability: Optional[float] = 1.0  # 0.0 - 1.0
    bound_status: str = "BOUND"        # BOUND | UNBOUND | CONTRABAND | EVIDENCE
    custom_metadata: Dict[str, Any] = Field(default_factory=dict)


class CharacterProgression(BaseModel):
    """通用时序演进快照 - 记录任意题材下角色的动态状态变迁"""
    chapter_index: int = Field(description="生效章节序号")
    tier_or_rank: str = Field(description="通用等级标识（如：'筑基中期' / '军规义体级' / '二级警督' / '副总裁'）")
    power_rating: float = Field(
        description="统一量化战力/能力标尺（数值型），用于代码级硬断言，严禁不可逆倒退或逻辑崩塌"
    )
    physical_status: str = Field(default="HEALTHY", description="HEALTHY | INJURED | CRITICAL | COMA")
    status_tags: List[str] = Field(
        default_factory=list,
        description="状态修饰词（如：['神经义体过载20%'] 或 ['经脉闭塞'] 或 ['声誉受损']）"
    )
    current_location: str = Field(default="UNKNOWN", description="当前所在地理或空间节点ID")
    inventory: List[GenericItem] = Field(default_factory=list)
    abilities: List[Ability] = Field(default_factory=list)
    social_influence: float = Field(default=0.0, description="社会声望/财富值/震惊点数")
    extended_attributes: Dict[str, Any] = Field(
        default_factory=dict,
        description="用户题材专属扩展字段（如 SAN值、信用点、气运值等）"
    )


class Character(BaseModel):
    """通用全题材角色实体模型"""
    id: str = Field(description="全局唯一实体标识，如 char_protagonist_01")
    name: str = Field(description="角色标准姓名/代号")
    aliases: List[str] = Field(default_factory=list, description="别名、绰号、头衔，用于Codex正则匹配")
    role: CharacterRole = CharacterRole.RECURRING
    gender: str = "UNSPECIFIED"
    age_apparent: int = 20
    is_alive: bool = True
    cause_of_death: Optional[str] = None
    
    # 核心人设不可变基石 (DNA Invariants)
    core_motivation: str = Field(description="根本行动驱动力（生存、复仇、守护、求知、财富等）")
    moral_bottom_line: str = Field(description="绝不逾越的行为底线")
    personality_tags: List[str] = Field(default_factory=list)
    appearance_anchors: List[str] = Field(
        default_factory=list,
        description="外貌记忆锚点，防止生成过程中外形特征漂移"
    )
    
    # 语言风格
    voice: VoiceFingerprint = Field(default_factory=VoiceFingerprint)
    
    # 时序历史记录与当前快照
    current_state: CharacterProgression
    history_states: List[CharacterProgression] = Field(
        default_factory=list,
        description="历史时序快照归档，用于 Narrative VCS 回滚"
    )

    def advance_chapter(self, new_state: CharacterProgression) -> None:
        """推进角色时序状态并留存快照"""
        self.history_states.append(self.current_state)
        self.current_state = new_state
