# N3→N4 接口约束方案与非模型夹具

日期：2026-10-30。提交人：C 实现者。基线：`world-components@b97adb2`（= origin，已核实）；工作区仅未跟踪的 `signoff-f9c1190.md`（原样保留）与冻结产物，零改动。
状态：**方案 v2＋夹具，待 C 审查者复审**。本方案定义的是**待实现、待验证的接口约束**，不是已接线能力；本轮不训练、不调用真实模型、不实现任何回退。
修订记录：v1（`8626082`）→ v2（`291f5ae`）→ v3（`641efe8`）→ **v4（本笔，按两项独立反例收敛权威绑定）**：① **任务与姓名解析绑定已提交状态**——任务正文从 `state.characters[eid].tasks[tid]`（goal/status/ownerId）解析、实体姓名从 state 实体表解析并核对（`name-mismatch`）；不存在调用者自带的独立注册表，同时篡改事实与旁路注册表的绕过不再存在；② **世界身份按正式层级校验**——`state.worldId`（WorldState 字段），缺失即 `world-missing` 停止，前后状态 `state.worldId` 不一致报 `world-mismatch`（不再比较顶层不存在字段）；v3 及更早：：① 来源模型改按**实际 schema**——任务完成由 `EntityDelta.tasksAchieved` 的**任务 ID** 表示，任务正文从权威任务注册表解析（id→goal/ownerId/status），时间为 `TimeAdvance.duration.{amount,unit}`，不再使用简化形状或自称「真实形状」；② 绑定增加**归属核对**（fact.entityId == source.entityId，否则 `ownership-mismatch`）与逐字段内容验证；夹具明确支持类型集（task_achieved、time），**未支持类型显式拒绝**（`unsupported-fact-kind`）；③ 根点校验区分**缺字段与显式 null**——GetStateData 各键必须存在（根点取显式 null/null/{}），键缺失或必填字段为 null 均记读取不完整（`missing-<field>`）；④ token 计数直接作用于**共享渲染器 `n4_render.render_input` 的实际输出**（确定性程序，无模型——完整提示头、事实行、尾部），仅分词为桩；不再使用自造渲染文本。

## 0. 背景与已确认事实

- N4 冻结独立留出集为 44/44＋1/1，**已验规模＝1–4 条事实**（含时间；不含时间时 1–3 条），训练输入上限 128 token、输出上限 64 token；接入包明确更长计划「未测试」。
- `component-contracts.md §8.1` 的「4–5 条事实」为范围错误，本批已更正为 1–4 并引用留出集与接入包；**不扩大 44/44 的既有结论**。
- `n3cap-07` 冻结 gold 含 5 事实句组；其 4+1 切分会把同一人物的任务与理智变化拆开，**不能称语义无损**。总指挥已裁决：超限标记为不支持，保留原 N3 计划与 ID；切分回退不实现。
- N4 当前 `render_input` **不消费 coreference、不消费句组边界**（既有待办）；跨组/组内指代对渲染无效果，属未验证。

## 1. `unsupported` 结果契约（超 4 条事实或超 128 token）

接口检查函数对每个计划产出三态结果之一：`accepted` / `unsupported` / `error`（另有绑定层的 `binding-failed`，见 §2）。

**形状**：

```json
{"status": "unsupported",
 "reason": "plan-too-long | input-too-long",
 "limits": {"maxFactsPerGroup": 4, "maxInputTokens": 128},
 "observed": {"groupIndex": 2, "facts": 5},
 "plan": {…原始 N3 计划，逐字段原样嵌入…}}
```

- **保留原计划**：`plan` 字段是 N3 计划的原样深拷贝——句组、factId、顺序、实体、时间全部不变；接口层不重写、不重排、不删指代。
- **coreference 明确不消费**：`accepted` 时构造的 `renderInput` 只含事实条目（按计划句组序展平的扁平事实表，与现行 `render_input` 消费面一致），coreference 与句组边界不传入；它们仅随 `plan` 原样保留供后续 N4-coref 工作。
- `unsupported` 不是失败也不是通过：不计入任何门，只标定「该计划超出 N4 当前已验范围」。
- 两个候选原因：`plan-too-long`（**实际单次 N4 输入＝展平事实总数** > 4——句组划分不能绕过上限，分组边界的语义意义留给候选方案）；`input-too-long`（**渲染替身文本**的桩 token 数 > 128——N4 消费的是 render_input 生成的提示文本而非 JSON，计数对象与之一致；渲染替身与桩分词均非真实验收，见 §3）。

## 2. 权威输入绑定（缺失或对不上即停止）

N3→N4 链的输入只能来自**按目标 pointId 读取的已提交记录**（对齐 [README 权威锚点](README.md)与 R1 冻结读取契约）：`state`、`pointId`、`version`、`stateDigest`、`previousPointId`、`timeAdvance`、**原始 `entityDeltas`**；前状态按 `previousPointId` 显式读取并核对同世界、版本连续（before.version＋1＝version）与血缘；根点用空 Δ、null 前驱、version 0。

- **根点/非根点分别校验，缺字段≠显式 null，世界身份在 state 层**：GetStateData v2 各键**必须存在**（no-default）；根点取**显式** null/null/{}。键缺失或必填字段为 null 均记 `missing-<field>`。**世界身份是 `state.worldId`（WorldState 字段，非顶层）**：缺失即 `world-missing` 并停止绑定；非根点 before 记录须存在且**前后 `state.worldId` 一致**（否则 `world-mismatch`）、version 连续、前驱身份一致（before.pointId == point.previousPointId）。
- **来源解析与内容核对（绑定到 state）**：`entityDeltas` 是按实体组织的 `EntityDelta` 映射（contracts.py）；task_achieved 的来源是 `tasksAchieved` 中的**任务 ID**，任务正文从**绑定 point 的 state**（`state.characters[eid].tasks[tid]`）解析，核对归属（fact.entityId == source.entityId → 否则 `ownership-mismatch`）、**实体姓名与 state 实体表一致**（否则 `name-mismatch`）、任务在册且 goal/owner/status 与事实一致；time 的来源是 `TimeAdvance.duration`，核对 amount/unit。**未支持的事实类型显式拒绝**（`unsupported-fact-kind`）。不一致即 `source-content-mismatch`。**不存在调用者自带的独立任务注册表**——任何旁路表都无法与事实合谋绕过 state 解析。
- **停止条件**（产出 `binding-failed`，拒绝进入接口检查）：缺 state/digest/version、前驱缺失（非根点）、版本不连续、世界不匹配、事实来源指针解析失败或指向不存在的 delta。
- **不从结果文本补造**：已提交叙事文本、preview 工作态、当前 head 均不得用于重建事实；绑定失败就是失败，不做任何差分补造。

## 2.1 N3 不变量是采纳前置

接口检查在覆盖检查之后、范围检查之前运行 N3 硬不变量（`n3_plan.check_invariants`）：I2 违规（如跨组指代）或 mention 不实的计划报 `error:plan-invariant-violation` 并停止，**不产出 renderInput**。coreference 不被 N4 消费只说明渲染层忽略指代，不免除计划本身的合法性——上游验证失败即接口停止，映射成功不等于计划可采纳。

## 3. 非模型夹具（`n3_n4_fixture.py`）

全部夹具为程序化验证，无模型调用。**token 计数用确定性桩**（固定 6 字符分块，与 N3 runner 自检同谱系）——**这不是真实 sentencepiece 分词器验收**；128/129 边界夹具验证的是接口的计数与判定逻辑，真实分词计数归 N4 浏览器批。

| # | 夹具 | 预期 |
| --- | --- | --- |
| F01 | 1 条事实单组 | accepted，renderInput 含该事实 |
| F04 | 4 条事实（展平上限） | accepted |
| F05 | 单组 5 条事实 | unsupported/plan-too-long，plan 原样保留（逐字段＋深拷贝断言） |
| F52 | 两组 3+2（展平 5 条） | unsupported/plan-too-long——分组不能绕过上限 |
| FT128 | 渲染替身文本恰 128 桩 token | accepted |
| FT129 | 129 桩 token | unsupported/input-too-long |
| FM01/02/03 | 计划漏/重/未知 factId | error/plan-fact-mismatch:missing / duplicate / unknown |
| FO01 | 输入序变化 | accepted，renderInput 展平序随计划句组序 |
| FT01 | time 在前驱之后 | accepted，time 条目原样传递、at=null 不变 |
| FN01 | 同名不同实体（各指代本组实体） | accepted（I2 合法） |
| FX01 | 跨组指代 | **error/plan-invariant-violation**（I2 前置停止，不产 renderInput） |
| FB01/02/03 | 非根点缺前驱 / 版本断裂 / 缺 stateDigest | binding-failed:missing-before / version-gap / missing-stateDigest |
| FBL1 | before.pointId 与 previousPointId 不相关 | binding-failed:predecessor-identity-mismatch |
| FBR1 | 合法根点（timeAdvance=null、空 Δ） | 绑定通过 |
| FBR2 | 根点带 timeAdvance | binding-failed:root-with-time |
| FSC1 | task goal 与实体任务列表不符 | binding-failed:source-content-mismatch |
| FTT1 | time amount 与 timeAdvance 不符 | binding-failed:source-content-mismatch |

**渲染与分词**：token 计数直接作用于**共享渲染器 `n4_render.render_input` 的实际输出**（确定性程序、无模型依赖——完整提示头、逐事实行、尾部一并计入）；仅 6 字符分块分词为桩，**不是**真实 sentencepiece 的验收；真实分词归 N4 浏览器批。

## 4. 未来候选（只登记追踪，不实现）

| 候选 | 内容 | 风险 | 独立验收条件 |
| --- | --- | --- | --- |
| 有约束拆分 | 超限句组按约束切分（如按实体边界而非固定 4+1）后分段渲染 | 切分改变句组边界与指代上下文；同人物事实被拆开（n3cap-07 已证 4+1 非语义无损）；段间连贯未验证 | 独立方案文档；拆分点语义论证；分段渲染的离线质量证据（N4 已验范围内）；与不拆分的对照报告 |
| 扩展 N4 | 训练/验收扩展到 >4 事实、>128 token 计划 | 训练语料需新建（隔离约束不变）；现有冻结留出集不可用于扩容调参 | 新隔离语料＋新冻结留出集＋独立质量门；不得复用 44/44 结论外推 |

两候选互不预设；在任一落地前，超限计划的正式结果就是 §1 的 `unsupported`。

## 5. 交付与验证

- 新增：本方案、`experiments/world-components/n2_selection/n3_n4_fixture.py`、结果归档 `artifacts/world-components/n3-n4-fixtures.json`。
- 验证命令：`n3_n4_fixture.py --selftest`（桩与判定逻辑自检）；`n3_n4_fixture.py --out artifacts/world-components/n3-n4-fixtures.json`（跑全部夹具）。
- 已签认制品（gold、判据、runner 签认、冻结记录）零改动；`signoff-f9c1190.md` 保持未跟踪。
