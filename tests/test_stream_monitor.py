"""
Tests for Stream Monitor - 流式流口水退化熔断测试
"""

from src.novel_factory.pipeline.stream_monitor import StreamMonitor


def test_stream_monitor_normal_flow():
    """测试正常流式输入不发生误中断"""
    monitor = StreamMonitor(min_loop_phrase_length=5, max_allowed_repetitions=3)

    chunks = ["暴风雨呼啸过城市，", "霓虹在积水中破碎闪烁。", "探员裹紧了身上的风衣。"]
    for c in chunks:
        res = monitor.feed_chunk(c)
        assert res.is_aborted is False
        assert res.chunk_text == c


def test_stream_monitor_drooling_abort():
    """测试流式死循环复读时即时触发硬熔断"""
    monitor = StreamMonitor(min_loop_phrase_length=6, max_allowed_repetitions=3)

    # 喂入正常前置
    res1 = monitor.feed_chunk("枪声骤然响起。")
    assert res1.is_aborted is False

    # 模拟流式生成进入死循环
    loop_token = "子弹在夜空中呼啸"
    res2 = monitor.feed_chunk(loop_token)
    assert res2.is_aborted is False
    res3 = monitor.feed_chunk(loop_token)
    assert res3.is_aborted is False

    # 第三次复读 -> 触发熔断
    res4 = monitor.feed_chunk(loop_token)
    assert res4.is_aborted is True
    assert "触发流式防流口水硬熔断" in res4.abort_reason


def test_stream_monitor_generator_wrapper():
    """测试 Generator 封装器自动在熔断时截断流"""
    monitor = StreamMonitor(min_loop_phrase_length=5, max_allowed_repetitions=2)

    raw_stream = ["第一段正常。", "死循环短语A", "死循环短语A", "这句永远不该被执行到"]
    yielded_results = list(monitor.wrap_stream(raw_stream))

    # 应该在第 3 个 chunk 截断停止
    assert len(yielded_results) == 3
    assert yielded_results[-1].is_aborted is True
    assert "这句永远不该被执行到" not in [r.chunk_text for r in yielded_results]
