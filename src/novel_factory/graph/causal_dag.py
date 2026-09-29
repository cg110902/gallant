"""
Causal DAG Solver - 基于 NetworkX 的剧情因果有向无环图与拓扑求解器
用于管理前置因果依赖、主支线剧情闭环检测、互斥事件分支判定与拓扑生成顺序推导。
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
import networkx as nx
from pydantic import BaseModel, Field


class NodeStatus(str, Enum):
    """因果节点执行状态"""
    PENDING = "PENDING"          # 尚未满足前置条件
    READY = "READY"              # 前置条件已全部满足，随时可执行
    IN_PROGRESS = "IN_PROGRESS"  # 正在渲染或进行中
    FULFILLED = "FULFILLED"      # 已达成/已闭环
    BLOCKED = "BLOCKED"          # 因互斥或依赖失败被永久阻塞
    FAILED = "FAILED"            # 发生剧情失败断裂


class CausalRelationType(str, Enum):
    """因果依赖边类型"""
    PREREQUISITE = "PREREQUISITE"          # A 为 B 的必要前置条件 (A -> B)
    MUTUALLY_EXCLUSIVE = "MUTUALLY_EXCLUSIVE"  # A 与 B 互斥，达成一个则另一者阻断
    ENABLES = "ENABLES"                    # A 为 B 的充分或催化条件
    TRIGGERS = "TRIGGERS"                  # A 发生后必然级联触发 B


class CausalNode(BaseModel):
    """因果图谱节点"""
    node_id: str
    node_type: str = "PLOT_BEAT"  # PLOT_BEAT, MILESTONE, CLIMAX, CHARACTER_GOAL, WORLD_EVENT
    title: str = ""
    description: str = ""
    status: NodeStatus = NodeStatus.PENDING
    chapter_index: Optional[int] = None
    beat_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CausalCycleError(Exception):
    """因果死锁循环异常（时间线产生祖父悖论）"""
    def __init__(self, cycle_nodes: List[str]):
        super().__init__(f"检测到因果死锁环: {' -> '.join(cycle_nodes)}")
        self.cycle_nodes = cycle_nodes


class CausalDependencyError(Exception):
    """因果前置依赖不满足异常"""
    pass


class CausalDAG:
    """因果图求解器"""

    def __init__(self):
        self.graph = nx.DiGraph()
        self._mutex_graph = nx.Graph()  # 无向图记录互斥对

    def add_node(self, node: CausalNode) -> None:
        """注册或更新因果节点"""
        self.graph.add_node(node.node_id, data=node)

    def get_node(self, node_id: str) -> Optional[CausalNode]:
        """获取指定节点数据"""
        if node_id in self.graph:
            return self.graph.nodes[node_id]["data"]
        return None

    def add_dependency(
        self,
        prerequisite_id: str,
        target_id: str,
        relation_type: CausalRelationType = CausalRelationType.PREREQUISITE,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        添加前置因果依赖边：prerequisite_id -> target_id
        如果形成死锁环，则立即回滚并抛出 CausalCycleError
        """
        if prerequisite_id not in self.graph:
            raise KeyError(f"前置节点未在因果图中注册: {prerequisite_id}")
        if target_id not in self.graph:
            raise KeyError(f"目标节点未在因果图中注册: {target_id}")

        self.graph.add_edge(
            prerequisite_id,
            target_id,
            relation_type=relation_type,
            metadata=metadata or {}
        )

        # 环检测 (Acyclic Invariant Check)
        cycles = list(nx.simple_cycles(self.graph))
        if cycles:
            # 回滚刚添加的边
            self.graph.remove_edge(prerequisite_id, target_id)
            cycle = cycles[0] + [cycles[0][0]]
            raise CausalCycleError(cycle)

        self._refresh_node_readiness(target_id)

    def add_mutual_exclusion(self, node_a: str, node_b: str, reason: str = "") -> None:
        """
        注册互斥节点对（例如：投降 vs 决战到底，加入魔门 vs 留守正道）
        """
        if node_a not in self.graph or node_b not in self.graph:
            raise KeyError("互斥节点必须预先存在于因果图中")
        self._mutex_graph.add_edge(node_a, node_b, reason=reason)

    def _refresh_node_readiness(self, node_id: str) -> None:
        """重新计算节点的 READY / PENDING 状态"""
        node: CausalNode = self.graph.nodes[node_id]["data"]
        if node.status in (NodeStatus.FULFILLED, NodeStatus.BLOCKED, NodeStatus.FAILED):
            return

        unfulfilled = self.get_unfulfilled_prerequisites(node_id)
        if not unfulfilled:
            node.status = NodeStatus.READY
        else:
            node.status = NodeStatus.PENDING

    def get_unfulfilled_prerequisites(self, node_id: str) -> List[str]:
        """获取目标节点所有尚未 FULFILLED 的直接前置依赖节点 ID"""
        if node_id not in self.graph:
            raise KeyError(f"节点不存在: {node_id}")

        unfulfilled = []
        for prereq_id in self.graph.predecessors(node_id):
            edge_data = self.graph.get_edge_data(prereq_id, node_id)
            rel_type = edge_data.get("relation_type", CausalRelationType.PREREQUISITE)
            if rel_type in (CausalRelationType.PREREQUISITE, CausalRelationType.TRIGGERS):
                prereq_node: CausalNode = self.graph.nodes[prereq_id]["data"]
                if prereq_node.status != NodeStatus.FULFILLED:
                    unfulfilled.append(prereq_id)
        return unfulfilled

    def can_execute_node(self, node_id: str) -> Tuple[bool, List[str]]:
        """
        断言目标节点当前是否能够执行
        返回: (是否可执行, 阻碍原因清单)
        """
        if node_id not in self.graph:
            return False, [f"节点不存在: {node_id}"]

        node: CausalNode = self.graph.nodes[node_id]["data"]
        if node.status == NodeStatus.BLOCKED:
            return False, ["节点处于 BLOCKED 状态，已被互斥分支封杀"]
        if node.status == NodeStatus.FULFILLED:
            return False, ["节点已经 FULFILLED 达成，无需重复执行"]

        # 检查互斥冲突
        if node_id in self._mutex_graph:
            for neighbor in self._mutex_graph.neighbors(node_id):
                neighbor_node: CausalNode = self.graph.nodes[neighbor]["data"]
                if neighbor_node.status == NodeStatus.FULFILLED:
                    return False, [f"互斥冲突：互斥节点 [{neighbor}] 已经达成，本节点被阻断"]

        # 检查前置依赖
        unfulfilled = self.get_unfulfilled_prerequisites(node_id)
        if unfulfilled:
            reasons = [f"前置未达成: [{p}]" for p in unfulfilled]
            return False, reasons

        return True, []

    def mark_fulfilled(self, node_id: str, chapter_index: int) -> List[str]:
        """
        将目标节点标记为 FULFILLED，并推进级联依赖与互斥裁剪
        返回受影响被阻断的节点列表 (Blocked nodes)
        """
        if node_id not in self.graph:
            raise KeyError(f"节点不存在: {node_id}")

        node: CausalNode = self.graph.nodes[node_id]["data"]
        node.status = NodeStatus.FULFILLED
        node.chapter_index = chapter_index

        blocked_nodes = []

        # 1. 处理互斥封杀
        if node_id in self._mutex_graph:
            for mutex_partner in self._mutex_graph.neighbors(node_id):
                partner_node: CausalNode = self.graph.nodes[mutex_partner]["data"]
                if partner_node.status != NodeStatus.FULFILLED:
                    partner_node.status = NodeStatus.BLOCKED
                    blocked_nodes.append(mutex_partner)
                    # 递归阻断以该互斥节点为必要前置的所有后继节点
                    descendants = list(nx.descendants(self.graph, mutex_partner))
                    for desc in descendants:
                        desc_node: CausalNode = self.graph.nodes[desc]["data"]
                        desc_node.status = NodeStatus.BLOCKED
                        blocked_nodes.append(desc)

        # 2. 刷新所有直接后继节点的状态
        for successor_id in self.graph.successors(node_id):
            self._refresh_node_readiness(successor_id)

        return blocked_nodes

    def get_executable_nodes(self) -> List[CausalNode]:
        """获取当前因果拓扑中所有满足条件可执行的节点"""
        ready_nodes = []
        for n_id in self.graph.nodes:
            can_run, _ = self.can_execute_node(n_id)
            if can_run:
                ready_nodes.append(self.graph.nodes[n_id]["data"])
        return ready_nodes

    def get_topological_order(self) -> List[str]:
        """
        获取全图的因果拓扑排序顺序
        用于全局大纲多级渲染排期
        """
        return list(nx.topological_sort(self.graph))

    def get_ancestors_chain(self, node_id: str) -> List[str]:
        """获取追溯此节点发生的所有因果祖先节点"""
        if node_id not in self.graph:
            return []
        return list(nx.ancestors(self.graph, node_id))

    def to_dict(self) -> Dict[str, Any]:
        """序列化整个因果拓扑图"""
        nodes_data = [node_data["data"].model_dump() for _, node_data in self.graph.nodes(data=True)]
        edges_data = [
            {
                "source": u,
                "target": v,
                "relation_type": data.get("relation_type", CausalRelationType.PREREQUISITE),
                "metadata": data.get("metadata", {})
            }
            for u, v, data in self.graph.edges(data=True)
        ]
        mutex_data = [
            {"node_a": u, "node_b": v, "reason": data.get("reason", "")}
            for u, v, data in self._mutex_graph.edges(data=True)
        ]
        return {
            "nodes": nodes_data,
            "edges": edges_data,
            "mutex": mutex_data
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CausalDAG":
        """从字典反序列化重构因果拓扑图"""
        dag = cls()
        for nd in data.get("nodes", []):
            dag.add_node(CausalNode(**nd))
        for ed in data.get("edges", []):
            dag.add_dependency(
                ed["source"],
                ed["target"],
                relation_type=CausalRelationType(ed.get("relation_type", CausalRelationType.PREREQUISITE)),
                metadata=ed.get("metadata", {})
            )
        for mx in data.get("mutex", []):
            dag.add_mutual_exclusion(mx["node_a"], mx["node_b"], reason=mx.get("reason", ""))
        return dag
