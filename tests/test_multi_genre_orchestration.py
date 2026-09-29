"""
Tests for Multi-Genre Orchestration & Anti-Drooling Breaker
测试全题材无代码化动态装配与运行期因果/质检拦截：
1. 修仙题材：战力梯队硬约束与天道越阶违规拦截；
2. 题材套话动态注入质检器；
3. 流式防流口水截断器在 Orchestrator 生产中的自动触发。
"""

from pathlib import Path
import tempfile
import yaml

from src.novel_factory.qc.contract_auditor import BeatContractAuditor
from src.novel_factory.orchestrator import NovelFactoryOrchestrator
from src.novel_factory.graph.invariant_checker import ProposedAction
from src.novel_factory.schemas.beat import BeatContract, CameraAngle, PacingType


def test_xianxia_power_tier_invariant_enforcement():
    """测试修仙题材战力天道不变式拦截：练气期小修士无法直接对元婴期老祖发动致命攻击"""
    # 构造修仙项目临时配置
    cfg_data = {
        "project_name": "IMMORTAL_LEGACY",
        "project_title": "万古仙尊",
        "version": "1.0.0",
        "genre": {
            "config_path": "configs/genres/xianxia_cultivation.yaml"
        },
        "pacing": {
            "config_path": "configs/pacing/webnovel_high_octane.yaml"
        },
        "qc_pipeline": {
            "rule_packs": ["configs/rules/anti_slop.yaml"],
            "auto_patch_on_failure": False
        },
        "models": {
            "cost_limit_per_chapter_cny": 0.50
        }
    }

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        yaml.dump(cfg_data, f)
        tmp_cfg_path = f.name

    try:
        orchestrator = NovelFactoryOrchestrator.from_project_config(
            config_path=tmp_cfg_path,
            db_path=":memory:"
        )

        # 注册练气期修士与元婴老祖
        orchestrator.graph.register_entity(
            entity_id="char_qi_novice",
            entity_type="CHARACTER",
            name="林凡",
            created_chapter=1,
            initial_payload={"tier_id": "TIER_QI_CONDENSATION", "power_rating": 20.0}
        )
        orchestrator.graph.register_entity(
            entity_id="char_nascent_ancestor",
            entity_type="CHARACTER",
            name="血煞老祖",
            created_chapter=1,
            initial_payload={"tier_id": "TIER_NASCENT_SOUL", "power_rating": 5000.0}
        )

        # 拟议一个练气强杀元婴的行为
        action = ProposedAction(
            actor_id="char_qi_novice",
            action_type="MELEE_ATTACK",
            target_id="char_nascent_ancestor"
        )

        snap = orchestrator.event_store.materialize_world_at(1)
        # 将图谱实体注入 snapshot 以便检验
        snap.entities["char_qi_novice"] = {"is_alive": True, "tier_id": "TIER_QI_CONDENSATION"}
        snap.entities["char_nascent_ancestor"] = {"is_alive": True, "tier_id": "TIER_NASCENT_SOUL"}

        report = orchestrator.invariant_checker.check_action(
            snapshot=snap,
            action=action,
            chapter_index=1
        )

        assert report.passed is False
        assert any(v.rule_name == "POWER_SCALE_OVERPOWERED_GAP" for v in report.violations)
        assert any("越阶" in v.message for v in report.violations)
        orchestrator.close()

    finally:
        Path(tmp_cfg_path).unlink(missing_ok=True)


def test_genre_banned_cliche_dynamic_injection():
    """测试修仙专属网络口水套话在 Linter 中被精准拦截"""
    cfg_data = {
        "project_name": "IMMORTAL_LEGACY",
        "project_title": "万古仙尊",
        "genre": {
            "config_path": "configs/genres/xianxia_cultivation.yaml"
        }
    }
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        yaml.dump(cfg_data, f)
        tmp_cfg_path = f.name

    try:
        orchestrator = NovelFactoryOrchestrator.from_project_config(
            config_path=tmp_cfg_path,
            db_path=":memory:"
        )

        # 提交一段带有“此子断不可留”和“恐怖如斯”的低质修仙口水文
        slop_text = (
            "血煞老祖脸色铁青。\n"
            "此子断不可留！\n"
            "对方的一身战力，竟然恐怖如斯！"
        )
        report = orchestrator.linter.lint_text(slop_text)
        assert report.passed is False
        matched = [v.matched_text for v in report.violations]
        assert "此子断不可留" in matched
        assert "恐怖如斯" in matched

        orchestrator.close()
    finally:
        Path(tmp_cfg_path).unlink(missing_ok=True)


def test_orchestrator_anti_drooling_stream_breaker():
    """测试 LLM 吐字发生流口水/死循环时，Orchestrator 自动截断至安全有效句子"""
    def drooling_writer(sys_p: str, user_p: str) -> str:
        # 模拟输出带有死循环狂奔的文本
        return (
            "刀锋撕裂了夜色。\n"
            "鲜血顺着刀尖滴落在地面上。\n"
            "。。。。。。。。。。。。。。。。。。。。"
        )

    orchestrator = NovelFactoryOrchestrator(llm_worker=drooling_writer)
    # 本用例聚焦机械质检闭环，显式关闭契约交付闸门以隔离被测关注点
    orchestrator.contract_auditor = BeatContractAuditor(
        enforce_word_count=False, enforce_camera_coverage=False, enforce_micro_events=False
    )

    beat = BeatContract(
        beat_id="ch01_b01",
        chapter_index=1,
        beat_index=1,
        target_words=500,
        pacing_type=PacingType.BUILD_UP,
        characters_present=[],
        location_id="loc_street"
    )

    result = orchestrator.produce_beat(
        chapter_index=1,
        scene_beat=beat,
        lore_entries=[]
    )

    # 验证连续狂奔的句号被成功截断
    assert "。。。。。。。。。。。。。。。。。。。。" not in result.prose
    assert "鲜血顺着刀尖滴落在地面上" in result.prose
    assert any("防流口水截断生效" in h for h in result.feedback_history)

    orchestrator.close()
