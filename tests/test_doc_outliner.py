import pytest
from src.novel_factory.controller.doc_outliner import DOCOutliner
from src.novel_factory.core.event_store import WorldSnapshot
from src.novel_factory.graph.causal_dag import CausalDAG, CausalNode, NodeStatus
from src.novel_factory.schemas.beat_contract import (
    ArcStatus,
    BeatContract,
    CameraAngle,
    ChapterOutline,
    MasterArcOutline,
    MicroEvent,
    PacingType,
    VolumeOutline,
)


def test_hierarchical_outline_creation_and_snowflake_beats():
    """验证四级雪花大纲构建与章节节拍自动分解"""
    outliner = DOCOutliner()
    
    # 1. Level 1: 全书宏观主线
    master_arc = MasterArcOutline(
        arc_id="arc_01",
        title="武动大荒：石符逆袭路",
        core_theme="弱肉强食与守护至亲",
        protagonist_ultimate_goal="踏入祖境，诛灭异魔",
        world_setting_summary="天玄大陆，元力与精神力并存的世界",
        target_total_chapters=120
    )
    outliner.set_master_arc(master_arc)
    
    # 2. Level 2: 第一卷
    vol1 = VolumeOutline(
        volume_index=1,
        volume_id="vol_01",
        title="青阳风云",
        core_crisis="林氏家族分家大比与雷谢两家逼迫",
        climax_milestone_id="ms_clan_tournament_champion",
        chapter_start=1,
        chapter_end=25
    )
    outliner.add_volume(vol1)

    # 3. Level 3: 第 1 章大纲
    ch1 = ChapterOutline(
        chapter_index=1,
        title="淬体与不屈",
        core_conflict="林动因父亲重伤遭宗族子弟冷嘲热讽",
        expected_cliffhanger="后山神秘血池中泛起微弱紫光，水底似乎有异物",
        location_id="loc_back_mountain",
        key_characters=["char_lin_dong", "char_lin_xia", "char_lin_shan"]
    )
    outliner.add_chapter(ch1)

    # 4. Level 4: 节拍自动雪花切分
    beats = outliner.auto_decompose_chapter_beats(1)
    assert len(beats) == 4
    
    pacing_sequence = [b.pacing_type for b in beats]
    assert pacing_sequence == [
        PacingType.BUILD_UP,
        PacingType.COGNITIVE_GAP,
        PacingType.CATHARSIS_PAYOFF,
        PacingType.CLIFFHANGER_HOOK
    ]
    assert all(b.chapter_index == 1 for b in beats)
    assert ch1.beats == beats


def test_validate_beat_contract_pass_and_fail():
    """验证分镜节拍契约严格前置断言"""
    outliner = DOCOutliner()
    
    valid_beat = BeatContract(
        beat_id="ch01_b01",
        chapter_index=1,
        beat_index=1,
        target_words=700,
        pacing_type=PacingType.BUILD_UP,
        required_camera_angles=[CameraAngle.POV, CameraAngle.CLOSE_UP],
        characters_present=["hero"],
        location_id="loc_training_ground",
        micro_events=[MicroEvent(event_id="e1", description="苦练通背拳")]
    )
    
    errors = outliner.validate_beat_contract(valid_beat)
    assert len(errors) == 0

    # 1. 目标字数越界（合规区间可配置，此处显式收紧以验证边界判定）
    strict_outliner = DOCOutliner(min_beat_words=400, max_beat_words=1200)
    invalid_words_beat = valid_beat.model_copy(update={"target_words": 200})
    err1 = strict_outliner.validate_beat_contract(invalid_words_beat)
    assert any("字数" in e for e in err1)
    # 默认区间放宽到 [100, 4000]，与 BeatContract schema 保持一致
    assert outliner.validate_beat_contract(invalid_words_beat) == []

    # 2. 在场角色为空
    no_char_beat = valid_beat.model_copy(update={"characters_present": []})
    err2 = outliner.validate_beat_contract(no_char_beat)
    assert any("在场角色为空" in e for e in err2)

    # 3. 缺乏镜头机位
    no_camera_beat = valid_beat.model_copy(update={"required_camera_angles": []})
    err3 = outliner.validate_beat_contract(no_camera_beat)
    assert any("镜头机位" in e for e in err3)

    # 4. 缺乏离散微事件清单（空洞注水检测）
    no_event_beat = valid_beat.model_copy(update={"micro_events": []})
    err4 = outliner.validate_beat_contract(no_event_beat)
    assert any("微事件" in e for e in err4)


def test_validate_beat_against_world_snapshot_and_dag():
    """验证结合世界快照（存活性）与因果 DAG（前置达成）的联合断言"""
    outliner = DOCOutliner()
    
    # 模拟世界快照：角色 ghost 已经阵亡
    snapshot = WorldSnapshot(
        chapter_index=10,
        last_sequence_num=50,
        entities={
            "hero": {"entity_id": "hero", "is_alive": True},
            "ghost": {"entity_id": "ghost", "is_alive": False, "killed_at_chapter": 8}
        }
    )
    
    # 模拟因果 DAG：前置任务尚未达成
    dag = CausalDAG()
    dag.add_node(CausalNode(node_id="find_key", title="寻找钥匙", status=NodeStatus.IN_PROGRESS))

    beat = BeatContract(
        beat_id="ch10_b02",
        chapter_index=10,
        beat_index=2,
        target_words=800,
        pacing_type=PacingType.CATHARSIS_PAYOFF,
        required_camera_angles=[CameraAngle.POV],
        characters_present=["hero", "ghost"],  # 死者在场
        location_id="loc_tomb",
        pre_conditions=["find_key"],          # 前置尚未完成
        micro_events=[MicroEvent(event_id="e1", description="开启墓门")]
    )

    errors = outliner.validate_beat_contract(beat, world_snapshot=snapshot, dag=dag)
    assert any("已死亡" in e for e in errors)
    assert any("DAG 前置未达成" in e for e in errors)


def test_verify_beat_postconditions():
    """测试分镜执行后置断言核验"""
    outliner = DOCOutliner()
    beat = BeatContract(
        beat_id="ch02_b03",
        chapter_index=2,
        beat_index=3,
        target_words=700,
        pacing_type=PacingType.CATHARSIS_PAYOFF,
        characters_present=["hero"],
        location_id="loc_arena",
        post_conditions=["通背九响", "震退林山"],
        micro_events=[MicroEvent(event_id="e1", description="施展通背拳打出九响")]
    )

    # 成功正文包含后置关键字
    good_prose = "林动气势骤变，衣袍翻飞间连续打出通背九响，沉闷的拳劲当场震退林山数步。"
    passed, missing = outliner.verify_beat_postconditions(beat, good_prose)
    assert passed is True
    assert len(missing) == 0

    # 失败正文漏掉要素
    bad_prose = "林动施展通背拳，击退了对手。"
    passed_bad, missing_bad = outliner.verify_beat_postconditions(beat, bad_prose)
    assert passed_bad is False
    assert any("通背九响" in m for m in missing_bad)


def test_doc_outliner_serialization():
    """测试全量大纲序列化与反序列化"""
    outliner = DOCOutliner()
    outliner.set_master_arc(MasterArcOutline(
        arc_id="a1",
        title="序列化大纲",
        core_theme="测试",
        protagonist_ultimate_goal="飞升",
        world_setting_summary="仙侠"
    ))
    outliner.add_volume(VolumeOutline(
        volume_index=1,
        volume_id="v1",
        title="第一卷",
        core_crisis="危机",
        climax_milestone_id="m1",
        chapter_start=1,
        chapter_end=10
    ))
    
    data = outliner.to_dict()
    outliner2 = DOCOutliner.from_dict(data)
    
    assert outliner2.master_arc.title == "序列化大纲"
    assert outliner2.volumes[1].title == "第一卷"
