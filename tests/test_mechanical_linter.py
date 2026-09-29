"""
Tests for Mechanical Linter - 配置驱动机械质检引擎测试
"""

from pathlib import Path
from src.novel_factory.qc.mechanical_linter import MechanicalLinter, Severity


def test_zero_moralizer_detection_from_config():
    """测试通过 YAML 加载的零议论反说教硬规则拦截"""
    linter = MechanicalLinter()
    dirty_text = (
        "主角拔掉数据线。\n"
        "这一幕让他深深明白，在这个残酷的社会唯有实力才是立足的根本。\n"
        "殊不知，这不过是命运的齿轮刚刚开始转动而已。"
    )

    report = linter.lint_text(dirty_text)
    assert report.passed is False
    assert report.total_errors >= 2
    categories = [v.category for v in report.violations]
    assert "ZERO_MORALIZER" in categories


def test_empty_filler_detection_from_config():
    """测试通过 YAML 加载的空洞连接词拦截"""
    linter = MechanicalLinter()
    dirty_text = (
        "不仅如此，敌方的巡逻无人机正在逼近。\n"
        "值得注意的是，安全通道已被锁死。\n"
        "然而，就在这时，警报声撕裂了夜空。"
    )

    report = linter.lint_text(dirty_text)
    assert report.total_errors >= 3
    categories = [v.category for v in report.violations]
    assert "EMPTY_FILLER" in categories


def test_cardboard_cliche_detection_from_config():
    """测试陈腐套话与刻板神态拦截"""
    linter = MechanicalLinter()
    dirty_text = (
        "他眼神中闪过一丝戏谑。\n"
        "他嘴角勾起了一抹冷笑。\n"
        "在场众人无不倒吸了一口凉气。"
    )

    report = linter.lint_text(dirty_text)
    assert report.total_warnings >= 3
    cliches = [v for v in report.violations if v.category == "CARDBOARD_CLICHE"]
    assert len(cliches) >= 3


def test_custom_user_rule_loading():
    """测试用户完全自定义专属规则字典加载（代码绝不干涉题材）"""
    custom_config = {
        "thresholds": {
            "min_pass_score": 90.0,
            "error_penalty": 10.0,
            "warning_penalty": 5.0
        },
        "rules": [
            {
                "id": "CUSTOM_NO_DETECTIVE_CATCHPHRASE",
                "category": "GENRE_SPECIFIC",
                "severity": "ERROR",
                "enabled": True,
                "pattern": "真相只有一个",
                "message": "禁止使用过于低幼柯南式的名台词",
                "suggestion": "改用刑侦物证推理表述"
            }
        ]
    }

    custom_linter = MechanicalLinter(rule_configs=[custom_config])
    text = "老刑警掐灭烟头，冷冷说道：‘真相只有一个。’"
    report = custom_linter.lint_text(text)

    assert report.passed is False
    assert report.total_errors == 1
    assert report.violations[0].rule_id == "CUSTOM_NO_DETECTIVE_CATCHPHRASE"


def test_clean_universal_text_passes_lint():
    """测试高质量、动作视听充实、无说教的干净文本通过质检"""
    linter = MechanicalLinter()
    clean_text = (
        "酸雨拍打在合金百叶窗上，发出沉闷的脆响。\n"
        "房间内只剩下散热风扇尖锐的蜂鸣声。\n"
        "零号将微型激光割刀贴在芯片边缘，手指没有丝毫晃动。\n"
        "桌对面的中间人猛地前倾身体，皮质手套在桌面上压出一道深痕。\n"
        "‘开价翻倍。’中间人的声线带着电流杂音。"
    )

    report = linter.lint_text(clean_text)
    assert report.passed is True
    assert report.total_errors == 0
    assert report.score >= 90.0


def test_ast_parsing_and_tail_moralizer_pruning():
    """测试 AST 解析与段尾说教剪枝器"""
    linter = MechanicalLinter()
    
    text_with_sermon = (
        "林动一拳砸穿石壁，碎屑飞溅。\n"
        "这一幕让他深深明白弱肉强食才是立足的根本。\n\n"
        "小貂在半空中翻了个筋斗。\n"
        "殊不知，这不过是命运的齿轮刚刚开始转动。"
    )
    
    cleaned, pruned_count = linter.prune_tail_moralizers(text_with_sermon)
    assert pruned_count >= 1
    assert "这一幕让他深深明白" not in cleaned
    assert "林动一拳砸穿石壁，碎屑飞溅。" in cleaned

