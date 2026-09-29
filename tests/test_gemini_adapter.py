"""
Tests for Gemini Adapter & Antigravity Native Integration
测试针对 Google Gemini 系列模型的原生深度适配特性：
1. GeminiModelFamily 推荐模型矩阵 (3.8-flash, 3.1-pro-preview, 3.5-flash-lite)；
2. 小说创作专属安全配置 (Fiction Safety Profile: 允许武打动作戏，阻断恶意攻击)；
3. 上下文缓存管理 (Context Cache Manager: TTL 与服务端缓存句柄)；
4. 思考预算分配 (Thinking Budget: Director思考充足，Writer高吞吐0延迟)；
5. 原生 Pydantic 结构化输出 (Structured Output via response_json_schema)；
6. 流式吐字与防流口水截断联动 (Streaming with Degeneration Guard)；
7. 百万 Token 全书因果回溯巡检 (Whole-Book Retrospective Consistency Auditor)。
"""

import pytest
from pydantic import BaseModel

from src.novel_factory.llm.client import get_llm_provider
from src.novel_factory.llm.gemini_adapter import (
    FictionSafetyProfile,
    GeminiContextCacheManager,
    GeminiModelFamily,
    GeminiNativeProvider,
    WholeBookAuditFinding,
    WholeBookAuditReport,
)
from src.novel_factory.pipeline.stream_monitor import StreamMonitor


class SimplePydanticContract(BaseModel):
    beat_id: str = "ch01_b01"
    target_words: int = 500
    pacing_tag: str = "BUILD_UP"
    micro_events: list[str] = ["拔剑", "出招"]


def test_gemini_model_matrix_definitions():
    """测试 Gemini 3.x 家族模型矩阵定义规范 (严禁使用已弃用的旧模型)"""
    assert GeminiModelFamily.DIRECTOR.value == "gemini-3.1-pro-preview"
    assert GeminiModelFamily.WRITER.value == "gemini-3.8-flash"
    assert GeminiModelFamily.JUDGE.value == "gemini-3.5-flash-lite"
    assert GeminiModelFamily.IMAGE_GEN.value == "gemini-3-pro-image"


def test_fiction_safety_settings():
    """测试小说动作戏专属安全放宽策略"""
    settings = FictionSafetyProfile.get_fiction_safety_settings()
    # 验证已生成安全策略项
    assert len(settings) == 4
    categories = [s.category.name for s in settings]
    assert "HARM_CATEGORY_DANGEROUS_CONTENT" in categories
    assert "HARM_CATEGORY_HARASSMENT" in categories

    # 验证危险内容阈值为仅阻断高风险 (允许小说内合理武打/兵刃搏杀)
    for s in settings:
        if s.category.name in ("HARM_CATEGORY_DANGEROUS_CONTENT", "HARM_CATEGORY_HARASSMENT"):
            assert s.threshold.name == "BLOCK_ONLY_HIGH"


def test_gemini_context_cache_manager_offline():
    """测试上下文缓存管理器离线降级与句柄管理"""
    mgr = GeminiContextCacheManager(client=None)
    handle = mgr.create_fiction_context_cache(
        world_preamble="世界观法则：凡人无法肉身横渡星系。",
        model=GeminiModelFamily.WRITER.value,
        display_name="test_world_cache"
    )
    # 无在线客户端时优雅降级为 None
    assert handle is None
    assert mgr.get_cache("non_existent") is None


def test_gemini_native_provider_generate():
    """测试 GeminiNativeProvider 基础文本生成与 Token 统计回传"""
    provider = GeminiNativeProvider(default_model=GeminiModelFamily.WRITER.value)
    res = provider.generate(
        system_prompt="你是一位仙侠小说作家。",
        user_prompt="写一段剑光呼啸的动作开场。"
    )
    assert len(res.text) > 0
    assert res.input_tokens > 0
    assert res.output_tokens > 0
    assert "gemini-3.8-flash" in res.model_name


def test_gemini_native_provider_structured_output():
    """测试 Pydantic 结构化实例生成"""
    provider = GeminiNativeProvider()
    parsed, gen_res = provider.generate_structured(
        system_prompt="你是一个分镜导演，输出结构化分镜计划。",
        user_prompt="规划第一章第一拍。",
        response_model=SimplePydanticContract
    )
    assert isinstance(parsed, SimplePydanticContract)
    assert parsed.beat_id == "ch01_b01"
    assert len(parsed.micro_events) >= 1
    assert gen_res.cached_input_tokens >= 0


def test_gemini_streaming_with_drooling_guard():
    """测试流式生成与防流口水截断器联动"""
    provider = GeminiNativeProvider()
    monitor = StreamMonitor()

    clean_text, aborted, reason = provider.generate_stream_with_guard(
        system_prompt="描写夜雨中的暗杀。",
        user_prompt="直接输出正文。",
        stream_monitor=monitor
    )
    assert len(clean_text) > 0
    assert aborted is False
    assert reason is None


def test_gemini_whole_book_retrospective_auditor():
    """测试 Gemini 100万 Token 全书因果一致性大体检"""
    provider = GeminiNativeProvider()

    # 构造跨章节样板书稿
    chapters = [
        (1, "第一章 剑出青阳", "林凡在青阳镇后山得到一枚神秘石符，立下三年之约。"),
        (2, "第二章 仇敌上门", "雷家少爷雷力带领家丁包围林家大院，雷力叫嚣要废掉林凡。"),
        (3, "第三章 一拳之威", "林凡施展九响通背拳，当场将雷力打成重伤吐血昏迷。")
    ]

    report = provider.audit_whole_book_retrospective(
        novel_title="武动神话",
        chapter_manuscripts=chapters
    )

    assert isinstance(report, WholeBookAuditReport)
    assert report.novel_title == "武动神话"
    assert report.total_chapters_audited == 3


def test_get_llm_provider_factory_gemini_dispatch():
    """测试工厂方法正确路由到 GeminiNativeProvider"""
    p = get_llm_provider(provider_type="gemini", model_name="gemini-3.8-flash")
    assert isinstance(p, GeminiNativeProvider)
    assert p.default_model == "gemini-3.8-flash"
