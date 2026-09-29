import pytest
from src.novel_factory.core.event_store import WorldSnapshot
from src.novel_factory.graph.causal_dag import (
    CausalDAG,
    CausalNode,
    NodeStatus,
    CausalRelationType,
    CausalCycleError,
)
from src.novel_factory.graph.invariant_checker import (
    InvariantChecker,
    ProposedAction,
    InvariantReport,
)


def test_dag_topological_order():
    """验证因果拓扑排序与依赖前置关系"""
    dag = CausalDAG()
    
    n1 = CausalNode(node_id="obtain_map", title="获得秘境地图")
    n2 = CausalNode(node_id="reach_ancient_tomb", title="抵达古墓外围")
    n3 = CausalNode(node_id="defeat_guardian", title="击败墓道傀儡")
    n4 = CausalNode(node_id="open_inner_vault", title="开启墓室密藏")
    
    for n in (n1, n2, n3, n4):
        dag.add_node(n)
        
    dag.add_dependency("obtain_map", "reach_ancient_tomb")
    dag.add_dependency("reach_ancient_tomb", "defeat_guardian")
    dag.add_dependency("defeat_guardian", "open_inner_vault")
    
    order = dag.get_topological_order()
    assert order == ["obtain_map", "reach_ancient_tomb", "defeat_guardian", "open_inner_vault"]
    
    # 验证初始状态只有 obtain_map 是可执行的
    can_exec, reasons = dag.can_execute_node("open_inner_vault")
    assert can_exec is False
    assert any("前置未达成" in r for r in reasons)
    
    can_exec_n1, _ = dag.can_execute_node("obtain_map")
    assert can_exec_n1 is True


def test_dag_cycle_detection():
    """验证死锁环（祖父悖论）检测与自动防御回滚"""
    dag = CausalDAG()
    dag.add_node(CausalNode(node_id="A"))
    dag.add_node(CausalNode(node_id="B"))
    dag.add_node(CausalNode(node_id="C"))
    
    dag.add_dependency("A", "B")
    dag.add_dependency("B", "C")
    
    # 试图注入死锁环 C -> A
    with pytest.raises(CausalCycleError) as exc_info:
        dag.add_dependency("C", "A")
        
    assert "A" in exc_info.value.cycle_nodes
    # 验证边被安全撤回，图依然是 DAG
    assert not dag.graph.has_edge("C", "A")


def test_dag_mutual_exclusion_and_branch_pruning():
    """验证互斥分支达成时的级联阻断"""
    dag = CausalDAG()
    
    # 分支节点
    dag.add_node(CausalNode(node_id="path_righteous", title="加入青云宗"))
    dag.add_node(CausalNode(node_id="path_demonic", title="投身九幽教"))
    
    # 后续衍生节点
    dag.add_node(CausalNode(node_id="righteous_spell", title="修习太极玄清道"))
    dag.add_node(CausalNode(node_id="demonic_blood", title="淬炼九幽魔血"))
    
    dag.add_dependency("path_righteous", "righteous_spell")
    dag.add_dependency("path_demonic", "demonic_blood")
    
    # 互斥绑定
    dag.add_mutual_exclusion("path_righteous", "path_demonic", reason="正邪不两立")
    
    # 达成正道分支
    blocked = dag.mark_fulfilled("path_righteous", chapter_index=5)
    
    assert "path_demonic" in blocked
    assert "demonic_blood" in blocked
    
    # 验证魔道分支状态已被标记为 BLOCKED
    demonic_node = dag.get_node("path_demonic")
    assert demonic_node.status == NodeStatus.BLOCKED
    
    demonic_spell = dag.get_node("demonic_blood")
    assert demonic_spell.status == NodeStatus.BLOCKED
    
    # 试图执行已被阻断的节点应直接被拒绝
    can_exec, reasons = dag.can_execute_node("path_demonic")
    assert can_exec is False
    assert any("BLOCKED" in r for r in reasons)


def test_dag_serialization():
    """验证因果 DAG 的完整序列化与反序列化"""
    dag = CausalDAG()
    dag.add_node(CausalNode(node_id="n1", title="任务一"))
    dag.add_node(CausalNode(node_id="n2", title="任务二"))
    dag.add_dependency("n1", "n2")
    dag.add_mutual_exclusion("n1", "n2", reason="测试互斥")
    
    data = dag.to_dict()
    dag2 = CausalDAG.from_dict(data)
    
    assert dag2.get_node("n1").title == "任务一"
    assert dag2.get_topological_order() == ["n1", "n2"]


def test_invariant_zero_zombie():
    """验证存活性硬不变式（死人不能施法或对话）"""
    snapshot = WorldSnapshot(
        chapter_index=10,
        last_sequence_num=100,
        entities={
            "hero": {"entity_id": "hero", "name": "萧炎", "is_alive": True, "inventory": []},
            "elder": {"entity_id": "elder", "name": "药老", "is_alive": False, "killed_at_chapter": 8, "inventory": []}
        }
    )
    checker = InvariantChecker()
    
    # 药老作为死者试图发起施法
    action = ProposedAction(
        actor_id="elder",
        action_type="CAST_SPELL",
        target_id="hero"
    )
    
    report = checker.check_action(snapshot, action, chapter_index=10)
    assert report.passed is False
    assert report.has_fatal_errors is True
    assert any(v.rule_name == "ZERO_ZOMBIE_VIOLATION" for v in report.violations)


def test_invariant_unpossessed_item():
    """验证道具持有合法性（不能使用不存在的道具）"""
    snapshot = WorldSnapshot(
        chapter_index=5,
        last_sequence_num=50,
        entities={
            "hero": {
                "entity_id": "hero",
                "name": "林动",
                "is_alive": True,
                "inventory": [{"item_id": "wooden_sword", "name": "木剑"}]
            }
        }
    )
    checker = InvariantChecker()
    
    # 试图使用未曾获得的石符
    action = ProposedAction(
        actor_id="hero",
        action_type="USE_ITEM",
        item_id="stone_amulet"
    )
    
    report = checker.check_action(snapshot, action, chapter_index=5)
    assert report.passed is False
    assert any(v.rule_name == "UNPOSSESSED_ITEM_USAGE" for v in report.violations)


def test_invariant_exclusive_possession():
    """验证唯一道具排他性持有（唯一宝物禁止克隆）"""
    snapshot = WorldSnapshot(
        chapter_index=3,
        last_sequence_num=30,
        entities={
            "hero_a": {
                "entity_id": "hero_a",
                "name": "主角A",
                "is_alive": True,
                "inventory": [{"item_id": "supreme_bone", "name": "至尊骨", "unique": True}]
            },
            "hero_b": {
                "entity_id": "hero_b",
                "name": "主角B",
                "is_alive": True,
                "inventory": [{"item_id": "supreme_bone", "name": "至尊骨", "unique": True}]
            }
        }
    )
    checker = InvariantChecker()
    report = checker.check_world_consistency(snapshot, chapter_index=3)
    assert report.passed is False
    assert any(v.rule_name == "EXCLUSIVE_POSSESSION_CONFLICT" for v in report.violations)


def test_invariant_spatial_colocation():
    """验证空间共存断言（相隔万里不可面对面近战）"""
    snapshot = WorldSnapshot(
        chapter_index=12,
        last_sequence_num=120,
        entities={
            "lin": {
                "entity_id": "lin",
                "name": "林动",
                "is_alive": True,
                "attributes": {"current_location": "大荒郡"},
                "inventory": []
            },
            "lang": {
                "entity_id": "lang",
                "name": "林琅天",
                "is_alive": True,
                "attributes": {"current_location": "大炎皇城"},
                "inventory": []
            }
        }
    )
    checker = InvariantChecker()
    
    # 异地肉搏攻击
    action = ProposedAction(
        actor_id="lin",
        action_type="MELEE_ATTACK",
        target_id="lang",
        is_telepresence=False
    )
    report = checker.check_action(snapshot, action, chapter_index=12)
    assert report.passed is False
    assert any(v.rule_name == "SPATIAL_DISCONNECTION_VIOLATION" for v in report.violations)
    
    # 远程神念传音则允许
    action_remote = ProposedAction(
        actor_id="lin",
        action_type="MELEE_ATTACK",
        target_id="lang",
        is_telepresence=True
    )
    report_remote = checker.check_action(snapshot, action_remote, chapter_index=12)
    assert report_remote.passed is True


def test_invariant_dag_prerequisites():
    """验证分镜前置事件依赖硬断言"""
    dag = CausalDAG()
    dag.add_node(CausalNode(node_id="gather_herbs", title="采集合气丹主药", status=NodeStatus.READY))
    
    checker = InvariantChecker(dag=dag)
    snapshot = WorldSnapshot(
        chapter_index=2,
        last_sequence_num=20,
        entities={"alchemist": {"entity_id": "alchemist", "name": "炼丹师", "is_alive": True, "inventory": []}}
    )
    
    # 尝试在药材尚未收集完成前炼丹
    action = ProposedAction(
        actor_id="alchemist",
        action_type="CAST_SPELL",
        required_prerequisites=["gather_herbs"]
    )
    report = checker.check_action(snapshot, action, chapter_index=2)
    assert report.passed is False
    assert any(v.rule_name == "UNFULFILLED_CAUSAL_PREREQUISITE" for v in report.violations)
    
    # 达成药材收集事件
    dag.mark_fulfilled("gather_herbs", chapter_index=2)
    report_ok = checker.check_action(snapshot, action, chapter_index=2)
    assert report_ok.passed is True
