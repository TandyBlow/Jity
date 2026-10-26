# 原方案对照修复清单（模型任务输入与职责）

状态：2026-10-25。背景：用户指令——叙事拆分实验推进前，先按原方案（browser-world-state-workflow.md）§7.1/§6.x 修正现有模型任务的输入与职责偏差；验证重点是「**模型收到的信息和程序执行的行为符合原方案**」，不是输出格式。核查对象：`schedule.ts`（任务输入构造）、`controller.ts`（输出消费与 preview）、`runtime/structured-output.ts`（输出 codec）、`runtime/prompts.ts`（提示词契约）。

## 1. 逐任务对照

| # | 任务 | 原方案要求 | 现状（证据） | 偏差 | 修复方向 | 验证方式 |
|---|---|---|---|---|---|---|
| 1 | action | §6.1：读最新工作状态、人物任务与个性、**链级 advance 上下文**；主角行动受玩家输入约束；intentStatus 决定输入能否作为待处理命令 | `schedule.ts:515` `input={actor, workingState}`——无输入文本、无 intentStatus | 缺玩家输入与消费状态 | input 补 `advance: {inputText\|null, intentStatus}`（context 已携带） | 输入形状断言（prompt 序列化含输入文本与消费状态）；场景：consumed 后主角不得重新消费输入 |
| 2 | targets | §6.2 步骤 2：分析已确认行动可能迫使谁反应 | `schedule.ts:635` `input={sourceId, actionText, workingState}` | 符合 | — | — |
| 3 | reaction | §6.2 步骤 4：目标读取**具体威胁**生成反应行动 | `schedule.ts:645` `input={sourceId, memberId, rollId, workingState}`——缺 source 的冻结行动文本 | 缺威胁文本 | input 补 `sourceActionText`（pendingGroup 冻结工作已有） | 输入形状断言；反应文本应针对威胁 |
| 4 | results | §7.1：结算前状态、**全组行动、骰点** | `schedule.ts:705` `input={groupId, workingState}`——缺成员行动文本与骰点引用 | 缺全组行动与骰点 | input 补 `members:[{memberId, actionText, rollRefs}]`（闭组冻结工作已有） | 输入形状断言；结果候选应引用全组行动 |
| 5 | updates | §6.3 依赖表：阶段 n 读**已更新**后的状态；§7.1 更新读取已确认结果；拆分阶段经 preview 应用前序候选后再生成后序候选 | `schedule.ts:709` input 不含 `lastResults`（已确认结果）；`updatesModelCall`（`schedule.ts:665-673`）拆分阶段把 priorStages/appliedDelta 作为数据附带、workingState 保持阶段前原样——前序候选由模型心算应用 | 缺已确认结果；拆分阶段不重算状态 | 每阶段前经 preview 应用前序候选（`controller.ts:221` preview 已有；阶段内未 stage 的候选可并入 preview 请求的 settlementGroups 投影，无需改 schema）；后序阶段输入=更新后 workingState＋已确认结果 | §11.2 强制拆分反例（位置影响外貌）：阶段 2 的输入必须已含新位置 |
| 6 | narration | §7.1：Sₜ₋₁、Δₜ、Sₜ、主角视角约束 | `controller.ts:276`、`controller.ts:428` `input={pointId, stateDigest}`——模型拿不到任何状态数据 | 缺全部状态输入 | input 补 before/delta/after/perspective（提交响应与 points 数据已有） | 输入形状断言；对 narration-split 冻结样本出忠实度数字 |
| 7 | pointPlan | §5.1/§6.1：冻结顺序**逐人物**判断（模型逐人返回 act/skip）；点位切分与时间跨度可由模型提议（§5.2） | `schedule.ts:437`＋`prompts.ts:33`：模型预选每点 actorIds；`schedule.ts:483-516` 只处理被预选者；`schedule.ts:543` 起：未被任何点覆盖的人物由**程序直接 record_skip**，从不调用其行动判断 | 逐人跳过判断从模型职责移到了 pointPlan 预选＋程序补录 | 保留点位切分/时间提议；撤人物预选——每点按冻结顺序逐人调用 action 判断（act 或 skip） | 场景：未被预选人物也有 action 调用与 skip/visited 记录 |
| 8 | targets 输出契约 | §6.2/§9.3：triggerKey 由程序分配；**模型不掷骰、不决定阈值**；骰点规则版本锁定（reaction-fixture-v1；真实基线 reaction-d20-v1 = d20≥11） | `structured-output.ts:144-155` 要求模型输出 `triggerKey`/`ruleVersion`/`target`；`controller.ts:370-372` 直接采纳模型规则建 rules（`controller.ts:55` 有 fixture 兜底） | 模型决定触发键与骰点阈值 | codec 收窄为 `{targetId}`；triggerKey 走 allocate_ids（kind:'trigger'）；rules 用程序锁定版本 | codec 负例：携带 triggerKey 的输出拒绝；controller 不再读模型规则 |
| 9 | time / continuation | §5.2 / §7.1 | `schedule.ts:578` `input={head, workingState}`；`schedule.ts:420` `input={round, head, workingState}` | 待核：continuation 是否需补主角与状态变化上下文（§7.1：「主角、当前世界和本轮状态变化」） | 随修复批次一并核对 | — |
| 10 | 预算门槛 | — | `schedule.ts:261`：narration/pointPlan/time 永不被预算或算力阻塞 | 合规 | — | — |

## 2. 修复顺序与边界

- 建议顺序：**8**（codec 收窄，独立可测）→ **6**（narration 输入，叙事实验直接依赖）→ **5**（updates 阶段间 preview 应用）→ **1/3/4**（输入补充）→ **7**（pointPlan 行为，动控制器面最大）。
- 边界：不改协议表结构与 wire schema；输入补充只使用 context/preview/提交响应已携带的数据；#5 的 preview 阶段投影语义需与 A 侧对齐后动。
- 明确区分（用户裁定）：**叙事流水线通过 ≠ 行动与结算链通过**；完整游戏链验收等本清单修复完成后再做。

## 3. 数据来源逐字段核对（2026-10-25，落实前置）

按用户要求对「context 已携带输入文本」「提交响应已有全部叙事数据」类表述逐字段核对真实响应形状（`types.ts` 的 RequestMap/DataMap 与 controller 实际持有）。结论：多数可用，**两处缺口**。

| 任务需要 | 真实来源（核对结果） | 结论 |
|---|---|---|
| action：玩家输入文本 | `ContextResponse.activeInput: {advanceId, inputId, text} \| null`（`types.ts:56`）——仅活动链携带 | ✓ 现有读取即可 |
| action：intentStatus | `world.advance.intentStatus`（`types.ts:41`） | ✓ |
| action/reaction/results：最新工作状态 | `preview_point` 返回 `data.workingState`（`types.ts:126`），controller 已持有 | ✓ |
| reaction：威胁文本 | 发起者冻结行动（控制器 `current.actionText`，与 targets 同源 `schedule.ts:635`） | ✓ |
| results：发起者行动 | 同上 | ✓ |
| results：**成员行动文本** | 控制器侧 `current.rolled` 只存 id/roll 引用（`schedule.ts:620`）**不留 actionText**；服务端 `world_group_work` 与恢复载荷 `FrozenGroup.members[].actionText`（`types.ts:52`）已存 | ⚠ 需从恢复/组工作读取，或控制器留存——实现时定，可能新增读取 |
| results：骰点 | `create_rolls` 响应 `data.rolls` 含 result/eligible/admitted（`RollOutcome`，`types.ts:66`） | ✓（控制器留存待实现时核对） |
| updates 阶段间重算 | `preview_point` 的 `settlementGroups` 接受任意候选投影（`types.ts:68`）——阶段内前序候选可并入，无需改 schema | ✓ 机制现成 |
| narration：Sₜ | `get_state?point=head` 或提交后 workingState | ✓ |
| narration：Sₜ₋₁ | `get_state?point=previousPointId`（get_state 支持任意点，`types.ts:96`） | ✓ 现有读取即可 |
| narration：**Δₜ** | **无现有读取**：`list_points` 只返回摘要不含 entityDeltas（`types.ts:129`）；按状态差分重建 Δ 有损（supersedes 语义不可恢复）。控制器在 claim 时可从 `memory.commitPayload.point.entityDeltas` 组装，但刷新恢复路径仍需读取 | ⚠ **需要新增读取**（扩展 list_points 或 narration-jobs 附带 point 明细）——与 A 侧对齐后定 |
| narration：视角约束 | `protagonistId` 在状态中 ✓；约束语义归提示词层 | ✓ |

落实纪律：修复只允许「补读取/补传递」，**不能只给提示词增加字段名**；每项修复必须带「输入形状断言」（prompt 序列化后的实际内容含所需数据）与行为级场景测试（§1 验证方式列）。

## 4. 批次启动（2026-10-25 用户裁决）

决定：启动本清单的调用链对齐修复；**暂不重跑全量 B3**；产品主线继续「无 LLM、无 WebGPU」，Qwen 诊断仅作旧路径参考。

诊断归因边界（按用户复核收窄）：P3 同时开启 schema 与缓存（cached 707/708 token），133s→10.9s **不能分别归功于两者**，也不代表真实游戏变化输入能稳定命中同比例缓存；五次长跑原文已丢失，其耗时组成是短诊断基础上的**推测**而非逐次证实；P2/P3 对 person_a 的提示词输出主角行动——**格式改善 ≠ 语义正确**。不作任何全量时长承诺。

适配器修复（聊天模板、关思考、json_schema、maxTokens 按任务收、cache_prompt、计时元数据保留）列为**独立修复项**，不挤占本清单主线。

实施方法：

- 每项先按 §3 核对真实数据来源，再改接口与行为；禁止只给提示词加字段名。
- **固定模型输出验证**：沿用 T01–T08 场景机制——协议、世界状态、恢复断言**保留**；与原方案冲突的**模型输入、调用顺序、输出声明**同步修正，逐处记录修改依据。现有测试声明不构成保留偏差的理由。
- 前两项改动面：
  - **#8 codec 收窄**：`structured-output.ts:144-155` targets 输出收窄为 `{targetId}`；`schedule.ts:603/610` 不再读模型的 triggerKey/规则；`controller.ts:54-55,370-372` 删除「采纳模型规则」路径——triggerKey 改运行时 `allocate_ids`（kind:'trigger'，按 (sourceId,targetId) 槽位），骰点规则用程序锁定版本（reaction-fixture-v1；真实基线 d20≥11）。注意：分配计划目前是场景预声明的，而目标集由模型现场决定——需要新增**运行时分配流**（每源一次 allocate_ids）。
  - **#6 narration 输入**：`controller.ts:276/428` 组装 `{before, delta, after, perspective}`——after=提交后 workingState、Δ=commitPayload.point.entityDeltas（非刷新路径）、Sₜ₋₁=`get_state?point=previousPointId`（新增只读调用）；刷新路径的 Δ 读取缺口（list_points 扩展或等价只读查询）与 A 侧对齐后补。`prompts.ts` 叙事契约改序列化四件套；B3 narration 样本与场景声明同步修正并记录依据。

## 5. #8 完成记录与 #6 实施方案（2026-10-25）

**#8 已完成（390/390 world-engine 测试绿、tsc 干净）**，按用户三条守卫落实：

- **目标集保全**：模型输出在 `consumeModelOutput` 捕获进新记忆字段 `lastTargets`（`controller.ts`），不走 `lastModel`——allocate_ids 这一跳成功后 lastModel 被清空（`step()` 的统一行为），目标集不丢、不重采样。
- **分配与重试稳定绑定**：槽位键 **`trigger:{groupId}:{sourceId}:{targetId}`**（按用户复核修正：触发是 per-threat 身份、判定键含 sourceId——不同来源指向同一目标各占各槽，互不复用不覆盖；首版 `trigger:{groupId}:{targetId}` 会让 C 的分配请求重发并覆盖 A 已确认的 D 键，已由回归测试钉死）；allocationKey `trigger:{groupId}:{sourceId}`——超时重试同请求幂等返回同键；**只请求本来源确实缺失的槽位**（混合键集：已有 c:d 时不重发、他人 a:d 不进请求）；已确认的键留在 `memory.ids`，extend_group 成功才清 `lastTargets`；空目标集零分配直接 extend。数据库约束更正：服务端主键是 **`(world_id, allocation_key, slot_key)`**，不是此前误写的 `(world_id, allocation_key, kind)`。
- **程序掌握规则**：codec 收窄为 `{targets:[{targetId}]}`（多带 triggerKey/ruleVersion/target 即拒，负例入测）；骰点规则=程序常量 `PROGRAM_ROLL_RULE`（fixture-v1/11，与录制值一致，d20 基线换常量即可）；场景侧 T02/T03 不再从录制 rolls 反推进模型输出，改用 `memory.ids` 种子（含来源段）绑定录制键值。
- **组合键编码（用户复核碰撞与超长后重做）**：拼接式槽位键有两个硬伤——`来源 a:b+目标 c` 与 `来源 a+目标 b:c` 折叠出同一个键（均为合法 ID）、三个 50 字符合法 ID 拼接 160 字符超 wire 上限 128。改为 `foldIdentity`：各段**长度前缀折叠**（消除边界歧义的前像）＋ SHA-256 截断 128 位，`triggerAllocationKey`/`triggerSlotKey` 键文本 ≤40 字符；ASCII 限定（world-canonical-v1 的 ID 纪律），非 ASCII 抛错。边界回归：标准向量（空串/abc）、折叠单射性（a:b|c ≠ a|b:c）、128 字符上限（50 字符 ID×3）、跨调用稳定（重试幂等绑同键）。T02/T03 种子与控制器夹具全部改经同一构造器，录制键值不变、语料零改动。
- 关键实施发现：`writeBind` 返回 CheckpointRequest 级绑定（含 expected* 三字段），`AllocateIdsRequest` 不接受——运行时分配请求必须显式取 worldId/leaseToken/fenceEpoch 三项，不能展开 bind。
- 验证：调度器单测（分配决策＋混合过滤＋空集零分配＋组合键四项边界）＋codec 负例＋**真实控制器回归**（`allocate_ids → extend_group`：超时后同字节重试、per-source 槽位、他人历史键无覆盖、extend 用程序键）＋T02/T03 全链（种子键=构造器绑定录制值，语料零改动）＋B3 harness 输出形状更新。

**#6 实施方案（2026-10-25 二次修订，按用户四点复核；待执行）**：

- **原始 Δ 读取，撤回重建兜底**：叙事的 Δ 一律来自**该点已保存的原始 Δ 的只读读取**（`list_points` 扩展或专用的点明细读取——§9.5 本就要求回放时「读取 Δₜ」，补读取能力即可，不加行动记录层）。正常提交路径可把 commit 时捕获的原始 Δ 当**缓存优化**先用；**恢复/冷启动路径必须走读取**，两条路径数据源相同（同一份已保存 Δ）。语义等价重建方案撤回——等价性未证明，且会让两条路径使用不同来源。
- **刷新就是内存丢失路径**：必须有一条从**全新控制器**开始的验证——不携带旧 commitPayload/capturedDelta/叙事输入，仅凭服务端读取取齐同一点的前状态、原始 Δ、后状态。
- **后状态读取显式用目标 pointId**：`get_state?point=<待叙事点>`，不得把「当前头」当作待生成叙事的点（历史重生成/后继点场景下两者不同）。
- **测试期望独立于组装实现**：`assembleNarrationInput` 可复用于生产与场景声明，但**测试期望不得由同一函数产出**——期望用独立手写的字面量对象，防止生产与测试共同遗漏字段时全绿。
- **标本保真度分级**：「finalState＋替换时间」近似标本只用于验证**读取路由**；至少补一条使用独立确定的真实前状态、原始 Δ、后状态的对照（正常提交＋冷启动各一），验证输入忠实性。
- 其余不变：记忆形状 `narration={pointId, previousPointId, capturedDelta(缓存), claim, input}`；组装阶梯改为 after 读（按目标 pointId）→ before 读（previousPointId，经 list_points 兜底推导）→ **原始 Δ 读** → `assembleNarrationInput` 补 perspective；harness `ReadStateSpecimen`；同步面=B3 两样本+T01 两叙事+T02–T08 各一（T06 无）。
- **原始 Δ 读取的落地形状（2026-10-25 用户确认三字段扩展，契约同步已完成）**：`GetStateData` 增加必填 `previousPointId: Id|null`、`timeAdvance: TimeAdvance|null`、`entityDeltas: dict[Id,EntityDelta]`（该点自身已保存记录，与 data.pointId 对应；根点=null/null/{}；**无默认值——缺字段=读取能力不完整，客户端必须停止叙事生成，不得当空增量**）。同步面全部落地：Pydantic 定义（requests.py）→ 重导出 schema/manifest → **11 条轨迹 get_state 步骤回填三字段**（提交点读=逐字复制最近前置 commit 的 point 记录含模板变量；根读=null/null/{}；sync_get_state_traces.mjs 一次性工具留档）→ 轨迹 contractDigest 重钉（新摘要 abda4555…）→ 契约夹具 get_state/success.json（历史读：p1≠头 root_0，三字段与 p1 对应）→ TS 类型（types.ts 必填三字段）→ 前端契约钉 contract-digest.json。验证：后端 923/923（含 export 16、traces 16）、前端 396/396＋tsc 净。
- **待做：控制器与场景接线**（下一批次）：①调度器组装阶梯——after 读（get_state 按目标 pointId）→ 补 previousPointId/timeAdvance/entityDeltas（缺任一→stop 原因 `narration_read_incomplete`）→ before 读（get_state 按 previousPointId；根点 before=null 不读）→ 发模型调用；commit 捕获 Δ 仅作缓存优化，恢复路径一律走读取。②adoptSuccess 路由 get_state.data 进 narration.input。③harness ReadStateSpecimen（锚点后插 get_state：served 取锚点后快照、data 由场景供给）。④六场景叙事声明改全量输入（**独立手写字面量，不经 assembleNarrationInput**）＋B3 两叙事样本＋prompts.ts 叙事契约。⑤验证：正常提交与全新控制器冷启动两条路径、独立期望；忠诚性对照（真实前后状态＋原始 Δ）。

## 6. #6/#5 落地（已随 8a2efcd、5759234 提交）与 #1/3/4 完成记录（2026-10-26）

**批次状态**：清单第 1、3、4 项与本轮复核跟进已完成（复核跟进见 §7）；第 6 项控制面与场景接线、第 5 项多阶段验收已在此前的 8a2efcd／5759234 提交中落地（5 节的「待做」列表即那两次提交的内容，本节不再重复）。命名按复核裁定：**#6「叙事读取」已关闭**；当前遗留的 H2 缺口是**冻结组行动恢复**（刷新/冷启动后 `groupActions` 为空），不是叙事读取。剩余：#7（pointPlan 逐人判断）、#9（continuation 上下文复核）、H2 冻结组行动恢复、以及 B3 全量重跑（用户裁定暂不做）。

**#1 action —— 链级 advance 上下文**

- 数据源（核对结果）：`ContextResponse.activeInput {advanceId,inputId,text}`（仅活动链、只由 context 回包携带）＋ `world.advance.intentStatus`。控制器新增 `activeInput` 服务态（`adoptState` 只在回包携带该字段时更新；`undefined`＝保持现状，不把缺失当 null）。
- 实现（经 §7 复核修正）：调度器 action 输入补 `advance:{inputText|null, intentStatus}`；`inputText` 按 **advance 身份绑定**取源——同一 advance 的 context `activeInput` 优先（服务端权威），否则用控制器保留的 `playerAdvance`（`start_advance` 成功时以请求原文＋回包 advanceId/inputId 留存）；advanceId 一变，旧记录自动失效、不跨轮泄漏。`intentStatus` 取调用时刻的 `world.advance`——不是「有文本就 pending」。提示词契约同步：判断**输入 actor 指定的角色**（不一定是主角），主角的 pending 输入须结合最新状态判断能否执行（可能已失效），consumed 只是触发背景。
- 边界：T01 没有 context 回包，文本来自 `playerAdvance`（不再接受 `inputText=null` 作为正确期望）；文本与状态是两路数据，不互相推断。

**#3 reaction —— 发起者威胁文本**

- 输入补 `sourceActionText`，逐字取当前源（`sources[0].actionText`）的冻结行动文本——与 targets 同源。提示词契约要求反应针对该具体威胁。

**#4 results —— 全组冻结行动与全部骰点判定**

- 输入补 `members:[{memberId, actionText, rollRefs}]`，`rollRefs` 含 `{targetId, rollId, result, eligible, admitted}`——**未准入与不合格的判定同样入列**（§7.1「骰点」）。
- 数据源：§3 核对时定为「控制器留存」（服务端 `FrozenGroup.members[].actionText` 只走恢复载荷；本轮不改 wire）。新记忆字段 `groupActions` 与 `sources` 同生命周期：`discover` 重置建立、准入 `extend` 前插、`create_rolls` 追加、`stage_unit`/`stage_time_scan`/`commit_point`/`clearRoundWork` 归零——只覆盖当前组，不是长期行动记录。
- **完整性守卫（§7 复核追加）**：results 调用前核对组成员（`pending.memberIds`，空则 `[sourceId]`）是否都有留存行动；缺任何一个就 `stop`（原因 `frozen_actions_missing:<ids>`），**绝不以 `members=[]` 让模型编结果**。刷新/冷启动的内存丢失由 H2 恢复批次从服务端 `FrozenGroup.members` 补水；补水完成前该路径明确停止。

**验证（固定模型输出机制，协议/状态/恢复断言保留）**

- 输入形状断言（提示词序列化后的实际内容）：`runtime/b3.test.ts` 断言 action 提示词含 `"inputText"`/`"intentStatus"`、reaction 含 `"sourceActionText"`、results 含成员的 `"actionText"` 与未准入判定的 `"eligible":false`。
- 调度器单测：action 的 advance 两态（有文本/无 context 读取）与「状态取自服务态」；reaction 的 `sourceActionText`；results 的成员顺序与两类判定（合格未准入、不合格未准入）。
- 真实控制器回归：`controller.test.ts` 端到端断言 action/reaction/results/updates 四处实测输入与提交后 `groupActions` 归零、`playerAdvance` 留存；另加「无冻结行动即停止」的驱动级探针。
- 场景级：T01/T02/T03/T04/T08 的声明输入全部改为**独立期望**——action 的 advance 由 `servedBeforeSteps` 取「调用时刻最近服务态＋最后一次 context」，results 的 members 由 `frozenGroupActionsAtStage` 按录制镜像（发起者先入、准入前插、roll 追加、stage 结算归零）。T02 新增手写字面量断言：四次行动的状态序列 `pending,pending,consumed,consumed`（第二/三点的 consume 由 commit 转态，一次性声明的旧写法会漏掉）＋四条 results 的成员顺序＋逐条判定值（含 `person_d` 准入后对 `person_e` 的合格未准入判定）。T02-empty-linked：`consumed`＋四人逆序前插＋三条准入判定。
- 顺带修复：5759234 遗留的 `prefer-const` lint 错误（`controller.test.ts` 两处 `let`）使 `npm run build` 断在 lint 阶段，本轮改为 `const` 后 build 通过。
- B3 冻结样本：action 两样本的 `inputText` 改为 T01 录制 `start_advance` 的逐字文本「我推开重门。」（原先是另写的句子，与「T01 school 世界派生」的出处不符）。

**本轮验证**：前端全量 477/477（world-engine 415）、`tsc -p tsconfig.world-contract.json` 净、`tsc --noEmit` 净、`npm run build` 通过（lint 仅既有 warning）；后端 `python -X utf8 -m pytest -q` 923/923。

## 7. 输入补齐复核跟进（2026-10-26，review 报告 artifacts/model-input-review.json）

复核裁定：477/477 与两套 tsc 通过**不足以**关闭「输入补齐」；控制器探针查出三处缺口。命名同步修正：**#6「叙事读取」已关闭**，当前遗留的 H2 缺口是**冻结组行动恢复**（与叙事读取无关）。

| 探针行 | 实测缺口 | 本轮处理 |
|---|---|---|
| `normal_input_without_context_roundtrip` | `start_advance` 收到原文，随后 action 得到 `inputText=null、intentStatus=pending` | 控制器在 `checkpoint_start_advance` 成功时留存 `playerAdvance={advanceId,inputId,text}`（原文取自请求、身份取自回包）；调度器 action 的文本按 advance 身份取源：同一 advance 的 context `activeInput` 优先，否则用留存原文；advanceId 不同则一律不用（不跨轮泄漏）。T01 不再以 null 为期望。 |
| `results_to_updates` | 结果已存 `lastResults`，updates 输入没有结果内容 | `settleDecision` 的 group updates 基座补 `results`（batch 与拆分阶梯每一阶段都带）；`updatesContract` 在 results 存在时明说「更新必须与之一致」；时间扫描（无 results）不提该句。 |
| `missing_frozen_actions` | 冻结行动缺失时仍调用 results、传 `members=[]` | results 前做完整性守卫：`pending.memberIds`（空则 `[sourceId]`）逐个核对其留存行动，缺一个即 `stop`（`frozen_actions_missing:<ids>`）、不发起模型调用；补水归 H2。 |

**提示词修正（action）**：原措辞「决定主角是否行动」与「pending 时必须执行」把两件事说死——调度器会对不同人物调用 action，先前变化也可能让玩家行动失效。改为判断**输入 actor 指定的角色**（不一定是主角）；仅当该角色是主角且 `intentStatus=pending` 时，输入才是待处理命令，且必须结合最新工作状态判断能否执行（目标/条件失效则不可执行）；consumed 只作触发背景；其他角色按自身任务与个性判断。

**验证**

- 调度器：advance 文本四态（无源/留存/旧 advance 失效/同 advance 的 context 优先）、留存与 context 的优先级、`results` 进入 updates 输入、缺成员即 stop。
- 真实控制器：端到端断言 action 的 `inputText='探索走廊'`（驱动自己发起的 advance，无 context 回读）、updates 的 `results`、提交后 `playerAdvance` 留存；新增两个探针级用例——「settle 点无冻结行动 → `frozen_actions_missing:person_a`，零模型调用、零传输」与「start_advance 成功后 `playerAdvance` 与身份绑定」。
- 场景级：T01 的 action 文本改为录制的 `start_advance` 原文（不再是 null）；T01/T02/T03/T04/T08 的 updates 声明补 `results`（T02/T03 逐阶段、逐组）；T02 复算断言更新输入 `results` 与录制 stage 请求逐组一致且非空；T02 的 results 声明由 `frozenGroupActionsAtStage` 生成，完整性守卫同时被"组 B 不得混入组 A 的行动"约束。
- 提示词：断言 action 契约含「输入 actor 指定的角色」「不一定是主角」「结合最新工作状态判断能否执行」；updates 含 results 时出现「已确认」句、时间扫描不出现。
- B3 冻结样本：updates 两样本补 `results`（T01 stage_unit 逐字值）。

**本轮验证**：前端全量 480/480（world-engine 418）、`tsc -p tsconfig.world-contract.json` 净、`tsc --noEmit` 净、`npm run build` 通过（lint 仅既有 warning）；后端 `python -X utf8 -m pytest -q` 923/923。

## 8. #7 pointPlan 逐人判断（2026-10-26）

**结论**：逐人跳过判断回到模型职责——计划只做点位切分，不再决定谁被问；省略不是跳过。空点（`actorIds` 为空）保留时间扫描承包槽位的原规则。

**调度器（`schedule.ts`）**

- 新增 `nextActor(view)`：从服务端 `working.cursor` 起按**冻结顺序**取下一个行动机会。槽位若只被**后序点**覆盖则推迟（本轮结束，不跳也不问——跳过会把它标成 visited、抹掉后序机会）；若**没有任何点覆盖**则在本点照常判断；已处理槽位（`groupActors`）绝不重复。
- `selectActorDecision` 以该单一入口取代 `actorsComplete` + 计划内查找：act → discover_group，skip → record_skip；多余分叉删除。
- 删除封存前的「程序补记跳过」分支——这正是「未被 pointPlan 覆盖 = 跳过」的偏差来源。
- `groupActors` 语义明确为「本点/本轮已处理」（在组内行动或显式跳过），`record_skip` 采纳时一律登记（原先只登记计划内人物），重试/回放不会二次询问。共同结算组成员不会再在自己的槽位上被问第二次（复核守卫 2）。
- 计划内人物、普通/瞬时/关联续点、空点时间扫描、successor 预约与叙事门槛的规则未改；`actorIds` 仍是点位切分的输入形状，wire/codec 不变。

**提示词**：`pointPlan` 契约补一句语义——`actorIds` 声明本点覆盖的冻结槽位，每个列出的槽位都会单独判断行动，未列出的槽位不得被当作跳过。

**场景与固定输出验证（T01，共享录制）**

- T01 的 `pointPlan` 只覆盖 person_a；旧实现由程序补记 b–f 五次 `record_skip`。现在 b–f 各有一次 `action` 调用（固定输出 `skip`）后再落 `record_skip`——transport 操作序列不变，模型调用 +5。
- 逐人判断需要「a 暂存后的最新工作态」：新增 B 预览标本 `b-preview-after-stage-s10`，body 逐字取自录制 s16（跳过只推进 visited/cursor，不改世界态与已暂存单元），测试断言其 workingState/pointProjection/mergedEntityDeltas 与 s16 全等。
- 录制 s16 预览留在原位置，改为 harness 校验位（`runInspect('s16')`）：驱动器不再发它（B 标本已覆盖同一读），但 s18–s20 的响应按 `$var` 引用 s16 捕获的 `workingStateDigest`，后移会破坏录制绑定——测试在跳过与封存之间发出该读，逐字核对 body、digest 链、独立 pin 与 s21 对齐。T01 因此分成两段控制器驱动（跳过之后 / 封存之前）。
- 端到端（`controller.test.ts`）与故障场景（T06）同步：段边界处理 s16、预算计数更新（e2e used 10→14、T06 used 8→13）、T06 的「复用已确认工作」断言收窄到 person_a 的行动/结算/更新。
- 复核守卫 2 的直接证据：旧 e2e 对已在共同组行动的 person_d 仍补记了一次 skip（夹具期望 5 次 skip），现在 person_d 既不询问也不补记（4 次 skip，b/c/e/f），模型调用序列与 `groupActors` 断言钉死该行为。

**验证（#7 交付时）**：前端全量 480/480（world-engine 418）、`tsc -p tsconfig.world-contract.json` 净、`tsc --noEmit` 净、`npm run build` 通过；后端 `python -X utf8 -m pytest -q` 923/923。

## 9. #9 continuation 输入复核（2026-10-26）

**复核结论**：#9 的缺口是「本轮状态变化」缺失——输入只有 `round + head + workingState`，没有本轮已提交点的 Δ；主角与当前世界本身已在 `workingState`（含 `protagonistId`/`characters`）里，再加重复字段没有意义。

**实现**

- 记忆新增 `roundChanges: {roundId, points:[{pointId, timeAdvance, entityDeltas}]} | null`，由提交成功的点投影累计（`commit_point` 采纳时按 `roundId` 追加，换 round 重置），continue/handback/cancel 后清空。数据源是控制器自己发出的 commit 请求，不新增读取。
- continuation 输入补 `roundChanges`：同 round 时为已提交点的时间与实体 Δ（按提交顺序）；**零本地历史时为 `null`**——会话在半途打开（如 T04 首个 assess_continuation）不能假装「本轮没有变化」。`workingState` 保持当前世界语义（最后一次 preview 的提交后投影），如此时也没有则如实为 `null`。
- 提示词契约补一句：输入含当前世界 `workingState`（主角在其中）与本轮已提交变化 `roundChanges`。
- B3 两样本：continuation-1 带一条已提交点变化，continuation-2 为零历史 `null`，note 记录依据。

**验证**

- 调度器单测：同 round 变化进入输入、零历史为 null、上一轮变化不串到本轮（roundId 不匹配即 null）。
- 真实控制器：提交后 `roundChanges` 记录点的时间与 Δ；continuation 模型输入含当前世界（`protagonistId`）与该变化；handback 结论后缓存清空。
- 场景：T04 两条 continuation 声明——第一条取自已录制的上一轮（T02 round_1：末点状态＋三个提交点的时间/Δ，见 §10），第二条为自动轮本点 Δ；输入由模型端口逐字核对。
- 提示词：断言 continuation 契约含当前世界与 `roundChanges`，输入序列化带出实际数组。

**边界（不掩盖，§10 已收紧）**：会话在 assess_continuation 半途打开且客户端没有本轮历史时，调度器在调用模型前明确停止（`continuation_context_missing:*`），补齐（服务端读/重建本轮点记录）归 H2；本批不新增读接口。

**验证数字**：前端全量 481/481（world-engine 419）、两套 tsc 净、`npm run build` 通过；后端 `python -X utf8 -m pytest -q` 923/923。清单第 1/3/4、5、6、7、8、9 项全部关闭（#6 叙事读取此前已关闭；H2 冻结组行动恢复与评估批次独立跟踪）。

## 10. #7/#9 定向复核跟进（2026-10-26，artifacts/slot-continuation-review.json）

复核确认两处守卫缺失（481 项测试与类型检查之外的定向探针）：

| 探针 | 实测 | 本轮处理 |
|---|---|---|
| `empty_plan_with_unvisited_frozen_slots` | `actorIds: []`＋游标 0＋六人未处理 → 直接进行时间扫描 | 删除「空计划即空点」的早退：`nextActor` 一律按冻结顺序取下一个未处理槽位；只有**人物机会都处理完**（visited 前缀到全序/游标走完）才是合法空点，时间扫描承包槽位。T03 的录制即旧偏差产物，按 §7 的同一套机制补齐。 |
| `continuation_without_world_or_round_history` | `workingState`、`roundChanges` 都为 null 仍调用模型并写入 handback | `continuationDecision` 先做完整性检查：缺任一即 `stop`（`continuation_context_missing:workingState,roundChanges`），零模型调用、零结论写入；H2 补读另做。 |

**T03 空点适配（录制不动，场景补交换）**

- T03 的 `plan` 零覆盖、六人未处理：在 begin 后、其预览标本之后插入 6 条 B-authored `record_skip`（固定输出=skip 对应的显式跳过），并顺延 revision 链：2..8（六次跳过）→ 9（stage_time_scan）→ 10（seal）→ 11（commit）；请求/响应成对重绑，拆分阶梯的边界预览（在建语料时按 begin 的旧 revision 生成）改为 8，stage 后的预览请求改为 9。轨迹文件与共享契约不动。
- 模型声明同步：六次 `action`（person_a..f，固定 `skip`，输入=begin 后预览的工作态）在时间扫描的阶段更新之前；测试断言调用序列与 ops 计数（T03 14→20）。

**T04 首条 continuation 的数据来源（不伪造）**

- T04 的世界正是 T02 的结束态（同 head/摘要/round/advance，两样本逐一核对，构建期断言）。场景从 T02 录制取「上一轮当前世界」＝s42 的 state，与「本轮已提交变化」＝三段 commit 请求点的时间/Δ；作为连续会话的内存种子（workingState + roundChanges）与 s2 的声明输入。新增守卫测试：抹掉这两块种子后，驱动直接 `continuation_context_missing`，零模型调用、零传输。

**其他回归**

- 合法空点的判定改由「人物机会已处理」表达：调度器空点单测改为 visited=全序；controller 的 split-updates 测试同样改为已访问空点。新增强制反例：零覆盖计划＋未处理槽位必须问 action。

**验证**：前端全量 484/484（world-engine 422）、两套 tsc 净、`npm run build` 通过；后端 `python -X utf8 -m pytest -q` 923/923。
