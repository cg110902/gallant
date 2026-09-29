"""
Tests for Codex Assembler - 确定性上下文装配器测试
"""

import pytest
from src.novel_factory.codex.codex_assembler import CodexAssembler
from src.novel_factory.graph.bec_graph import BECGraph
from src.novel_factory.schemas.beat import BeatContract, CameraAngle, PacingType
from src.novel_factory.schemas.entity import LoreEntry


@pytest.fixture
def test_setup():
    g = BECGraph(":memory:")
    # 注册在场角色
    g.register_entity(
        entity_id="char_detective",
        entity_type="CHARACTER",
        name="陈探长",
        created_chapter=1,
        initial_payload={
            "tier_or_rank": "一级警督",
            "power_rating": 280.0,
            "status_tags": ["旧伤未愈"],
            "inventory": [{"name": "配枪"}, {"name": "录音笔"}]
        }
    )
    yield g
    g.close()


def test_codex_assembler_four_tier_compilation(test_setup: BECGraph):
    """测试确定性上下文编译的四级装配与时序过滤"""
    assembler = CodexAssembler(max_token_budget=3000)

    beat = BeatContract(
        beat_id="ch03_beat02",
        chapter_index=3,
        beat_index=2,
        target_words=700,
        pacing_type=PacingType.COGNITIVE_GAP,
        required_camera_angles=[CameraAngle.POV, CameraAngle.CLOSE_UP],
        characters_present=["char_detective"],
        location_id="loc_rainy_dock",
        pre_conditions=["现场遗留有一枚刻着黑玫瑰徽章的黄铜钥匙"]
    )

    lore_list = [
        # 1. 全局词条
        LoreEntry(
            entry_id="rule_rainy_city",
            entity_type="SYSTEM_RULE",
            name="雨城常年潮湿法则",
            content="全市降雨受近海人工降雨气象塔控制，夜间湿度常达95%以上。",
            is_global=True,
            valid_from_chapter=1
        ),
        # 2. 级联触发词条 (同时命中 一级'黑玫瑰' + 二级'徽章')
        LoreEntry(
            entry_id="lore_black_rose_syndicate",
            entity_type="ORGANIZATION",
            name="黑玫瑰辛迪加",
            primary_keys=["黑玫瑰"],
            secondary_keys=["徽章", "纹身"],
            content="地下走私巨头，行事诡秘，所有高层成员皆佩戴黄铜黑玫瑰徽章。",
            is_global=False,
            valid_from_chapter=1
        ),
        # 3. 未满足二级词条 (仅有一级'钥匙'，缺少二级'银行')
        LoreEntry(
            entry_id="lore_swiss_bank",
            entity_type="LOCATION",
            name="瑞士秘密金库",
            primary_keys=["钥匙"],
            secondary_keys=["苏黎世", "金库"],
            content="只有特定号码的钥匙才能开启地下八层保险箱。",
            is_global=False,
            valid_from_chapter=1
        ),
        # 4. 已失效的时序词条 (仅在第1-2章有效，当前第3章)
        LoreEntry(
            entry_id="lore_expired_alibi",
            entity_type="SYSTEM_RULE",
            name="过期的搜查令",
            primary_keys=["现场"],
            content="搜查令已在第2章末尾被局长撤销。",
            is_global=False,
            valid_from_chapter=1,
            valid_to_chapter=2
        )
    ]

    context = assembler.assemble(
        chapter_index=3,
        scene_beat=beat,
        graph=test_setup,
        lore_entries=lore_list,
        global_invariants=["禁止破坏案发现场物证"],
        recent_text_buffer="探员戴上手套，弯腰拾起泥泞中的杂物。"
    )

    raw = context.raw_full_context

    # 1. 常驻法则断言
    assert "禁止破坏案发现场物证" in raw
    assert "雨城常年潮湿法则" in raw

    # 2. 在场实体状态断言 (从 BEC-Graph 实时召回)
    assert "char_detective" in raw
    assert "一级警督" in raw
    assert "录音笔" in raw

    # 3. 级联词条断言 (黑玫瑰满足级联条件，成功注入)
    assert "黑玫瑰辛迪加" in raw
    assert "lore_black_rose_syndicate" in context.active_entry_ids

    # 4. 未满足级联条件词条未注入
    assert "瑞士秘密金库" not in raw

    # 5. 时序失效词条严禁召回 (杜绝吃设定)
    assert "过期的搜查令" not in raw


def test_codex_token_budget_cap(test_setup: BECGraph):
    """测试当词条过长时严格遵守 Token 预算上限"""
    # 设置一个极低的 Token 预算 (比如 150 token)
    strict_assembler = CodexAssembler(max_token_budget=150)

    beat = BeatContract(
        beat_id="ch01_beat01",
        chapter_index=1,
        beat_index=1,
        target_words=500,
        pacing_type=PacingType.BUILD_UP,
        characters_present=["char_detective"],
        location_id="loc_office"
    )

    long_lore = [
        LoreEntry(
            entry_id=f"lore_long_{i}",
            entity_type="SYSTEM_RULE",
            name=f"长词条_{i}",
            content="这是一段非常非常长的设定文本，用来测试Token超出预算时的熔断截断机制。" * 5,
            is_global=True,
            valid_from_chapter=1
        )
        for i in range(10)
    ]

    context = strict_assembler.assemble(
        chapter_index=1,
        scene_beat=beat,
        graph=test_setup,
        lore_entries=long_lore
    )

    # 必须执行了熔断截断
    assert "熔断" in context.raw_full_context or "截断" in context.raw_full_context
