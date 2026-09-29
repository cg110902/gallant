"""
Entity & Relation Schema - 全题材通用双时态实体关系与 Codex 词条契约 (Domain-Agnostic)
支持用户通过 YAML 配置任意扩展题材专属关系类型（如 HACKED_BY, BLACKMAILED_BY 等）
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class StandardEntityTypes:
    """常见实体类型建议常量（可自由扩展）"""
    CHARACTER = "CHARACTER"        # 角色/人物/AI/神明
    ORGANIZATION = "ORGANIZATION"  # 宗门/巨型财阀/警局/黑帮/国家
    LOCATION = "LOCATION"          # 地理节点/星舰/安全屋/虚拟空间
    ARTIFACT = "ARTIFACT"          # 法宝/神经芯片/枪械/关键物证/商业机密
    SYSTEM_RULE = "SYSTEM_RULE"    # 世界法则/科技树/灵气定律/金融机制
    PLOT_THREAD = "PLOT_THREAD"    # 伏笔与剧情线索


class StandardRelations:
    """通用关系语义常量（支持任意自定义字符串）"""
    ENEMY_OF = "ENEMY_OF"              # 敌对/竞争
    ALLY_OF = "ALLY_OF"                # 盟友/合作
    KIN_OF = "KIN_OF"                  # 血亲/家属
    SUPERIOR_TO = "SUPERIOR_TO"        # 上下级管理
    SUBORDINATE_TO = "SUBORDINATE_TO"  # 臣服/下属
    POSSESSES = "POSSESSES"            # 持有/拥有
    LOCATED_IN = "LOCATED_IN"          # 驻留/坐落
    MEMBER_OF = "MEMBER_OF"            # 归属于（组织/势力）
    KILLED_BY = "KILLED_BY"            # 击杀因果
    BOUND_TO = "BOUND_TO"              # 契约/协议/誓言绑定


class EntityRelation(BaseModel):
    """通用双时态实体关系边（带生命周期与证据链）"""
    source_id: str = Field(description="源实体ID")
    relation_type: str = Field(
        description="关系类型（支持StandardRelations或用户在YAML中定义的任意关系，如 HACKED_BY）"
    )
    target_id: str = Field(description="目标实体ID")
    valid_from_chapter: int = Field(default=1, description="关系生效起始章节")
    valid_to_chapter: int = Field(default=999999, description="关系失效章节")
    provenance_chapter: int = Field(description="产生该关系的锚点章节")
    intensity: float = Field(default=1.0, description="关系强度/好感度 (-1.0 至 1.0)")
    evidence: str = Field(default="", description="剧情证据或事件摘要")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="用户自定义元数据")

    def is_active_at(self, chapter: int) -> bool:
        """断言在特定章节该关系是否有效"""
        return self.valid_from_chapter <= chapter <= self.valid_to_chapter


class LoreEntry(BaseModel):
    """确定性 Codex 词条 (SillyTavern / NovelCrafter 纯机制规范)"""
    entry_id: str
    entity_type: str = Field(description="实体类别（支持通用扩展）")
    name: str
    aliases: List[str] = Field(default_factory=list, description="别名与触发变体")
    
    # 级联触发机制 (Cascade Triggering)
    primary_keys: List[str] = Field(
        default_factory=list,
        description="一级触发关键词（正文出现任一即可激活候选池）"
    )
    secondary_keys: List[str] = Field(
        default_factory=list,
        description="二级级联条件词（仅当同时命中一级词与二级词时才真正注入）"
    )
    
    content: str = Field(description="实际注入给 Prompt 的设定文本")
    is_global: bool = Field(default=False, description="是否作为全局常驻上下文")
    scan_depth: int = Field(default=1, description="回溯扫描前序 Beat 数量")
    
    # 时序生命周期
    valid_from_chapter: int = 1
    valid_to_chapter: int = 999999

    def is_valid_at(self, chapter: int) -> bool:
        return self.valid_from_chapter <= chapter <= self.valid_to_chapter
