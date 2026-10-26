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

---

# A2-1 三轮：控制服务修复续作与验收

日期：2026-10-23。基于 `da22a1b` 及中断时留下的 `control.py` / 服务测试改动续作。本轮全量 backend **1018 passed、0 failed**；控制服务 **37 passed**；共同验收入口 PASS。共同契约摘要仍为 `480d950c0f8062f8fdd75cb0620eb4ac97a6a247ca3f45f2057f6fe9e2ce7062`，未修改契约、共享轨迹或生成物。

## 本轮行为

1. **拒绝与回滚。** `ServiceRefusal` 的 HTTP 状态、客户端动作及 control 必需标记统一取 `ERROR_CODES`。服务在事务内将 `KernelViolation` 映射为既有码；封存时间伪造返回 `version_mismatch/prefix_binding_mismatch`，位置违规按 A1 计划映射为 `request_malformed`，拒绝不保存修改。
2. **响应与事务对应。** world/control/work 在写事务内构造并保存为该操作的快照，避免提交后另一个操作插入导致首个响应携带后一个操作的 revision 或工作态。完整成功信封在提交前按 registry 指定的 Success 模型校验；创建世界也先构造、校验再写入 world 和全局幂等记录。故意损坏成功 data 的回归证明不会留下世界、业务改动或幂等记录，同 requestId 修正后可正常执行。
3. **目标与成员冻结。** discover 的 `targetIds` 按契约读取为字符串 ID 列表；extend 的 `targets` 才是 `TargetSpec`，其身份投影与内部规格分开保存。None 与已确认的空集分开；未确认目标不能 close，已确认目标不能改写，重复成员不能覆盖行动；stage 的 actor 集必须与关闭组成员完全一致。None、空列表和非空 discover 目标均经 Success 模型验证。
4. **时间与跳过。** skip 只能记录当前 order 槽位，并在同一事务锁定点时间。begin 和尚未锁定时的 set_point_time 均校验 kind/time 组合，避免保存无法 preview/commit 的工作态；非法组合与后续改时拒绝均有回归。
5. **活动链与关联点。** preview/commit/conclude/cancel 核对存储中的 advanceId/roundId；commit 另核对 sequence 和 round trigger，不能靠同时伪造内外字段绕过。preview 对 instant/linked 填入当前已提交前驱。schema 内部绑定不一致仍为 `request_malformed`，合法形状但与存储不符为 `version_mismatch`。
6. **取消与叙事。** cancel 按 registry 从未提交工作状态也可执行，但要求 head narration ready。叙事 claim 固定签发模式，head token 不能作为 history 授权；history 提交不清 head gate。每点仍只有一份叙事权威，head 摘要读取该点真实状态，gate 独立阻止计算。ready 同代叙事允许同文本重复提交，改文本或迟到 failed 均拒绝，避免先降级再覆盖原文。
7. **claim 元数据。** claim 自身保存签发和到期时间；gate 清除后仍能按契约重新取回、续期该 claim，不再从已清空或其他点的 gate 读取时间。此项只保证 fixture 服务的字段与身份稳定；真实 TTL、epoch 接管、失败重试换代及恢复仍按 A3 验收。

中断时四个失败测试已修正：取消探针使用其实际创建世界的服务实例；instant/linked 分别使用独立工作态；内部字段不一致断言 schema 拒绝码；历史写入断言单一叙事状态与独立 gate，不再要求同一点同时为 ready 和 pending。

## 本地验证与后续

- `cd backend; python -X utf8 -m pytest -q tests/test_world_control_service.py`：37 passed。
- `cd backend; python -X utf8 -m pytest -q`：1018 passed（包含内核测试）。
- `python -X utf8 backend/scripts/check_world_interface_baseline.py`：v1/v2 导出一致；Python 109＋317；TS 类型、契约 38、轨迹 65；四类破坏探针全部拒绝。

本轮本地测试通过后，独立审查仍复现目标冻结粒度及 history 抢占当前头两处 P1，A2-1 暂不关闭；续修与验证见下节。后续 A2-2 为最小 HTTP 路由、错误信封、实际序列化预算及启动/CORS 配置，再与 B1 按 T01 完成 H1。当前结果仅为本地服务层与共同接口检查，不宣称 HTTP、H1/H2、SQLite 或远端 CI 已验收。

---

# A2-1 四轮：按成员冻结目标与头/历史 claim 流程修复

日期：2026-10-23。审查确认两处 P1 均为服务缺陷，前三轮的 37 项控制服务测试没有覆盖。**本节两处 P1 已获独立复审通过，可以关闭；允许进入 A2-2。** 复审独立探针确认多人目标分别冻结、未分析完关组回滚、当前头拒绝 history、旧头换代和遗留状态恢复；复跑 42/1023 及共同入口 PASS。A2-2 与 H1 另行验收。

## P1：目标冻结粒度

组内新增内部 `targetIdsBySource`、`targetSpecsBySource`，按 sourceId 保存每名成员的目标及 trigger 规格。discover 的目标只确认发起者；准入新成员时，该成员目标初始化为 None，显式空列表表示已确认无目标。extend 先核对 sourceId 为组内成员，再单独检查该成员是否已确认，不能用 A 的目标状态阻断 B 的首次确认，也不能覆盖任一已确认集合。对外 `pendingGroup.targetIds` 仍为所有已确认目标的去重并集，不改变共享 schema，也不下发内部字段。

close 要求每名成员都已确认目标且 frontier 为空。参数化回归覆盖 A 确认→B 加入→提前 close 拒绝且无写入→B 确认空/非空目标→A/B 改写拒绝→合法 close/stage；另检查非成员 source 拒绝、目标并集去重、stage 后已提交 actedIds 不提前变化。该场景在原组级冻结实现中会错误允许提前 close，并拒绝 B 的目标确认。

## P1：当前头与历史点的认领边界

history claim/renew/submit 只能指向历史点，当前 head 一律拒绝；history delete 同样不能借旧实现留下的 history token 操作当前头。根点刚创建与 head delete 后尚未重新认领两个窗口均有回归，拒绝不保存 claim 或幂等记录，随后有效租约可完成 head claim、submit、delete 和再次生成，最终 gate=none、canCompute=true。

旧头首次进入历史叙事再生成时，原 head claim 保留原签发模式，由新 generation/token 签发 history claim，fenceEpoch=null；不在同一代次上切换模式。历史流程覆盖 claim、携 currentClaim 取回、续期、ready、删除、再次再生成及旧 token 迟到拒绝；相同 requestId 的重放仍只返回不含 token 的摘要。无 currentClaim 的新请求不能取回已存在的 history token。历史再生成不改当前 head narration/gate、phase/revision、世界状态、已提交进度或工作态。

另外，对原实现已产生的当前头 history claim，持有效租约执行 head claim 会换代并恢复 head gate，可继续正常提交；回归以旧可达的 head=ready/gate=pending 状态验证该恢复路径。上一轮“history 写入当前头后只需保持 gate pending”的测试预期被撤回，改为当前头拒绝 history、真正历史点完整再生成及当前头继续推进的场景。

## 验证

- 控制服务：`cd backend; python -X utf8 -m pytest -q tests/test_world_control_service.py`，**42 passed**。
- 全量后端：`cd backend; python -X utf8 -m pytest -q`，**1023 passed、0 failed**。
- 共同入口：`python -X utf8 backend/scripts/check_world_interface_baseline.py`，**PASS**；v1/v2 导出一致，Python 109＋317、TS 类型/契约 38/轨迹 65、四类破坏探针均通过。

共同契约摘要及共享轨迹未变。本轮未运行 HTTP/H1/H2 或远端 CI；TTL、SQLite、租约接管与 roll 准入仍按各自阶段另行验收。

---

# A2-2：HTTP 接入与 H1 本地联调

日期：2026-10-23。基于 A2-1 复审通过后的工作树继续开发。交付 `backend/app/routers/worlds.py`，按既有 v2 registry 装配路径/方法、checkpoint/round-conclusion 分派、查询绑定和成功状态码；`app.main` 接入相同路由。独立 fixture 工厂为 `backend/app/world_app.py`，不初始化旧战役数据库或模型客户端。

## 服务与 HTTP 行为

- 所有操作检查 `X-World-Protocol-Version: 2`，JSON 写另检查 body 版本；JSON 的整数拼写 2.0 与共享 Python/JSON Schema 语义一致，布尔值不作为版本接受。
- 错误返回共享 `ErrorResponse`，包括表定的 HTTP 状态、retryable/clientAction 和适用的 control 快照；非法 JSON、未知字段、分派错误不会落到 FastAPI 默认 422。只在世界路由处理错误，不替换既有战役 API 的异常处理。只读查询错误沿用其既有错误码表，不扩展契约。
- URL 的 worldId/pointId 不能被 JSON 覆盖。DELETE narration 的点身份此前不在请求模型中；现单独核对 URL 点与 claim，幂等记录同时比较该路径身份，同 requestId 改指另一点拒绝。
- GET/DELETE 字符串查询转换为严格的整数/布尔参数，查询重复、未知字段或非法值拒绝；list_points 支持 after/limit。includeRecovery=true 即使使用 fixture store 也校验租约，fixture 不提供 A3 恢复载荷。
- preview 在解析前按实际接收字节检查 512 KiB 请求预算；完整响应经 UTF-8 JSON 序列化后检查 2 MiB，超限返回 413 与 details.limit=request/response。测试覆盖恰好限制和多一字节、实际 512 KiB 请求及含大量中文的超 2 MiB 响应；preview 不产生写入。
- FixtureBaselineStore 的 create_rolls 返回声明内的 phase_invalid，details.reason=fixture_store_unsupported。restore_group_work 经下节 P2 修复后单独校验租约和绑定，因 fixture 没有服务端接受的恢复来源而返回 frozen_work_missing/source_not_active；不伪造 A3 骰点或恢复成功。独立进程使用真实服务器时钟，但不据此宣称真实 TTL/接管已实现。

## 启动

在 A 工作树使用独立端口、单进程内存 store。以下示例 origin 应替换为浏览器实际 origin；`WORLD_ALLOWED_ORIGINS` 接受逗号分隔列表。

```powershell
$env:WORLD_ALLOWED_ORIGINS = 'http://127.0.0.1:3100'
Set-Location backend
python -X utf8 -m uvicorn app.world_app:create_world_app --factory --host 127.0.0.1 --port 8100 --workers 1
```

重启会清空 fixture 世界；多 worker 不共享 store。现有 `app.main:app` 也提供世界路由，沿用主应用已有 CORS 配置。H1 可重复入口（仓库根目录）：

```powershell
python -X utf8 backend/scripts/check_world_http_h1.py --browser-worktree D:/others/Jity/.local/world-browser-worktree --browser-channel msedge
```

入口在本地临时端口启动独立 fixture API 与 Vite 页面，真实 Edge headless 执行 B checkout 的 `ControllerDriver`、调度器和 `HttpWorldTransport`。不启动模型服务、不改 B 源码；退出时关闭其创建的 API、页面服务和浏览器。需要 B checkout 已安装的 Vite/Playwright 与指定浏览器。

## H1 证据与当前边界

可分享记录为 `artifacts/world-http-h1.json`，完整交换保留在忽略的 `.local/world-http-h1/`。记录实际 A/B HEAD、未提交状态、参测源文件哈希、浏览器版本、API 地址和 CORS origin，且检查所列源文件在执行前后未变化。本次 A HEAD 为 `da22a1b`，B HEAD 为 `1f50cdb`，两边均带未提交工作；源哈希标识本次实际参测内容，不把 HEAD 单独当作该工作树实现。

T01 两个样本均由真实 B 控制器执行创建世界、根点叙事、动态分配、start/begin/discover/extend/close/stage、五次 skip、seal/commit 与提交点叙事，再读取状态/点列表/叙事。pointPlan 使用分配响应中的 point ID；浏览器没有另写 apply 或摘要算法。begin 后和 stage/skip 后 preview 均重复一次，data 完全一致，revision 不变；每样本 26 次已记录 HTTP 交换、8 次固定模型任务，停在 continuation 之前，最终 revision=13、cursor=6、gate=none、canCompute=true。

Python 使用共享手写 expectedProjection 与实际捕获身份独立计算最终 WorldState 和摘要；final preview、commit、get_state 三方对拍，并以独立 commit 请求模板计算 pointProjectionDigest。额外 T03 两个样本通过真实浏览器 HTTP transport 的直接固定候选 harness 执行非空 stage_time_scan、同列表 preview（含重复）、commit/叙事/读取，验证任务达成、个性来源点、理智与时间；该辅例不冒称由 B 的 T03 控制器调度。

**B 侧待处理：默认 fetch 的浏览器接收者。** 直接使用 `new HttpWorldTransport(apiUrl)` 在真实 Edge 报 Illegal invocation：transport 以 `this.fetcher(...)` 调用未绑定的 window.fetch。本次使用该类已有的注入配置 `new HttpWorldTransport(apiUrl, window.fetch.bind(window))`，仍为真实原生 Fetch 和真实 CORS，没有 mock 响应。B 应修正默认实现（如通过箭头函数转发原生 fetch）并补浏览器覆盖。当前仅该显式配置下的本地链路通过；**A2-2 待复审，H1 尚未宣布共同验收关闭**。HTTP/ASGI 测试与浏览器联调分别记录；不宣称 SQLite、H2、远端 CI 或真实模型已验收。

## 本地验证

- `test_world_http.py`：24 项，控制服务原 42 项均由全量后端覆盖。
- `cd backend; python -X utf8 -m pytest -q`：**1047 passed、0 failed**。
- `python -X utf8 backend/scripts/check_world_interface_baseline.py`：**PASS**（v1/v2 导出、Python 109＋317、TS 类型/契约 38/轨迹 65、四类破坏探针）。共同契约摘要未变。
- H1 入口：**T01 两样本真实 B 控制器＋HTTP，T03 两样本浏览器直接固定候选 HTTP，独立状态与摘要对拍全部 PASS**。参测 Edge 155.0.4283.62；默认 fetch 问题与显式配置边界如上。
- `git diff --check`：通过。本批工作树改动尚未提交或推送。

---

# A2-2 二轮：三处 P2 复审修复

日期：2026-10-23。上轮 24/1047 与共同检查通过后，独立复审仍发现 HTTP 数值解析、fixture 恢复错误码、无请求模型读取的路径 ID 三处 P2；A2-2 保持未关闭。新增回归在修复前实跑为 **12 failed、3 passed**，确认不是仅调整测试预期。

1. **精确 JSON 解析。** HTTP 请求直接复用 `world.canonical.parse_json`，Decimal 保留数值原文精度，再按共享安全整数规则校验；统一拒绝重复键、非有限数及不合法 canonical 字符串，不另建解析规则。回归拒绝 `10.0000000000000001`、`9.999999999999999999999999` 和会被 float 下溢为 0 的 `1e-1000`；拒绝相同/不同重复 requestId 及嵌套重复 initialSanity，均不建世界、不消费幂等 ID。合法 `10.0`、`1e1`、`10.0000000000000000` 保持同一规范摘要，可重放整数版本的同 requestId。
2. **恢复拒绝属于该操作的错误表。** restore 增独立 fixture handler，在事务内按顺序核对租约、已提交绑定和工作点。没有 accepted restore reference 时返回已声明的 `frozen_work_missing`、`details.reason=source_not_active`；错误租约/错点分别返回 lease_invalid/version_mismatch。所有拒绝不修改状态、revision 或幂等记录。HTTP 测试适配器对每个错误统一核对 status 及该 operation 的 errorCodes，防止“合法 ErrorResponse 但不属于该操作”的错误再次漏过。
3. **所有路径身份都校验。** URL 的 worldId/pointId 在进入服务前统一按共享 Id 类型校验，包含没有 requestSchema 的 narration_get。空格、非 ASCII 字符、超长点 ID 返回表内 version_mismatch，不再返回无法通过 NarrationGetSuccess 的 200。合法但不存在的点仍可读取 schema 有效的 missing 响应。

浏览器联调入口另补真实 B HttpWorldTransport 错误消费探针：每个 T01 样本 begin 后发送合法形状的 fixture restore，确认收到 WorldApiError/frozen_work_missing（不是 ProtocolError/HTTP-error mismatch），并读取上下文核对无写入；最终另用非法 narration 路径验证 WorldApiError/version_mismatch。这些探针独立记录在分享报告的 browserErrorChecks，不计作控制器调度步骤。

本轮不修改共享 schema、registry、manifest 或轨迹；B 默认 fetch 的接收者问题仍未修复，浏览器继续使用显式绑定的原生 fetch。**三处 P2 本地修复待复审，A2-2 与 H1 保持未关闭。**

复验：`test_world_http.py` **39 项**、控制服务 **42 项**，聚焦联合运行 **81 passed**；全量后端 `python -X utf8 -m pytest -q` **1062 passed、0 failed**。共同接口入口 **PASS**（Python 109＋317、TS 类型/契约 38/轨迹 65、四类破坏探针）。绑定原生 fetch 的 Edge T01 两样本＋T03 两样本全部通过，T01 两样本各追加的 restore/非法路径错误消费探针也通过；分享记录已重新生成，包含本轮源哈希和 browserErrorChecks。`git diff --check` 通过，本轮结果与 A2-2 二轮改动一并提交推送；提交后 A2-2 与 H1 仍待复审，状态不变。

# A2-2/H1 B 侧复核与默认 fetch 路径联调（2026-10-24）

B 按「A=`d59353b`、B=`adfd506`」组合执行 A2-2 三处 P2 复核与 H1 真实浏览器联调。结论：**B 侧裁定 A2-2 与 H1 关闭**，证据如下。

## 三处 P2 复核（代码 + 回归）

1. **精确 JSON 解析**：路由在 `_json_body` 直接复用共享 `parse_json`（`json.loads(parse_float=Decimal)` 保数值原文精度、`object_pairs_hook` 拒重复键、`parse_constant` 拒非有限数，随后 `canonical_bytes` 全量校验），发生在任何 float 转换之前。
2. **恢复错误码**：`handle_restore_group_work` 独立 fixture handler，事务内按租约→已提交绑定→工作点顺序核验后以 restore 自己的错误表拒绝（`frozen_work_missing`、`details.reason=source_not_active`），不伪造 A3 恢复。
3. **读路径 ID 校验**：`_safe_id` 对全部请求的 URL worldId/pointId 统一校验（含无 requestSchema 的 narration_get），非法身份按该操作的错误表返回 version_mismatch。

复跑：`test_world_http.py` **39 passed**；全量后端（`cd backend` 按规程）**1062 passed、0 failed**（从仓库根直跑会有 campaign_wiring 两例 cwd 伪失败，非本批回归）；统一验收入口 **PASS**。

## H1：默认 fetch 路径（兑现 B `83dbe3b`）

H1 harness 原以 `window.fetch.bind(window)` 显式注入绕过 B 默认实现的接收者缺陷；本批改为**默认 fetcher 路径**（`new HttpWorldTransport(apiUrl)`，构造器自 `fetch.bind(globalThis)` 绑定，83dbe3b），A 侧脚本随 `b496da7` 提交。参测组合：A=`b496da7`（=d59353b+harness 默认路径改造，工作树仅遗留既有 `backend/_proj_create.json` 未跟踪文件）、B=`adfd506`（干净）。真实 Edge headless 155.0.4283.62，跨源真实 CORS，独立 fixture API 单进程。

结果 **PASS**（`artifacts/world-http-h1.json`，sourceUnchangedDuringRun=true）：

- **T01 双样本**（真实 B ControllerDriver + 调度器 + HttpWorldTransport 默认 fetch，服务端动态分配 worldId/pointId 等全部身份）：每样本 26 次已记录 HTTP 交换、8 次固定模型任务，最终 revision=13、cursor=6、gate=none；Python 以共享手写 expectedProjection + 实际捕获身份独立计算 WorldState/摘要，final preview、commit、get_state 三方对拍一致——sample_1 `0dbc65a69515265e…`、sample_2 `5e92c2391b6e905d…`；独立 pointProjectionDigest `32c69a56…`/`f689e5b8…`；begin/preview 重复与模型输入的 begin 期望态校验全过。
- **错误消费探针**（浏览器侧）：restore 合法形状收 `frozen_work_missing`（WorldApiError，非 ProtocolError）、拒绝后 world/control/work 三段无变化；非法 narration 路径收 `version_mismatch`。
- **T03 双样本**（浏览器 transport 直接固定候选 harness）：非空 stage_time_scan、同列表 preview 重复一致、commit/叙事/读取，任务达成/个性来源点/理智/时间四字段验证，摘要 `696b3e28…`/`2132568c…`。

两次运行（harness 改造前提交态与 b496da7 干净态）摘要逐位一致。**边界不变**：SQLite、H2 刷新/接管、真实模型与远端 CI 未验收；A3 另行。

---

# A3 阶段划分

2026-10-26 起沿用 A2 的两段交付方式：

| 阶段 | 范围 | 关闭标准 |
|---|---|---|
| A3-1：SQLite 事务与恢复服务 | 持久化、幂等、租约/claim/gate、roll、冻结工作复制、时间锁/后继预约及清理 | 后端正反例、真实 SQLite 故障矩阵、共同检查与独立复审通过 |
| A3-2：HTTP 刷新与接管联调 | 与 B 的真实持久化服务连接、刷新恢复、所有权交接及恢复后提交 | 指定 A/B 提交组合完成 H2，保留请求绑定、原文字节/候选哈希和迟到围栏证据 |

首批仅交付存储功能；本页末尾记录 A3-1 完整后端交付与 A3-2 的最新依赖。
协议消费、ASGI 和 transport 探针不替代 B 恢复客户端的正式 H2。

# A3-1 首批交付：SQLite 持久化与当前工作态恢复

日期：2026-10-26。分支 `world-server`，基线 `aacb572`，实现提交
`ce446c85dff0310bb9adf47ebcd3fbcc20930b07`，含 7 个实现/接入文件和 6 个测试模块。
**本批已实现部分经本地验证与独立复审通过；整个 A3 保持进行中。**
共同契约、共享轨迹、生成物与前端源码未改，A1/A2 继续由全量回归覆盖。

## 本轮行为

1. **存储与事务。** 新增 `backend/app/database/world_store.py` 的
   `SQLiteBaselineStore`，复用 A2 WorldService 和纯内核。写操作使用 BEGIN IMMEDIATE，
   创建、序列及成功幂等结果同事务提交，跨连接重发不重复生效；SQL 中断和进程退出回滚。
2. **核心账本与回放。** `world_repository.py` 写入并核对世界、输入、轮次、点、
   租约、叙事、快照及成功请求，保留关闭轮次与结束输入；`world_storage_v2.sql`
   与共同 SQL 逐字节一致。`replay_state` 从初始世界和关系历史重算并逐点核验摘要。
3. **工作态恢复。** `world_work_repository.py` 从关系表恢复当前组、原始行动、
   按成员确认的目标、结果、候选和工作游标；核心快照仅保留工作点绑定。已确认内容、
   时间锁和封存前缀不可改写，正式提交/取消保留 consumed/abandoned 行，损坏时阻断读取。
4. **校验修复与精简。** 修复第十单元排序、工作进度和输入消费校验、重复时间扫描等问题；
   完整性检查批量读取，只写变化数据，创建重放按 requestId 查询。正常写只在事务内
   读取世界，旧成功记录不可删除或改写，未变化工作态不重复保存。

非空旧库缺少 core/work schema 标记时拒绝自动迁移并保留数据，要求显式迁移或
新的开发库路径。核心适配快照仍有过渡依赖，当前未移除。

## 启动

从 backend 运行，数据库父目录须存在；未配置路径则启动报错。CORS 沿用
`WORLD_ALLOWED_ORIGINS`，A2 的默认内存入口保留。

```sh
WORLD_SQLITE_PATH=/absolute/path/world-dev.sqlite \
  python -m uvicorn app.world_app:create_persistent_world_app --factory \
  --host 127.0.0.1 --port 8100
```

## 测试

| 模块（backend/tests） | 项数 | 主要验证 |
|---|---:|---|
| test_world_sqlite_store.py | 13 | 创建/提交跨重开、并发幂等、原文字节、进程退出及无效响应回滚 |
| test_world_relational_store.py | 25 | 核心多表故障回滚、历史保留、无缓存回放、关系损坏与旧库拒绝 |
| test_world_work_store.py | 24 | 工作态关系恢复、None/空目标、原文不可改、终态保留、stage/取消中断 |
| test_world_work_acceptance_faults.py | 11 | 原文及时间载荷损坏、虚构行动进度、封存降级拒绝 |
| test_world_work_acceptance_paths.py | 11 | 十单元逐步重开、ASGI 完整 T01、多成员确认、时间扫描与输入消费 |
| test_world_store_efficiency.py | 9 | 历史增长不增加读取 SQL 次数、不重复写历史、定向重放及事务读取 |

本批聚焦 **93 passed，14.32 秒**；后端全量 **1155 passed，29.73 秒**，3 条已有
SWIG 弃用警告。共同入口 **PASS**：v1/v2 导出一致、Python 109＋317、TS 类型、
契约 38/轨迹 65、四类破坏探针通过；`git diff --check` 通过。

可重复命令（前两条从 backend 运行，共同入口从仓库根运行）：

```sh
python -m pytest -q tests/test_world_sqlite_store.py tests/test_world_relational_store.py \
  tests/test_world_work_store.py tests/test_world_work_acceptance_faults.py \
  tests/test_world_work_acceptance_paths.py tests/test_world_store_efficiency.py
python -m pytest -q
python backend/scripts/check_world_interface_baseline.py
```

本机复跑使用 Python 3.11.7、SQLite 3.41.2，后端命令的解释器为
`/opt/anaconda3/bin/python`，依赖路径为 `PYTHONPATH=.deps:/private/tmp/jity-a3-test-deps:.`。
共同入口使用同一解释器，并将以上 backend 依赖路径展开为绝对路径。

## 独立复审与交付结论

另一名 Codex 代理只读复查 3 个存储模块、服务/入口改动和 6 个测试模块，独立复跑
93 项，并在临时库执行额外探针：双进程并发提交恰好一次实际提交、一次重放，version
只增加一次且响应 data 相同；无缓存回放与提交态相同；尝试修改旧根节点摘要被
LedgerMismatch 拒绝，重开后记录不变。**本批范围未发现遗留阻断，可交付。**
该结论是代理独立复审，不代表 B 或人类复核。

实现提交 `ce446c8` 已推送至 `origin/world-server`；对应
[CI 40217640179](https://github.com/TandyBlow/Jity/actions/runs/40217640179)
的 backend、frontend、world-interface 三个作业全部 success。本节交付记录另作
文档提交，不改变上述已参测实现。

本批 HTTP 证据是每次请求重新创建应用/存储的本进程 ASGI 测试，未完成真实浏览器
刷新/接管。H1 的既有结论不外推为持久化入口或 H2 通过。

## 首批交付时的未完成边界（历史记录）

普通读取仍依赖过渡核心快照。租约 TTL、单调 epoch、claim/gate 生命周期、roll、
规范化分配记录、accepted/frozen 清单及原文复制、完整后继预约和引用清理继续待办。
此前临时库复核确认过期租约仍可新写、过期接管被拒、交接 epoch 不递增、根点未立即
签发 claim、create_rolls 未支持；它们是后续 A3 工作，未包含在本批通过结论中。

FC01–FC32 已有部分同类故障覆盖，但指定运行测试矩阵尚未逐项接入；共同轨迹的
契约/消费检查也不等于所有 runtime-A3 路径通过。后续须完成上述实现、真实 SQLite
故障矩阵，并与 B 记录指定 A/B 提交组合的 H2，之后才能关闭整个 A3。

---

# A3-1 完整后端交付：事务权威、冻结恢复与后继预约

日期：2026-10-26。分支 `world-server`，实现提交
`c19340fa5401b8d69045e7cafdafbe66cf45d974`，已推送至同名远端分支。
本批接在远端 `be87679` 之后，保留其 get_state 原始点记录字段及 preview/正式采纳
规则分离。**既定 A3-1 后端范围通过验收与独立复审；整个 A3 尚未完成。**
上节的首批缺口是历史记录，本节为当前状态。交付继续写在本文件。

## 实现与边界

1. **事务、幂等和读取。** `world_store.py` 将权威、工作、判定、冻结来源与复制
   记录放入同一个 SQLite 写事务；跨连接并发、重复请求、SQL 中断和进程退出均有
   回滚/重放检查。get_state 从初始世界和关系历史回放并核对摘要，同时返回所请求点
   自己的 previousPointId/timeAdvance/entityDeltas；重启及清理后读取一致。
2. **租约、claim 和 gate。** `authority.py` 保存服务端随机凭证与独立到期时间：
   lease 默认 120 秒，claim 默认 180 秒；释放、到期接管及重启均保持 epoch 单调。
   根点创建和点提交立即签发 head claim/gate；过期和迟到写入受围栏拒绝。合法 gate
   清理不增加 checkpoint revision，resume 不跳过叙事条件；叙事缓存丢失后通过新一代
   claim 恢复，读取不偷偷改库。租约和 claim 分别续期。
3. **身份与判定。** `judgments.py` / `world_judgment_repository.py` 持久化有类型和
   作用域的身份分配、不可变最终骰点及签发时的资格基线；准入/闭组核对真实判定，
   不接受浏览器指定结果。人物顺序由服务端按理智、身份排序，重复请求不重新掷骰。
4. **冻结原文与复制。** `world_frozen_repository.py` / `recovery.py` 保存已确认行动、
   逐源目标、结果及候选的原始字节/摘要与接受来源。接管后先隐藏旧 epoch 正文，仅
   返回可恢复来源；restore 原样核对来源和 manifest，再在事务内分配副本 attempt。
   同业务重复复制返回同一副本；缺失/损坏拒绝，不重采样。未确认行动或目标与已确认
   空目标明确区分；纯时间扫描按保存候选恢复。
5. **时间锁、后继和清理。** `successor.py` / `world_work_repository.py` 保存独立的
   后继工作、封存前缀及未来基线；前驱提交前仅允许边界源行动、目标及判定。前驱
   正式提交与后继提升原子完成，当前/后继分别绑定自己的原文与候选。六种合法单位
   的 instant/0 预约均保留原单位。维护入口只清理 consumed/abandoned 的短期载荷，
   保留活动引用、身份及判定记录。

启动沿用上节的 `create_persistent_world_app`、显式 WORLD_SQLITE_PATH 与
WORLD_ALLOWED_ORIGINS。非空旧库缺少所需 schema 标记时明确拒绝自动迁移，保留
原数据，开发时选新库路径或另做显式迁移。核心控制元数据仍使用 A2 适配记录并与
关系表核对；当前工作与后继不再在该记录中保存第二份正文。

## 验收

新增 authority、authority_integration、judgments、recovery、successor、transactions
六个测试模块共 **159 项**。FC01–FC32 的指定 runtimeTest 均有实际函数落点，使用
真实 SQLite 语句故障、并发连接及重开验证，不把冻结规格或录制响应当作事务通过。
既有存储/服务回归同步改为使用服务端分配身份。

- 最终提交后端全量：**1316 passed，66.55 秒**，3 条已有 SWIG 弃用警告。
- 共同入口：**PASS**，v1/v2 导出一致，Python 109＋317、TS 类型/契约 38/轨迹 65，
  四类破坏探针均被拒绝；`git diff --check` 通过。
- 独立只读复审：authority/恢复/FC 聚焦 103 项、successor/judgments 聚焦 50 项；
  发现合法零分钟预约被内部硬编码拒绝，修复后整个 successor 组 26 项通过。
  整合远端 get_state 后的读取/清理及 units ladder 复验 27 项通过。
  最终 successor＋transactions 联合 **63 passed**，未发现剩余既定后端阻断。
  非时序后继及 FC22 测试显式注入时钟；过期/接管另用可推进时钟检查，不改生产 TTL。
- [CI 40243749381](https://github.com/TandyBlow/Jity/actions/runs/40243749381)：
  对应实现 `c19340f`，backend、frontend、world-interface 三个作业全部 **success**。

命令沿用前节解释器与依赖设置；从 backend 运行全量与下列聚焦组，共同入口从根运行：

```sh
python -m pytest -q tests/test_world_authority.py tests/test_world_authority_integration.py \
  tests/test_world_judgments.py tests/test_world_recovery.py tests/test_world_successor.py \
  tests/test_world_transactions.py
python -m pytest -q
python backend/scripts/check_world_interface_baseline.py
```

## 真实浏览器前置验证与 A3-2 状态

A=`c19340f`、B=`ec68f6e4d63e23e9a6eb0d42cb0a59c4fb8040e0`，真实 Chrome
155.0.8059.85、默认 B HttpWorldTransport、真实 CORS 与独立 SQLite 服务：
**两组前置流程通过，两次实际服务重启**。检查页面堆内存已丢失、重启后幂等重放、
释放/接管后 epoch 递增、旧持有者迟到写拒绝、旧正文先隐藏、受控复制后原文字节与
候选哈希相同，以及恢复后正式提交且无重复消费。最终状态由 Python 手写预期独立
对拍；运行前后 A/B 源码身份一致。原始请求及凭证只放在忽略的 `.local` 下。

```sh
# 从根目录运行；参数是固定到指定 B 提交的独立测试副本
python backend/scripts/check_world_http_h2.py \
  --browser-worktree /absolute/path/to/browser-checkout --browser-channel chrome
```

该脚本是 A 侧固定轨迹驱动的传输/恢复前置检查，**不覆盖 B 新恢复控制器的完整 H2**。

2026-10-26 再次 fetch，B 已更新至 `8b080574bccdbadde1b89a23a7b55a41568835a8`，
其中 `cc70105` 已新增真实恢复客户端首批：新会话续期/申请租约、带凭证读取 recovery、
按来源受控复制、重读原文、分页恢复历史并核对快照，Controller/Session 已接线。
因此此前“B 没有恢复客户端”的判断已过时。B 的真实 HTTP 历史子检查使用旧 A
`be87679`，也不能替代本次 SQLite 完整联调。

**A3-2 当前依赖：** B 的 R1 提案要求恢复读取提供完整骰点事实、逐威胁处理状态及
有序 sourceStack；当前已冻结恢复投影只有判定身份引用，不能据此还原全部结果与
执行顺序。R1 文字方案已收敛，但正式 Python/schema、导出/夹具、B 消费及新契约摘要
尚未冻结。下一步先按共同变更流程落实这些读取能力，再固定新的 A/B 组合，运行
真实 B 恢复控制器的 SQLite 刷新、接管及后继接续全链。A3-2/H2 保持未关闭。
