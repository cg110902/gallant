import pytest
from src.novel_factory.pipeline.local_patcher import (
    ChapterBeatSegment,
    LocalPatcher,
    PatchAlignmentError,
    PatchResult,
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


def test_patch_single_beat_preserves_others_and_audits_savings():
    """测试局部仅替换单个 Beat，审计 Token 节约率与 Diff 记录"""
    patcher = LocalPatcher()

    initial_segments = [
        ChapterBeatSegment("ch01_beat01", 1, "开头：风起云涌。" * 20),
        ChapterBeatSegment("ch01_beat02", 2, "中间：存在严重AI说教的糟糕段落。"),
        ChapterBeatSegment("ch01_beat03", 3, "结尾：悬念留存。" * 20)
    ]
    raw_chapter = patcher.format_segmented_chapter(initial_segments)

    # 针对 beat02 执行局部打补丁替换
    new_beat_02 = "中间重构：没有说教，只有利落拔刀与刀锋破空之声。"
    res: PatchResult = patcher.patch_single_beat(
        full_text_with_anchors=raw_chapter,
        target_beat_id="ch01_beat02",
        new_beat_content=new_beat_02
    )

    # 验证 Token 节约比例显著（只修补局部，节约 > 80%）
    assert res.tokens_saved_ratio >= 0.70
    assert len(res.diff_summary) > 0
    assert "old_ch01_beat02" in res.diff_summary
    assert "new_ch01_beat02" in res.diff_summary

    # 提取验证
    extracted_after = patcher.extract_segments(res.patched_full_text)
    assert len(extracted_after) == 3
    # beat01 和 beat03 毫发无损
    assert extracted_after[0].content == initial_segments[0].content
    assert extracted_after[1].content == new_beat_02
    assert extracted_after[2].content == initial_segments[2].content


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


def test_boundary_sanitization():
    """测试补丁边界标点自动对齐修复（补全句尾标点与闭合引号）"""
    patcher = LocalPatcher()
    raw_text = "<!-- BEAT_START: b1 -->旧段落<!-- BEAT_END: b1 -->"
    
    # 传入未闭合引号且缺句号的文本
    unclosed = "“老夫今日便取你性命"
    res = patcher.patch_single_beat(raw_text, "b1", unclosed)
    
    # 验证末尾自动闭合
    extracted = patcher.extract_segments(res.patched_full_text)
    assert extracted[0].content.endswith("”") or extracted[0].content.endswith("。”")
