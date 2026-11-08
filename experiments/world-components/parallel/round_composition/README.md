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
python -X utf8 $RC/record_manifest.py   # 记录输入/输出哈希、N5 门覆盖与 git 身份
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
1. **任务标题契约冲突。** N4.0 的要求行写着「不写任务标题」，但 v2 N5 对任务类事实只有一种帧：`完成任务「目标原文」`。照 N4.0 写（把结果写成动作）必然挂 G1；照 N5 写就违反 N4.0。定点探针：`out/contract-probes.json` 的 `task-title-quoted`（pass）与 `task-title-paraphrased`（`uncovered:f1:task_achieved`）。本组合 4 个 `ok` 场景里的任务类事实全部选了后者（写标题）。登记为 D1。
2. **两套 N5 程序核不一致。** 本组合用 v2 对齐器（`eval_n4_v2.judge_row`）。同一批正文再用 v7 识别器（`corpus_check.check_narration`，`verify_text` 调用）看：`reject-n5` 第 2 次截断文本 `fails=[] reviews=0`（v7 没有截断规则），`fail-n5-extra-actor` 的残留人名只算 review，不算 fail。也就是说，「N5 拒绝」目前取决于用哪套核。
3. **时间契约冲突。** N4.0 契约明确要求时间只模糊表达、不写具体时长；v2 N5 的 G3 要求正文出现计划里的精确数值。照 N4.0 写的合规文本（`…过了一会儿。`）必然挂 G3（`uncovered:f2:time`）。本实验没有放宽任何门，只把这个冲突固定成一个场景。
4. **N5 不硬拒新增具名人物。** v2 G2 只扫 `facts` 里已登记的人名和任务目标，新出现的名字（`管线丙`）不在扫描范围；v7 核也只给 review。本场景靠夹具自带的 `annotations.addsUnregisteredEntity` 才标成 `n5-false-pass`，不是判定器自己发现的。

**无法判断**
1. 模型能力：选择、组织、成句三步都是脚本。这里没有任何一条能说明真模型能不能做这几件事。
2. N5 语义复核：本次完全没跑（`semanticReview: not-run`）。硬门通过不等于语义正确。
3. **G4 只是意外触发，G5 没有执行。** 两个门都由 `rowId` 子串触发：`contract-time-conflict` 的 caseId 含 `conflict`，于是 G4 在它的两次尝试上各跑了一次，结果都是 `true`；但该案例只有一个人物（两条事实都是管线甲），G4 走的是「同一名字多次出现」分支 `text.count(名字) >= 2`，**不是**真正的双人冲突，所以这次 `true` 不构成对 G4 的验证。19 个场景里没有 caseId 含 `same-name`，`G5_same_name_bare` 一次都没执行。逐门的执行次数、涉及案例与取值全部由归档实测写进 `fixtures/manifest.json` 的 `n5GateCoverage`（不是手填）。
4. 输入长度/真实 token：本工作树没有 checkpoint，无法重算 token；模拟端口吃文本，所以也没有 N4 的 token 门。N4.0 结构输入的历史量级（287–390 tokens）来自归档 `n4-input-packing-r1.json`，不是本次实测。

## 6. 契约裁决项

上面暴露的四处冲突（任务标题、时间精确度、两套 N5 核、新增具名人物）加一处门控问题（G4/G5 靠 caseId 触发），逐条登记在 [contract-decisions.md](contract-decisions.md)，每条写清：谁要求什么、证据指向哪个文件的哪个字段、现在会怎样、可选方向与代价、需要谁定。

| 编号 | 冲突 | 现在的后果 | 证据 |
| --- | --- | --- | --- |
| D1 | N4.0「不写任务标题」 vs N5 要求 `完成任务「目标」` | 任务类事实写标题才过门，不写就挂 G1 | `out/contract-probes.json` `task-title-*`；`composition-run.json` `normal-move-task` |
| D2 | N4.0 强制模糊时间 vs N5 要求精确数值 | 含时间推进的点要么不过门，要么违反 N4.0 | `out/contract-probes.json` `time-*`；`contract-time-conflict` |
| D3 | 两套 N5 程序核口径不同 | 「N5 拒绝」取决于用哪套核 | `n5CrossCheck`（`reject-n5`、`fail-n5-extra-actor`） |
| D4 | 新增具名人物没有硬门 | 编造人物会被放行 | `n5-false-pass-unregistered-actor` |
| D5 | G4/G5 由 `rowId` 子串触发 | G4 意外触发一次（`true`），G5 从未跑 | `fixtures/manifest.json` `n5GateCoverage` |

本实验不裁决、不改门。

## 7. 其他观察（不作缺陷断言）

- N4.0 把环境 overlay 的各字段值直接拼进「地点外貌」且不带字段名（`地点外貌=旧；细雨；傍晚；高；昏暗；海雾贴着塔壁`）。值写错时无法区分是地点原文还是 overlay；本实验的第一版夹具就因为给钟楼写了「巷子里全是湿气」而暴露这点，已改成与场景一致的值。生产该由场景/时间系统写入地点外貌（与 N4.0 文档的已知缺口一致）。
- `pack_narrative_input` 对 `time` 只写「时间经过」、组后统一写「过去了一会儿」，所以 N4 端看不到具体时长——这正是上面时间冲突的来源，也是契约有意的设计。
- N2 的模拟端口只回编号集合，所以本实验只能校验「不漏必述、不选不可见、不越界」，**没有**校验「该不该写」（显著性与省略）——那部分本来就是模型职责。

## 8. 交付物与哈希

| 文件 | 作用 | SHA-256 |
| --- | --- | --- |
| `compose.py` | 组合器（程序步骤 + 模拟端口 + N5 + 回退） | `0b4e359fa8e80516677c2a4450fdd2f6d13539f914bed06f703e4828c5bc9020` |
| `make_fixtures.py` | 由登记的已提交状态生成输入点 | `c155c002a9812787a01bf186bf8b3d7691d44d344b1f2e1baa0db5c99f802735` |
| `check_determinism.py` | 两次运行比对 | `88406e52fcd9246fd59e1b39e1189ad94dd37f1732538ca8135113c3b5d82952` |
| `record_manifest.py` | 记录输入/输出哈希、N5 门覆盖（从归档实测）与 git 身份 | `d632f87ec63334c04f00b4f40c13ed15226705dc2028266dcd39246d753f9b92` |
| `contract_probes.py` | 两个契约冲突的定点探针（读归档，不重跑组合） | `7998a781a93ead993d1bed141b587bc8d7d6ec3e650cdaa2b3907416fe973656` |
| `contract-decisions.md` | D1–D5 契约裁决项登记 | `5cf89248004853036e3a8e8b5b1e0b245ab96588abe429861e72376f842bf57e` |
| `fixtures/cases.json` | 19 个场景的输入点（已提交状态、视角、选项） | `b4f55779218715ef255dc2a795a1271d1f914c8a99f775676a7d017a2a7291df` |
| `fixtures/mocks.json` | 三个模拟端口的脚本返回；**不是模型输出** | `6051a7afab4094f4f08120aa96bd6b42eb43c5691d347656096ecd03a1c32627` |

运行归档不列入上表，因为它们的哈希每次重跑都会变（归档里带 `runAt` 和各阶段毫秒）；输出哈希统一由 `record_manifest.py` 写进 `fixtures/manifest.json` 的 `outputs[]`，与该文件里的上游源码/契约哈希、git HEAD、N5 口径、门覆盖范围放在一起。重跑只应该改变计时与 `runAt`：这一点由 `out/determinism.json` 证明（`identicalAfterStrip: true`）。

本目录的 `.gitattributes` 把行尾固定为 LF（`* text eol=lf`），所以上面的哈希在任何平台检出后都对得上；不钉的话 Windows 检出会把 LF 换成 CRLF，字节哈希就变了。

`fixtures/manifest.json` 是提交前一刻写的：`git.head` 记的是承载本目录实现的提交 `ad28b0b`，`git.porcelain` 原样列出写文件时仍未提交的项（本目录的整理改动，以及协调者按约定不入库的 `TASK.md`）。它绑定源码/夹具/契约的哈希，不绑定它自己。

| 归档 | 作用 |
| --- | --- |
| `out/composition-run.json` | 原始运行归档：每场景每步的请求、响应、校验、耗时；`cases[].facts[]` 是事实溯源 |
| `out/determinism.json` / `-a.json` / `-b.json` | 确定性比对的结论与参与比对的两份完整输出 |
| `out/contract-probes.json` | 任务标题与时间表达的定点探针结果（每句的硬门取值与问题） |
| `out/console.log` | 本次运行的终端输出 |
| `fixtures/manifest.json` | 输入清单与哈希：上游实现、契约文档、旧归档、本实验夹具；含 `missing`（本次为 0）、`n5Rule`、`n5GateCoverage`（逐门执行次数/案例/取值，从归档实测）、`tokenGate` |

## 9. 边界与未做

- 没改生产路由、`backend/app`、`frontend/src/app/world/page.tsx`、共享契约、冻结语料或既有归档；没有训练、没有 GPU。
- 没有接真模型、没有浏览器验收、没有语义复核、没有 N4 token 门。
- 没有扩大 N5 判定：v2 硬门原样使用，`n5-false-pass` 是通过夹具标注记录的分歧，不是把门放宽。

## 10. 下一步建议

1. 先裁决 D1、D2（任务标题、时间精确度）：这两条决定任务类与时间类事实能不能被合规叙事，不裁决就直接接真模型，第一批数据会全撞在这里。
2. 再裁决 D3（两套 N5 核）与 D5（G4/G5 触发），让「N5 通过」这个词有唯一含义；之后才谈页面放行门。
3. 把选择/组织/成句三个端口换成真模型（先离线，再浏览器），复用本目录的夹具与归档格式；此时才需要补 N4 token 门和真正的端到端耗时。
4. 在真模型数据上再跑一遍这 19 个场景，重点看：必述覆盖、重试率、回退率、新具名人物出现率（D4 的入不入硬门取决于这个频率）。
