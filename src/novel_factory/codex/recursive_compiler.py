"""
Recursive Codex Compiler - 工业级递归与选择性词条级联编译器
深度复刻 SillyTavern World Info 与 NovelCrafter 核心检索哲学：
1. 双键选择性触发 (Selective Dual-Key Matching)：主键命中 + 次级条件键逻辑门 (AND_ANY, AND_ALL, NOT_ANY)；
2. 递归级联触发 (Recursive Scanning)：已激活词条内容注入语料池，引发多层级联引爆（受控 max_depth 深度与拓扑去重）；
3. 优先级预算求解 (Priority Knapsack Packing)：基于 insertion_order 与 Token 硬预算贪心修剪；
4. 全局常驻词条 (Constant World Rules)：核心大纲与法则零延迟全局置顶。
"""

import math
import re
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field


class SelectiveLogic(str, Enum):
    """次级键匹配逻辑门"""
    AND_ANY = "AND_ANY"    # 命中主键 且 命中任一次级键
    AND_ALL = "AND_ALL"    # 命中主键 且 命中全部次级键
    NOT_ANY = "NOT_ANY"    # 命中主键 但 严禁命中任一次级键 (负向排除过滤器)


class CodexEntryCategory(str, Enum):
    """设定分类"""
    CONSTANT_RULE = "CONSTANT_RULE"  # 全局常驻法则
    CHARACTER = "CHARACTER"          # 人物档案
    LOCATION = "LOCATION"            # 地理地缘
    ITEM = "ITEM"                    # 道具装备
    FACTION = "FACTION"              # 势力宗门
    PLOT_THREAD = "PLOT_THREAD"      # 支线暗线


class CodexEntry(BaseModel):
    """Codex 词条规范"""
    entry_id: str
    name: str
    content: str
    constant: bool = False                                      # 是否全局常驻
    primary_keys: List[str] = Field(default_factory=list)       # 一级主键触发词
    secondary_keys: List[str] = Field(default_factory=list)     # 二级条件词
    selective_logic: SelectiveLogic = SelectiveLogic.AND_ANY    # 次级键逻辑
    insertion_order: int = 100                                  # 优先级（数值越小优先级越高）
    category: CodexEntryCategory = CodexEntryCategory.CHARACTER
    enabled: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def estimate_tokens(self, chars_per_token: float = 1.6) -> int:
        """估算本词条消耗的 Token 数"""
        return max(1, math.ceil(len(self.content) / chars_per_token))


class CompiledCodexResult(BaseModel):
    """编译产出的结构化注入包"""
    constant_entries: List[CodexEntry] = Field(default_factory=list)
    activated_entries: List[CodexEntry] = Field(default_factory=list)
    dropped_entries: List[CodexEntry] = Field(default_factory=list)  # 超出预算被裁剪的词条
    total_estimated_tokens: int = 0
    max_budget: int = 3500
    activation_cascade_map: Dict[str, int] = Field(default_factory=dict)  # entry_id -> 触发所在递归深度
    formatted_prompt_block: str = ""


class RecursiveCodexCompiler:
    """递归级联检索编译器"""

    def __init__(
        self,
        token_budget: int = 3500,
        max_recursion_depth: int = 2,
        chars_per_token: float = 1.6
    ):
        self.token_budget = token_budget
        self.max_recursion_depth = max_recursion_depth
        self.chars_per_token = chars_per_token

    def _matches_entry(self, entry: CodexEntry, corpus: str) -> bool:
        """判断词条是否在给定语料库中满足触发条件"""
        if not entry.enabled:
            return False

        # 常驻词条直接无条件触发
        if entry.constant:
            return True

        if not entry.primary_keys:
            return False

        # 1. 检查一级主键 (Primary Keys - OR 关系)
        primary_hit = any(self._contains_key(corpus, k) for k in entry.primary_keys)
        if not primary_hit:
            return False

        # 如果没有配置次级键，则一级键命中即可
        if not entry.secondary_keys:
            return True

        # 2. 检查二级条件键 (Secondary Keys)
        if entry.selective_logic == SelectiveLogic.AND_ANY:
            return any(self._contains_key(corpus, k) for k in entry.secondary_keys)
        elif entry.selective_logic == SelectiveLogic.AND_ALL:
            return all(self._contains_key(corpus, k) for k in entry.secondary_keys)
        elif entry.selective_logic == SelectiveLogic.NOT_ANY:
            return not any(self._contains_key(corpus, k) for k in entry.secondary_keys)

        return True

    @staticmethod
    def _contains_key(corpus: str, key: str) -> bool:
        """大小写不敏感子串/词边界检测"""
        if not key:
            return False
        return key.lower() in corpus.lower()

    def compile(
        self,
        base_corpus: str,
        codex_entries: List[CodexEntry],
        extra_keywords: Optional[List[str]] = None
    ) -> CompiledCodexResult:
        """
        确定性执行递归级联检索并打包
        """
        full_corpus = base_corpus
        if extra_keywords:
            full_corpus += "\n" + " ".join(extra_keywords)

        activated_map: Dict[str, Tuple[CodexEntry, int]] = {}  # entry_id -> (entry, depth)
        constant_entries: List[CodexEntry] = []

        # 0. 抽取所有 Constant 常驻词条
        for entry in codex_entries:
            if entry.enabled and entry.constant:
                constant_entries.append(entry)
                activated_map[entry.entry_id] = (entry, 0)

        # 1. 递归扫描循环 (Depth 1 to max_depth)
        current_depth_corpus = full_corpus
        for depth in range(1, self.max_recursion_depth + 1):
            newly_activated_in_this_depth: List[CodexEntry] = []

            for entry in codex_entries:
                if not entry.enabled:
                    continue
                if entry.entry_id in activated_map:
                    continue  # 已激活过，跳过

                if self._matches_entry(entry, current_depth_corpus):
                    newly_activated_in_this_depth.append(entry)
                    activated_map[entry.entry_id] = (entry, depth)

            if not newly_activated_in_this_depth:
                break  # 没有新词条被级联激活，提前退出

            # 将本层新激活的词条正文扩充进检索语料池，供下一层递归引爆
            current_depth_corpus = "\n".join(e.content for e in newly_activated_in_this_depth)

        # 2. 收集非常驻的动态触发词条
        dynamic_activated: List[CodexEntry] = [
            e for (e, d) in activated_map.values() if not e.constant
        ]

        # 3. 排序策略：insertion_order 升序（数值越小越靠前）
        constant_entries.sort(key=lambda x: x.insertion_order)
        dynamic_activated.sort(key=lambda x: x.insertion_order)

        # 4. Token 预算贪心装配 (Priority Knapsack)
        retained_entries: List[CodexEntry] = []
        dropped_entries: List[CodexEntry] = []
        current_token_count = 0

        # 首先绝对保证 Constant 词条进入
        for ce in constant_entries:
            t = ce.estimate_tokens(self.chars_per_token)
            current_token_count += t
            retained_entries.append(ce)

        # 再依次容纳动态词条
        for de in dynamic_activated:
            t = de.estimate_tokens(self.chars_per_token)
            if current_token_count + t <= self.token_budget:
                current_token_count += t
                retained_entries.append(de)
            else:
                dropped_entries.append(de)

        # 5. 格式化最终 Prompt 注入块
        lines = ["=== 【世界设定与时序知识库 (Codex & World Info)】 ==="]
        if constant_entries:
            lines.append("\n[全局法则 (Constant Rules)]")
            for ce in constant_entries:
                lines.append(f"【{ce.name}】: {ce.content}")

        dyn_retained = [e for e in retained_entries if not e.constant]
        if dyn_retained:
            lines.append("\n[实时级联检索词条 (Cascaded Lore)]")
            for de in dyn_retained:
                depth = activated_map[de.entry_id][1]
                lines.append(f"【{de.name}】(级联深度 {depth}): {de.content}")

        formatted_block = "\n".join(lines)

        cascade_map = {eid: d for eid, (e, d) in activated_map.items()}

        return CompiledCodexResult(
            constant_entries=constant_entries,
            activated_entries=retained_entries,
            dropped_entries=dropped_entries,
            total_estimated_tokens=current_token_count,
            max_budget=self.token_budget,
            activation_cascade_map=cascade_map,
            formatted_prompt_block=formatted_block
        )
