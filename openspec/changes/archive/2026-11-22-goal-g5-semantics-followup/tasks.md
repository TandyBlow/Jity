# Tasks: G5 语义复开

## 1. 事实层修复

- [x] 1.1 占位句拒绝（`〈…做了什么…谁回应…〉`）与回归。
- [x] 1.2 状态字段行拒绝（`id=`/`位置为`/`精神为` 等）与回归。
- [x] 1.3 识别带与外观矛盾拒绝（s02/s05/s16）与回归。
- [x] 1.4 门与地点外观矛盾拒绝（s03）与回归。
- [x] 1.5 叙事 prompt 物品归属、只有结算动作才算发生；行动回声启发式回退。

## 2. 未修问题

- [ ] 2.1 s06 judgment 与 fact 不一致（自由文本 vs 结构化事实）需要单独设计；未修，转 G6 模型质量路线（D-020）。
- [x] 2.2 s07 双挂专项回归：共享事实只被句子点名一个成员时收窄 memberIds（`settlement.test.ts`）。

## 3. 复跑与读评

- [x] 3.1 s02–s06 在 D-018 后代码上干净复跑（run22/23/24，进度服务停用）；s02 285.6 s、s03 291.7 s、s04 290.0 s、s05 257.8 s、s06 295.5 s，驱动 problems 0。
- [x] 3.2 重做技术读评：hard 5/5，未通过（`artifacts/goal/narration/read-5-clean-20261121.md`）；事实层定向拒绝生效，但正文与 generic fact 问题仍在。
- [x] 3.3 用户抽检已按 D-019 豁免；报告如实记录。

## 4. 收口

- [x] 4.1 `openspec validate "goal-g5-semantics-followup" --strict`；归档；tag `goal-g5-semantics-followup-20261122`；ledger 更新。
