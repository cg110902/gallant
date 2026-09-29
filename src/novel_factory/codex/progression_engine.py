"""
Progression Engine - 实体时序进展与属性覆盖演化引擎
深度复刻 NovelCrafter Codex Progression 机制：
1. 属性叠加 (ADDITION)：技能习得、装备入库、被动词条获取，保留历史累计；
2. 属性覆盖 (REPLACEMENT)：境界突破、阶位晋升、身份更替，完全废止旧态；
3. 属性消除 (DELETION)：道具损毁、功力被废、词条剥离；
4. 作用域管理：支持永久演进 (PERMANENT) 与单章/区间瞬时 Buff/Debuff (EPHEMERAL)。
"""

from copy import deepcopy
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


class ProgressionType(str, Enum):
    """进展演进操作类型"""
    ADDITION = "ADDITION"        # 增量叠层（追加至列表或集合）
    REPLACEMENT = "REPLACEMENT"  # 覆盖替换（覆盖标量或对象字段）
    DELETION = "DELETION"        # 移除删除（从列表或字典剥离）


class ProgressionScope(str, Enum):
    """进展时态作用域"""
    PERMANENT = "PERMANENT"      # 永久演进（自生效章节起持续有效，直到被后续更新覆盖）
    EPHEMERAL = "EPHEMERAL"      # 瞬态效果（仅在指定章节区间生效，逾期自动回退）


class ProgressionDelta(BaseModel):
    """时序演进增量记录"""
    delta_id: str
    entity_id: str
    progression_type: ProgressionType
    scope: ProgressionScope = ProgressionScope.PERMANENT
    effective_chapter: int
    expire_chapter: Optional[int] = None  # 瞬态效果过期章节（含）
    field_path: str                       # 支持点分层级，如 "realm", "inventory", "attributes.spirit_power"
    value: Any                            # 变更值或增量项
    provenance_note: str = ""             # 原著依据或章节因果备忘


class ProgressionEngine:
    """实体时序演进管理器"""

    def __init__(self):
        # entity_id -> List[ProgressionDelta]
        self._deltas: Dict[str, List[ProgressionDelta]] = {}

    def register_delta(self, delta: ProgressionDelta) -> None:
        """注册一条时序演进增量，自动按生效章节排序"""
        if delta.scope == ProgressionScope.EPHEMERAL:
            if delta.expire_chapter is None:
                delta.expire_chapter = delta.effective_chapter  # 默认单章生效

        self._deltas.setdefault(delta.entity_id, []).append(delta)
        # 按生效章节严格升序排序
        self._deltas[delta.entity_id].sort(key=lambda d: d.effective_chapter)

    def register_batch(self, deltas: List[ProgressionDelta]) -> None:
        """批量注册演进增量"""
        for d in deltas:
            self.register_delta(d)

    def get_deltas_for_entity(self, entity_id: str) -> List[ProgressionDelta]:
        """获取实体的所有时序增量"""
        return self._deltas.get(entity_id, [])

    def compute_entity_state_at(
        self,
        entity_id: str,
        base_state: Dict[str, Any],
        target_chapter: int
    ) -> Dict[str, Any]:
        """
        核心物化算法：
        以初始创世状态 base_state 为基底，将 <= target_chapter 的所有增量有序应用
        处理永久替换、列表追加、瞬态 Buff 过期等
        """
        current_state = deepcopy(base_state)
        deltas = self._deltas.get(entity_id, [])

        for d in deltas:
            if d.effective_chapter > target_chapter:
                continue

            # 处理瞬态 Buff：如果已经过期，则不应用
            if d.scope == ProgressionScope.EPHEMERAL:
                if d.expire_chapter is not None and target_chapter > d.expire_chapter:
                    continue

            self._apply_delta_to_state(current_state, d)

        return current_state

    def _apply_delta_to_state(self, state: Dict[str, Any], delta: ProgressionDelta) -> None:
        """将单个 delta 应用到状态字典中（支持点分多级字段路径）"""
        tokens = delta.field_path.split(".")
        target_container = state

        # 深入遍历除末尾之外的所有层级
        for token in tokens[:-1]:
            if token not in target_container or not isinstance(target_container[token], dict):
                target_container[token] = {}
            target_container = target_container[token]

        leaf_key = tokens[-1]

        if delta.progression_type == ProgressionType.REPLACEMENT:
            target_container[leaf_key] = deepcopy(delta.value)

        elif delta.progression_type == ProgressionType.ADDITION:
            existing = target_container.get(leaf_key)
            if existing is None:
                # 若字段不存在，初始化为列表或字典
                if isinstance(delta.value, list):
                    target_container[leaf_key] = deepcopy(delta.value)
                else:
                    target_container[leaf_key] = [deepcopy(delta.value)]
            elif isinstance(existing, list):
                if isinstance(delta.value, list):
                    existing.extend(deepcopy(delta.value))
                else:
                    existing.append(deepcopy(delta.value))
            elif isinstance(existing, dict) and isinstance(delta.value, dict):
                existing.update(deepcopy(delta.value))
            else:
                # 标量兜底转换为列表
                target_container[leaf_key] = [existing, deepcopy(delta.value)]

        elif delta.progression_type == ProgressionType.DELETION:
            if leaf_key in target_container:
                existing = target_container[leaf_key]
                if isinstance(existing, list):
                    # 如果是列表，移除匹配项（支持字典按 id 移除或标量值移除）
                    if isinstance(delta.value, dict) and "item_id" in delta.value:
                        target_container[leaf_key] = [
                            x for x in existing
                            if not (isinstance(x, dict) and x.get("item_id") == delta.value["item_id"])
                        ]
                    else:
                        target_container[leaf_key] = [x for x in existing if x != delta.value]
                elif isinstance(existing, dict) and isinstance(delta.value, str):
                    target_container[leaf_key].pop(delta.value, None)
                else:
                    target_container.pop(leaf_key, None)

    def get_field_evolution_history(
        self,
        entity_id: str,
        field_path: str
    ) -> List[Tuple[int, Any, ProgressionType, ProgressionScope]]:
        """追溯某个字段在全书时间线上的全部演变历史"""
        history = []
        for d in self._deltas.get(entity_id, []):
            if d.field_path == field_path:
                history.append((d.effective_chapter, d.value, d.progression_type, d.scope))
        return history

    def truncate_deltas_after_chapter(self, target_chapter: int) -> int:
        """物理回滚：剥离所有在 target_chapter 之后发生的时间线增量"""
        total_removed = 0
        for entity_id in list(self._deltas.keys()):
            original_len = len(self._deltas[entity_id])
            self._deltas[entity_id] = [
                d for d in self._deltas[entity_id]
                if d.effective_chapter <= target_chapter
            ]
            total_removed += (original_len - len(self._deltas[entity_id]))
        return total_removed

    def to_dict(self) -> Dict[str, Any]:
        """序列化所有实体演进流水线"""
        serialized = {}
        for eid, deltas in self._deltas.items():
            serialized[eid] = [d.model_dump() for d in deltas]
        return serialized

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProgressionEngine":
        """反序列化构建演进引擎"""
        engine = cls()
        for eid, deltas_raw in data.items():
            for d in deltas_raw:
                engine.register_delta(ProgressionDelta(**d))
        return engine
