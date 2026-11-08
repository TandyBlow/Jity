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

- 盲包：`fixtures/reviewer-packet-v3.json`——每题只含权威事实行、视角行、写作要求行、首次调用原文、结束原因。**不含**已有 N6 结论与 D4 标签。
- 校准集：`fixtures/reviewer-calibration.json`（6 条短文，3 条含编造人名/地名、3 条干净、1 条否定句），答案在 `fixtures/reviewer-calibration-key.json`，复核者提交后对照。目的：避免把「没有检出」当成「能检出」。
- 复核者不参与本实验的批次运行，不看 `review-v3.json`、`fact-omission-v3.md` 与任何 N6 结论。

## 3. 流程

1. 复核者独立完成盲包与校准集，写成 `fixtures/review-v3-independent.json`（格式同 `review-v3.json` 的 `cases`，但不含 `n6` 字段）。
2. 校准集先对答案：编造的专名/地点必须被标出，否定句必须判「未传达」。若校准不过，先校准再进入正式标注，不进入分歧统计。
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

## 5. 与后续实验的关系

- 独立复核完成前，N4 对照批不登记。
- 独立复核的结果只用于两件事：给 v3 一个可引用的质量记录；把「哪些判据容易分歧」写进 N4 的验收协议（例如「移动算不算完整」）。
- 复核者不参与 N4 的设计，避免设计者与评判者同源。
