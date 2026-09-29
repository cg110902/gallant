"""
Name Collision Detector - 角色命名冲突检测器

长篇动辄上百个具名角色，取名冲突是真实且高频的事故：
  - 「陈天雄」与「陈天豪」同卷登场，读者完全分不清；
  - 「林薇」与「林蔚」音近形近；
  - 全书 40 个角色里 12 个姓「叶」；
  - 配角名字与主角的某个别号撞车。

本模块不依赖外部拼音库（保持零新增依赖），而是用三条可靠的启发式：
1. 字形重叠度 (Jaccard on characters)；
2. 声母近似表（手工维护的中文易混声母/韵母组）；
3. 姓氏分布过载检测。
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

# 中文常见易混同音/近音字组（同组内视为音近）
HOMOPHONE_GROUPS: List[Set[str]] = [
    {"薇", "蔚", "微", "巍", "威", "韦"},
    {"雄", "熊", "兄"},
    {"豪", "浩", "昊", "皓", "颢"},
    {"轩", "萱", "宣", "暄"},
    {"琳", "林", "霖", "临"},
    {"辰", "晨", "尘", "臣", "宸"},
    {"宇", "羽", "雨", "禹"},
    {"逸", "轶", "怡", "毅", "翼", "亦"},
    {"婷", "亭", "庭", "廷"},
    {"锋", "峰", "风", "丰", "封"},
    {"飞", "菲", "斐"},
    {"云", "雲", "芸", "韵"},
    {"静", "婧", "竞", "净"},
    {"瑶", "遥", "谣", "尧"},
    {"毅", "义", "亿", "奕"},
    {"凡", "帆", "繁", "藩"},
]

# 常见复姓（避免把复姓拆错）
COMPOUND_SURNAMES = {
    "欧阳", "司马", "上官", "诸葛", "东方",
    "夏侯", "皇甫", "尉迟", "公孙", "慕容", "长孙", "宇文", "南宫", "西门", "轩辕",
}


def _homophone_key(ch: str) -> str:
    """把字映射到其同音组代表字；不在任何组内则返回自身"""
    for group in HOMOPHONE_GROUPS:
        if ch in group:
            return min(group)
    return ch


@dataclass
class NameCollision:
    collision_type: str      # IDENTICAL / GLYPH_SIMILAR / PHONETIC_SIMILAR / SURNAME_OVERLOAD
    severity: str            # ERROR / WARNING
    names: List[str]
    entity_ids: List[str] = field(default_factory=list)
    similarity: float = 0.0
    message: str = ""
    suggestion: str = ""


@dataclass
class NameCollisionReport:
    passed: bool = True
    collisions: List[NameCollision] = field(default_factory=list)
    total_names_scanned: int = 0
    surname_distribution: Dict[str, int] = field(default_factory=dict)

    @property
    def errors(self) -> List[NameCollision]:
        return [c for c in self.collisions if c.severity == "ERROR"]

    def format_summary(self) -> str:
        if not self.collisions:
            return f"[命名冲突] PASS 已扫描 {self.total_names_scanned} 个角色名，未检出冲突"
        lines = [
            f"[命名冲突] {'PASS' if self.passed else 'FAIL'} "
            f"扫描 {self.total_names_scanned} 个名字，检出 {len(self.collisions)} 处风险"
        ]
        for c in self.collisions:
            lines.append(f"  - [{c.severity}] {c.collision_type}: {c.message}")
        return "\n".join(lines)


class NameCollisionDetector:
    """角色命名冲突检测器"""

    def __init__(
        self,
        glyph_similarity_threshold: float = 0.5,
        max_same_surname_ratio: float = 0.25,
        min_names_for_surname_check: int = 8,
    ):
        self.glyph_threshold = glyph_similarity_threshold
        self.max_same_surname_ratio = max_same_surname_ratio
        self.min_names_for_surname_check = min_names_for_surname_check

    # ---------- 基础度量 ----------

    @staticmethod
    def glyph_similarity(a: str, b: str) -> float:
        """字形重叠度：共享汉字数 / 并集汉字数"""
        sa, sb = set(a), set(b)
        if not sa or not sb:
            return 0.0
        return len(sa & sb) / len(sa | sb)

    @staticmethod
    def phonetic_similarity(a: str, b: str) -> float:
        """音近度：将每个字归一到同音组代表字后再比对"""
        if len(a) != len(b):
            ka = "".join(_homophone_key(c) for c in a)
            kb = "".join(_homophone_key(c) for c in b)
            sa, sb = set(ka), set(kb)
            return len(sa & sb) / len(sa | sb) if sa and sb else 0.0
        same = sum(1 for x, y in zip(a, b) if _homophone_key(x) == _homophone_key(y))
        return same / len(a)

    @staticmethod
    def extract_surname(name: str) -> str:
        if len(name) >= 2 and name[:2] in COMPOUND_SURNAMES:
            return name[:2]
        return name[0] if name else ""

    # ---------- 主检测 ----------

    def check(
        self,
        names: Sequence[str],
        entity_ids: Optional[Sequence[str]] = None,
    ) -> NameCollisionReport:
        """对一组角色名做全量两两冲突检测"""
        report = NameCollisionReport(total_names_scanned=len(names))
        ids = list(entity_ids) if entity_ids else list(names)
        id_of = {n: (ids[i] if i < len(ids) else n) for i, n in enumerate(names)}

        seen: Dict[str, List[str]] = defaultdict(list)
        for i, n in enumerate(names):
            seen[n].append(id_of.get(n, n))

        # 1. 完全重名
        for name, holders in seen.items():
            if len(holders) > 1:
                report.collisions.append(NameCollision(
                    collision_type="IDENTICAL",
                    severity="ERROR",
                    names=[name],
                    entity_ids=holders,
                    similarity=1.0,
                    message=f"完全重名：「{name}」被 {len(holders)} 个不同实体使用 ({', '.join(holders)})",
                    suggestion="必须为其中之一改名，或显式设定为同名梗并在正文中点明。",
                ))

        unique_names = [n for n in dict.fromkeys(names)]

        # 2. 两两形近 / 音近
        for i in range(len(unique_names)):
            for j in range(i + 1, len(unique_names)):
                a, b = unique_names[i], unique_names[j]
                if a == b:
                    continue
                glyph = self.glyph_similarity(a, b)
                phon = self.phonetic_similarity(a, b)

                if glyph >= self.glyph_threshold:
                    report.collisions.append(NameCollision(
                        collision_type="GLYPH_SIMILAR",
                        severity="WARNING" if glyph < 0.75 else "ERROR",
                        names=[a, b],
                        entity_ids=[id_of.get(a, a), id_of.get(b, b)],
                        similarity=round(glyph, 3),
                        message=(
                            f"字形高度相似：「{a}」与「{b}」共享 {glyph:.0%} 的汉字，"
                            f"读者在快速阅读时极易混淆"
                        ),
                        suggestion=f"建议将「{b}」改为字形差异更大的名字（更换非姓氏的用字）。",
                    ))
                elif phon >= 0.66 and len(a) == len(b):
                    report.collisions.append(NameCollision(
                        collision_type="PHONETIC_SIMILAR",
                        severity="WARNING",
                        names=[a, b],
                        entity_ids=[id_of.get(a, a), id_of.get(b, b)],
                        similarity=round(phon, 3),
                        message=(
                            f"读音高度相似：「{a}」与「{b}」音近度 {phon:.0%}，"
                            f"有声书与读者默读场景下易混"
                        ),
                        suggestion=f"建议调整「{b}」的用字，使其声母或韵母明显区分。",
                    ))

        # 3. 姓氏分布过载
        surnames = Counter(self.extract_surname(n) for n in unique_names if n)
        report.surname_distribution = dict(surnames)
        if len(unique_names) >= self.min_names_for_surname_check:
            for sur, cnt in surnames.items():
                ratio = cnt / len(unique_names)
                if ratio > self.max_same_surname_ratio and cnt >= 3:
                    holders = [n for n in unique_names if self.extract_surname(n) == sur]
                    report.collisions.append(NameCollision(
                        collision_type="SURNAME_OVERLOAD",
                        severity="WARNING",
                        names=holders,
                        similarity=round(ratio, 3),
                        message=(
                            f"姓氏过载：全书 {len(unique_names)} 个角色中有 {cnt} 个姓「{sur}」"
                            f"（占比 {ratio:.0%}），削弱角色区分度"
                        ),
                        suggestion=(
                            f"除非「{sur}」是设定中的家族主线，否则建议分散姓氏；"
                            f"当前同姓角色: {', '.join(holders)}"
                        ),
                    ))

        report.passed = not report.errors
        return report

    def check_new_name(
        self, candidate: str, existing_names: Sequence[str]
    ) -> Tuple[bool, List[NameCollision]]:
        """
        在为新角色取名时做准入校验。
        返回 (是否可用, 冲突列表)。建议接在导演智能体创建新角色的环节。
        """
        report = self.check(list(existing_names) + [candidate])
        related = [
            c for c in report.collisions
            if candidate in c.names and c.collision_type != "SURNAME_OVERLOAD"
        ]
        blocking = [c for c in related if c.severity == "ERROR"]
        return (not blocking), related

    def suggest_alternatives(self, candidate: str, existing_names: Sequence[str]) -> List[str]:
        """给出规避冲突的候选改名（替换末字为非同音组用字）"""
        safe_pool = list("羽然岚川石野青白墨寒知鹤竹松岳海砚淮岐")
        out: List[str] = []
        if not candidate:
            return out
        stem = candidate[:-1] if len(candidate) > 1 else candidate
        for ch in safe_pool:
            cand = stem + ch
            if cand in existing_names or cand == candidate:
                continue
            ok, _ = self.check_new_name(cand, existing_names)
            if ok:
                out.append(cand)
            if len(out) >= 5:
                break
        return out
