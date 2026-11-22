# Proposal: goal-legal-rate

## Why

run37/run39 显示 s06 合法失败被结算判成成功（未知实体阿豹）。D-022 要选质量路线，需要知道这是偶发还是系统性的：如果是 5/5 稳定复现，说明是语义提示/模型的系统性缺陷，路线应优先修结算；如果偶发，则需要采样与重试策略。现有样本只有 2 次，不够。

## What Changes

- 用同一夹具 s05/s06 复跑 5 次（早交还臂，保持低耗时），每次记录 `legal_failure_not_enforced` 是否命中。
- 写 `artifacts/goal/narration/legal-failure-rate-20261122.md`：命中率、原始 results 片段、对 D-022 的含义。
- 更新 D-022 与 ledger R01 的证据。
- 不改产品代码、不改门槛。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。纯测量；`.openspec.yaml` 设 `skip_specs: true`。

## Impact

- `artifacts/goal/narration/legal-failure-rate-20261122.md`
- `artifacts/goal/semantics/run40-legal-rate-*.json`
- `design/goal/decisions.md`、`design/goal/ledger.md`
