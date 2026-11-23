# 结算未知实体示例臂（2026-11-23，run107）

## 条件

- v8 叙事臂 + `settlementUnknownRule=1&settlementUnknownExample=1`；五回合 s02–s06。
- 示例规则：行动目标不在名单时，judgment 写 not_achieved，fact 写 blocked 的完整句子。

## 结果

- s02–s05：叙事硬错仍为 0（重复句存在）。
- s06：结算 3 次后中止。三次的 judgment 已出现「阿豹不在场，未能把红色电台交出去」的 blocked 理由，但 fact 仍写 `outcome: completed`（「路明非将红色电台递给阿豹…」），被 `results_unknown_entity` 拒绝。
- 结论：0.6B 能把 blocked 写进 judgment，却写不进 fact；提示示例无法修 fact 字段。

## 判定

- 示例臂无效；不采用。
- s06 的 5/5 阻塞只剩结算层，三条路：程序级 blocked fact（用模型自己的 blocked 理由作为事实文本）、手写结算数据微调 0.6B、换更强语义模型；或接受 s06 不通过。
