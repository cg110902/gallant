"""
Trope Cooldown - Codex Alias to QC Trope Cooldown Engine
保持向后兼容性，将底层逻辑统一收敛至 src/novel_factory/qc/trope_cooldown.py
"""

from src.novel_factory.qc.trope_cooldown import (
    TropeDefinition,
    HalfLifeFatigueTracker,
    TropeCooldownTracker,
)

__all__ = [
    "TropeDefinition",
    "HalfLifeFatigueTracker",
    "TropeCooldownTracker",
]
