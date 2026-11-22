# Proposal: goal-handback-auto

## Why

D-024 的产品化候选 b 是「有限自动链」（限一轮）。不用再写一个评估臂也能回答：现有 run27–34 的逐点叙事时间已经记录了每个自动点，第一轮自动链的完成时间就是候选 b 的交还时间。先量出来，避免为一条已被数据否定的路线写代码。

## What Changes

- 新增证据 `artifacts/goal/narration/handback-auto-chain-20261122.md`：16 个回合的第一轮自动链完成时间。
- 在 `design/goal/decisions.md` 的 D-024 记录候选 b 的测量结果与结论。
- 更新 `design/goal/ledger.md` 的 R10 行：加入 D-024 评估臂与自动链测量证据、待决取舍。
- 不改产品代码与门槛。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。纯测量与文档；`.openspec.yaml` 设 `skip_specs: true`。

## Impact

- `artifacts/goal/narration/handback-auto-chain-20261122.md`（新增）
- `design/goal/decisions.md`、`design/goal/ledger.md`
- 不涉及 `frontend/`、`backend/`、`openspec/specs/`。
