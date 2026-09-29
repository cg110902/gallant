"""
Offline Deterministic Writer - 无需 API Key 的确定性离线写手

它不是语言模型，而是一个**严格遵守节拍契约的程序化写手**：
解析 BeatRenderer 编译出的真实 Prompt，按字数、镜头机位、微事件、
后置状态与章末钩子的要求拼装中文正文。

存在的意义有三个，都是工程上的真实需求：
1. **离线冒烟生产**：没有 API Key 也能跑通全链路，验证闸门、治理与导出；
2. **CI 回归**：确定性输出使得跨版本的质检结果可比对；
3. **闸门自检**：如果一个严格照契约写作的写手都通不过质检，
   那说明闸门本身的标定有问题，而不是内容有问题。

它写不出好小说——它只负责证明流水线是通的。
"""

from dataclasses import dataclass, field
import hashlib
import random
import re
from typing import Any, Dict, List, Optional, Sequence

from src.novel_factory.llm.client import BaseLLMProvider, LLMGenerationResult


# ---------------------------------------------------------------- 素材库
# 分机位素材：每个机位的句式必须能被 BeatContractAuditor 的特征探针检出，
# 同时避开 anti_slop 规则包里的禁用套话（如"倒吸一口凉气"）。

POV_LINES = [
    "{who}数着自己的心跳，一下，两下。",
    "这一刻{who}只想着一件事：活下去。",
    "{who}在心里把每一条路都走了一遍，没有一条是通的。",
    "{who}心里迅速盘算着退路。",
    "{who}脑海里闪过三种应对，全都行不通。",
    "{who}忽然意识到自己漏掉了什么。",
    "{who}心头一紧，手指不自觉地蜷了一下。",
    "{who}想起三年前那个同样下着雨的夜晚。",
    "{who}暗道不好，这一步已经踏进了别人的局。",
    "{who}心中默数着对方换弹的间隔。",
    "这个念头在{who}心里只停留了半秒。",
]

CLOSE_UP_LINES = [
    "{thing}的金属外壳上凝着一层细密的水珠。",
    "{who}的指腹蹭过{thing}的刻痕，那里少了一块。",
    "血从指缝里渗出来，在{thing}上积成一小滩。",
    "{who}的指尖压在{thing}上，指节泛白。",
    "{thing}的边缘割破了掌心，血珠顺着纹路滑下。",
    "{who}的瞳孔骤然收缩成针尖大小。",
    "一道细小的裂痕爬过{thing}的表面。",
    "{who}腕骨上的旧疤在冷光里泛出青灰。",
    "{thing}接口处渗出一线幽蓝的电弧。",
    "{who}的喉结无声地滚动了一下。",
    "汗珠从{who}的眉骨滑进眼角。",
]

PANORAMIC_LINES = [
    "{place}的地面积水倒映着满街的广告灯，被脚步踩得粉碎。",
    "半空中悬着的巨幅投影切换了画面，冷光扫过整条街。",
    "远处传来警笛，声音在楼群之间来回折返。",
    "{place}的天色压得很低，云层里透出病态的橙红。",
    "远处的高架桥上，磁悬列车拖着长长的光带掠过。",
    "整条街道浸在雨幕里，霓虹招牌扭曲成一片模糊的色块。",
    "{place}空无一人，只有排水口翻涌着灰白的泡沫。",
    "四周的楼体广告牌同时切换，冷光洒满半条巷子。",
    "雨水顺着{place}的铁皮檐口连成一道水帘。",
    "{place}上空盘旋着三架巡逻无人机，红灯有节奏地闪烁。",
]

REACTION_LINES = [
    "{who}一脚踹开挡在面前的铁门。",
    "{who}把{thing}换到左手，右手垂在身侧。",
    "{who}贴着墙角绕过去，没有发出任何声响。",
    "{who}突然停住，转身面对{place}的入口。",
    "围观的人群同时后退半步，有人手里的杯子摔碎在地。",
    "酒馆里的喧哗在一瞬间被掐断，只剩通风管的嗡鸣。",
    "几个看热闹的家伙脸色发白，转身就往巷口跑。",
    "人群中爆发出一阵压不住的骚动。",
    "所有人的目光都钉在{who}身上，没人敢先开口。",
    "旁边摊主的手停在半空，汤勺里的汤洒了一地。",
    "有人低声惊呼，随即被同伴死死捂住嘴。",
]

ACTION_LINES = [
    "{who}一脚踹开挡在面前的铁门。",
    "{who}把{thing}换到左手，右手垂在身侧。",
    "{who}贴着墙角绕过去，没有发出任何声响。",
    "{who}突然停住，转身面对{place}的入口。",
    "{who}侧身让过{thing}，反手扣住对方的腕关节。",
    "{who}把{thing}塞进内袋，转身贴着墙根移动。",
    "{who}抬手拨开挡路的铁架，脚下没有停。",
    "{who}用{thing}撬开锈死的接口，金属发出刺耳的摩擦声。",
    "{who}压低身形，从积水里捞起那枚{thing}。",
    "{who}把{thing}按在桌面上，指节抵着桌沿。",
]

DIALOGUE_LINES = [
    "「这里不安全，跟我走。」",
    "「你还有三十秒可以反悔。」",
    "「我要的不是钱。」",
    "「{who}，你知道自己在跟谁做交易吗。」",
    "「这笔账，今天就得结。」",
    "「让开。我不想再说第二遍。」",
    "「你以为我是一个人来的？」",
    "「{thing}在我手上，条件我来开。」",
    "「三分钟。三分钟后这里会被清场。」",
]

# 各节奏类型的情绪落点（会被 PayoffDensityMeter 的特征探针识别）
PACING_FLAVOR: Dict[str, List[str]] = {
    "BUILD_UP": [
        "{who}被逼到墙角，退无可退。",
        "对方的嘲讽像钝刀子一样割过来。",
        "{who}咬牙忍下这口气，指甲掐进掌心。",
        "屈辱感顺着脊背爬上来，{who}没有作声。",
    ],
    "COGNITIVE_GAP": [
        "对方显然以为自己已经赢了。",
        "{who}没有解释，只是把{thing}又往前推了半寸。",
        "没有人注意到{who}左手一直没离开过口袋。",
        "局面看上去一边倒，但{who}的呼吸始终很稳。",
    ],
    "CATHARSIS_PAYOFF": [
        "{who}反手一击，对方整个人贴着墙滑了下去。",
        "全场寂静。刚才还在叫嚣的人，此刻跪在地上。",
        "那张一直挂着嘲讽的脸，当众裂开了。",
        "{who}一步踏出，刚才围上来的人纷纷让出一条路。",
    ],
    "CLIFFHANGER_HOOK": [
        "巷子深处传来第二串脚步声。",
        "{who}低头看向掌心，那道印记正在发烫。",
        "通讯器里只剩下一片电流声。",
    ],
}

# 章末钩子（HookEnforcer 会对这些做强度评级）
# 章末钩子模板。每一条都必须能被 HookEnforcer 判到 SOLID 以上：
# 要么命中危机/反转/信息炸弹特征，要么以未作答的反问台词收尾。
HOOK_ENDINGS = [
    "一道陌生的身影从雨里缓缓走出。\n刀锋已经抵住了{who}的咽喉。",
    "「原来当年下令的人，一直坐在那张椅子上。」",
    "屏幕上跳出的真名，让{who}僵在原地。\n「这不可能。」",
    "下一刻，整条街的灯同时熄灭。\n黑暗里有人低声问：「你到底是谁？」",
    "{who}忽然明白，那个人根本没有死。",
    "身后传来一声轻笑：「你以为你杀的真是他？」",
    "通讯频道里传来一个本不该存在的声音：「好久不见。」",
    "{thing}的屏幕上只剩一行字：究竟是谁在看着他们。",
    "枪口已经抵在后颈上。\n「别回头。」",
    "所有人的目光同时转向门口。\n门开了，进来的人不该出现在这里。",
]

# 章末悬念的收束句式：把大纲写定的钩子包装成合格的断章
HOOK_WRAPPERS = [
    "{hook}。\n{who}的呼吸停了半拍。\n「你以为这就完了？」",
    "{hook}。\n下一刻，整条街的灯同时熄灭。\n黑暗里有人问：「你到底是谁？」",
    "{hook}。\n身后传来一声轻笑：「原来你一直都知道。」",
    "{hook}——刀锋已经抵住了{who}的咽喉。",
    "{hook}。\n{who}忽然明白，那个人根本没有死。",
    "{hook}。\n{thing}的屏幕上跳出一行字：究竟是谁在看着他们。",
]


@dataclass
class BeatSpec:
    """从真实 Prompt 中解析出的契约要点"""
    chapter_index: int = 1
    beat_index: int = 1
    beat_id: str = ""
    target_words: int = 700
    pacing_type: str = "BUILD_UP"
    cameras: List[str] = field(default_factory=list)
    micro_events: List[str] = field(default_factory=list)
    post_conditions: List[str] = field(default_factory=list)
    prohibitions: List[str] = field(default_factory=list)
    banned_words: List[str] = field(default_factory=list)
    foreshadow_hints: List[str] = field(default_factory=list)
    characters: List[str] = field(default_factory=list)
    is_patch: bool = False
    repair_hints: List[str] = field(default_factory=list)


class PromptParser:
    """从 BeatRenderer / LocalPatcher 生成的 Prompt 中还原契约要点"""

    _BEAT_RE = re.compile(r"节拍编号:\s*(\S+)\s*\(第\s*(\d+)\s*章第\s*(\d+)\s*拍\)")
    _PATCH_RE = re.compile(r"【局部微创打补丁任务 - 节拍\s*(\S+)】")
    _WORDS_RE = re.compile(r"目标字数区间:\s*约\s*(\d+)\s*字")
    _PACING_RE = re.compile(r"叙事节奏:\s*(\w+)")
    _EVENT_RE = re.compile(r"-\s*\[必须推进事件\]:\s*(.+)")
    # 自动分解出的结构模板事件是写作提示，不是要逐字抄进正文的句子
    TEMPLATE_EVENT_MARKERS = ("展示", "声势", "蓄势", "误判", "瞠目", "清点", "破局")
    _CAMERA_RE = re.compile(r"-\s*【([^】]+)】")
    _BAN_RE = re.compile(r"严禁出现\s*([^\n]+)")
    _VIOLATION_RE = re.compile(r"-\s*\[违规项\]:\s*(.+)")
    _PRESENCE_RE = re.compile(r"-\s*([^（(\n]+)(?:（[^）]*）)?\s*$")

    CAMERA_MAP = {
        "第一/第三人称主视点": "POV",
        "微距特写机位": "CLOSE_UP",
        "全景环境机位": "PANORAMIC",
        "围观震惊反应机位": "REACTION_CAM",
    }

    def parse(self, user_prompt: str) -> BeatSpec:
        spec = BeatSpec()

        patch_m = self._PATCH_RE.search(user_prompt)
        if patch_m:
            spec.is_patch = True
            spec.beat_id = patch_m.group(1)
            m = re.match(r"ch0*(\d+)_b0*(\d+)", spec.beat_id)
            if m:
                spec.chapter_index, spec.beat_index = int(m.group(1)), int(m.group(2))
            spec.repair_hints = self._VIOLATION_RE.findall(user_prompt)
            wm = re.search(r"必须仍然满足约\s*(\d+)\s*字", user_prompt)
            if wm:
                spec.target_words = int(wm.group(1))
            # 补丁 Prompt 现在会携带完整契约，必须一并还原，
            # 否则修补会把初稿已达成的合规改没
            spec.micro_events = self._bullets(
                self._section(user_prompt, "【必须保留的微事件（修补后仍要全部存在）】")
            )
            pace_m = re.search(r"【本节拍叙事节奏】(\w+)", user_prompt)
            if pace_m:
                spec.pacing_type = pace_m.group(1)
            hook_m = re.search(r"必须兑现的悬念是「([^」]+)」", user_prompt)
            if hook_m:
                spec.post_conditions.append(hook_m.group(1))
            cam_m = re.search(r"【必须保留的镜头机位】(.+)", user_prompt)
            if cam_m:
                spec.cameras = [c.strip() for c in cam_m.group(1).split("、") if c.strip()]
            pc_m = re.search(r"【在场角色（只有这些人可以说话与行动）】(.+)", user_prompt)
            if pc_m:
                spec.characters = [c.strip() for c in pc_m.group(1).split("、") if c.strip()]
        else:
            bm = self._BEAT_RE.search(user_prompt)
            if bm:
                spec.beat_id = bm.group(1)
                spec.chapter_index = int(bm.group(2))
                spec.beat_index = int(bm.group(3))
            wm = self._WORDS_RE.search(user_prompt)
            if wm:
                spec.target_words = int(wm.group(1))
            pm = self._PACING_RE.search(user_prompt)
            if pm:
                spec.pacing_type = pm.group(1)

        for raw in self._CAMERA_RE.findall(user_prompt):
            mapped = self.CAMERA_MAP.get(raw.strip())
            if mapped and mapped not in spec.cameras:
                spec.cameras.append(mapped)

        spec.micro_events = [e.strip() for e in self._EVENT_RE.findall(user_prompt)]

        # 后置契约段
        post_block = self._section(user_prompt, "【执行后必须达成的后置契约】")
        spec.post_conditions = self._bullets(post_block)

        # 禁令段（含动态疲劳词）
        ban_block = self._section(user_prompt, "【严格禁令事项】")
        for line in self._bullets(ban_block):
            m = self._BAN_RE.search(line)
            if m:
                spec.banned_words.extend(
                    w.strip() for w in re.split(r"[,，、]", m.group(1)) if w.strip()
                )
            else:
                spec.prohibitions.append(line)

        # 长程治理强制指令（伏笔回收/复述等）
        gov_block = self._section(user_prompt, "【本章长程治理强制指令】")
        spec.foreshadow_hints = self._bullets(gov_block)

        # 在场角色名单（Writer Prompt 现在会显式声明）
        if not spec.characters:
            presence_block = self._section(
                user_prompt, "【本节拍在场角色（只有这些人可以说话与行动）】"
            )
            for line in self._bullets(presence_block):
                name = re.split(r"[（(]", line)[0].strip()
                if name and "无具名角色" not in name:
                    spec.characters.append(name)

        return spec

    @staticmethod
    def _section(text: str, header: str) -> str:
        idx = text.find(header)
        if idx < 0:
            return ""
        rest = text[idx + len(header):]
        nxt = rest.find("\n【")
        return rest[:nxt] if nxt > 0 else rest

    @staticmethod
    def _bullets(block: str) -> List[str]:
        out = []
        for line in block.split("\n"):
            line = line.strip()
            if line.startswith("- "):
                cleaned = line[2:].strip()
                if cleaned and cleaned != "无特殊禁令":
                    out.append(cleaned)
        return out


class OfflineDeterministicWriter:
    """
    契约驱动的确定性写手。

    以 (beat_id, 重试轮次) 做随机种子，因此同一节拍的输出稳定可复现，
    而不同章节/节拍之间有足够的素材差异，不会触发跨章雷同告警。
    """

    def __init__(
        self,
        characters: Optional[Sequence[str]] = None,
        things: Optional[Sequence[str]] = None,
        places: Optional[Sequence[str]] = None,
        seed_salt: str = "",
    ):
        self.characters = list(characters) if characters else ["他"]
        self.things = list(things) if things else ["刀"]
        self.places = list(places) if places else ["巷子"]
        self.seed_salt = seed_salt
        self.parser = PromptParser()
        self._attempt_counter: Dict[str, int] = {}

    # ------------------------------------------------------------ 主入口

    def __call__(self, system_prompt: str, user_prompt: str) -> str:
        spec = self.parser.parse(user_prompt)
        key = f"{spec.beat_id}|{spec.is_patch}"
        attempt = self._attempt_counter.get(key, 0)
        self._attempt_counter[key] = attempt + 1

        seed = int(
            hashlib.md5(
                f"{self.seed_salt}|{spec.beat_id}|{spec.beat_index}|{attempt}".encode()
            ).hexdigest()[:8],
            16,
        )
        rng = random.Random(seed)
        return self._compose(spec, rng, attempt)

    # ------------------------------------------------------------ 组装

    def _fill(self, template: str, rng: random.Random,
              cast: Optional[Sequence[str]] = None) -> str:
        pool = list(cast) if cast else self.characters
        return template.format(
            who=rng.choice(pool),
            thing=rng.choice(self.things),
            place=rng.choice(self.places),
        )

    def _compose(self, spec: BeatSpec, rng: random.Random, attempt: int) -> str:
        paragraphs: List[str] = []
        # 严守在场纪律：未列入在场名单的角色不得出现
        cast = spec.characters or self.characters

        # 1. 微事件必须被真实写出（这是契约的核心，不能只擦边）。
        #    但自动分解出的抽象模板事件只是写作提示，逐字抄进正文会让成稿
        #    出现"展示当前困境与外部强敌迫近的声势。"这种非人类句子。
        for ev in spec.micro_events:
            if self._is_template_event(ev):
                paragraphs.append(self._paragraph(rng, PACING_FLAVOR.get(
                    spec.pacing_type, PACING_FLAVOR["BUILD_UP"]), cast, count=2))
            else:
                paragraphs.append(self._event_paragraph(ev, rng, cast))

        # 2. 治理指令：伏笔回收/复述要留下可检出的痕迹
        for hint in spec.foreshadow_hints:
            kw = self._extract_quoted(hint)
            if kw:
                paragraphs.append(
                    f"{rng.choice(cast)}又想起了{kw}，那件事始终没有了结。"
                )

        # 3. 镜头机位全覆盖
        camera_pool = {
            "POV": POV_LINES,
            "CLOSE_UP": CLOSE_UP_LINES,
            "PANORAMIC": PANORAMIC_LINES,
            "REACTION_CAM": REACTION_LINES,
        }
        for cam in (spec.cameras or ["POV", "CLOSE_UP"]):
            lines = camera_pool.get(cam, POV_LINES)
            paragraphs.append(self._paragraph(rng, lines, cast, count=2))

        # 4. 节奏落点：决定本拍的情绪极性
        flavor = PACING_FLAVOR.get(spec.pacing_type, PACING_FLAVOR["BUILD_UP"])
        paragraphs.append(self._paragraph(rng, flavor, cast, count=2))

        # 5. 后置状态必须在正文中兑现
        planned_hook = (
            self._planned_hook(spec) if spec.pacing_type == "CLIFFHANGER_HOOK" else ""
        )
        for cond in spec.post_conditions:
            if cond.strip() == planned_hook:
                continue   # 留到结尾作为钩子兑现，避免中途剧透
            paragraphs.append(self._condition_paragraph(cond, rng, cast))

        # 6. 补足字数：动作 + 对白 + 环境交替，保持移动端段落律动
        filler_pools = [ACTION_LINES, DIALOGUE_LINES, PANORAMIC_LINES, CLOSE_UP_LINES]
        guard = 0
        while self._word_count(paragraphs) < spec.target_words * 0.92 and guard < 200:
            pool = filler_pools[guard % len(filler_pools)]
            paragraphs.append(self._paragraph(rng, pool, cast, count=2))
            guard += 1

        # 7. 钩子收尾：优先兑现大纲写定的章末悬念
        if spec.pacing_type == "CLIFFHANGER_HOOK":
            planned = self._planned_hook(spec)
            if planned:
                wrapper = rng.choice(HOOK_WRAPPERS)
                paragraphs.append(
                    wrapper.format(
                        hook=planned.rstrip("。"),
                        who=rng.choice(cast),
                        thing=rng.choice(self.things),
                    )
                )
            else:
                paragraphs.append(self._fill(rng.choice(HOOK_ENDINGS), rng, cast))

        text = "\n\n".join(paragraphs)

        # 8. 尊重禁令：动态疲劳词与本拍禁忌
        text = self._apply_bans(text, spec, rng)

        # 9. 超出上限时从尾部裁剪（保留钩子）
        text = self._trim_to_budget(text, spec.target_words)
        return text

    # ------------------------------------------------------------ 细节

    MAX_PARA_CHARS = 145   # 排版规则上限 150，留一点余量

    def _paragraph(self, rng: random.Random, pool: List[str],
                   cast: Optional[Sequence[str]] = None, count: int = 2) -> str:
        """单段同时受句数(<=3)与字符数(<=150)约束，符合移动端排版规则"""
        picks = rng.sample(pool, k=min(count, len(pool)))
        out = ""
        for p in picks:
            piece = self._fill(p, rng, cast)
            if len(out) + len(piece) > self.MAX_PARA_CHARS:
                break
            out += piece
        return out or self._fill(picks[0], rng, cast)[: self.MAX_PARA_CHARS]

    def _event_paragraph(self, event: str, rng: random.Random,
                         cast: Optional[Sequence[str]] = None) -> str:
        """
        把微事件写成具体的物理过程。
        直接复述事件描述，保证契约审计能检出痕迹；再补一句动作细节。
        """
        core = event.rstrip("。")
        detail = self._fill(rng.choice(ACTION_LINES), rng, cast)
        para = f"{core}。{detail}"
        # 事件描述本身可能很长，超限时只保留事件句（契约痕迹优先于文采）
        return para if len(para) <= self.MAX_PARA_CHARS else f"{core}。"

    def _condition_paragraph(self, cond: str, rng: random.Random,
                             cast: Optional[Sequence[str]] = None) -> str:
        core = cond.rstrip("。")
        para = f"{core}。{self._fill(rng.choice(CLOSE_UP_LINES), rng, cast)}"
        return para if len(para) <= self.MAX_PARA_CHARS else f"{core}。"

    @staticmethod
    def _is_template_event(description: str) -> bool:
        """判定是否为自动分解产生的抽象模板事件"""
        return sum(
            1 for m in PromptParser.TEMPLATE_EVENT_MARKERS if m in description
        ) >= 1 and "：" not in description and "，" not in description

    @staticmethod
    def _planned_hook(spec: BeatSpec) -> str:
        """大纲写定的章末悬念会被注入最后一拍的后置契约"""
        for cond in spec.post_conditions:
            c = cond.strip()
            if c and len(c) <= 40:
                return c
        return ""

    @staticmethod
    def _extract_quoted(text: str) -> str:
        m = re.search(r"[「『""]([^」』""]{2,40})[」』""]", text)
        return m.group(1) if m else ""

    @staticmethod
    def _word_count(paragraphs: List[str]) -> int:
        return sum(len(re.sub(r"\s+", "", p)) for p in paragraphs)

    def _apply_bans(self, text: str, spec: BeatSpec, rng: random.Random) -> str:
        for w in spec.banned_words:
            if w and w in text:
                text = text.replace(w, "")
        return text

    @staticmethod
    def _trim_to_budget(text: str, target: int, tolerance: float = 0.22) -> str:
        upper = int(target * (1 + tolerance))
        paras = text.split("\n\n")
        while len(re.sub(r"\s+", "", "".join(paras))) > upper and len(paras) > 2:
            # 从倒数第二段删起，保留结尾钩子
            paras.pop(-2)
        return "\n\n".join(paras)


class OfflineWriterProvider(BaseLLMProvider):
    """把离线写手包装成标准 Provider，可走网关与成本审计链路"""

    def __init__(self, writer: Optional[OfflineDeterministicWriter] = None,
                 model_name: str = "offline-deterministic"):
        self.writer = writer or OfflineDeterministicWriter()
        self.model_name = model_name
        self.call_count = 0

    def generate(
        self, system_prompt: str, user_prompt: str,
        temperature: float = 0.7, max_tokens: int = 1500
    ) -> LLMGenerationResult:
        self.call_count += 1
        text = self.writer(system_prompt, user_prompt)
        in_tokens = int((len(system_prompt) + len(user_prompt)) / 1.6)
        return LLMGenerationResult(
            text=text,
            input_tokens=in_tokens,
            cached_input_tokens=int(in_tokens * 0.7),
            output_tokens=int(len(text) / 1.6),
            latency_ms=0.0,
            model_name=self.model_name,
        )
