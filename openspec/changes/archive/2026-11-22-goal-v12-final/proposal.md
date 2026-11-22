# Proposal: goal-v12-final

## Why

现行 `design/goal/goal.md` 是 Goal v11 的「执行路线书」：终态与 G1–G8 阶段表混在一起，读起来像施工计划而不是目标。用户要求 goal 只写最终目标，不写阶段性路线；同时移动端支持、两档设备与「再次可行动 ≤60 秒」的延迟口径已经明确（D-023/D-024）。

## What Changes

- 重写 `design/goal/goal.md` 为 Goal v12：只写终态、非目标、约束与未决项；删除 G1–G8 阶段表，能力状态继续由 `ledger.md` 承担。
- 更新 `CLAUDE.md` 的「Active project: Goal v11」段落为 v12。
- 更新 `design/README.md` 中对 `goal.md` 的描述（从「最终目标、硬门槛、G1–G8、执行规则」改为「最终目标、终态门槛、约束与未决项」）。
- **BREAKING**：goal 不再包含 G1–G8 编号路线；既有归档 change、tag 与 `ledger.md` 保留为证据。
- 不修改产品代码、验收协议与决策记录；D-022（叙事质量路线）、D-023（移动档门槛）、D-024（延迟口径与调度改造）以链接保留。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。本变更只改目标文档，产品行为与 `openspec/specs/` 的要求不变；`.openspec.yaml` 设 `skip_specs: true`。

## Impact

- `design/goal/goal.md`（重写）
- `CLAUDE.md`（「Active project」段落）
- `design/README.md`（索引描述）
- 不涉及 `frontend/`、`backend/`、`openspec/specs/`。
