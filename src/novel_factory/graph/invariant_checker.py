"""
Invariant Checker - 物理与叙事逻辑硬不变式检验器
在生成前与后置验证中执行严格断言：
1. 存活性不变式 (Zero-Zombie Invariant)：死亡实体不得作为主动施动者或对话者；
2. 物品排他性持有不变式 (Exclusive Possession Invariant)：唯一性宝物/核心道具禁止同时存在于多个活体角色背囊；
3. 空间共存与可达性不变式 (Co-location Invariant)：面对面物理交互角色必须身处同一地理空间；
4. 道具施用先决不变式 (Item Prerequisite Invariant)：使用/消耗/转让物品前必须真实持有；
5. 因果拓扑先决不变式 (DAG Prerequisite Invariant)：剧情分镜的前置剧情事件必须已达成 (FULFILLED)。
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set
from pydantic import BaseModel, Field

from src.novel_factory.core.event_store import WorldSnapshot
from src.novel_factory.graph.causal_dag import CausalDAG, NodeStatus


class InvariantViolation(BaseModel):
    """不变式冲突记录"""
    rule_name: str
    severity: str = "ERROR"  # ERROR, WARNING
    message: str
    entity_ids: List[str] = Field(default_factory=list)
    chapter_index: int = 1
    beat_id: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


@dataclass
class InvariantReport:
    """不变式检查综合报告"""
    passed: bool
    violations: List[InvariantViolation] = field(default_factory=list)
    chapter_index: int = 1
    beat_id: Optional[str] = None

    @property
    def has_fatal_errors(self) -> bool:
        return any(v.severity == "ERROR" for v in self.violations)


class ProposedAction(BaseModel):
    """待验证的分镜动作拟议"""
    actor_id: str
    action_type: str  # DIALOGUE, MELEE_ATTACK, CAST_SPELL, USE_ITEM, TRANSFER_ITEM, TRAVEL, SOCIAL_INTERACTION
    target_id: Optional[str] = None
    item_id: Optional[str] = None
    location_id: Optional[str] = None
    required_prerequisites: List[str] = Field(default_factory=list)
    is_telepresence: bool = False  # 是否为神念分身/投影/千里传音


class InvariantChecker:
    """工业级叙事不变式检查器"""

    def __init__(self, dag: Optional[CausalDAG] = None):
        self.dag = dag or CausalDAG()
        self._custom_rules: List[Callable[[WorldSnapshot, ProposedAction, InvariantReport], None]] = []

    def register_custom_rule(
        self,
        rule_fn: Callable[[WorldSnapshot, ProposedAction, InvariantReport], None]
    ) -> None:
        """注册可扩展自定义业务领域不变式"""
        self._custom_rules.append(rule_fn)

    def check_action(
        self,
        snapshot: WorldSnapshot,
        action: ProposedAction,
        chapter_index: int,
        beat_id: Optional[str] = None
    ) -> InvariantReport:
        """
        全面验证分镜行为在目标章节时空状态下的因果合法性
        """
        report = InvariantReport(
            passed=True,
            violations=[],
            chapter_index=chapter_index,
            beat_id=beat_id
        )

        # 1. 存活性检查 (Zero-Zombie Invariant)
        self._check_aliveness(snapshot, action, report)

        # 2. 道具持有先决性检查 (Item Possession Invariant)
        self._check_item_possession(snapshot, action, report)

        # 3. 道具排他性持有检查 (Exclusive Possession Invariant)
        self._check_exclusive_possession(snapshot, report)

        # 4. 空间共存与可达性检查 (Co-location Invariant)
        self._check_colocation(snapshot, action, report)

        # 5. 因果图前置条件达成检查 (DAG Prerequisite Invariant)
        self._check_dag_prerequisites(action, report)

        # 6. 自定义规则链
        for custom_rule in self._custom_rules:
            custom_rule(snapshot, action, report)

        if report.has_fatal_errors:
            report.passed = False

        return report

    def check_world_consistency(
        self,
        snapshot: WorldSnapshot,
        chapter_index: int
    ) -> InvariantReport:
        """全局时空状态一致性自检（用于章节结算后的全局安全巡检）"""
        report = InvariantReport(
            passed=True,
            violations=[],
            chapter_index=chapter_index
        )
        self._check_exclusive_possession(snapshot, report)
        
        # 检查死者是否仍持有活动关系
        for rel_key, rel_data in snapshot.relations.items():
            src_id = rel_data.get("source_id")
            tgt_id = rel_data.get("target_id")
            src_entity = snapshot.entities.get(src_id)
            tgt_entity = snapshot.entities.get(tgt_id)
            
            if src_entity and not src_entity.get("is_alive", True):
                if rel_data.get("relation_type") not in ("MURDERED_BY", "BURIED_BY", "LEGACY_OF"):
                    report.violations.append(InvariantViolation(
                        rule_name="DEAD_ENTITY_ACTIVE_RELATION",
                        severity="WARNING",
                        message=f"已故实体 [{src_id}] 仍保有存续社会关系: {rel_key}",
                        entity_ids=[src_id],
                        chapter_index=chapter_index
                    ))

        if report.has_fatal_errors:
            report.passed = False
        return report

    def _check_aliveness(
        self,
        snapshot: WorldSnapshot,
        action: ProposedAction,
        report: InvariantReport
    ) -> None:
        """规则 1: 存活性判定"""
        actor = snapshot.entities.get(action.actor_id)
        if not actor:
            report.violations.append(InvariantViolation(
                rule_name="ENTITY_NOT_FOUND",
                severity="ERROR",
                message=f"行为施动实体不存在于世界快照: {action.actor_id}",
                entity_ids=[action.actor_id],
                chapter_index=report.chapter_index,
                beat_id=report.beat_id
            ))
            return

        if not actor.get("is_alive", True):
            actor_name = actor.get("name", action.actor_id)
            report.violations.append(InvariantViolation(
                rule_name="ZERO_ZOMBIE_VIOLATION",
                severity="ERROR",
                message=f"死者异动违规：角色 [{actor_name}] 已于更早章节死亡，严禁执行主动行为 [{action.action_type}]",
                entity_ids=[action.actor_id],
                chapter_index=report.chapter_index,
                beat_id=report.beat_id,
                details={"killed_at_chapter": actor.get("killed_at_chapter")}
            ))

        # 目标若是特定交互（如物理决斗/交谈），目标若已死且非搜尸/验尸，则违规
        if action.target_id:
            target = snapshot.entities.get(action.target_id)
            if target and not target.get("is_alive", True):
                if action.action_type in ("DIALOGUE", "MELEE_ATTACK", "DUEL", "TRADE"):
                    target_name = target.get("name", action.target_id)
                    report.violations.append(InvariantViolation(
                        rule_name="INTERACT_WITH_CORPSE_VIOLATION",
                        severity="ERROR",
                        message=f"交互对象悖论：目标角色 [{target_name}] 已死亡，无法对其进行 [{action.action_type}] 交互",
                        entity_ids=[action.actor_id, action.target_id],
                        chapter_index=report.chapter_index,
                        beat_id=report.beat_id
                    ))

    def _check_item_possession(
        self,
        snapshot: WorldSnapshot,
        action: ProposedAction,
        report: InvariantReport
    ) -> None:
        """规则 2: 道具持有合法性判定"""
        if action.action_type in ("USE_ITEM", "TRANSFER_ITEM", "EQUIP_ITEM", "CONSUME_ITEM"):
            if not action.item_id:
                report.violations.append(InvariantViolation(
                    rule_name="MISSING_ITEM_SPECIFICATION",
                    severity="ERROR",
                    message=f"动作 [{action.action_type}] 未指定道具 ID",
                    entity_ids=[action.actor_id],
                    chapter_index=report.chapter_index,
                    beat_id=report.beat_id
                ))
                return

            actor = snapshot.entities.get(action.actor_id)
            if not actor:
                return

            inventory = actor.get("inventory", [])
            has_item = any(item.get("item_id") == action.item_id for item in inventory)

            if not has_item:
                actor_name = actor.get("name", action.actor_id)
                report.violations.append(InvariantViolation(
                    rule_name="UNPOSSESSED_ITEM_USAGE",
                    severity="ERROR",
                    message=f"空手套白狼违规：角色 [{actor_name}] 背囊中不存在道具 [{action.item_id}]，无法执行 [{action.action_type}]",
                    entity_ids=[action.actor_id],
                    chapter_index=report.chapter_index,
                    beat_id=report.beat_id,
                    details={"missing_item_id": action.item_id}
                ))

    def _check_exclusive_possession(
        self,
        snapshot: WorldSnapshot,
        report: InvariantReport
    ) -> None:
        """规则 3: 唯一性道具排他持有判定（全图扫描）"""
        item_holders: Dict[str, List[str]] = {}

        for ent_id, ent_data in snapshot.entities.items():
            if not ent_data.get("is_alive", True):
                continue
            for item in ent_data.get("inventory", []):
                item_id = item.get("item_id")
                # 若道具声明了唯一性属性 (unique=True 或 is_unique=True)
                is_unique = item.get("unique", False) or item.get("is_unique", False) or item.get("tier") in ("ARTIFACT", "HEIRLOOM")
                if is_unique and item_id:
                    item_holders.setdefault(item_id, []).append(ent_id)

        for item_id, holders in item_holders.items():
            if len(holders) > 1:
                holder_names = [snapshot.entities[h].get("name", h) for h in holders]
                report.violations.append(InvariantViolation(
                    rule_name="EXCLUSIVE_POSSESSION_CONFLICT",
                    severity="ERROR",
                    message=f"道具克隆悖论：唯一宝物 [{item_id}] 同时出现在多名角色的背囊中: {', '.join(holder_names)}",
                    entity_ids=holders,
                    chapter_index=report.chapter_index,
                    beat_id=report.beat_id,
                    details={"conflicting_item_id": item_id, "holders": holders}
                ))

    def _check_colocation(
        self,
        snapshot: WorldSnapshot,
        action: ProposedAction,
        report: InvariantReport
    ) -> None:
        """规则 4: 空间共存判定"""
        if action.is_telepresence:
            return  # 远程分身或通灵通讯跳过空间同场断言

        if action.target_id and action.action_type in ("MELEE_ATTACK", "DUEL", "TRANSFER_ITEM"):
            actor = snapshot.entities.get(action.actor_id)
            target = snapshot.entities.get(action.target_id)
            if not actor or not target:
                return

            actor_loc = actor.get("attributes", {}).get("current_location")
            target_loc = target.get("attributes", {}).get("current_location")

            if actor_loc and target_loc and actor_loc != target_loc:
                actor_name = actor.get("name", action.actor_id)
                target_name = target.get("name", action.target_id)
                report.violations.append(InvariantViolation(
                    rule_name="SPATIAL_DISCONNECTION_VIOLATION",
                    severity="ERROR",
                    message=f"时空错位违规：[{actor_name}] 位于 [{actor_loc}]，而 [{target_name}] 位于 [{target_loc}]，二者未同场却发起近距交互 [{action.action_type}]",
                    entity_ids=[action.actor_id, action.target_id],
                    chapter_index=report.chapter_index,
                    beat_id=report.beat_id,
                    details={"actor_loc": actor_loc, "target_loc": target_loc}
                ))

    def _check_dag_prerequisites(
        self,
        action: ProposedAction,
        report: InvariantReport
    ) -> None:
        """规则 5: DAG 因果前置达成判定"""
        for prereq_node_id in action.required_prerequisites:
            node = self.dag.get_node(prereq_node_id)
            if not node:
                report.violations.append(InvariantViolation(
                    rule_name="PREREQUISITE_NODE_NOT_FOUND",
                    severity="ERROR",
                    message=f"所依赖的因果前置节点未在因果图中注册: [{prereq_node_id}]",
                    entity_ids=[action.actor_id],
                    chapter_index=report.chapter_index,
                    beat_id=report.beat_id
                ))
            elif node.status != NodeStatus.FULFILLED:
                report.violations.append(InvariantViolation(
                    rule_name="UNFULFILLED_CAUSAL_PREREQUISITE",
                    severity="ERROR",
                    message=f"因果断裂：行为必须的前置因果事件 [{node.title or prereq_node_id}] 尚未达成 (当前状态: {node.status.value})",
                    entity_ids=[action.actor_id],
                    chapter_index=report.chapter_index,
                    beat_id=report.beat_id,
                    details={"prerequisite_id": prereq_node_id, "current_status": node.status.value}
                ))
