"""
Stream Monitor - 工业级流式退化监控与防流口水截断器 (Streaming Degeneration & Anti-Drooling Breaker)
在 Token/Chunk 流式传输过程中实时监测滑动窗口内的字符狂奔、短语死循环与语义退化塌陷：
1. 字符狂奔熔断 (Character Runaway)：连续单一标点或字符狂飙（如 ......、？？？？）；
2. 周期短语死循环熔断 (Exact Period Loop)：基于滑动窗口检测短语连续循环；
3. 滑窗 N-Gram 密度塌陷 (Sliding N-Gram Collapse)：滑窗内局部高频震荡；
4. 自动微创尾部修剪 (Clean Tail Truncation)：熔断后自动将残余复读片段截断至最后一个有效句号/分号，保留可用前半段。
"""

from collections import Counter
from dataclasses import dataclass
from enum import Enum
import re
from typing import AsyncGenerator, Generator, Iterable, List, Optional, Tuple


class DegenerationType(str, Enum):
    """退化类型"""
    EXACT_PERIOD_LOOP = "EXACT_PERIOD_LOOP"      # 周期短语死循环
    CHARACTER_RUNAWAY = "CHARACTER_RUNAWAY"      # 标点/单字失控狂奔
    SLIDING_NGRAM_COLLAPSE = "SLIDING_NGRAM_COLLAPSE"  # 滑窗高密度局部震荡


@dataclass
class StreamChunkResult:
    chunk_text: str
    is_aborted: bool = False
    degeneration_type: Optional[DegenerationType] = None
    abort_reason: Optional[str] = None
    repeated_pattern: Optional[str] = None
    clean_tail_offset: int = 0  # 建议截断的尾部字符数


class StreamMonitor:
    """流式监听器与死循环断路器"""

    def __init__(
        self,
        min_loop_phrase_length: int = 5,
        max_allowed_repetitions: int = 3,
        max_character_runaway: int = 10,
        sliding_window_size: int = 120
    ):
        self.min_loop_len = min_loop_phrase_length
        self.max_reps = max_allowed_repetitions
        self.max_char_runaway = max_character_runaway
        self.sliding_window_size = sliding_window_size
        self.buffer: str = ""

    def reset(self):
        """重置内部缓冲区"""
        self.buffer = ""

    def get_full_buffer(self) -> str:
        """获取当前完整接收的文本"""
        return self.buffer

    def get_clean_text(self) -> str:
        """
        获取剔除尾部死循环后的干净文本：
        从末尾往前寻找最后一个完整的标点符号（。！？；”）
        """
        if not self.buffer:
            return ""

        # 逆序搜索句终标点
        delimiters = ["。", "！", "？", "；", "”", "…"]
        last_idx = -1
        for d in delimiters:
            idx = self.buffer.rfind(d)
            if idx > last_idx:
                last_idx = idx

        if last_idx != -1:
            return self.buffer[:last_idx + 1]
        return self.buffer

    def feed_chunk(self, chunk: str) -> StreamChunkResult:
        """
        接收流式输入的新增 Chunk 片段，实时断言是否存在流口水死循环
        """
        self.buffer += chunk

        # 1. 检查单字/标点狂奔 (Character Runaway)
        runaway_match = re.search(r"([^a-zA-Z0-9\s])\1{" + str(self.max_char_runaway) + r",}$", self.buffer)
        if runaway_match:
            char_run = runaway_match.group(0)
            return StreamChunkResult(
                chunk_text=chunk,
                is_aborted=True,
                degeneration_type=DegenerationType.CHARACTER_RUNAWAY,
                abort_reason=f"触发字符狂奔熔断：字符 [{char_run[0]}] 连续出现 {len(char_run)} 次",
                repeated_pattern=char_run[0],
                clean_tail_offset=len(char_run)
            )

        # 2. 检查尾部周期短语死循环 (Exact Period Loop)
        if len(self.buffer) >= self.min_loop_len * self.max_reps:
            max_check_len = min(40, len(self.buffer) // self.max_reps)
            for pattern_len in range(self.min_loop_len, max_check_len + 1):
                pattern = self.buffer[-pattern_len:]
                count = 0
                idx = len(self.buffer)

                while idx >= pattern_len and self.buffer[idx - pattern_len:idx] == pattern:
                    count += 1
                    idx -= pattern_len

                if count >= self.max_reps:
                    abort_tail_len = count * pattern_len
                    reason = f"触发流式防流口水硬熔断：短语 [{pattern}] 连续复读 {count} 次"
                    return StreamChunkResult(
                        chunk_text=chunk,
                        is_aborted=True,
                        degeneration_type=DegenerationType.EXACT_PERIOD_LOOP,
                        abort_reason=reason,
                        repeated_pattern=pattern,
                        clean_tail_offset=abort_tail_len
                    )

        # 3. 检查滑动窗口 N-Gram 密度塌陷 (Sliding N-Gram Collapse)
        # 例如同一 4 字符短语在最近 sliding_window_size 个字符内密集出现 >= 4 次
        if len(self.buffer) >= 25:
            window_text = self.buffer[-self.sliding_window_size:]
            ngram_len = 4
            ngrams = [window_text[i:i+ngram_len] for i in range(len(window_text) - ngram_len + 1)]
            counts = Counter(ngrams)
            for ng, cnt in counts.items():
                if cnt >= 4 and not ng.isspace() and not re.match(r"^[\s，。、]+$", ng):
                    return StreamChunkResult(
                        chunk_text=chunk,
                        is_aborted=True,
                        degeneration_type=DegenerationType.SLIDING_NGRAM_COLLAPSE,
                        abort_reason=f"触发滑窗局部塌陷熔断：四元组 [{ng}] 在 {self.sliding_window_size} 字内密集重复 {cnt} 次",
                        repeated_pattern=ng,
                        clean_tail_offset=len(chunk)
                    )

        return StreamChunkResult(chunk_text=chunk, is_aborted=False)

    def wrap_stream(
        self,
        stream_generator: Iterable[str]
    ) -> Generator[StreamChunkResult, None, None]:
        """同步 Generator 封装器"""
        self.reset()
        for chunk in stream_generator:
            res = self.feed_chunk(chunk)
            yield res
            if res.is_aborted:
                break

    async def wrap_async_stream(
        self,
        async_stream: AsyncGenerator[str, None]
    ) -> AsyncGenerator[StreamChunkResult, None]:
        """异步 AsyncGenerator 封装器"""
        self.reset()
        async for chunk in async_stream:
            res = self.feed_chunk(chunk)
            yield res
            if res.is_aborted:
                break
