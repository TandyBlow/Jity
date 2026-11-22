# Proposal: goal-mode-v12

## Why

`design/goal/goal-mode-prompt.md` 与 `goal-mode-short.md` 仍是 Goal v11 的任务书：包含 G1–G8 执行顺序、只写笔记本设备、只测 60 秒首段。Goal v12 已改为只写终态（`design/goal/goal.md`，`c1f93c99`），并新增移动端两档设备、再次可行动 ≤60 秒与 OpenSpec 工作包命名调整。设定 goal 用的文本必须同步，否则每次 goal 会话都会按旧任务书执行。

## What Changes

- 重写 `design/goal/goal-mode-prompt.md` 为 v12 长文任务书：终态目标、两档设备、延迟与质量口径、OpenSpec 管理协议（工作包 change 命名 `goal-<slug>`，不再使用 G 编号）、未决项闸门。
- 重写 `design/goal/goal-mode-short.md` 为 v12 短版（设置入口，≤4000 字），明确写出用 OpenSpec 管理工作包与文档。
- **BREAKING**：任务书不再包含 G1–G8 执行顺序；能力状态以 `ledger.md` 为准，工作包由未决项与账本缺口决定。
- 不修改产品代码、验收协议与决策记录。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。纯文档变更；`.openspec.yaml` 设 `skip_specs: true`。

## Impact

- `design/goal/goal-mode-prompt.md`（重写）
- `design/goal/goal-mode-short.md`（重写）
- `design/README.md`（Active 表描述如涉版本则同步）
- 不涉及 `frontend/`、`backend/`、`openspec/specs/`。
