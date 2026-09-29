"""
生成一本可直接投产的样板书大纲（40 章 / 3 卷，赛博朋克题材）。

用途：为无 API Key 的离线全链路生产提供真实的输入。
大纲本身是人工设计的（主线目标、分卷危机、每章冲突与钩子都具体可执行），
不是脚手架占位文案——否则大纲校验会直接判 ERROR。
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.novel_factory.controller.doc_outliner import DOCOutliner
from src.novel_factory.controller.outline_store import CastMember, OutlineStore
from src.novel_factory.schemas.beat_contract import (
    ChapterOutline,
    MasterArcOutline,
    VolumeOutline,
)

TOTAL = 40

# 每卷的章节冲突脚本：(标题关键词, 核心冲突, 章末钩子)
VOL1 = [
    ("破损的接口", "零号在酸雨后巷被荒坂猎犬围堵，义体过载前必须脱身", "陌生身影从雨里走出"),
    ("变电箱陷阱", "零号诱敌进入变电箱，强行反黑对方的战术目镜", "解码器跳出不属于任何协议的乱码"),
    ("黑市的价码", "零号向赛博巫医求医，对方开出无法承受的价码", "巫医说出了母亲的名字"),
    ("旧档案", "零号潜入市政档案库调取母亲的死亡记录", "记录上的死亡时间比她下葬早了三天"),
    ("第一次交锋", "荒坂安保追至档案库，零号被迫正面交手", "对方的战术编号与母亲档案上的一致"),
    ("断线的证人", "唯一证人老秤在会面前一小时被灭口", "老秤临死前把一枚芯片塞进了零号口袋"),
    ("芯片里的东西", "零号破译芯片，发现一份被删除的人体实验名单", "名单第一行是他自己的名字"),
    ("通缉令", "荒坂发布全城通缉，零号的义体被远程标记", "他的左手开始不受控制地抽搐"),
    ("裴照的条件", "情报贩子裴照提出合作，条件是交出芯片", "裴照袖口露出与猎犬相同的纹身"),
    ("卷一终：雨停", "零号识破裴照的双面身份，在码头设局反制", "码头集装箱里站着一个与他长得一模一样的人"),
]

VOL2 = [
    ("复制体", "零号面对与自己同源的复制体，无法判断谁是原件", "复制体报出了只有他知道的童年暗号"),
    ("神经烙印", "巫医检测出零号颅内有第三方植入的神经烙印", "烙印的激活码掌握在荒坂手里"),
    ("苏漓入局", "地下医生苏漓主动接触，声称能移除烙印", "苏漓的工具箱里有母亲的旧工牌"),
    ("三天期限", "荒坂发出最后通牒：三天内交出芯片否则远程引爆烙印", "倒计时在视网膜上开始跳动"),
    ("旧同僚", "零号找到母亲当年的同事白鹭，对方已精神崩溃", "白鹭反复念叨着七号实验体"),
    ("七号", "零号查明七号实验体的编号规则，推算出自己是第几号", "他不是七号，七号另有其人"),
    ("苏漓的手术", "苏漓冒险为零号剥离烙印，手术中途断电", "醒来时苏漓不见了，手术台上留着一封信"),
    ("信里的坐标", "零号按信中坐标找到废弃实验站", "实验站的营养舱里还泡着十七个人"),
    ("唤醒", "零号唤醒其中一人，对方叫出了他母亲的称呼", "那人说：你母亲还活着"),
    ("卷二终：活人", "零号冲击荒坂医疗塔寻找母亲，遭遇复制体军团", "母亲的病房是空的，墙上写着两个字：快跑"),
]

VOL3 = [
    ("快跑", "零号在医疗塔坍塌前带走唯一线索，被复制体追击", "追击者摘下面罩，是白鹭"),
    ("白鹭的真相", "白鹭坦白自己才是第一批实验体，精神崩溃是伪装", "白鹭手里有荒坂董事会的名单"),
    ("董事会名单", "零号发现名单上有一个本该在二十年前死去的名字", "那个名字是他父亲的"),
    ("裴照再现", "裴照带着半数证据回归，要求共同行动", "裴照的义体里装着母亲的记忆备份"),
    ("记忆备份", "零号读取备份，看到母亲主动参与实验的画面", "母亲在画面里对着镜头说：对不起"),
    ("动机", "零号查明母亲参与实验是为了保住他的命", "代价是另外十六个孩子"),
    ("十六人", "幸存者要求零号交出自己抵命", "零号没有反驳，只是问了一句：谁下的令"),
    ("顶层", "零号突入荒坂顶层，与父亲隔着一张桌子对坐", "父亲推过来一杯酒，说：你比我预想的慢了三年"),
    ("卷三终·上：清算", "零号公开全部证据，引爆全城舆论与暴动", "父亲在直播画面里按下了一个红色按钮"),
    ("卷三终·下：雨夜尽头", "全城义体同时过载，零号在崩溃的城市里做出最后选择", "雨停了。他第一次听见自己真实的心跳"),
]

VOLUMES = [
    ("第一卷 断线", "零号被全城通缉，必须在七日内找到唯一证人洗清嫌疑", 1, 10, VOL1),
    ("第二卷 复制", "零号发现自己是人体实验的产物，须在烙印引爆前找到解法", 11, 20, VOL2),
    ("第三卷 清算", "零号直面幕后主使，必须在复仇与十六名幸存者之间做出抉择", 21, 30, VOL3),
]

CAST = [
    ("char_zero", "零号", "CHARACTER", {"tier_or_rank": "初级民用植入", "power_rating": 120.0}),
    ("char_hunter", "荒坂猎犬", "CHARACTER", {"tier_or_rank": "军规级战术改装", "power_rating": 460.0}),
    ("char_medic", "赛博巫医", "CHARACTER", {"tier_or_rank": "纯血自然人", "power_rating": 40.0}),
    ("char_peizhao", "裴照", "CHARACTER", {"tier_or_rank": "初级民用植入", "power_rating": 180.0}),
    ("char_suli", "苏漓", "CHARACTER", {"tier_or_rank": "初级民用植入", "power_rating": 110.0}),
    ("char_bailu", "白鹭", "CHARACTER", {"tier_or_rank": "重度义体化", "power_rating": 1200.0}),
    ("char_father", "荒坂垣", "CHARACTER", {"tier_or_rank": "重度义体化", "power_rating": 2400.0}),
    ("item_chip", "染血的芯片", "ITEM", {"rarity": "唯一"}),
    ("loc_alley", "酸雨后巷", "LOCATION", {}),
    ("loc_tower", "荒坂医疗塔", "LOCATION", {}),
]

LORE = [
    {
        "entry_id": "lore_acid_rain", "entity_type": "SYSTEM_RULE", "name": "工业酸雨腐蚀法则",
        "primary_keys": ["酸雨", "雨"], "content":
            "雨水含强酸性合成剂，裸露义体接缝在三十分钟内会电阻过载，"
            "过载后神经反馈延迟约零点四秒。",
        "is_global": True, "valid_from_chapter": 1,
    },
    {
        "entry_id": "lore_chrome_tier", "entity_type": "SYSTEM_RULE", "name": "义体化等级与神经负荷",
        "primary_keys": ["义体", "植入", "改装"], "content":
            "义体化率越高，免疫抑制剂依赖越强；超过八成即游走在赛博精神病边缘。",
        "is_global": True, "valid_from_chapter": 1,
    },
    {
        "entry_id": "lore_arasaka", "entity_type": "FACTION", "name": "荒坂财团",
        "primary_keys": ["荒坂"], "secondary_keys": ["财团", "猎犬"],
        "content": "荒坂财团掌控夜之城的义体黑市与市政档案系统，安保部门代号猎犬。",
        "is_global": False, "valid_from_chapter": 1,
    },
    {
        "entry_id": "lore_black_clinic", "entity_type": "LOCATION", "name": "义体黑市",
        "primary_keys": ["黑市", "巫医"], "content":
            "义体黑市由赛博巫医经营，交易不留记录，只认现货与人情。",
        "is_global": False, "valid_from_chapter": 1,
    },
]

FORESHADOWS = [
    ("fs_chip", "零号颈后那枚来历不明的军规级芯片", 1, ["芯片", "颈后"], "MAIN_LINE"),
    ("fs_mother", "母亲死亡时间与下葬时间对不上", 4, ["母亲", "死亡记录"], "MAIN_LINE"),
    ("fs_tattoo", "裴照袖口与猎犬相同的纹身", 9, ["纹身", "裴照"], "ARC_LEVEL"),
    ("fs_number7", "七号实验体究竟是谁", 16, ["七号", "实验体"], "ARC_LEVEL"),
    ("fs_father", "董事会名单上那个本该死去的名字", 23, ["名单", "父亲"], "MAIN_LINE"),
]

THREADS = [
    ("t_main", "复仇主线", "MAIN", 1, None),
    ("t_identity", "身世之谜", "SECONDARY", 1, 30),
    ("t_romance", "苏漓感情线", "ROMANCE", 13, 30),
    ("t_city", "夜之城势力格局", "BACKGROUND", 1, None),
]


def build() -> OutlineStore:
    o = DOCOutliner()
    o.set_master_arc(MasterArcOutline(
        arc_id="arc_neon_rain",
        title="霓虹雨夜：断线者",
        core_theme="被规则碾碎的人，如何重新定义规则",
        protagonist_ultimate_goal="查明母亲之死的真相，并让下令者在全城面前付出代价",
        world_setting_summary=(
            "近未来夜之城，义体化率决定社会阶层。荒坂财团掌控黑市与档案系统，"
            "酸雨终年不停，底层人用身体零件抵押债务。"
        ),
        target_total_chapters=TOTAL,
    ))

    for vi, (title, crisis, start, end, chapters) in enumerate(VOLUMES, start=1):
        o.add_volume(VolumeOutline(
            volume_index=vi, volume_id=f"vol_{vi:02d}", title=title,
            core_crisis=crisis, climax_milestone_id=f"milestone_v{vi}",
            chapter_start=start, chapter_end=end,
            key_antagonists=["char_hunter"] if vi == 1 else ["char_bailu", "char_father"],
            key_rewards=["item_chip"],
        ))
        for offset, (name, conflict, hook) in enumerate(chapters):
            ci = start + offset
            cast_for_chapter = ["char_zero"]
            if vi == 1:
                cast_for_chapter.append("char_hunter" if offset < 6 else "char_peizhao")
            elif vi == 2:
                cast_for_chapter.append("char_suli" if offset >= 2 else "char_medic")
            else:
                cast_for_chapter.append("char_bailu" if offset < 5 else "char_father")
            o.add_chapter(ChapterOutline(
                chapter_index=ci,
                title=f"第 {ci} 章 {name}",
                core_conflict=conflict,
                expected_cliffhanger=hook,
                location_id="loc_tower" if vi == 3 else "loc_alley",
                key_characters=cast_for_chapter,
                planned_beats_count=4,
            ))

    # 第 31~40 章：尾声卷，留作未规划区间以验证 require-outline 的拒绝行为
    store = OutlineStore(o)
    for eid, name, etype, payload in CAST:
        store.add_cast(CastMember(
            entity_id=eid, name=name, entity_type=etype,
            created_chapter=1, payload=payload,
        ))
    store.lore = list(LORE)
    return store


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("sample_book/outline.yaml")
    store = build()
    store.save(out)
    report = store.validate()
    print(f"已生成样板书大纲: {out}")
    print(report.format_summary())
    print(f"演员表 {len(store.cast)} 个实体 | 设定词条 {len(store.lore)} 条")
    print(f"未规划章节数: {len(store.unplanned_chapters(1, TOTAL))} "
          f"（第 31~40 章有意留空，用于验证 --require-outline 的拒绝行为）")


if __name__ == "__main__":
    main()
