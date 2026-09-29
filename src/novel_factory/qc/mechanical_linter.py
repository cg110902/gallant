"""
Mechanical Linter - 数据与配置驱动的高精度纯机制机械质检与语法树剪枝引擎 (Config-Driven AST)
核心代码严禁硬编码任何题材特定文本或文学性判断；所有检测规则、阈值与扣分逻辑均通过 YAML 配置动态加载。
特性：
1. AST 语法树解析 (Document -> Paragraph -> Sentence)；
2. 零议论反说教 AST 段尾修剪器 (prune_tail_moralizers)；
3. 移动端脉冲流排版检验 (Mobile Pulse Flow & Isolated Climax Line)；
4. 题材专属套话与黑名单动态加载 (Genre Rules Loader)。
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple, Union
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


# ================== AST 结构定义 ==================

@dataclass
class SentenceAST:
    sentence_index: int
    raw_text: str
    is_dialogue: bool = False
    ending_punctuation: str = "。"


@dataclass
class ParagraphAST:
    paragraph_index: int
    raw_text: str
    sentences: List[SentenceAST] = field(default_factory=list)

    @property
    def sentence_count(self) -> int:
        return len(self.sentences)

    @property
    def is_isolated_line(self) -> bool:
        """是否为单句孤立行（常用于核心高潮、反转或重击）"""
        return self.sentence_count == 1 and len(self.raw_text.strip()) <= 45


@dataclass
class DocumentAST:
    paragraphs: List[ParagraphAST] = field(default_factory=list)

    @classmethod
    def parse_from_text(cls, text: str) -> "DocumentAST":
        """将纯文本正文解析为 AST 树"""
        doc = cls()
        lines = text.split("\n")
        para_idx = 0

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            para_idx += 1
            # 切分句子
            raw_sentences = [s.strip() for s in re.split(r"([。！？!?…]+)", line_str) if s.strip()]
            sentences: List[SentenceAST] = []
            
            # 配对句子与标点
            i = 0
            sent_idx = 0
            while i < len(raw_sentences):
                s_text = raw_sentences[i]
                punct = "。"
                if i + 1 < len(raw_sentences) and re.match(r"^[。！？!?…]+$", raw_sentences[i+1]):
                    punct = raw_sentences[i+1]
                    i += 2
                else:
                    i += 1

                sent_idx += 1
                full_sent = s_text + punct
                is_dial = (full_sent.startswith("“") or full_sent.startswith('"'))
                sentences.append(SentenceAST(
                    sentence_index=sent_idx,
                    raw_text=full_sent,
                    is_dialogue=is_dial,
                    ending_punctuation=punct
                ))

            doc.paragraphs.append(ParagraphAST(
                paragraph_index=para_idx,
                raw_text=line_str,
                sentences=sentences
            ))

        return doc


# ================== 核心 Linter ==================

class MechanicalLinter:
    """
    配置驱动的通用机械质检与语法树剪枝引擎
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
            default_rules_dir = Path(__file__).resolve().parents[3] / "configs" / "rules"
            if default_rules_dir.exists():
                for yaml_file in default_rules_dir.glob("*.yaml"):
                    self.load_rules(yaml_file)

    def load_rules(self, source: Union[str, Path, Dict[str, Any]]) -> None:
        """从文件路径或直接字典加载规则"""
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

    def prune_tail_moralizers(self, text: str) -> Tuple[str, int]:
        """
        基于 AST 语法树剪枝：
        自动扫描每个段落末尾。若末尾句子命中 ZERO_MORALIZER 说教规则，直接干净剪除，保留前段动作句子。
        返回: (修剪后的文本, 修剪句子数)
        """
        doc = DocumentAST.parse_from_text(text)
        moralizer_rules = [r for r in self.rules if r.category == "ZERO_MORALIZER" and r.enabled]
        
        pruned_count = 0
        cleaned_paragraphs = []

        for para in doc.paragraphs:
            if not para.sentences:
                cleaned_paragraphs.append(para.raw_text)
                continue

            last_sentence = para.sentences[-1]
            is_moralizer = False

            for rule in moralizer_rules:
                if rule.get_compiled().search(last_sentence.raw_text):
                    is_moralizer = True
                    break

            if is_moralizer and len(para.sentences) > 1:
                # 剔除末尾说教句，保留前面的动作句
                remaining = para.sentences[:-1]
                pruned_para_text = "".join(s.raw_text for s in remaining)
                cleaned_paragraphs.append(pruned_para_text)
                pruned_count += 1
            elif is_moralizer and len(para.sentences) == 1:
                # 整段就一句说教，直接整段剔除
                pruned_count += 1
                continue
            else:
                cleaned_paragraphs.append(para.raw_text)

        return "\n\n".join(cleaned_paragraphs), pruned_count

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
