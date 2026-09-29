"""
百章级生产压力测试 (Long-Haul Stress Test)

目的不是测"能不能跑"，而是回答长篇生产真正的工程问题：
1. 长程引擎在 100+ 章规模下是否线性退化（内存、SQLite、SimHash 索引）；
2. 断点续产在中途崩溃后能否精确恢复；
3. 治理引擎（伏笔/爽点/钩子/升级）是否在长跨度上给出有意义的信号；
4. 单章成本与耗时是否稳定，可否据此外推全书预算。

用法：
    python scripts/stress_test.py --chapters 100
    python scripts/stress_test.py --chapters 300 --crash-at 150
"""

import argparse
import random
import time
import tracemalloc
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.novel_factory.commerce.power_curve import PowerCurveGuard
from src.novel_factory.commerce.thread_scheduler import StoryThread, ThreadPriority
from src.novel_factory.consistency.foreshadowing import ForeshadowWeight
from src.novel_factory.orchestrator import NovelFactoryOrchestrator
from src.novel_factory.runtime.resume import ProductionJournal, ResumableProducer
from src.novel_factory.schemas.beat import BeatContract, CameraAngle, MicroEvent, PacingType
from src.novel_factory.schemas.commit import StateDelta


# 六种风格化段落模板，保证章节间有真实差异（否则 SimHash 会合理地全量报警）
TEMPLATES = [
    "{who}的指尖停在{thing}上，{part}泛白。\n远处的{place}在雨里扭曲成一片模糊。\n"
    "他心里飞快盘算着退路。\n围观的人群同时倒吸一口凉气。\n",
    "{place}的空气里浮着铁锈味。\n{who}把{thing}收回袖中，动作没有一丝停顿。\n"
    "他知道，这一步踏出去就没有回头路。\n街角的灯忽明忽暗。\n",
    "{who}抬眼看向{place}的方向，瞳孔微微收缩。\n{thing}在他掌心发烫。\n"
    "四周安静得能听见自己的心跳。\n有人在后排失手打翻了茶盏。\n",
    "雷声滚过{place}上空。\n{who}压低身形，{part}紧贴着湿冷的石墙。\n"
    "他数着对方的脚步声，一步，两步。\n{thing}的微光映亮了半张脸。\n",
    "{place}的长街上空无一人。\n{who}将{thing}举到眼前，仔细端详着那道裂痕。\n"
    "他忽然明白了什么，喉结滚动了一下。\n身后传来一声极轻的响动。\n",
    "{who}把{thing}按在桌面上，指节抵着桌沿。\n{place}里所有的目光都聚了过来。\n"
    "他不急不缓地开口，声音压得很低。\n人群中爆发出一阵哗然。\n",
]

# 词池必须足够大，否则 100 章之间会产生真实的高度雷同——
# 那样测的就不是系统，而是 mock 生成器的贫乏。
WHO = ["零号", "陈九", "苏漓", "老秤", "白鹭", "沈砚", "裴照", "阿蛮",
       "雪奴", "楼三", "祁烬", "温桑"]
THING = ["解码器", "断刃", "黄铜钥匙", "染血的信封", "神经接口", "青玉扳指",
         "半张海图", "锈蚀怀表", "骨制哨子", "褪色符纸", "铅封药瓶", "碎裂面具"]
PLACE = ["霓虹长街", "地下拍卖行", "旧码头", "钟楼", "雾巷", "废弃车站",
         "盐仓", "红灯区天台", "地脉裂口", "老茶馆", "船坞栈桥", "焚化场"]
PART = ["指节", "腕骨", "肩背", "掌心", "眉骨", "后颈", "小臂", "喉结"]
MOOD = ["冷", "灼热", "潮湿", "刺骨", "黏腻", "干燥", "腥甜", "沉闷"]
SOUND = ["汽笛", "雨点", "钟声", "低频嗡鸣", "脚步", "犬吠", "纺机声", "风铃"]

HOOKS = [
    "\n一道陌生的身影从雨里缓缓走出。",
    "\n「原来你一直都是他们的人？」",
    "\n刀锋已经抵住了他的咽喉。",
    "\n他忽然意识到，那个人根本没有死。",
    "\n下一刻，整条街的灯同时熄灭。",
]


def make_writer(rng: random.Random, target_chars: int = 620):
    """构造一个产出足量、且章节间有真实差异的确定性 Mock 作者"""

    def writer(system_prompt: str, user_prompt: str) -> str:
        blocks = []
        length = 0
        while length < target_chars:
            tpl = rng.choice(TEMPLATES)
            text = tpl.format(
                who=rng.choice(WHO), thing=rng.choice(THING),
                place=rng.choice(PLACE), part=rng.choice(PART),
            )
            # 追加一句随机感官细节，进一步拉开章节之间的指纹距离
            text += (
                f"空气是{rng.choice(MOOD)}的，远处传来{rng.choice(SOUND)}。\n"
            )
            blocks.append(text)
            length += len(text)
        return "".join(blocks) + rng.choice(HOOKS)

    return writer


def build_orchestrator(db_path: str, seed: int) -> NovelFactoryOrchestrator:
    rng = random.Random(seed)
    orch = NovelFactoryOrchestrator(
        db_path=db_path,
        llm_worker=make_writer(rng, target_chars=620),
        enforce_governance=False,       # 压测关注吞吐与退化，不做硬否决
        max_cost_per_chapter=100.0,
    )
    orch.contract_auditor.enforce_camera_coverage = False

    # 注册角色（经统一入口，同步写入图谱与事件库）
    for i, name in enumerate(WHO):
        orch.register_entity(f"char_{i}", "CHARACTER", name, created_chapter=1,
                             initial_payload={"power_rating": 100.0})
    orch.power_guard.set_protagonist("char_0")
    orch.power_guard.register_antagonist("char_1")

    # 注册故事线
    orch.thread_scheduler.register_thread(StoryThread(
        thread_id="t_main", title="复仇主线", priority=ThreadPriority.MAIN))
    orch.thread_scheduler.register_thread(StoryThread(
        thread_id="t_romance", title="感情线", priority=ThreadPriority.ROMANCE))
    return orch


def plan_for(orch: NovelFactoryOrchestrator, ch: int):
    beats = []
    for bi, pacing in enumerate(
        [PacingType.BUILD_UP, PacingType.COGNITIVE_GAP,
         PacingType.CATHARSIS_PAYOFF, PacingType.CLIFFHANGER_HOOK], start=1
    ):
        beats.append(BeatContract(
            beat_id=f"ch{ch:04d}_b{bi}",
            chapter_index=ch, beat_index=bi,
            target_words=650, word_tolerance_ratio=0.5,
            pacing_type=pacing,
            required_camera_angles=[CameraAngle.POV],
            characters_present=["char_0", "char_1"],
            location_id="loc_city",
            micro_events=[MicroEvent(event_id=f"e{ch}_{bi}", description="推进主线冲突")],
        ))
    return {
        "title": f"第 {ch} 章",
        "beat_contracts": beats,
        "lore_entries": [],
        "state_delta": StateDelta(
            chapter_index=ch,
            entity_mutations={"char_0": {"power_rating": 100.0 + ch * 2.0}},
        ),
    }


def run(chapters: int, workdir: Path, crash_at: int | None, seed: int) -> int:
    workdir.mkdir(parents=True, exist_ok=True)
    db = str(workdir / "stress.db")
    journal = workdir / "stress_journal.json"

    print(f"=== 压力测试: {chapters} 章 | 工作目录 {workdir} ===")
    tracemalloc.start()
    t0 = time.time()

    orch = build_orchestrator(db, seed)

    # 每 10 章埋一条伏笔，模拟真实长篇的伏笔密度
    for ch in range(1, chapters + 1, 10):
        orch.foreshadow_ledger.plant(
            foreshadow_id=f"fs_{ch}", summary=f"第{ch}章埋下的线索",
            planted_chapter=ch,
            weight=ForeshadowWeight.ARC_LEVEL if ch % 30 else ForeshadowWeight.MAIN_LINE,
            keywords=[f"线索{ch}"],
        )

    per_chapter_ms = []

    def on_progress(ch, job):
        if ch % 20 == 0:
            cur, peak = tracemalloc.get_traced_memory()
            print(f"  第 {ch:>4} 章 | {job.status.value:<12} | "
                  f"累计 {time.time() - t0:6.1f}s | 内存 {cur / 1e6:6.1f}MB")

    producer = ResumableProducer(
        orch, journal_path=journal, retry_backoff_seconds=0,
        progress_callback=on_progress,
    )

    all_chapters = list(range(1, chapters + 1))

    if crash_at:
        print(f"\n--- 阶段一：生产至第 {crash_at} 章后模拟进程崩溃 ---")
        producer.run(all_chapters[:crash_at], lambda c: plan_for(orch, c))
        orch.close()

        print("--- 阶段二：全新进程从断点恢复 ---")
        orch = build_orchestrator(db, seed)
        producer = ResumableProducer(
            orch, journal_path=journal, retry_backoff_seconds=0,
            progress_callback=on_progress,
        )
        resume_at = producer.resume_point(all_chapters)
        completed = sum(
            1 for j in producer.journal.jobs.values() if j.status.value == "COMPLETED"
        )
        print(f"    阶段一成功提交 {completed} 章 | 恢复点: 第 {resume_at} 章")
        expected = completed + 1
        if resume_at != expected:
            print(f"    [FAIL] 恢复点错误，期望第 {expected} 章（首个未完成章）")
            return 1
        print(f"    [OK] 断点恢复正确，不会重复生产已完成的 {completed} 章")

    summary = producer.run(all_chapters, lambda c: plan_for(orch, c))
    elapsed = time.time() - t0

    # ---- 数据完整性抽查（这些曾经都是真实事故）----
    print("\n===== 数据完整性抽查 =====")
    log = orch.repo.get_commit_log(limit=chapters + 10)
    chapter_ids = [c["chapter_index"] for c in log]
    dup = len(chapter_ids) != len(set(chapter_ids))
    print(f"提交日志章节数 {len(chapter_ids)} | 重复章节: {'有(FAIL)' if dup else '无'}")
    exported = orch.exporter.get_all_chapters()
    print(f"导出可见章节数 {len(exported)} | 与日志一致: {len(exported) == len(set(chapter_ids))}")

    mid = max(1, chapters // 2)
    orch.repo.checkout_chapter(mid)
    recoverable = len(orch.repo.list_orphaned_commits())
    print(f"回滚至第 {mid} 章 -> 可恢复的孤立提交 {recoverable} 条（非破坏性回滚）")
    if recoverable:
        orch.repo.restore_orphaned_commit(
            orch.repo.list_orphaned_commits()[-1]["commit_id"]
        )
        print("已成功恢复一条被回滚的提交")

    cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print("\n" + summary.format_summary())

    # ---- 长程引擎在规模下的表现 ----
    print("\n===== 长程引擎巡检 (末章) =====")
    last = chapters
    hook_trend = orch.hook_enforcer.analyze_trend(window=30)
    print(f"章末钩子: 近30章均值 {hook_trend.avg_score} | 连续弱钩 {hook_trend.weak_streak}")
    for a in hook_trend.alerts:
        print(f"  ! {a}")

    density = orch.payoff_meter.analyze(last)
    print(density.format_summary())

    fs = orch.foreshadow_ledger.audit_chapter(last)
    print(f"伏笔台账: 未回收 {fs.open_count} 条 | 超期 {len(fs.overdue)} 条 | "
          f"记忆过期 {len(fs.stale)} 条")

    power = orch.power_guard.check(last)
    print(power.format_summary())

    threads = orch.thread_scheduler.check(last)
    print(f"多线调度: 断更 {len(threads.starved)} 条")

    baseline = orch.simhash_index.current_baseline()
    if baseline is not None:
        print(f"跨章雷同: 本书相似度基线(中位数) {baseline:.1%} | "
              f"当前判定线 {orch.simhash_index._effective_similarity_threshold():.1%}")
        print("  注：压测 mock 仅使用有限句式模板，章节间天然高度雷同，"
              "此处告警反映的是生成器的贫乏而非系统误判。")

    # ---- 性能与成本外推 ----
    book = orch.cost_auditor.audit_book_total()
    per_ch = elapsed / max(1, chapters)
    print("\n===== 性能与成本 =====")
    print(f"总耗时 {elapsed:.1f}s | 单章均耗时 {per_ch * 1000:.0f}ms")
    print(f"峰值内存 {peak / 1e6:.1f}MB")
    print(f"总成本 ¥{book.total_cost_cny:.4f} | 单章均价 ¥{book.avg_cost_per_chapter:.5f}")
    print(f"外推 1000 章预算: ¥{book.avg_cost_per_chapter * 1000:.2f}（mock 计价，仅验证链路）")

    db_size = Path(db).stat().st_size / 1e6 if Path(db).exists() else 0
    print(f"SQLite 体积 {db_size:.1f}MB | 单章均 {db_size / max(1, chapters) * 1000:.1f}KB")

    orch.close()

    if dup:
        print("\n[FAIL] 版本库中出现重复章节")
        orch.close()
        return 1

    failed = summary.failed
    if failed:
        print(f"\n[FAIL] {failed} 章生产失败")
        return 1
    print("\n[OK] 压力测试通过")
    return 0


def main():
    ap = argparse.ArgumentParser(description="百章级生产压力测试")
    ap.add_argument("--chapters", type=int, default=100)
    ap.add_argument("--workdir", default=".stress")
    ap.add_argument("--crash-at", type=int, default=None,
                    help="在该章后模拟崩溃，验证断点续产")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    raise SystemExit(run(args.chapters, Path(args.workdir), args.crash_at, args.seed))


if __name__ == "__main__":
    main()
