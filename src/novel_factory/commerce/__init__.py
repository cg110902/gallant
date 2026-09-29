"""
Commercial Viability Layer - 网文商业性引擎

文笔干净、逻辑自洽的小说，依然可能扑街。网文的商业命脉是另一套指标：
爽点密度够不够、章末钩子留没留、升级节奏崩没崩、支线断没断更。

本层提供四大商业性引擎：

1. HookEnforcer       - 章末钩子强制器：钩子类型识别与强度评级；
2. PayoffDensityMeter - 爽点密度曲线：憋屈/爆发配比与"憋太久"预警；
3. PowerCurveGuard    - 升级节奏守门员：战力膨胀速率与越阶失控约束；
4. ThreadScheduler    - 多线叙事调度器：支线断更预警与 POV 配额管理。
"""

from .hook_enforcer import (
    HookEnforcer,
    HookType,
    HookEvaluation,
    HookStrength,
)
from .payoff_density import (
    PayoffDensityMeter,
    ChapterEmotionBeat,
    DensityReport,
    EmotionValence,
)
from .power_curve import (
    PowerCurveGuard,
    PowerSample,
    PowerCurveReport,
    PowerCurveViolation,
)
from .thread_scheduler import (
    ThreadScheduler,
    StoryThread,
    ThreadPriority,
    ThreadScheduleReport,
)

__all__ = [
    "HookEnforcer",
    "HookType",
    "HookEvaluation",
    "HookStrength",
    "PayoffDensityMeter",
    "ChapterEmotionBeat",
    "DensityReport",
    "EmotionValence",
    "PowerCurveGuard",
    "PowerSample",
    "PowerCurveReport",
    "PowerCurveViolation",
    "ThreadScheduler",
    "StoryThread",
    "ThreadPriority",
    "ThreadScheduleReport",
]
