# Tasks

## 1. 评估臂

- [x] 1.1 `SettlementOptions.unknownEntityRule` + `buildResultsPrompt` 规则行。
- [x] 1.2 `GameModelOptions.settlementUnknownRule` 透传；页面 URL 开关与证据字段。
- [x] 1.3 3 次 s05/s06 复跑（`settlementUnknownRule=1` + `schedHandback=player`），统计结算门命中。
- [x] 1.4 写 `artifacts/goal/narration/read-unknown-rule-20261122.md`；更新 D-022 与 ledger R01。

## 2. 校验与收尾

- [x] 2.1 `npx vitest run` 与 `openspec validate goal-unknown-rule --strict` 通过。
- [x] 2.2 提交并打 tag `goal-unknown-rule-20261122`；归档。
