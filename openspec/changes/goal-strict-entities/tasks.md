# Tasks

## 1. 校验

- [x] 1.1 `assertKnownEntities` + 默认开启 + 重试反馈补规则。
- [x] 1.2 `SettlementOptions`/`GameModelOptions` 透传；页面 `strictKnownEntities=0` A/B 开关与证据字段。
- [x] 1.3 `npx vitest run`（1252 passed / 17 skipped）与 `next build` 通过。
- [ ] 1.4 3 次 s05/s06（guard 默认开 + 早交还），记录结算门与回合结果。
- [ ] 1.5 写 `artifacts/goal/narration/read-strict-entities-20261122.md`；更新 D-022 与 ledger R01。

## 2. 收尾

- [ ] 2.1 `openspec validate goal-strict-entities --strict`，归档，提交，打 tag `goal-strict-entities-20261122`。
