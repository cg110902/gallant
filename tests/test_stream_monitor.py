import asyncio
import pytest
from src.novel_factory.pipeline.stream_monitor import (
    StreamMonitor,
    DegenerationType,
    StreamChunkResult,
)


def test_stream_monitor_normal_flow():
    """测试正常流式输入不发生误中断"""
    monitor = StreamMonitor(min_loop_phrase_length=5, max_allowed_repetitions=3)

    chunks = ["暴风雨呼啸过城市，", "霓虹在积水中破碎闪烁。", "探员裹紧了身上的风衣。"]
    for c in chunks:
        res = monitor.feed_chunk(c)
        assert res.is_aborted is False
        assert res.chunk_text == c
    assert "探员裹紧了身上的风衣。" in monitor.get_full_buffer()


def test_stream_monitor_exact_period_loop():
    """测试流式短语死循环复读时即时触发硬熔断并提取干净前文"""
    monitor = StreamMonitor(min_loop_phrase_length=6, max_allowed_repetitions=3)

    monitor.feed_chunk("枪声骤然在古巷响起。子弹贯穿了夜空。")
    
    # 模拟流式生成进入死循环
    loop_token = "子弹在夜空中呼啸"
    monitor.feed_chunk(loop_token)
    monitor.feed_chunk(loop_token)
    res_final = monitor.feed_chunk(loop_token)

    assert res_final.is_aborted is True
    assert res_final.degeneration_type == DegenerationType.EXACT_PERIOD_LOOP
    assert "触发流式防流口水硬熔断" in res_final.abort_reason

    # 验证提取出的干净正文剔除了死循环尾巴
    clean_text = monitor.get_clean_text()
    assert clean_text == "枪声骤然在古巷响起。子弹贯穿了夜空。"
    assert loop_token not in clean_text


def test_stream_monitor_character_runaway():
    """测试连续标点/单字失控狂奔拦截"""
    monitor = StreamMonitor(max_character_runaway=8)
    
    res1 = monitor.feed_chunk("林动愣在了原地")
    assert res1.is_aborted is False
    
    res2 = monitor.feed_chunk("............")  # 12 个连续点
    assert res2.is_aborted is True
    assert res2.degeneration_type == DegenerationType.CHARACTER_RUNAWAY
    assert "触发字符狂奔熔断" in res2.abort_reason


def test_stream_monitor_sliding_ngram_collapse():
    """测试滑动窗口局部高频震荡塌陷"""
    monitor = StreamMonitor(sliding_window_size=80)
    
    # 在 80 字符滑窗内高频插入四字短语 "恐怖如斯"
    repeating_seq = "恐怖如斯！萧炎展现的实力恐怖如斯，众人皆惊叹恐怖如斯，威势简直恐怖如斯！"
    res = monitor.feed_chunk(repeating_seq)
    
    assert res.is_aborted is True
    assert res.degeneration_type == DegenerationType.SLIDING_NGRAM_COLLAPSE


def test_stream_monitor_sync_wrapper():
    """测试同步生成器包装器在熔断点截断"""
    monitor = StreamMonitor(min_loop_phrase_length=5, max_allowed_repetitions=2)
    raw_stream = ["第一段正常。", "死循环短语A", "死循环短语A", "这句永远不该被执行到"]
    
    yielded = list(monitor.wrap_stream(raw_stream))
    assert len(yielded) == 3
    assert yielded[-1].is_aborted is True
    assert "这句永远不该被执行到" not in [r.chunk_text for r in yielded]


def test_stream_monitor_async_wrapper():
    """测试异步流生成器包装器"""
    monitor = StreamMonitor(max_character_runaway=5)
    
    async def run_test():
        async def sample_async_gen():
            yield "正常开始。"
            yield "？？？？？？"
            yield "被截断的内容"
            
        results = []
        async for item in monitor.wrap_async_stream(sample_async_gen()):
            results.append(item)
        return results

    results = asyncio.run(run_test())
    assert len(results) == 2
    assert results[-1].is_aborted is True
