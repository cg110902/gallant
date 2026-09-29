"""
Quality Control Module - 质检与反AI退化引擎
"""

from .mechanical_linter import (
    LintReport,
    LintViolation,
    MechanicalLinter,
    Severity,
)
from .repetition_detector import (
    DroolingIncident,
    RepetitionAnalysisReport,
    RepetitionDetector,
)
from .simhash_dedup import (
    SimHashDeduplicator,
    CrossChapterDedupIndex,
    DynamicFatigueMatrix,
    DuplicateIncident,
    DynamicBanListRecommendation,
)
from .trope_cooldown import (
    TropeDefinition,
    HalfLifeFatigueTracker,
    TropeCooldownTracker,
)

__all__ = [
    "Severity",
    "LintViolation",
    "LintReport",
    "MechanicalLinter",
    "DroolingIncident",
    "RepetitionAnalysisReport",
    "RepetitionDetector",
    "SimHashDeduplicator",
    "CrossChapterDedupIndex",
    "DynamicFatigueMatrix",
    "DuplicateIncident",
    "DynamicBanListRecommendation",
    "TropeDefinition",
    "HalfLifeFatigueTracker",
    "TropeCooldownTracker",
]
