# 01 线：短场景事实监督（第七批）

状态：**batch 8 ready**。71 行人手写的 61–152 字短场景，已提交到本线分支，可直接消费。材料提交：`66f681a49cd99e99807005e830c3797d40a4ab07`。

这不是模型、不是候选权重、不是自动评测报告，也不替代训练脚本或最终验收。它是给叙事训练/浏览器路线用的**正文监督**：输入是已经结算的世界变化，正文要像小说，但关键事实一个不漏、输入没有的东西一个不加。

## 交付物

| 路径 | 内容 |
|---|---|
| `experiments/narration-quality/corpus-short/rows.jsonl` | 71 行主材料：完整 `input`、`targetText`、检查元数据 |
| `experiments/narration-quality/corpus-short/rows-authored.jsonl` | 20 行产品世界行，单独一份便于核对 |
| `experiments/narration-quality/corpus-short/first/` | 首批 22 行短正文的定义与写回脚本（含 2 分钟派生对照） |
| `experiments/narration-quality/corpus-short/authored/` | 产品世界的 20 个场景定义与生成脚本（世界文件初始快照 + 一个 authored 变化） |
| `experiments/narration-quality/corpus-short/long/` | 4 行 109–136 字长正文的定义与写回脚本（冻结 `x` 原样） |
| `experiments/narration-quality/corpus-short/short/` | 25 行另外选行短正文的定义与写回脚本（`short2-*`，冻结 `x` 原样） |
| `experiments/narration-quality/corpus-short/index.json` | 批次索引、来源、行类型、世界族/类别/长度统计、失败对应 |
| `experiments/narration-quality/corpus-short/review.md` | 71 行逐行人工阅读记录（变化落实、边界、字数） |
| `experiments/narration-quality/corpus-short/check_corpus.py` | 结构检查：冻结输入原样、authored 来源/SHA、authored 变化与结果状态一致、train-only、长度/字段、姿势/事件动词/授权实体/时间/requiredFacts |
| `results/quality/team-01-input.json` | 共享交接：指向实际 jsonl，含正文、可消费字段、限制 |

## 来源与隔离

- 51 行旧材料来自 `narration-dataset-v1` 的 `rows-xy.jsonl`，源提交 `1ab6ca791f97529a7bffed1f4837bf81a28badcb`：22 行首批短场景（其中 1 行是 2 分钟派生对照）+ 4 行另外选行（`row-0117`/`0132`/`0137`/`0183`）的长正文 + 25 行另外选行的短正文。
- 只用 **train**。没有用 dev/test；旧 199 行和 `splits/v1.json` 未修改。`sourceSplit` 全部为 `train`，检查脚本会对照 `splits/v1.json` 重算。
- `input` 是旧行 `x` 的原样拷贝；每行有 `sourceInputSha256`，检查脚本会重算。4 行长正文只是给另外四行冻结 `x` 写更长的目标，25 行 `short2-*` 是另外 25 行冻结 `x` 的短正文，输入都没有改。
- 20 行产品材料来自 `frontend/public/worlds/dragon-raja-free-day.world.json` 的初始快照，源提交 `865ae64e0901a70c3db4f1d0eb2af60268943c53`，世界文件 SHA-256 `0a8b63be2932ceb5d597adf332123d8cfb584c2fd92ddd351770d4a9fa09f24a`。每行只落一个 authored 的本回合变化；不是浏览器会话，不声称前几回合发生过。人物、地点、物品、任务全部来自该世界文件，检查脚本会验证正文里出现的世界实体名都在本行输入里。
- 旧长 `y` 只做文风参考，不做事实来源。已发现长 `y` 与 `本回合变化` 不一致的行（`row-0182`、`row-0199`），正文按变化写，不按长 `y` 搬事件。
- **1 行派生对照**：`short-0008-two-minute-no-change` 以 `row-0008` 为底，只把 `本回合变化.时间推进` 从 20 分钟改成 2 分钟，其余输入和状态不变；`sourceRowId=derived:row-0008`、`sourceEvidence.derived=true`、`baseRowId=row-0008`，并写明 derivation。它的 `sourceRowId` 故意不写成 `row-0008`，这样 10 线按 `sourceRowId` join `rows-v2` 时会自然跳过它，不需要额外分支。它只训练“两分钟过去、没有新事件”，不是旧 199 行中的冻结行；检查脚本会验证相对底行只改了时间。

## 一行结构

```json
{
  "id": "short-0050-backdoor-lock",
  "sourceRowId": "row-0050",
  "sourceEvidence": {"dataset": "...", "sourceCommit": "...", "rowId": "row-0050", "split": "train"},
  "sourceSplit": "train",
  "sourceInputSha256": "...",
  "worldFamily": "library-lending",
  "categories": ["appearance_change", "task_complete"],
  "sequenceId": null,
  "turnIndex": null,
  "input": { "...旧 x 原样..." },
  "targetText": "「查清九八年秋天为什么换后门的锁」——顾望舒办完了。她把钥匙从锁孔里取出来……",
  "targetChars": 89,
  "requiredFacts": [
    {"kind": "time_advance", "text": "10 分钟"},
    {"entity": "秦既白", "kind": "appearance_removed", "text": "袖口沾了机油"},
    {"entity": "顾望舒", "kind": "task_completed", "task": "查清九八年秋天为什么换后门的锁"}
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

71 行，正文 61–152 字（15 行 60–79、49 行 80–119、7 行 120–160，均值 95.0）。其中 4 行（`row-0138`/`row-0161`/`row-0175`/`row-0178`）是只写已结算地点/外貌、不写事件的 strict 场景，对应 02 `req-02-02` 的“只实现已结算变化加至多一个许可外貌细节”；1 行 2 分钟无变化对照，来自 09 真实运行里 `elapsed-two-minutes` 仍让模型开盒子的失败。

一行可能覆盖多类，所以下表行数合计大于 71。

| 类型 | 行数 | 具体 |
|---|---:|---|
| 无变化 | 3 | `row-0008` 装订间 20 分钟；`short-0008-two-minute-no-change` 同状态 2 分钟；`dr-0001` 服务巷 2 分钟 |
| 移动/两人分开 | 16 | 旧 `row-0100`/`row-0182`/`row-0199`/`row-0111`/`row-0119`/`row-0136`/`row-0034`；产品 `dr-0002`/`dr-0007`/`dr-0010`/`dr-0011`/`dr-0014`/`dr-0015`/`dr-0017`/`dr-0018` |
| 物品变化 | 19 | 旧杯水干、报夹换铜夹、绳头重编、除湿机重启、合订本封面/扉页/夹层残页、封条蜡印、报捆绳结、胶片盒三层标签、挂钟电池、值班表贴正、校样补字、铜灯灯罩、邮筒投信口；产品护目镜、挂锁、担架、演习枪 |
| 地点变化 | 12 | 旧报刊库返潮、灯全亮、空出三个位置、吊兰黄叶、窗开一条缝、胶锅糊边、借阅台旧书、长桌区光退、楼梯间刻字磨掉、古籍库柜格空出 |
| 外貌变化 | 9 | 旧苏既明换金属细框眼镜、江既白手指沾黑、苏既明手指沾灰、苏既白手掌红印/袖口湿、叶暮指节胶布、温砚袖口印泥；产品芬格尔油印/护膝、护目镜 |
| 任务完成/新增 | 28+8 | 旧换锁/火灾/闭馆通告/封面来路/缺页数/封面翻正/换锈管/三人补字/重排版/值班名字/交接记录/封面来源/篆字/两项调查/三月名字/二十二页/补字/铜灯同场/备用弹匣；产品护目镜、报告小桥、备床、换弹匣、检查门闩、告知门闩、症状问答、新增问门闩/第七本 |
| 情绪/精神变化 | 18 | 旧十五行；产品 `dr-0006`、`dr-0016`、`dr-0019`；每行都写 from/to 两个数字 |
| 个性/秘密说出一层 | 11 | 旧 `row-0055` 两层班次、`row-0183` 新个性、`row-0137` 写条子、`row-0056` 值班名字后无措、`row-0074` 确定门从外面锁、`row-0180` 认出半个篆字、`row-0090` 反锁门、`row-0039`/`row-0061` 两人替换；产品 `dr-0005`、`dr-0016` |

世界族：`library-news` 25、`dragon-raja-free-day` 19、`library-courtyard` 7、`library-lending` 7、`library-basement` 6、`library-utilities` 5、`library-upper-corridor` 1。

## 给 10：怎么直接消费

- 把 `input` + `targetText` 作为 **`yShort`** 样本；正文是 61–152 字，不是 20–60 字的单事实 beat。
- 产品 20 行（`dr-*`）是卡塞尔学院自由一日世界，可直接补产品实体；不要再只学旧图书馆的映射。
- 7 行 120–160 字可直接用于“更长但仍只含 2–3 个事实”的目标；不要用它们去凑密集多事实。
- 本批的正文已经按 10 线参考 binder 逐条对齐：
  - 按 `narration_rules.build_facts`/`binds` 只读重算，71 行的 84 条强制事实（moved / task_achieved / personality_changed / sanity_changed）全部能绑定到正文句子。
  - 按 `projection_v2.normalize_projection` + `v2_render.serialize` 重算，71 行都能序列化；只有 `short-0008-two-minute-no-change` 与 `row-0008` 的 `xProse` 不同，且只差“20 分钟 → 2 分钟”。
  - 任务完成的事实要求目标文本原样出现，并配“办完/做完”这类完成语，所以正文里会出现 `「查清…」` 的引述；精神值变化要求同时出现 from/to 两个数字。这两条是当前对齐器的硬要求，不是文风偏好；如果 10 的下一版对齐器放宽，可以再改写出更自然的版本。
- 如果 `qwen25-beat-v1` 需要 beat：从 `requiredFacts` 拆，但 beat 文本要另写；不要机械切 `targetText`。本批现在能按事实绑定，已经具备切 beat 的条件。
- `styleReferenceIds` 指向旧长文；只借节奏、对白密度、人物反应，不搬事件。
- 本批没有连续回合；`sequenceId`/`turnIndex` 为 `null`，不要当连续序列。
- 导入时注意三类来源：① 22 行首批 + 4 行 `short-long-*` + 25 行 `short2-*` 都是冻结 `x`，可与 `rows-v2` 的 `xProse` 逐字节对照（`short-0008-two-minute-no-change` 的 `sourceRowId` 是 `derived:row-0008`，按 id 查不到，正好跳过；不要把它当成缺失）；② `dr-*` 产品行没有对应的 `rows-v2` 源，不能做“等于冻结 `xProse`”的断言，需要按世界文件 SHA 单独登记；③ 产品行不能按 `sourceRowId` join `rows_v2`，导入脚本要显式跳过或按 `id` 单独处理。
- 71 行里有 7 行 120–152 字；如果 `yShort` 只想要 60–120，按 `targetChars` 过滤即可，不要机械截断。

## 给 02：怎么当参照

- 这是“事实不漏、边界不越、读起来像正文”的短参照，不是候选输出，也不是逐字模板。
- 对照 `requiredFacts` 看关键动作/结果；对照 `knowledgeBoundary`/`forbiddenInventions` 看有没有替角色说出不知道的秘密、有没有补重大往事/线索。
- 改述可以，事实和边界不能破；`targetText` 只是一种实现，不是必须逐字复现。
- 任务完成行现在把目标原样放在「」里并写完成语，精神值行写 from/to 数字；这两类句子会偏“任务播报”，是为了先让当前对齐器能过，不是要求 02 的最终文风照抄。等 02 放宽到“行为层面落实”时，01 再补一版不带数字/不带引述的对照。
- 真实生成失败时，把输入、生成文本和错误类型（漏事实/捏造/指代/文风）交给 01，下一批按同类补；不要用规则模板替换失败样本然后宣称达标。

## 按真实失败补的行

| 真实失败 | 证据 | 对应材料 |
|---|---|---|
| 无变化却开盒子/写古董 | `results/quality/beat-qwen25-1.5b-instruct.json` `elapsed-two-minutes` | `short-0008-two-minute-no-change`、`dr-0001-no-change-lane` |
| 移动只写 11 个字，像电报 | 同上 `move-direction` | `dr-0015-move-without-posture`、`dr-0011-su-report-bridge` |
| 程序 realizer 写“站在某地” | `results/quality/browser-09.json` 04-settlement 通知 | `dr-0015`（全文无姿势词），检查脚本有姿势词硬检查 |
| 同地点另一人的句子被误判成视角人物的 at 事实 | 同上 actor swap | `dr-0016-two-people-clear-subjects`（每句用名字开头）、`dr-0002` |
| realizer 写输入没有的“跨溪小桥” | 同上 `unlicensed_entity` | `dr-0017-chu-checks-hatch`，检查脚本有“实体必须在输入里出现”的硬检查 |
| 任务完成但必须不说出答案 | `row-0050`/`row-0152`/`row-0169`/`row-0188` 的旧失败，02 的 `req-02-02` | `short-long-0117`、`short-long-0132`、`dr-0008`、`dr-0017`、`dr-0018` |
| 两人同场时指代/主语混淆 | 02 的指代问题、09 的 actor swap | `dr-0016`、`dr-0002`、`dr-0007` |
| 任务完成句没有目标原文，被对齐器判成漏事实 | 10 线 binder 只读重算（本批修复前 34 条任务事实未绑定） | 28 个任务完成行统一改成“`「目标」` + 办完/做完”，并写入 `requiredFacts` 检查 |
| 精神值变化没有 from/to 数字，绑定器无法落实 | 同上（本批修复前 18 条未绑定） | 15 行旧材料 + `dr-0006`/`dr-0016`/`dr-0019` 全部写数字 |

## 人工检查证据

71 行都完整读过 `input`（视角、上回合状态、本回合变化、本回合状态）和正文，`review.md` 留了逐行记录。重点检查：

1. 关键动作/结果是否漏（移动的起终点、任务完成、物品新状态、精神值方向）。
2. 是否新增命名角色、物品、线索、往事、承诺。
3. 是否替视角人物说出 `knowledgeBoundary.mustNotReveal` 里的秘密。
4. 是否把长 `y` 的事实错误搬进来；`row-0182`/`row-0199` 是明确的反例。
5. 字数、单段、无占位符、无输入未授权的姿势词和事件动词。

结构检查命令：

```bash
python -X utf8 experiments/narration-quality/corpus-short/check_corpus.py
```

当前输出：71 行；长度 61–152（15 行 60–79、49 行 80–119、7 行 120–160）；51 行旧材料（22 行首批 + 4 行同冻结输入的长正文 + 25 行同冻结输入的短正文，含 1 行派生对照只改时间）+ 20 行产品世界 authored；全部标 train；世界文件 SHA、行哈希、authored 变化与结果状态一致性、姿势词（输入有依据除外）、未授权实体、事件动词、时间推进和 `requiredFacts` 检查通过。语义检查是人工的，脚本不替代。

10 线 `import_short_corpus.py` 的只读副本（`/tmp`，不改 10 线工作树）已经跑过本批：71 行、84 条 beat、84 条强制事实、`problems: []`；其中 19 行本来就没有强制事实（无变化/纯外貌/纯物品/仅地点），所以 `beatCount=0`，其余 52 行每条事实都切出了 beat。

## 已知限制

- 没有 GPU 生成/训练；正文是人手写的监督材料。
- 没有自动语义评分；`requiredFacts` 是清单，不是完整逻辑。
- 71 行，旧馆 51 行 + 产品世界 20 行；产品行只来自一个初始快照，不是全人物、全地点、全类别平衡采样。
- 长度 61–152，140 字以上只有 1 行，且长场景都是两三个事实，不是密集多事实。
- 任务目标原样引述、精神值数字会让部分句子偏“任务播报”；这是当前对齐器的硬要求，等对齐器接受行为层面落实后再补自然版对照。
- 少量空间具体化（杯口朝向、门虚掩、风）是有依据的细微细节，不是已结算事实；如果训练侧要求更严，可逐行删。
- 旧长 `y` 有事实错误，未作为事实来源；本批不修改旧数据，也不重新划分。
- 产品行是 authored 开发材料，不是浏览器记录；没有单独的 `variant` 行。
- `short-long-*` 长正文是同一冻结 `x` 的第二个实现，不改变旧行；不要把它当成旧数据的修正版。
- 没有独立终验材料；这是开发监督，不是最终验收集。

## 下一批

按 02/10 的真实遗漏、捏造、指代和文风问题补，优先：

1. 60–80 字的单事实短场景；
2. 140–152 字、仍只含 2–3 个事实的场景；
3. 同一世界族的连续两回合（01 只做短场景，完整场景/连续回合仍归 05）；
4. 真实模型最容易错的“两人分开/任务完成但不说答案/秘密只说出一层”；
5. 10 明确要的 120 行目标：本批 71 行，剩余按真实失败补，不虚报数量。

继续只用 train 或另立有来源的开发世界材料；不碰 dev/test，不改旧 199 行。
