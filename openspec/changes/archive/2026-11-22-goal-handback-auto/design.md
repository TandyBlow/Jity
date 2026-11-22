# Design: goal-handback-auto

## Context

见 proposal。D-024 已批准评估臂原型；无自动链的「玩家回合交还」实测 36.9–45.0 s。候选 b 是保留一轮自动链，需要知道它的交还时间。现有证据的 `pointNarration` 以 `auto` 前缀标记自动轮的点，第一轮自动链的完成时间可直接读出。

## Goals / Non-Goals

- Goals：量化「保留一轮自动链」的交还时间，判断是否满足 60 s。
- Non-Goals：不实现新的调度臂；不改变默认自动链；不评估质量。

## Decisions

1. **以第一个 auto 点的 `completedAtMs` 作为候选 b 的交还时间**：自动轮的计划在 `LocalGameModel.planPoints` 里是一个覆盖候选 order 的点（game-model.ts:296–303），所以第一个 auto 点完成即第一轮自动链结束。替代方案（写一个 `schedHandback=one-auto` 臂）成本高且结论可先由数据判定。
2. **只统计 run27–34**：它们是同一调度、同一输入集；run35/36 是移动模拟档，单独处理。

## Risks / Trade-offs

- [自动轮可能有多个点] → 当前计划是一个 auto 点；若未来变化，需重算。
- [第一轮自动链的 continue 判定本身有开销] → 模型调用约 1–2 s，已包含在 auto 点开始前的空档里，不影响结论量级。

## Migration Plan

不适用。

## Open Questions

无。
