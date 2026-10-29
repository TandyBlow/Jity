# D1 签字记录（AI 独立标注、v3 冻结与分支判定）

日期：2026-10-29。签字对象：`dd2a513`（含实现提交 `2386ca0`；`world-components`，已推送）。
签字：C 审查者（独立复审结论）。记录：C 实现者。
范围：**D1 标注与冻结流程关闭**——AI 独立标注协议、原始标签一致性、v3 冻结、既有六臂重评分与 D1 分支判定。

**不扩大：** AI 独立性按归档协议和身份声明验收；本签字不代表真人评价、模型质量通过或 D2 完成。N2 模型臂仍未通过，训练未开始。

## 复核方式

C 审查者在 `core.autocrlf=false` 的临时干净检出中独立复跑：冻结标签字节一致；冻结记录、六臂评分和分支结果均可复现。

## 复核数字

| 项 | 结论 |
| --- | --- |
| 原始标签一致度 | 两份 AI 标签 **92/92 一致，κ=1.0**；分歧 0，无待裁决项 |
| 三类分布 | must 32、may 40、omit 20 |
| v3 vs v2 must 差异 | **0/16**，未超过 >2/16 门，沿用既有 N3 16 项输入 |
| 六臂逐项 D1 判据 | **均 0/16**；不宣布任何 N2 模型通过 |
| P1-rule | must-R=**1.0**、must-P 宏平均 **0.433333**、微平均 **0.421053**（32/76） |
| 降级分支 | 16 项中满足降级条件的项数为 **0**；逐项与 macro 两种解释均不触发降级或资源转移 |

## 证据哈希（git blob 内容 sha256，LF）

| 文件 | sha256 |
| --- | --- |
| `artifacts/world-components/n2-labels-v3.json` | `b7ffaf94f00cbea0ae47941d53dfa3f04b5659f1a32c83341e1c56e8df1ac889` |
| `artifacts/world-components/n2-must-v3.json` | `59664cf9d4584e7afde73ea93856089fa782e65a5013fe77e156a36e7b1c1ecf` |
| `artifacts/world-components/n2-annotation-status.json` | `11e37814794f2feabc858503ffbc8086c9954292b2a303a226efd1f701a864b9` |
| `experiments/world-components/n2_selection/annotation/labels-v3.jsonl` | `39588eeb7fce2842f3f380e2608aad74468255831b7fc2e30c2879c41b9e2403` |
| `experiments/world-components/n2_selection/annotation/labels-ai-a.jsonl` | `c3a5f82d318424285813264c2e7b9970705e2bd6f7b25aba86821d004c21740a` |
| `experiments/world-components/n2_selection/annotation/labels-ai-b.jsonl` | `40a4b0ec82d8b3532cad2291001db663024f29492a95c4df2a9009e34732b2b6` |
| `experiments/world-components/n2_selection/recompute_must_v3.py` | `887c66f81b6d7b82a786a6f53a59aab93ec61c0b9042895f86a0e0006f54dcf2` |
| `experiments/world-components/n2_selection/annotation_kappa.py` | `6a3d02487e06f6b177eed7760d43e0edd6cd342a4560919bcc9c7205291c4827` |

## 下一步（承接 d1-ai-closure.md §5）

1. **D2 准备**：8 项能力样本（4 项含时间、4 项双人同事件）、grouping/coref gold、隔离记录、指标与 prompt 冻结，完成后才运行 N3 模型臂；16 项与 8 项分开报告，不合并分母。
2. D2 原协议的**人工 gold 要求**未因 D1 的 AI 执行安排自动变更；若改用 AI 生成或复核，须另行明确标识和审查方法。
3. N4 留出集保持封存；浏览器端到端、指代消费和生产接线仍是原待办。
