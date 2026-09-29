import pytest
from src.novel_factory.codex.progression_engine import (
    ProgressionEngine,
    ProgressionDelta,
    ProgressionType,
    ProgressionScope,
)


@pytest.fixture
def hero_base_state():
    return {
        "entity_id": "char_lin_dong",
        "name": "林动",
        "realm": "淬体一重",
        "title": "林氏分家子弟",
        "skills": ["通背拳"],
        "inventory": [],
        "attributes": {
            "spirit_level": 0,
            "status_tags": ["平凡"]
        }
    }


def test_attribute_replacement(hero_base_state):
    """验证属性完全覆盖替换 (REPLACEMENT)"""
    engine = ProgressionEngine()
    
    # 第 3 章突破到淬体三重
    engine.register_delta(ProgressionDelta(
        delta_id="d1",
        entity_id="char_lin_dong",
        progression_type=ProgressionType.REPLACEMENT,
        effective_chapter=3,
        field_path="realm",
        value="淬体三重"
    ))
    # 第 8 章突破到地元境初期
    engine.register_delta(ProgressionDelta(
        delta_id="d2",
        entity_id="char_lin_dong",
        progression_type=ProgressionType.REPLACEMENT,
        effective_chapter=8,
        field_path="realm",
        value="地元境初期"
    ))

    # 查询第 1 章：应当是初始境界
    state_ch1 = engine.compute_entity_state_at("char_lin_dong", hero_base_state, target_chapter=1)
    assert state_ch1["realm"] == "淬体一重"

    # 查询第 5 章：应当是淬体三重
    state_ch5 = engine.compute_entity_state_at("char_lin_dong", hero_base_state, target_chapter=5)
    assert state_ch5["realm"] == "淬体三重"

    # 查询第 10 章：应当是地元境初期
    state_ch10 = engine.compute_entity_state_at("char_lin_dong", hero_base_state, target_chapter=10)
    assert state_ch10["realm"] == "地元境初期"


def test_addition_and_deletion(hero_base_state):
    """验证列表追加 (ADDITION) 与项目移除 (DELETION)"""
    engine = ProgressionEngine()

    # 第 2 章获得石符
    engine.register_delta(ProgressionDelta(
        delta_id="add_item",
        entity_id="char_lin_dong",
        progression_type=ProgressionType.ADDITION,
        effective_chapter=2,
        field_path="inventory",
        value={"item_id": "stone_amulet", "name": "神秘石符"}
    ))

    # 第 4 章学会八荒掌
    engine.register_delta(ProgressionDelta(
        delta_id="add_skill",
        entity_id="char_lin_dong",
        progression_type=ProgressionType.ADDITION,
        effective_chapter=4,
        field_path="skills",
        value="八荒掌"
    ))

    # 第 6 章消耗/遗失石符
    engine.register_delta(ProgressionDelta(
        delta_id="del_item",
        entity_id="char_lin_dong",
        progression_type=ProgressionType.DELETION,
        effective_chapter=6,
        field_path="inventory",
        value={"item_id": "stone_amulet"}
    ))

    # 第 3 章验证：有石符，技能只有通背拳
    state_ch3 = engine.compute_entity_state_at("char_lin_dong", hero_base_state, target_chapter=3)
    assert len(state_ch3["inventory"]) == 1
    assert state_ch3["inventory"][0]["item_id"] == "stone_amulet"
    assert state_ch3["skills"] == ["通背拳"]

    # 第 5 章验证：有石符，且习得八荒掌
    state_ch5 = engine.compute_entity_state_at("char_lin_dong", hero_base_state, target_chapter=5)
    assert len(state_ch5["inventory"]) == 1
    assert "八荒掌" in state_ch5["skills"]

    # 第 7 章验证：石符已被移除，但八荒掌仍存留
    state_ch7 = engine.compute_entity_state_at("char_lin_dong", hero_base_state, target_chapter=7)
    assert len(state_ch7["inventory"]) == 0
    assert "八荒掌" in state_ch7["skills"]


def test_ephemeral_buff_expiration(hero_base_state):
    """验证单章或区间瞬态效果 (EPHEMERAL Buff/Debuff) 过期自动回退"""
    engine = ProgressionEngine()

    # 第 5 章使用燃血丹，获得临时状态，仅持续第 5-6 章
    engine.register_delta(ProgressionDelta(
        delta_id="blood_pill",
        entity_id="char_lin_dong",
        progression_type=ProgressionType.ADDITION,
        scope=ProgressionScope.EPHEMERAL,
        effective_chapter=5,
        expire_chapter=6,
        field_path="attributes.status_tags",
        value="狂暴(燃血)"
    ))

    # 第 4 章：未生效
    state_ch4 = engine.compute_entity_state_at("char_lin_dong", hero_base_state, target_chapter=4)
    assert "狂暴(燃血)" not in state_ch4["attributes"]["status_tags"]

    # 第 5 章：生效
    state_ch5 = engine.compute_entity_state_at("char_lin_dong", hero_base_state, target_chapter=5)
    assert "狂暴(燃血)" in state_ch5["attributes"]["status_tags"]

    # 第 6 章：仍在有效期
    state_ch6 = engine.compute_entity_state_at("char_lin_dong", hero_base_state, target_chapter=6)
    assert "狂暴(燃血)" in state_ch6["attributes"]["status_tags"]

    # 第 7 章：逾期自动失效
    state_ch7 = engine.compute_entity_state_at("char_lin_dong", hero_base_state, target_chapter=7)
    assert "狂暴(燃血)" not in state_ch7["attributes"]["status_tags"]


def test_rollback_truncation(hero_base_state):
    """验证时间线物理截断回滚"""
    engine = ProgressionEngine()
    for ch in range(1, 10):
        engine.register_delta(ProgressionDelta(
            delta_id=f"delta_{ch}",
            entity_id="char_lin_dong",
            progression_type=ProgressionType.REPLACEMENT,
            effective_chapter=ch,
            field_path="attributes.spirit_level",
            value=ch * 10
        ))

    # 第 9 章验证精神力
    state_ch9 = engine.compute_entity_state_at("char_lin_dong", hero_base_state, target_chapter=9)
    assert state_ch9["attributes"]["spirit_level"] == 90

    # 回滚截断至第 5 章
    removed = engine.truncate_deltas_after_chapter(5)
    assert removed == 4

    # 再次查询第 9 章，由于 6-9 章增量已被物理删除，只能取到第 5 章的值
    state_post_rollback = engine.compute_entity_state_at("char_lin_dong", hero_base_state, target_chapter=9)
    assert state_post_rollback["attributes"]["spirit_level"] == 50


def test_engine_serialization(hero_base_state):
    """验证演进引擎序列化与持久化恢复"""
    engine = ProgressionEngine()
    engine.register_delta(ProgressionDelta(
        delta_id="test_d",
        entity_id="hero",
        progression_type=ProgressionType.REPLACEMENT,
        effective_chapter=1,
        field_path="realm",
        value="元丹境"
    ))
    
    data = engine.to_dict()
    engine2 = ProgressionEngine.from_dict(data)
    
    state = engine2.compute_entity_state_at("hero", {"realm": "淬体"}, target_chapter=1)
    assert state["realm"] == "元丹境"
