# Tasks

## 1. 开发门

- [x] 1.1 在 `accept-world-local.mjs` 增加 `expect: legal_failure` 检查（读 results 原始输出）。
- [x] 1.2 在 `turns-semantics-s05-s06.json` 的 s06 标 `expect: legal_failure`。
- [x] 1.3 复跑 s05/s06，记录 `legal_failure_not_enforced` 命中（run39）。

## 2. 记录

- [x] 2.1 D-022 追加根因：s06 的失败在结算层，不在叙事。
- [x] 2.2 更新 `design/goal/ledger.md` 的 R01 证据与缺口。
- [x] 2.3 写 `artifacts/goal/narration/read-legal-check-20261122.md`。

## 3. 校验与收尾

- [x] 3.1 `openspec validate goal-legal-check --strict` 通过。
- [x] 3.2 按路径提交，打 tag `goal-legal-check-20261122`。
- [x] 3.3 `openspec archive goal-legal-check --yes`。
