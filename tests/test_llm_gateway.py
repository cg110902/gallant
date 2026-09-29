import time
import pytest
from src.novel_factory.llm.client import BaseLLMProvider, LLMGenerationResult
from src.novel_factory.llm.gateway import (
    CircuitState,
    GatewayCircuitError,
    GatewayConfig,
    ModelGateway,
)
from src.novel_factory.pipeline.stream_monitor import StreamMonitor


class FlakyFailingProvider(BaseLLMProvider):
    """用于测试重试与熔断机制的模拟异常驱动"""
    def __init__(self, fail_count: int = 2):
        self.fail_count = fail_count
        self.call_count = 0

    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.7, max_tokens: int = 1500) -> LLMGenerationResult:
        self.call_count += 1
        if self.call_count <= self.fail_count:
            raise ConnectionError(f"模拟网络超时异常 (第 {self.call_count} 次)")
        return LLMGenerationResult(
            text="重试成功产出的内容",
            input_tokens=100,
            cached_input_tokens=50,
            output_tokens=20,
            latency_ms=10.0,
            model_name="flaky-mock"
        )


def test_gateway_normal_generation():
    """测试网关正常生成与默认参数透传"""
    config = GatewayConfig(provider_name="mock", model_name="mock-test")
    gateway = ModelGateway(config)

    res = gateway.generate("系统设定", "任务描述")
    assert res.text != ""
    assert res.input_tokens > 0
    assert gateway.circuit_state == CircuitState.CLOSED


def test_gateway_retry_and_backoff_success():
    """测试网络抖动时自动指数退避重试并在第3次成功"""
    config = GatewayConfig(
        provider_name="mock",
        max_retries=3,
        retry_base_delay=0.01  # 测试加速
    )
    gateway = ModelGateway(config)
    flaky = FlakyFailingProvider(fail_count=2)
    gateway.provider = flaky  # 替换为故障模拟驱动

    res = gateway.generate("系统提示", "用户提示")
    assert res.text == "重试成功产出的内容"
    assert flaky.call_count == 3
    assert gateway.circuit_state == CircuitState.CLOSED


def test_gateway_circuit_breaker_trip():
    """测试连续失败超过阈值时触发熔断"""
    config = GatewayConfig(
        provider_name="mock",
        max_retries=1,
        circuit_failure_threshold=2,
        circuit_recovery_timeout=0.2
    )
    gateway = ModelGateway(config)
    always_fail = FlakyFailingProvider(fail_count=999)
    gateway.provider = always_fail

    # 第 1 次彻底失败 (消耗完重试)
    with pytest.raises(RuntimeError):
        gateway.generate("系统", "用户")
    assert gateway.circuit_state == CircuitState.CLOSED  # 失败 1 次 < 2

    # 第 2 次彻底失败 -> 达到阈值 2，触发 OPEN
    with pytest.raises(RuntimeError):
        gateway.generate("系统", "用户")
    assert gateway.circuit_state == CircuitState.OPEN

    # 第 3 次请求应被断路器直接拒收，抛出 GatewayCircuitError 而无需等待网络
    with pytest.raises(GatewayCircuitError) as exc_info:
        gateway.generate("系统", "用户")
    assert "网关已熔断" in str(exc_info.value)

    # 等待冷却超时，断路器进入 HALF_OPEN
    time.sleep(0.25)
    # 修复故障
    always_fail.fail_count = 0
    res_recovered = gateway.generate("系统", "用户")
    assert res_recovered.text == "重试成功产出的内容"
    assert gateway.circuit_state == CircuitState.CLOSED


def test_format_cache_optimized_prompt():
    """测试 Prompt Caching 优化前缀切分"""
    codex = "【天玄大陆世界观】：元力为本，八大祖符镇守天地。"
    task = "写林动在林家后山修炼通背拳，第 1 节拍。"

    system_p, user_p = ModelGateway.format_cache_optimized_prompt(codex, task)
    assert "不可变世界设定" in system_p
    assert codex in system_p
    assert "当前单节拍动态创作任务" in user_p
    assert task in user_p


def test_gateway_stream_mock_with_drool_monitor():
    """测试流式透传结合防流口水截断"""
    gateway = ModelGateway()
    monitor = StreamMonitor(min_loop_phrase_length=5, max_allowed_repetitions=2)

    chunks = [
        "第一句正常。",
        "连续复读短语",
        "连续复读短语",
        "不该输出的后续"
    ]

    emitted = list(gateway.stream_generate_mock(chunks, stream_monitor=monitor))
    assert len(emitted) == 3
    assert "不该输出的后续" not in emitted
