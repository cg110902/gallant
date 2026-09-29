"""
Gemini Adapter & Deep Integration Engine - Antigravity 原生 Gemini 模型深度适配核心
充分挖掘并融合 Google Gemini 系列模型的独有架构特性：
1. 模型矩阵与角色动态路由 (Model Family & Role Router)：
   - Director 编剧智能体 -> gemini-3.1-pro-preview (超强推理与长线因果规划)
   - Writer 主笔智能体 -> gemini-3.8-flash (高速吐字、100万长上下文、移动端排版)
   - Judge 裁判智能体 -> gemini-3.5-flash-lite (极致低延迟、布尔契约质检)
2. 显式与隐式 Prompt Caching (Context Caching 降低 75% 费用与延迟)；
3. 声明式 Pydantic 原生结构化输出 (response_json_schema / 零解析漂移)；
4. 小说战斗/打斗场景专属安全放宽策略 (Creative Writing Fiction Safety Tuning)；
5. 思考预算分配器 (Thinking Budget Allocation: Director思考充足，Writer低延迟吐字)；
6. 100万 Token 全书超长上下文回溯因果审计器 (Whole-Book Retrospective Consistency Auditor)；
7. 原生流式吐字与防流口水截断器联动 (Stream Generation & Degeneration Guard)。
"""

from dataclasses import dataclass
from enum import Enum
import json
import logging
import os
import time
from typing import Any, Callable, Dict, Generator, List, Optional, Type, Union
from pydantic import BaseModel, Field

from src.novel_factory.llm.client import BaseLLMProvider, LLMGenerationResult
from src.novel_factory.pipeline.stream_monitor import StreamChunkResult, StreamMonitor
from src.novel_factory.schemas.beat_contract import BeatContract
from src.novel_factory.qc.llm_judge import JudgeEvaluation

logger = logging.getLogger(__name__)

# 尝试导入官方 modern SDK google-genai
try:
    from google import genai
    from google.genai import types
    from google.genai.types import (
        Content,
        CreateCachedContentConfig,
        GenerateContentConfig,
        HarmBlockThreshold,
        HarmCategory,
        Part,
        SafetySetting,
        ThinkingConfig,
    )
    HAS_GENAI_SDK = True
except ImportError:
    HAS_GENAI_SDK = False


class GeminiModelFamily(str, Enum):
    """Gemini 推荐生产模型矩阵 (禁止使用废弃的 1.5/2.0 模型)"""
    DIRECTOR = "gemini-3.1-pro-preview"   # 深度推理与长线因果规划
    WRITER = "gemini-3.8-flash"          # 高吞吐长篇正文渲染
    JUDGE = "gemini-3.5-flash-lite"      # 极速布尔质检与微创修补
    FAST_LITE = "gemini-3.5-flash-lite"  # 轻量任务
    PRO_REASONING = "gemini-3.1-pro-preview"
    IMAGE_GEN = "gemini-3-pro-image"     # 角色立绘与封面多模态生成


class FictionSafetyProfile:
    """小说创作专属安全策略 (避免激烈战斗/武打动作戏被误杀拦截)"""

    @staticmethod
    def get_fiction_safety_settings() -> List[Any]:
        if not HAS_GENAI_SDK:
            return []
        return [
            SafetySetting(
                category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH
            ),
            SafetySetting(
                category=HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH
            ),
            SafetySetting(
                category=HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH
            ),
            SafetySetting(
                category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE
            )
        ]


@dataclass
class GeminiCacheHandle:
    """Gemini 显式上下文缓存句柄"""
    cache_name: str
    model: str
    display_name: str
    expire_time: Optional[str] = None
    cached_tokens: int = 0


class GeminiContextCacheManager:
    """
    Gemini 原生上下文缓存管理器
    将庞大且静态的【世界观法则 + BEC时态图谱实体名单 + 排版写作军规】缓存于 Google 服务端，
    后续每个节拍生产复用该缓存，输入 Token 享受 75% 价格折让并实现毫秒级响应。
    """

    def __init__(self, client: Optional[Any] = None):
        self.client = client
        self._active_caches: Dict[str, GeminiCacheHandle] = {}

    def create_fiction_context_cache(
        self,
        world_preamble: str,
        model: str = GeminiModelFamily.WRITER.value,
        display_name: str = "novel_factory_world_bible",
        ttl_seconds: int = 7200
    ) -> Optional[GeminiCacheHandle]:
        """为世界观静态上下文创建显式服务端 Cache"""
        if not HAS_GENAI_SDK or not self.client:
            logger.info("google-genai SDK 或客户端未初始化，回退至隐式前缀缓存模式")
            return None

        try:
            config = CreateCachedContentConfig(
                contents=[
                    Content(
                        role="user",
                        parts=[Part.from_text(text=world_preamble)]
                    )
                ],
                system_instruction="你是一尊顶级小说制造引擎，请基于预存的世界观法则与实体档案开展严密创作。",
                display_name=display_name,
                ttl=f"{ttl_seconds}s"
            )
            cached_res = self.client.caches.create(
                model=model,
                config=config
            )
            handle = GeminiCacheHandle(
                cache_name=cached_res.name,
                model=model,
                display_name=display_name,
                expire_time=getattr(cached_res, "expire_time", None)
            )
            self._active_caches[display_name] = handle
            logger.info(f"Gemini 上下文缓存创建成功: {cached_res.name}")
            return handle
        except Exception as e:
            logger.warning(f"创建 Gemini 上下文缓存失败，自动降级为标准请求: {e}")
            return None

    def get_cache(self, display_name: str) -> Optional[GeminiCacheHandle]:
        return self._active_caches.get(display_name)


class WholeBookAuditFinding(BaseModel):
    """全书回溯因果巡检异常项"""
    finding_type: str  # RESURRECTED_ZOMBIE, UNRESOLVED_FORESHADOWING, REALM_REGRESSION, TIMELINE_GAP
    severity: str = "ERROR"
    chapter_range: str
    character_or_item: str
    issue_description: str
    suggested_patch_chapter: int


class WholeBookAuditReport(BaseModel):
    """全书百万 Token 回溯一致性体检报告"""
    novel_title: str
    total_chapters_audited: int
    estimated_tokens_consumed: int
    is_causally_consistent: bool
    findings: List[WholeBookAuditFinding] = Field(default_factory=list)
    narrative_cohesion_score: float = 9.0
    summary: str = ""


class GeminiNativeProvider(BaseLLMProvider):
    """
    Antigravity 原生 Gemini 工业适配提供商
    深度整合：
    1. 动态模型矩阵切换 (gemini-3.8-flash, gemini-3.1-pro-preview, gemini-3.5-flash-lite)；
    2. Thinking Budget 细粒度调控；
    3. Pydantic 结构化输出支持；
    4. 流式防流口水截断；
    5. 小说专用安全免误杀配置。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = GeminiModelFamily.WRITER.value,
        thinking_budget: Optional[int] = None,
        enable_caching: bool = True
    ):
        self.api_key = (
            api_key
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
            or ""
        )
        self.default_model = default_model
        self.thinking_budget = thinking_budget
        self.enable_caching = enable_caching

        self.client = None
        if HAS_GENAI_SDK and self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"初始化 genai.Client 异常: {e}")

        self.cache_manager = GeminiContextCacheManager(client=self.client)

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2500,
        model_override: Optional[str] = None,
        thinking_budget_override: Optional[int] = None,
        cached_content_name: Optional[str] = None
    ) -> LLMGenerationResult:
        """标准小说正文与提示词渲染"""
        model = model_override or self.default_model
        start_t = time.time()

        if HAS_GENAI_SDK and self.client:
            return self._generate_via_sdk(
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                thinking_budget=thinking_budget_override if thinking_budget_override is not None else self.thinking_budget,
                cached_content_name=cached_content_name,
                start_time=start_t
            )
        else:
            return self._generate_via_mock(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model,
                start_time=start_t
            )

    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[BaseModel],
        model_override: Optional[str] = None,
        thinking_budget: int = 1024
    ) -> Tuple[BaseModel, LLMGenerationResult]:
        """
        利用 Gemini 原生 response_json_schema 获得 100% 合法的 Pydantic 数据实例
        专用于 novel_director (大纲节拍契约) 与 novel_judge (盲测布尔矩阵)
        """
        model = model_override or GeminiModelFamily.DIRECTOR.value
        start_t = time.time()

        if HAS_GENAI_SDK and self.client:
            cfg = GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.2,  # 结构化输出需极低采样温度
                response_mime_type="application/json",
                response_json_schema=response_model.model_json_schema(),
                safety_settings=FictionSafetyProfile.get_fiction_safety_settings()
            )
            if thinking_budget > 0:
                cfg.thinking_config = ThinkingConfig(
                    thinking_budget=thinking_budget,
                    include_thoughts=False
                )

            resp = self.client.models.generate_content(
                model=model,
                contents=user_prompt,
                config=cfg
            )
            latency = (time.time() - start_t) * 1000
            json_text = resp.text or "{}"
            parsed_obj = response_model.model_validate_json(json_text)

            usage = getattr(resp, "usage_metadata", None)
            in_t = getattr(usage, "prompt_token_count", 0) if usage else 0
            out_t = getattr(usage, "candidates_token_count", 0) if usage else 0
            cached_t = getattr(usage, "cached_content_token_count", 0) if usage else 0

            gen_result = LLMGenerationResult(
                text=json_text,
                input_tokens=in_t,
                cached_input_tokens=cached_t,
                output_tokens=out_t,
                latency_ms=latency,
                model_name=model
            )
            return parsed_obj, gen_result

        else:
            # 离线环境兜底构造默认实例
            latency = (time.time() - start_t) * 1000
            default_inst = response_model.model_construct()
            gen_result = LLMGenerationResult(
                text="{}",
                input_tokens=100,
                cached_input_tokens=70,
                output_tokens=100,
                latency_ms=latency,
                model_name="mock-gemini-structured"
            )
            return default_inst, gen_result

    def generate_stream_with_guard(
        self,
        system_prompt: str,
        user_prompt: str,
        stream_monitor: Optional[StreamMonitor] = None,
        temperature: float = 0.7,
        max_tokens: int = 2500,
        model_override: Optional[str] = None
    ) -> Tuple[str, bool, Optional[str]]:
        """
        Gemini 流式输出 + 实时防流口水截断联动
        返回: (最终干净文本, 是否触发截断, 截断原因)
        """
        model = model_override or GeminiModelFamily.WRITER.value
        monitor = stream_monitor or StreamMonitor()
        monitor.reset()

        if HAS_GENAI_SDK and self.client:
            cfg = GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=temperature,
                max_output_tokens=max_tokens,
                safety_settings=FictionSafetyProfile.get_fiction_safety_settings(),
                thinking_config=ThinkingConfig(thinking_budget=0)  # 正文生成强制 0 思考延迟
            )
            aborted = False
            abort_reason = None

            for chunk in self.client.models.generate_content_stream(
                model=model,
                contents=user_prompt,
                config=cfg
            ):
                chunk_text = chunk.text or ""
                for ch in chunk_text:
                    res = monitor.feed_chunk(ch)
                    if res.is_aborted:
                        aborted = True
                        abort_reason = res.abort_reason
                        break
                if aborted:
                    break

            return monitor.get_clean_text(), aborted, abort_reason

        else:
            # 离线 Mock
            default_prose = "酸雨敲击着霓虹招牌。\n零号握紧短刀，目光冷冽地扫过长廊。\n阴影里的脚步声戛然而止。"
            for ch in default_prose:
                monitor.feed_chunk(ch)
            return monitor.get_clean_text(), False, None

    def audit_whole_book_retrospective(
        self,
        novel_title: str,
        chapter_manuscripts: List[Tuple[int, str, str]],  # List of (chapter_index, title, prose)
        custom_focus_questions: Optional[List[str]] = None
    ) -> WholeBookAuditReport:
        """
        【Gemini 100万 Token 杀手级特性】：全书因果超长上下文回溯巡检
        可一次性将整部小说前 50~100 章（30~50万字）挂入 Gemini 上下文，执行全书全局因果大体检！
        """
        questions = custom_focus_questions or [
            "死者违规复活 (Zero-Zombie)：是否有前文已明确死亡的角色在后文主动行动或说话？",
            "伏笔遗忘与暗线断裂：前 10 章交代的关键信物或誓言，在后续章节中是否彻底丢失线索？",
            "战力与境界倒退：主角或配角是否出现战力等级或境界无故倒退或逻辑前后冲突？",
            "时空拓扑矛盾：同一角色是否在相隔数万里的两个地点无传送门连续瞬间出现？"
        ]

        # 拼接全书超长正文
        full_book_corpus = []
        for ch_idx, title, prose in chapter_manuscripts:
            full_book_corpus.append(f"=== 第 {ch_idx} 章: {title} ===\n{prose}\n")
        joined_corpus = "\n".join(full_book_corpus)

        user_p = f"""【任务：全书全局因果回溯与长篇一致性巡检】
小说书名: 《{novel_title}》
待巡检总章节数: {len(chapter_manuscripts)} 章

【需重点排查的四大长篇硬伤】:
{chr(10).join(f"{i+1}. {q}" for i, q in enumerate(questions))}

【全书正文全量内容】:
{joined_corpus}
"""
        sys_p = "你是一位最严谨的资深网文总编辑兼长篇因果一致性审查专家，专门使用百万上下文排查大部头小说的长期逻辑崩盘问题。"

        report_obj, _ = self.generate_structured(
            system_prompt=sys_p,
            user_prompt=user_p,
            response_model=WholeBookAuditReport,
            model_override=GeminiModelFamily.DIRECTOR.value,
            thinking_budget=2048
        )
        report_obj.novel_title = novel_title
        report_obj.total_chapters_audited = len(chapter_manuscripts)
        return report_obj

    def _generate_via_sdk(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        thinking_budget: Optional[int],
        cached_content_name: Optional[str],
        start_time: float
    ) -> LLMGenerationResult:
        cfg = GenerateContentConfig(
            system_instruction=system_prompt if not cached_content_name else None,
            temperature=temperature,
            max_output_tokens=max_tokens,
            safety_settings=FictionSafetyProfile.get_fiction_safety_settings(),
            cached_content=cached_content_name
        )
        if thinking_budget is not None and thinking_budget > 0:
            cfg.thinking_config = ThinkingConfig(
                thinking_budget=thinking_budget,
                include_thoughts=False
            )
        elif thinking_budget == 0:
            cfg.thinking_config = ThinkingConfig(thinking_budget=0)

        resp = self.client.models.generate_content(
            model=model,
            contents=user_prompt,
            config=cfg
        )
        latency = (time.time() - start_time) * 1000
        text = resp.text or ""

        usage = getattr(resp, "usage_metadata", None)
        in_t = getattr(usage, "prompt_token_count", 0) if usage else int((len(system_prompt) + len(user_prompt)) / 1.6)
        out_t = getattr(usage, "candidates_token_count", 0) if usage else int(len(text) / 1.6)
        cached_t = getattr(usage, "cached_content_token_count", 0) if usage else 0

        return LLMGenerationResult(
            text=text,
            input_tokens=in_t,
            cached_input_tokens=cached_t,
            output_tokens=out_t,
            latency_ms=latency,
            model_name=model
        )

    def _generate_via_mock(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        start_time: float
    ) -> LLMGenerationResult:
        canned = "酸雨顺着破损的霓虹招牌滴落。\n零号收起微型激光刀，手指没有丝毫晃动。\n暗巷尽头的脚步声戛然而止。"
        in_tokens = int((len(system_prompt) + len(user_prompt)) / 1.6)
        out_tokens = int(len(canned) / 1.6)
        cached_tokens = int(in_tokens * 0.75) if self.enable_caching else 0
        latency = (time.time() - start_time) * 1000

        return LLMGenerationResult(
            text=canned,
            input_tokens=in_tokens,
            cached_input_tokens=cached_tokens,
            output_tokens=out_tokens,
            latency_ms=latency,
            model_name=f"{model}(offline-gemini-adapter)"
        )
