"""
Stream Monitor - 流式生成实时退化与流口水熔断器 (Streaming Repetition Breaker)
在 Token 流式传输过程中实时监测滑动窗口内的字符与短语复读，一旦捕获连续死循环立即主动发出 Hard Abort 截断中断信号。
"""

from dataclasses import dataclass
from typing import Generator, Iterable, List, Optional, Tuple


@dataclass
class StreamChunkResult:
    chunk_text: str
    is_aborted: bool = False
    abort_reason: Optional[str] = None


class StreamMonitor:
    """流式监听器与死循环熔断断路器"""

    def __init__(
        self,
        min_loop_phrase_length: int = 5,
        max_allowed_repetitions: int = 3
    ):
        self.min_loop_len = min_loop_phrase_length
        self.max_reps = max_allowed_repetitions
        self.buffer: str = ""

    def reset(self):
        self.buffer = ""

    def feed_chunk(self, chunk: str) -> StreamChunkResult:
        """
        接收流式输入的新增 Chunk 片段，实时断言是否存在流口水死循环
        """
        self.buffer += chunk

        # 检查缓冲区末尾是否陷入连续重复循环
        if len(self.buffer) >= self.min_loop_len * self.max_reps:
            max_check_len = min(35, len(self.buffer) // self.max_reps)
            for pattern_len in range(self.min_loop_len, max_check_len + 1):
                pattern = self.buffer[-pattern_len:]
                count = 0
                idx = len(self.buffer)

                while idx >= pattern_len and self.buffer[idx - pattern_len:idx] == pattern:
                    count += 1
                    idx -= pattern_len

                if count >= self.max_reps:
                    reason = f"触发流式防流口水硬熔断：短语 [{pattern}] 连续复读 {count} 次"
                    return StreamChunkResult(
                        chunk_text=chunk,
                        is_aborted=True,
                        abort_reason=reason
                    )

        return StreamChunkResult(chunk_text=chunk, is_aborted=False)

    def wrap_stream(
        self,
        stream_generator: Iterable[str]
    ) -> Generator[StreamChunkResult, None, None]:
        """包装原始流式生成器，提供自动阻断保护"""
        self.reset()
        for chunk in stream_generator:
            res = self.feed_chunk(chunk)
            yield res
            if res.is_aborted:
                break
