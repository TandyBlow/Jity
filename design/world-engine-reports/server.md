# A：共同接口基线交付

日期：2026-10-22。共同接口实现：`e3b197a79f95adfbe215dddf5dfd3f9ed5b12823`；S1：`cabb04c`；v1：`26011c8`。接口摘要：`480d950c0f8062f8fdd75cb0620eb4ac97a6a247ca3f45f2057f6fe9e2ce7062`。本报告及 change-list 在随后文档提交中正式验收该实现；两条开发分支从包含冻结记录的同一提交建立并推送。

环境：Windows / PowerShell；Python 3.12.3、SQLite 3.50.4、Pydantic 2.13.4、jsonschema 4.26.0；Node 22.20.0、npm 10.9.3、TypeScript 5.9.3、Ajv 8.20.0、Vitest 5.0.1。CI 配置 Python 3.12、Node 22；Node 升级匹配现有 Vitest 5 的 engines 要求。

统一验收入口：`python -X utf8 backend/scripts/check_world_interface_baseline.py`。在原工作区和从该提交新建的干净 worktree 中运行，后者先执行全新 `npm ci`，均通过。统一入口覆盖 v1/v2 只读生成核对、Python 426 项（109+317）、TS 类型、契约 38 项、轨迹 65 项，以及四类故意破坏探针。默认 v1 导出仍是原 12 个产物字节；v2 为 5 个生成物，manifest 共 147 项。生成与检查不重写手写夹具，pin 由 Python 生成。

`npm --prefix frontend test` 为 10 文件、165 项通过；S1 JS 复核 60/0；lint 与生产 build 通过，保留既有 useBrowserAutoPlay hook 依赖 warning。额外全量 backend（`python -X utf8 -m pytest -q`）为 **923 passed、0 failed**，此前记录的 `test_campaign_wiring.py` 创建会话与 slot 过滤两例 404 已不存在。frontend 在 `07924f3` 的远端运行中失败于 npm ci；本验收提交 `05c213e` 是首次带 world-interface 作业的运行，backend、frontend、world-interface 三个作业全部 success。

CI 保留既有 backend pytest 与 frontend lint/build，新增 npm test 与 world-interface。统一入口中的聚焦消费测试和 frontend 作业全套有意重叠；空集、缺依赖或跳过必需检查均不计通过。

交付：Python v2 与 PrefixProjection、trace 模型；可装载 SQL 与 50 项约束反例；21 个独立规范向量；32 条 FC 故障规格（具体准备、请求夹具、故障点、预期和命名 A3 落点）；完整预期投影与不调用 apply 的摘要工具；11 份 T01～T09 双样本轨迹、全部 32 操作覆盖，无 fixture-only 豁免。

SQL 区分实际基线点与预约的封存前驱：后者可在前驱尚未提交时保存。root-ready 由玩家 round 触发器保留；pause/resume/restore 不套全局 ready 触发器；当前 epoch 在 max attempt 前过滤；TTL、引用/哈希真实性、跨表提交与提升由 A3 服务验证，DDL 测试不证明事务已实现。

Python 预期工具只对手写 expectedProjection 绑定身份，按既有 world-canonical-v1 计算摘要；拒绝业务响应变量、未声明/未捕获/覆盖变量与旧摘要。`--bindings` 供未来 HTTP 测试编排传入捕获身份，不接收实际状态或实际摘要作为答案。TS 读取这些预期值，不实现第二套编码/状态计算。

验收结论：IF-03/04a/04b/07/08 及 A0 共同前置通过。下一步 A1 纯内核，A2 控制状态/FixtureBaselineStore/最小 API，与 B1 用 T01 完成 H1；A3 按 FC01～FC32 实现 SQLite 中断、租约/claim、原文复制/去重/清理并用 T07 完成 H2。当前未运行生产服务或实际事务。

---

# A1a-1：内核函数面与模块划分

日期：2026-10-22。基线 `79f8120`，计划见 [a1-kernel-plan](../world-protocol/v2/a1-kernel-plan.md)。内核是对既有 `WorldState`（`backend/app/schemas/world/contracts.py`，权威不变）与 `canonical_digest`/`prefix_projection` 的纯函数；模块新建于 `backend/app/services/world/`，已实现 **17 个函数**（函数面 18 个，`next_working_progress` 待其 working 演进语义从轨迹钉死后实现）。语义权威为 v2 registry notes、v2 请求模型与 11 份轨迹；只消费 v2 类型（`v2.work.SettlementGroup`、`v2.requests.CommitPointRequest` 等），不 import v1 形态（`PointCommitRequest`/`RoundCheckpoint`/`SettlementCandidates`/`PreviewRequest`/`RollRequest`），以 import 边界断言固化。

## 模块与签名

| 模块 | 函数 | 说明 |
|---|---|---|
| `violations.py` | `Violation(kind, detail, path)`；`ViolationKind` 枚举 | 内部违规分类：ID 不可解析 / 内容语义非法 / 位置非法 / 覆盖不完整 / 时间锁；不进契约，A2 按 a1-kernel-plan §四映射 |
| `state.py` | `build_initial_state(initial: WorldInitialState) -> WorldState` | create_world 初始态：位置/外观取 initial，描述变更集为空，任务原样 |
| `state.py` | `state_digest(state: WorldState) -> Hex64` | `canonical_digest(state.model_dump(mode='json'))`；规范化恒等已验证 |
| `timing.py` | `advance_time(at: WorldTime, ta: TimeAdvance) -> WorldTime` | elapsed 按日历加 duration，instant 零时长；月/年加法规则待钉（见下） |
| `timing.py` | `time_lock_trigger(...) -> bool` | 首个 confirmed action/target/skip/time-scan 锁时间（`set_point_time` notes），A1a-4 定形 |
| `units.py` | `validate_unit(unit, world_roster)`；`validate_commit_groups(groups, world_roster)`；`unit_content_hash(unit)`；`begin_working`/`stage_working`/`skip_working`/`scan_working` | 覆盖规则（2026-10-22 裁决，已钉结论 #8）：taskCoverage=世界全体角色；personalityCoverage 无达成则空、有达成＝世界全员（组与扫描同规则，§6.3 为准）；角色专属字段键必须在册、个性变化⊆声明 coverage；跨单元同 actor 违规（拍板）。contentHash=候选集规范摘要。working 语义已按全部轨迹钉死（A2-0）：begin 从 round 已提交进度拷贝起步、仅 settledUnitIds 清空且 intent 投影当前值；discover/extend/close/seal 等不动 working；stage=cursor+actor 数、acted/visited 并入 actors、settledUnitIds 追加、intent 置 consumed；skip=cursor+1、visited 并入 slotActor；scan=cursor 到 order 全长、visited 补齐全员、intent 不动；head 提交进度只在 commit 提升 |
| `ladder.py` | `check_checkpoint(operation, work, control)` | 数据驱动解释 registry precondition 矩阵的结构可判部分（phase/pointWork/pendingGroup/settledUnits/timeLocked≡confirmedWork/paused/gate）；lease/narration/gate 时效与 activeAdvance/frozenSource 归 A2/A3 事务 |
| `merge.py` | `point_entity_deltas(groups, time_scan) -> dict[Id, EntityDelta]` | **入参即含 `time_scan: SettlementGroup | None`**（该点已存 `stage_time_scan` 候选）；外序显著；不变量 `entityDeltas == collapse(merge(groups ∪ timeScan))` |
| `merge.py` | `collapse_tasks(added, achieved) -> (added, achieved)` | 塌缩两步缺一不可：本点新增且已达成的 ID 从 `tasksAchieved` 摘除＋该新增记录置 `status:"achieved"`（T03-collapse 夹具；只做一半任一步都假失败） |
| `commit.py` | `verify_point_binding(point: TimelinePoint, sealed_prefix) -> tuple[Violation, ...]` | 提交点与封存前缀比对（kind/timeAdvance/绑定）；T08 s9 证实必需，出口 `version_mismatch`（`details.reason=prefix_binding_mismatch`），非 `point_time_locked`（后者只属 `set_point_time`） |
| `commit.py` | `apply_point(state, *, time_advance, deltas, point) -> WorldState` | 时间推进＋逐实体应用：positionSet 覆盖、描述变更入 `StoredDescriptionChange`（sourcePointId/sourceSequence/active＋supersedes 失活链）、sanity 覆盖、任务提升与挂树 |
| `preview.py` | `preview_working_state(state, time_advance, deltas) -> WorldState`；`preview_projection(...) -> PreviewData` 形 | 与 commit 同一条合并路，不落存储；`mergedEntityDeltas == pointProjection.entityDeltas` 由模型校验 |
| `preview.py` | `preview_over_budget(request_bytes, response_bytes) -> Violation \| None` | 请求 512 KiB / 响应 2 MiB 判定侧（`preview_budget_exceeded`） |
| `replay.py` | `replay_world(initial, applied_points) -> WorldState` | 从 canonical projection 重建（`get_state` notes）；终态摘要与轨迹 `expectedDigests`、投影夹具三方一致 |

## A1 覆盖的操作与留界

内核覆盖：`create_world`、`commit_point`、`preview_point`、`get_state`/`list_points` 的读出、`checkpoint_stage_unit`/`checkpoint_stage_time_scan` 的候选校验与 contentHash。不进 A1：lease/narration/rolls（A3）、pause/resume/conclude/cancel/prepare_successor/restore_group_work（A2/A3）；控制阶梯谓词（begin/discover/extend/close/stage/seal 的合法性）由 A1b 以纯函数交付、A2 消费，A1a 不实现。

## 已钉结论（B 实跑＋A 拍板，2026-10-22；原待钉点清零）

1. **unit contentHash**：`canonical_digest(SettlementGroup.model_validate(cand).model_dump(mode='json'))`——B 对 18 个 `stage_unit` 步骤 ×2 样本全命中（T01 `c7ff254c…` 等）；A1a-2 测试已固化（断言所有成功响应 `work.settledUnits[]`；T07/T09 恢复场景的组在前置场景 stage、本轨迹不带候选字节，副本语义归 A3）。职责出处：该「A1/A3 responsibility」原文在 `v2/projections.py` 的 `prefix_projection` docstring；registry/api-contract 只有 `get_state` 的 "Rebuilds ... from the canonical projection"，两者不混引。
2. **世界线与回放起点**（B 实测，摘要逐位；三条分支并排，回放各自独立挂起点）：

```
9301b799 (root_0, 11:59:00/0)
├ 32256da8 (11:59:02/0, 无 Δ；= root 只换时间，T02 s12 / T08 s10 实测)
│   ├ T02 p1 → p2 instant 9dd127b0 (11:59:02/1) → p3 linked 3s 85848d51 (=segmented, 11:59:05/0)
│   │      └ T04 p4 +2s e189aed7 (11:59:07/0)；T03-collapse p4 +2s 4bbc7728
│   ├ T08 p1（s9 error 跳过）
│   └ T02-empty-linked p2 同 9dd127b0 → p3 linked 0s 312f65d3 (11:59:02/2)
├ 4f5a33e7 (11:59:02/0 ＋ person_a→corridor)   ← T01 p1（= normal 快照）
└ 61569325 (12:00:00/0, +60s)                  ← T03 time_only（= time 快照）
```

`4f5a33e7` 与 `32256da8` 是**兄弟节点**（同一时刻 11:59:02/0，前者多 person_a 位移）：T02 系回放绝不能挂在 T01 终态之后。回放与不变量**必须过滤 `responseKind == 'success'`**：T08 s9 是 `commit_point` 409 `version_mismatch`/`prefix_binding_mismatch`（时间 3s 与已封存前缀 2s 不符），不是成功 commit。
3. **时间语义**（B 五锚点全部吻合）：零时长 instant 点在同一 `dateTime` 上递增 `instantOrdinal`，有推进的点重置为 0；`32256da8`=11:59:02/0、`9dd127b0`=/1、`312f65d3`=/2、`85848d51`=11:59:05/0、`e189aed7`=11:59:07/0。A1a-4 照此实现。
4. **preview 边界**：只吃请求里的 `settlementGroups`，绝不叠加已存 settledUnits（追加型变化会重复计）；A1b 补「同点外貌变化被 preview 两次只出现一次」断言。
5. **supersedes 失活链**：同点新增链跨组＝同点 supersedes，schema 已禁，merge 阶段判违规；跨点只允许引用旧点 id，旧记录 `active=false`，新记录 `sourcePointId/sourceSequence` 取提交点。
6. **跨组 positionSet（拍板）**：沿用 v1 意图——跨单元同 actor 判违规（内容语义非法→`request_malformed`），位置冲突随之不可达；不取 last-wins（把「谁生效」绑到外序语义且无夹具支撑）。
7. **月/年时长**：v2 全夹具零覆盖；定为公历夹月末（clamp to month end），A1b 自建夹具，H1 记一笔待确认。
8. **覆盖规则（B 审出、2026-10-22 裁决）**：`taskCoverageIds`＝**世界全体角色**（T03-collapse 单人组仍覆盖 6 人，非 round roster——v1「roster 覆盖」意图有误）；`personalityCoverageIds` 无达成＝空，**有达成＝世界全体**（workflow 设计 §6.3「扫描所有人物/不得只检查共同结算成员」为准；组与 time-scan 同规则）。T03-collapse 组（coverage=actors）为**已知偏差夹具**：轨迹/manifest 不动，validate 断言其 coverage 违规，回放不走 validate 不受影响；**处理期限＝首次把该场景用于成功联调之前**——届时按 §2.2 更新共享夹具（双样本已验证：改为全员 coverage 后校验通过、合并 Δ 不变，仅 contentHash 随候选集字节改变；A1b-2 先以本地正例覆盖新规则）。角色专属字段键（tasksAchieved/personalities/sanities/subtasksAdded）必须在册，个性变化必须落在声明的 coverage 内。`set_point_time`/`record_skip` 另有矩阵未载的局部不变量：要求 open work。B 的 schedule.ts coverage 生成（round.order）需同步为世界全体。

## B1 §7 确认

日期：2026-10-23。对应 B 侧 [b1-controller-design §7](https://github.com/TandyBlow/Jity/blob/38c464dce59bb80d39f4a49845d1c42abe0e863c/design/world-engine-reports/b1-controller-design.md#7-待与-a-确认阻塞-harness-场景语料与-h1调度纯函数步骤已闭环)。本记录确认设计要求和 B1 验收口径；A2 实际服务能力另经 H1 验证。

确认时的代码身份：A 为 `world-server` 的 `b29d898a1c2e12a40bc4fccea4558a22f86a3fad`；B 为 `world-browser` 的 `38c464dce59bb80d39f4a49845d1c42abe0e863c`。共同接口实现基线为 `e3b197a79f95adfbe215dddf5dfd3f9ed5b12823`，协议版本为 2，契约摘要为 `480d950c0f8062f8fdd75cb0620eb4ac97a6a247ca3f45f2057f6fe9e2ce7062`。这些身份用于本次确认，H1 将另记实际参测的 A/B 提交组合。

### 1. B1 控制器验收分层：认可

认可 B 使用自有场景夹具，响应语料取自共享轨迹，按以下分段验收：

| 分段 | 执行与验收要求 |
|---|---|
| `controller` | 由真实 driver 推导请求，严格核对 operation、request、scope 及模型调用顺序 |
| `command` | 注入暂停、恢复、取消、预算事件及心跳；作为外部命令处理 |
| `probe` | 执行故意非法请求、重放和故障探针，断言相应错误及恢复行为 |
| `inspect` | 执行验收读取 |
| `stop` | 明确场景停止边界，边界后的额外执行视为失败 |

控制器所需额外 preview 仅允许出现在夹具声明的位置。共享轨迹继续用于契约层逐字消费，既有 65 项轨迹检查保留；本确认不修改共享轨迹格式、轨迹内容或契约导出物。B1 控制器夹具通过与真实 HTTP 联调分别记录结果。无阻塞 harness/T01 语料开发的修订要求。

### 2. preview 使用要求及 digest 策略：认可

在契约前置条件与绑定成立时，A2 须支持 `begin_point`、`stage_unit`、`stage_time_scan` 后调用 `preview_point`，并允许同一点多次 preview，不增设只能调用一次的限制。前置条件沿用 registry：`paused=false`、head narration ready、gate cleared、point work 为 open 或 sealed；身份、版本和 checkpoint revision 按现有请求字段核对。沿用最多 32 个单元、请求 JSON 512 KiB、响应 2 MiB 的限制；实际响应字节由 A2 服务层序列化后测量。

每次 preview 从同一权威基线及请求的完整 `settlementGroups` 重算，不将上次工作态当作新基线，不再叠加已保存单元；时间只应用一次。纯时间扫描候选以 `groupId=null` 单元放在同一个列表内，扫描后的 preview 必须反映该候选的状态变化。preview 不带 requestId、不进入幂等表、不推进 revision 或已提交状态。

认可 B1 夹具采用以下摘要策略：

- 共享轨迹未提供的中间 preview，由 B 编写工作态标本，digest 使用符合 schema 的占位值，并在 B 自有夹具或验收说明中明确标注其占位性质。
- 中间占位 digest 不作为状态计算、规范编码或摘要一致性的语义证据，也不替代真实服务返回的摘要。
- 最终 preview（T01 s16）及 commit 路径使用共享独立预期和对应身份绑定进行摘要断言，不能将实际响应摘要同时作为预期。
- B 不另写 canonical 摘要算法。本轮不要求 B1 的中间 preview 校验真实 digest，A 提供额外中间态标本或工具不构成 harness 开工前置。

### 当前实现与 H1 安排

当前 A 已有纯内核 `backend/app/services/world/preview.py`：`preview_point(state, point, groups)` 复用 merge/apply 生成完整 wire data 及真实摘要，`preview_over_budget` 提供字节预算判定；已有 T01 s16 契约/摘要锚点和 T03 纯时间 preview 对拍测试。该实现状态不代表 FixtureBaselineStore、HTTP 路由、请求绑定校验和实际序列化预算已交付，也不代表 H1 已通过。

A2 最小服务与 B1 harness 就绪后，A 提供 FixtureBaselineStore、服务启动方式及地址/CORS 配置，B 以真实 driver、HTTP transport 和相应 harness 配置完成 T01 普通点 H1，覆盖创建世界/根点叙事、启动 round、begin/discover/extend/close/stage/seal/commit 及提交点叙事。H1 检查 begin/stage 后 preview、同点重复 preview 的状态与摘要稳定性、动态身份绑定、实际请求/响应序列化，以及最终 preview/commit/读取状态的摘要一致性；配套纯时间场景检查 stage_time_scan 后 preview，另检查真实字节预算边界。真实 HTTP 下使用 A 返回的真实 digest，中间占位值仅保留在 B1 的固定响应夹具中。

H1 结果须记录实际 A/B 提交、共同契约摘要、启动配置、执行步骤、身份绑定及检查结果。覆盖规则的 T03-collapse 已知偏差仍按已钉结论 #8，在首次将该场景用于成功联调前处理；本确认不宣称 SQLite 崩溃恢复或 H2 已验收。

## 固定预期绑定（A1a-2 直接采用）

- `fixtures/projections/{normal,segmented,time}.expected.json` 为 **WorldState 终态快照**（同一学校世界，时间 11:59:02/11:59:05/12:00:00 对应 T01/T02/T03 终态），`canonical_digest(WorldState.model_validate(doc).model_dump(mode='json'))` 与轨迹 **sample_1** 的 `expectedDigests` 相等（`4f5a33e7`/`85848d51`/`61569325`；B 以三条独立路径复现）。**sample_2 是不同身份/业务变量的另一条世界**（`952edfa2`/`f59d6d3b`/`908c8ef8`），不与快照等值；回放逐样本独立跑，快照不充当 sample_2 预期。
- `description-collapse.expected.json` 是 DescriptionChange 形态片段、`task-normalization.expected.json` 是 EntityDelta 形态片段——塌缩/归一化行为断言比对对应片段，不是整状态。
- 回放配方：以轨迹 `samples[i].values` 实例化各步请求 → 依次 apply 轨迹内全部成功 commit → 终态摘要对 `expectedDigests`。起点按 s1 `get_context` 的 head 摘要映射（B 实测）：`9301b799`＝root 初始态（T01/T02/T05/T06/T08 等直接从 root 起步，T02 的无 Δ 时间点在轨迹内 commit）、`32256da8`＝root＋无 Δ elapsed 2s（T02-empty-linked）、`85848d51`＝segmented 快照（T03-collapse/T04）；三条分支互相独立，不存在跨轨迹链式回放。


---

# A2-1 二轮：独立评审八项修复与轨迹对齐

日期：2026-10-23。A2-1 首轮交付（`fb46520`）经独立探针复现 7×P1 + 1×P2 后暂不关闭；本轮在 `world-server` 上全部修复并固化探针。全量 backend **999 passed、0 failed**（基线 986：-5 简化测试 +18 新测试），本地门 6 模块 92 项 PASS，共同验收入口 PASS（v1/v2 导出、Python 契约、TS 契约与 65 轨迹、四类破坏探针）。

## 八项修复

1. **写操作统一绑定与门槛**（control.py `_bind_expected`/`_bind_work_point`/`_ladder`）：所有 `CheckpointRequest` 写（含 start_advance/begin/conclude/cancel/preview）统一核对 expectedPointId=已提交 head、expectedVersion、expectedCheckpointRevision=操作前 revision；带 pointId 的检查点写核对 pointId=活动工作点；narration head 模式经 `_bind_head_mode` 强制租约/epoch 且只允许指向当前 head；conclude/cancel 补跑 ladder（phase=assess_continuation、gate cleared）。
2. **提交前不改已提交状态**：begin 不再移动 headPointId（轨迹 s7-s17 的 expectedPointId 恒为捕获的 root，正是该语义）；stage/skip 不再直接改 `advance.intentStatus`——消费只发生在 `work.working.intentStatus` 投影里，commit_point 才提升 head、round 游标与 intent（T01 s18 响应 intentStatus=consumed 与该提升一致）。
3. **冻结核验全量化**：stage 补 `validate_commit_groups`（coverage 全员/roster，违反分别映射 request_malformed/version_mismatch）与 groupId 三方一致性；commit 逐单元比对 groupId、memberIds、`unit_content_hash`（封存后改候选内容即使同步改 Δ 也被 `prefix_binding_mismatch` 拒绝），并复核 `point.previousPointId == head`。
4. **幂等纳入同一事务**：普通写在 transact 内部先查幂等表再执行（并发重发同一 begin：一个成功一个重放，不再 phase_invalid）；create_world 在 store 锁内查全局表后建世界（同 requestId 不再建出第二个世界；不同载荷同 ID → request_id_reused）。
5. **preview 与 lease_renew 跑通**：preview 走 ComputeResult 信封（无 requestId/requestHash/replayed），handler 复用 `preview.py` 配方（sequence=len(points)+1、kind/previousPointId/trigger 取自 work 与 round，digest 单层编码），同点重复 preview 摘要稳定、不推进 revision；lease_renew 修 `_now(store)` 签名。
6. **叙事按 point 单一权威**：`narrations[pointId]` 为唯一存储（root 建于创建、新点建于 commit），head 摘要与 gate 全部派生；gate 只在「ready 且 pointId==headPointId」的 submit 清除——补写历史叙事不再动当前 head 的 gate；未提交/未知点 claim 拒 version_mismatch。轨迹钉死的新规则：**fresh claim（replayed=false）必须带 claimToken**（NarrationClaimSuccess 校验器），无 token summary 只出现在 replay。
7. **ID 分配去碰撞**：桶键改为 (scope, slotKey)，新 ID 用 world 内单调计数器 `f"{kind}_{n}"`——`first_same`/`other_same` 后四位碰撞复现不再成立，同 slotKey 不同 scope 不再串号。
8. **get_state 按 point**：`pointStates[pointId]` 缓存 {version, state, stateDigest}（root 建于创建、commit 写入），请求 root 返回 initial 态 version=0，未指点返回 head，未知点拒 version_mismatch。

## 轨迹/契约对齐中钉死的新语义

- **revision 算术**：T01 s5-s18 逐期望核对——每个检查点操作（含 begin_point）消费一个 revision：start_advance→1、begin→2、discover→3、extend→4、close→5、stage→6、skip×5→11、seal→12、commit→13。首轮测试流程在 begin 后少加 1，被缺失的校验掩盖；本轮修正。
- **信封形状**：写操作按 `OperationResult` 全量携带 world/control/work；get_context 按 `ContextResponse`（补 activeInput：仅 pending 输入链携带文本；recovery 恒 null 留 A3）；get_state/list_points/narration_get 按 `ReadResult`（无 operation/requestId/requestHash/replayed）；preview 按 `ComputeResult`。无 advance 的 world.advance 固定 `{advanceId:null, inputId:null, intentStatus:"expired", inputAvailable:false}`；`inputAvailable`=advance 链存在（T01 s18 consumed 时仍 true）。create data 的 lease 为 LeaseGrant 三字段（holderId 不上 wire）。
- **wire 字面量**：conclude/cancel 的 operation 字面量为 `conclude`/`cancel`；lease_release 请求体无 worldId（路径参数），服务按原始 dict 路由、按模型字段过滤验证；PendingGroupView 不含 actionTexts（内部存储不下发）。

## 测试

`test_world_control_service.py` 重写：T01 全序（含 s16 位双 preview）每步按导出 Success 类验证信封；八项探针各成回归测试（绑定四连拒、租约栅栏、conclude 被 gate 阻断、stage coverage/roster 拒、封存候选篡改三连拒、create/begin 幂等与线程级并发重放、preview 中程执行与租约续期、历史叙事不清 gate、分配唯一性、历史/未知点 get_state）。HTTP 路由（A2-2）仍按计划押后。
