# Proposal: goal-micro-facts

## Why

上一轮把 targets 与字符串匹配对照后，匹配基线更强；协同链的 position 仍读手写事实，judgment 的骰点文本含结果词。复核轮建议转向结构化事实：动作、施事、受事、位置、否定，并用真实结算结果替换人工事实。本轮先做事实测试集与规则基线，量出模型的真实位置。

## What Changes

- 24 条手写事实测试集（direct/negation/pronoun/ellipsis/movement），每条形 targets/destination/negated。
- 规则基线：字符串匹配 + 否定 + 代词/省略 + 移动 + 阻断结算。
- 模型组合：pair-scorer（targets）+ position 打分（destination）；否定字段模型未实现。
- 链改用规则结算的 position（动作 + 骰点），不再读手写事实；重测端到端、调用数、耗时。
- 产出 `artifacts/goal/micro-facts/`；不动产品。

## Impact

- 研究实验；规则与测试集同源，比较不是公平泛化；风险写明。
