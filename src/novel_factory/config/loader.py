"""
Config Loader - 工业级通用项目与题材配置加载器
支持声明式 YAML 加载、相对路径智能解析、跨题材法则自动校验与装配。
"""

from pathlib import Path
from typing import Any, Dict, Optional, Union
import yaml

from src.novel_factory.config.schemas import (
    GenreConfig,
    ModelRouteConfig,
    PacingConfig,
    PowerScaleConfig,
    PowerTierConfig,
    ProjectConfig,
    QCRulePackConfig,
)


class ProjectConfigLoader:
    """项目与题材配置解析器"""

    def __init__(self, root_dir: Optional[Union[str, Path]] = None):
        if root_dir is None:
            # 默认为当前代码所在项目的顶层根目录
            self.root_dir = Path(__file__).resolve().parents[3]
        else:
            self.root_dir = Path(root_dir).resolve()

    def _resolve_path(self, relative_or_absolute_path: Union[str, Path]) -> Path:
        """解析相对路径为绝对路径"""
        p = Path(relative_or_absolute_path)
        if p.is_absolute():
            return p
        return (self.root_dir / p).resolve()

    def load_yaml(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """安全加载并解析 YAML 文件"""
        target = self._resolve_path(file_path)
        if not target.exists():
            raise FileNotFoundError(f"配置文件不存在: {target}")

        with open(target, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data or {}

    def load_genre_config(self, genre_file_path: Union[str, Path]) -> GenreConfig:
        """加载特定题材法则配置 (Genre Spec)"""
        data = self.load_yaml(genre_file_path)

        # 解析战力梯队标尺
        power_scale = None
        if "power_scale" in data and data["power_scale"]:
            ps_raw = data["power_scale"]
            tiers = [PowerTierConfig(**t) for t in ps_raw.get("tiers", [])]
            power_scale = PowerScaleConfig(
                scale_name=ps_raw.get("scale_name", "通用能力等级"),
                tiers=tiers,
                max_cross_tier_gap=ps_raw.get("max_cross_tier_gap", 1)
            )

        return GenreConfig(
            genre=data.get("genre", "UNIVERSAL"),
            name=data.get("name", "通用题材"),
            power_scale=power_scale,
            custom_relation_types=data.get("custom_relation_types", []),
            genre_banned_cliches=data.get("genre_banned_cliches", []),
            exclusive_item_categories=data.get("exclusive_item_categories", []),
            world_rules=data.get("world_rules", {})
        )

    def load_pacing_config(self, pacing_file_path: Union[str, Path]) -> PacingConfig:
        """加载节奏心跳配置 (Pacing Spec)"""
        data = self.load_yaml(pacing_file_path)
        return PacingConfig(
            pacing_name=data.get("pacing_name", data.get("pacing", "DEFAULT_PACING")),
            target_words_per_chapter=data.get("target_words_per_chapter", 3000),
            beats_per_chapter=data.get("beats_per_chapter", 4),
            pacing_sequence=data.get("pacing_sequence", ["HOOK", "BUILD_UP", "CLIMAX", "HOOK_CLIFFHANGER"]),
            climax_frequency_chapters=data.get("climax_frequency_chapters", 5)
        )

    def load_project_master(self, project_file_path: Union[str, Path] = "project.yaml") -> ProjectConfig:
        """
        加载项目顶层总控配置，并级联装配题材、节奏、质检与模型
        """
        raw = self.load_yaml(project_file_path)

        # 1. 题材配置挂载
        genre_path = ""
        genre_obj = None
        if "genre" in raw and isinstance(raw["genre"], dict):
            genre_path = raw["genre"].get("config_path", "")
            if genre_path:
                genre_obj = self.load_genre_config(genre_path)

        # 2. 叙事节奏配置挂载
        pacing_path = ""
        pacing_obj = None
        if "pacing" in raw and isinstance(raw["pacing"], dict):
            pacing_path = raw["pacing"].get("config_path", "")
            if pacing_path:
                pacing_obj = self.load_pacing_config(pacing_path)

        # 3. 质检与反套路配置
        qc_raw = raw.get("qc_pipeline", {})
        qc_obj = QCRulePackConfig(
            rule_packs=qc_raw.get("rule_packs", []),
            repetition_rules=qc_raw.get("repetition_rules"),
            auto_patch_on_failure=qc_raw.get("auto_patch_on_failure", True),
            max_local_patch_retries=qc_raw.get("max_local_patch_retries", 3)
        )

        # 4. 模型路由
        models_raw = raw.get("models", {})
        models_obj = ModelRouteConfig(
            director_agent=models_raw.get("director_agent", "gemini-3.1-pro-preview"),
            writer_agent=models_raw.get("writer_agent", "gemini-3.8-flash"),
            judge_agent=models_raw.get("judge_agent", "gemini-3.5-flash-lite"),
            enable_prompt_caching=models_raw.get("enable_prompt_caching", True),
            cost_limit_per_chapter_cny=models_raw.get("cost_limit_per_chapter_cny", 0.40)
        )

        return ProjectConfig(
            project_name=raw.get("project_name", "UNTITLED_NOVEL"),
            project_title=raw.get("project_title", "未命名长篇小说"),
            version=raw.get("version", "1.0.0"),
            genre_config_path=genre_path,
            pacing_config_path=pacing_path,
            qc=qc_obj,
            models=models_obj,
            genre=genre_obj,
            pacing=pacing_obj
        )
