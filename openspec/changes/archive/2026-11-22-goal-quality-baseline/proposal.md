# Proposal: goal-quality-baseline

## Why

D-022 要选质量路线，先要有统一的基线。两条开发门（结算 `legal_failure_not_enforced`、正文 `unknown_entity_claim`）已经就位；把近期所有证据跑一遍，得到「多少回合至少命中一条门、按类别各多少」的基线，后续任何路线都用同一把尺子量。

## What Changes

- 用 `check-prose-facts.mjs` 批量检查 run27–run40 的语义证据与 run41 的套件证据（17 个 run、42 个回合）。
- 写 `artifacts/goal/narration/quality-baseline-20261122.md`：命中分布、s06 的稳定命中、局限。
- D-022 追加基线数字。
- 不改产品、不改门槛。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。纯开发期测量；`.openspec.yaml` 设 `skip_specs: true`。

## Impact

- `artifacts/goal/narration/prose-facts-baseline-20261122.json`、`quality-baseline-20261122.md`
- `design/goal/decisions.md`（D-022）
