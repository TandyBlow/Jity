# 01 线：短场景事实监督（第一批）

状态：**first batch ready**。17 行人手写的 60–160 字短场景，已提交到本线分支，可直接消费。材料提交：`ba0edc858fd15d3d3b894f6163447b93a2e6e6fd`。

这不是模型、不是候选权重、不是自动评测报告，也不替代训练脚本或最终验收。它是给叙事训练/浏览器路线用的**正文监督**：输入是已经结算的世界变化，正文要像小说，但关键事实一个不漏、输入没有的东西一个不加。

## 交付物

| 路径 | 内容 |
|---|---|
| `experiments/narration-quality/corpus-short/rows.jsonl` | 17 行主材料：完整 `input`、`targetText`、检查元数据 |
| `experiments/narration-quality/corpus-short/index.json` | 批次索引、来源、世界族/类别/长度统计 |
| `experiments/narration-quality/corpus-short/review.md` | 逐行人工阅读记录（变化落实、边界、字数） |
| `experiments/narration-quality/corpus-short/check_corpus.py` | 结构检查：冻结输入原样、train-only、长度/字段 |
| `experiments/narration-quality/corpus-short/README.md` | 字段说明与消费方式 |
| `results/quality/team-01-input.json` | 共享交接：指向实际 jsonl，含首批正文、可消费字段、限制 |

## 来源与隔离

- 输入来自旧数据集 `narration-dataset-v1` 的 `rows-xy.jsonl`，源提交 `1ab6ca791f97529a7bffed1f4837bf81a28badcb`。
- 只用 **train**（17 行全部 train）。没有用 dev/test；旧 199 行和 `splits/v1.json` 未修改。
- `input` 是旧行 `x` 的原样拷贝；每行有 `sourceInputSha256`，检查脚本会重算。
- 旧长 `y` 只做文风参考，不做事实来源。已发现长 `y` 与 `本回合变化` 不一致的行（`row-0182`、`row-0199`），正文按变化写，不按长 `y` 搬事件。
- 没有新造世界；`worldFamily` 只是旧图书馆世界的馆内区域分组。

## 一行结构

```json
{
  "id": "short-0050-backdoor-lock",
  "sourceRowId": "row-0050",
  "sourceEvidence": {"dataset": "...", "sourceCommit": "...", "rowId": "row-0050", "split": "train"},
  "sourceSplit": "train",
  "sourceInputSha256": "...",
  "worldFamily": "library-lending",
  "categories": ["item_change", "task_complete"],
  "sequenceId": null,
  "turnIndex": null,
  "input": { "...旧 x 原样..." },
  "targetText": "「锁的事，我查清了。」……",
  "targetChars": 76,
  "requiredFacts": [
    {"kind": "time_advance", "text": "10 分钟"},
    {"kind": "appearance_removed", "entity": "秦既白", "text": "袖口沾了机油"},
    {"kind": "task_completed", "entity": "顾望舒", "task": "查清九八年秋天为什么换后门的锁"}
  ],
  "licensedDetails": ["..."],
  "knowledgeBoundary": {"viewpoint": "顾望舒", "canKnow": ["..."], "mustNotReveal": ["..."]},
  "forbiddenInventions": ["..."],
  "styleReferenceIds": ["row-0050", "row-0100"],
  "notes": "..."
}
```

**模型输入只放 `input`，训练目标只放 `targetText`。** `requiredFacts`/`licensedDetails`/`knowledgeBoundary`/`forbiddenInventions`/`styleReferenceIds` 是检查元数据，不能拼进 prompt，也不能当参考答案喂给模型。

## 第一批覆盖

17 行，正文 76–106 字（要求 60–160）。

| 类型 | 行数 | 具体 |
|---|---:|---|
| 无变化 | 1 | `row-0008` 装订间 20 分钟无变化 |
| 移动/两人分开 | 3 | `row-0100` 两人交换位置；`row-0182` 柏清和进长桌区、温暮留走廊；`row-0199` 叶暮下楼梯间、方既白留天台 |
| 物品/地点变化 | 7 | 杯水干、报夹换铜夹、绳头重编、除湿机重启、灯全亮、报刊库返潮等 |
| 任务完成/新增 | 6 | 换锁查清、火灾查清、两项闭馆通告查清、封面来路查清；新增送签字、问第三个名字 |
| 精神/情绪变化 | 6 | 小升、下降、微降、上升、大跌 |
| 个性/秘密说出一层 | 1 | `row-0055` 秦书言说母亲当班、韩望舒说父亲当班 |

世界族：`library-news` 7、`library-basement` 3、`library-lending` 2、`library-utilities` 2、`library-courtyard` 2、`library-upper-corridor` 1。

## 给 10：怎么直接消费

- 把 `input` + `targetText` 作为 **`yShort`** 样本；正文是 76–106 字，不是 20–60 字的单事实 beat。
- 如果 `qwen25-beat-v1` 需要 beat：从 `requiredFacts` 拆，但 beat 文本要另写；不要机械切 `targetText`。
- `styleReferenceIds` 指向旧长文；只借节奏、对白密度、人物反应，不搬事件。
- 本批全部 train；不会把 dev/test 输入带进训练。旧 199 行/划分不动。
- 本批没有连续回合；`sequenceId`/`turnIndex` 为 `null`，不要当连续序列。
- 首批已就绪，可直接读 `rows.jsonl`；下一批按真实失败类型/世界族补。

## 给 02：怎么当参照

- 这是“事实不漏、边界不越、读起来像正文”的短参照，不是候选输出，也不是逐字模板。
- 对照 `requiredFacts` 看关键动作/结果；对照 `knowledgeBoundary`/`forbiddenInventions` 看有没有替角色说出不知道的秘密、有没有补重大往事/线索。
- 改述可以，事实和边界不能破；`targetText` 只是一种实现，不是必须逐字复现。
- 真实生成失败时，把输入、生成文本和错误类型（漏事实/捏造/指代/文风）交给 01，下一批按同类补；不要用规则模板替换失败样本然后宣称达标。

## 人工检查证据

每行完整读过 `input`（视角、上回合状态、本回合变化、本回合状态）和正文，并在 `review.md` 留了逐行记录。重点检查：

1. 关键动作/结果是否漏（移动的起终点、任务完成、物品新状态、精神值方向）。
2. 是否新增命名角色、物品、线索、往事、承诺。
3. 是否替视角人物说出 `knowledgeBoundary.mustNotReveal` 里的秘密。
4. 是否把长 `y` 的事实错误搬进来；`row-0182`/`row-0199` 是明确的反例。
5. 字数、单段、无占位符。

结构检查命令：

```bash
python -X utf8 experiments/narration-quality/corpus-short/check_corpus.py
```

当前输出：17 行；长度 76–106；冻结输入逐行一致；全部 train；通过。语义检查是人工的，脚本不替代。

## 已知限制

- 没有 GPU 生成/训练；正文是人手写的监督材料。
- 没有自动语义评分；`requiredFacts` 是清单，不是完整逻辑。
- 只有 17 行，且只覆盖旧馆内世界/train；不是全人物、全地点、全类别平衡采样。
- 长度集中在 76–106；60–80 和 120–160 两端覆盖不足。
- 少量空间具体化（杯口朝向、门虚掩、风）是有依据的细微细节，不是已结算事实；如果训练侧要求更严，可逐行删。
- 旧长 `y` 有事实错误，未作为事实来源；本批不修改旧数据，也不重新划分。
- 没有独立终验材料；这是开发监督，不是最终验收集。

## 下一批

按 02/10 的真实遗漏、捏造、指代和文风问题补，优先：

1. 60–80 字的单事实短场景；
2. 120–160 字但只含 2–3 个事实的场景；
3. 同一世界族的连续两回合（01 只做短场景，完整场景/连续回合仍归 05）；
4. 真实模型最容易错的“两人分开/任务完成但不说答案/秘密只说出一层”。

继续只用 train 或另立有来源的开发世界材料；不碰 dev/test，不改旧 199 行。
