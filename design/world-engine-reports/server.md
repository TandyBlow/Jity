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

日期：2026-10-22。基线 `79f8120`，计划见 [a1-kernel-plan](../world-protocol/v2/a1-kernel-plan.md)。内核是对既有 `WorldState`（`backend/app/schemas/world/contracts.py`，权威不变）与 `canonical_digest`/`prefix_projection` 的纯函数；模块新建于 `backend/app/services/world/`。语义权威为 v2 registry notes、v2 请求模型与 11 份轨迹；只消费 v2 类型（`v2.work.SettlementGroup`、`v2.requests.CommitPointRequest` 等），不 import v1 形态（`PointCommitRequest`/`RoundCheckpoint`/`SettlementCandidates`/`PreviewRequest`/`RollRequest`），以 import 边界断言固化。

## 模块与签名

| 模块 | 函数 | 说明 |
|---|---|---|
| `violations.py` | `Violation(kind, detail, path)`；`ViolationKind` 枚举 | 内部违规分类：ID 不可解析 / 内容语义非法 / 位置非法 / 覆盖不完整 / 时间锁；不进契约，A2 按 a1-kernel-plan §四映射 |
| `state.py` | `build_initial_state(initial: WorldInitialState) -> WorldState` | create_world 初始态：位置/外观取 initial，描述变更集为空，任务原样 |
| `state.py` | `state_digest(state: WorldState) -> Hex64` | `canonical_digest(state.model_dump(mode='json'))`；规范化恒等已验证 |
| `timing.py` | `advance_time(at: WorldTime, ta: TimeAdvance) -> WorldTime` | elapsed 按日历加 duration，instant 零时长；月/年加法规则待钉（见下） |
| `timing.py` | `time_lock_trigger(...) -> bool` | 首个 confirmed action/target/skip/time-scan 锁时间（`set_point_time` notes），A1a-4 定形 |
| `units.py` | `validate_unit(unit: SettlementGroup, roster: frozenset[Id]) -> tuple[Violation, ...]` | schema 之外的状态级单元校验：actor 在册、六阶段交叉、覆盖清单 |
| `units.py` | `unit_content_hash(unit: SettlementGroup) -> Hex64` | 绑定完整有序候选集（`SettledUnitView.contentHash`）；公式 A1a-3 用 T01 响应复算钉死 |
| `units.py` | `next_working_progress(...) -> WorkingProgress` | stage_unit/skip 后的工作进度推进纯函数，A2 决定何时调用 |
| `merge.py` | `point_entity_deltas(groups, time_scan) -> dict[Id, EntityDelta]` | **入参即含 `time_scan: SettlementGroup | None`**（该点已存 `stage_time_scan` 候选）；外序显著；不变量 `entityDeltas == collapse(merge(groups ∪ timeScan))` |
| `merge.py` | `collapse_tasks(added, achieved) -> (added, achieved)` | 塌缩两步缺一不可：本点新增且已达成的 ID 从 `tasksAchieved` 摘除＋该新增记录置 `status:"achieved"`（T03-collapse 夹具；只做一半任一步都假失败） |
| `commit.py` | `apply_point(state, *, time_advance, deltas, point) -> WorldState` | 时间推进＋逐实体应用：positionSet 覆盖、描述变更入 `StoredDescriptionChange`（sourcePointId/sourceSequence/active＋supersedes 失活链）、sanity 覆盖、任务提升与挂树 |
| `preview.py` | `preview_working_state(state, time_advance, deltas) -> WorldState`；`preview_projection(...) -> PreviewData` 形 | 与 commit 同一条合并路，不落存储；`mergedEntityDeltas == pointProjection.entityDeltas` 由模型校验 |
| `preview.py` | `preview_over_budget(request_bytes, response_bytes) -> Violation \| None` | 请求 512 KiB / 响应 2 MiB 判定侧（`preview_budget_exceeded`） |
| `replay.py` | `replay_world(initial, applied_points) -> WorldState` | 从 canonical projection 重建（`get_state` notes）；终态摘要与轨迹 `expectedDigests`、投影夹具三方一致 |

## A1 覆盖的操作与留界

内核覆盖：`create_world`、`commit_point`、`preview_point`、`get_state`/`list_points` 的读出、`checkpoint_stage_unit`/`checkpoint_stage_time_scan` 的候选校验与 contentHash。不进 A1：lease/narration/rolls（A3）、pause/resume/conclude/cancel/prepare_successor/restore_group_work（A2/A3）；控制阶梯谓词（begin/discover/extend/close/stage/seal 的合法性）由 A1b 以纯函数交付、A2 消费，A1a 不实现。

## 待钉点（实现时以轨迹钉死，逐条落断言）

1. `unit_content_hash` 公式：T01 候选请求 ↔ 响应 `settledUnits[].contentHash` 离线复算。
2. 跨组同点 `supersedes` 与 `positionSet` 冲突语义（schema 只禁同批内同点 supersedes）。
3. 月/年 `Duration` 的日历加法规则（`WorldTime.dateTime` 字符串运算）。
4. preview 叠加边界：请求 `settlementGroups` 与已存 settledUnits/timeScan 的关系（notes：from the authoritative baseline 重算）。
5. T03-collapse 的前置点链与回放起点（seq=4，非 T03 直接延续）。
6. supersedes 失活链的跨点行为（`StoredDescriptionChange.active` 翻转时机；v1 夹具 `pureRemoval` 在 v2 零覆盖，A1b 自建）。

## 固定预期绑定（A1a-2 直接采用）

- `fixtures/projections/{normal,segmented,time}.expected.json` 为 **WorldState 终态快照**（同一学校世界，时间 11:59:02/11:59:05/12:00:00 对应 T01/T02/T03 终态），`canonical_digest(WorldState.model_validate(doc).model_dump(mode='json'))` 与轨迹 `samples[].expectedDigests` 的 `/data/stateDigest` 相等（B 以三条独立路径复现）。
- `description-collapse.expected.json` 是 DescriptionChange 形态片段、`task-normalization.expected.json` 是 EntityDelta 形态片段——塌缩/归一化行为断言比对对应片段，不是整状态。
- 回放配方：以轨迹 `samples[i].values` 实例化各步请求 → 依次 apply → 终态摘要对 `expectedDigests`；T02/T03 与 T01 共享世界线（链式回放）。
