"""
Agents Module - Antigravity 专职子智能体协同桥梁
"""

from .orchestrator_bridge import (
    SubagentCoordinationBus,
    SubagentRole,
    SubagentTaskPayload,
)

__all__ = [
    "SubagentRole",
    "SubagentTaskPayload",
    "SubagentCoordinationBus",
]
