"""
Tests for Trope Cooldown Tracker - 套路冷却与反转调度测试
"""

from src.novel_factory.codex.trope_cooldown import TropeCooldownTracker, TropeDefinition


def test_trope_cooldown_and_inversion_suggestions():
    """测试套路触发冷却拦截与反转建议输出"""
    tracker = TropeCooldownTracker()

    # 初始状态：拍卖会套路在第 1 章可用
    avail, rem, _ = tracker.check_availability("AUCTION_HEIST", current_chapter=1)
    assert avail is True
    assert rem == 0

    # 在第 5 章使用了拍卖会截胡套路
    tracker.record_trope_use("AUCTION_HEIST", chapter_index=5)

    # 在第 15 章再次尝试使用（冷却期为25章，应处于冷却中，剩余15章）
    avail_15, rem_15, suggestions = tracker.check_availability("AUCTION_HEIST", current_chapter=15)
    assert avail_15 is False
    assert rem_15 == 15
    assert len(suggestions) > 0  # 必须提供反转建议，例如反向坑杀或合谋做庄

    # 到了第 32 章（已过去27章，超出25章冷却），套路重新解冻可用
    avail_32, rem_32, _ = tracker.check_availability("AUCTION_HEIST", current_chapter=32)
    assert avail_32 is True
    assert rem_32 == 0


def test_custom_genre_trope_definition():
    """测试用户自定义题材套路规则"""
    custom_trope = TropeDefinition(
        trope_id="CYBER_DECK_VIRUS",
        name="接入网路遭遇脑机病毒陷阱",
        cooldown_chapters=10,
        inversion_recommendations=["病毒反被主角诱导至主网反噬巨企服务器"]
    )
    tracker = TropeCooldownTracker(custom_tropes=[custom_trope])

    tracker.record_trope_use("CYBER_DECK_VIRUS", chapter_index=2)
    avail, rem, suggs = tracker.check_availability("CYBER_DECK_VIRUS", chapter_index=5)

    assert avail is False
    assert rem == 7
    assert "反噬巨企服务器" in suggs[0]
