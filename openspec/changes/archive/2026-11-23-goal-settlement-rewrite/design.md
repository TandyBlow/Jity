# Design: goal-settlement-rewrite

- 触发：未知名字出现在 fact 文本，文本无否定词（不在场/没有/未能/没能/未被/没在/不在/无法/拒绝）。
- 重写条件：该 fact 的 actor 有 blocked/not_achieved judgment，理由含同一组否定词。
- 动作：fact.text = judgment.reason，outcome = blocked，标记 `unknownEntityRewrite`；evidence 的 facts 会带上重写后的句子。
- 无 blocked 判词时保持原拒绝，避免把编造的成败交给叙事。
- 校验与最终解析各跑一次；后者是提交事实的来源。

## 结果

- run108（0.45）：5/5 完成；s06 结算为「没有这个人/没有这件东西/不在场」，正文写被拒动作；硬错 s03/s05 归因、s04 时长、s06 凭空动作。
- run109（0.2）：5/5 完成；s03/s04/s06 主角加规则阅读。
- run110（0.2+瘦身）：5/5 完成；s02 归因、s05 结算占位符、s06 坏事实。
- 判词搬移解决中止；5/5 叙事质量仍不过。
