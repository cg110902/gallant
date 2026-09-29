"""
Persona Consistency Registry - 人设一致性指纹与称谓关系引擎

长篇写到两三百章，最典型的崩坏是「所有人说话都像同一个人」，以及：
  - 称谓错乱：属下当面直呼主角姓名、师徒之间互称兄弟；
  - 口癖蒸发：设定了口头禅的角色，一百章后再没说过；
  - 语体漂移：粗鄙武夫突然开始用书面语讲哲理；
  - 知识越界：角色说出他在当前剧情里不可能知道的信息（信息穿越）。

本模块为每个角色建立可机械校验的【人设指纹】，并对正文做 OOC 检测。
称谓采用有向关系建模：A 对 B 的当面称呼 与 背后称呼 可以不同，这是中文叙事的刚需。
"""

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


class SpeechRegister(str, Enum):
    """语体登记：决定用词的文白程度与句式复杂度"""
    VULGAR = "VULGAR"            # 市井粗鄙，多短句脏话
    COLLOQUIAL = "COLLOQUIAL"    # 日常口语
    NEUTRAL = "NEUTRAL"          # 中性
    FORMAL = "FORMAL"            # 正式、克制
    ARCHAIC = "ARCHAIC"          # 文言古雅
    TECHNICAL = "TECHNICAL"      # 术语密集（黑客、医师、修士）


# 各语体的禁用特征词（出现即视为语体漂移）
REGISTER_FORBIDDEN: Dict[SpeechRegister, List[str]] = {
    SpeechRegister.VULGAR: ["综上所述", "诚如", "窃以为", "兹", "然则", "承蒙"],
    SpeechRegister.COLLOQUIAL: ["窃以为", "兹", "然则", "伏惟"],
    SpeechRegister.ARCHAIC: ["OK", "搞定", "牛逼", "没问题啊", "拜拜"],
    SpeechRegister.FORMAL: ["老子", "妈的", "牛逼", "滚蛋"],
    SpeechRegister.TECHNICAL: [],
    SpeechRegister.NEUTRAL: [],
}

_DIALOGUE_RE = re.compile(r"[“「『\"]([^”」』\"]{1,300})[”」』\"]")


@dataclass
class AddressRule:
    """A 对 B 的称谓规则（有向）"""
    speaker_id: str
    target_id: str
    face_to_face: str                      # 当面称呼，如「师尊」
    behind_back: Optional[str] = None      # 背后称呼，如「那老东西」
    forbidden: List[str] = field(default_factory=list)  # 绝对不能使用的称呼
    valid_from_chapter: int = 1            # 关系演变：称谓可随剧情改变
    valid_to_chapter: int = 999999

    def active_at(self, chapter_index: int) -> bool:
        return self.valid_from_chapter <= chapter_index <= self.valid_to_chapter


@dataclass
class PersonaProfile:
    """角色人设指纹"""
    entity_id: str
    name: str
    register: SpeechRegister = SpeechRegister.NEUTRAL
    verbal_tics: List[str] = field(default_factory=list)      # 口头禅
    tic_min_frequency_chapters: int = 20                      # 至少每 N 章出现一次口癖
    signature_vocabulary: List[str] = field(default_factory=list)  # 专属高频词
    forbidden_vocabulary: List[str] = field(default_factory=list)  # 绝不会说的词
    max_sentence_length: int = 60                             # 单句上限（寡言角色更短）
    knowledge_boundary: List[str] = field(default_factory=list)  # 尚不知晓的信息关键词
    self_reference: str = ""                                  # 自称，如「本座」「洒家」「我」
    aliases: List[str] = field(default_factory=list)

    def all_names(self) -> List[str]:
        return [self.name] + [a for a in self.aliases if a]


@dataclass
class PersonaViolation:
    violation_type: str
    severity: str           # ERROR / WARNING
    entity_id: str
    message: str
    evidence: str = ""
    repair_hint: str = ""


@dataclass
class PersonaReport:
    chapter_index: int
    passed: bool = True
    violations: List[PersonaViolation] = field(default_factory=list)

    @property
    def errors(self) -> List[PersonaViolation]:
        return [v for v in self.violations if v.severity == "ERROR"]

    def format_summary(self) -> str:
        if not self.violations:
            return f"[人设一致性] 第{self.chapter_index}章 PASS"
        lines = [
            f"[人设一致性] 第{self.chapter_index}章 "
            f"{'PASS' if self.passed else 'FAIL'} 检出 {len(self.violations)} 处"
        ]
        for v in self.violations:
            lines.append(f"  - [{v.severity}] {v.violation_type} [{v.entity_id}]: {v.message}")
        return "\n".join(lines)

    def repair_instructions(self) -> List[str]:
        return [v.repair_hint for v in self.violations if v.repair_hint]


class PersonaRegistry:
    """人设一致性注册表与 OOC 检测器"""

    def __init__(self):
        self.profiles: Dict[str, PersonaProfile] = {}
        self.address_rules: List[AddressRule] = []
        # entity_id -> 最近一次出现口癖的章节
        self._last_tic_chapter: Dict[str, int] = {}

    # ---------- 注册 ----------

    def register_profile(self, profile: PersonaProfile) -> None:
        self.profiles[profile.entity_id] = profile

    def register_address(self, rule: AddressRule) -> None:
        self.address_rules.append(rule)

    def get_address(
        self, speaker_id: str, target_id: str, chapter_index: int, face_to_face: bool = True
    ) -> Optional[str]:
        """查询在指定章节 A 应当如何称呼 B"""
        for r in self.address_rules:
            if r.speaker_id == speaker_id and r.target_id == target_id and r.active_at(chapter_index):
                return r.face_to_face if face_to_face else (r.behind_back or r.face_to_face)
        return None

    # ---------- 检测 ----------

    @staticmethod
    def extract_dialogues(text: str) -> List[str]:
        """抽取正文中的所有引号台词"""
        return _DIALOGUE_RE.findall(text)

    def check_chapter(
        self,
        chapter_index: int,
        text: str,
        present_entities: Optional[Sequence[str]] = None,
        enforce_tic_frequency: bool = True,
    ) -> PersonaReport:
        """对整章正文做人设一致性检测"""
        report = PersonaReport(chapter_index=chapter_index)
        dialogues = self.extract_dialogues(text)
        joined_dialogue = "\n".join(dialogues)
        present = list(present_entities) if present_entities else list(self.profiles.keys())

        for ent_id in present:
            prof = self.profiles.get(ent_id)
            if not prof:
                continue
            appears = any(n in text for n in prof.all_names())

            # 1. 语体漂移检测
            for banned in REGISTER_FORBIDDEN.get(prof.register, []):
                if banned in joined_dialogue:
                    report.violations.append(PersonaViolation(
                        violation_type="REGISTER_DRIFT",
                        severity="WARNING",
                        entity_id=ent_id,
                        message=(
                            f"语体漂移：角色 [{prof.name}] 设定为 {prof.register.value} 语体，"
                            f"台词中却出现了不相称的用词「{banned}」"
                        ),
                        evidence=banned,
                        repair_hint=(
                            f"「{prof.name}」是 {prof.register.value} 语体，"
                            f"请把台词中的「{banned}」改写为符合其身份的说法。"
                        ),
                    ))

            # 2. 禁用词检测（角色绝不会说的话）
            for banned in prof.forbidden_vocabulary:
                if banned and banned in joined_dialogue:
                    report.violations.append(PersonaViolation(
                        violation_type="FORBIDDEN_VOCABULARY",
                        severity="ERROR",
                        entity_id=ent_id,
                        message=f"人设禁用词违规：[{prof.name}] 绝不会说「{banned}」",
                        evidence=banned,
                        repair_hint=f"删除或改写「{prof.name}」台词中的「{banned}」，此词违背其人设。",
                    ))

            # 3. 信息穿越检测（说出当前不该知道的事）
            for secret in prof.knowledge_boundary:
                if secret and secret in joined_dialogue:
                    report.violations.append(PersonaViolation(
                        violation_type="KNOWLEDGE_BOUNDARY_BREACH",
                        severity="ERROR",
                        entity_id=ent_id,
                        message=(
                            f"信息穿越：[{prof.name}] 在本章尚不应知晓「{secret}」，"
                            f"却在台词中提及"
                        ),
                        evidence=secret,
                        repair_hint=(
                            f"「{prof.name}」此时还不知道「{secret}」，请删除该台词，"
                            f"或先补写其获知该信息的情节。"
                        ),
                    ))

            # 4. 口癖保鲜检测
            if appears and prof.verbal_tics:
                if any(t in joined_dialogue for t in prof.verbal_tics):
                    self._last_tic_chapter[ent_id] = chapter_index
                elif enforce_tic_frequency:
                    last = self._last_tic_chapter.get(ent_id)
                    if last is not None and (chapter_index - last) > prof.tic_min_frequency_chapters:
                        report.violations.append(PersonaViolation(
                            violation_type="VERBAL_TIC_FADED",
                            severity="WARNING",
                            entity_id=ent_id,
                            message=(
                                f"口癖蒸发：[{prof.name}] 已 {chapter_index - last} 章未使用其标志性口头禅 "
                                f"{prof.verbal_tics}，角色辨识度正在流失"
                            ),
                            repair_hint=(
                                f"请在「{prof.name}」本章的台词中自然地带出其口头禅"
                                f"「{prof.verbal_tics[0]}」，不要生硬堆砌。"
                            ),
                        ))
                    elif last is None:
                        self._last_tic_chapter[ent_id] = chapter_index

            # 5. 自称一致性
            if prof.self_reference and appears:
                other_self_refs = {"本座", "老夫", "洒家", "朕", "贫道", "在下", "本宫", "老子"}
                other_self_refs.discard(prof.self_reference)
                for sr in other_self_refs:
                    if sr in joined_dialogue and prof.self_reference not in joined_dialogue:
                        report.violations.append(PersonaViolation(
                            violation_type="SELF_REFERENCE_DRIFT",
                            severity="WARNING",
                            entity_id=ent_id,
                            message=(
                                f"自称漂移嫌疑：[{prof.name}] 设定自称「{prof.self_reference}」，"
                                f"本章台词中出现了「{sr}」而未出现其本应使用的自称"
                            ),
                            evidence=sr,
                            repair_hint=f"确认「{sr}」不属于「{prof.name}」，其自称应为「{prof.self_reference}」。",
                        ))
                        break

        # 6. 称谓关系检测
        report.violations.extend(self._check_address_rules(chapter_index, text, dialogues))

        report.passed = not report.errors
        return report

    def _check_address_rules(
        self, chapter_index: int, text: str, dialogues: List[str]
    ) -> List[PersonaViolation]:
        """检测称谓违规：使用了明令禁止的称呼"""
        out: List[PersonaViolation] = []
        joined = "\n".join(dialogues)
        for rule in self.address_rules:
            if not rule.active_at(chapter_index):
                continue
            speaker = self.profiles.get(rule.speaker_id)
            target = self.profiles.get(rule.target_id)
            if not speaker or not target:
                continue
            # 说话人必须在场才判定
            if not any(n in text for n in speaker.all_names()):
                continue
            for bad in rule.forbidden:
                if bad and bad in joined:
                    out.append(PersonaViolation(
                        violation_type="ADDRESS_RULE_VIOLATION",
                        severity="ERROR",
                        entity_id=rule.speaker_id,
                        message=(
                            f"称谓违规：[{speaker.name}] 对 [{target.name}] 禁止使用称呼「{bad}」，"
                            f"当面应称「{rule.face_to_face}」"
                        ),
                        evidence=bad,
                        repair_hint=(
                            f"将「{speaker.name}」对「{target.name}」的称呼"
                            f"「{bad}」改为「{rule.face_to_face}」。"
                        ),
                    ))
        return out

    # ---------- Prompt 注入 ----------

    def build_context_block(
        self, chapter_index: int, present_entities: Sequence[str]
    ) -> str:
        """生成注入 Writer Prompt 的人设与称谓约束块"""
        lines: List[str] = []
        for ent_id in present_entities:
            prof = self.profiles.get(ent_id)
            if not prof:
                continue
            parts = [f"- {prof.name}（{prof.register.value}）"]
            if prof.self_reference:
                parts.append(f"自称「{prof.self_reference}」")
            if prof.verbal_tics:
                parts.append(f"口头禅「{'/'.join(prof.verbal_tics)}」")
            if prof.forbidden_vocabulary:
                parts.append(f"绝不说「{'/'.join(prof.forbidden_vocabulary[:3])}」")
            lines.append("；".join(parts))

        addr_lines: List[str] = []
        present_set = set(present_entities)
        for r in self.address_rules:
            if not r.active_at(chapter_index):
                continue
            if r.speaker_id in present_set and r.target_id in present_set:
                sp = self.profiles.get(r.speaker_id)
                tg = self.profiles.get(r.target_id)
                if sp and tg:
                    addr_lines.append(
                        f"- {sp.name} 当面称 {tg.name} 为「{r.face_to_face}」"
                        + (f"，背后称「{r.behind_back}」" if r.behind_back else "")
                    )

        if not lines and not addr_lines:
            return ""
        block = ["【人设声纹约束】"] + lines
        if addr_lines:
            block += ["【称谓关系约束】"] + addr_lines
        return "\n".join(block)
