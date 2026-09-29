"""
CLI 全命令端到端测试

此前 CLI 文档宣称 6 个命令、实现 3 个、export 只打印一行字。
本测试确保每个命令都真实可执行且产生真实副作用。
"""

import json
from pathlib import Path
import re

import pytest

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def plain(text: str) -> str:
    """剥离 Rich 输出的 ANSI 控制序列，便于稳定断言"""
    return _ANSI_RE.sub("", text)

from src.novel_factory.cli.main import build_parser, main
from src.novel_factory.orchestrator import NovelFactoryOrchestrator
from src.novel_factory.schemas.beat import BeatContract, CameraAngle, PacingType
from src.novel_factory.schemas.commit import StateDelta


PROSE = (
    "酸雨泼在青石地面上，腐蚀出白色的泡沫。\n"
    "他的指尖压在解码器边缘，指节泛白。\n"
    "巷口的流浪汉抬起头，瞳孔骤然收缩。\n"
    "他心里飞快盘算着退路。\n"
    "远处的霓虹在雨幕里扭曲成一片血红。\n"
)


@pytest.fixture
def seeded_db(tmp_path: Path) -> str:
    """构造一个含三章真实提交的生产数据库"""
    db = str(tmp_path / "novel.db")
    orch = NovelFactoryOrchestrator(
        db_path=db, llm_worker=lambda s, u: PROSE * 3, enforce_governance=False
    )
    orch.contract_auditor.enforce_word_count = False
    orch.contract_auditor.enforce_camera_coverage = False
    orch.register_entity("char_a", "CHARACTER", "零号", created_chapter=1)

    for ch in (1, 2, 3):
        beat = BeatContract(
            beat_id=f"ch{ch:02d}_b01", chapter_index=ch, beat_index=1,
            target_words=300, pacing_type=PacingType.BUILD_UP,
            required_camera_angles=[CameraAngle.POV],
            characters_present=["char_a"], location_id="loc_1",
        )
        orch.produce_chapter(ch, f"第 {ch} 章", [beat], [], StateDelta(chapter_index=ch))
    orch.close()
    return db


# ---------- 解析器完整性 ----------

def test_all_documented_commands_are_registered():
    parser = build_parser()
    actions = [a for a in parser._actions if a.dest == "command"]
    registered = set(actions[0].choices.keys())
    expected = {"demo", "produce", "status", "rollback", "export", "inspect",
                "govern", "resume", "workbench", "outline"}
    assert expected == registered


# ---------- export 必须真的落盘 ----------

def test_export_actually_writes_files(seeded_db, tmp_path: Path, capsys):
    out = tmp_path / "exports"
    main(["export", "--db", seeded_db, "--output", str(out), "--format", "all"])

    txt = out / "manuscript_submission.txt"
    md = out / "full_book.md"
    sft = out / "sft_dataset.jsonl"

    assert txt.exists() and txt.stat().st_size > 0
    assert md.exists() and md.stat().st_size > 0
    assert sft.exists() and sft.stat().st_size > 0

    # 投稿 TXT 必须使用两格全角缩进
    content = txt.read_text(encoding="utf-8")
    assert "　　" in content
    # Markdown 必须含 frontmatter 与目录
    md_content = md.read_text(encoding="utf-8")
    assert md_content.startswith("---")
    assert "## 目录" in md_content
    # SFT 必须是合法 JSONL
    for line in sft.read_text(encoding="utf-8").strip().split("\n"):
        json.loads(line)


def test_export_single_format(seeded_db, tmp_path: Path):
    out = tmp_path / "exports"
    main(["export", "--db", seeded_db, "--output", str(out), "--format", "txt"])
    assert (out / "manuscript_submission.txt").exists()
    assert not (out / "full_book.md").exists()


def test_export_without_db_fails_gracefully(tmp_path: Path, capsys):
    main(["export", "--db", str(tmp_path / "nope.db"), "--output", str(tmp_path / "o")])
    assert "找不到生产数据库" in plain(capsys.readouterr().out)


# ---------- produce ----------

def test_produce_writes_journal_and_commits(tmp_path: Path):
    db = str(tmp_path / "p.db")
    journal = tmp_path / "j.json"
    main([
        "produce", "--db", db, "--journal", str(journal),
        "--start", "1", "--end", "2", "--no-governance",
    ])
    assert journal.exists()
    data = json.loads(journal.read_text(encoding="utf-8"))
    assert set(data["jobs"].keys()) == {"1", "2"}

    orch = NovelFactoryOrchestrator(db_path=db)
    assert len(orch.repo.get_commit_log()) == 2
    orch.close()


def test_produce_resumes_from_journal(tmp_path: Path, capsys):
    """已完成的章节必须被跳过，并明确提示断点续产位置（不得重复烧钱）"""
    from src.novel_factory.runtime.resume import JobStatus, ProductionJournal

    db = str(tmp_path / "p.db")
    journal = tmp_path / "j.json"

    # 预置一段"已完成"的生产历史，模拟上一次运行中途被杀
    seed = ProductionJournal(journal)
    for ch in (1, 2):
        seed.mark(ch, status=JobStatus.COMPLETED, word_count=2000)

    main(["produce", "--db", db, "--journal", str(journal), "--start", "1", "--end", "4",
          "--no-governance"])
    out = plain(capsys.readouterr().out)

    assert "断点续产" in out
    assert "将从第 3 章" in out
    # 前两章不得被重跑
    assert "第 1 章 ->" not in out and "第 2 章 ->" not in out

    data = json.loads(journal.read_text(encoding="utf-8"))
    assert data["jobs"]["1"]["status"] == "COMPLETED"
    assert set(data["jobs"].keys()) == {"1", "2", "3", "4"}


# ---------- rollback ----------

def test_rollback_moves_head(seeded_db, capsys):
    main(["rollback", "--db", seeded_db, "--chapter", "2"])
    assert "已回滚至第 2 章" in plain(capsys.readouterr().out)

    orch = NovelFactoryOrchestrator(db_path=seeded_db)
    assert orch.repo.get_head_commit().chapter_index == 2
    orch.close()


def test_rollback_to_missing_chapter_reports_error(seeded_db, capsys):
    main(["rollback", "--db", seeded_db, "--chapter", "99"])
    assert "回滚失败" in plain(capsys.readouterr().out)


def test_rollback_list_branches(seeded_db, capsys):
    main(["rollback", "--db", seeded_db, "--list-branches"])
    assert "剧情分支" in plain(capsys.readouterr().out)


# ---------- inspect / govern / status / resume ----------

def test_inspect_reports_metrics(seeded_db, capsys):
    main(["inspect", "--db", seeded_db])
    out = plain(capsys.readouterr().out)
    assert "章节质检指标总览" in out
    assert "SimHash 指纹" in out


def test_inspect_single_chapter(seeded_db, capsys):
    main(["inspect", "--db", seeded_db, "--chapter", "2"])
    assert "章节质检指标总览" in plain(capsys.readouterr().out)


def test_govern_runs_full_sweep(seeded_db, capsys):
    main(["govern", "--db", seeded_db, "--window", "5"])
    out = plain(capsys.readouterr().out)
    assert "章末钩子强度趋势" in out
    assert "爽点密度曲线" in out
    assert "伏笔台账" in out
    assert "角色命名冲突扫描" in out


def test_status_shows_commit_tree(seeded_db, capsys):
    main(["status", "--db", seeded_db])
    out = plain(capsys.readouterr().out)
    assert "项目名称" in out
    assert "最近提交" in out


def test_resume_lists_jobs(tmp_path: Path, capsys):
    db = str(tmp_path / "p.db")
    journal = tmp_path / "j.json"
    main(["produce", "--db", db, "--journal", str(journal), "--start", "1", "--end", "2",
          "--no-governance"])
    capsys.readouterr()

    main(["resume", "--journal", str(journal)])
    out = plain(capsys.readouterr().out)
    assert "生产日志" in out
    assert "批次生产摘要" in out


def test_resume_reset_marks_chapter_for_rerun(tmp_path: Path, capsys):
    db = str(tmp_path / "p.db")
    journal = tmp_path / "j.json"
    main(["produce", "--db", db, "--journal", str(journal), "--start", "1", "--end", "2",
          "--no-governance"])
    capsys.readouterr()

    main(["resume", "--journal", str(journal), "--reset", "1"])
    assert "已重置第 1 章" in plain(capsys.readouterr().out)
    data = json.loads(journal.read_text(encoding="utf-8"))
    assert data["jobs"]["1"]["status"] == "PENDING"


# ---------- demo ----------

def test_demo_runs_end_to_end(capsys):
    main(["demo"])
    out = plain(capsys.readouterr().out)
    assert "黄金三章试产演示完成" in out
    assert "长程治理巡检" in out
    assert "成功回滚至" in out
