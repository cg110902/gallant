---
name: novel-factory
description: >-
  Industrial novel factory production workflow in Antigravity. Use when the user asks to
  brainstorm, plan outlines, produce novel chapters, run anti-slop mechanical QC,
  audit token costs, or manage narrative state and Git-like rollbacks.
---

# Novel Factory - Antigravity 工业化小说生产车间

本技能为 Antigravity Agent 提供完整的全题材小说生产流水线操作规程。底层基于本地 SQLite 时序实体图谱 (BEC-Graph)、ACL 2023 DOC 细粒度规划控制器、机械化 Anti-Slop 质检器与 Git 级 Narrative VCS。

---

## 1. 快速巡检与工作区状态查看

在进行任何创作或大纲修改前，首先检查当前工程状态：

```bash
.venv/Scripts/python.exe src/novel_factory/cli.py run-demo
```
或者查询当前分支 HEAD 状态与数据库实体总览。

---

## 2. 核心生产操作流程 (Step-by-Step SOP)

### 步骤一：审阅项目挂载配置 (`project.yaml`)
检查或修改根目录下的 `project.yaml`：
* `genre`: 挂载题材包（如 `configs/genres/cyberpunk_scifi.yaml` 或 `suspense_mystery.yaml`）
* `pacing`: 挂载节奏心跳模型（如 `configs/pacing/webnovel_high_octane.yaml`）
* `qc_pipeline`: 确认启用的规则包（`configs/rules/anti_slop.yaml`）

### 步骤二：调度总导演制订节拍契约 (`novel_director`)
调用专职导演子智能体 `novel_director`：
1. 传入当前章节目标与上下文；
2. 拆解为 3~4 个 600~800 字的 `BeatContract`；
3. 严格声明每个节拍的前置条件、后置状态转移与必须推进的微事件清单（Micro-Events）；
4. 检查套路冷却状态（`TropeCooldownTracker`），若近期已触发过同类套路，强制采纳反转建议。

### 步骤三：调度主笔作家渲染正文 (`novel_writer`)
调用主笔子智能体 `novel_writer`：
1. 传入 `CodexAssembler` 编译出的高纯度时序上下文（控制在 3500 Token 内）；
2. 严格按机位调度与短句律动渲染正文；
3. 事件完成即收笔，严禁说教与空洞注水。

### 步骤四：执行双轨质检与局部微创打补丁 (QC & Local Patch)
1. **机械硬规则检查 (Mechanical Lint)**：
   * 运行质检扫描，确保 0 违规、得分 $\ge 85$；
   * 自动拦截一切“这让他深深明白……”等段尾说教。
2. **局部 Patch 修补**：
   * 若某节拍不合格，**绝对不要推倒整章重写**！
   * 调用 `LocalPatcher` 针对缺陷节拍下发差分修复指令，原位打补丁，其余段落 100% 保持不变。

### 步骤五：原子提交与图谱同步推进 (Narrative VCS)
合格后执行原子提交：
1. 生成唯一 SHA-256 提交节点；
2. 将本章引起的实体变动增量（`StateDelta`）同步写入本地 SQLite 图谱；
3. 如遇主线跑偏或战力失控，随时执行 `repo.checkout_chapter(N)` 一键时空回滚并开辟新分支。

---

## 3. 稿件全渠道导出规程

生产完毕后，调用导出器导出成品：
```python
from src.novel_factory.export import ManuscriptExporter
from src.novel_factory.vcs import NarrativeRepository

repo = NarrativeRepository(db_path="novel_master.db")
exporter = ManuscriptExporter(repo)

# 1. 导出番茄/起点两格缩进标准投稿 TXT
exporter.export_to_txt("dist/manuscript_submission.txt")

# 2. 导出带目录的完整 Markdown
exporter.export_to_markdown("dist/full_book.md", book_title="作品书名")

# 3. 导出模型微调 SFT 训练集 (JSONL)
exporter.export_to_jsonl_dataset("dist/sft_dataset.jsonl")
```
