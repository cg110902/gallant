"""
Event Sourcing Core - 不可变领域事件规范 (Immutable Domain Events)
构建小说时态事实库的核心单元，所有人物成长、关系缔结、物品流转与死亡均表达为不可篡改的事件。
"""

from enum import Enum
import json
import time
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class EventType(str, Enum):
    """领域事件类型枚举"""
    ENTITY_SPAWNED = "ENTITY_SPAWNED"                # 实体首次登场/被创造
    ATTRIBUTE_CHANGED = "ATTRIBUTE_CHANGED"          # 实体属性演进（境界/战力/状态标签）
    ITEM_ACQUIRED = "ITEM_ACQUIRED"                  # 获得物品/装备
    ITEM_TRANSFERRED = "ITEM_TRANSFERRED"            # 物品转赠/掉落/被缴获
    ITEM_DESTROYED = "ITEM_DESTROYED"                # 物品被损毁/消耗
    RELATION_FORMED = "RELATION_FORMED"              # 关系建立（结盟/敌对/拜师/契约）
    RELATION_TERMINATED = "RELATION_TERMINATED"      # 关系终结（背叛/解约/驱逐）
    ENTITY_KILLED = "ENTITY_KILLED"                  # 角色死亡/实体湮灭
    PLOT_THREAD_OPENED = "PLOT_THREAD_OPENED"        # 埋下伏笔/支线激活
    PLOT_THREAD_RESOLVED = "PLOT_THREAD_RESOLVED"    # 伏笔闭环/支线结算


class Event(BaseModel):
    """不可变事件数据模型"""
    event_id: str = Field(description="全局唯一事件UUID或哈希")
    sequence_num: int = Field(default=0, description="严格单调递增全局时序序号")
    chapter_index: int = Field(description="发生章节序号")
    beat_id: Optional[str] = Field(default=None, description="所属分镜节拍ID")
    timestamp: float = Field(default_factory=time.time, description="真实系统时间戳")
    event_type: EventType
    entity_id: str = Field(description="主事件实体ID")
    target_entity_id: Optional[str] = Field(default=None, description="关联目标实体ID（用于关系与转赠）")
    payload: Dict[str, Any] = Field(default_factory=dict, description="事件具体属性增量或变动内容")
    provenance_text: str = Field(default="", description="事件发生的原著正文摘要或因果证据")

    def to_json(self) -> str:
        return json.dumps(self.model_dump(), ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "Event":
        return cls(**json.loads(json_str))
