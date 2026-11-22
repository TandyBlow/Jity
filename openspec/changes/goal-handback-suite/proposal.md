# Proposal: goal-handback-suite

## Why

D-024 的评估臂已在 s02–s06 上验证 15 个回合 ≤60 s；还需要 20 输入套件的全量数据，才能同时给出「交还时间分布」与两条开发门（结算/正文）的命中计数，作为 D-022/D-023 的共同基线。

## What Changes

- 用 `schedHandback=player&offscreenPolicy=skip` 跑 `turns-20-chunk1/2/3/3b/5`；已跑完 chunk1–3（12 回合）与 chunk3b 的 3 个回合（未完成）。
- 给所有合法失败夹具补 `expect: legal_failure`（chunk2、turns-20、offline-2、semantics-16、semantics-s02-s06），否则 20 输入套件不会触发结算门。
- 记录 15 个回合的交还时间与问题；chunk3b 的 s15/s16 与 chunk5 因宿主内存回收停止，未继续（按后台任务回收规则，不自行重启）。
- 不改产品代码与默认调度。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。测量与夹具标注；`.openspec.yaml` 设 `skip_specs: true`。

## Impact

- `frontend/scripts/product-acceptance/turns-*.json`（expect 标注）
- `artifacts/goal/acceptance/run41-*.json`
- `design/goal/decisions.md`（D-024 追加）
