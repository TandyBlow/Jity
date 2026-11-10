# 短场景事实监督（01 线，第一、二批）

这是 01 线交给叙事训练/浏览器路线消费的**短场景正文材料**，不是模型、不是候选权重、不是质量评测报告。共 39 行，正文 60–138 字：25 行来自旧图书馆 train（21 行原样 + 3 行另外选行的手写长正文 + 1 行明确标记的 2 分钟时间对照），另有 14 行是产品世界 `dragon-raja-free-day` 的 authored 短场景。全部由人从已结算变化写成，逐行读过输入与正文。

## 文件

| 文件 | 作用 |
|---|---|
| `rows.jsonl` | 主材料；一行一个短场景，含完整输入、`targetText` 和检查元数据 |
| `rows-authored.jsonl` | 14 行产品世界行，由 `authored/scenes.json` 生成；与 `rows.jsonl` 中的 authored 段一致，便于单独检查 |
| `authored/scenes.json` | 产品世界的 14 个 authored 场景定义：状态选择、变化、正文和边界 |
| `authored/build_authored.py` | 从世界文件初始快照生成产品世界行，并重建 `rows.jsonl` 的 authored 段 |
| `long/scenes.json` | 3 行 120–160 字长正文的写作定义，挂在冻结 train 行 row-0117/0132/0183 上 |
| `long/build_long.py` | 读取冻结 `x`、重算哈希、把 `short-long-*` 行写回 `rows.jsonl`，其他行逐字节保留 |
| `index.json` | 批次索引、来源、可消费字段、世界族/类别/长度统计 |
| `review.md` | 逐行人工阅读记录：变化是否落实、边界是否守住、字数 |
| `check_corpus.py` | 结构检查：冻结输入是否原样、authored 来源/SHA 是否对、是否只用 train、长度/字段是否合格 |
| `README.md` | 本说明 |

## 来源与隔离

- 25 行旧材料来自 `narration-dataset-v1` 的 `rows-xy.jsonl`，源提交 `1ab6ca791f97529a7bffed1f4837bf81a28badcb`；只用 **train** 划分，没有使用 dev/test 行。旧 199 行和 `splits/v1.json` 均未修改。3 行长正文（`short-long-0117`/`0132`/`0183`）只是给另外三行冻结 `x` 写更长的手写目标，`input` 仍是原样。
- 14 行产品材料来自 `frontend/public/worlds/dragon-raja-free-day.world.json` 的初始快照，源提交 `865ae64e0901a70c3db4f1d0eb2af60268943c53`，文件 SHA-256 `0a8b63be2932ceb5d597adf332123d8cfb584c2fd92ddd351770d4a9fa09f24a`。每行只落一个 authored 的本回合变化；不是浏览器会话，不声称前几回合发生过。人物、地点、物品、任务全部来自该世界文件，没有新造产品人物。
- 旧行 `input` 是 `x` 的原样拷贝；产品行由 `authored/build_authored.py` 从世界初始快照生成，`sourceInputSha256` 都是规范化 JSON 的 SHA-256，`check_corpus.py` 会逐行重算。
- 两类材料都标 `sourceSplit: train`；旧行从未见过的 dev/test 输入不进入训练，产品行是新开发材料。`worldFamily` 用于按世界族补样本和隔离独立终验。
- 旧行里的长 `y` 只作为文风参考（见 `styleReferenceIds`），**不作为事实来源**。有些长 `y` 与 `本回合变化` 不一致（例如 `row-0182` 让两人在走廊对话并说去借阅台，但变化只让柏清和去长桌区、温暮留走廊；`row-0199` 让方既白去装订间，但变化只让叶暮去楼梯间、方既白留天台并新增问名字任务）。本批正文按变化写，不按长 `y` 搬事件。
- **1 行派生对照**：`short-0008-two-minute-no-change` 以 `row-0008` 为底，只把 `本回合变化.时间推进` 从 20 分钟改成 2 分钟，其余输入和状态不变；`sourceEvidence.derived=true`、`baseRowId=row-0008`，并写明 derivation。它来自 09 这批真实运行里 `elapsed-two-minutes` 仍然让模型开盒子的失败，只训练“两分钟过去、没有新事件”，不是旧 199 行中的冻结行。检查脚本会验证它相对底行只改了时间。
- **14 行产品世界 authored**：`dr-0001` 到 `dr-0014`。前 9 行是 60–71 字短场景，覆盖无变化、移动、任务完成、外貌、个性、精神、两人分开、任务新增；后 5 行是 120–138 字的两事实场景（开笼搬担架、过桥报告、备床、换弹匣、凯撒进庭院）。`dr-0009` 是显式 from/to 数字的精神值变体，`variant="sanity-literal"`，不是主正文。
- **3 行旧行长正文**：`short-long-0117`/`0132`/`0183`，`input` 仍是冻结 `x` 原样，`targetText` 是新写的 120–137 字版本，用来补 120–160 字的两三事实场景。

## 一行长什么样

必填字段：

| 字段 | 含义 |
|---|---|
| `id` | 本材料内的唯一 id |
| `sourceRowId` | 旧行 id（如 `row-0008`）或 authored id（如 `authored:dragon-raja-free-day#...`）；长正文行用 `short-long-*` 作本行 id、原 `row-*` 作来源 |
| `sourceEvidence` | 数据集、源提交、源文件/世界 SHA、train 划分；authored 行另有 `authored=true` 和 `premise` |
| `sourceSplit` | 固定 `train` |
| `sourceInputSha256` | 本行 `input` 的规范化 SHA-256 |
| `worldFamily` | 旧馆内区域族（如 `library-news`）或 `dragon-raja-free-day` |
| `categories` | 本行覆盖的变化类型，例如 `movement`、`task_complete`、`sanity_change` |
| `input` | 完整四键输入：视角、上回合状态、本回合变化、本回合状态 |
| `targetText` | 人手写的 60–160 字自然中文叙事 |
| `targetChars` | `len(targetText)`（码点） |
| `requiredFacts` | 这行必须落实的已结算事实：时间、移动、物品/外貌、任务、精神值等 |
| `licensedDetails` | 正文里允许出现的、有输入依据的细节和细微动作 |
| `knowledgeBoundary` | 视角是谁、能知道什么、不能替谁说出什么秘密 |
| `forbiddenInventions` | 本行明确禁止补写的往事、线索、物品或事件 |
| `styleReferenceIds` | 可参考节奏/对白/人物反应的旧行；不是事实来源 |
| `notes` | 本行的写作取舍 |
| `variant` | 可选的检查变体；目前只有 `sanity-literal` |

**模型输入只应使用 `input`，训练目标只应使用 `targetText`。** `requiredFacts`、`licensedDetails`、`knowledgeBoundary`、`forbiddenInventions`、`styleReferenceIds` 是检查/审计元数据，不能拼进 prompt，也不能作为参考答案喂给模型。

## 覆盖

| 类别 | 行数 | 例子 |
|---|---:|---|

| 无变化 | 3 | `row-0008` 装订间二十分钟；`short-0008-two-minute-no-change` 同状态两分钟；`dr-0001` 服务巷两分钟 |
| 移动/两人分开 | 8 | 旧 `row-0100`/`row-0182`/`row-0199`；产品 `dr-0002` 诺诺进器材棚、`dr-0007` 路明非进棚、`dr-0011` 苏茜过桥上二层、`dr-0014` 凯撒进庭院、`dr-0010` 担架从笼内到棚 |
| 物品变化 | 9 | 旧杯水干、报夹换铜夹、绳头重编、除湿机重启、合订本封面/扉页；产品护目镜、挂锁、担架、演习枪 |
| 地点变化 | 6 | 旧报刊库返潮、灯全亮、空出三个位置、吊兰黄叶、窗开一条缝 |
| 外貌变化 | 5 | 旧苏既明换金属细框眼镜、江既白手指沾黑、苏既明手指沾灰；产品芬格尔油印解除/护膝扣好、护目镜戴好 |
| 任务完成/新增 | 11+4 | 旧换锁/火灾/闭馆通告/封面来路/缺页数/封面翻正/两项闭馆通告；产品护目镜、报告小桥、备床、换弹匣、新增问门闩 |
| 情绪/精神变化 | 9 | 旧七行；产品 `dr-0006` 无数字下降、`dr-0009` 数字变体 |
| 个性/秘密说出一层 | 3 | 旧 `row-0055` 两层班次、`row-0183` 新个性；产品 `dr-0005` 诺诺先护人再探头 |

一行可能覆盖多类，所以上表行数合计大于 39。

世界族分布：

- `library-news` 13
- `library-basement` 4
- `library-utilities` 3
- `library-lending` 2
- `library-courtyard` 2
- `library-upper-corridor` 1
- `dragon-raja-free-day` 14

## 给 10（训练）的消费方式

- 直接把 `input` + `targetText` 当作 `yShort` 样本；`targetText` 是 60–138 字的短文，不是逐事实的一两句 beat。产品 14 行可直接补卡塞尔学院世界，不要再只学旧图书馆的实体映射。
- 如果要做 beat 目标，可从 `requiredFacts` 拆，但 beat 文本要另写；不要把 `requiredFacts` 原样拼进 prompt。
- `styleReferenceIds` 指向旧长文；只借节奏、对白密度和人物反应，不搬事件。
- 本批可以按 `worldFamily` 分组混入；旧 25 行没有使用旧 dev/test，产品 14 行是新 authored 材料，不会把独立终验的输入带进训练。
- 本批没有连续回合；`sequenceId`/`turnIndex` 为 `null`。需要连续回合时由 05 线或后续批次提供，不要把这 39 行误当连续序列。
- `dr-0009` 是显式数字变体，`variant="sanity-literal"`；如果训练侧不需要数字，可单独丢掉，不要把它和 `dr-0006` 当成两个事件。

## 给 02（浏览器叙事）的消费方式

- 这 39 行是“事实不漏、边界不越、读起来像正文”的参照，不是候选模型输出。产品 14 行可以直接检查卡塞尔学院实体上的移动、任务、装备、分开和物品转移。
- 对照 `requiredFacts` 看：关键动作/结果有没有漏；对照 `knowledgeBoundary`/`forbiddenInventions` 看：有没有替角色说出不知道的秘密、有没有补重大往事/线索。
- 如果某条真实生成在这些行上出错，把输入、输出和错误类型交给 01，下一批按同类世界族补，不要用规则模板替换失败样本。`dr-0001` 是无变化对照，`dr-0002`/`dr-0007`/`dr-0011`/`dr-0014` 是移动+分开对照，`dr-0008` 是“新增任务但不给答案”的对照，`dr-0010` 是“物品转移但登记没完成”的对照。

## 验证

```bash
python -X utf8 experiments/narration-quality/corpus-short/check_corpus.py
```

当前结果：39 行；长度 60–138（15 行 60–79、16 行 80–119、8 行 120–160）；25 行旧材料（21 行原样 + 3 行另外选行的长正文 + 1 行派生对照只改时间）+ 14 行产品世界 authored；旧行全部 train，authored 行标 train；世界文件 SHA、行哈希、authored 变化与结果状态一致性重算通过。语义层面的“变化是否落实、边界是否守住”由 `review.md` 的逐行记录负责，脚本不替代人工阅读。

## 已知限制

- 本批没有 GPU 生成，也没有模型训练；正文是人手写的监督材料。
- 没有自动语义评分；`requiredFacts` 是检查清单，不是可机器判定的完整逻辑。
- 旧馆 25 行 + 产品世界 14 行；产品行只来自一个初始快照，只覆盖部分人物/地点，不是全类别、全人物、全地点的平衡采样。
- 正文长度 60–138 字，已补 8 行 120–160；但 140–160 字的上端只有 1 行，且都是两三个事实，不是密集多事实场景。
- 旧长 `y` 有事实错误，未作为事实来源；本批不修改旧数据，也不重新划分旧 splits。
- `licensedDetails` 中含少量空间/动作具体化（如杯口朝向、门虚掩、用裤缝擦手），均不改变已结算事实；如果训练侧要求更严，可逐行删。
- 产品 14 行是 authored 开发材料，不是浏览器记录；`dr-0009` 是数字对齐变体，不是主正文；`short-long-*` 长正文是同一冻结输入的第二个实现，不改变旧行。

## 下一批

按 02/10 的真实遗漏、捏造、指代和文风问题补；优先补：

1. 更短（60–80 字）的单事实场景；
2. 更长（120–160 字）但只含 2–3 个事实的场景；
3. 同一世界族的连续两回合（与 05 线区分：01 只做短场景，不抢完整场景/连续回合）；
4. 被真实模型混淆的“两人分开/任务完成但不说答案/他人秘密只说出一层”类型；
5. 产品世界更多人物/地点，以及 10 明确要的 120 行目标；本批只交 14 行产品 + 3 行长正文，不虚报数量；剩余缺口按真实失败继续补。

补样本时继续只用 train 或另立有来源的开发世界材料，不碰 dev/test，不修改旧 199 行。
