# Proposal: goal-settlement-rewrite

## Why

0.6B 在 s06 的判词里已写「阿豹不在场，未能…」，事实字段却仍写 completed，三次被 `results_unknown_entity` 拒绝，回合中止。需要把模型自己的 blocked 判词搬进事实字段，而不是让叙事拿不到任何结果。

## What Changes

- `assertKnownEntities`：fact 点名未登记实体且无否定词时，若该成员 judgment 为 blocked/not_achieved 且理由含否定线索，用判词文本与 blocked outcome 重写该 fact；否则仍拒绝。
- 该重写在校验与最终解析各执行一次（最终解析必须带上，否则提交的 facts 仍是原句）。
- 单测新增「判词搬移」用例；默认行为不变（无 blocked 判词时仍拒绝）。

## Capabilities

（无；结算层确定性修正。）

## Impact

- `frontend/src/lib/world-engine/local/semantics/settlement/results.ts`、`settlement.test.ts`。
- 证据：`artifacts/goal/narration/run108/109/110`、`read-v8-rewrite-5turn-20261123.md`。
