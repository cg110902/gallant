# Novel Factory · 工业化长篇小说生产流水线

配置驱动的中文长篇小说自动化生产系统。以 **BEC 时序实体图谱 + 事件溯源 + Git 式剧情版本库**
为状态底座，以 **契约化节拍生产 + 多闸门质检 + 长程治理引擎** 为质量保障，
目标是让百万字级别的连载在数百章之后仍然不崩。

> 本项目的核心主张：**长篇小说的失败几乎从不是单章文笔问题，而是跨越数百章的状态漂移。**
> 因此系统的重心不在"生成"，而在"约束"。

---

## 为什么需要这么多闸门

一个没有约束的生成流水线，会心安理得地输出下面这种东西并标记为「质检通过」：

```
契约要求 1200 字，实际交付 17 字 —— 通过 ✓
三章正文一字不差             —— 通过 ✓
出场角色根本不存在于世界图谱   —— 通过 ✓
```

本系统的每一道闸门，都对应一类真实发生过的生产事故。

---

## 架构总览

```
                    ┌─────────────── project.yaml（声明式挂载）───────────────┐
                    │  题材包 · 节奏模型 · 质检规则包 · 模型路由 · 预算上限      │
                    └────────────────────────┬──────────────────────────────┘
                                             ▼
  ┌────────────┐   契约    ┌────────────┐   正文   ┌──────────────────────────┐
  │ DOC 大纲   │─────────▶│ 节拍渲染器  │────────▶│        四道质检闸门        │
  │ 控制器     │          │ + 局部补丁  │◀────────│ 契约履约/机械文本/         │
  └────────────┘   返工    └────────────┘  修复指令 │ 因果不变量/过审风控        │
        ▲                                          └────────────┬─────────────┘
        │ 强制指令                                              ▼ 通过
        │                                          ┌──────────────────────────┐
  ┌─────┴──────────────────────────┐               │   章级放行闸门            │
  │      长程治理引擎（八件套）      │◀──────────────│ 跨章雷同 · 长程治理        │
  │ 伏笔台账 · 故事日历 · 人设指纹   │    审计回流    └────────────┬─────────────┘
  │ 命名冲突 · 章末钩子 · 爽点密度   │                            ▼ 原子提交
  │ 升级节奏 · 多线调度             │               ┌──────────────────────────┐
  └────────────────────────────────┘               │ Narrative VCS (Git-DAG)  │
                                                   │ BEC 图谱 · 事件溯源       │
                                                   └──────────────────────────┘
```

---

## 快速开始

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e .

novel-factory demo                    # 黄金三章端到端试产 + 时空回滚演示
```

### 批量生产（支持断点续产）

```bash
# 离线 mock 跑通链路
novel-factory produce --start 1 --end 20

# 接真实模型
export GEMINI_API_KEY=...
novel-factory produce --provider gemini --model gemini-3.8-flash --start 1 --end 100
```

进程被杀 / 限流 / 预算熔断之后，**用完全相同的命令再跑一次即可从断点继续**，
已完成章节不会重复烧钱。

### 全部命令

| 命令 | 作用 |
|---|---|
| `demo` | 黄金三章端到端试产演示与时空回滚验证 |
| `produce` | 批量自动化生产章节，带重试、退避与断点续产 |
| `status` | 项目配置、战力标尺、提交树与实体花名册 |
| `rollback` | 一键时空回滚与剧情分支管理 |
| `export` | 导出投稿 TXT / 全书 Markdown / SFT 数据集 / 世界观设定集 |
| `inspect` | 章节质检指标、SimHash 指纹与高频词疲劳矩阵 |
| `govern` | 长程治理巡检：伏笔台账、爽点曲线、钩子趋势、命名冲突、多线甘特图 |
| `resume` | 查看与操作断点续产日志，支持重置单章重跑 |

---

## 四道生产闸门

节拍级质检，任意一道不过即触发**局部微创打补丁**（绝不重写整章）：

| 闸门 | 检查内容 | 典型拦截 |
|---|---|---|
| **契约履约** (`BeatContractAuditor`) | 字数 SLA、微事件推进、镜头机位覆盖、绝对禁忌、后置状态、在场纪律 | 契约 1200 字只交付 17 字；必达事件没写；未在场角色冒出台词 |
| **机械文本** (`MechanicalLinter`) | 段尾说教、禁用套话、移动端段落律动、题材陈词 | 「这让他深深明白……」被 AST 剪枝直接剁掉 |
| **因果不变量** (`InvariantChecker`) | 存活性、道具持有与排他、空间共存、DAG 前置 | 死者行动；未注册的幽灵角色出场；无中生有的道具 |
| **过审风控** (`ComplianceScanner`) | 分级敏感词、变形绕写归一化 | 政治红线、涉未成年人内容、可操作性犯罪教程 |

章级放行还会额外检查**跨章语义雷同**与**长程治理**结论。

> 微事件推进采用**三档置信度**判定：高置信视为已推进，低置信判致命违约，
> 中间的灰色地带降级为提示并移交 LLM 语义裁判——机械匹配不该假装自己能理解语义。

---

## 长程治理引擎

这是让长篇"活过三百章"的部分。所有引擎**既在生产前下发强制指令（预防），
也在生产后做审计（拦截）**——只审计不预防等于永远在返工。

### 一致性层

| 引擎 | 解决的问题 |
|---|---|
| `ForeshadowLedger` 伏笔台账 | 埋了忘收 / 收了没埋 / 收得太晚。按量级自动推导回收窗口与记忆保鲜期 |
| `StoryCalendar` 故事日历 | 把「三日后」「一炷香」编译为绝对分钟数，检测时序倒流、伤愈过快、约定逾期 |
| `PersonaRegistry` 人设指纹 | 称谓错乱、口癖蒸发、语体漂移、自称漂移、信息穿越 |
| `NameCollisionDetector` 命名冲突 | 重名、形近、音近、姓氏过载；支持新角色取名准入校验 |

### 商业性层

| 引擎 | 解决的问题 |
|---|---|
| `HookEnforcer` 章末钩子 | 识别钩子类型并评级（DEAD/WEAK/SOLID/STRONG），检测收束性与说教式结尾 |
| `PayoffDensityMeter` 爽点密度 | 「憋太久」与「爽麻了」双向预警，输出下一章情绪建议与 ASCII 曲线 |
| `PowerCurveGuard` 升级节奏 | 战力暴涨、境界通胀、"再无对手"的张力归零 |
| `ThreadScheduler` 多线调度 | 支线断更预警、主线占比失衡、卷末收束倒计时、甘特图 |

```bash
novel-factory govern --window 30    # 一次性巡检以上全部维度
```

---

## 配置驱动

一切题材、战力、文风、质检、模型均通过 YAML 声明式挂载，代码零硬编码业务规则。

```yaml
# project.yaml
genre:
  config_path: "configs/genres/cyberpunk_scifi.yaml"   # 或 xianxia / suspense / space_opera ...
pacing:
  config_path: "configs/pacing/webnovel_high_octane.yaml"  # 或 classic_three_act
qc_pipeline:
  rule_packs:
    - "configs/rules/anti_slop.yaml"
    - "configs/rules/formatting.yaml"
```

- `configs/genres/` — 6 个题材包（赛博朋克 / 仙侠 / 悬疑 / 太空歌剧 / 历史 / 都市异能）
- `configs/pacing/` — 网文高燃模型、经典三幕剧
- `configs/rules/` — 反 AI 味、排版、重复度、过审风控词库

---

## 编程接口

```python
from src.novel_factory.orchestrator import NovelFactoryOrchestrator

orch = NovelFactoryOrchestrator.from_provider(
    provider_type="gemini", model_name="gemini-3.8-flash",
    config_path="project.yaml", db_path="novel_master.db",
)

# 统一注册入口：同时写入 BEC 图谱与事件溯源库
orch.register_entity("char_zero", "CHARACTER", "零号", created_chapter=1)

# 生产前收集长程强制指令（伏笔回收 / 爽点调度 / 支线续更）
directives = orch.collect_governance_directives(chapter_index=12)

result = orch.produce_chapter(
    chapter_index=12, title="第十二章", beat_contracts=beats,
    lore_entries=[], state_delta=delta,
)

print(result.qc_passed, result.blockers)
print(result.governance.format_summary())
```

---

## 测试与压测

```bash
pytest -q                                              # 234 项单元与集成测试

python scripts/stress_test.py --chapters 100 --crash-at 60
```

压测覆盖真实长跑场景：内存与 SQLite 线性度、断点崩溃恢复精确性、
长程引擎在百章跨度上的信号有效性、单章成本与耗时外推。

测试套件中的 `tests/test_qc_gate_integration.py` 是**回归安全网**——
它断言的全部是「必须失败」的场景。任何人放宽闸门，这些测试会立刻变红。

---

## 项目结构

```
src/novel_factory/
├── orchestrator.py          # 全链路总编排（生产 + 治理）
├── schemas/                 # 节拍契约、实体、提交等数据契约
├── config/                  # 声明式配置加载与校验
├── controller/              # DOC 四级雪花大纲控制器
├── codex/                   # 上下文装配、递归检索、进展引擎、套路冷却
├── pipeline/                # 节拍渲染、局部补丁、流式退化监控
├── qc/                      # 契约审计、机械 Lint、SimHash、重复度、风控、裁判
├── graph/                   # BEC 时序图谱、因果 DAG、不变量检查
├── core/                    # 事件溯源与世界快照
├── consistency/             # 长程一致性层（伏笔/时间/人设/命名）
├── commerce/                # 商业性层（钩子/爽点/升级/多线）
├── runtime/                 # 断点续产运行时
├── vcs/                     # Git 式剧情版本库
├── llm/                     # 多模型网关、Gemini 深度适配、成本审计
├── export/                  # 手稿与 SFT 数据集导出
└── cli/                     # 终端总控台与 HITL 工作台
```

---

## 已知边界

诚实地说明当前做不到的事：

- **语义判定依赖 LLM 裁判**：微事件推进、逻辑断裂、OOC 的最终判定无法纯机械完成，
  灰色地带交由 `novel_judge` 复核，裁判本身的准确率决定上限。
- **敏感词库是骨架**：`configs/rules/compliance.yaml` 为工程示例，
  正式投产前须按目标平台最新审核细则扩充。
- **命名音近检测无拼音依赖**：使用手工维护的易混字组，覆盖常见情况但非完备。
- **真实 API 链路未做规模验证**：`from_provider` 已打通并回传真实 token 用量，
  但百章级真实调用的稳定性与成本需在有 Key 的环境下实测。
