# Design: goal-micro-eval

## 冻结

- 规则、pair-scorer-int8、t2-int8 的 sha256 写入 `artifacts/goal/micro-eval/protocol.md`；评测期间不改。

## 数据

- 300 条；字段 `action/present/current/candidates/dice/expect{targets,destination,negated}/tags`。
- 六类构造各 ≥30；独立作者不看规则/模型输出；第二人复核标引。
- 切分：开发集 100 / 测试集 200，按构造分层；测试集只在最终评估时使用。

## 方案

- 纯规则；10M（pair-scorer + position 打分）；规则+模型（规则优先，模型补否定/指代）；0.6B；云端。
- 指标：字段准确率、行级全对、延迟、调用数；按 tags 分组。

## 判定

- 每类构造的胜率决定该构造的实现方式；模型只在规则失败的构造上评估。
- 云端只作参考，不参与部署选择。
