# B1 控制器设计补充（B 侧）

状态：2026-10-22，基于分支 `world-browser`（`79f8120`，契约摘要 `480d950c…`）；同日二轮修订：组扩张顺序/DFS、`updates` 调用粒度、`pointPlan` 边界、T03-collapse guard、错误路由、requestId 生命周期、preview 标本与 digest 策略；同日三轮：调度纯函数实现并经两轮评审修复闭环（complete 入口、scope 规律、stateKey、DFS 兄弟顺序、候选装配、act/skip 输出、updates split 与 canonical 序、全 actor skip 补时间扫描、缺 lease 叙事不再抛错）。§7 两项待 A 确认后开 harness 语料与 H1。本文是 [分工文档](../browser-world-state-work-split.md) §四 B1 行的实现层补充，替代原计划中与共享轨迹逐字消费相关的表述。

## 0. 验收口径：共享轨迹是契约标本，不是控制器金标

共享轨迹的序列含大量控制器正常推导不会发出的步骤，逐字消费与"从状态推导请求"不相容：

| 证据 | 步骤 | 性质 |
|---|---|---|
| `preview_point` 全部 11 份轨迹仅 T01 s16 一次 | T02/T03/T03-collapse/T04/T08 零 preview | 控制器拿 `workingState` 必须多次 preview，逐字消费必然对不上 |
| T01 s21–s23 | `get_state`/`list_points`/`narration_get` | 验收读取，控制器不停在这里 |
| T04 s15 | conclude 重复请求（`requestId` 同 s13，成功 replay） | 幂等重放验证，归 harness |
| T05 s2/s5/s6 | `checkpoint_pause`/`resume` | 外部命令；s3/s4 是 `lease_renew`/`narration_claim_renew` 心跳，B1 同样归 command 注入而非调度推导；且 paused 下 s7/s8 仍 `narration_claim/submit` |
| T06 s4 | 成功 replay（同 `requestId` 重发） | 与 s5–s9 错误探针一样归 harness |
| T06 s5–s9、T08 s8–s9、T07、T09 | `request_id_reused`/`stale_epoch`/`revision_mismatch`/`version_mismatch`/`point_time_locked`/`frozen_work_*`/`cache_missing`/`claim_fenced` | 故意非法请求或故障注入，控制器永远不该发出 |

分层结论：

1. **契约层（不变，已绿）**：共享轨迹继续由 `runTrace` + `FixtureWorldTransport` 逐字消费，65 项检查照旧。不改 `trace.schema.json`，不加 driver 标记。
2. **控制器层（B1 新增）**：B 自有场景夹具执行控制器，响应语料取自共享轨迹的 request/response。夹具步骤显式标注段落，harness 按段核对：

| 段 | 执行者 | 核对方式 |
|---|---|---|
| `controller` | 控制器推导请求 | harness 逐字核对 operation/request/scope，额外 preview 允许出现在声明位置 |
| `command` | harness 直发 | pause/resume/cancel/预算事件/心跳，响应交控制器重新调度 |
| `probe` | harness 直发 | 故意非法请求/重放，断言错误码与 clientAction |
| `inspect` | harness 直发 | `get_state`/`list_points`/`narration_get` 验收读取 |
| `stop` | 场景边界 | 控制器必须在此停住，后续请求视为缺陷 |

覆盖清单（11 份全列）：T01 单点全流程（含根点叙事）；T02 三点 normal/instant/linked + 组扩张 + 冻结文本反应；T02-empty-linked 空 linked + 时间扫描；T03 空点 60s 时间扫描（actionless 六步）；T03-collapse 预分配 task/change ID + 非空候选塌缩；T04 自动轮 continue + handback（两次 conclude，s15 replay 归 harness `probe`；**cancel 不在 T04，在 T08 s13**）；T05 命令驱动暂停/恢复 + 心跳；T06 错误/幂等语义改用 B 自有 fault transport 覆盖（s4 replay 与 s5–s9 探针不进控制器段）；T08 取 s1–s7 与 s10–s15 正常段（s8/s9 负探针归 harness；s13 `round_conclusion_cancel` 是 cancel 语义的覆盖落点）；T07/T09 留 B2/H2（刷新/接管/损坏恢复）。

## 1. ScenarioHarness 与 IdentityStore

- **IdentityStore**：
  - seed 优先——T02/T02-el/T03/T04/T05/T08 用输入种子的 group/trigger/point/nextRoundId；无 seed 才 `allocate_ids`（T01 s4、T03-collapse s2 均在点工作开始前）。
  - 分配范围按实证补全：T01 s4 `allocationKey: "chain_slots"` 一次分配 advance/input/round/point/group；T03-collapse s2 `allocationKey: "task_collapse_slots"` 分配 task×2/change/point。`allocationKey` 与 slot plan 是**场景声明（harness 配置，进控制器 memory）**，不属模型输出；模型输出中的 local refs 按 slotKey 绑定到预分配 ID（controller 不得自行造 ID）。
  - requestId 生命周期：**timeout/`request_in_progress` → 同内容沿用原 requestId 重发**；**definitive 拒绝（`fix_request`/`refresh_context`/`reacquire_lease` 等终态 clientAction）→ 旧操作退休，新操作新 requestId**。刷新后重建的请求不得沿用旧 requestId，防止撞 `request_id_reused`。
  - triggerKey 与 roll 规则（`create_rolls` 请求的 `ruleVersion`、`target`，T02 s18–s19 实证）是场景决策值，经模型端口 `targets` 任务输出供给，控制器与 harness 都不硬编码。
- **Harness** 职责：初始 world/lease 建立、玩家输入注入、`command`/`probe`/`inspect` 段执行（含心跳 lease_renew/narration_claim_renew、T06 式 replay）、停止边界判定、预算事件注入。
- **H1 修正**：不是"只换 transport"。固定夹具的 seed ID/固定 requestId/triggerKey 在真实 HTTP 下由 IdentityStore 的 allocate 分支与真实 requestId factory 替代，且控制器在 begin/stage 后的多次 preview 必须被最小 API 接受。H1 = 换 transport **加** harness 配置切换。→ 待 A 确认项 2。

## 2. `scheduleNext` 签名（修正）

pure 指对服务端状态 pure，允许携带控制器记忆：

- **输入**：context 全量（`control`: phase/paused/revision/gate/blockedReasons/canCompute；`world`: head.narrationStatus、advance.intent、activeInput、round{order,cursor,actedIds,visitedIds,conclusion}、lease、successor、activePointId）+ work 全量（phase/sealed/timeScanComplete/timeLocked/baseline.version/working{cursor,actedIds,visitedIds,settledUnitIds,intentStatus}/settledUnits/pendingGroup/successor）+ memory + 外部事件。
- **ControllerMemory**（B 本地，非服务权威）：已 stage 的 settlementGroups（stage payload 与 preview 缓存）、每源已分析 target 集/已创建 roll/已准入成员、workingState 缓存、preview 完成标记、待提交候选、预算计数、在途 requestId、本方预算暂停标记。
- **输出**（判别联合）：`{kind:'transport', operation, request, scope}` / `{kind:'read_working_state'}` / `{kind:'model', task, key, input}` / `{kind:'await_command', reason}` / `{kind:'stop', reason}`。retry 计数与退避在 driver 层，不进纯函数。

调度规则修正（对原计划的三处纠偏）：

1. `blockedReasons` 非空 ≠ 停，按块路由（全 8 种）：`phase_not_computable` → 控制面下一步（T01 s4 allocate 后即 `start_advance`）；`narration_pending` → 叙事管线（claim/generate/submit）；`narration_failed` → regenerate 路径（重试叙事生成）；`cache_missing` → regenerate；`claim_expired` → 重新 claim；`claim_fenced` → refresh_context 后重调度；`lease_invalid` → `lease_acquire`；`paused` → 见 §5（本地预算暂停才可 resume，否则等用户命令）。
2. `canCompute=false` 只挡状态计算模型任务（六步），不挡控制面操作、narration、`allocate_ids`、preview。
3. paused 挡状态计算与推进，不挡 narration claim/submit、`lease_renew`、`narration_claim_renew`（T05 s3/s4/s7/s8 实证）；叙事 ready 不自动清暂停（T05 语义）。

## 3. 模型任务表、pointPlan 与 workingState 读取策略

- **端口扩展**：`FixtureModelTask` 增 `time`（单点 timeAdvance 值）与 `pointPlan`（round 的点分段计划）。**pointPlan 必须带分段边界**：每点 `{kind, timeAdvance, actorIds}`，控制器在"该点 actorIds 全部作为源分析完毕并 stage/skip"时 seal——T02 为 P1 normal `[a,b]` elapsed 2s / P2 instant `[c,d]` 0s / P3 linked `[e,f]` instant 3s；T03 空点 `[]`（仅时间扫描）。没有边界控制器不知道何时 seal P1，会把 C/D 塞进 P1。time/pointPlan **必须走模型端口**（controller.test 锁定调用序列），fixture 的 output 才是种子值；harness 不得绕过端口直接喂值，否则 B3 必改接口。生产来源（提示词/规则）在 B3 定义。端口是 B 目录内文件，不属契约变更。
- **updates：调用粒度与输出形状都锁死（防 B3 改接口）**：
  - 输出形状：有序 stage 序列（位置→外貌→任务→小任务→个性→理智），每 stage 可为空。
  - 调用粒度：**按 stage 调用 1–6 次，task key 携带 stage 序号**；场景夹具声明拆分或合并。一次调用返回六个 stage 时，模型在同一输出里生成后序 stage（不存在"程序应用前序 stage 后再生成"）；按 stage 拆分调用时，后序调用才看到已应用的前序结果。两种模式端口都能表达，场景选择。
- **调用图（非线性，端口契约，controller.test 断言调用序列）**：action 每槽位/每源（round.order/cursor 推进）；targets 每确认行动源（输出含每目标 triggerKey 与 roll 规则 ruleVersion/target）；create_rolls 每确认目标（含已行动目标，按 targetId ASCII 排序）；reaction 每准入新成员；results/updates 每组；continuation 仅 assess_continuation；narration 每点（root 与每个提交点）；initial 仅 create_world 前（T01 的 `create_world` 模板即 `initial` 调用的输出经场景绑定，fixture 调用序列以 initial 开头）。
- **action 输出形状（已定，含 skip 分支）**：`{kind:'act', text}` 或 `{kind:'skip'}`——计划内 actor 返回 skip 时控制器发 `record_skip(slotActorId=actor)` 并推进槽位，不发 discover；这与"计划点不覆盖的 round 成员 leave-behind skip"（§4 select_actor 收尾路径）是两条不同路径。
- **updates split 落地形状**：场景在 memory 声明 `updatesStages`（空 = 单次合并调用）；split 时每次调用 key 带 stage（`<groupId>#<stage>` / `time_scan:<pointId>#<stage>`），driver 按 stage 累积输出；`checkUpdatesStages` 强制 canonical stage 序，乱序/重复直接拒绝。
- **scope 规律（fixture 逐字比对依赖）**：`checkpoint_*`/`create_rolls`/`commit_point`/`preview_point` 等 world 操作 scope 仅 `{worldId}`；`narration_claim`/`narration_submit` 为 `{worldId, pointId=head.pointId}`；`create_world` 为 `{}`。
- **guard（修正，T03-collapse 是正例不是反例）**：只拒绝**悬空引用**——后序 stage 需要的对象既不在输入状态、也不在本序列更早/同 stage 的输出中。跨 stage 的 ID 重叠若服务器接受则放行：T03-collapse 的 stage 候选把 v13 同时放进 `tasksAchieved` 与 `subtasksAdded`（pending，parentTaskId v12），最终 Δ 塌缩为 `subtasksAdded: v13 achieved`，这是合法路径，controller.test 用它锁行为。不得实现成"所有引用必须指向已有状态或更早 stage"的严格前向引用检查。
- **workingState 读取策略**：`begin_point` 后、每次 `stage_unit` 后、**`stage_time_scan` 后**（T03/T02-el 的时间扫描改变任务/个性/理智，必须重读）调用 `preview_point`，以返回的 `data.workingState` 作模型输入；提交前用 `data.pointProjection` + `data.mergedEntityDeltas` 核对 stage payload。
  - **缓存键（stateKey，语义失效）**：`(pointId, work.baseline.version, work.timeAdvance, working.settledUnitIds, timeScanComplete)`。按 `checkpointRevision` 失效在语义上过宽——T01 五次 `record_skip` 各升 revision，会多出五次无意义 preview；skip/pause 不改变工作态，不应失效。`timeScanComplete` 必须入键：时间扫描改写任务/个性/理智而不动 settledUnitIds，漏掉会跳过 scan 后的强制 preview。fixture 按本键写。
  - **preview 标本与 digest 策略**：中间 preview 响应（workingState/pointProjection/mergedEntityDeltas）不在共享轨迹里，由 B 手写标本；两个 digest 字段（`workingStateDigest`/`pointProjectionDigest`）为 schema 必填，B1 夹具用固定占位值并声明**digest 断言只覆盖最终 preview（T01 s16 语料，来自共享轨迹）与 commit 路径**，不对中间 preview 的占位 digest 做语义断言；B 不自行实现 canonical 摘要。若后续要对中间态做严格 digest 校验，另请 A 用测试侧工具生成（§7.2）。
  - preview 前置（契约已固定）：paused=false、headNarration=ready、gate=cleared、pointWork open|sealed。控制器发 `read_working_state` 前自查。

## 4. 组扩张与反应队列（T02/T02-el 实证循环，修订）

单源分析循环（frontier DFS，T02-empty-linked s4–s13 逐条实证）：

```text
源入队（首个源 = 槽位 actor，经 discover_group；新源 = 准入成员）
→ 模型 targets（该源的完整目标集 + 每目标 triggerKey + roll 规则）
→ extend_group 保存完整目标集（空集也保存，T02 s4/s8、T02-el s7/s10/s13）
→ 逐目标（按 targetId ASCII 排序，不是模型输出序：T02 s17 存 [d,a]、s18/s19 roll 执行 a→d）：
    create_rolls([target])（已行动目标也 roll，作判定输入；请求带 ruleVersion/target）
    → 响应 admitted=false → 下一目标
    → 响应 admitted=true → 模型 reaction → extend_group admittedMember（actionText + rollRefs，T02-el s6/s9/s12）
    → 该成员作为新源立即入队递归分析（DFS：T02-el s6 准入 d 后 s7 即分析 d 的空目标集，s8 才 roll 兄弟目标 e）
→ frontier 空 → 模型 results、updates → stage_unit（候选含 group 全量）
```

多点/多槽：select_actor 无 pendingGroup 时按 pointPlan 取下一 actor 开新组（T02 P1 s3–s6 为 a、s7–s10 为 b，两组各自 discover/extend/close/stage）。frontier 按组的 pendingGroup 与 memory 的 per-source 分析集共同判定。T02-empty-linked 追加：terminal instant group → 空 linked 点 → begin → `stage_time_scan` → seal → commit → 叙事。

实现拆分：**4a** 组扩张 frontier（T02/T02-el，纯函数测试先行）；**4b** pointPlan 分段/时间（time/pointPlan 任务接线）；**4c** 自动 round 与 conclusion（T04 continue/handback；cancel 覆盖归 T08 正常段）。

## 5. 错误与预算语义（18 码全表，已对 api-contract 核对）

| clientAction | 错误码 | 控制器动作 |
|---|---|---|
| retry_same_request | request_in_progress | 同内容沿用原 requestId 重发 |
| reacquire_lease | stale_epoch, lease_invalid | `lease_acquire`；接管/双心跳语义 B2/H2 深化 |
| refresh_context | revision_mismatch, phase_invalid, version_mismatch, claim_fenced | GET context 后重调度；旧操作退休、新操作新 requestId |
| wait_narration | narration_blocked | 控制器自己是叙事生成方：优先完成本方叙事管线（claim→generate→submit）；仅当 pending 不属于本方（如接管场景）才 await |
| regenerate_narration | cache_missing, claim_expired | 叙事重试路径（重新 claim 后生成提交） |
| resolve_gate | paused | **本地预算暂停**（memory 有标记）→ 可 `checkpoint_resume`；用户/服务暂停 → await 用户命令，resume 是 command 不是推导 |
| pause | frozen_work_missing, frozen_work_corrupt | `checkpoint_pause` 落库并停止提示修复/取消，不重采样（B2/H2 深化） |
| fix_request | request_id_reused（终态停）, point_time_locked, request_malformed, preview_budget_exceeded（413，请求/响应超限） | 停止或修参换新 requestId，不得静默重试 |
| none | protocol_version_unsupported | stop |

- **主动预算暂停 ≠ `preview_budget_exceeded`**：后者是 preview 的 413 体积错误。主动预算暂停是 B 的调用数/耗时/点数策略，经 `checkpoint_pause` 落库，由 harness 事件注入。
- 18 码的 httpStatus/retryable/clientAction 逐一 pin 进 schedule 单测，契约漂移时调度不得静默错位。注意三个反直觉映射：`paused → resolve_gate`（非 pause）、`claim_fenced → refresh_context`（非重领）、`narration_blocked → wait_narration` 的控制器侧实现是"先完成本方叙事"。

## 6. 实施顺序（替代原步骤 1–7）

1. 纯函数 + 手写状态（T01/T02/T03 的 context/work/memory 样本手写进测试）→ 调度决策单测（含 18 码 pin）
2. 控制器循环 T01（harness 段标注 + preview 标本按 §3 digest 策略落定后开工）
3. 组扩张 4a：T02/T02-empty-linked
4. pointPlan 分段/时间 + 自动轮 4b+4c：T02/T03/T03-collapse/T04 + T08 正常段（successor/time-lock/cancel）
5. 叙事/暂停/错误：T05 + B 自有 fault transport（T06 语义）
6. 验收记录入 browser.md；H1 待 A2 就绪后以 transport+harness 配置切换执行

代码落点（均 B 属地）：`frontend/src/lib/world-engine/` 增 `schedule.ts`（纯决策）、`projection.ts`（模型输入投影——B1 最大工作量，独立文件与测试，不塞进 schedule）、`controller.ts`（驱动循环）、`harness.ts` 与 `controller.test.ts`（夹具与验收）。

## 7. 待与 A 确认（阻塞 harness 场景语料与 H1；调度纯函数步骤已闭环）

1. **验收口径**：B1 控制器验收用 B 自有场景夹具（§0 分层），共享轨迹保持契约层逐字消费；A 侧无需改 trace.schema 与任何导出物，仅需认叮该分层作为 B1 验收标准。
2. **H1/A2 最小 API**：`begin_point`/`stage_unit`/`stage_time_scan` 后的多次 `preview_point` 必须可用（§3 读取策略依赖此）。preview 不入幂等表已明确，多次调用仅耗响应预算；若 A2 的 FixtureBaselineStore 对 preview 有次数/状态限制，请在 A2 交付说明中写明。**另请认叮 digest 策略**：中间 preview 的 B 夹具标本用手写状态 + 占位 digest（§3），B1 的 digest 断言只覆盖最终 preview 与 commit 路径；如 A 认为中间态也必须严格 digest，请用测试侧工具为 B 生成标本。
