---
name: novel-factory
description: >-
  Industrial novel factory production workflow in Antigravity. Use when the user asks to
  brainstorm, plan outlines, produce novel chapters, run anti-slop mechanical QC,
  audit token costs, manage narrative state, run long-range consistency governance
  (foreshadowing / timeline / persona / naming), check commercial viability
  (chapter hooks / payoff density / power curve / thread scheduling),
  resume an interrupted production run, or export manuscripts.
---

# Novel Factory · Antigravity 工业化小说生产车间

全题材长篇小说生产流水线操作规程。底层为 SQLite 时序实体图谱 (BEC-Graph)、
事件溯源、ACL 2023 DOC 细粒度规划控制器、四道质检闸门、八大长程治理引擎
与 Git 级 Narrative VCS。

---

## 0. 心智模型（先读这一段）

**长篇小说的失败几乎从不是单章文笔问题，而是跨越数百章的状态漂移。**

因此本车间的重心不是"生成"，而是"约束"。每一次生产循环都是：

```
收集长程强制指令  →  按契约生成  →  四道闸门校验  →  局部补丁  →  章级放行  →  原子提交
   （预防）                            （拦截）        （修复）      （治理）      （固化）
```

只做拦截不做预防，等于永远在返工烧钱。

---

## 1. 快速巡检

```bash
novel-factory status          # 项目配置、战力标尺、提交树、实体花名册
novel-factory govern          # 长程治理全维度巡检
novel-factory resume          # 查看断点续产日志
```

---

## 2. 核心生产 SOP

### 步骤一：审阅挂载配置 (`project.yaml`)

- `genre` — 题材包（赛博朋克 / 仙侠 / 悬疑 / 太空歌剧 / 历史 / 都市异能）
- `pacing` — 节奏模型（`webnovel_high_octane` 高燃网文 / `classic_three_act` 三幕剧）
- `qc_pipeline` — 启用的规则包

### 步骤二：收集长程强制指令（**不可跳过**）

```python
directives = orchestrator.collect_governance_directives(
    chapter_index=N, present_entities=[...]
)
```

返回内容会被自动注入 Writer Prompt，包含：
- 本章**必须回收**哪些超期伏笔、**必须复述**哪些即将被读者遗忘的伏笔；
- 当前该**继续压制蓄力**还是**必须给一次爆发兑现**；
- 哪条支线已**断更超限**，本章必须带一笔。

### 步骤三：调度总导演制订节拍契约 (`novel_director`)

拆解为 3~4 个 `BeatContract`。硬性要求：
1. `characters_present` 必须是图谱中**已注册且存活**的 entity_id；
2. `target_words` 总和 = 本章目标字数（这是交付 SLA，不是建议）；
3. `micro_events` 必须是**物理事件**（"把解码器插入接口，指示灯转绿"），
   不能是抽象概括（"意识到了危险"）；
4. 新角色取名必须过 `name_detector.check_new_name()` 准入校验；
5. 最后一拍应为 `CLIFFHANGER_HOOK`，并在 `post_conditions` 声明留何悬念。

### 步骤四：调度主笔渲染正文 (`novel_writer`)

只写当前这一拍。Prompt 中已自动携带：
Codex 时序上下文、人设声纹约束、称谓关系约束、故事内时间锚点、
跨章高频疲劳词动态禁令、长程治理强制指令。

### 步骤五：四道闸门与局部微创补丁

```
契约履约 ∧ 机械文本 ∧ 因果不变量 ∧ 过审风控  =  节拍放行
```

任意一道不过 → `LocalPatcher` 下发**定向差分修复指令**，原位打补丁，
其余段落 100% 保持不变。**绝对不要推倒整章重写。**

补丁 Prompt 同样携带人设与时间约束——否则修补过程本身会重新引入 OOC。

### 步骤六：章级放行与原子提交

章级额外检查：跨章语义雷同（自适应基线）、长程治理结论、全章风控。
通过后生成 SHA-256 提交节点，`StateDelta` 同步写入图谱与事件库。

---

## 3. 长期生产：必须用断点续产

多章批量生产**永远不要写裸循环**：

```python
from src.novel_factory.runtime.resume import ResumableProducer

producer = ResumableProducer(orchestrator, journal_path="run.json")
summary = producer.run(range(1, 201), plan_provider=my_plan_fn)
```

或直接用 CLI：

```bash
novel-factory produce --start 1 --end 200 --provider gemini
# 崩溃后用完全相同的命令再跑一次即可从断点继续
novel-factory resume --reset 87    # 人工处理后重置某章重跑
```

能力保障：JSON 日志落盘、精确恢复、指数退避重试、财务熔断时**挂起等待人工决策**。
生产路径上所有事件写入均幂等，重跑同一章不会崩。

---

## 4. 长程治理巡检

```bash
novel-factory govern --window 30
```

| 维度 | 看什么 |
|---|---|
| 章末钩子 | 近 N 章平均强度、连续弱钩子streak（追读率杀手） |
| 爽点密度 | 连续憋屈章数、距上次爆发章数、ASCII 情绪曲线 |
| 伏笔台账 | 未回收 / 超期违约 / 记忆过期待复述 |
| 命名冲突 | 重名、形近、音近、姓氏过载 |
| 多线调度 | 断更支线、主线占比、收束倒计时、甘特图 |
| 升级节奏 | 战力暴涨、境界通胀、威胁比归零 |

---

## 5. 时空回滚

主线跑偏或战力失控时：

```bash
novel-factory rollback --chapter 87 --branch fix/power-scale
```

BEC 图谱、事件溯源与进展引擎会同步回退到该章末尾状态。

---

## 6. 全渠道导出

```bash
novel-factory export --format all --output dist/
```

产出：
- `manuscript_submission.txt` — 番茄/起点投稿标准（两格全角缩进）
- `full_book.md` — 含 YAML frontmatter 与目录导航
- `sft_dataset.jsonl` — ShareGPT 格式微调数据集（数据飞轮）
- `world_bible.md` — 世界观设定集

---

## 7. 禁止事项

- 禁止为了让测试通过而放宽任何闸门；
- 禁止在 Python 中硬编码题材、战力、节奏或禁语规则（一律进 `configs/` YAML）；
- 禁止绕过 `ResumableProducer` 做多章生产；
- 禁止只在图谱注册实体而不同步事件库（用 `orchestrator.register_entity()`）。
