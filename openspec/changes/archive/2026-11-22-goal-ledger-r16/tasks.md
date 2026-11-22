# Tasks

## 1. 账本校正

- [x] 1.1 复核 `artifacts/goal/acceptance/summary.json` 的输入数与门（20 输入、首段 20/20、回合 20/20、0 失败、9 个时限收尾）。
- [x] 1.2 更新 `design/goal/ledger.md` 的 R16 行：状态、证据、缺口。
- [x] 1.3 确认 R16 与 G8 摘要行一致，不写「通过」。

## 2. 校验与收尾

- [x] 2.1 `openspec validate goal-ledger-r16 --strict` 通过。
- [x] 2.2 按路径提交，打 tag `goal-ledger-r16-20261122`。
- [x] 2.3 `openspec archive goal-ledger-r16 --yes`。
