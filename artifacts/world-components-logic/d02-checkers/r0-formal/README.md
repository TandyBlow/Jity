# 正式 R0 任务头与 development 评估

日期：2026-11-10。执行者：助手。范围：scale-v2 `train` 288 条训练、`development` 48 条评估；**未读 sealed**。

## 结论

这是第一版正式 R0 任务头，不是可上线模型，也不代表人审通过。

- 编码器：MiniRBT-H256 第 0、1 层冻结，fp32，CPU；哈希前后一致。
- M1：token mention BIO、5 角色多标签、候选实体 Bilinear 打分。
- M2：5 类整段标签、issue token BIO、issue 起始位置 6 类 scope。
- 训练：20 epochs，batch 16，AdamW，仅新头；train 288，dev 48。
- 结果：M1 span F1 0.606；M2 标签准确率 0.917，但 dev 只有 attempt/mixed 两类；4/8 条 mixed 被误判为 attempt（关键安全错误）。
- 没有 dev 五类宏平均：development 中没有 non_action/uncertain/result_assertion 样本；只能报告 present-class macro F1 0.810。

## M1 development

| 指标 | 数值 |
|---|---:|
| span precision / recall / F1 | 0.580 / 0.634 / **0.606** |
| 匹配 span / gold / predicted | 83 / 131 / 143 |
| 角色集合完全正确 | 80 / 83 |
| 实体完全正确 | 69 / 74 |
| 整段全部绑定正确 | 77 / 83 |
| 主体包含执行人（gold / pred） | 44 / 45 |
| 预测主体错误包含执行人 | 1 |

角色召回：

| 角色 | 召回 |
|---|---:|
| subject | 1.000 |
| object | 0.500 |
| tool | 0.130 |
| recipient | 0.571 |
| destination | 0.111 |

工具和目的地角色几乎未学会；当前 M1 不能用于自动放行。

## M2 development

| 指标 | 数值 |
|---|---:|
| 标签准确率 | 0.917（44/48） |
| present-class macro F1 | 0.810 |
| 标签支持 | attempt 40 / mixed 8 |
| 安全误放行（gold 非 attempt 被预测 attempt） | **4 / 8** |
| issue span P / R / F1 | 0.714 / 0.526 / 0.606 |
| issue TP / FP / FN | 10 / 4 / 9 |
| 匹配 issue 的 scope 准确率 | 1.000（10 条） |

混淆：

| gold | predicted | count |
|---|---|---:|
| attempt | attempt | 40 |
| mixed | mixed | 4 |
| mixed | attempt | 4 |

`scopeAccuracy=1.0` 只有 10 个匹配 issue，不能外推。

## 工程身份

- 训练样本 288，dev 48；train/dev 场景组无交集。
- 编码器哈希：前后一致；新头全部参数变化。
- 头文件 `heads.pt` 只留本地，不入 Git；SHA 见 `record.json`。
- 运行 `python3 experiments/world-components-logic/d02_r0_formal.py --epochs 20 --batch-size 16`；本次主流程约 5.7 秒。
- 没有 provider、没有生产接线、没有写世界、没有 A/B/C。

## 限制

1. 开发集只有 4 个场景组、48 条，分布偏窄；不能当泛化成绩。
2. dev 只有 attempt/mixed 两类表达，五类宏平均无法计算。
3. M1 只预测公开五角色，不预测诊断角色、未知/歧义状态；实体候选只在样本世界内打分，没有“无实体”选项。
4. M2 issue 只用一个 BIO 头和起始 scope；多 issue、嵌套作用域未覆盖。
5. 编码器是手动 MiniRBT 前向，不是项目正式训练器；正式 R0 仍需接入冻结训练器并做可重复冻结批次。
6. 数据仍是 assistant draft，未人审；结果不能作为质量通过或训练授权延续。

## 下一步

- 先修复 M1 工具/目的地召回和角色类别不平衡，补 dev 的表达类别；
- 用同一冻结编码器比较 R1（完整 MiniRBT-H256）和 R2（联合微调），保持数据/头/步数一致；
- 所有比较只报 dev，不碰 sealed；训练前保存冻结配置和随机种子。
