"""
Manuscript Exporter - 商业全渠道稿件导出器与 SFT 数据飞轮管道
支持：
1. 起点/番茄平台投稿标准 TXT（每段两格全角中文缩进 '　　' 与规范空行）；
2. 结构化 Markdown 文档（含 YAML Frontmatter、全书目录超链接导航）；
3. 大模型 SFT 微调数据集自动沉淀（Instruction-Context-Response 标准 ShareGPT / JSONL 格式）；
4. 世界设定集总账 (World Bible JSON) 全量导出。
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
            lines.append(f"\n\n{ch['title']}\n\n")
            prose = ch["full_prose"]
            for paragraph in prose.split("\n"):
                p = paragraph.strip()
                if p:
                    lines.append(f"{indent}{p}\n\n")

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

        # 生成目录超链接
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

    def export_to_jsonl_dataset(
        self,
        output_file_path: str,
        format_style: str = "sharegpt"  # sharegpt or raw
    ) -> int:
        """
        导出为大模型 SFT 微调数据格式 (JSONL)
        自动沉淀优质训练样本，构建数据飞轮
        """
        chapters = self.get_all_chapters()
        dataset_count = 0
        Path(output_file_path).parent.mkdir(parents=True, exist_ok=True)

        with open(output_file_path, "w", encoding="utf-8") as f:
            for ch in chapters:
                if format_style == "sharegpt":
                    item = {
                        "id": f"novel_factory_{ch['commit_id'][:10]}",
                        "messages": [
                            {
                                "role": "system",
                                "content": "你是一名工业级网文主笔作家，严格遵循机位调度与微事件推进，杜绝空洞说教。"
                            },
                            {
                                "role": "user",
                                "content": f"请为小说创作章节【{ch['title']}】的正文内容。"
                            },
                            {
                                "role": "assistant",
                                "content": ch["full_prose"]
                            }
                        ],
                        "metadata": {
                            "chapter_index": ch["chapter_index"],
                            "word_count": ch["word_count"],
                            "qc_metrics": json.loads(ch.get("qc_metrics_json") or "{}")
                        }
                    }
                else:
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
        """
        导出人类可读的世界观设定集 (Markdown)。

        早期实现把原始 JSON 倾倒进 .md 文件，并返回实体数量——
        既不是设定集，返回值口径也与其它导出器（返回字符数）不一致。
        """
        entities = [dict(e) for e in self.graph.conn.execute(
            "SELECT * FROM entities ORDER BY entity_type, created_chapter"
        ).fetchall()]
        relations = [dict(r) for r in self.graph.conn.execute(
            "SELECT * FROM entity_relations ORDER BY source_id, valid_from_chapter"
        ).fetchall()]

        by_type: Dict[str, List[Dict[str, Any]]] = {}
        for e in entities:
            by_type.setdefault(e.get("entity_type") or "UNKNOWN", []).append(e)

        type_labels = {
            "CHARACTER": "人物", "ITEM": "物品道具", "LOCATION": "地点",
            "FACTION": "势力组织", "SYSTEM_RULE": "世界法则", "UNKNOWN": "其它",
        }

        lines: List[str] = [
            "# 世界观设定集 (World Bible)",
            "",
            f"> 自动生成自叙事图谱 | 实体 {len(entities)} 个 | 关系 {len(relations)} 条",
            "",
        ]

        for etype, items in by_type.items():
            lines.append(f"## {type_labels.get(etype, etype)}（{len(items)}）")
            lines.append("")
            for e in items:
                status = "存活" if e.get("is_alive") else "已阵亡"
                lines.append(f"### {e.get('name') or e.get('entity_id')}")
                lines.append("")
                lines.append(f"- **ID**: `{e.get('entity_id')}`")
                lines.append(f"- **状态**: {status}")
                lines.append(f"- **首次登场**: 第 {e.get('created_chapter')} 章")
                try:
                    payload = json.loads(e.get("current_payload_json") or "{}")
                except (json.JSONDecodeError, TypeError):
                    payload = {}
                for k, v in payload.items():
                    lines.append(f"- **{k}**: {v}")

                owned = [r for r in relations if r.get("source_id") == e.get("entity_id")]
                if owned:
                    lines.append("- **关系**:")
                    for r in owned:
                        end = r.get("valid_to_chapter")
                        span = (
                            f"第{r.get('valid_from_chapter')}章起"
                            if end is None or end >= 999999
                            else f"第{r.get('valid_from_chapter')}~{end}章"
                        )
                        lines.append(
                            f"  - {r.get('relation_type')} → `{r.get('target_id')}` ({span})"
                        )
                lines.append("")

        if not entities:
            lines.append("_图谱中尚无任何实体。先注册角色与设定，再导出设定集。_")
            lines.append("")

        content = "\n".join(lines)
        Path(output_file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_file_path, "w", encoding="utf-8") as f:
            f.write(content)

        return len(content)
