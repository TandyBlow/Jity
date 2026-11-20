# Proposal: G2 浏览器状态内核收口

## Why

G3 的十点测量在第 4 点被内核恢复缺口阻断：结算失败后 advance 未关闭，取消不生效，后续提交恒为 `turn_in_progress`（证据 `artifacts/goal/timing-runs/points-10-rerun.json`）。同时 G2 欠账：32 个 v2 操作未逐项定案（31 实现，`checkpoint_restore_group_work` 恒拒），`get_context.recovery` 恒 `null`，`state-invariants` 未接入 restore，Python–TS 没有冻结差分向量，骰点协议未冻结。

## What Changes

- 修复结算失败后的取消/恢复：允许取消 failed head，页面在 `turn_in_progress` 分支恢复可提交状态；补回归测试。
- 定案 `checkpoint_restore_group_work` 与 `get_context.recovery:null`：实现或声明非产品语义，写入 `decisions.md`。
- 把 `state-invariants/` 的 point-continuity、任务层级、可见性检查接入 restore；corrupt-restore 拒绝。
- 补 linked/instant successor time 路径。
- 用 Python v2 内核生成冻结差分向量，TS 对 `buildInitialState`、`applyPoint`、`pointEntityDeltas`、`replayWorld`、canonical digest 逐字节断言；覆盖空列表、0、嵌套位置、物品移动、任务层级、非 BMP 排序与拒绝路径。
- 冻结骰点协议：阈值、程序持有、requestId 去重。
- 补多标签租约、刷新、重复提交、取消恢复测试。
- 证据：`artifacts/goal/kernel-diff.json`、`kernel-ops.md`。

## Capabilities

### New Capabilities

- `browser-world-kernel`: 浏览器内核的失败回合终止、恢复守卫与可重放摘要契约。

### Modified Capabilities

None.

## Impact

- `frontend/src/lib/world-engine/local/{transport,session}.ts`、`controller.ts`、`schedule.ts`、`state-invariants/` 与相关测试。
- `frontend/src/app/world-local/page.tsx`（`turn_in_progress` 分支的按钮/阶段恢复）。
- `backend/app/world_app.py`、`backend/app/services/world/` 只作差分预言机，不改运行期权威。
- 证据与文档：`artifacts/goal/kernel-diff.json`、`kernel-ops.md`、`design/goal/{ledger,decisions}.md`。
