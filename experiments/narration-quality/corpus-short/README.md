# 短场景事实监督（01 线，第一批）

这是 01 线交给叙事训练/浏览器路线消费的**短场景正文材料**，不是模型、不是候选权重、不是质量评测报告。第一批 22 行，正文 62–106 字：21 行的 `input` 是旧行原样，另有 1 行明确标记的 2 分钟时间对照（只改 `时间推进`），全部由人从已结算变化写成，逐行读过输入与正文。

## 文件

| 文件 | 作用 |
|---|---|
| `rows.jsonl` | 主材料；一行一个短场景，含完整输入、`targetText` 和检查元数据 |
| `index.json` | 批次索引、来源、可消费字段、世界族/类别/长度统计 |
| `review.md` | 逐行人工阅读记录：变化是否落实、边界是否守住、字数 |
| `check_corpus.py` | 结构检查：冻结输入是否原样、是否只用 train、长度/字段是否合格 |
| `README.md` | 本说明 |

## 来源与隔离

- 输入全部来自旧数据集 `narration-dataset-v1` 的 `rows-xy.jsonl`，源提交 `1ab6ca791f97529a7bffed1f4837bf81a28badcb`。
- 只用 **train** 划分；没有使用 dev/test 行。旧 199 行和 `splits/v1.json` 均未修改。
- `input` 是旧行 `x` 的原样拷贝；`sourceInputSha256` 是规范化 JSON 的 SHA-256，`check_corpus.py` 会逐行重算。
- 没有新造世界、没有新造人物。`worldFamily` 只是把旧图书馆世界按馆内区域分组，便于后续按族补样本和隔离独立终验。
- 旧行里的长 `y` 只作为文风参考（见 `styleReferenceIds`），**不作为事实来源**。有些长 `y` 与 `本回合变化` 不一致（例如 `row-0182` 让两人在走廊对话并说去借阅台，但变化只让柏清和去长桌区、温暮留走廊；`row-0199` 让方既白去装订间，但变化只让叶暮去楼梯间、方既白留天台并新增问名字任务）。本批正文按变化写，不按长 `y` 搬事件。
- **1 行派生对照**：`short-0008-two-minute-no-change` 以 `row-0008` 为底，只把 `本回合变化.时间推进` 从 20 分钟改成 2 分钟，其余输入和状态不变；`sourceEvidence.derived=true`、`baseRowId=row-0008`，并写明 derivation。它来自 09 这批真实运行里 `elapsed-two-minutes` 仍然让模型开盒子的失败，只训练“两分钟过去、没有新事件”，不是旧 199 行中的冻结行。检查脚本会验证它相对底行只改了时间。

## 一行长什么样

必填字段：

| 字段 | 含义 |
|---|---|
| `id` | 本材料内的唯一 id |
| `sourceRowId` | 旧行 id，例如 `row-0008` |
| `sourceEvidence` | 数据集、源提交、源文件、行 id、train 划分 |
| `sourceSplit` | 固定 `train` |
| `sourceInputSha256` | 旧 `x` 的规范化 SHA-256 |
| `worldFamily` | 馆内区域族，例如 `library-news`、`library-basement` |
| `categories` | 本行覆盖的变化类型，例如 `movement`、`task_complete`、`sanity_change` |
| `input` | 完整旧 `x`：视角、上回合状态、本回合变化、本回合状态 |
| `targetText` | 人手写的 60–160 字自然中文叙事 |
| `targetChars` | `len(targetText)`（码点） |
| `requiredFacts` | 这行必须落实的已结算事实：时间、移动、物品/外貌、任务、精神值等 |
| `licensedDetails` | 正文里允许出现的、有输入依据的细节和细微动作 |
| `knowledgeBoundary` | 视角是谁、能知道什么、不能替谁说出什么秘密 |
| `forbiddenInventions` | 本行明确禁止补写的往事、线索、物品或事件 |
| `styleReferenceIds` | 可参考节奏/对白/人物反应的旧行；不是事实来源 |
| `notes` | 本行的写作取舍 |

**模型输入只应使用 `input`，训练目标只应使用 `targetText`。** `requiredFacts`、`licensedDetails`、`knowledgeBoundary`、`forbiddenInventions`、`styleReferenceIds` 是检查/审计元数据，不能拼进 prompt，也不能作为参考答案喂给模型。

## 第一批覆盖

| 类别 | 行数 | 例子 |

一行可能覆盖多类，所以下表行数合计大于 22。
|---|---:|---|
| 无变化 | 2 | `row-0008` 装订间二十分钟无变化；`short-0008-two-minute-no-change` 同状态只过两分钟 |
| 移动/两人分开 | 3 | `row-0100` 两人交换位置；`row-0182` 柏清和进长桌区、温暮留走廊；`row-0199` 叶暮下楼梯间、方既白留天台 |
| 物品变化 | 4 | 杯水干、报夹换铜夹、绳头重编、除湿机重启 |
| 地点变化 | 6 | 报刊库返潮、灯全亮、空出三个位置、吊兰黄叶、窗开一条缝 |
| 外貌变化 | 2 | 苏既明换金属细框眼镜；江既白手指沾黑、袖口蹭灰 |
| 任务完成/新增 | 4+2 | 换锁查清、火灾查清、两项闭馆通告查清、封面来路查清；新增送签字、问第三个名字 |
| 情绪/精神变化 | 6 | 叶既白小升、黎既白下降、顾照微降、温照上升、温暮下降、江既白大跌 |
| 个性/秘密说出一层 | 1 | `row-0055` 秦书言说母亲当班、韩望舒说父亲当班 |

世界族分布：

- `library-news` 10
- `library-basement` 4
- `library-utilities` 3
- `library-lending` 2
- `library-courtyard` 2
- `library-upper-corridor` 1

## 给 10（训练）的消费方式

- 直接把 `input` + `targetText` 当作 `yShort` 样本；`targetText` 是 62–106 字的短文，不是逐事实的一两句 beat。
- 如果要做 beat 目标，可从 `requiredFacts` 拆，但 beat 文本要另写；不要把 `requiredFacts` 原样拼进 prompt。
- `styleReferenceIds` 指向旧长文；只借节奏、对白密度和人物反应，不搬事件。
- 本批可以按 `worldFamily` 分组混入；没有使用 dev/test，不会把独立终验的输入带进训练。
- 本批没有连续回合；`sequenceId`/`turnIndex` 为 `null`。需要连续回合时由 05 线或后续批次提供，不要把这 22 行误当连续序列。

## 给 02（浏览器叙事）的消费方式

- 这 22 行是“事实不漏、边界不越、读起来像正文”的参照，不是候选模型输出。
- 对照 `requiredFacts` 看：关键动作/结果有没有漏；对照 `knowledgeBoundary`/`forbiddenInventions` 看：有没有替角色说出不知道的秘密、有没有补重大往事/线索。
- 如果某条真实生成在这些行上出错，把输入、输出和错误类型交给 01，下一批按同类世界族补，不要用规则模板替换失败样本。

## 验证

```bash
python -X utf8 experiments/narration-quality/corpus-short/check_corpus.py
```

当前结果：22 行；长度 62–106；21 行冻结输入逐行一致，1 行派生对照只改时间；全部来自 train；结构检查通过。语义层面的“变化是否落实、边界是否守住”由 `review.md` 的逐行记录负责，脚本不替代人工阅读。

## 已知限制

- 本批没有 GPU 生成，也没有模型训练；正文是人手写的监督材料。
- 没有自动语义评分；`requiredFacts` 是检查清单，不是可机器判定的完整逻辑。
- 只覆盖旧馆内世界，且只覆盖 22 个 train/派生场景；不是全类别、全人物、全地点的平衡采样。
- 正文长度集中在 62–106 字，接近 60 字下限的短场景仍少；后续可按 02/10 的真实失败补更短和更长的两端。
- 旧长 `y` 有事实错误，未作为事实来源；本批不修改旧数据，也不重新划分旧 splits。
- `licensedDetails` 中含少量空间具体化（如杯口朝向、门虚掩），均不改变已结算事实；如果训练侧要求更严，可逐行删。

## 下一批

按 02/10 的真实遗漏、捏造、指代和文风问题补；优先补：

1. 更短（60–80 字）的单事实场景；
2. 更长（120–160 字）但只含 2–3 个事实的场景；
3. 同一世界族的连续两回合（与 05 线区分：01 只做短场景，不抢完整场景/连续回合）；
4. 被真实模型混淆的“两人分开/任务完成但不说答案/他人秘密只说出一层”类型。

补样本时继续只用 train 或另立有来源的开发世界材料，不碰 dev/test，不修改旧 199 行。
