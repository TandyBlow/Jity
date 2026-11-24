# 微型模型评测协议（2026-11-24）

## 状态

冻结规则与模型，等待独立作者写 300 条数据。本文件只定协议，不含数据；数据未写之前不做新的模型调整。

## 冻结

- `artifacts/goal/micro-facts/rules.py` sha256 `c746a9727779de2da42afd3255f2aacbc947b5ece4417b9858395d763e88a91c`
- `pair-scorer-int8.onnx` sha256 `c9d1b0c55d215709943c9cac45aaab3202d0231fc1cdc20a5a4406869f3d966d`
- `t2-int8.onnx` sha256 `e00c2daa081dbcb5f1a4be425b79090d2a01f999972b9c2fbdec16c90124be6f`
- 评测脚本与阈值冻结；评测期间不改规则、不改模型、不改测试集。

## 数据

- 300 条自然语言游戏行动；字段：`action`、`present`、`current`、`candidates`、`dice`、`expect{targets, destination, negated}`、`tags`。
- 覆盖：陌生人物、陌生场景、多轮对话、复合行动、隐含意图、上下文指代；每类 ≥30 条。
- 作者规则：独立作者，不看 `rules.py`、现有测试集与模型输出；先写数据，再跑系统。
- 数据入库前由第二人复核标引；分歧记录，不静默取一。

## 方案

| 方案 | 目的 |
|---|---|
| 纯规则 | 对照基线 |
| 10M 专用模型 | pair-scorer + position 打分 |
| 规则 + 模型 | 规则优先，模型补否定/指代 |
| 0.6B 通用模型 | 对照现有 Jity |
| 云端大模型 | 质量上限参考 |

## 指标

- 字段准确率（targets / destination / negated）、行级全对、单次延迟、调用数。
- 按 `tags` 分组报告胜率，不报单一总分；规则能解决的构造不要求模型赢。

## 判定

- 每类构造上的胜率决定该构造用规则还是模型；模型只在规则失败的构造上被评估。
- 云端大模型只作质量参考，不参与部署选择。

## 待办

- [ ] 独立作者完成 300 条并复核。
- [ ] 五方案 harness 跑通（10M 与 0.6B 已有；云端需接口）。
- [ ] 结果写 `artifacts/goal/micro-eval/`，更新 D-030。
