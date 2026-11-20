# Design: G2 浏览器状态内核收口

## Context

见 `proposal.md` 的 Why。运行期权威链路：`local/session.ts` → `controller.ts` → `schedule.ts` → `local/transport.ts`，Python v2 只作差分预言机。G3 证据 `artifacts/goal/timing-runs/points-10-rerun.json` 显示：t4 结算在提交点前失败（`updates tasks` 拒绝未登记角色），之后 t5–t10 全部 `turn_in_progress`。

## Decisions

### 1. 失败回合必须可终止

- 复现：用 `controller`/`local-transport` 的 fixture 模型构造一个 `updates` 语义失败，然后 cancel，再 submit。
- 已知可疑点：`handleCancel` 的 `checkHeadReady` 只允许 `ready`；failed head 永远无法取消。另一可能是 controller 的 cancel 请求使用了过期的 bind/ids。
- 决定：cancel 必须在任何活跃 phase 关闭 advance；`checkHeadReady` 对 cancel 放宽到 `ready | failed`，`checkpoint_start_advance` 仍要求 `ready`。若复现显示是 bind/ids 问题，则修 request 构造，保持传输层校验不放宽。
- 页面：`turn_in_progress` 分支恢复 `phase='ready'` 并把文本还给玩家；恢复尝试与停止路径一致。

### 2. 两个未决操作

- `checkpoint_restore_group_work`：产品恢复走本地快照与 checkpoint，不用「恢复组工作」；决定声明为**非产品语义**，保留 `frozen_work_missing` 拒绝，写入 `decisions.md`。
- `get_context.recovery:null`：本地恢复不依赖服务端 recovery；保持 `null` 并声明语义。两者都不留「以后再说」。

### 3. restore 接 invariants

`state-invariants/guarded-restore.ts` 已有点连续性/任务层级/可见性检查；在 session restore 读取存档后、开始 play 前调用。失败时不应用状态、不写回，返回不变量代码；corrupt 存档按现有 archive-then-delete 流程处理。

### 4. 冻结差分向量

- Python `backend/app/world_app.py` + `schemas/world/` 生成向量：S0、每点 Δ、期望 `stateDigest`、拒绝样例。
- 覆盖：空列表、0、嵌套位置、物品移动、任务层级、非 BMP 排序、非法新实体/拒绝路径。
- 产物 `artifacts/goal/kernel-diff.json`；TS 测试读取并逐字节断言 `buildInitialState`/`applyPoint`/`pointEntityDeltas`/`replayWorld`/digest。
- 不一致按 bug 调查，不按 Python 单方改 TS。

### 5. 骰点协议

冻结：阈值常量、骰点由程序生成并持久化、`requestId` 去重、恢复不重掷。以测试锁定；协议写入 `kernel-ops.md`。

### 6. 其余恢复测试

多标签租约（30 s TTL、fence）、刷新恢复、重复提交、取消恢复：复用 `session-recovery.test.ts` 与 `lease.mjs` 场景，补断言。

## Risks / Trade-offs

- [放宽 cancel 的 head 条件会掩盖叙事失败] → 只放宽 cancel；commit/claim 仍要求 ready，failed 文本保持失败标注。
- [Python 向量与本树 schema 漂移] → 生成脚本固定输入与哈希，向量入库；生成时记录 Python commit。
- [页面恢复逻辑与 G4 重叠] → 只做最小可提交恢复，完整交互验收仍归 G4。

## Non-Goals

- 不改模型、不换权重、不加运行时叙事检查。
- 不实现 `checkpoint_restore_group_work` 的产品用法。
- 不做多用户同步。
