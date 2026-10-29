# N4 成句语料构造协议

日期：2026-10-29。复核轮 11 修订：扩批 v9.1（600 行 / 150 组）、句级覆盖与可选逗号移动识别、三项工具最新结果见 §8。依据：[方案表](../../model-training-runtime.md)（N4 例外条款）、[C任务边界](../../README.md)样本隔离、2026-10-29 语料设计评审六项要求。本协议约束 `build_seeds.py`（构造）、`build_expansion.py`（扩批）、`corpus_check.py`（行校验）、`dedup_check.py`（去重）、`validate_plan_authority.py`（权威核对）与语料 JSONL 形状。

## 1. 行 schema（JSONL，每行一对象）

| 字段 | 约束 |
| --- | --- |
| `sourceGroupId` | 组 ID。**同一事实种子的模板行与全部改写行共用**；`split` 在组级一致（校验器强制），训练/开发验收按组隔离，禁止按行随机拆分 |
| `rowOrigin` | `template-seed`（程序渲染）或 `rewrite`（改写）——逐行标记 |
| `rewriter` | `program`（种子行）或 `zcode-model`（改写行，如实标注；模型改写进入训练依据方案表 N4 例外条款） |
| `task` | 本批全部 `n4-sentence` |
| `split` | `train` 或 `dev`（组级） |
| `tier` | `small`（60 个 train 源：24 既有＋36 新）/`large`（120 个 train 源，含 small）/`fixed-dev`（30 个 dev 源） |
| `world` | 独立构造的 before 注册表：`protagonistId`＋全部被引用地点＋每个人物 id/homeLocId/initialSanity/initialPersonality/tasks。**每个被引用容器必须登记**；移动目标不得等于移动者 home（无幂等移动） |
| `rawDelta` | 独立构造的原始 Δ（`entityDeltas`＋`time`）。时间推进始终保留在 Δ 中；正文可省略时间，但 Δ 不因省略而删除 |
| `fullPlan` | 完整事实表（**含**时间条目的 plan 超集）；权威来源核对与 Δ 对账跑在 fullPlan 上 |
| `timeScope` | `expressed`（plan＝fullPlan）或 `omitted`（plan＝fullPlan 去掉时间条目）；正文检查只对 plan 负责 |
| `plan` | 事实计划条目数组（表达计划），`ref` 下标＋kind/entityId/name/值。由程序枚举**独立构造**（非状态差分反推），`planConstruction` 记录构造方法（声明）；权威证据由 `validate_plan_authority.py` 独立产出——把 plan 映射为 backend v2 `EntityDelta`/`TimeAdvance` 并经 pydantic 逐行校验，结果落 `authority-report.json`（含 server 树 HEAD、apply.py 哈希与逐行组合哈希），行内 `planValidation` 仅指向该报告 |
| `planOnlyClaims` | 非 Δ 的计划条目（positioned 现状、no_change 空点断言）；组级一致 |
| `text` | 正文 |
| `planRefs` | 逐句回指：句子按句号切分后每句引用的 plan 下标数组。**引用存在≠事实忠实**，忠实由校验器逐类核对＋人工抽验 |
| `mustExpress` / `mayMention` / `mustNotAdd` | 三类标注齐备（必述下标／可选下标／禁止新增主张的文字描述） |
| `hashes` | `plan`/`fullPlan`/`world`/`rawDelta`/`text` 的 canonical JSON sha256，校验器重算比对 |
| `purpose` | 用途记录（一行一写） |
| `overlap` | 仅改写行、**校验时计算不写回**：见 §4 |

## 2. 排除清单（dedup_check.py 扫描源，版本钉 commit）

| 源 | 提取字段 |
| --- | --- |
| `frontend/src/lib/world-engine/runtime/narration-eval-samples.ts`（nv-*，HEAD 7af52d7） | mechanical/reference/forbidden 数组/goal/mayMention/note 全部字符串 |
| `frontend/src/lib/world-engine/runtime/narration-eval-validation.ts`（hv-*，同上） | 同上 |
| `frontend/src/lib/world-engine/runtime/narration-split-samples.ts`（ns-*，同上） | requiredFacts.phrase、mustNotFabricate、描述文本 |
| `frontend/src/lib/world-engine/runtime/b3-samples.ts`，同上 | 任务 goal、appearance、描述 |
| `artifacts/narration-eval-recheck/run.json`（归档采纳稿/参照/生成文本） | 递归全部字符串值 ≥4 字 |
| `artifacts/narration-split-baseline.json`（程序基线输出） | 同上 |
| `artifacts/world-page/*.json`＋`artifacts/world-chain/*.json`＋`artifacts/narration-http-review.json`（**整链真机归档**，复核轮 3 要求纳入） | 递归全部字符串值；C 树缺失时回退主树读取并记录实际路径，仍缺记 MISSING 不静默跳过 |

**Forbid 串剥注记变体**：含 `（…）` 的源串，剥注记后的核心串同样入源集——直接来自冒烟探针教训（`narration-freeform` = nv-cont-1 forbidden 串剥「（方向反转）」派生）。

**已知漏扫项（如实声明）**：TS 文件的类型代码与注释不扫；`world-page/`、`world-chain/` 等整链归档里的真机输入原文未扫；模板句式拼接代码（committed-narration 等）以短语人工核对补（「没有新的变化」教训即来源于此——本批种子空点句式已显式避开）。**去重结论只能表述为"在上述清单范围与规则下零命中"**；换名、方向反转等未穷尽派生由人工抽验补，不宣称独立证明。

**扫描规则**：语料侧只扫**内容字段**（text＋plan 的 name/from/to/at/goal/text；结构字段 kind/unit/ref/amount/entityId/rendered/scope 排除——短结构值如 kind="time" 会对长元描述串产生假方向命中）；源串 ≥4 字做逐字段**双向**子串检查（不拼接整行——拼接改变方向且掩盖字段边界）；<4 字（人名/短地名等 cast 词）不判失败只登记命中（设计目标=新词表零 cast 命中，命中即回改）。

## 3. 词表（与 B cast 零交集）

基础组：人物陈舟/苏晚/周砚/林望/沈青；地点东门/水房/钟楼/侧院/柴房/石桥/碑亭；物品铜铃/木匣/青瓷碗/油纸伞；任务 goal 把铜铃挂回钟楼/整理柴房/修缮石桥栏杆/清点碑亭石刻。

扩批新增：人物顾一帆/白桦/祁霖/温以宁/阮秋/岑野/宋知远/贺清言/洛之衡/薛映（char_2xx）；地点灰墙巷/洗砚池/南渡口/旧灯房/竹径/断碑崖（loc_2xx）；任务 goal 把信笺送去洗砚池/更换旧灯房的灯油/修补灰墙巷的路面/抄录断碑崖的铭文/给竹径立一块木牌/打捞洗砚池的木匣（task_2xx）；外貌描述与人格描述词表见 `build_expansion.py`。

时长取自 `n4_render.num_cn`（唯一数字格式器，1–99）：2/5/6/15/20/30/45 分钟与 90 分钟（渲染为“两/五/六/十五/二十/三十/四十五分钟”“一小时”）；识别器 `cn_to_int` 反向解析“两”=2。构造器断言新词表与 dedup cast 集合零交。

## 4. 改写重叠率（复核信号，非硬门）

- **遮蔽单列**：人名、数值＋单位、任务引语「」三类先替换为占位符 ⟨N⟩/⟨V⟩/⟨Q⟩——它们本来就应原样保留（引语逐字、人名一致、数值与计划一致由校验器按忠实性单独核对），不计入重叠率。
- **算法**：字符 2-gram 集合重合率 = |bigrams(rewrite_masked) ∩ bigrams(seed_masked)| ÷ |bigrams(rewrite_masked)|，分母=改写行。同组 template-seed 行为种子基线。
- **用途**：ratio > 0.6 的行标 `review-flag`（人工看是否真的改写了），**不因此失败**；低于阈值不构成质量证明，只是不再触发复核。该比值由 `corpus_check.py` 运行时计算并打印，**不写回语料行**。
- 防照抄机制=重叠率信号＋校验器逐类忠实核对＋协调人抽验三层。

## 5. 校验器逐类核对（corpus_check.py，v5 识别器白名单）

**判定模型：pass 只覆盖被受控识别模式完整识别且与计划一致的表达；任何未识别残句（无依据细节、否定、意图、换人物、错数值、新增事件）一律 needs-review，needs-review 不算事实通过。** v4 起按**句**计算覆盖（不再按逗号切段），标点视为分隔符不计入残句；移动识别器允许起点与终点之间有一个可选逗号，因此「X离开了A，抵达了B」是可识别的同一事实，而「X离开了A。」（未述终点）仍是 needs-review。语料 schema v3：行携带独立构造的 `world`（before 注册表）与 `rawDelta`，`plan` 为同一生成器对 Δ 的投影（同源保证）；`planOnlyClaims` 承载非 Δ 计划条目。哈希覆盖 plan/fullPlan/world/rawDelta/text；组级一致性含 world/rawDelta/planOnlyClaims；v5 另断言同组 expressed/omitted 两份计划除时间条目外事实完全一致。**负例自检 19 例**（口径类 fail 2 例、review 17 例：越界/漏覆盖/方向反转/人物交换/数值错/任务否定/新增事件/无依据细节/否定移动/意图冒充/否定空点/完成人物不符/半截移动等）**＋可控等价 3 例**（外貌变体、已在变体、分行移动变体）必须以预期判定类通过，否则报告作废（exit 2）。

## 6. 权威验证（validate_plan_authority.py，v2 apply 来源核对）

格式合法之外证明**事实来源合法**（复核轮 2 要求）。三阶段：①行 `world` 构造 before `WorldState`（pydantic 含 fixed_registry 一致性）；②**before 层来源核对**——moved 起点==注册表 home、sanity 旧值==注册表理智（−999 类必炸）、任务 goal 必须是该人物注册任务且 owner 一致且仍 pending、positioned 现状==before 位置、no_change 行 Δ 必须为空；③**A 侧 kernel `apply_point`** 把 rawDelta 应用到 before（KernelViolation=非法），after 核对（位置/理智/任务 achieved）。脚本以 `--server-tree` 钉 A 工作树（默认 `.local/world-server-worktree`），报告含 server HEAD＋apply.py sha256，逐行绑定 plan+world+rawDelta 组合哈希。

## 7. 规模与构造顺序

首批（已冻结）为 30 个源组（24 train＋6 dev），组内两种时间表达（expressed/omitted）×（模板种子＋改写）＝每组 4 行。复核轮 11 的扩批规模：

- `small`：60 个 train 源（24 既有＋36 新）；
- `large`：120 个 train 源（包含 small 全部）；
- `fixed-dev`：30 个 dev 源（6 既有＋24 新）。

时长池按 split 分离：train 使用 2/5/6/15/20/30/45/90 分钟，新增 dev 使用 1/4/7/10 分钟（基础组冻结值不变）。跨 split 输入豁免**仅限省略时间后的原子 `no_change`**（plan == [no_change]，唯一渲染为“无变化”）；含时间的空点（time＋no_change）可由时长区分，不豁免，dev 不得复用 train 输入。

合计 150 组 / 600 行（seed 300＋rewrite 300）。构造顺序：`build_seeds.py` 生成基础 60 行 → `build_expansion.py` 追加扩批行（非幂等，已存在 `n4x-*` 行即中止）。扩批构造时断言：world/rawDelta/fullPlan 组合签名在**含既有组在内**的全组集合唯一（既有组自身重复只登记不篡改）；每行训练输入可由 `n4_render.render_input` 渲染；train/dev 渲染输入（no_change 除外）双向不相交；槽位按族计数器分配，与全局循环下标解耦。语料清单（§1–§6、§8 全部可见）仍先交协调人抽验，通过后才开微调；微调开工时的 tokenizer legacy 决策见方案表 §6（训练/评估/基线统一设置并重新验证）。

## 8. 复核轮 11 当前结果（2026-10-29）

| 工具 | 命令 | 结果 |
| --- | --- | --- |
| 行校验 | `python experiments/world-components/n4_corpus/corpus_check.py` | 自检 19 负例＋3 等价通过；150/150 组一致；**600 pass / 0 needs-review / 0 fail** |
| 去重 | `python .../dedup_check.py corpus.seeds.jsonl rewrites.jsonl` | 探针自检通过；**600/600 行在清单范围与规则下零命中**；cast 词零命中 |
| 权威核对 | `python .../validate_plan_authority.py` | 篡改矩阵 14/14；**全部 plan 经 A 侧 kernel apply 来源合法**；报告钉 server HEAD `4e17025`、apply.py `e626fdbb0679ca0c` |

已登记、未修改的冻结既有回归项：base 组签名重复 1 对（`n4-empty-009`/`n4-empty-027`）；既有 train/dev 共享渲染输入 1 对（`n4-task-014`/`n4-task-026`）；no_change 渲染输入跨 split 共享 6 个（空点的唯一渲染形态）。扩批组不产生新的跨 split 输入冲突。**本批只声明语料构造与校验结果；未在此 600 行语料上重跑微调/评估，质量结论不在此处。**

> 本节是复核轮 11 当时的口径与记录；轮 12 把 no_change 豁免收窄为原子 `no_change`，所以上面的“6 个共享输入”不再描述当前文件，当前计数与两档结果统一见 §9（校验表结果不变）。

## 9. 复核轮 12（2026-10-29）

**语料修正**：上一版把所有含 no_change 的计划都当豁免，导致 4 个新增含时间空点 dev 输入与 train 重合（如 `n4x-d101-empty` 与 `n4x-t001-empty` 同为“两分钟＋无变化”）。现改为：豁免只限原子 `no_change`；新增 dev 使用独立时长池 1/4/7/10 分钟。重建后校验：行校验 600 pass（19 负例＋3 等价自检）、去重 600/600 零命中、权威核对 0 错误（server `4e17025`、apply `e626fdbb`）。

**分母口径**：dev 120 行按渲染输入归并为 **56 个独立输入**；其中 3 个在 train 出现过（原子“无变化”；冻结 `n4-empty-009/027` 的 25 分钟空点；冻结 `n4-task-014/026` 的任务达成），列为 regression 并局部退出泛化分母；**未见输入 53 个**。评估脚本已改为每独立输入只生成一次，unseen/regression 分栏统计。

**两档入口**：`train_n4_sentence.py --tier small|large --run-tag r2-small|r2-large`，两档均 360 优化步（batch 8、lr 1e-4、seed 20261029）；small＝60 组/240 行（12 epochs）、large＝120 组/480 行（6 epochs）；checkpoint 与报告按 tag 分路径。

**原始结果（识别器三态）**：

| 档 | unseen 输入 | unseen pass/review/fail | regression pass/review/fail |
| --- | --- | --- | --- |
| r2-small | 53 | 45 / 8 / 0 | 3 / 0 / 0 |
| r2-large | 53 | 50 / 3 / 0 | 3 / 0 / 0 |

大档相对小档：**7 个未见输入改善、2 个倒退，净增 5 个通过**（43 个两档同过、1 个两档同 review）。零样本 base 臂在全部输入上均为 review（输出回显事实行），仅作对照。

**人工复核（协调人，2026-10-29）**：原始 `review` 保留，裁决如下——

- 小档 8 条 review 均为“下降写成上升”（10→8、10→7、11→8、14→11 却写“升到了”）。
- 大档 3 条并非全是下降写成上升：

| 输入 | 确认的事实错误 |
| --- | --- |
| `n4x-d109-chain`（有／无时间两条） | 12→15（上升），却写“降到了15” |
| `n4x-d115-chain`（无时间一条） | 11→8（下降），却写“升到了8” |

三条均标“确认方向错误”。抽验通过项基本通顺、偏模板；两档在省略时间的未见输入上均未擅自补时间。**协调人裁定：两档对照试验可验收，N4 模型质量未通过。**

**耗时口径更正**：首跑记录的 unseen meanWall（0.83s / 2.37s）未复现。协调人交错重放两个模型、以 CUDA 同步计时，两档生成均值 **1.206s / 1.205s**，对应 **21.51 / 21.43 tokens**；首跑差异不作为固有性能差异，两档比较以重放值为准（归档 JSON 的逐输入 wallSeconds 仍是首跑单次测量）。

归档：`artifacts/world-components/n4-finetune-{train,eval}-r2-small.json`、`-r2-large.json`。

## 10. 复核轮 13 单变量方向实验（2026-10-29）

**唯一变量**：共享渲染器 `n4_render.render_entry` 的理智行由 `理智：{name} {from}→{to}` 改为附加程序计算的 `（上升／下降／不变）`。语料文件、基座（Randeng-T5-77M）、大档数据（120 组/480 行）、360 优化步、batch 8、lr 1e-4、seed 20261029 均不变。核验：53 个未见输入中仅 10 个 chain 输入（5 个 dev chain 组 × 有/无时间）字节变化，其余 43 个输入逐字节相同。

**新增检查**：`corpus_check` v5 与构造器都断言“同一组的有时间／无时间两份计划除时间条目外事实完全一致”，150/150 组通过；行校验 600 pass（19＋3 自检）、去重 600/600 零命中、权威核对 0 错误（语料未改，报告沿用轮 12 重建后的结果）。

**结果（识别器三态，仅证据，不作质量结论）**：

| 臂 | unseen 53 | regression 3 |
| --- | --- | --- |
| r2-large（方向不显式） | 50 pass / 3 review / 0 fail | 3 pass |
| r3-direction（方向显式） | **53 pass / 0 review / 0 fail** | 3 pass |

相对 r2-large：50 个原本通过的输入保持通过，已知的 3 个方向错误输入（`d109` 有/无时间、`d115` 无时间）全部转为通过，无其他输入改善或倒退。零样本 base 臂仍全 review。归档：`artifacts/world-components/n4-finetune-{train,eval}-r3-direction.json`。

**未做**：小档不重跑（单变量对照只针对大档）；耗时未按交错重放口径重测；人工抽验与质量门结论仍待后续。**本轮不宣布 N4 质量通过**；渲染器方向提示是否保留，待协调人复核后决定。

## 11. 独立留出验收（2026-10-29，冻结 r3-direction）

**冻结清单**：`experiments/world-components/n4_holdout/freeze-r3-direction.json`，在验收前固定并逐项校验哈希：r3-direction 检查点（7 文件）、基座、共享渲染器 `n4_render.py`、判据 `corpus_check.py`、600 行语料、留出集与权威报告、解码设置（greedy、max_new_tokens=64、legacy=False）。验收脚本发现任何一项不符即中止，不会静默换件重跑。

**留出集**：`experiments/world-components/n4_holdout/holdout.jsonl`，24 组 / 48 行 / 45 个独立输入。人物、地点、任务、外貌、人格均为新词表，时长取自与语料不相交的池子；与训练/开发语料零输入重合；只有省略时间后的原子“无变化”输入必然共享，作为 1 个回归项单列（4 行合 1 输入），不计入未见分母。留出集校验：行校验 648 pass（600 语料＋48 留出，19＋3 自检）、去重 48/48 零命中、权威核对 0 错误（server `4e17025`、apply `e626fdbb`）、174/174 组一致。**时长覆盖（复核轮 15 更正）**：构造器定义了八档时长 9/11/13/18/22/35/50/75 分钟，但每族只取前四档，所以本次冻结留出集**实际只覆盖 9/11/13/18 分钟**（每档 6 行）；22/35/50/75 未被使用。此前本节与汇报误写为八档全覆盖，现更正。按复核要求**保留冻结数据、不为补覆盖而改动本次留出集**；未来新留出集应让时长下标跨族推进。构造器未改生成逻辑，重跑 `build_holdout.py` 仍逐字节复现同一文件（sha256 `a9323e03…`）。

留出集构造一次后冻结，未据模型输出改动。校验命令：`corpus_check.py corpus.seeds.jsonl rewrites.jsonl holdout.jsonl`、`dedup_check.py holdout.jsonl`、`validate_plan_authority.py --rows holdout.jsonl --report holdout-authority-report.json`。

**预登记验收规则**：每个未见留出输入由冻结判据判定，verdict 必须为 pass；任何 review/fail 即本次留出验收不通过；不重生、不回退、不改判据；一次贪心解码。共享回归输入不参与未见分母。

**一次运行结果（2026-10-29）**：

| 臂 | 未见 44 | 共享回归 1 |
| --- | --- | --- |
| r3-direction | **44 pass / 0 review / 0 fail** | 1 pass |
| base（零样本） | 0 pass / 44 review | 0 pass / 1 review |

自动规则结果：**met**（44/44 未见输入通过）。归档：`artifacts/world-components/n4-holdout-eval-r3-direction.json`。复跑命令：`eval_n4_finetune.py --run-tag r3-direction --holdout experiments/world-components/n4_holdout/holdout.jsonl --freeze experiments/world-components/n4_holdout/freeze-r3-direction.json`。

**边界**：这是冻结设置下的一次独立留出结果，不追溯改写开发批 53 项的证据地位；整体质量门是否关闭由协调人裁定，本文不代替签字。

## 12. 复核轮 15–16 工程收口（2026-10-29）

不做重训、不重跑留出验收，只补两项检查与一处文档更正。

**1. 冻结校验补齐。** `eval_n4_finetune.py` 的 `verify_freeze` 原先漏验两项、也未核对解码配置。现在逐项比对 9 个钉定对象与运行期解码设置：

| 检查项 | 内容 |
| --- | --- |
| 渲染器 / 判据 | `n4_render.py`、`corpus_check.py` sha256 |
| 留出集 / 其权威报告 | `holdout.jsonl`、`holdout-authority-report.json` sha256 |
| 语料 | `corpus.seeds.jsonl`、`rewrites.jsonl` sha256 |
| **训练报告** | `n4-finetune-train-r3-direction.json` sha256（本轮新增） |
| 检查点 / 基座 | 目录内逐文件 sha256_16 |
| **解码配置** | 运行期 greedy/maxNewTokens/numBeams/tokenizerLegacy 与冻结清单**全等**（本轮新增） |

**篡改自检 13 例**：上述每个钉定值各改一次、解码四项各改一次，必须全部被捕获；未改动的清单必须通过。不通过则中止（exit 2）。核对方式只读，不改冻结文件、不写回清单。

**验证方式**：`eval_n4_finetune.py --run-tag r3-direction --holdout …/holdout.jsonl --freeze …/freeze-r3-direction.json --verify-only`。该模式只跑冻结校验与自检、**不执行推理**，输出 `artifacts/world-components/n4-holdout-freeze-verify-r3-direction.json`；既有接受结果仍以 `n4-holdout-eval-r3-direction.json` 为准，未重跑。本轮实测：自检 13/13 通过、9 项与解码全等、留出结构 48 行 / 45 输入（44 未见 + 1 共享回归）。

**端到端篡改演示**（改清单副本、不动冻结文件）：把 `trainingReport.file` 指向 r2-large 报告 → `FREEZE MISMATCH trainingReport`；把 `decode.maxNewTokens` 改为 32 → `FREEZE MISMATCH decode: runtime={…64…} frozen={…32…}`；把 `holdout.authorityReport.file` 指向语料报告 → `FREEZE MISMATCH holdout.authorityReport`。三例均在推理前中止（exit 2）。校验顺序为先验真清单、再跑自检，避免篡改清单被自检信息掩盖。

**2. 时长覆盖更正。** 见 §11 的“时长覆盖”段：冻结留出集实际只覆盖 9/11/13/18 分钟，22/35/50/75 未被使用；构造器新增打印实际使用档位与未用档位，数据未改（重跑仍复现 sha256 `a9323e03…`）。

**3. 复核轮 16：配置单一来源与入口守卫。** 此前 `DECODE` 只用于冻结比对，而生成走独立的 `MAX_NEW`、tokenizer 硬编码 `legacy=False`，因此改 `MAX_NEW=32` 仍能通过冻结检查（协调人实测）。现做法：删除 `MAX_NEW` 等重复常量，只保留一个 `DECODE` 字典；冻结比对、tokenizer 构造、`generate()`（`max_new_tokens`/`num_beams`/`do_sample`）与报告四处**全部读取同一字典**，不再有第二份。验证：把 `DECODE["maxNewTokens"]` 改成 32、把 `tokenizerLegacy` 改成 True 各跑一次 `--verify-only`，均报 `FREEZE MISMATCH decode` 并在推理前退出。报告里的 `tokenizer.legacy` 也不再写死，改为读 `DECODE["tokenizerLegacy"]`；`--verify-only` 输出同样回显该值，便于不跑推理就核对生效配置。另修入口：`--holdout` 与 `--freeze` 必须成对出现（任一缺失即退出），`--verify-only` 缺任一参数也立即退出；参数解析移到 torch/transformers 导入之前，所以漏参数不会进入开发批推理（协调人实测原先会进入）。四种漏参组合均已实测退出。

**4. 协调人验收结论（2026-10-29，复核轮 17）。** 两处 `tokenizer.legacy` 均读 `DECODE`；冻结三件套与原验收报告哈希未变；44/44 离线验收结论保持通过。**本批工程收口完成，可进入工程接入。** 训练侧 `train_n4_sentence.py` 保持已验证的 `legacy=False`（r3 冻结产物的一部分，未改）；训练/评测配置统一留到未来新训练轮处理。本轮未重跑模型、未改写归档。
