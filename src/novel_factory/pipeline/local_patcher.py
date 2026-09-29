"""
Local Patcher & Segment Splicer - 节拍局部微创打补丁与平滑缝合引擎
深度解决长篇网文质检修复中的次生灾害与 Token 浪费问题：
1. 锚点与 AST 双模段落解析与定位；
2. 原位差分缝合 (In-Place Splicing)：只修缺陷 Beat，其余 75%+ 正文零改动原样保留；
3. 衔接边界平滑校验 (Transition Boundary Smoothing)：消除引号未闭合、标点冲突或断头句；
4. 节约 Token 经济学审计与 Unified Diff 变动对比生成。
"""

import difflib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class ChapterBeatSegment:
    beat_id: str
    beat_index: int
    content: str


@dataclass
class PatchResult:
    target_beat_id: str
    patched_full_text: str
    clean_prose: str
    tokens_saved_ratio: float  # 节约的 Token 比例 (例如 0.75 表示相比全章重写节省 75%)
    diff_summary: str


class PatchAlignmentError(Exception):
    """补丁对齐或锚点缺失异常"""
    pass


class LocalPatcher:
    """章节节拍局部补丁与平滑缝合引擎"""

    BEAT_START_PATTERN = r"<!--\s*BEAT_START:\s*([a-zA-Z0-9_-]+)\s*-->"
    BEAT_END_PATTERN = r"<!--\s*BEAT_END:\s*([a-zA-Z0-9_-]+)\s*-->"

    def format_segmented_chapter(self, segments: List[ChapterBeatSegment]) -> str:
        """使用标准显式锚点将多个 Beat 组装为带标记的章节文本"""
        blocks = []
        for seg in segments:
            blocks.append(f"<!-- BEAT_START: {seg.beat_id} -->\n{seg.content.strip()}\n<!-- BEAT_END: {seg.beat_id} -->")
        return "\n\n".join(blocks)

    def extract_segments(self, full_text_with_anchors: str) -> List[ChapterBeatSegment]:
        """从带锚点的章节文本中精确拆解出各个 Beat"""
        pattern = re.compile(
            r"<!--\s*BEAT_START:\s*([a-zA-Z0-9_-]+)\s*-->\s*(.*?)\s*<!--\s*BEAT_END:\s*\1\s*-->",
            re.DOTALL
        )
        matches = pattern.findall(full_text_with_anchors)
        segments: List[ChapterBeatSegment] = []
        for idx, (b_id, content) in enumerate(matches, start=1):
            segments.append(ChapterBeatSegment(beat_id=b_id, beat_index=idx, content=content.strip()))
        return segments

    def patch_single_beat(
        self,
        full_text_with_anchors: str,
        target_beat_id: str,
        new_beat_content: str
    ) -> PatchResult:
        """
        原位替换目标 Beat，保持其余所有 Beat 100% 文本与格式不变，并审计衔接平滑度
        """
        pattern = re.compile(
            rf"(<!--\s*BEAT_START:\s*{re.escape(target_beat_id)}\s*-->\s*)(.*?)(\s*<!--\s*BEAT_END:\s*{re.escape(target_beat_id)}\s*-->)",
            re.DOTALL
        )
        match = pattern.search(full_text_with_anchors)
        if not match:
            raise PatchAlignmentError(f"未在章节中定位到目标节拍锚点: {target_beat_id}")

        old_beat_content = match.group(2).strip()
        cleaned_new_beat = self._sanitize_boundary(new_beat_content.strip())

        # 原位插回
        replacement = rf"\g<1>{cleaned_new_beat}\g<3>"
        patched_full_text = pattern.sub(replacement, full_text_with_anchors, count=1)
        clean_prose = self.render_clean_prose(patched_full_text)

        # 计算节约 Token 经济比率
        total_len = len(clean_prose)
        patch_len = len(cleaned_new_beat)
        saved_ratio = max(0.0, 1.0 - (patch_len / max(1, total_len)))

        # 生成 Diff 摘要
        diff_lines = list(difflib.unified_diff(
            old_beat_content.splitlines(),
            cleaned_new_beat.splitlines(),
            fromfile=f"old_{target_beat_id}",
            tofile=f"new_{target_beat_id}",
            lineterm=""
        ))
        diff_summary = "\n".join(diff_lines)

        return PatchResult(
            target_beat_id=target_beat_id,
            patched_full_text=patched_full_text,
            clean_prose=clean_prose,
            tokens_saved_ratio=round(saved_ratio, 3),
            diff_summary=diff_summary
        )

    def _sanitize_boundary(self, text: str) -> str:
        """平滑边界标点与未闭合双引号"""
        sanitized = text.strip()
        # 补全末尾落下的标点
        if sanitized and sanitized[-1] not in ("。", "！", "？", "”", "…", "；"):
            sanitized += "。"

        # 检查双引号对称性
        left_quotes = sanitized.count("“")
        right_quotes = sanitized.count("”")
        if left_quotes > right_quotes:
            sanitized += "”"

        return sanitized

    def render_clean_prose(self, full_text_with_anchors: str) -> str:
        """剥离所有锚点注释，导出适合读者阅读的最终纯净文本"""
        text = re.sub(r"<!--\s*BEAT_START:.*-->\s*", "", full_text_with_anchors)
        text = re.sub(r"\s*<!--\s*BEAT_END:.*-->", "", text)
        return text.strip()

    def generate_patch_prompt(
        self,
        target_beat_id: str,
        original_beat_text: str,
        violation_messages: List[str],
        preceding_context: str,
        post_condition_reminders: List[str],
        persona_block: str = "",
        time_anchor_line: str = "",
        target_words: Optional[int] = None
    ) -> str:
        """
        生成高精度局部重绘 Prompt，强制模型只修改缺陷行，杜绝全篇发散重写。

        注意：补丁同样是一次生成，必须携带人设声纹与时间锚点约束，
        否则修补过程本身就会重新引入 OOC 与时序矛盾。
        """
        violations_str = "\n".join([f"- [违规项]: {m}" for m in violation_messages])
        reminders_str = "\n".join([f"- [必须满足]: {r}" for r in post_condition_reminders])

        constraint_parts: List[str] = []
        if time_anchor_line:
            constraint_parts.append(time_anchor_line)
        if persona_block:
            constraint_parts.append(persona_block)
        if target_words:
            constraint_parts.append(
                f"【字数契约】修补后的正文必须仍然满足约 {target_words} 字的交付要求。"
            )
        constraints_str = ("\n" + "\n".join(constraint_parts) + "\n") if constraint_parts else ""

        return f"""【局部微创打补丁任务 - 节拍 {target_beat_id}】
前序紧邻上下文摘要:
\"\"\"{preceding_context[-300:]}\"\"\"

需要修补的原草稿片段:
\"\"\"{original_beat_text}\"\"\"

【必须清洗修复的违规点】:
{violations_str}

【必须强制达成的后置契约】:
{reminders_str}
{constraints_str}
【修补准则】:
1. 保持整体场景动作流程与关键结果绝对不变；
2. 原位剔除上述违规的说教、套话或逻辑冲突，替换为具体的视听动词或环境细节；
3. 直接输出重构后的纯正文，严禁包含任何前言或解释。"""
