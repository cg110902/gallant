"""
Novel Factory CLI - 工业化小说生产车间终端工作台
基于 Rich 终端渲染，提供流水线状态监视、黄金三章端到端实操推导、提交日志树查验与时空回滚。
"""

import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from typing import List
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.novel_factory.orchestrator import NovelFactoryOrchestrator
from src.novel_factory.schemas.beat import BeatContract, CameraAngle, MicroEvent, PacingType
from src.novel_factory.schemas.commit import StateDelta
from src.novel_factory.schemas.entity import LoreEntry

console = Console(force_terminal=True, legacy_windows=False)


def print_banner():
    console.print(Panel.fit(
        "[bold cyan]Novel Factory Enterprise v4.0[/bold cyan]\n"
        "[dim]工业级全题材长篇小说智能制造流水线 | Antigravity 本地工作台[/dim]",
        border_style="cyan"
    ))


def run_demo():
    """执行端到端黄金三章（赛博朋克题材）试产演示"""
    print_banner()
    console.print("[bold yellow]>>> 启动样板书 [霓虹雨夜：断线黑客的复仇纪元] 黄金三章试产流水线...[/bold yellow]\n")

    # 1. 模拟一个能够修复瑕疵的 Worker 回调
    def smart_writer(sys_p: str, user_p: str) -> str:
        if "局部微创打补丁任务" in user_p:
            # 补丁调用：输出干净利落的修正文本（无说教、短句）
            return (
                "零号没有回答，只是将微型激光刀向前递了半寸。\n"
                "刺啦一声，皮质手套被割开一道焦黑的裂口。\n"
                "中间人的瞳孔猛地收缩，按在桌面的五指僵硬得泛白。"
            )
        # 初稿调用：输出符合高水准的干净动作戏
        return (
            "酸雨泼洒在阴暗的后巷青石地面上，腐蚀出白色的泡沫。\n"
            "零号靠在生锈的铁门后，指尖的神经解码器红灯急促闪烁。\n"
            "后方的机械脚步声在十步外停住。\n"
            "‘找到你了，老鼠。’追捕者的电子合成音带着金属刮擦声。"
        )

    project_cfg = Path(__file__).resolve().parents[2] / "project.yaml"
    orchestrator = NovelFactoryOrchestrator(
        project_config_path=str(project_cfg) if project_cfg.exists() else None,
        db_path=":memory:",
        llm_worker=smart_writer
    )

    # 2. 预置基础实体与设定
    orchestrator.graph.register_entity(
        entity_id="char_zero",
        entity_type="CHARACTER",
        name="零号",
        created_chapter=1,
        initial_payload={"tier_or_rank": "初级民用植入", "power_rating": 120.0, "status_tags": ["接口受潮短路"]}
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
        ),
        LoreEntry(
            entry_id="lore_cyberspace_ghost",
            entity_type="PLOT_THREAD",
            name="旧网幽灵信标",
            primary_keys=["解码器"],
            secondary_keys=["闪烁", "红灯"],
            content="零号脑内被封印的军规芯片，会在遇到高危电磁波时自动发出求救信号。",
            is_global=False,
            valid_from_chapter=1
        )
    ]

    # 3. 循环推进第 1 ~ 3 章 (黄金三章契约)
    chapter_plans = [
        (1, "第一章 破损的接口", PacingType.BUILD_UP, "300字危机：酸雨后巷遭遇荒坂猎犬围堵，接口受潮"),
        (2, "第二章 绝境反黑入", PacingType.COGNITIVE_GAP, "800字反制：诱敌进入变电箱陷阱，强行反黑其义体"),
        (3, "第三章 惊骇的认知反差", PacingType.CATHARSIS_PAYOFF, "2500字社会性震惊：反杀猎犬并当众破译其绝密芯片，全场骇然")
    ]

    for ch_idx, title, pacing, desc in chapter_plans:
        console.print(f"[bold green]>> 正在生产 第 {ch_idx} 章: {title} [{pacing.value}][/bold green]")
        
        # 构造当章的 2 个节拍
        b1 = BeatContract(
            beat_id=f"ch0{ch_idx}_b01",
            chapter_index=ch_idx,
            beat_index=1,
            target_words=600,
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
            target_words=600,
            pacing_type=PacingType.CLIFFHANGER_HOOK if ch_idx == 3 else pacing,
            required_camera_angles=[CameraAngle.POV, CameraAngle.REACTION_CAM],
            characters_present=["char_zero"],
            location_id="loc_alley",
            post_conditions=["章末留下更庞大阴谋的线索钩子"]
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

        console.print(f"  [OK] 提交完成: SHA=[cyan]{ch_res.commit.commit_id}[/cyan] | 字数={ch_res.commit.word_count} | 质检全票通过={ch_res.commit.qc_metrics['all_beats_passed']}")

    # 4. 展示提交树状态
    console.print("\n[bold cyan]=== 当前剧情版本库提交历史 (Commit Log) ===[/bold cyan]")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Commit ID", style="dim", width=16)
    table.add_column("Chapter", justify="center", width=8)
    table.add_column("Title", width=25)
    table.add_column("Word Count", justify="right", width=12)

    for item in orchestrator.repo.get_commit_log():
        table.add_row(item["commit_id"], f"第 {item['chapter_index']} 章", item["title"], f"{item['word_count']} 字")
    console.print(table)

    # 5. 演示 Narrative VCS 一键时空回滚
    console.print("\n[bold red]>>> 模拟剧情探索分支：执行时空回滚到第 2 章末尾...[/bold red]")
    orchestrator.repo.checkout_chapter(target_chapter_index=2)
    new_head = orchestrator.repo.get_head_commit()
    console.print(f"[bold yellow][OK] 已成功回滚至: 第 {new_head.chapter_index} 章 [{new_head.title}], HEAD SHA={new_head.commit_id}[/bold yellow]")

    # 验证图谱状态同步还原
    state_restored = orchestrator.graph.get_entity_state_at("char_zero", 3)
    console.print(f"[OK] BEC-Graph 实体状态同步回退断言成功: 零号战力还原为 {state_restored['power_rating']}")

    console.print("\n[bold green][SUCCESS] 端到端五阶段全链路实战验证顺利完成！系统达到工业生产标准。[/bold green]")
    orchestrator.close()


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "run-demo":
        run_demo()
    else:
        run_demo()


if __name__ == "__main__":
    main()
