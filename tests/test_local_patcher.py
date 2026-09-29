"""
Tests for Local Patcher - 单节拍局部微创打补丁测试
"""

import pytest
from src.novel_factory.pipeline.local_patcher import (
    ChapterBeatSegment,
    LocalPatcher,
    PatchAlignmentError,
)


def test_segment_assembly_and_extraction():
    """测试带锚点章节组装与逆向拆解提取"""
    patcher = LocalPatcher()

    segments = [
        ChapterBeatSegment("ch01_beat01", 1, "第一拍内容：主角遭遇挑衅。"),
        ChapterBeatSegment("ch01_beat02", 2, "第二拍内容：对手自以为得计。"),
        ChapterBeatSegment("ch01_beat03", 3, "第三拍内容：一招反杀惊艳全场。")
    ]

    formatted_text = patcher.format_segmented_chapter(segments)
    assert "<!-- BEAT_START: ch01_beat01 -->" in formatted_text
    assert "<!-- BEAT_END: ch01_beat03 -->" in formatted_text

    extracted = patcher.extract_segments(formatted_text)
    assert len(extracted) == 3
    assert extracted[0].beat_id == "ch01_beat01"
    assert extracted[1].content == "第二拍内容：对手自以为得计。"


def test_patch_single_beat_preserves_others():
    """测试局部仅替换单个 Beat，其余 Beat 100% 保持完全不变"""
    patcher = LocalPatcher()

    initial_segments = [
        ChapterBeatSegment("ch01_beat01", 1, "开头：风起云涌。"),
        ChapterBeatSegment("ch01_beat02", 2, "中间：存在严重AI说教的糟糕段落。"),
        ChapterBeatSegment("ch01_beat03", 3, "结尾：悬念留存。")
    ]
    raw_chapter = patcher.format_segmented_chapter(initial_segments)

    # 针对 beat02 执行局部打补丁替换
    new_beat_02 = "中间重构：没有说教，只有利落拔刀与刀锋破空之声。"
    patched_chapter = patcher.patch_single_beat(
        full_text_with_anchors=raw_chapter,
        target_beat_id="ch01_beat02",
        new_beat_content=new_beat_02
    )

    # 提取验证
    extracted_after = patcher.extract_segments(patched_chapter)
    assert len(extracted_after) == 3
    # beat01 和 beat03 毫发无损
    assert extracted_after[0].content == "开头：风起云涌。"
    assert extracted_after[1].content == new_beat_02
    assert extracted_after[2].content == "结尾：悬念留存。"


def test_render_clean_prose():
    """测试去除所有内部锚点导出最终纯净文本"""
    patcher = LocalPatcher()
    segments = [
        ChapterBeatSegment("b1", 1, "第一段。"),
        ChapterBeatSegment("b2", 2, "第二段。")
    ]
    raw_text = patcher.format_segmented_chapter(segments)
    clean = patcher.render_clean_prose(raw_text)

    assert "BEAT_START" not in clean
    assert "BEAT_END" not in clean
    assert "第一段。" in clean
    assert "第二段。" in clean


def test_patch_nonexistent_beat_raises():
    """测试替换不存在的节拍抛出对齐异常"""
    patcher = LocalPatcher()
    raw_text = "<!-- BEAT_START: b1 -->内容<!-- BEAT_END: b1 -->"

    with pytest.raises(PatchAlignmentError):
        patcher.patch_single_beat(raw_text, "non_existent_beat", "新内容")
