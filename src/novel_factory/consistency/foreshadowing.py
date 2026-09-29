"""
Foreshadow Ledger - 伏笔 / 契诃夫之枪全生命周期台账

长篇网文读者最不能忍的三件事：
  「埋了忘收」—— 挂在墙上的枪从头到尾没响；
  「收了没埋」—— 突然掏出一个从未提过的救命道具（Deus ex machina）；
  「收得太晚」—— 三百章前的悬念早被读者遗忘，回收时毫无爽感。

本模块以 SQLite 持久化台账形式，强制追踪每一条伏笔的：
埋设章节 → 提醒(复述)章节 → 承诺回收窗口 → 实际回收章节。
并在每章生产前吐出「本章应当回收/应当复述」的待办清单，
在每章生产后审计是否出现「凭空回收」的失控伏笔。
"""

from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Sequence


class ForeshadowStatus(str, Enum):
    PLANTED = "PLANTED"          # 已埋设，等待回收
    REINFORCED = "REINFORCED"    # 已复述强化（读者记忆刷新）
    PAID_OFF = "PAID_OFF"        # 已回收兑现
    ABANDONED = "ABANDONED"      # 主动废弃（需在结局前显式声明）
    OVERDUE = "OVERDUE"          # 超出承诺窗口仍未回收


class ForeshadowWeight(str, Enum):
    """伏笔量级决定容忍的回收窗口与超期惩罚力度"""
    MAIN_LINE = "MAIN_LINE"      # 主线级：身世、终极反派、金手指来历
    ARC_LEVEL = "ARC_LEVEL"      # 卷级：本卷核心谜题
    DETAIL = "DETAIL"            # 细节级：一句闲笔、一件小道具


# 各量级伏笔的默认最长回收窗口（章）与记忆保鲜期（章）
DEFAULT_PAYOFF_WINDOW: Dict[ForeshadowWeight, int] = {
    ForeshadowWeight.MAIN_LINE: 400,
    ForeshadowWeight.ARC_LEVEL: 80,
    ForeshadowWeight.DETAIL: 25,
}
DEFAULT_MEMORY_FRESHNESS: Dict[ForeshadowWeight, int] = {
    ForeshadowWeight.MAIN_LINE: 60,
    ForeshadowWeight.ARC_LEVEL: 30,
    ForeshadowWeight.DETAIL: 15,
}


@dataclass
class ForeshadowRecord:
    """单条伏笔台账记录"""
    foreshadow_id: str
    summary: str                              # 伏笔内容摘要
    weight: ForeshadowWeight = ForeshadowWeight.DETAIL
    planted_chapter: int = 1
    status: ForeshadowStatus = ForeshadowStatus.PLANTED
    payoff_deadline_chapter: Optional[int] = None
    paid_off_chapter: Optional[int] = None
    last_mentioned_chapter: Optional[int] = None
    keywords: List[str] = field(default_factory=list)   # 用于在正文中检出该伏笔
    planted_evidence: str = ""                          # 埋设时的原文片段
    payoff_evidence: str = ""
    related_entities: List[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "foreshadow_id": self.foreshadow_id,
            "summary": self.summary,
            "weight": self.weight.value,
            "planted_chapter": self.planted_chapter,
            "status": self.status.value,
            "payoff_deadline_chapter": self.payoff_deadline_chapter,
            "paid_off_chapter": self.paid_off_chapter,
            "last_mentioned_chapter": self.last_mentioned_chapter,
            "keywords": self.keywords,
            "related_entities": self.related_entities,
            "notes": self.notes,
        }


@dataclass
class ForeshadowReport:
    """某一章的伏笔健康度报告"""
    chapter_index: int
    due_soon: List[ForeshadowRecord] = field(default_factory=list)     # 临近截止，应尽快回收
    overdue: List[ForeshadowRecord] = field(default_factory=list)      # 已超期违约
    stale: List[ForeshadowRecord] = field(default_factory=list)        # 太久没提，读者已遗忘
    unplanted_payoffs: List[str] = field(default_factory=list)         # 凭空回收（未埋先收）
    open_count: int = 0

    @property
    def healthy(self) -> bool:
        return not self.overdue and not self.unplanted_payoffs

    def format_summary(self) -> str:
        lines = [
            f"[伏笔台账] 第{self.chapter_index}章 | 未回收 {self.open_count} 条 | "
            f"{'HEALTHY' if self.healthy else 'AT RISK'}"
        ]
        for r in self.overdue:
            lines.append(
                f"  - [超期违约] {r.foreshadow_id} 「{r.summary}」"
                f" 第{r.planted_chapter}章埋设，承诺第{r.payoff_deadline_chapter}章前回收"
            )
        for r in self.due_soon:
            lines.append(
                f"  - [临近截止] {r.foreshadow_id} 「{r.summary}」"
                f" 截止第{r.payoff_deadline_chapter}章"
            )
        for r in self.stale:
            lines.append(
                f"  - [记忆过期] {r.foreshadow_id} 「{r.summary}」"
                f" 已 {self.chapter_index - (r.last_mentioned_chapter or r.planted_chapter)} 章未复述，建议插入回忆锚点"
            )
        for s in self.unplanted_payoffs:
            lines.append(f"  - [凭空回收] 正文出现未经埋设的关键要素: {s}")
        return "\n".join(lines)

    def to_writer_directives(self) -> List[str]:
        """转换为可直接注入 Writer Prompt 的强制指令"""
        directives: List[str] = []
        for r in self.overdue:
            directives.append(
                f"【必须回收伏笔】「{r.summary}」已超出承诺回收章节，本章必须给出明确兑现。"
            )
        for r in self.due_soon:
            directives.append(
                f"【优先回收伏笔】「{r.summary}」回收窗口即将关闭，本章应推进其兑现。"
            )
        for r in self.stale:
            directives.append(
                f"【复述提醒】「{r.summary}」已久未提及，本章需以自然方式（角色回想/对话带过）重新点一次，"
                f"刷新读者记忆，严禁大段倒叙。"
            )
        return directives


class ForeshadowLedger:
    """伏笔全生命周期台账（SQLite 持久化）"""

    def __init__(self, db_path: Optional[str] = ":memory:"):
        self.conn = sqlite3.connect(db_path or ":memory:")
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self) -> None:
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS foreshadows (
                    foreshadow_id TEXT PRIMARY KEY,
                    summary TEXT NOT NULL,
                    weight TEXT NOT NULL,
                    planted_chapter INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    payoff_deadline_chapter INTEGER,
                    paid_off_chapter INTEGER,
                    last_mentioned_chapter INTEGER,
                    keywords_json TEXT DEFAULT '[]',
                    planted_evidence TEXT DEFAULT '',
                    payoff_evidence TEXT DEFAULT '',
                    related_entities_json TEXT DEFAULT '[]',
                    notes TEXT DEFAULT ''
                )
            """)
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_foreshadow_status
                ON foreshadows (status, payoff_deadline_chapter)
            """)

    # ---------- 写入 ----------

    def plant(
        self,
        foreshadow_id: str,
        summary: str,
        planted_chapter: int,
        weight: ForeshadowWeight = ForeshadowWeight.DETAIL,
        keywords: Optional[Sequence[str]] = None,
        payoff_deadline_chapter: Optional[int] = None,
        planted_evidence: str = "",
        related_entities: Optional[Sequence[str]] = None,
        notes: str = "",
    ) -> ForeshadowRecord:
        """埋设一条新伏笔，自动按量级推导回收截止章节"""
        deadline = payoff_deadline_chapter or (
            planted_chapter + DEFAULT_PAYOFF_WINDOW[weight]
        )
        rec = ForeshadowRecord(
            foreshadow_id=foreshadow_id,
            summary=summary,
            weight=weight,
            planted_chapter=planted_chapter,
            status=ForeshadowStatus.PLANTED,
            payoff_deadline_chapter=deadline,
            last_mentioned_chapter=planted_chapter,
            keywords=list(keywords or []),
            planted_evidence=planted_evidence,
            related_entities=list(related_entities or []),
            notes=notes,
        )
        self._upsert(rec)
        return rec

    def reinforce(self, foreshadow_id: str, chapter_index: int) -> bool:
        """在某章复述强化伏笔，刷新读者记忆时钟"""
        rec = self.get(foreshadow_id)
        if not rec or rec.status in (ForeshadowStatus.PAID_OFF, ForeshadowStatus.ABANDONED):
            return False
        rec.last_mentioned_chapter = chapter_index
        rec.status = ForeshadowStatus.REINFORCED
        self._upsert(rec)
        return True

    def pay_off(self, foreshadow_id: str, chapter_index: int, evidence: str = "") -> bool:
        """回收兑现伏笔"""
        rec = self.get(foreshadow_id)
        if not rec:
            return False
        rec.status = ForeshadowStatus.PAID_OFF
        rec.paid_off_chapter = chapter_index
        rec.last_mentioned_chapter = chapter_index
        rec.payoff_evidence = evidence
        self._upsert(rec)
        return True

    def abandon(self, foreshadow_id: str, reason: str = "") -> bool:
        """主动废弃伏笔（需要显式决策，避免悄无声息的烂尾）"""
        rec = self.get(foreshadow_id)
        if not rec:
            return False
        rec.status = ForeshadowStatus.ABANDONED
        rec.notes = (rec.notes + " | 废弃原因: " + reason).strip(" |")
        self._upsert(rec)
        return True

    def _upsert(self, rec: ForeshadowRecord) -> None:
        with self.conn:
            self.conn.execute("""
                INSERT OR REPLACE INTO foreshadows
                (foreshadow_id, summary, weight, planted_chapter, status,
                 payoff_deadline_chapter, paid_off_chapter, last_mentioned_chapter,
                 keywords_json, planted_evidence, payoff_evidence, related_entities_json, notes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                rec.foreshadow_id, rec.summary, rec.weight.value, rec.planted_chapter,
                rec.status.value, rec.payoff_deadline_chapter, rec.paid_off_chapter,
                rec.last_mentioned_chapter, json.dumps(rec.keywords, ensure_ascii=False),
                rec.planted_evidence, rec.payoff_evidence,
                json.dumps(rec.related_entities, ensure_ascii=False), rec.notes
            ))

    # ---------- 读取 ----------

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> ForeshadowRecord:
        return ForeshadowRecord(
            foreshadow_id=row["foreshadow_id"],
            summary=row["summary"],
            weight=ForeshadowWeight(row["weight"]),
            planted_chapter=row["planted_chapter"],
            status=ForeshadowStatus(row["status"]),
            payoff_deadline_chapter=row["payoff_deadline_chapter"],
            paid_off_chapter=row["paid_off_chapter"],
            last_mentioned_chapter=row["last_mentioned_chapter"],
            keywords=json.loads(row["keywords_json"]),
            planted_evidence=row["planted_evidence"],
            payoff_evidence=row["payoff_evidence"],
            related_entities=json.loads(row["related_entities_json"]),
            notes=row["notes"],
        )

    def get(self, foreshadow_id: str) -> Optional[ForeshadowRecord]:
        row = self.conn.execute(
            "SELECT * FROM foreshadows WHERE foreshadow_id = ?", (foreshadow_id,)
        ).fetchone()
        return self._row_to_record(row) if row else None

    def list_open(self, as_of_chapter: Optional[int] = None) -> List[ForeshadowRecord]:
        """列出所有尚未回收/废弃的活跃伏笔"""
        rows = self.conn.execute(
            "SELECT * FROM foreshadows WHERE status IN (?, ?, ?)",
            (ForeshadowStatus.PLANTED.value, ForeshadowStatus.REINFORCED.value,
             ForeshadowStatus.OVERDUE.value)
        ).fetchall()
        recs = [self._row_to_record(r) for r in rows]
        if as_of_chapter is not None:
            recs = [r for r in recs if r.planted_chapter <= as_of_chapter]
        return sorted(recs, key=lambda r: (r.payoff_deadline_chapter or 10**9))

    def list_all(self) -> List[ForeshadowRecord]:
        rows = self.conn.execute("SELECT * FROM foreshadows ORDER BY planted_chapter").fetchall()
        return [self._row_to_record(r) for r in rows]

    # ---------- 审计 ----------

    def audit_chapter(
        self,
        chapter_index: int,
        due_soon_window: int = 10,
        chapter_text: Optional[str] = None,
        declared_payoff_keywords: Optional[Sequence[str]] = None,
    ) -> ForeshadowReport:
        """
        对指定章节做伏笔健康度审计。

        chapter_text 若提供，则额外检测「凭空回收」：
        正文中出现了被登记为关键要素、但当前并无任何已埋设伏笔覆盖的名词。
        """
        report = ForeshadowReport(chapter_index=chapter_index)
        open_recs = self.list_open(as_of_chapter=chapter_index)
        report.open_count = len(open_recs)

        for rec in open_recs:
            deadline = rec.payoff_deadline_chapter
            last_seen = rec.last_mentioned_chapter or rec.planted_chapter
            freshness = DEFAULT_MEMORY_FRESHNESS[rec.weight]

            if deadline is not None and chapter_index > deadline:
                rec.status = ForeshadowStatus.OVERDUE
                self._upsert(rec)
                report.overdue.append(rec)
            elif deadline is not None and (deadline - chapter_index) <= due_soon_window:
                report.due_soon.append(rec)

            if (chapter_index - last_seen) > freshness and rec not in report.overdue:
                report.stale.append(rec)

        if chapter_text and declared_payoff_keywords:
            known_kw = set()
            for rec in self.list_all():
                known_kw.update(rec.keywords)
            for kw in declared_payoff_keywords:
                if kw in chapter_text and kw not in known_kw:
                    report.unplanted_payoffs.append(kw)

        return report

    def detect_mentions(self, chapter_text: str) -> List[str]:
        """扫描正文，返回本章实际提及到的伏笔 ID（用于自动刷新记忆时钟）"""
        mentioned: List[str] = []
        for rec in self.list_open():
            if any(kw and kw in chapter_text for kw in rec.keywords):
                mentioned.append(rec.foreshadow_id)
        return mentioned

    def auto_reinforce_from_text(self, chapter_index: int, chapter_text: str) -> int:
        """自动依据正文提及情况刷新伏笔记忆时钟，返回刷新条数"""
        ids = self.detect_mentions(chapter_text)
        for fid in ids:
            self.reinforce(fid, chapter_index)
        return len(ids)

    def close(self) -> None:
        self.conn.close()
