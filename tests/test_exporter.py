import json
import os
import tempfile
from pathlib import Path
import pytest
from src.novel_factory.export.manuscript_exporter import ManuscriptExporter
from src.novel_factory.graph.bec_graph import BECGraph
from src.novel_factory.schemas.commit import StateDelta
from src.novel_factory.vcs.repository import NarrativeRepository


@pytest.fixture
def populated_repo():
    graph = BECGraph(":memory:")
    graph.register_entity("char_lin", "CHARACTER", "林动", created_chapter=1, initial_payload={"realm": "淬体三重"})
    repo = NarrativeRepository(db_path=":memory:", graph=graph)
    
    # 提交第 1 章
    prose_1 = (
        "后山水池冰凉刺骨。\n"
        "少年咬牙坚持，汗水混杂着水珠滚落。\n"
        "忽然，池底深处泛起一抹温润的紫芒。"
    )
    repo.commit_chapter(1, "第一章 淬体池奇变", prose_1, StateDelta(chapter_index=1), qc_metrics={"score": 92.0})

    # 提交第 2 章
    prose_2 = (
        "青阳镇林家大院人声鼎沸。\n"
        "演武场中央，林山面色桀骜，眼神阴冷。\n"
        "林动缓步登台，神色波澜不惊。"
    )
    repo.commit_chapter(2, "第二章 演武争端", prose_2, StateDelta(chapter_index=2), qc_metrics={"score": 88.5})

    yield repo, graph
    repo.close()


def test_export_to_txt_standard_indent(populated_repo):
    """测试番茄/起点两格全角缩进 TXT 导出"""
    repo, graph = populated_repo
    exporter = ManuscriptExporter(repo=repo, graph=graph)

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        tmp_txt = f.name

    try:
        char_count = exporter.export_to_txt(tmp_txt, full_width_indent=True)
        assert char_count > 0

        with open(tmp_txt, "r", encoding="utf-8") as f:
            content = f.read()

        assert "第一章 淬体池奇变" in content
        assert "第二章 演武争端" in content
        # 验证全角空格缩进（'　　'）
        assert "　　后山水池冰凉刺骨。" in content
        assert "　　青阳镇林家大院人声鼎沸。" in content
    finally:
        if os.path.exists(tmp_txt):
            os.remove(tmp_txt)


def test_export_to_markdown_with_toc(populated_repo):
    """测试带 Frontmatter 与超链接目录的 Markdown 导出"""
    repo, graph = populated_repo
    exporter = ManuscriptExporter(repo=repo, graph=graph)

    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
        tmp_md = f.name

    try:
        length = exporter.export_to_markdown(tmp_md, book_title="武动乾坤前传", author="天蚕土豆")
        assert length > 0

        with open(tmp_md, "r", encoding="utf-8") as f:
            content = f.read()

        assert 'title: "武动乾坤前传"' in content
        assert 'author: "天蚕土豆"' in content
        assert "## 目录 (Table of Contents)" in content
        assert "[第一章 淬体池奇变](#chapter-1)" in content
        assert '<a id="chapter-1"></a>' in content
        assert "## 第一章 淬体池奇变" in content
    finally:
        if os.path.exists(tmp_md):
            os.remove(tmp_md)


def test_export_to_sft_jsonl_dataset(populated_repo):
    """OpenAI messages 格式的 SFT 数据集"""
    repo, graph = populated_repo
    exporter = ManuscriptExporter(repo=repo, graph=graph)

    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        tmp_jsonl = f.name

    try:
        count = exporter.export_to_jsonl_dataset(tmp_jsonl, format_style="openai")
        assert count == 2

        with open(tmp_jsonl, "r", encoding="utf-8") as f:
            lines = [json.loads(l) for l in f.readlines()]

        assert len(lines) == 2
        item1 = lines[0]
        assert "messages" in item1
        assert len(item1["messages"]) == 3
        assert item1["messages"][0]["role"] == "system"
        assert item1["messages"][1]["role"] == "user"
        assert item1["messages"][2]["role"] == "assistant"
        assert "第一章 淬体池奇变" in item1["messages"][1]["content"]
        assert "后山水池冰凉刺骨" in item1["messages"][2]["content"]
        assert item1["metadata"]["qc_metrics"]["score"] == 92.0
    finally:
        if os.path.exists(tmp_jsonl):
            os.remove(tmp_jsonl)


def test_export_world_bible(populated_repo):
    """世界设定集必须是人类可读的 Markdown，而不是 JSON 倾倒"""
    repo, graph = populated_repo
    exporter = ManuscriptExporter(repo=repo, graph=graph)

    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
        tmp_md = f.name

    try:
        char_count = exporter.export_world_bible(tmp_md)
        # 返回值口径与其它导出器一致：字符数
        assert char_count > 0

        content = open(tmp_md, "r", encoding="utf-8").read()
        assert len(content) == char_count
        assert content.startswith("# 世界观设定集")
        assert "char_lin" in content
        # 不得再是裸 JSON
        with pytest.raises(json.JSONDecodeError):
            json.loads(content)
    finally:
        if os.path.exists(tmp_md):
            os.remove(tmp_md)


def test_export_world_bible_handles_empty_graph(tmp_path):
    """空图谱不应产出空文件或崩溃"""
    from src.novel_factory.graph.bec_graph import BECGraph
    from src.novel_factory.vcs.repository import NarrativeRepository

    g = BECGraph(":memory:")
    r = NarrativeRepository(db_path=":memory:", graph=g)
    exporter = ManuscriptExporter(repo=r, graph=g)
    out = tmp_path / "wb.md"
    n = exporter.export_world_bible(str(out))
    assert n > 0
    assert "尚无任何实体" in out.read_text(encoding="utf-8")
    r.close()


def test_sharegpt_format_uses_conversations_schema(populated_repo, tmp_path):
    """
    此前 format_style='sharegpt' 却输出 OpenAI 的 messages 字段。
    直接喂给按 ShareGPT 解析的训练脚本会全量丢样本——格式名必须与结构一致。
    """
    repo, graph = populated_repo
    exporter = ManuscriptExporter(repo=repo, graph=graph)
    out = tmp_path / "sharegpt.jsonl"

    exporter.export_to_jsonl_dataset(str(out), format_style="sharegpt")
    items = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]

    assert "conversations" in items[0]
    assert "messages" not in items[0]
    roles = [m["from"] for m in items[0]["conversations"]]
    assert roles == ["system", "human", "gpt"]
    assert all("value" in m for m in items[0]["conversations"])


def test_only_passed_filters_rejected_chapters(populated_repo, tmp_path):
    """把没过质检的稿子喂进微调数据，等于主动污染数据飞轮"""
    repo, graph = populated_repo
    with repo.conn:
        repo.conn.execute(
            "UPDATE commits SET qc_metrics_json = ? WHERE chapter_index = 1",
            (json.dumps({"chapter_qc_passed": False}),),
        )
    exporter = ManuscriptExporter(repo=repo, graph=graph)

    out_all = tmp_path / "all.jsonl"
    out_ok = tmp_path / "ok.jsonl"
    assert exporter.export_to_jsonl_dataset(str(out_all)) == 2
    assert exporter.export_to_jsonl_dataset(str(out_ok), only_passed=True) == 1
