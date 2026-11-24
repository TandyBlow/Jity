# micro-facts 结论（2026-11-24）

## 测试集

- 24 条手写事实输入：direct 6、negation 6、pronoun 2、ellipsis 4、movement 6；每条给 targets / destination / negated 三个字段。
- 规则（基线）：字符串匹配 + 否定词 + 代词/省略解析 + 移动词 + 结果阻断（骰点含拦/挡住等）。
- 模型组合：pair-scorer 出 targets、position 打分出头出 destination；否定字段模型没有。

## 结果

| 字段 | 规则 | 模型 |
|---|---|---|
| targets | 24/24 | 16/24 |
| destination | 24/24 | 15/24 |
| negated | 24/24 | 未实现 |

- 模型分组：targets——direct 6/6、ellipsis 1/4、negation 1/6、pronoun 2/2、movement 6/6；destination——direct 2/6、ellipsis 2/4、negation 3/6、pronoun 2/2、movement 6/6。

## 判定

- 在这批测试上规则全面优于模型；判定条件（模型在否定/省略集比基线高 ≥2 行）不成立，记录证伪。
- 规则与测试集同源（按同一批构造编写），这不是公平的泛化比较；公平版本需要独立作者的构造。
- 模型的 direct targets 6/6、movement 6/6 说明它没坏；缺的是否定字段与「无移动」判定，且 destination 在无移动动作上乱选。
- 下一步若要继续模型路线：先补否定头与无移动判定，再在规则未覆盖的构造上测。

## 复现

```bash
python artifacts/goal/micro-facts/eval_facts.py
```
