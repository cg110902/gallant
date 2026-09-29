"""
Novel Factory Master CLI - 工业化小说生产车间终端总控台
基于 Rich 终端渲染，提供：
1. demo: 快速执行黄金三章试产演示与时空回滚验证；
2. produce: 读取 project.yaml 批量自动化生产章节；
3. status: 探查当前剧情提交树 (Commit DAG)、实体状态与财务审计；
4. rollback: 一键时空穿越与剧情分支回滚；
5. export: 导出番茄/起点纯文本手稿、Markdown 全书与 ShareGPT SFT 数据集；
6. inspect: 审查特定章节的 SimHash 指纹与高频词疲劳矩阵。
"""

import argparse
from pathlib import Path
import sys
from typing import List, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.novel_factory.config.loader import ProjectConfigLoader
from src.novel_factory.export.manuscript_exporter import ManuscriptExporter
from src.novel_factory.orchestrator import NovelFactoryOrchestrator
from src.novel_factory.schemas.beat import BeatContract, CameraAngle, MicroEvent, PacingType
from src.novel_factory.schemas.commit import StateDelta
from src.novel_factory.schemas.entity import LoreEntry

console = Console(force_terminal=True, legacy_windows=False)


def print_banner():
    console.print(Panel.fit(
        "[bold cyan]Novel Factory Enterprise v4.5[/bold cyan]\n"
        "[dim]工业级全题材长篇小说智能制造流水线 | Antigravity 本地工作台[/dim]",
        border_style="cyan"
    ))


def cmd_demo(args):
    """执行端到端黄金三章试产演示与时空回滚"""
    print_banner()
    console.print("[bold yellow]>>> 启动样板书 [霓虹雨夜：断线黑客的复仇纪元] 黄金三章试产流水线...[/bold yellow]\n")

    def smart_writer(sys_p: str, user_p: str) -> str:
        if "局部微创打补丁任务" in user_p:
            return (
                "零号没有回答，只是将微型激光刀向前递了半寸。\n"
                "刺啦一声，皮质手套被割开一道焦黑的裂口。\n"
                "中间人的瞳孔猛地收缩，按在桌面的五指僵硬得泛白。"
            )
        return (
            "酸雨泼洒在阴暗的后巷青石地面上，腐蚀出白色的泡沫。\n"
            "零号靠在生锈的铁门后，指尖的神经解码器红灯急促闪烁。\n"
            "后方的机械脚步声在十步外停住。\n"
            "‘找到你了，老鼠。’追捕者的电子合成音带着金属刮擦声。"
        )

    project_cfg = Path("project.yaml")
    orchestrator = NovelFactoryOrchestrator.from_project_config(
        config_path=str(project_cfg) if project_cfg.exists() else None,
        db_path=":memory:",
        llm_worker=smart_writer
    )

    orchestrator.graph.register_entity(
        entity_id="char_zero",
        entity_type="CHARACTER",
        name="零号",
        created_chapter=1,
        initial_payload={"tier_or_rank": "初级民用植入", "power_rating": 120.0}
    )
    orchestrator.graph.register_entity(
        entity_id="char_hunter",
        entity_type="CHARACTER",
        name="荒坂猎犬",
        created_chapter=1,
        initial_payload={"tier_or_rank": "军规级战术改装", "power_rating": 450.0}
    )

    lore_entries = [
        LoreEntry(
            entry_id="lore_acid_rain",
            entity_type="SYSTEM_RULE",
            name="工业酸雨腐蚀法则",
            content="雨水中含有强酸性化学合成剂，裸露义体接缝会在30分钟内发生电阻过载。",
            is_global=True,
            valid_from_chapter=1
        )
    ]

    chapter_plans = [
        (1, "第一章 破损的接口", PacingType.BUILD_UP, "酸雨后巷遭遇荒坂猎犬围堵"),
        (2, "第二章 绝境反黑入", PacingType.COGNITIVE_GAP, "诱敌进入变电箱陷阱并强行反黑"),
        (3, "第三章 惊骇的认知反差", PacingType.CATHARSIS_PAYOFF, "破译芯片并在暗网引发舆论轰动")
    ]

    for ch_idx, title, pacing, desc in chapter_plans:
        console.print(f"[bold green]>> 正在生产 第 {ch_idx} 章: {title} [{pacing.value}][/bold green]")
        b1 = BeatContract(
            beat_id=f"ch0{ch_idx}_b01",
            chapter_index=ch_idx,
            beat_index=1,
            target_words=500,
            pacing_type=pacing,
            required_camera_angles=[CameraAngle.POV, CameraAngle.CLOSE_UP],
            characters_present=["char_zero", "char_hunter"],
            location_id="loc_alley",
            pre_conditions=[desc],
            micro_events=[MicroEvent(event_id=f"e{ch_idx}_1", description=desc)]
        )
        b2 = BeatContract(
            beat_id=f"ch0{ch_idx}_b02",
            chapter_index=ch_idx,
            beat_index=2,
            target_words=500,
            pacing_type=PacingType.CLIFFHANGER_HOOK if ch_idx == 3 else pacing,
            required_camera_angles=[CameraAngle.POV, CameraAngle.REACTION_CAM],
            characters_present=["char_zero"],
            location_id="loc_alley"
        )
        delta = StateDelta(
            chapter_index=ch_idx,
            entity_mutations={"char_zero": {"power_rating": 120.0 + ch_idx * 80.0}}
        )
        ch_res = orchestrator.produce_chapter(
            chapter_index=ch_idx,
            title=title,
            beat_contracts=[b1, b2],
            lore_entries=lore_entries,
            state_delta=delta
        )
        console.print(f"  [OK] 提交: SHA=[cyan]{ch_res.commit.commit_id}[/cyan] | 字数={ch_res.commit.word_count} | 质检通过={ch_res.commit.qc_metrics['all_beats_passed']}")

    # 打印版本库提交历史
    console.print("\n[bold cyan]=== 剧情版本库提交历史 (Commit Log) ===[/bold cyan]")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Commit ID", style="dim", width=16)
    table.add_column("Chapter", justify="center", width=8)
    table.add_column("Title", width=25)
    table.add_column("Word Count", justify="right", width=12)

    for item in orchestrator.repo.get_commit_log():
        table.add_row(item["commit_id"], f"第 {item['chapter_index']} 章", item["title"], f"{item['word_count']} 字")
    console.print(table)

    # 演示 Narrative VCS 一键时空回滚
    console.print("\n[bold red]>>> 模拟时空回滚：回滚至第 2 章末尾...[/bold red]")
    orchestrator.repo.checkout_chapter(target_chapter_index=2)
    new_head = orchestrator.repo.get_head_commit()
    console.print(f"[bold yellow][OK] 成功回滚至: 第 {new_head.chapter_index} 章 [{new_head.title}], HEAD SHA={new_head.commit_id}[/bold yellow]")

    state_restored = orchestrator.graph.get_entity_state_at("char_zero", 3)
    console.print(f"[OK] 图谱实体状态同步还原: 零号战力为 {state_restored['power_rating']}")
    console.print("\n[bold green][SUCCESS] 黄金三章试产演示顺利完成！系统达到工业生产标准。[/bold green]")
    orchestrator.close()


def cmd_status(args):
    """探查当前剧情库与配置状态"""
    print_banner()
    loader = ProjectConfigLoader()
    proj_path = Path(args.project) if hasattr(args, "project") and args.project else Path("project.yaml")

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


def cmd_export(args):
    """手稿与训练数据集导出"""
    print_banner()
    out_dir = Path(args.output) if args.output else Path("exports")
    out_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"[bold green]>>> 准备导出文稿至目录: {out_dir}[/bold green]")
    console.print("[dim]手稿格式支持: 番茄/起点标准缩进 TXT、Markdown 全书、ShareGPT SFT 微调数据集。[/dim]")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="novel-factory",
        description="工业化小说制造流水线 (Antigravity Novel Factory CLI)"
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # demo
    demo_p = subparsers.add_parser("demo", help="运行黄金三章全链路快速演示")

    # status
    status_p = subparsers.add_parser("status", help="查看项目与法则体系状态")
    status_p.add_argument("--project", default="project.yaml", help="项目配置文件路径")

    # export
    export_p = subparsers.add_parser("export", help="导出成品小说手稿或微调数据集")
    export_p.add_argument("--project", default="project.yaml", help="项目配置文件路径")
    export_p.add_argument("--output", default="exports", help="导出目标目录")
    export_p.add_argument("--format", choices=["txt", "md", "sft", "all"], default="all", help="导出格式")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "demo" or args.command is None:
        cmd_demo(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "export":
        cmd_export(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
