# Proposal: goal-narr-point-scope

## Why

每个玩家回合拆两个 point，正文出现同一动作、同一句结算事实各写一遍。run115/116 的证据显示：没有自己结算的 point 会回退借用上一 point 的结果，instant point 也带玩家行动原文。

## What Changes

- 去掉 `onPointCommitted` 的跨 point `resultsText` 回退。
- `planPoints` 记录每 point 的 actorIds；叙事只在玩家所在 point 带行动原文。
- 测试 110 passed；run117 五回合 5/5、49.8/39.8/38.1/56.8/38.6 s（5/5 ≤60 s）、检查器 0，动作与结算句不再重复。

## Capabilities

（无；叙事输入收窄与验证。）

## Impact

- `frontend/src/lib/world-engine/local/game-model.ts`。
- 证据：`artifacts/goal/narration/run117-*.json`、`prose-facts-check-run117.json`、`read-run117-20261123.md`。
