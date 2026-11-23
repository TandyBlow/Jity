# Proposal: goal-mobile-compact

## Why

用户裁决继续移动工程攻关。按 run94 的调用分解，results/position 的 prefill 是移动档的主要成本；先压缩 results 场景清单，再尝试压缩位置/外貌的容器目录，量化收益与风险。

## What Changes

- 新增 `compactSettlement` 评估臂：results 提示只列行动提到的人物/物品，不再列整屏场景（`types.ts`、`results.ts`、`game-model.ts`、`page.tsx`）。
- 位置/外貌的容器目录压缩试过后回退：裁掉的容器会被模型当作目的地，触发重试，净效果为负。
- 默认路径不变。

## Capabilities

（无；移动工程评估臂。）

## Impact

- `frontend/src/lib/world-engine/local/semantics/settlement/{types,results}.ts`、`local/game-model.ts`、`app/world-local/page.tsx`。
- 证据：`artifacts/goal/narration/run103-mobile-compact.json`、`run104-mobile-compact2.json`、`read-mobile-compact-20261123.md`。
