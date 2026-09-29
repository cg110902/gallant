"""
Long-Range Consistency Layer - 长程一致性层

百万字长篇崩坏的根源从来不是单章文笔，而是跨越数百章的状态漂移。
本层提供四大长程一致性引擎：

1. ForeshadowLedger  - 伏笔/契诃夫之枪台账：埋设-回收全生命周期追踪与超期预警；
2. StoryCalendar     - 故事内时间线日历：绝对时钟推进、时序倒流与时长矛盾检测；
3. PersonaRegistry   - 人设一致性指纹：称谓表、口癖、语体风格与 OOC 检测；
4. NameCollisionDetector - 角色命名冲突：重名、形近、音近与姓氏过载检测。
"""

from .foreshadowing import (
    ForeshadowLedger,
    ForeshadowRecord,
    ForeshadowStatus,
    ForeshadowReport,
    ForeshadowWeight,
)
from .timeline import (
    StoryCalendar,
    StoryInstant,
    TimeAnchor,
    TimelineConflict,
    TimelineReport,
)
from .persona import (
    AddressRule,
    PersonaProfile,
    PersonaRegistry,
    PersonaViolation,
    PersonaReport,
)
from .name_collision import (
    NameCollisionDetector,
    NameCollision,
    NameCollisionReport,
)

__all__ = [
    "ForeshadowLedger",
    "ForeshadowRecord",
    "ForeshadowStatus",
    "ForeshadowReport",
    "ForeshadowWeight",
    "StoryCalendar",
    "StoryInstant",
    "TimeAnchor",
    "TimelineConflict",
    "TimelineReport",
    "AddressRule",
    "PersonaProfile",
    "PersonaRegistry",
    "PersonaViolation",
    "PersonaReport",
    "NameCollisionDetector",
    "NameCollision",
    "NameCollisionReport",
]
