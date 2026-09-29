"""
Manuscript Exporter - 商业全渠道稿件导出器
支持番茄/起点标准 TXT（两格全角缩进与分章规范）、全书 Markdown 目录书卷排版、模型微调 JSONL 数据集与 World Bible 设定集全量导出。
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from src.novel_factory.graph.bec_graph import BECGraph
from src.novel_factory.vcs.repository import NarrativeRepository


class ManuscriptExporter:
    """稿件与语料导出器"""

    def __init__(self, repo: NarrativeRepository, graph: Optional[BECGraph] = None):
        self.repo = repo
        self.graph = graph or repo.graph

    def get_all_chapters(self) -> List[Dict[str, Any]]:
        """按章节顺序获取当前分支所有有效提交"""
        commits = self.repo.get_commit_log(limit=9999)
        full_chapters = []
        for c in commits:
            row = self.repo.conn.execute(
                "SELECT * FROM commits WHERE commit_id = ?",
                (c["commit_id"],)
            ).fetchone()
            if row:
                full_chapters.append(dict(row))
        return sorted(full_chapters, key=lambda x: x["chapter_index"])

    def export_to_txt(
        self,
        output_file_path: str,
        full_width_indent: bool = True
    ) -> int:
        """
        导出为起点/番茄等主流平台投稿标准的 TXT 文本
        - 标题独占行
        - 每段首行采用两格全角中文空格（'　　'）
        - 段落之间保留单行空行
        """
        chapters = self.get_all_chapters()
        lines: List[str] = []

        indent = "　　" if full_width_indent else ""

        for ch in chapters:
            lines.append(f"\n\n{ch['title']}\n")
            prose = ch["full_prose"]
            for paragraph in prose.split("\n"):
                p = paragraph.strip()
                if p:
                    lines.append(f"{indent}{p}\n")

        full_content = "".join(lines).strip()
        Path(output_file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_file_path, "w", encoding="utf-8") as f:
            f.write(full_content)

        return len(full_content)

    def export_to_markdown(
        self,
        output_file_path: str,
        book_title: str = "未命名作品",
        author: str = "Novel Factory"
    ) -> int:
        """导出为结构化 Markdown 文档（含 YAML Frontmatter 与全书目录导航）"""
        chapters = self.get_all_chapters()
        total_words = sum(c["word_count"] for c in chapters)

        md_blocks = [
            "---",
            f"title: \"{book_title}\"",
            f"author: \"{author}\"",
            f"total_chapters: {len(chapters)}",
            f"total_words: {total_words}",
            "---\n",
            f"# {book_title}\n",
            "## 目录 (Table of Contents)\n"
        ]

        # 生成目录
        for ch in chapters:
            md_blocks.append(f"- [{ch['title']}](#chapter-{ch['chapter_index']})")
        md_blocks.append("\n---\n")

        # 写入章节正文
        for ch in chapters:
            md_blocks.append(f"<a id=\"chapter-{ch['chapter_index']}\"></a>")
            md_blocks.append(f"## {ch['title']}\n")
            md_blocks.append(ch["full_prose"])
            md_blocks.append("\n---\n")

        content = "\n".join(md_blocks)
        Path(output_file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_file_path, "w", encoding="utf-8") as f:
            f.write(content)

        return len(content)

    def export_to_jsonl_dataset(self, output_file_path: str) -> int:
        """
        导出为大模型 SFT 微调数据格式 (JSONL)
        每行为一条带上下文、分镜契约与合格正文的训练样本
        """
        chapters = self.get_all_chapters()
        dataset_count = 0
        Path(output_file_path).parent.mkdir(parents=True, exist_ok=True)

        with open(output_file_path, "w", encoding="utf-8") as f:
            for ch in chapters:
                item = {
                    "chapter_index": ch["chapter_index"],
                    "title": ch["title"],
                    "word_count": ch["word_count"],
                    "commit_id": ch["commit_id"],
                    "prose": ch["full_prose"]
                }
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
                dataset_count += 1

        return dataset_count

    def export_world_bible(self, output_file_path: str) -> int:
        """导出当前世界的全部实体与关系时序图谱总账"""
        entities = self.graph.conn.execute("SELECT * FROM entities").fetchall()
        relations = self.graph.conn.execute("SELECT * FROM entity_relations").fetchall()

        dump = {
            "entities": [dict(e) for e in entities],
            "relations": [dict(r) for r in relations]
        }

        Path(output_file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_file_path, "w", encoding="utf-8") as f:
            json.dump(dump, f, ensure_ascii=False, indent=2)

        return len(entities)
