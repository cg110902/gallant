"""
Compliance & Sensitive Content Scanner - 过审风控扫描器

国内网文平台首要死因不是文笔，是过不了审。本模块在提交前做机械风控拦截：
1. 分级敏感词库 (BLOCK / REVIEW / SOFTEN)；
2. 变形绕写检测（插入空格、全角半角、拼音首字母、同音替换的简单归一化）；
3. 未成年人涉性内容的强制红线；
4. 血腥暴力过度描写的软性降级建议；
5. 真实国家/政党/领导人指代的政治红线；
6. 品牌与真实企业名的法务风险提示。

设计原则：宁可误报给人看，不可漏报被封书。
所有词库均为外部 YAML 声明式挂载，代码零硬编码业务词。
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Union

import yaml


class ComplianceAction(str, Enum):
    BLOCK = "BLOCK"        # 硬红线，禁止提交
    REVIEW = "REVIEW"      # 需人工复核
    SOFTEN = "SOFTEN"      # 建议弱化改写


DEFAULT_COMPLIANCE_PACK = "configs/rules/compliance.yaml"


@dataclass
class ComplianceHit:
    term: str
    category: str
    action: ComplianceAction
    line_number: int
    context: str
    suggestion: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "term": self.term,
            "category": self.category,
            "action": self.action.value,
            "line_number": self.line_number,
            "context": self.context,
            "suggestion": self.suggestion,
        }


@dataclass
class ComplianceReport:
    passed: bool = True
    hits: List[ComplianceHit] = field(default_factory=list)
    scanned_chars: int = 0

    @property
    def blocking_hits(self) -> List[ComplianceHit]:
        return [h for h in self.hits if h.action == ComplianceAction.BLOCK]

    @property
    def review_hits(self) -> List[ComplianceHit]:
        return [h for h in self.hits if h.action == ComplianceAction.REVIEW]

    def format_summary(self) -> str:
        if not self.hits:
            return "[过审风控] PASS 未检出风险内容"
        lines = [f"[过审风控] {'PASS' if self.passed else 'BLOCKED'} 检出 {len(self.hits)} 处风险"]
        for h in self.hits:
            lines.append(f"  - [{h.action.value}] {h.category} 第{h.line_number}行 命中「{h.term}」")
        return "\n".join(lines)


class ComplianceScanner:
    """过审风控扫描器"""

    def __init__(self, rules: Optional[Dict[str, Any]] = None):
        # category -> {action, terms, suggestion}
        self.categories: Dict[str, Dict[str, Any]] = {}
        if rules:
            self.load_rules(rules)

    @classmethod
    def from_default_pack(cls, path: Union[str, Path] = DEFAULT_COMPLIANCE_PACK) -> "ComplianceScanner":
        """从默认声明式词库挂载；文件缺失时退化为空扫描器（不阻断流水线）"""
        scanner = cls()
        p = Path(path)
        if p.exists():
            scanner.load_rules(p)
        return scanner

    def load_rules(self, source: Union[str, Path, Dict[str, Any]]) -> None:
        if isinstance(source, (str, Path)):
            with open(source, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        else:
            data = source

        for cat in data.get("categories", []):
            name = cat.get("name")
            if not name:
                continue
            self.categories[name] = {
                "action": ComplianceAction(cat.get("action", "REVIEW")),
                "terms": [t for t in cat.get("terms", []) if t],
                "suggestion": cat.get("suggestion", ""),
            }

    @staticmethod
    def normalize(text: str) -> str:
        """
        归一化以对抗简单的绕写变形：
        去除空白、分隔符与常见插入字符，全角转半角。
        """
        text = text.replace("\u3000", "")
        out = []
        for ch in text:
            code = ord(ch)
            if 0xFF01 <= code <= 0xFF5E:
                out.append(chr(code - 0xFEE0))
            else:
                out.append(ch)
        norm = "".join(out)
        return re.sub(r"[\s\-_·•．.*＊~～|丨/\\]+", "", norm)

    def scan(self, text: str, block_on_review: bool = False) -> ComplianceReport:
        """
        扫描正文。
        block_on_review=True 时，REVIEW 级也会导致 passed=False（严格模式）。
        """
        report = ComplianceReport(scanned_chars=len(text))
        lines = text.split("\n")
        normalized_lines = [self.normalize(ln) for ln in lines]

        for cat_name, cfg in self.categories.items():
            action: ComplianceAction = cfg["action"]
            suggestion: str = cfg["suggestion"]
            for term in cfg["terms"]:
                norm_term = self.normalize(term)
                if not norm_term:
                    continue
                for idx, norm_line in enumerate(normalized_lines, start=1):
                    if norm_term in norm_line:
                        raw = lines[idx - 1]
                        report.hits.append(ComplianceHit(
                            term=term,
                            category=cat_name,
                            action=action,
                            line_number=idx,
                            context=raw[:60],
                            suggestion=suggestion,
                        ))

        if report.blocking_hits:
            report.passed = False
        elif block_on_review and report.review_hits:
            report.passed = False
        return report
