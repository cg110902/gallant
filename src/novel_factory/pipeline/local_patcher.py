"""
Local Patcher - 节拍局部打补丁与微创重绘引擎 (AST / Anchor-based Local Patching)
拒绝全章推倒重写带来的次生灾害与Token浪费；精准定位质检失败的单分镜节拍，进行原位无缝缝合与差分修复。
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class ChapterBeatSegment:
    beat_id: str
    beat_index: int
    content: str


class PatchAlignmentError(Exception):
    """补丁对齐或锚点缺失异常"""
    pass


class LocalPatcher:
    """章节节拍局部补丁管理器"""

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
    ) -> str:
        """
        原位替换目标 Beat，保持其余所有 Beat 100% 文本与格式不变
        """
        pattern = re.compile(
            rf"(<!--\s*BEAT_START:\s*{re.escape(target_beat_id)}\s*-->\s*)(.*?)(\s*<!--\s*BEAT_END:\s*{re.escape(target_beat_id)}\s*-->)",
            re.DOTALL
        )
        if not pattern.search(full_text_with_anchors):
            raise PatchAlignmentError(f"未在章节中定位到目标节拍锚点: {target_beat_id}")

        replacement = rf"\g<1>{new_beat_content.strip()}\g<3>"
        return pattern.sub(replacement, full_text_with_anchors, count=1)

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
        post_condition_reminders: List[str]
    ) -> str:
        """
        生成高精度局部重绘 Prompt，强制模型只修改缺陷行，杜绝发散
        """
        violations_str = "\n".join([f"- [违规项]: {m}" for m in violation_messages])
        reminders_str = "\n".join([f"- [必须满足]: {r}" for r in post_condition_reminders])

        return f"""【局部微创打补丁任务 - 节拍 {target_beat_id}】
前序紧邻上下文摘要:
\"\"\"{preceding_context[-300:]}\"\"\"

需要修补的原草稿片段:
\"\"\"{original_beat_text}\"\"\"

【必须清洗修复的违规点】:
{violations_str}

【必须强制达成的后置契约】:
{reminders_str}

【修补准则】:
1. 保持整体场景动作流程与关键结果绝对不变；
2. 原位剔除上述违规的说教、套话或逻辑冲突，替换为具体的视听动词或环境细节；
3. 直接输出重构后的纯正文，严禁包含任何前言或解释。"""
