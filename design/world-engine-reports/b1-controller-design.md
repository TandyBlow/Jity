# B1 控制器设计补充（B 侧）

状态：2026-10-22，基于分支 `world-browser`（`79f8120`，契约摘要 `480d950c…`）。§7 两项待 A 确认后定稿；确认前步骤 1–5 可先行，H1 不开跑。本文是 [分工文档](../browser-world-state-work-split.md) §四 B1 行的实现层补充，替代原计划中与共享轨迹逐字消费相关的表述。

## 0. 验收口径：共享轨迹是契约标本，不是控制器金标

共享轨迹的序列含大量控制器正常推导不会发出的步骤，逐字消费与"从状态推导请求"不相容：

| 证据 | 步骤 | 性质 |
|---|---|---|
| `preview_point` 全部 11 份轨迹仅 T01 s16 一次 | T02/T03/T03-collapse/T04/T08 零 preview | 控制器拿 `workingState` 必须多次 preview，逐字消费必然对不上 |
| T01 s21–s23 | `get_state`/`list_points`/`narration_get` | 验收读取，控制器不停在这里 |
| T04 s15 | conclude 重复请求（replay） | 幂等重放验证，归 harness |
| T05 s2/s5/s6 | `checkpoint_pause`/`resume` | 外部命令，非调度推导；且 paused 下 s7/s8 仍 `narration_claim/submit` |
| T06 s5–s9、T08 s8–s9、T07、T09 | `request_id_reused`/`stale_epoch`/`revision_mismatch`/`version_mismatch`/`point_time_locked`/`frozen_work_*`/`cache_missing`/`claim_fenced` | 故意非法请求或故障注入，控制器永远不该发出 |

分层结论：

1. **契约层（不变，已绿）**：共享轨迹继续由 `runTrace` + `FixtureWorldTransport` 逐字消费，65 项检查照旧。不改 `trace.schema.json`，不加 driver 标记。
2. **控制器层（B1 新增）**：B 自有场景夹具执行控制器，响应语料取自共享轨迹的 request/response。夹具步骤显式标注段落，harness 按段核对：

| 段 | 执行者 | 核对方式 |
|---|---|---|
| `controller` | 控制器推导请求 | harness 逐字核对 operation/request/scope，额外 preview 允许出现在声明位置 |
| `command` | harness 直发 | pause/resume/cancel/预算事件注入，响应交控制器重新调度 |
| `probe` | harness 直发 | 故意非法请求/重放，断言错误码与 clientAction |
| `inspect` | harness 直发 | `get_state`/`list_points`/`narration_get` 验收读取 |
| `stop` | 场景边界 | 控制器必须在此停住，后续请求视为缺陷 |

覆盖清单（11 份全列）：T01 单点全流程（含根点叙事）；T02 三点 normal/instant/linked + 组扩张 + 冻结文本反应；T02-empty-linked 空 linked + 时间扫描；T03 空点 60s 时间扫描（actionless 六步）；T03-collapse 预分配 task/change ID + 非空候选塌缩；T04 自动 round continue/handback/cancel（s15 replay 归 harness `probe`）；T05 命令驱动暂停/恢复；T06 错误/幂等语义改用 B 自有 fault transport 覆盖（s5–s9 探针不进控制器段）；T08 取 s1–s7 与 s10–s15 正常段（s8/s9 负探针归 harness）；T07/T09 留 B2/H2（刷新/接管/损坏恢复）。

## 1. ScenarioHarness 与 IdentityStore

- **IdentityStore**：seed 优先——T02/T02-el/T03/T04/T05/T08 用输入种子的 group/trigger/point/nextRoundId；无 seed 才 `allocate_ids`（T01 s4、T03-collapse s2 均在点工作开始前）。requestId factory：重试沿用原 requestId（幂等键语义），新业务操作新 requestId。triggerKey 由场景固定。
- **Harness** 职责：初始 world/lease 建立、玩家输入注入、时间/分段计划供给（§3）、`command`/`probe`/`inspect` 段执行、停止边界判定、预算事件注入。
- **H1 修正**：不是"只换 transport"。固定夹具的 seed ID/固定 requestId/triggerKey 在真实 HTTP 下由 IdentityStore 的 allocate 分支与真实 requestId factory 替代，且控制器在 begin/stage 后的多次 preview 必须被最小 API 接受。H1 = 换 transport **加** harness 配置切换。→ 待 A 确认项 2。

## 2. `scheduleNext` 签名（修正）

pure 指对服务端状态 pure，允许携带控制器记忆：

- **输入**：context 全量（`control`: phase/paused/revision/gate/blockedReasons/canCompute；`world`: head.narrationStatus、advance.intent、activeInput、round{order,cursor,actedIds,visitedIds,conclusion}、lease、successor、activePointId）+ work 全量（phase/sealed/timeScanComplete/timeLocked/baseline.version/working{cursor,actedIds,visitedIds,settledUnitIds,intentStatus}/settledUnits/pendingGroup/successor）+ memory + 外部事件。
- **ControllerMemory**（B 本地，非服务权威）：已 stage 的 settlementGroups（stage payload 与 preview 缓存）、每源已分析 target 集/已创建 roll/已准入成员、workingState 缓存、preview 完成标记、待提交候选、预算计数、在途 requestId。
- **输出**（判别联合）：`{kind:'transport', operation, request, scope}` / `{kind:'read_working_state'}` / `{kind:'model', task, key, input}` / `{kind:'await_command', reason}` / `{kind:'stop', reason}`。retry 计数与退避在 driver 层，不进纯函数。

调度规则修正（对原计划的三处纠偏）：

1. `blockedReasons` 非空 ≠ 停，按块路由：`phase_not_computable` → 控制面下一步（T01 s4 allocate 后即 `start_advance`）；`narration_pending` → claim/submit；`cache_missing` → regenerate；`claim_expired`/`claim_fenced` → 重领/refresh。
2. `canCompute=false` 只挡状态计算模型任务（六步），不挡控制面操作、narration、`allocate_ids`、preview。
3. paused 挡状态计算与推进，不挡 narration claim/submit、`lease_renew`、`narration_claim_renew`（T05 s3/s4/s7/s8 实证）；叙事 ready 不自动清暂停（T05 语义）。

## 3. 模型任务表与 workingState 读取策略

- **端口扩展**：`FixtureModelTask` 增 `time`（单点 timeAdvance 值）与 `pointPlan`（round 的点分段：normal/instant/linked 序列，T02 为 P1 normal 2s / P2 instant / P3 linked 3s，T03 空点 60s）。B1 场景夹具中由场景种子提供；生产来源（提示词/规则）在 B3 定义。端口是 B 目录内文件，不属契约变更。
- **updates 粒度（现在定死，防 B3 改接口）**：updates 输出定义为**有序 stage 序列**（位置→外貌→任务→小任务→个性→理智），每 stage 可为空；后序 stage 引用前序未产出目标时控制器拒绝。不采用"单次合并"语义；T01/T02 的全空 updates 不再是盲区，T03/T03-collapse 的非空候选测 guard。
- **调用图（非线性，端口契约，controller.test 断言调用序列）**：action 每槽位（round.order/cursor 推进）；targets 每确认行动；create_rolls 每确认目标（含已行动目标，按 targetId 排序，作判定输入）；reaction 每准入新成员；results/updates 每组；continuation 仅 assess_continuation；narration 每点（root 与每个提交点）；initial 仅 create_world 后。
- **workingState 读取策略**：`begin_point` 后、每次 `stage_unit` 后调用 `preview_point`，以 `(pointId, checkpointRevision, work.baseline.version)` 为缓存键取 `data.workingState` 作模型输入；提交前用 `data.pointProjection` + `data.mergedEntityDeltas` 核对 stage payload。preview 前置（契约已固定）：paused=false、headNarration=ready、gate=cleared、pointWork open|sealed。preview 不入幂等表、可重复调用，多次调用仅耗响应预算。

## 4. 组扩张与反应队列（T02 实证循环）

discover（模型 action）→ targets → `extend_group` 保存完整目标集（空集也保存）→ 按声明顺序逐目标 `create_rolls`（已行动目标也 roll）→ admission（`extend_group` admittedMember）→ 每准入目标 reaction（模型）→ 新成员作为新源递归分析（frontier）→ 无新源 → `close_group`。T02-empty-linked 追加：terminal instant group → 空 linked 点 → begin → `stage_time_scan` → seal → commit → 叙事。

实现拆分：**4a** 组扩张 frontier（T02/T02-el，纯函数测试先行）；**4b** 点分段/时间计划（`time`/`pointPlan` 任务接线）；**4c** 自动 round 与 conclusion/cancel（T04）。

## 5. 错误与预算语义（18 码全表，已对 api-contract 核对）

| clientAction | 错误码 | 控制器动作 |
|---|---|---|
| retry_same_request | request_in_progress | 沿用原 requestId 重发 |
| reacquire_lease | stale_epoch, lease_invalid | `lease_acquire`；接管/双心跳语义 B2/H2 深化 |
| refresh_context | revision_mismatch, phase_invalid, version_mismatch, claim_fenced | GET context 后重新调度 |
| wait_narration | narration_blocked | await_command，等 head 叙事 |
| regenerate_narration | cache_missing, claim_expired | 叙事重试路径 |
| resolve_gate | paused | 处理 gate/pause 语义 |
| pause | frozen_work_missing, frozen_work_corrupt | `checkpoint_pause` 落库并停止提示修复/取消，不重采样（B2/H2 深化） |
| fix_request | request_id_reused（终态停）, point_time_locked, request_malformed, preview_budget_exceeded（413，请求/响应超限） | 停止或修参，不得静默重试 |
| none | protocol_version_unsupported | stop |

- **主动预算暂停 ≠ `preview_budget_exceeded`**：后者是 preview 的 413 体积错误。主动预算暂停是 B 的调用数/耗时/点数策略，经 `checkpoint_pause` 落库，由 harness 事件注入。
- 18 码的 httpStatus/retryable/clientAction 逐一 pin 进 controller.test，契约漂移时调度不得静默错位。注意两个反直觉映射：`paused → resolve_gate`（非 pause）、`claim_fenced → refresh_context`（非重领）。

## 6. 实施顺序（替代原步骤 1–7）

1. 纯函数 + 手写状态（T01/T02/T03 的 context/work/memory 样本手写进测试）→ 调度决策单测
2. 控制器循环 T01（harness 段标注 + 端口扩展：time/pointPlan/updates 序列）
3. 组扩张 4a：T02/T02-empty-linked
4. 分段/时间/自动轮 4b+4c：T02/T03/T03-collapse/T04
5. 叙事/暂停/错误：T05 + B 自有 fault transport（T06 语义）
6. 验收记录入 browser.md；H1 待 A2 就绪后以 transport+harness 配置切换执行

代码落点（均 B 属地）：`frontend/src/lib/world-engine/` 增 `schedule.ts`（纯决策）、`controller.ts`（驱动循环）、`harness.ts` 与 `controller.test.ts`（夹具与验收）。

## 7. 待与 A 确认（阻塞 H1，不阻塞步骤 1–5）

1. **验收口径**：B1 控制器验收用 B 自有场景夹具（§0 分层），共享轨迹保持契约层逐字消费；A 侧无需改 trace.schema 与任何导出物，仅需认叮该分层作为 B1 验收标准。
2. **H1/A2 最小 API**：`begin_point`/`stage_unit` 后的多次 `preview_point` 必须可用（§3 读取策略依赖此）。preview 不入幂等表已明确，多次调用仅耗响应预算；若 A2 的 FixtureBaselineStore 对 preview 有次数/状态限制，请在 A2 交付说明中写明。
