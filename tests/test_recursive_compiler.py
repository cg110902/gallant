import pytest
from src.novel_factory.codex.recursive_compiler import (
    CodexEntry,
    SelectiveLogic,
    CodexEntryCategory,
    RecursiveCodexCompiler,
)


def test_constant_rule_always_included():
    """验证常驻词条无条件注入"""
    compiler = RecursiveCodexCompiler(token_budget=1000)
    entries = [
        CodexEntry(
            entry_id="world_axiom",
            name="元力守恒定律",
            content="凡突破地元境，必吸纳纯阴之气，不可违背。",
            constant=True,
            insertion_order=10
        ),
        CodexEntry(
            entry_id="unrelated",
            name="某路人",
            content="无关路人资料",
            primary_keys=["路人甲"],
            constant=False
        )
    ]
    
    result = compiler.compile("林动在后山刻苦修炼。", entries)
    assert len(result.constant_entries) == 1
    assert result.constant_entries[0].entry_id == "world_axiom"
    assert "元力守恒定律" in result.formatted_prompt_block
    assert "某路人" not in result.formatted_prompt_block


def test_selective_dual_key_logic():
    """验证双键选择性触发逻辑门 (AND_ANY, AND_ALL, NOT_ANY)"""
    compiler = RecursiveCodexCompiler(token_budget=2000)
    entries = [
        # 1. AND_ANY: 必须包含主键，且包含任一次级键
        CodexEntry(
            entry_id="e_any",
            name="林琅天(仇敌状态)",
            content="林氏宗族分家生死大敌",
            primary_keys=["林琅天"],
            secondary_keys=["杀意", "大比", "仇恨"],
            selective_logic=SelectiveLogic.AND_ANY
        ),
        # 2. AND_ALL: 必须包含主键，且包含全部次级键
        CodexEntry(
            entry_id="e_all",
            name="涅盘心融合绝学",
            content="只有古墓与涅盘心同时出现才能使用的大法",
            primary_keys=["涅盘心"],
            secondary_keys=["古墓", "绫清竹"],
            selective_logic=SelectiveLogic.AND_ALL
        ),
        # 3. NOT_ANY: 包含主键，但严禁包含排除词
        CodexEntry(
            entry_id="e_not",
            name="林动(日常状态)",
            content="未开启吞噬之力的普通少年林动",
            primary_keys=["林动"],
            secondary_keys=["吞噬祖符", "魔化"],
            selective_logic=SelectiveLogic.NOT_ANY
        )
    ]

    # 场景 A: 命中林琅天 + 杀意 -> e_any 激活
    res_a = compiler.compile("林动注视着林琅天，胸中杀意如沸水翻涌。", entries)
    active_ids_a = [e.entry_id for e in res_a.activated_entries]
    assert "e_any" in active_ids_a
    assert "e_not" in active_ids_a  # 林动命中，且没有吞噬祖符/魔化

    # 场景 B: 仅有林琅天，无次级键 -> e_any 不应激活
    res_b = compiler.compile("远处那人正是林琅天，气质卓绝。", entries)
    active_ids_b = [e.entry_id for e in res_b.activated_entries]
    assert "e_any" not in active_ids_b

    # 场景 C: 命中涅盘心与古墓，但缺绫清竹 -> e_all 不激活
    res_c = compiler.compile("古墓石室内，悬浮着一颗散发温热光芒的涅盘心。", entries)
    active_ids_c = [e.entry_id for e in res_c.activated_entries]
    assert "e_all" not in active_ids_c

    # 场景 D: 命中涅盘心 + 古墓 + 绫清竹 -> e_all 激活
    res_d = compiler.compile("古墓石室内，绫清竹身形微颤，上方正是涅盘心。", entries)
    active_ids_d = [e.entry_id for e in res_d.activated_entries]
    assert "e_all" in active_ids_d

    # 场景 E: 命中林动 + 吞噬祖符 -> e_not 受到 NOT_ANY 抑制
    res_e = compiler.compile("林动祭起吞噬祖符，虚空扭曲。", entries)
    active_ids_e = [e.entry_id for e in res_e.activated_entries]
    assert "e_not" not in active_ids_e


def test_recursive_scanning_cascade():
    """验证 SillyTavern 风格的递归多级联触发与防死循环"""
    compiler = RecursiveCodexCompiler(token_budget=3000, max_recursion_depth=3)
    
    entries = [
        # 第 1 层触发：Prompt 提到 "石符"
        CodexEntry(
            entry_id="item_stone_amulet",
            name="神秘石符",
            content="自后山水池捡拾的奇物，内藏小貂这等远古天妖貂妖灵。",
            primary_keys=["石符"]
        ),
        # 第 2 层触发：石符正文中提到了 "小貂"
        CodexEntry(
            entry_id="char_diao",
            name="天妖貂阿貂",
            content="天妖貂族强者，为护送吞噬祖符肉身陨落。",
            primary_keys=["小貂", "天妖貂"]
        ),
        # 第 3 层触发：小貂正文中提到了 "吞噬祖符"
        CodexEntry(
            entry_id="item_ancestor_symbol",
            name="吞噬祖符",
            content="天地间八大祖符之一，掌控无尽吞噬之力，可吞噬万物元气。",
            primary_keys=["吞噬祖符"]
        ),
        # 第 4 层词条：提到 "八大祖符"，但 max_recursion_depth=3，应当截断或根据深度决定
        CodexEntry(
            entry_id="lore_eight_symbols",
            name="八大祖符神话",
            content="符祖留给这片天地的至高圣物。",
            primary_keys=["八大祖符"]
        ),
        # 互相引用闭环测试（小貂提到石符，石符提到小貂，防止死循环）
        CodexEntry(
            entry_id="cyclic_test",
            name="死循环测试",
            content="本条目提到了石符。",
            primary_keys=["死循环专用"]
        )
    ]

    # 输入初始文本只包含一级触发词 "石符"
    base_text = "林动从怀中摸出那一枚温凉的石符，眼神凝重。"
    result = compiler.compile(base_text, entries)
    
    activated_ids = [e.entry_id for e in result.activated_entries]
    assert "item_stone_amulet" in activated_ids
    assert "char_diao" in activated_ids
    assert "item_ancestor_symbol" in activated_ids
    
    # 验证级联深度记录
    assert result.activation_cascade_map["item_stone_amulet"] == 1
    assert result.activation_cascade_map["char_diao"] == 2
    assert result.activation_cascade_map["item_ancestor_symbol"] == 3


def test_token_budget_priority_trimming():
    """验证 Token 超限时基于 insertion_order 的优先级背包裁剪"""
    # 严格设置 Token 预算极小（如 60 Token，约 96 字符）
    compiler = RecursiveCodexCompiler(token_budget=60, chars_per_token=1.6)
    
    entries = [
        CodexEntry(
            entry_id="high_priority",
            name="绝密关键情报",
            content="林氏家族宗族大会定于三月后，胜者可入族藏宝阁选功法。" * 2,  # 约 60 字符 (38 tokens)
            primary_keys=["林氏"],
            insertion_order=10  # 优先级高
        ),
        CodexEntry(
            entry_id="low_priority",
            name="次要琐碎背景",
            content="青阳镇有三大家族，平日里偶有摩擦，酒肆林立热闹非凡。" * 2,  # 约 60 字符 (38 tokens)
            primary_keys=["林氏"],
            insertion_order=90  # 优先级低
        )
    ]

    # 两条都会被关键词 "林氏" 触发，但预算只能装下一条
    result = compiler.compile("关于林氏家族的一切动向。", entries)
    
    active_ids = [e.entry_id for e in result.activated_entries]
    dropped_ids = [e.entry_id for e in result.dropped_entries]
    
    assert "high_priority" in active_ids
    assert "low_priority" in dropped_ids
    assert result.total_estimated_tokens <= 60
