# Proposal: goal-unknown-rule

## Why

s06 合法失败的根因是结算层：results 模型把未知实体阿豹的交接判成 `achieved`/`completed`（4/5）。现有提示已有「只能使用下面出现的人物」和「failed/blocked 照实写」，但模型仍会放过未登记目标。先做一个不换模型、不改默认的评估臂：在 results 提示里显式写明未登记实体必须 `not_achieved`/`blocked`，用同一套门量命中率变化。

## What Changes

- `SettlementOptions` 增加 `unknownEntityRule`；`buildResultsPrompt` 在开启时插入一条明确规则。
- `GameModelOptions.settlementUnknownRule` 透传；页面 URL `settlementUnknownRule=1` 开启，证据记录开关。
- 默认关闭，不改产品路径。
- 3 次 s05/s06 复跑对比 `legal_failure_not_enforced` 命中率。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。评估臂；`.openspec.yaml` 设 `skip_specs: true`。

## Impact

- `frontend/src/lib/world-engine/local/semantics/settlement/{types,results}.ts`
- `frontend/src/lib/world-engine/local/game-model.ts`
- `frontend/src/app/world-local/page.tsx`
- 证据：`artifacts/goal/semantics/run42-*.json`
