# N3→N4 接口约束方案与非模型夹具

日期：2026-10-30。提交人：C 实现者。基线：`world-components@b97adb2`（= origin，已核实）；工作区仅未跟踪的 `signoff-f9c1190.md`（原样保留）与冻结产物，零改动。
状态：**方案＋夹具，待 C 审查者复审**。本方案定义的是**待实现、待验证的接口约束**，不是已接线能力；本轮不训练、不调用真实模型、不实现任何回退。

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
- 两个候选原因：`plan-too-long`（任一句组事实数 > 4）；`input-too-long`（展平后的 render 输入 token 数 > 128，计数器见 §3 桩说明）。

## 2. 权威输入绑定（缺失或对不上即停止）

N3→N4 链的输入只能来自**按目标 pointId 读取的已提交记录**（对齐 [README 权威锚点](README.md)与 R1 冻结读取契约）：`state`、`pointId`、`version`、`stateDigest`、`previousPointId`、`timeAdvance`、**原始 `entityDeltas`**；前状态按 `previousPointId` 显式读取并核对同世界、版本连续（before.version＋1＝version）与血缘；根点用空 Δ、null 前驱、version 0。

- 事实清单（manifest）的每条事实必须带指向原始 `entityDeltas` 的来源指针；绑定校验逐条核对指针可解析、指向的 delta 存在于绑定点的原始 Δ 中。
- **停止条件**（产出 `binding-failed`，拒绝进入接口检查）：缺 state/digest/version、前驱缺失（非根点）、版本不连续、世界不匹配、事实来源指针解析失败或指向不存在的 delta。
- **不从结果文本补造**：已提交叙事文本、preview 工作态、当前 head 均不得用于重建事实；绑定失败就是失败，不做任何差分补造。

## 3. 非模型夹具（`n3_n4_fixture.py`）

全部夹具为程序化验证，无模型调用。**token 计数用确定性桩**（固定 6 字符分块，与 N3 runner 自检同谱系）——**这不是真实 sentencepiece 分词器验收**；128/129 边界夹具验证的是接口的计数与判定逻辑，真实分词计数归 N4 浏览器批。

| # | 夹具 | 预期 |
| --- | --- | --- |
| F01 | 1 条事实单组 | accepted，renderInput 含该事实 |
| F04 | 4 条事实单组 | accepted（范围内上限） |
| F05 | 5 条事实单组 | unsupported/plan-too-long，plan 原样保留（逐字段相等断言） |
| FT128 | render 输入恰 128 桩 token | accepted |
| FT129 | 129 桩 token | unsupported/input-too-long |
| FM01 | 计划漏 factId | error/plan-fact-mismatch（missing） |
| FM02 | 计划重复 factId | error/plan-fact-mismatch（duplicate） |
| FM03 | 计划引用未知 factId | error/plan-fact-mismatch（unknown） |
| FO01 | 输入序变化 | accepted，renderInput 展平序随计划句组序（确定性映射断言） |
| FT01 | time 前驱（time 在前驱之后） | accepted，time 条目原样传递、at=null 处理不变 |
| FN01 | 同名不同实体 | accepted，coreference 原样保留但不进 renderInput |
| FX01 | 跨组指代（I2 域外引用） | accepted，coreference 原样保留不进 renderInput（接口不越权改判 N3 的 I2 结论） |
| FB01 | 非根点缺前驱记录 | binding-failed（missing-before） |
| FB02 | 版本不连续 | binding-failed（version-gap） |
| FB03 | 缺 stateDigest | binding-failed（missing-digest） |

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
