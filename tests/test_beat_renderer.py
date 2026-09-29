"""
Tests for Beat Renderer - 节拍 Prompt 编译与输出解析测试
"""

from src.novel_factory.codex.codex_assembler import AssembledContext
from src.novel_factory.pipeline.beat_renderer import BeatRenderer
from src.novel_factory.schemas.beat import BeatContract, CameraAngle, MicroEvent, PacingType


def test_beat_renderer_prompt_compilation():
    """测试将契约与上下文渲染为专业 Writer Agent 指令"""
    renderer = BeatRenderer()

    assembled = AssembledContext(
        chapter_index=1,
        beat_id="ch01_beat01",
        global_block="【全局法则】当前世界为赛博朋克近未来",
        tracked_entities_block="【在场实体】零号（初级义体植入）",
        cascaded_lore_block="【触发设定】黑市义体暗藏后门",
        active_entry_ids=["lore_black_market"],
        estimated_tokens=200,
        raw_full_context="【全局法则】当前世界为赛博朋克近未来\n【在场实体】零号"
    )

    beat = BeatContract(
        beat_id="ch01_beat01",
        chapter_index=1,
        beat_index=1,
        target_words=600,
        pacing_type=PacingType.BUILD_UP,
        required_camera_angles=[CameraAngle.POV, CameraAngle.REACTION_CAM],
        characters_present=["char_zero"],
        location_id="loc_alley",
        micro_events=[
            MicroEvent(event_id="e1", description="义体接口因酸雨发生接触不良短路"),
            MicroEvent(event_id="e2", description="后方脚步声逼近，零号熄灭烟头")
        ],
        strict_prohibitions=["零号向对方乞求"]
    )

    compiled = renderer.compile_writer_prompt(
        assembled_context=assembled,
        scene_beat=beat,
        dynamic_ban_list=["冷哼", "暴喝"]
    )

    sys_p = compiled["system_prompt"]
    user_p = compiled["user_prompt"]

    # 1. 验证硬规则
    assert "Show, Don't Tell" in sys_p
    assert "微事件密度约束" in sys_p

    # 2. 验证机位与微事件注入
    assert "围观震惊反应机位" in user_p
    assert "义体接口因酸雨发生接触不良短路" in user_p
    assert "冷哼, 暴喝" in user_p
    assert "零号向对方乞求" in user_p


def test_beat_renderer_parse_output():
    """测试解析模型生成输出"""
    renderer = BeatRenderer()
    raw_llm = "   酸雨倾泻在破旧的霓虹灯管上。零号靠在锈蚀的铁门旁。   "
    output = renderer.parse_output("ch01_beat01", raw_llm)

    assert output.beat_id == "ch01_beat01"
    assert output.prose == "酸雨倾泻在破旧的霓虹灯管上。零号靠在锈蚀的铁门旁。"
    assert output.actual_words == len(output.prose)
    assert output.qc_passed is False
