# Design: goal-legal-rate

## Context

见 proposal。`accept-world-local.mjs` 已有 `expect:'legal_failure'` 门（run39 命中一次）；s06 的 results 原始输出可用 `entry.legalFailure` 读取。早交还臂（`schedHandback=player`）把单回合压到 26–51 s，适合重复采样。

## Goals / Non-Goals

- Goals：估计 s06 在 5 次独立运行里的命中率。
- Non-Goals：不改变结算提示或模型；不覆盖其他场景；不把命中率当质量门槛。

## Decisions

1. **固定同一夹具与臂**：s05/s06、base 1.7B、`schedHandback=player`、`offscreenPolicy=skip`；每次用新的输出文件。替代方案（不同输入采样）会把输入差异混进命中率。
2. **命中判据沿用 run39 的门**：results 出现 `completed`/`achieved` 即记命中；`legalFailure` 明细进证据。

## Risks / Trade-offs

- [5 次样本小] → 报告写明这是点估计，不是置信区间；若结果分裂，追加运行。
- [早交还臂改变回合长度] → 结算调用与默认路径相同，不影响 s06 的判定内容。

## Migration Plan

不适用。

## Open Questions

无。
