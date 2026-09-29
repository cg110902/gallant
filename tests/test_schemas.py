"""
Tests for Universal Schemas - 全题材通用契约单元测试
"""

from src.novel_factory.schemas import (
    Character,
    CharacterProgression,
    CharacterRole,
    EntityRelation,
    GenericItem,
    LoreEntry,
    BeatContract,
    PacingType,
    CameraAngle,
    MicroEvent,
    StandardRelations,
    StandardEntityTypes,
    StateDelta,
    StoryCommit,
)


def test_character_creation_and_progression_universal():
    """测试全题材通用角色实体与时序进展状态"""
    # 模拟赛博朋克题材角色
    initial_state = CharacterProgression(
        chapter_index=1,
        tier_or_rank="初级民用植入",
        power_rating=150.0,
        physical_status="HEALTHY",
        status_tags=["神经轻度过载"],
        current_location="loc_night_market",
        inventory=[
            GenericItem(item_id="item_cyber_deck", name="军用解码器v2", bound_status="BOUND")
        ]
    )

    char = Character(
        id="char_hacker_zero",
        name="零号",
        role=CharacterRole.PROTAGONIST,
        core_motivation="瓦解巨型垄断公司并找回被格式化的记忆",
        moral_bottom_line="绝不向仿生孤儿开枪",
        current_state=initial_state
    )

    assert char.id == "char_hacker_zero"
    assert char.current_state.tier_or_rank == "初级民用植入"
    assert len(char.current_state.inventory) == 1

    # 推进状态
    advanced_state = CharacterProgression(
        chapter_index=5,
        tier_or_rank="军规级战术改装",
        power_rating=450.0,
        physical_status="INJURED",
        current_location="loc_subway_ruins"
    )
    char.advance_chapter(advanced_state)

    assert char.current_state.tier_or_rank == "军规级战术改装"
    assert len(char.history_states) == 1
    assert char.history_states[0].tier_or_rank == "初级民用植入"


def test_entity_relation_custom_and_temporal():
    """测试通用实体双时态关系与用户自定义关系类型"""
    relation = EntityRelation(
        source_id="char_agent_01",
        relation_type="HACKED_BY",  # 用户在YAML中扩展的非内建题材关系
        target_id="faction_megacorp",
        valid_from_chapter=3,
        valid_to_chapter=12,
        provenance_chapter=3,
        evidence="第3章在神经漫游网络中被植入深度后门"
    )

    assert relation.is_active_at(2) is False
    assert relation.is_active_at(3) is True
    assert relation.is_active_at(10) is True
    assert relation.is_active_at(13) is False


def test_lore_entry_universal_cascade():
    """测试 Codex 词条的通用级联触发机制"""
    entry = LoreEntry(
        entry_id="item_black_box",
        entity_type=StandardEntityTypes.ARTIFACT,
        name="加密黑匣子",
        primary_keys=["黑匣子", "机密存储器"],
        secondary_keys=["自毁", "密码熔断"],
        content="尝试三次密码错误将释放微型铝热剂烧毁芯片。",
        valid_from_chapter=1,
        valid_to_chapter=100
    )

    assert entry.is_valid_at(1) is True
    assert entry.is_valid_at(100) is True
    assert entry.is_valid_at(101) is False


def test_beat_contract_universal():
    """测试全题材通用的 DOC 细粒度节拍契约"""
    contract = BeatContract(
        beat_id="ch01_beat01",
        chapter_index=1,
        beat_index=1,
        target_words=650,
        pacing_type=PacingType.BUILD_UP,
        required_camera_angles=[CameraAngle.POV, CameraAngle.CLOSE_UP],
        characters_present=["char_hacker_zero", "char_debt_collector"],
        location_id="loc_slum_alley",
        micro_events=[
            MicroEvent(event_id="e1", description="催债帮派包围安全屋后巷"),
            MicroEvent(event_id="e2", description="黑客启动EMP陷阱前置开关")
        ],
        strict_prohibitions=["零号向对方妥协乞求"]
    )

    assert contract.chapter_index == 1
    assert len(contract.micro_events) == 2
    assert contract.zero_moralizer_enforced is True


def test_story_commit_cryptographic_chain():
    """测试 Narrative VCS 章节提交链与 SHA-256 唯一签名生成"""
    delta_1 = StateDelta(
        chapter_index=1,
        entity_mutations={"char_protagonist": {"power_rating": 250.0}}
    )
    commit_1 = StoryCommit.create(
        chapter_index=1,
        title="第1章 赛博雨夜",
        full_prose="霓虹灯在酸雨积水中扭曲闪烁。",
        state_delta=delta_1
    )

    assert len(commit_1.commit_id) == 16
    assert commit_1.parent_commit_id is None

    delta_2 = StateDelta(chapter_index=2)
    commit_2 = StoryCommit.create(
        chapter_index=2,
        title="第2章 神经脉冲",
        full_prose="接口插入的瞬间，剧烈的刺痛贯穿视网膜。",
        state_delta=delta_2,
        parent_commit_id=commit_1.commit_id
    )

    assert commit_2.parent_commit_id == commit_1.commit_id
    assert commit_2.commit_id != commit_1.commit_id
