# Design: goal-micro-facts

## 测试集

- 24 条：direct 6、negation 6、pronoun 2、ellipsis 4、movement 6；字段 targets（人名集合）、destination（结算后位置）、negated。
- negation 覆盖：没有递给、谁也没给、没找到、没有走进、没有交给、没理。
- ellipsis 覆盖：他/她、在场的两个人、第二个人、在场的人、他们。

## 基线

- 字符串匹配 + 否定词表 + 代词/省略规则 + 移动词 + 骰点阻断（拦/挡住/被顶住）。

## 模型

- targets：pair-scorer；destination：position 打分；否定：无（记缺）。

## 判定

- 模型在否定/省略集需比基线高 ≥2 行才继续模型路线；否则记录证伪。
- 链的 position 改为规则结算后，端到端 ≥8/12 才算链可用。
