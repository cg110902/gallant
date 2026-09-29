"""
Config Schemas - 全题材通用声明式配置数据模型
用于将题材规则、战力梯队、叙事节拍、机械质检与模型路由彻底与底层代码解耦。
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PowerTierConfig(BaseModel):
    """单级战力/境界梯队"""
    tier_id: str
    name: str
    numeric_min: float = 0.0
    numeric_max: float = 100.0
    description: str = ""


class PowerScaleConfig(BaseModel):
    """世界观战力/能力体系标尺"""
    scale_name: str
    tiers: List[PowerTierConfig] = Field(default_factory=list)
    max_cross_tier_gap: int = 1  # 跨阶逆伐的最大允许差值（超过此阶差在不变式检查中将触发不可抗逆告警）

    def get_tier_index(self, tier_id: str) -> Optional[int]:
        for idx, t in enumerate(self.tiers):
            if t.tier_id == tier_id:
                return idx
        return None


class GenreConfig(BaseModel):
    """
    通用题材领域法则配置 (Domain/Genre Agnostic Rulepack)
    完全由 YAML 驱动，涵盖战力梯队、专属社会关系拓扑、行业禁忌套路词等。
    """
    genre: str
    name: str
    power_scale: Optional[PowerScaleConfig] = None
    custom_relation_types: List[str] = Field(default_factory=list)
    genre_banned_cliches: List[str] = Field(default_factory=list)
    exclusive_item_categories: List[str] = Field(default_factory=list)
    world_rules: Dict[str, Any] = Field(default_factory=dict)


class PacingBeatConfig(BaseModel):
    """节拍模板细分定义"""
    beat_index: int
    pacing_type: str = "BUILD_UP"
    target_words_ratio: float = 0.25
    suggested_camera_angles: List[str] = Field(default_factory=list)


class PacingConfig(BaseModel):
    """
    叙事节奏与节拍曲线配置
    """
    pacing_name: str
    target_words_per_chapter: int = 3000
    beats_per_chapter: int = 4
    pacing_sequence: List[str] = Field(default_factory=lambda: ["HOOK", "BUILD_UP", "CLIMAX", "HOOK_CLIFFHANGER"])
    climax_frequency_chapters: int = 5
    beats_template: List[PacingBeatConfig] = Field(default_factory=list)


class QCRulePackConfig(BaseModel):
    """
    质检与反套路配置
    """
    rule_packs: List[str] = Field(default_factory=list)
    repetition_rules: Optional[str] = None
    auto_patch_on_failure: bool = True
    max_local_patch_retries: int = 3
    simhash_chapter_threshold: int = 18
    simhash_beat_threshold: int = 14


class ModelRouteConfig(BaseModel):
    """
    模型路由与成本审计配置
    """
    director_agent: str = "gemini-3.1-pro-preview"
    writer_agent: str = "gemini-3.8-flash"
    judge_agent: str = "gemini-3.5-flash-lite"
    enable_prompt_caching: bool = True
    cost_limit_per_chapter_cny: float = 0.40


class ProjectConfig(BaseModel):
    """
    工厂生产项目总控配置 (Project Master Specification)
    统一装配题材、节奏、质检与成本预算，驱动全自动工业生产线。
    """
    project_name: str
    project_title: str
    version: str = "1.0.0"
    genre_config_path: str = ""
    pacing_config_path: str = ""
    qc: QCRulePackConfig = Field(default_factory=QCRulePackConfig)
    models: ModelRouteConfig = Field(default_factory=ModelRouteConfig)

    # 深度解析装配后的全量对象
    genre: Optional[GenreConfig] = None
    pacing: Optional[PacingConfig] = None
