# Design: goal-handback-suite

## Context

见 proposal。套件文件沿用 G8 的 5 个 chunk；每次运行前清空存储，模型冷载。早交还臂把每回合压到 35–53 s，4 回合一个 session 约 3–5 分钟。

## Goals / Non-Goals

- Goals：15–20 个真实页面输入的交还时间与两条开发门命中计数。
- Non-Goals：不把它当验收（臂不是产品默认）；不重启被回收的后台任务。

## Decisions

1. **合法失败夹具统一标 `expect`**：套件里的 s06 与语义夹具是同一输入；不标就漏掉结算门。替代方案（每个文件手写专用检查）会漂移。
2. **被回收即停止**：宿主内存回收杀掉 chunk3b 后，不自行重启；剩余 chunk 待用户允许后继续。

## Risks / Trade-offs

- [不完整样本] → 报告只统计完成的 12 个回合与 chunk3b 的 3 个已完成回合，并标注未完成。
- [臂与默认不同] → 明确写「早交还臂」，不与 G8 默认路径的数字混算。

## Migration Plan

不适用。

## Open Questions

- 是否在用户方便时补跑 chunk3b 的 s15/s16 与 chunk5。
