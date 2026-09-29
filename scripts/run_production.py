"""
离线全链路实产：用确定性写手把样板书真正生产出来。

没有 API Key 也要能回答这些问题：
- 章节能不能【真的通过】全部闸门，而不是一路 QC_REJECTED？
- 长程引擎在连续几十章上会不会给出有意义的信号（伏笔催收、爽点调度、套路冷却）？
- 断点续产、回滚、导出在真实数据上是否成立？
- 各项阈值（钩子评分线、爽点密度、相似度基线）标定得是否合理？
"""

import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.novel_factory.commerce.power_curve import PowerCurveGuard
from src.novel_factory.commerce.thread_scheduler import StoryThread, ThreadPriority
from src.novel_factory.consistency.foreshadowing import ForeshadowWeight
from src.novel_factory.consistency.persona import PersonaProfile, PersonaRegistry, SpeechRegister
from src.novel_factory.llm.offline_writer import OfflineDeterministicWriter
from src.novel_factory.orchestrator import NovelFactoryOrchestrator
from src.novel_factory.runtime.resume import ResumableProducer
from src.novel_factory.schemas.commit import StateDelta

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_sample_book import FORESHADOWS, THREADS  # noqa: E402

THINGS = [
    "解码器", "微型激光刀", "染血的芯片", "神经接口", "旧工牌",
    "铅封药瓶", "战术目镜", "黄铜钥匙", "半张海图", "锈蚀怀表",
]
PLACES = [
    "酸雨后巷", "霓虹长街", "废弃变电站", "码头栈桥", "地下拍卖行",
    "荒坂医疗塔", "老茶馆", "钟楼", "焚化场", "红灯区天台",
]


def setup(orch: NovelFactoryOrchestrator, outline_path: Path) -> None:
    """装配长程引擎：伏笔台账、故事线、人设声纹、升级曲线"""
    report = orch.load_outline(outline_path, bootstrap=True)
    if not report.passed:
        print(report.format_summary())
        raise SystemExit("大纲不合格，拒绝开工")

    for fid, summary, ch, keywords, weight in FORESHADOWS:
        orch.foreshadow_ledger.plant(
            foreshadow_id=fid, summary=summary, planted_chapter=ch,
            weight=ForeshadowWeight(weight), keywords=keywords,
        )

    for tid, title, prio, intro, close_by in THREADS:
        orch.thread_scheduler.register_thread(StoryThread(
            thread_id=tid, title=title, priority=ThreadPriority(prio),
            introduced_chapter=intro, last_advanced_chapter=intro,
            must_close_by_chapter=close_by,
        ))

    orch.persona_registry.register_profile(PersonaProfile(
        entity_id="char_zero", name="零号", register=SpeechRegister.COLLOQUIAL,
        self_reference="我", forbidden_vocabulary=["综上所述", "窃以为"],
    ))
    orch.persona_registry.register_profile(PersonaProfile(
        entity_id="char_father", name="荒坂垣", register=SpeechRegister.FORMAL,
        self_reference="我", forbidden_vocabulary=["老子", "妈的"],
    ))

    orch.power_guard.set_protagonist("char_zero")
    for aid in ("char_hunter", "char_bailu", "char_father"):
        orch.power_guard.register_antagonist(aid)


def plan_provider(orch: NovelFactoryOrchestrator):
    def _plan(ch: int):
        plan = orch.build_chapter_plan(ch, require_outline=True)
        # 主角战力按阶梯缓慢成长，反派同步登场，供升级节奏引擎评估
        power = 120.0 + (ch // 5) * 45.0
        # 反派同步成长：否则威胁度无从评估（升级节奏引擎会报采样缺失）
        mutations = {"char_zero": {"power_rating": power}}
        if ch <= 10:
            mutations["char_hunter"] = {"power_rating": 460.0 + ch * 6}
        elif ch <= 20:
            mutations["char_bailu"] = {"power_rating": 1200.0 - (ch - 10) * 20}
        else:
            mutations["char_father"] = {"power_rating": 2400.0 - (ch - 20) * 80}
        plan["state_delta"] = StateDelta(chapter_index=ch, entity_mutations=mutations)
        # 时间线：每章推进半天，卷间有跳跃
        orch.calendar.anchor_chapter(
            ch, elapsed_minutes=8 * 60,
            declared_text="次日" if ch % 3 else "三日后",
        )
        # 故事线调度：主线每章推进，支线按建议轮转
        orch.thread_scheduler.advance("t_main", ch)
        for t in orch.thread_scheduler.suggest_threads_for_chapter(ch, slots=1):
            orch.thread_scheduler.advance(t.thread_id, ch)
        return plan

    return _plan


def main():
    ap = argparse.ArgumentParser(description="离线全链路实产")
    ap.add_argument("--workdir", default="sample_book")
    ap.add_argument("--outline", default=None)
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=30)
    ap.add_argument("--governance", action="store_true", default=True)
    args = ap.parse_args()

    wd = Path(args.workdir)
    wd.mkdir(parents=True, exist_ok=True)
    outline = Path(args.outline) if args.outline else wd / "outline.yaml"
    db = str(wd / "book.db")
    journal = wd / "journal.json"

    writer = OfflineDeterministicWriter(
        characters=["零号"], things=THINGS, places=PLACES, seed_salt="neon-rain",
    )
    orch = NovelFactoryOrchestrator(
        project_config_path="project.yaml", db_path=db,
        llm_worker=writer, enforce_governance=args.governance,
    )
    setup(orch, outline)

    print(f"=== 开始生产 第 {args.start}~{args.end} 章 ===")
    t0 = time.time()
    rows = []

    def on_progress(ch, job):
        rows.append((ch, job.status.value, job.word_count, job.cost_cny, job.blockers))
        mark = {"COMPLETED": "OK  ", "QC_REJECTED": "HELD"}.get(job.status.value, job.status.value)
        note = ("  | " + "; ".join(job.blockers)[:70]) if job.blockers else ""
        print(f"  第{ch:>3}章 {mark} {job.word_count:>5}字 ¥{job.cost_cny:.5f}{note}")

    producer = ResumableProducer(
        orch, journal_path=journal, retry_backoff_seconds=0,
        progress_callback=on_progress,
    )
    summary = producer.run(range(args.start, args.end + 1), plan_provider(orch))
    elapsed = time.time() - t0

    print()
    print(summary.format_summary())

    ok = sum(1 for r in rows if r[1] == "COMPLETED")
    print(f"一次通过率: {ok}/{len(rows)} = {ok / max(1, len(rows)):.0%} | 耗时 {elapsed:.1f}s")

    last = args.end
    print("\n=== 全书长程治理巡检 ===")
    head = orch.repo.get_head_commit()
    gov = orch.audit_chapter_governance(
        last, head.full_prose if head else "",
        present_entities=["char_zero", "char_hunter", "char_father"],
    )
    print(gov.format_summary())

    print("\n=== 章末钩子分布 ===")
    hist = orch.hook_enforcer.get_history()
    from collections import Counter
    dist = Counter(e.strength.value for e in hist.values())
    for k in ("STRONG", "SOLID", "WEAK", "DEAD"):
        print(f"  {k:<7}{dist.get(k, 0):>3} 章")
    if hist:
        print(f"  平均分 {sum(e.score for e in hist.values()) / len(hist):.2f}")

    print("\n=== 爽点密度曲线 ===")
    print(orch.payoff_meter.render_curve(width=min(60, last)))

    print("\n=== 伏笔台账 ===")
    for r in orch.foreshadow_ledger.list_all():
        state = r.status.value
        print(f"  [{state:<10}] {r.foreshadow_id:<12} 埋于第{r.planted_chapter:>2}章 "
              f"截止第{r.payoff_deadline_chapter:>3}章  {r.summary[:26]}")

    print("\n=== 财务 ===")
    book = orch.cost_auditor.audit_book_total()
    print(f"  总成本 ¥{book.total_cost_cny:.4f} | 单章均价 ¥{book.avg_cost_per_chapter:.5f} "
          f"| 缓存节约 ¥{book.total_cny_saved_by_caching:.4f}")
    print(f"  外推 1000 章: ¥{book.avg_cost_per_chapter * 1000:.2f}（离线写手计价，仅验证链路）")

    print("\n=== 导出 ===")
    out = wd / "exports"
    n_txt = orch.exporter.export_to_txt(str(out / "manuscript.txt"))
    n_md = orch.exporter.export_to_markdown(str(out / "full_book.md"), book_title="霓虹雨夜：断线者")
    n_sft = orch.exporter.export_to_jsonl_dataset(str(out / "sft.jsonl"))
    n_wb = orch.exporter.export_world_bible(str(out / "world_bible.md"))
    print(f"  投稿TXT {n_txt:,} 字符 | Markdown {n_md:,} 字符 | SFT {n_sft} 条 | 设定集 {n_wb:,} 字符")

    chapters = orch.exporter.get_all_chapters()
    total_words = sum(c["word_count"] for c in chapters)
    print(f"  成书 {len(chapters)} 章 / {total_words:,} 字")

    orch.close()

    (wd / "run_report.json").write_text(json.dumps({
        "chapters": len(chapters), "total_words": total_words,
        "pass_rate": ok / max(1, len(rows)),
        "hook_distribution": dict(dist),
        "cost_cny": book.total_cost_cny,
        "elapsed_seconds": round(elapsed, 1),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
