"""
Novel Factory Master CLI - 工业化小说生产车间终端总控台

命令全集：
1. demo     : 黄金三章端到端试产演示（含质检闸门与时空回滚验证）
2. produce  : 读取 project.yaml 批量自动化生产章节（支持断点续产）
3. status   : 项目配置、法则体系、提交树与财务审计总览
4. rollback : 一键时空回滚与剧情分支管理
5. export   : 导出投稿 TXT / 全书 Markdown / SFT 数据集 / 世界观设定集
6. inspect  : 审查章节的质检指标、SimHash 指纹与词频疲劳矩阵
7. govern   : 长程治理巡检（伏笔台账 / 爽点曲线 / 支线甘特图 / 升级曲线）
8. resume   : 查看与操作断点续产日志
9. workbench: 人机协同断点工作台，查看并解除生产断点
10. outline : 全书大纲脚手架生成、层级校验与查看
"""

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable, Dict, List, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.novel_factory.cli.workbench import HITLBreakpointManager, HumanDecision, WorkbenchDashboard
from src.novel_factory.config.loader import ProjectConfigLoader
from src.novel_factory.core.db import ConcurrentProductionError
from src.novel_factory.export.manuscript_exporter import ManuscriptExporter
from src.novel_factory.orchestrator import NovelFactoryOrchestrator
from src.novel_factory.runtime.resume import JobStatus, ProductionJournal, ResumableProducer
from src.novel_factory.schemas.beat import BeatContract, CameraAngle, MicroEvent, PacingType
from src.novel_factory.schemas.commit import StateDelta
from src.novel_factory.schemas.entity import LoreEntry

console = Console(force_terminal=True, legacy_windows=False)

DEFAULT_DB = "novel_master.db"


def print_banner():
    console.print(Panel.fit(
        "[bold cyan]Novel Factory Enterprise v5.0[/bold cyan]\n"
        "[dim]工业级全题材长篇小说智能制造流水线 | Antigravity 本地工作台[/dim]",
        border_style="cyan"
    ))


def _build_orchestrator(args, db_path: str) -> NovelFactoryOrchestrator:
    """按命令行参数装配生产线（真实 Provider 或离线 Mock）"""
    provider_type = getattr(args, "provider", "mock") or "mock"
    project = getattr(args, "project", "project.yaml")
    cfg_path = project if Path(project).exists() else None

    common = dict(
        enforce_governance=not getattr(args, "no_governance", False),
        acquire_write_lock=getattr(args, "lock", False),
        force_write_lock=getattr(args, "force_lock", False),
    )
    if provider_type == "mock":
        return NovelFactoryOrchestrator(
            project_config_path=cfg_path, db_path=db_path, **common
        )
    return NovelFactoryOrchestrator.from_provider(
        provider_type=provider_type,
        model_name=getattr(args, "model", "gemini-3.8-flash"),
        api_key=getattr(args, "api_key", None),
        base_url=getattr(args, "base_url", None),
        config_path=cfg_path,
        db_path=db_path,
        **common,
    )


# ============================ demo ============================

def cmd_demo(args):
    """端到端黄金三章试产演示与时空回滚"""
    print_banner()
    console.print("[bold yellow]>>> 启动样板书 [霓虹雨夜：断线黑客的复仇纪元] 黄金三章试产流水线...[/bold yellow]\n")

    beat_prose = {
        (1, 1): (
            "酸雨泼洒在阴暗的后巷青石地面上，腐蚀出白色的泡沫。\n"
            "零号靠在生锈的铁门后，指尖的神经解码器红灯急促闪烁。\n"
            "后方的机械脚步声在十步外停住。\n"
            "他心里迅速盘算着退路，喉结无声地滚动了一下。\n"
            "「找到你了，老鼠。」荒坂猎犬的电子合成音带着金属刮擦声。"
        ),
        (1, 2): (
            "整条街道的霓虹在雨幕里扭曲成一片血红。\n"
            "巷口的流浪汉抬起头，瞳孔骤然收缩，连滚带爬地躲进垃圾堆。\n"
            "零号把颈后那道旧疤按在冰冷的铁门上，疼痛让他清醒了半分。\n"
            "他知道自己只剩下一次机会。\n"
            "一道陌生的身影从雨里缓缓走出。"
        ),
        (2, 1): (
            "变电箱的铁皮被撬开一道缝，铜绿色的接口暴露在雨里。\n"
            "零号把解码器插进去，指节因为用力而泛白。\n"
            "荒坂猎犬的战术灯扫过巷子，光柱在积水上碎成一片。\n"
            "他屏住呼吸，心里默数着对方义体过载的秒数。\n"
            "三，二，一。"
        ),
        (2, 2): (
            "整片街区的照明在同一瞬间熄灭。\n"
            "远处酒馆里的人群同时惊呼出声，杯盏摔碎了一地。\n"
            "黑暗里只剩下解码器屏幕的幽蓝微光，映着零号紧绷的下颌。\n"
            "「你以为断电就能跑？」猎犬的声音从正后方逼近。\n"
            "屏幕上跳出一行不属于任何已知协议的乱码。"
        ),
        (3, 1): (
            "暗网论坛的数据洪流在视网膜投影上疯狂滚动。\n"
            "零号盯着那枚从猎犬颈后取下的芯片，指尖微微发抖。\n"
            "加密层在第七次冲击后彻底崩解。\n"
            "他心里那个盘桓了三年的猜测，此刻终于有了答案。\n"
            "窗外的城市在酸雨中亮起大片广告灯牌。"
        ),
        (3, 2): (
            "论坛里成千上万条留言在十秒内涌出，整个板块陷入哗然。\n"
            "有人截图，有人删帖，更多的人在疯狂转发那串编号。\n"
            "零号摘下投影目镜，长长吐出一口气。\n"
            "「原来当年下令的人，一直坐在那张椅子上。」\n"
            "他缓缓抬起头，瞳孔里映出荒坂大厦顶层那盏未曾熄灭的灯。"
        ),
    }

    def smart_writer(sys_p: str, user_p: str) -> str:
        if "局部微创打补丁任务" in user_p or "修复" in user_p:
            return (
                "零号没有回答，只是将微型激光刀向前递了半寸。\n"
                "刺啦一声，皮质手套被割开一道焦黑的裂口。\n"
                "中间人的瞳孔猛地收缩，按在桌面的五指僵硬得泛白。\n"
                "围观的酒客同时后退半步，有人手里的玻璃杯摔碎在地。\n"
                "远处的霓虹招牌在酸雨里明灭，照得整条巷子忽明忽暗。\n"
                "他心里清楚，这一刀不能再往前送了。\n"
                "「下一句话，想清楚再说。」"
            )
        # 从 Prompt 中解析节拍编号，模拟一个真正按契约分镜写作的作者
        m = re.search(r"节拍编号:\s*ch0?(\d+)_b0?(\d+)", user_p)
        key = (int(m.group(1)), int(m.group(2))) if m else (1, 1)
        return beat_prose.get(key, beat_prose[(1, 1)])

    project_cfg = Path(getattr(args, "project", "project.yaml"))
    orchestrator = NovelFactoryOrchestrator.from_project_config(
        config_path=str(project_cfg) if project_cfg.exists() else None,
        db_path=":memory:",
        llm_worker=smart_writer
    )
    # 演示用：关闭治理硬闸门，以便完整展示全链路（真实生产建议开启）
    orchestrator.enforce_governance = False

    orchestrator.register_entity(
        entity_id="char_zero", entity_type="CHARACTER", name="零号",
        created_chapter=1, initial_payload={"tier_or_rank": "初级民用植入", "power_rating": 120.0}
    )
    orchestrator.register_entity(
        entity_id="char_hunter", entity_type="CHARACTER", name="荒坂猎犬",
        created_chapter=1, initial_payload={"tier_or_rank": "军规级战术改装", "power_rating": 450.0}
    )

    # 长程引擎初始化：让演示体现真实的治理能力
    orchestrator.power_guard.set_protagonist("char_zero")
    orchestrator.power_guard.register_antagonist("char_hunter")
    orchestrator.foreshadow_ledger.plant(
        foreshadow_id="fs_chip", summary="零号颈后那枚来历不明的军规级芯片",
        planted_chapter=1, keywords=["芯片", "颈后"],
    )

    lore_entries = [
        LoreEntry(
            entry_id="lore_acid_rain", entity_type="SYSTEM_RULE", name="工业酸雨腐蚀法则",
            content="雨水中含有强酸性化学合成剂，裸露义体接缝会在30分钟内发生电阻过载。",
            is_global=True, valid_from_chapter=1
        )
    ]

    chapter_plans = [
        (1, "第一章 破损的接口", PacingType.BUILD_UP, "酸雨后巷遭遇荒坂猎犬围堵"),
        (2, "第二章 绝境反黑入", PacingType.COGNITIVE_GAP, "诱敌进入变电箱陷阱并强行反黑"),
        (3, "第三章 惊骇的认知反差", PacingType.CATHARSIS_PAYOFF, "破译芯片并在暗网引发舆论轰动"),
    ]

    for ch_idx, title, pacing, desc in chapter_plans:
        console.print(f"[bold green]>> 正在生产 第 {ch_idx} 章: {title} [{pacing.value}][/bold green]")

        orchestrator.calendar.anchor_chapter(
            ch_idx, elapsed_minutes=180, declared_text="次日" if ch_idx > 1 else ""
        )
        orchestrator.power_guard.record(ch_idx, "char_zero", 120.0 + ch_idx * 30.0)
        orchestrator.power_guard.record(ch_idx, "char_hunter", 450.0)

        b1 = BeatContract(
            beat_id=f"ch0{ch_idx}_b01", chapter_index=ch_idx, beat_index=1,
            target_words=160, word_tolerance_ratio=0.6, pacing_type=pacing,
            required_camera_angles=[CameraAngle.POV, CameraAngle.CLOSE_UP],
            characters_present=["char_zero", "char_hunter"], location_id="loc_alley",
            pre_conditions=[desc],
            micro_events=[MicroEvent(event_id=f"e{ch_idx}_1", description=desc)]
        )
        b2 = BeatContract(
            beat_id=f"ch0{ch_idx}_b02", chapter_index=ch_idx, beat_index=2,
            target_words=160, word_tolerance_ratio=0.6,
            pacing_type=PacingType.CLIFFHANGER_HOOK if ch_idx == 3 else pacing,
            required_camera_angles=[CameraAngle.POV, CameraAngle.REACTION_CAM],
            characters_present=["char_zero"], location_id="loc_alley"
        )
        delta = StateDelta(
            chapter_index=ch_idx,
            entity_mutations={"char_zero": {"power_rating": 120.0 + ch_idx * 30.0}}
        )
        ch_res = orchestrator.produce_chapter(
            chapter_index=ch_idx, title=title, beat_contracts=[b1, b2],
            lore_entries=lore_entries, state_delta=delta
        )
        flag = "[green]PASS[/green]" if ch_res.qc_passed else "[yellow]HELD[/yellow]"
        console.print(
            f"  {flag} 提交 SHA=[cyan]{ch_res.commit.commit_id}[/cyan] | "
            f"字数={ch_res.commit.word_count} | "
            f"钩子={ch_res.commit.qc_metrics.get('hook_strength')} | "
            f"成本=¥{ch_res.commit.qc_metrics.get('total_cost_cny')}"
        )
        for b in ch_res.blockers:
            console.print(f"    [yellow]· 闸门提示: {b}[/yellow]")

    console.print("\n[bold cyan]=== 剧情版本库提交历史 (Commit Log) ===[/bold cyan]")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Commit ID", style="dim", width=16)
    table.add_column("Chapter", justify="center", width=8)
    table.add_column("Title", width=25)
    table.add_column("Word Count", justify="right", width=12)
    for item in orchestrator.repo.get_commit_log():
        table.add_row(item["commit_id"], f"第 {item['chapter_index']} 章", item["title"], f"{item['word_count']} 字")
    console.print(table)

    console.print("\n[bold cyan]=== 长程治理巡检 ===[/bold cyan]")
    gov = orchestrator.audit_chapter_governance(3, orchestrator.repo.get_head_commit().full_prose)
    console.print(gov.format_summary())

    console.print("\n[bold red]>>> 模拟时空回滚：回滚至第 2 章末尾...[/bold red]")
    orchestrator.repo.checkout_chapter(target_chapter_index=2)
    new_head = orchestrator.repo.get_head_commit()
    console.print(f"[bold yellow][OK] 成功回滚至: 第 {new_head.chapter_index} 章 [{new_head.title}], HEAD SHA={new_head.commit_id}[/bold yellow]")
    state_restored = orchestrator.graph.get_entity_state_at("char_zero", 3)
    console.print(f"[OK] 图谱实体状态同步还原: 零号战力为 {state_restored['power_rating']}")
    console.print("\n[bold green][SUCCESS] 黄金三章试产演示完成。[/bold green]")
    orchestrator.close()


# ============================ produce ============================

def cmd_produce(args):
    """批量自动化生产章节（断点续产）"""
    print_banner()
    db_path = args.db or DEFAULT_DB
    try:
        orchestrator = _build_orchestrator(args, db_path)
    except ConcurrentProductionError as e:
        console.print(f"[bold red]无法开工：{e}[/bold red]")
        return

    start, end = args.start, args.end
    if end < start:
        console.print("[bold red]错误：--end 不能小于 --start[/bold red]")
        return

    chapters = list(range(start, end + 1))
    journal_path = Path(args.journal)

    console.print(
        f"[bold green]>>> 批量生产 第 {start} ~ {end} 章 "
        f"(供应商={args.provider}, 模型={args.model}, 日志={journal_path})[/bold green]"
    )

    outline_path = Path(args.outline)
    if outline_path.exists():
        rep = orchestrator.load_outline(outline_path)
        console.print(f"[cyan]已加载大纲 {outline_path} —— {rep.format_summary().splitlines()[0]}[/cyan]")
        if not rep.passed and args.require_outline:
            console.print("[bold red]大纲存在致命问题，拒绝开工。请先修复后重试。[/bold red]")
            for i in rep.errors[:10]:
                console.print(f"  [red]- {i.scope} {i.ref}: {i.message}[/red]")
            orchestrator.close()
            return
        registered = orchestrator.outline_store.bootstrap_world(orchestrator)
        if registered:
            console.print(f"[cyan]已按演员表注册 {registered} 个世界实体[/cyan]")
        missing = orchestrator.outline_store.unplanned_chapters(start, end)
        if missing:
            msg = f"区间内有 {len(missing)} 章尚未规划大纲: {missing[:10]}"
            if args.require_outline:
                console.print(f"[bold red]{msg}，拒绝开工。[/bold red]")
                orchestrator.close()
                return
            console.print(f"[yellow]{msg}（将以占位标题生产）[/yellow]")
    elif args.require_outline:
        console.print(
            f"[bold red]--require-outline 已启用但找不到大纲文件 {outline_path}[/bold red]"
        )
        orchestrator.close()
        return

    def plan_provider(ch: int) -> Dict[str, Any]:
        """优先按全书大纲生成生产参数，缺失时退化为占位契约"""
        return orchestrator.build_chapter_plan(
            chapter_index=ch,
            fallback_characters=args.characters.split(",") if args.characters else None,
            fallback_location=args.location,
            require_outline=args.require_outline,
        )

    def on_progress(ch: int, job):
        color = {
            JobStatus.COMPLETED: "green", JobStatus.QC_REJECTED: "yellow",
            JobStatus.FAILED: "red", JobStatus.SUSPENDED: "magenta",
        }.get(job.status, "white")
        console.print(
            f"  [{color}]第 {ch} 章 -> {job.status.value}[/{color}] "
            f"字数={job.word_count} 成本=¥{job.cost_cny:.4f}"
            + (f" | {job.error}" if job.error else "")
        )

    producer = ResumableProducer(
        orchestrator=orchestrator,
        journal_path=journal_path,
        max_attempts_per_chapter=args.retries,
        suspend_on_qc_failure=args.halt_on_reject,
        progress_callback=on_progress,
    )

    resume_at = producer.resume_point(chapters)
    if resume_at is not None and resume_at != start:
        console.print(f"[cyan]检测到历史生产日志，将从第 {resume_at} 章断点续产[/cyan]")

    summary = producer.run(chapters, plan_provider, stop_after=args.limit)
    console.print("\n" + summary.format_summary())

    book = orchestrator.cost_auditor.audit_book_total()
    console.print(
        f"[dim]全书累计: ¥{book.total_cost_cny:.4f} | "
        f"单章均价 ¥{book.avg_cost_per_chapter:.5f} | "
        f"缓存节约 ¥{book.total_cny_saved_by_caching:.4f}[/dim]"
    )
    orchestrator.close()


# ============================ status ============================

def cmd_status(args):
    """项目与法则体系状态"""
    print_banner()
    loader = ProjectConfigLoader()
    proj_path = Path(args.project)

    if not proj_path.exists():
        console.print(f"[bold red]错误：找不到项目配置文件: {proj_path}[/bold red]")
        return

    proj = loader.load_project_master(proj_path)
    console.print(f"[bold green]项目名称: {proj.project_name} ({proj.project_title})[/bold green]")
    console.print(f"[cyan]已挂载题材: {proj.genre.name if proj.genre else '通用'} ({proj.genre.genre if proj.genre else 'N/A'})[/cyan]")
    console.print(f"[cyan]已挂载节奏: {proj.pacing.pacing_name if proj.pacing else '默认节奏'}[/cyan]")
    console.print(f"[cyan]每章预算限额: ¥{proj.models.cost_limit_per_chapter_cny:.2f}[/cyan]")

    if proj.genre and proj.genre.power_scale:
        console.print(f"\n[bold magenta]=== 战力/等级标尺: {proj.genre.power_scale.scale_name} ===[/bold magenta]")
        t_table = Table(show_header=True)
        t_table.add_column("阶位 ID", width=18)
        t_table.add_column("阶位名称", width=22)
        t_table.add_column("战力范围", width=15)
        for t in proj.genre.power_scale.tiers:
            t_table.add_row(t.tier_id, t.name, f"{t.numeric_min} - {t.numeric_max}")
        console.print(t_table)

    db_path = args.db or DEFAULT_DB
    if Path(db_path).exists():
        orch = NovelFactoryOrchestrator(project_config_path=str(proj_path), db_path=db_path)
        dash = WorkbenchDashboard(console=console)
        console.print()
        console.print(dash.render_overview(orch.repo, orch.graph))
        roster = orch.graph.list_entities()
        if roster:
            console.print(dash.render_entity_roster(orch.graph, current_chapter=1))
        log = orch.repo.get_commit_log(limit=10)
        if log:
            t = Table(title="最近提交", show_header=True, header_style="bold magenta")
            t.add_column("Commit"); t.add_column("章"); t.add_column("标题"); t.add_column("字数", justify="right")
            for c in log:
                t.add_row(c["commit_id"][:12], str(c["chapter_index"]), c["title"], str(c["word_count"]))
            console.print(t)
        orch.close()
    else:
        console.print(f"\n[dim]（尚无生产数据库 {db_path}，运行 produce 后可查看提交树）[/dim]")


# ============================ rollback ============================

def cmd_rollback(args):
    """时空回滚与分支管理"""
    print_banner()
    db_path = args.db or DEFAULT_DB
    if not Path(db_path).exists():
        console.print(f"[bold red]错误：数据库不存在: {db_path}[/bold red]")
        return

    orch = NovelFactoryOrchestrator(db_path=db_path)

    if args.list_branches:
        t = Table(title="剧情分支", show_header=True)
        t.add_column("分支名"); t.add_column("HEAD")
        for b in orch.repo.list_branches():
            t.add_row(str(b.get("branch_name")), str(b.get("head_commit_id"))[:12])
        console.print(t)
        orch.close()
        return

    if args.branch:
        orch.repo.create_branch(args.branch)
        console.print(f"[green]已创建并切换到新剧情分支: {args.branch}[/green]")

    if args.chapter is not None:
        try:
            ok = orch.repo.checkout_chapter(target_chapter_index=args.chapter)
        except Exception as e:
            console.print(f"[bold red]回滚失败: {e}[/bold red]")
            orch.close()
            return
        if ok:
            head = orch.repo.get_head_commit()
            console.print(
                f"[bold yellow][OK] 已回滚至第 {head.chapter_index} 章 [{head.title}] "
                f"HEAD={head.commit_id}[/bold yellow]"
            )
            console.print("[dim]BEC 图谱、事件溯源与进展引擎已同步回退。[/dim]")
        else:
            console.print(f"[bold red]回滚失败：找不到第 {args.chapter} 章的提交[/bold red]")
    orch.close()


# ============================ export ============================

def cmd_export(args):
    """手稿与训练数据集导出（真实落盘）"""
    print_banner()
    db_path = args.db or DEFAULT_DB
    if not Path(db_path).exists():
        console.print(f"[bold red]错误：找不到生产数据库 {db_path}，请先执行 produce。[/bold red]")
        return

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    orch = NovelFactoryOrchestrator(db_path=db_path)
    exporter: ManuscriptExporter = orch.exporter

    title = args.title
    if Path(args.project).exists():
        try:
            proj = ProjectConfigLoader().load_project_master(Path(args.project))
            title = args.title or proj.project_title
        except Exception:
            pass
    title = title or "未命名作品"

    results: List[tuple] = []
    fmt = args.format
    try:
        if fmt in ("txt", "all"):
            p = out_dir / "manuscript_submission.txt"
            n = exporter.export_to_txt(str(p))
            results.append(("投稿标准 TXT (两格全角缩进)", p, n))
        if fmt in ("md", "all"):
            p = out_dir / "full_book.md"
            n = exporter.export_to_markdown(str(p), book_title=title)
            results.append(("全书 Markdown (含目录)", p, n))
        if fmt in ("sft", "all"):
            p = out_dir / "sft_dataset.jsonl"
            n = exporter.export_to_jsonl_dataset(str(p))
            results.append(("SFT 微调数据集 (ShareGPT)", p, f"{n} 条样本"))
        if fmt in ("bible", "all"):
            p = out_dir / "world_bible.md"
            n = exporter.export_world_bible(str(p))
            results.append(("世界观设定集", p, n))
    except Exception as e:
        console.print(f"[bold red]导出失败: {type(e).__name__}: {e}[/bold red]")
        orch.close()
        return

    t = Table(title=f"导出完成 -> {out_dir}", show_header=True, header_style="bold green")
    t.add_column("产物"); t.add_column("路径"); t.add_column("规模", justify="right")
    for name, path, size in results:
        t.add_row(name, str(path), str(size))
    console.print(t)
    orch.close()


# ============================ inspect ============================

def cmd_inspect(args):
    """审查章节质检指标与疲劳矩阵"""
    print_banner()
    db_path = args.db or DEFAULT_DB
    if not Path(db_path).exists():
        console.print(f"[bold red]错误：找不到生产数据库 {db_path}[/bold red]")
        return

    orch = NovelFactoryOrchestrator(db_path=db_path)
    chapters = orch.exporter.get_all_chapters()
    if not chapters:
        console.print("[yellow]数据库中尚无已提交章节。[/yellow]")
        orch.close()
        return

    targets = [c for c in chapters if args.chapter is None or c["chapter_index"] == args.chapter]
    if not targets:
        console.print(f"[yellow]找不到第 {args.chapter} 章。[/yellow]")
        orch.close()
        return

    t = Table(title="章节质检指标总览", show_header=True, header_style="bold magenta")
    t.add_column("章"); t.add_column("标题"); t.add_column("字数", justify="right")
    t.add_column("节拍通过"); t.add_column("章级放行"); t.add_column("钩子")
    t.add_column("雷同", justify="right"); t.add_column("成本", justify="right")

    for c in targets:
        try:
            m = json.loads(c.get("qc_metrics_json") or "{}")
        except (json.JSONDecodeError, TypeError):
            m = {}
        t.add_row(
            str(c["chapter_index"]), c["title"], str(c["word_count"]),
            "✓" if m.get("all_beats_passed") else "✗",
            "✓" if m.get("chapter_qc_passed", True) else "✗",
            str(m.get("hook_strength") or "-"),
            str(m.get("simhash_incident_count", 0)),
            f"¥{m.get('total_cost_cny', 0):.5f}",
        )
    console.print(t)

    # 重建疲劳矩阵与 SimHash 指纹
    for c in chapters:
        orch.fatigue_matrix.record_chapter_text(c["chapter_index"], c["full_prose"])
        orch.simhash_index.index_chapter(c["chapter_index"], c["full_prose"])

    last_ch = targets[-1]["chapter_index"]
    bans = orch.fatigue_matrix.get_dynamic_ban_list(last_ch)
    if bans:
        bt = Table(title=f"第 {last_ch} 章滑窗高频词疲劳矩阵 (动态禁令)", show_header=True)
        bt.add_column("疲劳词"); bt.add_column("出现次数", justify="right"); bt.add_column("建议")
        for b in bans[:15]:
            bt.add_row(
                str(getattr(b, "term", "")),
                str(getattr(b, "occurrence_count", getattr(b, "count", ""))),
                str(getattr(b, "reason", getattr(b, "suggestion", "建议替换同义表达"))),
            )
        console.print(bt)
    else:
        console.print("[dim]未检出高频疲劳词。[/dim]")

    fp = orch.simhash_index.simhash.compute_simhash(targets[-1]["full_prose"])
    console.print(f"[cyan]第 {last_ch} 章 64 位 SimHash 指纹: {fp:#018x}[/cyan]")
    orch.close()


# ============================ govern ============================

def cmd_govern(args):
    """长程治理巡检"""
    print_banner()
    db_path = args.db or DEFAULT_DB
    if not Path(db_path).exists():
        console.print(f"[bold red]错误：找不到生产数据库 {db_path}[/bold red]")
        return

    orch = NovelFactoryOrchestrator(db_path=db_path)
    chapters = orch.exporter.get_all_chapters()
    if not chapters:
        console.print("[yellow]尚无已提交章节。[/yellow]")
        orch.close()
        return

    # 回放全书以重建长程引擎状态
    for c in chapters:
        orch.hook_enforcer.evaluate(c["chapter_index"], c["full_prose"])
        orch.payoff_meter.record_chapter(c["chapter_index"], text=c["full_prose"])

    last = chapters[-1]["chapter_index"]

    console.print("[bold cyan]=== 章末钩子强度趋势 ===[/bold cyan]")
    trend = orch.hook_enforcer.analyze_trend(window=args.window)
    ht = Table(show_header=True)
    ht.add_column("章"); ht.add_column("强度"); ht.add_column("评分", justify="right"); ht.add_column("钩子类型")
    for ch, ev in sorted(orch.hook_enforcer.get_history().items())[-args.window:]:
        ht.add_row(str(ch), ev.strength.value, f"{ev.score:.1f}",
                   "、".join(t.value for t in ev.hook_types) or "-")
    console.print(ht)
    console.print(f"[dim]近 {args.window} 章平均钩子强度: {trend.avg_score}[/dim]")
    for a in trend.alerts:
        console.print(f"[yellow]  ! {a}[/yellow]")

    console.print("\n[bold cyan]=== 爽点密度曲线 ===[/bold cyan]")
    console.print(orch.payoff_meter.render_curve(width=args.window))
    density = orch.payoff_meter.analyze(last)
    console.print(density.format_summary())

    console.print("\n[bold cyan]=== 伏笔台账 ===[/bold cyan]")
    open_fs = orch.foreshadow_ledger.list_open()
    if open_fs:
        ft = Table(show_header=True)
        ft.add_column("ID"); ft.add_column("摘要"); ft.add_column("量级")
        ft.add_column("埋设章", justify="right"); ft.add_column("回收截止", justify="right")
        for r in open_fs:
            ft.add_row(r.foreshadow_id, r.summary[:30], r.weight.value,
                       str(r.planted_chapter), str(r.payoff_deadline_chapter))
        console.print(ft)
    else:
        console.print("[dim]台账中暂无未回收伏笔。[/dim]")

    console.print("\n[bold cyan]=== 角色命名冲突扫描 ===[/bold cyan]")
    roster = orch.graph.list_entities(entity_type="CHARACTER")
    if roster:
        nr = orch.name_detector.check([e["name"] for e in roster], [e["entity_id"] for e in roster])
        console.print(nr.format_summary())
    else:
        console.print("[dim]图谱中暂无角色实体。[/dim]")

    if orch.thread_scheduler.threads:
        console.print("\n[bold cyan]=== 多线推进甘特图 ===[/bold cyan]")
        console.print(orch.thread_scheduler.render_gantt(max(1, last - args.window), last))

    orch.close()


# ============================ resume ============================

def cmd_resume(args):
    """断点续产日志管理"""
    print_banner()
    journal = ProductionJournal(Path(args.journal))
    if not journal.jobs:
        console.print(f"[yellow]日志 {args.journal} 为空或不存在。[/yellow]")
        return

    if args.reset is not None:
        journal.reset_chapter(args.reset)
        console.print(f"[green]已重置第 {args.reset} 章状态，下次 produce 将重跑该章。[/green]")
        return

    t = Table(title=f"生产日志: {args.journal}", show_header=True, header_style="bold magenta")
    t.add_column("章"); t.add_column("状态"); t.add_column("尝试", justify="right")
    t.add_column("字数", justify="right"); t.add_column("成本", justify="right"); t.add_column("备注")
    for ch, job in sorted(journal.jobs.items()):
        color = {
            JobStatus.COMPLETED: "green", JobStatus.QC_REJECTED: "yellow",
            JobStatus.FAILED: "red", JobStatus.SUSPENDED: "magenta",
        }.get(job.status, "white")
        note = job.error or ("; ".join(job.blockers)[:50] if job.blockers else "")
        t.add_row(str(ch), f"[{color}]{job.status.value}[/{color}]", str(job.attempts),
                  str(job.word_count), f"¥{job.cost_cny:.4f}", note)
    console.print(t)
    console.print("\n" + journal.summary().format_summary())


# ============================ outline ============================

def cmd_outline(args):
    """全书大纲：脚手架生成 / 校验 / 查看"""
    print_banner()
    from src.novel_factory.controller.outline_store import OutlineStore

    path = Path(args.file)
    store = OutlineStore()

    if args.init:
        if path.exists() and not args.force:
            console.print(f"[bold red]{path} 已存在，如需覆盖请加 --force[/bold red]")
            return
        store = OutlineStore.scaffold(
            title=args.title, total_chapters=args.chapters, volumes=args.volumes
        )
        store.save(path)
        console.print(f"[green]已生成大纲模板: {path}[/green]")
        console.print("[dim]请编辑该文件填写主线目标、分卷危机与各章冲突，再运行 outline --validate[/dim]")
        return

    if not path.exists():
        console.print(
            f"[bold red]大纲文件不存在: {path}[/bold red]\n"
            f"[dim]用 `novel-factory outline --init` 生成模板。[/dim]"
        )
        return

    store.load(path)
    report = store.validate()

    o = store.outliner
    if o.master_arc:
        console.print(Panel.fit(
            f"[bold cyan]{o.master_arc.title}[/bold cyan]\n"
            f"母题: {o.master_arc.core_theme}\n"
            f"主角终极目标: {o.master_arc.protagonist_ultimate_goal}\n"
            f"全书规模: {o.master_arc.target_total_chapters} 章",
            border_style="cyan", title="主线大纲"
        ))

    if store.cast:
        ct = Table(title="演员表 (开书注册进世界图谱)", show_header=True, header_style="bold green")
        ct.add_column("实体 ID"); ct.add_column("名称"); ct.add_column("类型"); ct.add_column("初始属性")
        for m in store.cast.values():
            ct.add_row(m.entity_id, m.name, m.entity_type, str(m.payload))
        console.print(ct)

    if o.volumes:
        vt = Table(title="分卷规划", show_header=True, header_style="bold magenta")
        vt.add_column("卷"); vt.add_column("标题"); vt.add_column("章节区间")
        vt.add_column("核心危机", overflow="fold")
        for v in sorted(o.volumes.values(), key=lambda x: x.volume_index):
            vt.add_row(str(v.volume_index), v.title,
                       f"{v.chapter_start}-{v.chapter_end}", v.core_crisis[:40])
        console.print(vt)

    if args.show_chapters and o.chapters:
        ct = Table(title="章节规划", show_header=True)
        ct.add_column("章"); ct.add_column("标题"); ct.add_column("核心冲突", overflow="fold")
        ct.add_column("章末钩子", overflow="fold")
        for idx in sorted(o.chapters):
            c = o.chapters[idx]
            ct.add_row(str(idx), c.title, c.core_conflict[:30], c.expected_cliffhanger[:30])
        console.print(ct)

    # 注意：报告正文里含有 [ERROR] / [WARNING] 这类方括号片段，
    # 一旦包在 Rich 样式标签里就会被当成标记语法吞掉，必须关闭 markup。
    console.print(
        report.format_summary(),
        style="green" if report.passed else "red",
        markup=False,
    )

    gaps = store.unplanned_chapters(1, o.master_arc.target_total_chapters if o.master_arc else 0)
    if gaps:
        preview = ", ".join(str(g) for g in gaps[:20])
        more = f" ...（共 {len(gaps)} 章）" if len(gaps) > 20 else ""
        console.print(f"[yellow]尚未规划的章节: {preview}{more}[/yellow]")


# ============================ workbench ============================

def cmd_workbench(args):
    """人机协同断点工作台：查看与解除生产断点"""
    print_banner()
    manager = HITLBreakpointManager(state_file_path=Path(args.state_file))
    state = manager.load_state()

    if not state.is_paused:
        console.print("[green]当前没有待处理的人机断点，流水线处于自动运行状态。[/green]")
        return

    console.print(Panel.fit(
        f"[bold yellow]断点类型: {state.active_breakpoint.value if state.active_breakpoint else 'UNKNOWN'}[/bold yellow]\n"
        f"章节: 第 {state.chapter_index} 章"
        + (f" | 节拍: {state.beat_id}" if state.beat_id else "") + "\n\n"
        + state.prompt_message,
        border_style="yellow", title="等待人工决策"
    ))

    if state.context_data:
        t = Table(show_header=True, header_style="bold magenta", title="断点现场")
        t.add_column("字段"); t.add_column("内容", overflow="fold")
        for k, v in state.context_data.items():
            t.add_row(str(k), str(v)[:400])
        console.print(t)

    if not args.decide:
        console.print(
            "\n[dim]使用 --decide {approve|modify|rollback|takeover} 解除断点。[/dim]"
        )
        return

    mapping = {
        "approve": HumanDecision.APPROVE,
        "modify": HumanDecision.MODIFY_AND_PROCEED,
        "rollback": HumanDecision.ROLLBACK,
        "takeover": HumanDecision.MANUAL_TAKEOVER,
    }
    decision = mapping[args.decide]

    db_path = args.db or DEFAULT_DB
    if decision == HumanDecision.ROLLBACK and Path(db_path).exists():
        orch = NovelFactoryOrchestrator(db_path=db_path)
        orch.hitl_manager = manager
        res = orch.resolve_breakpoint(decision)
        orch.close()
    else:
        res = manager.resolve_breakpoint(decision)

    console.print(f"[green]断点已解除: {res}[/green]")
    console.print(
        "[dim]如需重跑该章，执行: "
        f"novel-factory resume --reset {state.chapter_index}[/dim]"
    )


# ============================ parser ============================

def _add_provider_args(p):
    p.add_argument("--provider", default="mock",
                   choices=["mock", "gemini", "gemini_rest", "deepseek", "openai", "custom"],
                   help="大模型供应商（默认 mock 离线模式）")
    p.add_argument("--model", default="gemini-3.8-flash", help="模型名称")
    p.add_argument("--api-key", dest="api_key", default=None, help="API Key（亦可用环境变量）")
    p.add_argument("--base-url", dest="base_url", default=None, help="自定义 OpenAI 兼容端点")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="novel-factory",
        description="工业化小说制造流水线 (Antigravity Novel Factory CLI)"
    )
    sub = parser.add_subparsers(dest="command", help="子命令")

    demo_p = sub.add_parser("demo", help="运行黄金三章全链路快速演示")
    demo_p.add_argument("--project", default="project.yaml")

    prod_p = sub.add_parser("produce", help="批量自动化生产章节（支持断点续产）")
    prod_p.add_argument("--project", default="project.yaml")
    prod_p.add_argument("--db", default=DEFAULT_DB, help="生产数据库路径")
    prod_p.add_argument("--start", type=int, default=1, help="起始章号")
    prod_p.add_argument("--end", type=int, default=3, help="结束章号")
    prod_p.add_argument("--limit", type=int, default=None, help="本次最多生产多少章")
    prod_p.add_argument("--retries", type=int, default=3, help="单章最大重试次数")
    prod_p.add_argument("--journal", default=".production_journal.json", help="断点日志路径")
    prod_p.add_argument("--location", default="DEFAULT_SCENE", help="默认场景 ID")
    prod_p.add_argument("--characters", default="", help="在场角色 ID，逗号分隔")
    prod_p.add_argument("--halt-on-reject", action="store_true", help="质检驳回即挂起等待人工")
    prod_p.add_argument("--no-governance", action="store_true", help="关闭长程治理硬闸门")
    prod_p.add_argument("--outline", default="outline.yaml", help="全书大纲文件")
    prod_p.add_argument("--no-lock", dest="lock", action="store_false", default=True,
                        help="不获取生产写锁（不推荐；并发写会导致章节静默丢失）")
    prod_p.add_argument("--force-lock", action="store_true",
                        help="强制接管残留的生产写锁")
    prod_p.add_argument("--require-outline", action="store_true",
                        help="缺少大纲或大纲不合格时拒绝开工（推荐正式生产开启）")
    _add_provider_args(prod_p)

    status_p = sub.add_parser("status", help="查看项目、法则体系与提交树状态")
    status_p.add_argument("--project", default="project.yaml")
    status_p.add_argument("--db", default=DEFAULT_DB)

    rb_p = sub.add_parser("rollback", help="时空回滚与剧情分支管理")
    rb_p.add_argument("--db", default=DEFAULT_DB)
    rb_p.add_argument("--chapter", type=int, default=None, help="回滚到该章末尾")
    rb_p.add_argument("--branch", default=None, help="回滚后创建的新分支名")
    rb_p.add_argument("--list-branches", action="store_true", help="列出全部剧情分支")

    exp_p = sub.add_parser("export", help="导出成品手稿或微调数据集")
    exp_p.add_argument("--project", default="project.yaml")
    exp_p.add_argument("--db", default=DEFAULT_DB)
    exp_p.add_argument("--output", default="exports", help="导出目标目录")
    exp_p.add_argument("--format", choices=["txt", "md", "sft", "bible", "all"], default="all")
    exp_p.add_argument("--title", default=None, help="书名（默认取 project.yaml）")

    ins_p = sub.add_parser("inspect", help="审查章节质检指标与疲劳矩阵")
    ins_p.add_argument("--db", default=DEFAULT_DB)
    ins_p.add_argument("--chapter", type=int, default=None, help="仅审查指定章节")

    gov_p = sub.add_parser("govern", help="长程治理巡检（伏笔/爽点/钩子/命名/多线）")
    gov_p.add_argument("--db", default=DEFAULT_DB)
    gov_p.add_argument("--window", type=int, default=20, help="巡检窗口章数")

    ol_p = sub.add_parser("outline", help="全书大纲：生成模板 / 校验 / 查看")
    ol_p.add_argument("--file", default="outline.yaml")
    ol_p.add_argument("--init", action="store_true", help="生成大纲脚手架模板")
    ol_p.add_argument("--force", action="store_true", help="覆盖已存在的大纲文件")
    ol_p.add_argument("--title", default="未命名作品")
    ol_p.add_argument("--chapters", type=int, default=300, help="全书规划章数")
    ol_p.add_argument("--volumes", type=int, default=4, help="分卷数")
    ol_p.add_argument("--show-chapters", action="store_true", help="列出全部章节规划")

    wb_p = sub.add_parser("workbench", help="人机协同断点工作台：查看与解除生产断点")
    wb_p.add_argument("--state-file", dest="state_file", default=".hitl_state.json")
    wb_p.add_argument("--db", default=DEFAULT_DB)
    wb_p.add_argument("--decide", choices=["approve", "modify", "rollback", "takeover"],
                      default=None, help="做出人工决策并解除断点")

    res_p = sub.add_parser("resume", help="查看与操作断点续产日志")
    res_p.add_argument("--journal", default=".production_journal.json")
    res_p.add_argument("--reset", type=int, default=None, help="重置指定章节以便重跑")

    return parser


COMMANDS: Dict[str, Callable[[Any], None]] = {
    "demo": cmd_demo,
    "produce": cmd_produce,
    "status": cmd_status,
    "rollback": cmd_rollback,
    "export": cmd_export,
    "inspect": cmd_inspect,
    "govern": cmd_govern,
    "resume": cmd_resume,
    "workbench": cmd_workbench,
    "outline": cmd_outline,
}


def main(argv: Optional[List[str]] = None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        args = parser.parse_args(["demo"])

    handler = COMMANDS.get(args.command)
    if handler is None:
        parser.print_help()
        return
    handler(args)


if __name__ == "__main__":
    main()
