# micro-facts 结论（2026-11-24）

## 测试集

- 29 条手写事实输入：direct 6、negation 6、pronoun 2、ellipsis 4、movement 6、adversarial 5（复核轮反例：部分否定、否定犹豫、问句里的地名、看/望、双重否定）。
- 规则（基线）：字符串匹配 + 否定词 + 代词/省略解析 + 移动词 + 结果阻断。
- 模型组合：pair-scorer 出 targets、position 打分出头出 destination；否定字段模型没有。

## 结果

| 字段 | 规则 | 模型 |
|---|---|---|
| targets | 27/29 | 20/29 |
| destination | 27/29 | 16/29 |
| negated | 27/29 | 未实现 |

- 反例子集（5 条）：规则 targets 3/5、destination 3/5；模型 targets 4/5、destination 1/5。
- 反例暴露的规则缺陷：否定词一刀切（「我没给诺诺水，但给了秦越」清空全部目标；「我没有犹豫」误清空）；问句里的地名当成移动（「我在西回廊问诺诺庭院在哪里」判成去庭院）；看/望不当成移动。
- 模型的强项：反例 targets 4/5（规则 3/5）；弱项：反例 destination 1/5，且没有否定字段。

## 判定

- 总体仍是规则领先（27/29 vs 20/29、27/29 vs 16/29）；反例 targets 上模型 4/5 > 规则 3/5——互补性开始出现，只有 5 条。
- 「模型在否定/省略集比基线高 ≥2 行」的判定仍不成立：否定集规则 6/6、模型 1/6；反例子集模型 targets 高 1 行，未达 2。
- 规则与测试集同源，反例由复核者构造（不是独立作者）；公平比较需要独立作者的 300 条，协议见 `artifacts/goal/micro-eval/protocol.md`。
- 研究目标不应设为「模型击败规则」：规则能解决的就用规则，模型只在规则失败的构造上评估。

## 复现

```bash
python artifacts/goal/micro-facts/eval_facts.py
```
