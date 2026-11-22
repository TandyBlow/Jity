# Design: goal-strict-entities

## Context

见 proposal。`results.ts` 的 `readResultsAnswer` 已有严格的成员/骰点校验与 `callJson` 重试；`GroupMember.actionText` 与 `WorldState.initial` 的登记名单都在手边。新增的只是「事实文本里不得出现未登记引入名」这一条。

## Goals / Non-Goals

- Goals：把「未知实体被判成功」从模型行为变成程序可拒绝。
- Non-Goals：不抓代词引入；不替代质量门；不改提示的默认规则（提示臂仍单独开关）。

## Decisions

1. **默认开启**：这是 R01 的确定性要求，不是实验臂。A/B 用 `strictKnownEntities=0` 复现旧行为。
2. **失败即中止该点**：重试 3 次仍出现未登记名，就让该点以可见失败结束，绝不把 fact 改写或丢弃后照常提交。
3. **名字提取沿用开发门的规则**（给/向/让/跟 + 2–3 字，排除代词与「的了着过」），宁漏勿误。

## Risks / Trade-offs

- [误杀] 合法但未登记的称呼（绰号）会被拒 → 反馈让模型改写为登记名；仍失败则中止，可见。
- [中止率] s06 可能从「写错」变成「点失败」；这是诚实的失败，但仍不算可玩通过，需要后续质量路线。

## Migration Plan

不适用。

## Open Questions

无。
