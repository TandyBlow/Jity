# Tasks: goal-micro-eval

- [x] 1. 冻结规则与模型，记录 sha256（`artifacts/goal/micro-eval/protocol.md`）。
- [x] 2. 300 条数据（6 类各 ≥30）；作者为执行 Agent，独立性限制已记录。
- [x] 3. 五方案 harness：规则、10M（int8）、规则+模型、0.6B 已跑；云端待跑。
- [x] 4. 按 tags 评估：规则 269/263/262，模型 218/207，混合 280/263/262；三字段全对 227/—/225；0.6B 145/233/278、全对 103。
- [x] 5. 结论写 `artifacts/goal/micro-eval/conclusion-20261124.md`，D-030 已更新；数据弱点与混合回退问题已记录。
