# Design: goal-unknown-rule

## Context

见 proposal。results 提示的规则块在 `results.ts` 的 `buildResultsPrompt`；`SettlementOptions` 已从 `createSettlementModelPort` 透传到 `runResults`。页面已有多个评估开关（`schedHandback`、`narrationFewShot`），沿用同一模式。

## Goals / Non-Goals

- Goals：测一条提示规则能否把结算误判从 4/5 压到 0/5。
- Non-Goals：不换模型、不微调、不改默认提示；不覆盖「未登记物品/地点」以外的情形。

## Decisions

1. **只在开启时插规则**：默认提示保持 G5 已归档的形态，避免评估臂污染基线。
2. **规则措辞直接给字段值**：`judgment: not_achieved`、`fact.outcome: blocked`，并要求写「没有这个人/不在场」，减少模型自由发挥。
3. **3 次采样**：与 `goal-legal-rate` 的 5 次口径相比更省时；若 3 次全清再补 2 次。

## Risks / Trade-offs

- [规则可能过度拒绝] → 正常回合（s05）也在同一臂里跑，出现 `not_achieved` 泛滥会立刻可见。
- [提示长度增加] → 单行规则，prefill 增量可忽略。

## Migration Plan

不适用。

## Open Questions

无。
