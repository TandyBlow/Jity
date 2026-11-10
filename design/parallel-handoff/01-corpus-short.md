# 01 线：短场景事实监督（第一至三批）

状态：**batch 3 ready**。39 行人手写的 60–138 字短场景，已提交到本线分支，可直接消费。材料提交：`f98c096be957373faacf9a95f0d12782ab69f0a8`。

这不是模型、不是候选权重、不是自动评测报告，也不替代训练脚本或最终验收。它是给叙事训练/浏览器路线用的**正文监督**：输入是已经结算的世界变化，正文要像小说，但关键事实一个不漏、输入没有的东西一个不加。

## 交付物

| 路径 | 内容 |
|---|---|
| `experiments/narration-quality/corpus-short/rows.jsonl` | 39 行主材料：完整 `input`、`targetText`、检查元数据 |
| `experiments/narration-quality/corpus-short/rows-authored.jsonl` | 14 行产品世界行，单独一份便于核对 |
| `experiments/narration-quality/corpus-short/authored/` | 产品世界的 14 个场景定义与生成脚本（世界文件初始快照 + 一个 authored 变化） |
| `experiments/narration-quality/corpus-short/long/` | 3 行 120–160 字长正文的定义与写回脚本（冻结 `x` 原样） |
| `experiments/narration-quality/corpus-short/index.json` | 批次索引、来源、行类型、世界族/类别/长度统计 |
| `experiments/narration-quality/corpus-short/review.md` | 逐行人工阅读记录（变化落实、边界、字数） |
| `experiments/narration-quality/corpus-short/check_corpus.py` | 结构检查：冻结输入原样、authored 来源/SHA、authored 变化与结果状态一致、train-only、长度/字段 |
| `experiments/narration-quality/corpus-short/README.md` | 字段说明与消费方式 |
| `results/quality/team-01-input.json` | 共享交接：指向实际 jsonl，含正文、可消费字段、限制 |

## 来源与隔离

- 25 行旧材料来自 `narration-dataset-v1` 的 `rows-xy.jsonl`，源提交 `1ab6ca791f97529a7bffed1f4837bf81a28badcb`：21 行原样短场景 + 3 行另外选行（`row-0117`/`0132`/`0183`）的 120–137 字长正文 + 1 行时间派生。
- 只用 **train**。没有用 dev/test；旧 199 行和 `splits/v1.json` 未修改。
- `input` 是旧行 `x` 的原样拷贝；每行有 `sourceInputSha256`，检查脚本会重算。3 行长正文只是给另外三行冻结 `x` 写更长的目标，输入没有改。
- 14 行产品材料来自 `frontend/public/worlds/dragon-raja-free-day.world.json` 的初始快照，源提交 `865ae64e0901a70c3db4f1d0eb2af60268943c53`，世界文件 SHA-256 `0a8b63be…`。每行只落一个 authored 的本回合变化；不是浏览器会话，不声称前几回合发生过。人物、地点、物品、任务全部来自该世界文件。
- 旧长 `y` 只做文风参考，不做事实来源。已发现长 `y` 与 `本回合变化` 不一致的行（`row-0182`、`row-0199`），正文按变化写，不按长 `y` 搬事件。
- **1 行派生对照**：`short-0008-two-minute-no-change` 以 `row-0008` 为底，只把 `本回合变化.时间推进` 从 20 分钟改成 2 分钟，其余输入和状态不变；`sourceEvidence.derived=true`、`baseRowId=row-0008`，并写明 derivation。它只训练“两分钟过去、没有新事件”，不是旧 199 行中的冻结行；检查脚本会验证相对底行只改了时间。

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

## 覆盖

39 行，正文 60–138 字（15 行 60–79、16 行 80–119、8 行 120–160）。其中 4 行（`row-0138`/`row-0161`/`row-0175`/`row-0178`）是只写已结算地点/外貌、不写事件的 strict 场景，对应 02 `req-02-02` 的“只实现已结算变化加至多一个许可外貌细节”；1 行 2 分钟无变化对照，来自 09 真实运行里 `elapsed-two-minutes` 仍让模型开盒子的失败。

一行可能覆盖多类，所以下表行数合计大于 39。

| 类型 | 行数 | 具体 |
|---|---:|---|
| 无变化 | 3 | `row-0008` 装订间 20 分钟；`short-0008-two-minute-no-change` 同状态 2 分钟；`dr-0001` 服务巷 2 分钟 |
| 移动/两人分开 | 8 | 旧 `row-0100`/`row-0182`/`row-0199`；产品 `dr-0002` 诺诺进棚、`dr-0007` 路明非进棚、`dr-0010` 担架从笼内到棚、`dr-0011` 苏茜过桥上二层、`dr-0014` 凯撒进庭院 |
| 物品变化 | 9 | 旧杯水干、报夹换铜夹、绳头重编、除湿机重启、合订本封面/扉页；产品护目镜、挂锁、担架、演习枪 |
| 地点变化 | 6 | 灯全亮、报刊库返潮、空出三个位置、吊兰黄叶、窗开一条缝 |
| 外貌变化 | 5 | 旧苏既明换金属细框眼镜、江既白手指沾黑、苏既明手指沾灰；产品芬格尔油印/护膝、护目镜 |
| 任务完成/新增 | 11+4 | 旧换锁/火灾/闭馆通告/封面来路/缺页数/封面翻正；产品护目镜、报告小桥、备床、换弹匣、新增问门闩 |
| 精神/情绪变化 | 9 | 旧七行；产品 `dr-0006` 无数字下降、`dr-0009` 数字变体 |
| 个性/秘密说出一层 | 3 | 旧 `row-0055` 两层班次、`row-0183` 新个性；产品 `dr-0005` 诺诺先护人再探头 |

世界族：`dragon-raja-free-day` 14、`library-news` 13、`library-basement` 4、`library-utilities` 3、`library-lending` 2、`library-courtyard` 2、`library-upper-corridor` 1。

## 给 10：怎么直接消费

- 把 `input` + `targetText` 作为 **`yShort`** 样本；正文是 60–138 字，不是 20–60 字的单事实 beat。
- 产品 14 行（`dr-*`）是卡塞尔学院自由一日世界，可直接补产品实体；不要再只学旧图书馆的映射。
- 8 行 120–160 字可直接用于“更长但仍只含 2–3 个事实”的目标；不要用它们去凑密集多事实。
- 如果 `qwen25-beat-v1` 需要 beat：从 `requiredFacts` 拆，但 beat 文本要另写；不要机械切 `targetText`。
- `styleReferenceIds` 指向旧长文；只借节奏、对白密度、人物反应，不搬事件。
- 本批全部 train；不会把 dev/test 输入带进训练。旧 199 行/划分不动。
- 本批没有连续回合；`sequenceId`/`turnIndex` 为 `null`，不要当连续序列。
- `dr-0009` 是显式数字变体（`variant="sanity-literal"`）；如果训练侧不需要数字，单独丢掉，不要和 `dr-0006` 当两个事件。

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

当前输出：39 行；长度 60–138（15 行 60–79、16 行 80–119、8 行 120–160）；25 行旧材料（21 行冻结输入逐行一致 + 3 行同冻结输入的长正文 + 1 行派生对照只改时间）+ 14 行产品世界 authored；全部标 train；世界文件 SHA、行哈希、authored 变化与结果状态一致性通过。语义检查是人工的，脚本不替代。

## 已知限制

- 没有 GPU 生成/训练；正文是人手写的监督材料。
- 没有自动语义评分；`requiredFacts` 是清单，不是完整逻辑。
- 39 行，旧馆 25 行 + 产品世界 14 行；产品行只来自一个初始快照，不是全人物、全地点、全类别平衡采样。
- 长度已补到 60–138，但 140–160 字的上端只有 1 行，且长场景都是两三个事实，不是密集多事实。
- 少量空间具体化（杯口朝向、门虚掩、风）是有依据的细微细节，不是已结算事实；如果训练侧要求更严，可逐行删。
- 旧长 `y` 有事实错误，未作为事实来源；本批不修改旧数据，也不重新划分。
- 产品行是 authored 开发材料，不是浏览器记录；`dr-0009` 是数字对齐变体，不是主正文。
- `short-long-*` 长正文是同一冻结 `x` 的第二个实现，不改变旧行；不要把它当成旧数据的修正版。
- 没有独立终验材料；这是开发监督，不是最终验收集。

## 下一批

按 02/10 的真实遗漏、捏造、指代和文风问题补，优先：

1. 60–80 字的单事实短场景；
2. 140–160 字、仍只含 2–3 个事实的场景；
3. 同一世界族的连续两回合（01 只做短场景，完整场景/连续回合仍归 05）；
4. 真实模型最容易错的“两人分开/任务完成但不说答案/秘密只说出一层”；
5. 10 明确要的 120 行目标：本批 39 行，剩余按真实失败补，不虚报数量。

继续只用 train 或另立有来源的开发世界材料；不碰 dev/test，不改旧 199 行。
