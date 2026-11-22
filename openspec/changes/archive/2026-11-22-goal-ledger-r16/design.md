# Design: goal-ledger-r16

## Context

See proposal. The G8 summary (`artifacts/goal/acceptance/summary.json`, generated 2026-11-21T16:08Z) lists 20 inputs; the ledger summary row already says "技术证据齐（G5/G6 未通过）" but the R16 row still says "未实现".

## Goals / Non-Goals

- Goals：让 R16 与验收证据和 G8 摘要一致。
- Non-Goals：不新跑 20 输入；不改门槛；不宣布整体通过。

## Decisions

1. **以 summary.json 与 G8 报告为准**：两者是已归档的技术证据；R16 的旧记录是 G8 完成前的状态。替代方案（重跑 20 输入）成本高且不改变结论。
2. **保留质量缺口**：R16 状态写「技术证据齐（质量线未通过）」，不写「通过」。

## Risks / Trade-offs

- [summary 只覆盖 16 个输入？] → 复核 summary 的 inputs 数量；若不足 20，按实际数量写，不夸大。

## Migration Plan

不适用。

## Open Questions

无。
