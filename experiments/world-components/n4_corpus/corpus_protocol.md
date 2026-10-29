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

## 5. 校验器逐类核对（corpus_check.py，v4 识别器白名单）

**判定模型：pass 只覆盖被受控识别模式完整识别且与计划一致的表达；任何未识别残句（无依据细节、否定、意图、换人物、错数值、新增事件）一律 needs-review，needs-review 不算事实通过。** v4 起按**句**计算覆盖（不再按逗号切段），标点视为分隔符不计入残句；移动识别器允许起点与终点之间有一个可选逗号，因此「X离开了A，抵达了B」是可识别的同一事实，而「X离开了A。」（未述终点）仍是 needs-review。语料 schema v3：行携带独立构造的 `world`（before 注册表）与 `rawDelta`，`plan` 为同一生成器对 Δ 的投影（同源保证）；`planOnlyClaims` 承载非 Δ 计划条目。哈希覆盖 plan/fullPlan/world/rawDelta/text；组级一致性含 world/rawDelta/planOnlyClaims。**负例自检 19 例**（口径类 fail 2 例、review 17 例：越界/漏覆盖/方向反转/人物交换/数值错/任务否定/新增事件/无依据细节/否定移动/意图冒充/否定空点/完成人物不符/半截移动等）**＋可控等价 3 例**（外貌变体、已在变体、分行移动变体）必须以预期判定类通过，否则报告作废（exit 2）。

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

**原始结果（识别器三态，仅证据，不作质量判定）**：

| 档 | unseen 输入 | unseen pass/review/fail | regression pass/review/fail | unseen meanWall |
| --- | --- | --- | --- | --- |
| r2-small | 53 | 45 / 8 / 0 | 3 / 0 / 0 | 0.83s |
| r2-large | 53 | 50 / 3 / 0 | 3 / 0 / 0 | 2.37s |

零样本 base 臂在全部输入上均为 review（输出回显事实行），仅作对照。8/3 个 review 全部是 chain 组的精神值方向词（下行却写“升到了”），被识别器按方向核对拦下，未判 fail。归档：`artifacts/world-components/n4-finetune-{train,eval}-r2-small.json`、`-r2-large.json`。**人工抽验与质量门结论仍待后续，不用本轮数字宣布通过。**
