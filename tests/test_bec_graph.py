"""
Tests for BEC-Graph - 双时态实体因果图谱单元测试
"""

import pytest
from src.novel_factory.graph.bec_graph import BECGraph
from src.novel_factory.schemas.entity import EntityRelation, StandardRelations


@pytest.fixture
def graph():
    g = BECGraph(":memory:")
    yield g
    g.close()


def test_entity_registration_and_time_travel(graph: BECGraph):
    """测试实体登记与时空回溯查询"""
    # 注册角色，初始状态为第 1 章
    graph.register_entity(
        entity_id="char_zero",
        entity_type="CHARACTER",
        name="零号",
        created_chapter=1,
        initial_payload={"tier_or_rank": "民用级", "power_rating": 100.0}
    )

    # 第 5 章升级
    graph.update_entity_progression(
        entity_id="char_zero",
        chapter_index=5,
        new_payload={"tier_or_rank": "军规级", "power_rating": 350.0}
    )

    # 第 10 章再次升级
    graph.update_entity_progression(
        entity_id="char_zero",
        chapter_index=10,
        new_payload={"tier_or_rank": "死神级", "power_rating": 1200.0}
    )

    # 时空回溯断言
    state_ch1 = graph.get_entity_state_at("char_zero", 1)
    state_ch3 = graph.get_entity_state_at("char_zero", 3)  # 应获取第1章状态
    state_ch5 = graph.get_entity_state_at("char_zero", 5)
    state_ch8 = graph.get_entity_state_at("char_zero", 8)  # 应获取第5章状态
    state_ch12 = graph.get_entity_state_at("char_zero", 12) # 应获取第10章状态

    assert state_ch1["tier_or_rank"] == "民用级"
    assert state_ch3["tier_or_rank"] == "民用级"
    assert state_ch5["tier_or_rank"] == "军规级"
    assert state_ch8["tier_or_rank"] == "军规级"
    assert state_ch12["tier_or_rank"] == "死神级"


def test_bitemporal_relation_lifecycle(graph: BECGraph):
    """测试双时态关系有效区间与失效注销"""
    rel = EntityRelation(
        source_id="char_zero",
        relation_type=StandardRelations.ALLY_OF,
        target_id="char_doc",
        valid_from_chapter=2,
        valid_to_chapter=8,
        provenance_chapter=2,
        evidence="第2章在地下诊所达成合作"
    )
    graph.add_relation(rel)

    # 断言时序区间
    assert len(graph.get_active_relations_at(source_id="char_zero", chapter=1)) == 0
    assert len(graph.get_active_relations_at(source_id="char_zero", chapter=2)) == 1
    assert len(graph.get_active_relations_at(source_id="char_zero", chapter=5)) == 1
    assert len(graph.get_active_relations_at(source_id="char_zero", chapter=8)) == 1
    assert len(graph.get_active_relations_at(source_id="char_zero", chapter=9)) == 0

    # 手动提前注销
    graph.invalidate_relation(
        source_id="char_zero",
        relation_type=StandardRelations.ALLY_OF,
        target_id="char_doc",
        cutoff_chapter=4
    )
    assert len(graph.get_active_relations_at(source_id="char_zero", chapter=5)) == 0


def test_causality_invariants_action_validation(graph: BECGraph):
    """测试因果硬不变式（死人不能行动、未持有不能使用道具）"""
    # 注册角色与道具
    graph.register_entity("char_alive", "CHARACTER", "活着的刺客", created_chapter=1, is_alive=True)
    graph.register_entity("char_dead", "CHARACTER", "死去的守卫", created_chapter=1, is_alive=False)
    graph.register_entity("item_plasma_cutter", "ARTIFACT", "等离子切割器", created_chapter=1)

    # 1. 死人行动断言 -> 失败
    can_act, reason = graph.verify_action_causality("char_dead", "ATTACK", None, chapter=2)
    assert can_act is False
    assert "已死亡" in reason

    # 2. 活人无装备使用道具 -> 失败
    can_use, reason = graph.verify_action_causality("char_alive", "USE_ITEM", "item_plasma_cutter", chapter=2)
    assert can_use is False
    assert "并未持有" in reason

    # 3. 授予道具持有关系 -> 成功
    graph.add_relation(
        EntityRelation(
            source_id="char_alive",
            relation_type=StandardRelations.POSSESSES,
            target_id="item_plasma_cutter",
            valid_from_chapter=2,
            valid_to_chapter=999,
            provenance_chapter=2
        )
    )
    can_use_now, reason = graph.verify_action_causality("char_alive", "USE_ITEM", "item_plasma_cutter", chapter=2)
    assert can_use_now is True
    assert reason is None
