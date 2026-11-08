# C7 完整叙事离线组合（round_composition）

日期：2026-11-08。分支 `exp/c-round-composition`，父提交 `6440534`。独占目录：本目录。

- **支持哪条 R：** R11（叙事拆分与组合）。次要涉及 R02/R03（事实来源与约束）、R12/R13（表达纪律）。
- **当前档位：** **有实验结果**——组合接线与程序判定可复跑；**不是**「已接线」，因为选择/组织/成句三步仍是脚本模拟端口，没接生产路由、没接真模型。
- **这份证据能证明什么：** 冻结的 N1/N2/N3/N4.0/N5 接口能被串起来；每个事实能追到 `entityId`+字段路径；模块失败、N5 拒绝、重试和回退都有显式状态；同样输入两次跑结果一致（去掉计时字段后逐字节相同）。
- **这份证据不能证明什么：** 任何模型能力。19 个场景里的「正文」全是 `fixtures/mocks.json` 里手写的脚本字符串，不是模型输出。这里没有任何 N4 成句质量、N5 语义复核或浏览器耗时的结论。

## 1. 复跑

```bash
# 在 worktree 根目录（.local/parallel/c-round-composition）
RC=experiments/world-components/parallel/round_composition
python -X utf8 $RC/make_fixtures.py     # 由登记的已提交状态生成 19 个输入点
python -X utf8 $RC/compose.py           # 跑组合，写 out/composition-run.json
python -X utf8 $RC/check_determinism.py # 跑两遍比对（去掉计时字段）
python -X utf8 $RC/contract_probes.py   # 两个契约冲突的定点探针（不重跑组合）
# 裁决后的新版本（D1/D2/D5 生效，旧 v2 不动）
python -X utf8 $RC/test_judge_v3.py      # judge_v3 单元检查（D1-D5 各一组断言）
python -X utf8 $RC/make_v3_fixtures.py   # D1/D5 样本（7 例，含反例）
python -X utf8 $RC/compose_v3.py         # 26 例在 n5-v3 下重跑，写 out/composition-v3-run.json
python -X utf8 $RC/record_manifest.py    # 记录输入/输出哈希、N5 门覆盖与 git 身份
```

`compose.py` 退出码 0 表示 19 个场景的实际状态全部等于预期状态。环境：Python 3.11.15，Windows 10，只用 CPU，无模型加载。

## 2. 机制：一个场景里，谁给谁什么

组合器按固定顺序把同一个场景过一遍。每次交接的数据和落点如下（全部写进 `out/composition-run.json` 的 `cases[].stages`）：

| 步骤 | 谁做 | 拿到什么 | 产出什么 | 检查什么 | 归档字段 |
| --- | --- | --- | --- | --- | --- |
| 视角 | 程序 `n2_perspective.resolve_perspective` | 目标点状态 + 调用方要的视角 | 解析后的视角（主体、地点链） | 主体必须在册，位置必须能解析，否则 `incomplete` | `stages.perspective` |
| N1 事实提取 | 程序 `narration_pipeline.extract_facts` | 目标点状态、前驱点、原始 `entityDeltas`、`timeAdvance` | 事实条目（`factId/kind/entityId/来源字段/at/atPath`） | 有阻断性诊断就停（`incomplete`） | `stages.n1.facts` |
| N2 内容选择 | **模拟端口** + 程序校验 | N1 全部事实、视角、`mayPolicy`、`visibleOtherActions` | `selectedFactIds` | 未知 id、漏必述、选了不可见、空选择 → `stopped-at-selection`。同时把程序规则（must/may/invisible 及理由）完整存档 | `stages.selection` |
| N3 组织表达 | **模拟端口** + 程序不变量 | 已选事实、名字表、性别提示 | 窄计划 `sentences[{index,factIds,coreference,time}]` | `check_plan_v3`：覆盖一致、引用存在、无名同组、时间归属、称谓授权 → 否则 `stopped-at-organization` | `stages.organization` |
| 场景上下文 | 程序 `build_scene_context` | 状态、视角、已选事实、显式环境 overlay | 场景（地点链、人物、可见物）、世界视图 | 主体/地点可解析；缺环境字段记诊断不编造 | `stages.scene` |
| N4.0 输入装配 | 程序 `pack_narrative_input` | 已选事实、计划、场景、世界视图 | 结构化记录文本（场景/人物/可见/事实/分组/视角/要求） | fail-closed：计划与选集不符、未知 kind、缺 `resultText`、缺字段 → `stopped-at-input` | `stages.n4Input.input` |
| N4 成句 | **模拟端口** | N4.0 文本 + 上一次的失败原因 | 正文候选、结束原因；端口故障抛错 | 空文本单列 | `stages.n4n5.attempts[]` |
| N5 核对 | 程序 `eval_n4_v2.judge_row` | 计划、已选事实、正文、结束原因 | 硬门结果与问题列表 | 每次都跑：G1 必述覆盖、G2 残留人名/目标、G3 时间精确值、G6 未截断。G4 只在 `rowId` 含 `conflict` 时跑、G5 只在含 `same-name` 时跑（触发靠案例命名，见 D5） | `stages.n4n5.attempts[].n5` |
| 回退 | 程序模板 | 已选事实（仅限模板支持的 kind） | 模板正文 + 它的 N5 结果 | 回退正文单独记录，**不改变失败状态** | `stages.fallback` |
| 交叉核对 | 程序 `verify_text → corpus_check` | 最后一次正文 | v7 识别器的 fails/reviews | 只记录，不参与判定 | `stages.n5CrossCheck` |

事实溯源写在 `cases[].facts[]`：每条事实带 `factId`、`kind`、`entityId`、`source`（哪个实体的哪个字段）、`at`/`atPath`（在哪个地点）、`planGroups`（被 N3 分到第几组）、`n5Covered`（N5 是否认到正文里的对应表达）。

## 3. 一个场景从头走到尾（normal-move-task）

1. **输入（`fixtures/cases.json`）**：`point.entityDeltas = {char_pa: {positionSet: {containerId: loc_2}, tasksAchieved: ["task_1"]}}`，`point.state` 里管线甲已在钟楼、`task_1` 已达成；`before` 是前驱点。视角 `{type: protagonist}`。
2. **N1** 产出两条事实：`f0` 移动（`source={entityId:char_pa, field:positionSet}`，`at=钟楼`），`f1` 任务达成（`source={entityId:char_pa, taskId:task_1}`）。无诊断。
3. **N2 模拟端口**只回 `["f0","f1"]`；程序规则核对：两条都是 `must`（`self-position`、`self-task`），选集没有漏必述、没有多余 id。
4. **N3 模拟端口**回 `G1｜f0 f1`；`check_plan_v3` 通过（id 集合一致、无称谓、时间空）。
5. **场景**：地点链 `钟楼`，人物只有视角主体，可见物为空；环境来自本场景显式给的 overlay。
6. **N4.0** 组装出的文本（原样，来自归档）：

```text
叙事任务。
场景：
地点=钟楼
地点外貌=旧；细雨；傍晚；高；昏暗；海雾贴着塔壁
人物：
管线甲｜性格=沉稳｜外貌=常态｜随身=无
可见：
无
事实：
f0｜移动｜管线甲｜管线镇→钟楼
f1｜任务达成｜管线甲｜把铜铃挂回钟楼
分组：
G1｜f0 f1
视角：管线甲；第三人称限知；只写管线甲的内心，他人只写可见动作。
要求：写场景、行动与视角人物心理；不写任务标题、数值面板、具体时长、字段名；不新增未列出的具名人物/物品/地点；他人只写可见动作。
正文：
```

7. **N4 模拟端口**回一句脚本正文：`管线甲从管线镇来到了钟楼。管线甲完成了任务「把铜铃挂回钟楼」。`
8. **N5**：`G1/G2/G3/G6` 全 true，`covered=[f0,f1]`，无问题 → 状态 `ok`。
9. **落点**：`out/composition-run.json` 里 `cases[0].stages` 保存上面每步的完整请求、响应、校验、耗时；`cases[0].facts` 保存两条事实的来源与覆盖。

## 4. 19 个场景与结果

`expect` 是开跑前写死的预期；`实际` 是本次结果；`重试` 是成句端口的重跑次数（预算 2 次）；`回退` 指模板回退是否产出正文。

| 场景 | 触发路径 | expect | 实际 | 重试 | 回退 |
| --- | --- | --- | --- | --- | --- |
| normal-move-task | 正常：移动 + 任务达成 | ok | ok | 0 | 关 |
| normal-two-actors | 正常：他人同地可见移动（`visibleOtherActions`） | ok | ok | 0 | 关 |
| normal-inner-change | 正常：外貌 + 个性 + 理智 | ok | ok | 0 | 关 |
| retry-n5-success | 第 1 次漏必述，第 2 次补齐 | ok | ok | 1 | 关 |
| fail-n1-unregistered | N1：增量指向未注册实体 | incomplete | incomplete | 0 | — |
| fail-perspective | 视角：主体不在册 | incomplete | incomplete | 0 | — |
| fail-n2-invalid | N2：选了不存在的 factId | stopped-at-selection | stopped-at-selection | 0 | — |
| fail-n2-missing-must | N2：漏掉必述 | stopped-at-selection | stopped-at-selection | 0 | — |
| fail-n2-empty | N2：空选择 | stopped-at-selection | stopped-at-selection | 0 | — |
| fail-n2-invisible | N2：选了不可见事实（他人在别处完成非在追任务） | stopped-at-selection | stopped-at-selection | 0 | — |
| fail-n3-coverage | N3：计划漏一条已选事实 | stopped-at-organization | stopped-at-organization | 0 | — |
| fail-n3-unknown | N3：计划引用不存在的 factId | stopped-at-organization | stopped-at-organization | 0 | — |
| reject-n5 | 两次都过不了硬门（第 2 次截断） | n5-rejected | n5-rejected | 1 | 有（模板过门） |
| fail-n5-extra-actor | 正文多写一句已登记人物的动作 | n5-rejected | n5-rejected | 1 | 有（模板过门） |
| fail-sentence-port | 成句端口两次都超时 | sentence-port-failed | sentence-port-failed | 1 | 有（模板过门） |
| fail-sentence-empty | 成句返回空字符串 | empty-output | empty-output | 1 | 有（模板过门） |
| contract-time-conflict | N4.0 模糊时间 vs N5 精确时间 | n5-rejected | n5-rejected | 1 | 关（刻意禁用） |
| n5-false-pass-unregistered-actor | 新增具名人物，N5 硬门未覆盖 | n5-false-pass | n5-false-pass | 0 | 关（刻意禁用） |
| fallback-unsupported-kind | 新任务类型无模板帧 | n5-rejected | n5-rejected | 1 | 无（记 `template-unsupported-kind`） |

汇总（归档 `summary`）：19/19 符合预期；状态分布 `ok 4 / incomplete 2 / stopped-at-selection 4 / stopped-at-organization 2 / n5-rejected 4 / empty-output 1 / sentence-port-failed 1 / n5-false-pass 1`；重试 7 个场景；模板回退实际产出正文 4 次。

组合器自身耗时（不含任何模型推理，模拟端口立即返回）：均值 0.9 ms，中位 0.5 ms，最大 3.3 ms/场景。这个数字只说明程序开销可以忽略，**不能**用来对比模型耗时。

两次运行的确定性：`out/determinism.json` 记录去掉 `runAt`、`timings`、各阶段 `ms` 后两次归档逐字节相同。

## 5. 已证明 / 已失败 / 无法判断

**已证明（本实验范围内）**
1. 冻结接口能串成一条链：N1 程序事实 → N2 选集校验 → N3 计划不变量 → 场景 + N4.0 结构化输入 → 成句端口 → N5 硬门 → 回退。
2. 每个事实都能追到实体、字段路径、地点链，并被标记进哪个句组、N5 是否认到它（`cases[].facts`）。
3. 七类失败状态都能停在正确的步骤上，且都不会被写成 `ok`：N1 阻断、视角不可解析、选集三层校验、计划两层不变量、端口故障、空文本、N5 拒绝。
4. 成句重跑预算、回退记录、回退不影响状态这三件事成立；回退正文即便过 N5，场景状态仍是失败。
5. 同一输入两次跑结果一致（去掉计时字段）。
6. N5 硬门确实在判：`reject-n5`、`fail-n5-extra-actor`、`contract-time-conflict` 三例的脚本正文都被拒，说明 `ok` 不是恒真。

**已失败（本实验暴露的问题）**
1. **任务标题契约冲突（已按 D1=C 在新版本解决）。** N4.0 的要求行写着「不写任务标题」，但 v2 N5 对任务类事实只有一种帧：`完成任务「目标原文」`。照 N4.0 写（把结果写成动作）必然挂 G1；照 N5 写就违反 N4.0。定点探针：`out/contract-probes.json` 的 `task-title-quoted`（pass）与 `task-title-paraphrased`（`uncovered:f1:task_achieved`）。4 个 `ok` 场景里含任务类事实的是 `normal-move-task` 与 `retry-n5-success`，这两个都选了后者（写标题）。另一条更自然的路（改成结果表述 `outcome` + `resultText`）今天也走不通：判定器对它直接抛 `no v2 pattern for kind outcome`（`out/contract-probes.json` → `outcome-kind-unsupported`，`pass=null`）。登记为 D1。
2. **两套 N5 程序核不一致。** 本组合用 v2 对齐器（`eval_n4_v2.judge_row`）。同一批正文再用 v7 识别器（`corpus_check.check_narration`，`verify_text` 调用）看：`reject-n5` 第 2 次截断文本 `fails=[] reviews=0`（v7 没有截断规则），`fail-n5-extra-actor` 的残留人名只算 review，不算 fail。也就是说，「N5 拒绝」目前取决于用哪套核。
3. **时间契约冲突。** N4.0 契约明确要求时间只模糊表达、不写具体时长；v2 N5 的 G3 要求正文出现计划里的精确数值。照 N4.0 写的合规文本（`…过了一会儿。`）必然挂 G3（`uncovered:f2:time`）。本实验没有放宽任何门，只把这个冲突固定成一个场景。**该冲突已按 D2=A 在新版本 `n5-v3` 中解决（见第 7 节），v2 归档保留原状。**
4. **N5 不硬拒新增具名人物。** v2 G2 只扫 `facts` 里已登记的人名和任务目标，新出现的名字（`管线丙`）不在扫描范围；v7 核也只给 review。本场景靠夹具自带的 `annotations.addsUnregisteredEntity` 才标成 `n5-false-pass`，不是判定器自己发现的。

**无法判断**
1. 模型能力：选择、组织、成句三步都是脚本。这里没有任何一条能说明真模型能不能做这几件事。
2. N5 语义复核：本次完全没跑（`semanticReview: not-run`）。硬门通过不等于语义正确。
3. **G4 只是意外触发，G5 没有执行。** 两个门都由 `rowId` 子串触发：`contract-time-conflict` 的 caseId 含 `conflict`，于是 G4 在它的两次尝试上各跑了一次，结果都是 `true`；但该案例只有一个人物（两条事实都是管线甲），G4 走的是「同一名字多次出现」分支 `text.count(名字) >= 2`，**不是**真正的双人冲突，所以这次 `true` 不构成对 G4 的验证。19 个场景里没有 caseId 含 `same-name`，`G5_same_name_bare` 一次都没执行。逐门的执行次数、涉及案例与取值全部由归档实测写进 `fixtures/manifest.json` 的 `n5GateCoverage`（不是手填）。
4. 输入长度/真实 token：本工作树没有 checkpoint，无法重算 token；模拟端口吃文本，所以也没有 N4 的 token 门。N4.0 结构输入的历史量级（287–390 tokens）来自归档 `n4-input-packing-r1.json`，不是本次实测。

## 6. 契约裁决项

上面暴露的四处冲突（任务标题、时间精确度、两套 N5 核、新增具名人物）加一处门控问题（G4/G5 靠 caseId 触发），逐条登记在 [contract-decisions.md](contract-decisions.md)：契约原文、证据指向哪个文件的哪个字段、现在会怎样、选项与代价、**一条建议（不是决定）**、若选建议项要改什么/重跑什么、验收判据。该文件还含真模型实验前的四条门槛和一张待填的裁决记录表。

| 编号 | 冲突 | 现在的后果 | 证据 |
| --- | --- | --- | --- |
| D1 | N4.0「不写任务标题」 vs N5 要求 `完成任务「目标」` | 任务类事实写标题才过门，不写就挂 G1；改成结果表述则判定器无帧可判 | `out/contract-probes.json` `task-title-*`、`outcome-kind-unsupported`；`composition-run.json` `normal-move-task` |
| D2 | N4.0 强制模糊时间 vs N5 要求精确数值 | 含时间推进的点要么不过门，要么违反 N4.0 | `out/contract-probes.json` `time-*`；`contract-time-conflict` |
| D3 | 两套 N5 程序核口径不同 | 「N5 拒绝」取决于用哪套核 | `n5CrossCheck`（`reject-n5`、`fail-n5-extra-actor`） |
| D4 | 新增具名人物没有硬门 | 编造人物会被放行 | `n5-false-pass-unregistered-actor` |
| D5 | G4/G5 由 `rowId` 子串触发 | G4 意外触发一次（`true`），G5 从未跑 | `fixtures/manifest.json` `n5GateCoverage` |

本实验不裁决、不改门。

## 7. 裁决落地：N5 v3（新版本、新归档）

D1–D5 的裁决已经实施为一个**新的判定器**（`judge_v3.py`，版本 `n5-v3`），旧判定器与旧归档原样冻结。这一节只说 v3 做了什么、结果是什么、什么仍然不能证明。

**每条裁决对应的实现**

| 裁决 | 实现 | 归档里怎么看得出来 |
| --- | --- | --- |
| D1 C | `outcome` 事实按「主体 + resultText 原文」判覆盖；事实没有 resultText 时抛 `JudgeBlocked(outcome-result-missing)`，**不退回任务目标** | `d1-outcome-result` 硬门通过；`d1-outcome-judge-block` 状态 `blocked-at-judge`；`probesUnderV3` 的 `outcome-result-v3` 通过、`outcome-goal-quoted-v3` 被拒（`uncovered:f1:outcome` + `residue-goal`） |
| D2 A | 模糊表达（有词表）只有在**正文没有出现任何时长**时才算覆盖；出现时长就完整解析（符号、小数、半、几/数）与权威值比对，解析不了就失败；没有时间事实却写时长也失败 | `contract-time-conflict` 从 `n5-rejected` 变为 `n5-pass`，`time.vague=过了一会儿`；`probesUnderV3` 的 `time-exact` 仍通过 |
| D3 B | 硬门与语义分栏：`n5` 只放门结果，`n6` 单独记，`quality` 由 `quality()` 计算，N6 未跑时一律 `pending` | 26 例 `qualityPending=26`、`qualityPassed=0`；`n6.status=not-run` |
| D4 B | 未登记名来自人工标注文件；没标注时 `count=null`，标注过且干净才是 `0` | `d4Labeled=10`、`d4Positives=1`、`d4Unchecked=16`；标注挂在具体正文上（`d4.text`） |
| D5 C→A | G4/G5 改由数据触发（同名多实体 / 同名实体获授权）；判定器不接收 `rowId`；每个案例用两个假 rowId 各判一次并比对；**计划里的合法代词授权参与事实匹配**（同名实体的授权仍由 G5 拒绝） | `g4Triggered=2`、`g5Triggered=1`、`rowIdInvarianceFailures=0`；`d5-same-name-grant` 因 G5 被拒 |

**新增样本族（D5 要求的「先登记样本」）**

| 样本 | 构成 | 主文本 | 反例文本（要求被拒） |
| --- | --- | --- | --- |
| `d5-conflict-two-actors` | 两名不同名角色完成同一目标（`plan_v3` 合并成一组） | 两人都被点名 → 通过 | 只点一人 → 一人事实未覆盖 |
| `d5-same-name-actors` | 两个实体都叫「管线乙」，各自完成同一目标 | 每个名字各出现一次 → G4 触发且通过 | 只出现一次 → 覆盖 + G4 同时失败 |
| `d5-same-name-grant` | 同上，但计划被**篡改**，给同名实体授权代词 | — | 主文本即反例：G5 触发并失败 |
| `d5-control-single-actor` | 普通单人场景 | 通过 | —（对照：G4/G5 均不触发） |

**结果（`out/composition-v3-run.json`）**

28 例（19 原例 + 9 新例）全部落在预期：`n5-pass 12 / n5-rejected 4 / incomplete 3 / stopped-at-selection 4 / stopped-at-organization 2 / sentence-port-failed 1 / empty-output 1 / blocked-at-judge 1`；`qualityPending=28`、`qualityPassed=0`；`g4Triggered=2`、`g5Triggered=1`；`rowIdInvarianceFailures=0`；D4 标注 10 例、正例 1、未检查 18。

**复核补正（2026-11-08，第二轮复核提出的两个反例）**

| 问题 | 原来的行为 | 现在的行为 | 归档证据 |
| --- | --- | --- | --- |
| 时长只截取尾数 | `8.8分钟` 被读成 8 分钟通过；`负八分钟` 丢符号通过；`过了一会儿，八分半钟过去了` 没识别出时长，靠模糊表达通过；`几分钟` 也靠模糊表达通过 | 扫描完整表达式（符号、小数、中文数、半、几/数、时辰）；`8.8` → 8.8 与 8 不符、`负八分钟` → −8、`八分半钟` → 8.5，三者都判 `time-value-mismatch`；`几分钟` 判 `time-value-unparseable`；**只要出现时长就不再回退模糊表达** | `d2-time-value-strict` 主文本（约八分钟）通过，四条反例全部被拒，问题码写在归档里 |
| 合法代词授权被忽略 | 匹配时固定传 `pronoun=None`，同一移动事实 + 合法「他」授权，v2 通过、v3 报 `uncovered:f0:moved` | 从计划取每个实体的授权代词参与匹配（`他/她/TA`），同名实体的授权仍由 G5 拒绝 | `d2-pronoun-grant`：`他从管线镇来到了钟楼。` 通过；`…来到了桥头。` 仍被拒；`d5-same-name-grant` 仍因 G5 失败 |

两条都补了回归用例（`test_judge_v3.py` 的 `test_d2_regressions` 与 `test_pronoun_grant`），并且作为归档样本固定下来（`d2-time-value-strict`、`d2-pronoun-grant`）。

**v2 的同类弱点（冻结，不改）**：旧对齐器同样会把 `8.8分钟` 读成 `8分钟`、把 `负八分钟` 读成 `8分钟` 并放行（实测）。它不认模糊表达，所以 `八分半钟`、`几分钟` 反而会因缺精确值被拒。按「旧门冻结」的规则本次不动 v2；**引用 v2 的时间类结果时，不能把它当成「数值被严格核对」的证据**。

**确定性**：`check_determinism.py` 现在把 v2 与 v3 各跑两遍、去掉计时字段后逐字节比对，两节都是 `identicalAfterStrip=true`（`out/determinism.json`）。

**旧版本未被改动**：`out/composition-run.json` 仍是 `b594c008…`。为确认 v2 路径没有因为新增文件而改变，我另外跑了一遍 `compose.py --out out/_parity-v2.json` 并与冻结归档逐案比对（状态、每次尝试的硬门、问题列表、回退是否产出）——完全相同，临时文件已删除。

**已知的严格性代价**：任何时长表述都要对得上权威值，所以像「半天没动」这种习惯说法（视为 0.5 天）也会被判不符；模糊词表里收的是「半晌/一会儿/片刻」这类不含数值的说法。这是按裁决「出现时长必须核对」取的严格口径，如果真模型数据里误伤明显，需要另行裁决是否给固定的习惯说法开口子。

**仍然不能证明的**：正文全部是脚本字符串；N6 未执行，所以没有任何一条是质量通过；D4 只有一个标注者，漏报率算不出来（见 `human-review-v1.md`）。

## 8. 其他观察（不作缺陷断言）

- N4.0 把环境 overlay 的各字段值直接拼进「地点外貌」且不带字段名（`地点外貌=旧；细雨；傍晚；高；昏暗；海雾贴着塔壁`）。值写错时无法区分是地点原文还是 overlay；本实验的第一版夹具就因为给钟楼写了「巷子里全是湿气」而暴露这点，已改成与场景一致的值。生产该由场景/时间系统写入地点外貌（与 N4.0 文档的已知缺口一致）。
- `pack_narrative_input` 对 `time` 只写「时间经过」、组后统一写「过去了一会儿」，所以 N4 端看不到具体时长——这正是上面时间冲突的来源，也是契约有意的设计。
- N2 的模拟端口只回编号集合，所以本实验只能校验「不漏必述、不选不可见、不越界」，**没有**校验「该不该写」（显著性与省略）——那部分本来就是模型职责。

## 9. 交付物与哈希

| 文件 | 作用 | SHA-256 |
| --- | --- | --- |
| `compose.py` | 组合器（程序步骤 + 模拟端口 + N5 + 回退） | `0b4e359fa8e80516677c2a4450fdd2f6d13539f914bed06f703e4828c5bc9020` |
| `make_fixtures.py` | 由登记的已提交状态生成输入点 | `c155c002a9812787a01bf186bf8b3d7691d44d344b1f2e1baa0db5c99f802735` |
| `check_determinism.py` | v2/v3 各跑两遍比对（去掉计时字段） | `450eb7cea31e738750833ebd833b94ede792fd73fd95442a95897b54df78f424` |
| `record_manifest.py` | 记录输入/输出哈希、N5 门覆盖（从归档实测）与 git 身份 | `ca48d9dc00eaf896456aed3f881892df85bcaea785df9f9afcd6c6dcbfabb750` |
| `contract_probes.py` | 两个契约冲突的定点探针（读归档，不重跑组合） | `8c5925ae17f3fef597cf1f5a2a3bfe1d0275c639df2d06e73774ed5f7d4b355c` |
| `contract-decisions.md` | D1–D5 裁决记录与执行边界 | `03f56475163ba1d54a579c26d38f8c2034d0733b7f46e268b65373e844fcecd2` |
| `judge_v3.py` | 裁决后的 N5 v3（`outcome` 帧、模糊时间、数据触发 G4/G5、`quality()`） | `d3cfabea5027dfccdf7b72c5b8e845d2bf5ca0f61dc2f0f2a9bf7765a5c4215b` |
| `compose_v3.py` | 26 例在 v3 下重跑，记录 n5/n6/quality/d4 与反例 | `f7ff9f37341f49c0a48becf67d5445976185204c8fd78727b7b4433082f77fc8` |
| `make_v3_fixtures.py` | D1/D5 样本族生成 | `0d948d0362f8eab7b579ea46a1b67f4acb6daed1108a529243c9fbdbdcc8dbd9` |
| `test_judge_v3.py` | v3 单元检查（D1/D2/D3/D4/D5） | `f5a474a763b66452dabffeb566c2af85b579e871bab374cfc4152edda69c1ed9` |
| `human-review-v1.md` | D4 首批 10 条人工核验表 | `c7522ed3b1686c479f576f06a2fd00476627630490da8555620c732e3b4524fa` |
| `fixtures/cases-v3-extra.json` | D1/D5 样本（7 例，含反例） | `dc6c1dee153c804381596ca5ea9457dbd2831a703e3a674eee31a5cc10647d35` |
| `fixtures/annotations-v1.json` | D4 人工标注（10 例，未标注为 null） | `3a3ede5e4b8064a732fadba2fb6ce776b87457870d2416dfe97ab800ff94e2e1` |
| `fixtures/cases.json` | 19 个场景的输入点（已提交状态、视角、选项） | `b4f55779218715ef255dc2a795a1271d1f914c8a99f775676a7d017a2a7291df` |
| `fixtures/mocks.json` | 三个模拟端口的脚本返回；**不是模型输出** | `6051a7afab4094f4f08120aa96bd6b42eb43c5691d347656096ecd03a1c32627` |

运行归档不列入上表，因为它们的哈希每次重跑都会变（归档里带 `runAt` 和各阶段毫秒）；输出哈希统一由 `record_manifest.py` 写进 `fixtures/manifest.json` 的 `outputs[]`，与该文件里的上游源码/契约哈希、git HEAD、N5 口径、门覆盖范围放在一起。重跑只应该改变计时与 `runAt`：这一点由 `out/determinism.json` 证明（`identicalAfterStrip: true`）。

本目录的 `.gitattributes` 把行尾固定为 LF（`* text eol=lf`），所以上面的哈希在任何平台检出后都对得上；不钉的话 Windows 检出会把 LF 换成 CRLF，字节哈希就变了。

`fixtures/manifest.json` 是提交前一刻写的，所以 `git.headAtRecording` 是发布它的那一笔的**父提交**（内容上就是上一笔，即承载当前实现的提交；历史改写会让这个字段变成悬空引用，此时以逐文件哈希为准）。`git.porcelain` 原样列出写文件时仍未提交的项（本目录的改动，以及协调者按约定不入库的 `TASK.md`）。它绑定源码/夹具/契约的哈希，不绑定它自己。

| 归档 | 作用 |
| --- | --- |
| `out/composition-run.json` | 原始运行归档：每场景每步的请求、响应、校验、耗时；`cases[].facts[]` 是事实溯源 |
| `out/determinism.json` | 两次运行比对结论，v2 与 v3 各一节 |
| `out/determinism-a.json` / `-b.json`（v2）、`out/determinism-v3-a.json` / `-v3-b.json`（v3） | 参与比对的完整输出 |
| `out/contract-probes.json` | 任务标题、时间表达与 `outcome` 帧的定点探针结果（`probes` 为归档文本，`syntheticProbes` 为构造行） |
| `out/composition-v3-run.json` | v3 新归档：26 例的链、v3 硬门、`n6`/`quality`、D4 标注、反例、rowId 不变性、`probesUnderV3` |
| `out/console.log` / `out/console-v3.log` | v2 / v3 运行的终端输出 |
| `fixtures/manifest.json` | 输入清单与哈希：上游实现、契约文档、旧归档、本实验夹具；含 `missing`（本次为 0）、`n5Rule`、`n5GateCoverage`（逐门执行次数/案例/取值，从归档实测）、`tokenGate` |

## 10. 边界与未做

- 没改生产路由、`backend/app`、`frontend/src/app/world/page.tsx`、共享契约、冻结语料或既有归档；没有训练、没有 GPU。
- 没有接真模型、没有浏览器验收、没有语义复核（N6 未执行）、没有 N4 token 门。
- 没有扩大 v2 判定：旧硬门与旧归档原样使用。新版本 `n5-v3` 是按裁决新增的，不替换旧门；两套并存的边界写在 `contract-decisions.md`。
- v3 的 26 例正文同样是脚本字符串；`quality` 全部 `pending`，没有任何质量通过结论。

## 11. 下一步建议

1. 先裁决 D1、D2（任务标题、时间精确度）：这两条决定任务类与时间类事实能不能被合规叙事，不裁决就直接接真模型，第一批数据会全撞在这里。
2. 再裁决 D3（两套 N5 核）与 D5（G4/G5 触发），让「N5 通过」这个词有唯一含义；之后才谈页面放行门。
3. 把选择/组织/成句三个端口换成真模型（先离线，再浏览器），复用本目录的夹具与归档格式；此时才需要补 N4 token 门和真正的端到端耗时。
4. 在真模型数据上再跑一遍这 19 个场景，重点看：必述覆盖、重试率、回退率、新具名人物出现率（D4 的入不入硬门取决于这个频率）。
