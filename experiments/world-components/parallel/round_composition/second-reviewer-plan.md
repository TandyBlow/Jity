# 第二复核者安排（N6 / D4 独立复核）

日期：2026-11-09。按裁决，独立复核要在 N4 对照实验**之前**完成。现在 v3 的两份复核（`review-v3.json` 的 N6、D4）都出自运行实验的同一个会话，`reviewStatus` 仍是 `pending-independent-review`；重试正文从未复核。

## 1. 要复核什么

对象：v3 的 10 个**首次调用**原文（不是重试，不是回退模板）。

逐条标注：

| 项 | 取值 | 要求 |
| --- | --- | --- |
| 每条必述事实是否传达 | `yes` / `no` / `undetermined` | 必须附正文原句 |
| 同名人物是否混淆 | `yes` / `no` / `undetermined` | 附证据 |
| 是否新增未授权的事件或专名 | 原句列表（可为空） | 专名与事件分开记 |
| 视角是否改变 | `yes` / `no` / `undetermined` | 第一人称、他人内心都算 |
| 可读性 | 1–5 | 只作描述，不进通过判定 |

## 2. 材料与隔离

- 盲包：`fixtures/reviewer-packet-v3.json`——每题含**完整场景**（地点、地点外貌、同栋）、**人物身份与 entityId、权威性格/外貌**、可见物品、权威事实行、视角、写作要求、首次调用原文、结束原因。**不含**已有 N6 结论与 D4 标签。
  - 修正记录：第一版只给事实行，复核者无法判断某段环境描写是否经过授权，也无法区分两个同名人物；现已补上场景与身份信息（`reviewer-packet-v3.json` 的 `scene` 字段）。
- 校准集：`fixtures/reviewer-calibration.json`（6 条短文），答案在 `fixtures/reviewer-calibration-key.json`，复核者提交后对照。目的：避免把「没有检出」当成「能检出」。
  - **专名与事件分开**：编造专名只有 **2 例**（`c2` 王五、`c4` 柳溪渡），不是文档早先写的 3 例；`c3` 的「钟声」归**新增事件**，单独记在 `inventedEvents`。`c5` 是否定句，事实判「未传达」。
- 复核者不参与本实验的批次运行，不看 `review-v3.json`、`fact-omission-v3.md` 与任何 N6 结论。

## 3. 流程

1. 复核者独立完成盲包与校准集，写成 `fixtures/review-v3-independent.json`（字段：每条事实 `conveyed` + 证据、`sameNameConfused`、`inventedProperNames`、`inventedEvents`、`povChanged`、`readability`）。
2. 校准集先对答案：两例编造专名（王五、柳溪渡）必须被标出，钟声必须记进新增事件，否定句必须判「未传达」。若校准不过，先校准再进入正式标注，不进入分歧统计。
3. 两份记录（原 `review-v3.json` 与独立版）逐条比较，输出 `review-comparison-v3.md`：
   - 一致率（按事实条数、按样本）；
   - 分歧清单，每条附两方证据；
   - 由你裁定的最终结论（保留原始判断，不覆盖）。
4. D4 的「真实正例/反例」用校准集补足：v3 的 D4 计数是 0，单看它无法区分「没有错误」与「没检出错误」。

## 4. 交付物

| 文件 | 内容 |
| --- | --- |
| `fixtures/reviewer-packet-v3.json` | 盲包（已生成） |
| `fixtures/reviewer-calibration.json` + `-key.json` | 校准集与答案（已生成） |
| `fixtures/review-v3-independent.json` | 独立复核记录（待填） |
| `review-comparison-v3.md` | 一致率、分歧、裁定（待写） |

## 5. 复核者来源（按 2026-11-09 裁决）

已经看过旧 N6 判断与遗漏分析的会话（包括本实验的会话）**不能充当盲审**。可接受的来源只有两种：

1. 未接触旧结论的人员；
2. 隔离的新会话（只给盲包与校准集，不给旧复核、分析报告或本文件的其他章节）。

两种来源都要在最终记录里如实写明。目前尚未执行独立标注，`reviewStatus` 仍是 `pending-independent-review`。

## 6. 与后续实验的关系

- 独立复核完成前，N4 对照批不登记。
- 独立复核的结果只用于两件事：给 v3 一个可引用的质量记录；把「哪些判据容易分歧」写进 N4 的验收协议（例如「移动算不算完整」）。
- 复核者不参与 N4 的设计，避免设计者与评判者同源。
