# Design: G2 浏览器状态内核收口

## Context

见 `proposal.md` 的 Why。运行期权威链路：`local/session.ts` → `controller.ts` → `schedule.ts` → `local/transport.ts`，Python v2 只作差分预言机。G3 证据 `artifacts/goal/timing-runs/points-10-rerun.json` 显示：t4 结算在提交点前失败（`updates tasks` 拒绝未登记角色），之后 t5–t10 全部 `turn_in_progress`。

## Decisions

### 1. 失败回合必须可终止

- 复现结果（2026-11-20）：fixture 中「updates 抛错 → cancel → 新 submit」通过；真实 5 回合运行中 `session.cancel` 返回 `world_complete` 且 advance 清零。残留的停摆不是内核 cancel，而是页面的 `busy`/`phase` 与驱动下一回合点击的竞态：turn 2 在 98 ms 内空转（handler 被 busy 挡住，`__worldTurns` 仍是上一回合的 done 记录），之后按钮一直不可点。
- 修复：页面 stop 路径复用 cancel→补写→cancel（`e75cd4a6`）；`turn_in_progress` 分支恢复 `phase='ready'` 并归还输入；驱动在回合间等待页面离开结算阶段，并要求终止记录属于当前回合。
- 保留：`checkpoint_start_advance` 仍要求 head ready；failed head 不能被 cancel（已知限制，需重试或删除叙事后可继续），不在本变更加放宽。若后续页面恢复仍无法清 failed head，另开决定。

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
