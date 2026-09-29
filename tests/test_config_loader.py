"""
Tests for Config Subsystem - 全题材通用声明式配置加载与法则装配测试
验证：
1. 默认 project.yaml 完整层级解析；
2. 仙侠、科幻、悬疑、都市、星际、历史 6 大题材法则包加载；
3. 战力阶梯梯队 (PowerScale) 索引与阶差计算；
4. 节奏心跳模板与质检配置映射。
"""

from pathlib import Path
import pytest

from src.novel_factory.config.loader import ProjectConfigLoader
from src.novel_factory.config.schemas import GenreConfig, PacingConfig, ProjectConfig


@pytest.fixture
def loader():
    return ProjectConfigLoader()


def test_load_project_master(loader):
    """测试主工程配置文件解析"""
    proj = loader.load_project_master("project.yaml")
    assert isinstance(proj, ProjectConfig)
    assert proj.project_name == "CYBER_NIGHT_2088"
    assert proj.version == "1.0.0"
    assert proj.models.cost_limit_per_chapter_cny == 0.40
    assert proj.genre is not None
    assert proj.genre.genre == "CYBERPUNK_SCIFI"


def test_load_all_six_genres(loader):
    """测试 6 大核心网文题材领域法则包完全解析"""
    genre_files = [
        "configs/genres/cyberpunk_scifi.yaml",
        "configs/genres/suspense_mystery.yaml",
        "configs/genres/xianxia_cultivation.yaml",
        "configs/genres/urban_supernatural.yaml",
        "configs/genres/space_opera.yaml",
        "configs/genres/historical_kingdom.yaml"
    ]

    for g_path in genre_files:
        p = Path(g_path)
        assert p.exists(), f"题材配置文件丢失: {g_path}"
        g_cfg = loader.load_genre_config(p)
        assert isinstance(g_cfg, GenreConfig)
        assert len(g_cfg.genre) > 0
        assert len(g_cfg.name) > 0
        assert len(g_cfg.genre_banned_cliches) > 0

        # 验证力量体系标尺存在
        if g_cfg.power_scale:
            assert len(g_cfg.power_scale.tiers) >= 3
            assert g_cfg.power_scale.max_cross_tier_gap >= 1


def test_xianxia_power_scale_hierarchy(loader):
    """验证修仙境界梯队索引与越阶计算"""
    xianxia = loader.load_genre_config("configs/genres/xianxia_cultivation.yaml")
    scale = xianxia.power_scale
    assert scale is not None

    mortal_idx = scale.get_tier_index("TIER_MORTAL")
    qi_idx = scale.get_tier_index("TIER_QI_CONDENSATION")
    core_idx = scale.get_tier_index("TIER_GOLDEN_CORE")
    nascent_idx = scale.get_tier_index("TIER_NASCENT_SOUL")

    assert mortal_idx == 0
    assert qi_idx == 1
    assert core_idx == 3
    assert nascent_idx == 4

    # 练气与元婴阶差为 3，远超允许的跨阶差值 1
    assert nascent_idx - qi_idx == 3
    assert (nascent_idx - qi_idx) > scale.max_cross_tier_gap


def test_pacing_config_loading(loader):
    """验证节奏节拍曲线解析"""
    pacing = loader.load_pacing_config("configs/pacing/webnovel_high_octane.yaml")
    assert isinstance(pacing, PacingConfig)
    assert pacing.beats_per_chapter >= 3
    assert "CLIMAX" in pacing.pacing_sequence or "HOOK" in pacing.pacing_sequence
