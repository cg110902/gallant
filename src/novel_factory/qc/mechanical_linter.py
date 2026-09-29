"""
Mechanical Linter - 数据与配置驱动的高精度纯机制机械质检引擎 (Configuration-Driven)
核心代码严禁硬编码任何题材特定文本或文学性判断；所有检测规则、阈值与扣分逻辑均通过 YAML 配置动态加载。
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Union
import yaml


class Severity(str, Enum):
    ERROR = "ERROR"      # 硬伤：直接阻断提交
    WARNING = "WARNING"  # 警告：需扣分但允许在容忍阈值内


@dataclass
class LintRule:
    """声明式质检规则"""
    id: str
    category: str
    severity: Severity
    pattern: str
    message: str
    suggestion: str
    enabled: bool = True
    _compiled_regex: Optional[re.Pattern] = None

    def get_compiled(self) -> re.Pattern:
        if self._compiled_regex is None:
            self._compiled_regex = re.compile(self.pattern)
        return self._compiled_regex


@dataclass
class LintViolation:
    rule_id: str
    category: str
    severity: Severity
    line_number: int
    matched_text: str
    message: str
    suggestion: str


@dataclass
class LintReport:
    score: float  # 0.0 ~ 100.0
    passed: bool
    total_errors: int
    total_warnings: int
    violations: List[LintViolation] = field(default_factory=list)

    def format_summary(self) -> str:
        status = "PASSED" if self.passed else "FAILED"
        lines = [
            f"=== 机械质检报告 [{status}] 得分: {self.score:.1f} / 100 ===",
            f"硬性违规 (Errors): {self.total_errors}, 警告项 (Warnings): {self.total_warnings}"
        ]
        for v in self.violations:
            prefix = "[x]" if v.severity == Severity.ERROR else "[!]"
            lines.append(
                f"{prefix} Line {v.line_number} [{v.rule_id}] 命中: \"{v.matched_text}\""
                f"\n    类别: {v.category}"
                f"\n    原因: {v.message}"
                f"\n    建议: {v.suggestion}"
            )
        return "\n".join(lines)


class MechanicalLinter:
    """
    配置驱动的通用机械质检引擎
    代码本身是中立的规则执行器，一切行为由传入的配置文件决定
    """

    def __init__(
        self,
        rule_configs: Optional[List[Union[str, Path, Dict[str, Any]]]] = None,
        min_pass_score: Optional[float] = None,
        error_penalty: float = 8.0,
        warning_penalty: float = 3.0,
        max_sentences_per_paragraph: int = 3,
        max_chars_per_paragraph: int = 150
    ):
        self.rules: List[LintRule] = []
        self.min_pass_score = min_pass_score or 85.0
        self.error_penalty = error_penalty
        self.warning_penalty = warning_penalty
        self.max_sentences_per_paragraph = max_sentences_per_paragraph
        self.max_chars_per_paragraph = max_chars_per_paragraph

        # 加载配置
        if rule_configs:
            for cfg in rule_configs:
                self.load_rules(cfg)
        else:
            # 自动探测加载默认配置目录 configs/rules/
            default_rule_file = Path(__file__).resolve().parents[3] / "configs" / "rules" / "anti_slop.yaml"
            if default_rule_file.exists():
                self.load_rules(default_rule_file)

    def load_rules(self, source: Union[str, Path, Dict[str, Any]]) -> None:
        """从文件或字典加载声明式质检规则"""
        if isinstance(source, (str, Path)):
            with open(source, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        else:
            data = source

        # 解析阈值设置（若配置文件包含）
        if "thresholds" in data:
            th = data["thresholds"]
            self.min_pass_score = th.get("min_pass_score", self.min_pass_score)
            self.error_penalty = th.get("error_penalty", self.error_penalty)
            self.warning_penalty = th.get("warning_penalty", self.warning_penalty)

        # 解析规则列表
        raw_rules = data.get("rules", [])
        for r in raw_rules:
            if not r.get("enabled", True):
                continue
            severity = Severity.ERROR if r.get("severity") == "ERROR" else Severity.WARNING
            self.rules.append(
                LintRule(
                    id=r["id"],
                    category=r.get("category", "GENERAL"),
                    severity=severity,
                    pattern=r["pattern"],
                    message=r.get("message", "命中违规模式"),
                    suggestion=r.get("suggestion", "请重构该句"),
                    enabled=True
                )
            )

    def lint_text(self, text: str) -> LintReport:
        """基于已加载的全部规则对文本执行确定性扫描"""
        violations: List[LintViolation] = []
        lines = text.split("\n")

        for line_idx, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            if not line:
                continue

            # 1. 匹配所有已启用的正则声明规则
            for rule in self.rules:
                compiled = rule.get_compiled()
                for m in compiled.finditer(line):
                    violations.append(
                        LintViolation(
                            rule_id=rule.id,
                            category=rule.category,
                            severity=rule.severity,
                            line_number=line_idx,
                            matched_text=m.group(),
                            message=rule.message,
                            suggestion=rule.suggestion
                        )
                    )

            # 2. 通用移动端排版约束检查（段落呼吸感）
            sentences = [s for s in re.split(r"[。！？!?]", line) if s.strip()]
            if len(sentences) > self.max_sentences_per_paragraph or len(line) > self.max_chars_per_paragraph:
                violations.append(
                    LintViolation(
                        rule_id="MOBILE_PARAGRAPH_OVERFLOW",
                        category="FORMATTING",
                        severity=Severity.WARNING,
                        line_number=line_idx,
                        matched_text=line[:30] + "...",
                        message=f"单段句子数 ({len(sentences)}) 或字数 ({len(line)}) 过长，不适配手机端翻页沉浸体验",
                        suggestion=f"建议单段限制在 {self.max_sentences_per_paragraph} 句话或 {self.max_chars_per_paragraph} 字以内"
                    )
                )

        # 核算最终分值
        total_errors = sum(1 for v in violations if v.severity == Severity.ERROR)
        total_warnings = sum(1 for v in violations if v.severity == Severity.WARNING)

        deduction = (total_errors * self.error_penalty) + (total_warnings * self.warning_penalty)
        final_score = max(0.0, 100.0 - deduction)
        passed = (final_score >= self.min_pass_score) and (total_errors == 0)

        return LintReport(
            score=final_score,
            passed=passed,
            total_errors=total_errors,
            total_warnings=total_warnings,
            violations=violations
        )
