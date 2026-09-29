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

__all__ = [
    "Severity",
    "LintViolation",
    "LintReport",
    "MechanicalLinter",
    "DroolingIncident",
    "RepetitionAnalysisReport",
    "RepetitionDetector",
]
