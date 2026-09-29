"""
Codex Assembler - 确定性上下文编译器 (Deterministic Context Compiler)
深度借鉴 NovelCrafter Codex 与 SillyTavern World Info 机制：
基于当前章节时序、场景在场实体与文本正则级联，精确编译低成本、零时序幻觉的高纯度上下文。
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
import re

from src.novel_factory.graph.bec_graph import BECGraph
from src.novel_factory.schemas.beat import BeatContract
from src.novel_factory.schemas.entity import LoreEntry


@dataclass
class AssembledContext:
    """编译产出的结构化上下文包"""
    chapter_index: int
    beat_id: str
    global_block: str
    tracked_entities_block: str
    cascaded_lore_block: str
    active_entry_ids: List[str]
    estimated_tokens: int
    raw_full_context: str


class CodexAssembler:
    """确定性上下文装配器"""

    def __init__(
        self,
        max_token_budget: int = 3500,
        chars_per_token_estimate: float = 1.6  # 中文汉字与英文混合估算比
    ):
        self.max_token_budget = max_token_budget
        self.chars_per_token = chars_per_token_estimate

    def assemble(
        self,
        chapter_index: int,
        scene_beat: BeatContract,
        graph: BECGraph,
        lore_entries: List[LoreEntry],
        global_invariants: Optional[List[str]] = None,
        recent_text_buffer: str = ""
    ) -> AssembledContext:
        """
        确定性执行四级装配编译
        """
        # 1. 第一级：Global 常驻法则与当前大纲目标
        global_lines = [
            "【最高法则与剧情不变式 (Global Invariants)】",
            f"- 当前章节序号: 第 {chapter_index} 章 | 节拍: {scene_beat.beat_id}",
            f"- 节拍叙事类型: {scene_beat.pacing_type.value}",
            f"- 必须覆盖机位: {', '.join([c.value for c in scene_beat.required_camera_angles])}"
        ]
        if global_invariants:
            for inv in global_invariants:
                global_lines.append(f"- {inv}")
        global_block = "\n".join(global_lines)

        # 2. 第二级：Tracked 在场实体时序状态（从 BEC-Graph 实时召回）
        tracked_lines = ["【在场实体真实时序状态 (Tracked Entities)】"]
        for entity_id in scene_beat.characters_present:
            state = graph.get_entity_state_at(entity_id, chapter_index)
            relations = graph.get_active_relations_at(source_id=entity_id, chapter=chapter_index)
            
            if state:
                tier = state.get("tier_or_rank", "未知等级")
                power = state.get("power_rating", "N/A")
                tags = state.get("status_tags", [])
                inventory = state.get("inventory", [])
                inv_names = [item.get("name", "") for item in inventory if isinstance(item, dict)]
                
                rel_strs = [
                    f"{r.relation_type}->{r.target_id}" 
                    for r in relations if r.target_id in scene_beat.characters_present
                ]
                
                desc = (
                    f"* 实体 [{entity_id}]: 等级/阶位 [{tier}], 战力标尺 [{power}], "
                    f"当前状态标签 {tags}, 持有关键物品 {inv_names}"
                )
                if rel_strs:
                    desc += f", 对在场者即时关系: {', '.join(rel_strs)}"
                tracked_lines.append(desc)
            else:
                tracked_lines.append(f"* 实体 [{entity_id}]: (未登记历史状态，采用默认基础档案)")

        tracked_block = "\n".join(tracked_lines)

        # 3. 第三级：Cascaded / Regex 触发词条 (SillyTavern 级联触发)
        # 扫描范围：场景卡的前置条件 + 最近生成的 600 字文本
        scan_corpus = "\n".join(scene_beat.pre_conditions) + "\n" + recent_text_buffer[-600:]
        
        cascaded_lines = ["【动态级联设定词条 (Triggered Lore)】"]
        active_entry_ids: List[str] = []

        for entry in lore_entries:
            # 严格时序过滤：未生效或已失效的词条绝不召回
            if not entry.is_valid_at(chapter_index):
                continue

            # 全局词条直接注入
            if entry.is_global:
                cascaded_lines.append(f"* [{entry.name}]: {entry.content}")
                active_entry_ids.append(entry.entry_id)
                continue

            # 一级关键词匹配
            primary_hit = any(re.search(re.escape(k), scan_corpus) for k in entry.primary_keys)
            if not primary_hit:
                continue

            # 二级级联条件词匹配（若定义）
            if entry.secondary_keys:
                secondary_hit = any(re.search(re.escape(k), scan_corpus) for k in entry.secondary_keys)
                if not secondary_hit:
                    continue  # 未满足级联条件，跳过

            # 命中激活
            cascaded_lines.append(f"* [{entry.name} (触发注入)]: {entry.content}")
            active_entry_ids.append(entry.entry_id)

        cascaded_block = "\n".join(cascaded_lines)

        # 4. 组装与 Token 预算安全门禁
        full_context = f"{global_block}\n\n{tracked_block}\n\n{cascaded_block}"
        estimated_tokens = int(len(full_context) / self.chars_per_token)

        # 若超出预算，按优先级裁剪（Cascaded 优先级最低）
        if estimated_tokens > self.max_token_budget:
            # 缩减 cascaded_block
            safe_char_len = int(self.max_token_budget * self.chars_per_token) - len(global_block) - len(tracked_block)
            if safe_char_len > 100:
                cascaded_block = cascaded_block[:safe_char_len] + "\n...(由于Token预算限制已截断其余低优设定)"
            else:
                cascaded_block = "【设定词条因超出Token预算已安全熔断】"
            full_context = f"{global_block}\n\n{tracked_block}\n\n{cascaded_block}"
            estimated_tokens = int(len(full_context) / self.chars_per_token)

            # 兜底硬截断：当 global/tracked 两块自身就撑破预算时，
            # 上面按差值裁剪 cascaded 是不够的，预算会被突破。
            # Token 预算直接对应真金白银与上下文窗口，必须是硬上限。
            if estimated_tokens > self.max_token_budget:
                hard_limit = int(self.max_token_budget * self.chars_per_token)
                notice = "\n...(上下文超出Token硬预算，已强制截断)"
                full_context = full_context[:max(0, hard_limit - len(notice))] + notice
                estimated_tokens = int(len(full_context) / self.chars_per_token)

        return AssembledContext(
            chapter_index=chapter_index,
            beat_id=scene_beat.beat_id,
            global_block=global_block,
            tracked_entities_block=tracked_block,
            cascaded_lore_block=cascaded_block,
            active_entry_ids=active_entry_ids,
            estimated_tokens=estimated_tokens,
            raw_full_context=full_context
        )
