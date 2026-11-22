# Proposal: goal-legal-check

## Why

s06「合法失败」的回合一再被写成成功动作。追查 run37 的证据发现：不是叙事模型编的——`results` 模型自己把「把红色电台递给阿豹（未知实体）」判成 `achieved`/`completed`，叙事只是照抄结算。开发期检查器只看正文与叙事提示，抓不到这类结算错误；需要一条按场景预期检查结算的开发门。

## What Changes

- `accept-world-local.mjs` 新增 `expect: 'legal_failure'` 支持：该回合的 `results` 原始输出里若出现 `outcome:'completed'` 或 `label:'achieved'`，记 `legal_failure_not_enforced`，并把命中文本写进证据。
- `turns-semantics-s05-s06.json` 的 s06 标 `expect: legal_failure`。
- 复跑并记录：run39 命中该门；run37 的证据回读确认根因在结算层。
- 不改产品代码、不改运行期检查（D-021 维持）。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。纯开发期验收工具；`.openspec.yaml` 设 `skip_specs: true`。

## Impact

- `frontend/scripts/product-acceptance/accept-world-local.mjs`
- `frontend/scripts/product-acceptance/turns-semantics-s05-s06.json`
- `design/goal/decisions.md`（D-022 追加根因）
- `design/goal/ledger.md`（R01 证据）
- 证据：`artifacts/goal/semantics/run39-legal-check.json`
