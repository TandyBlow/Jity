# 语义 → 实验平台：任务达成金标独立核查请求

日期：2026-11-28。分支：`semantic-micro-only`（已推送）。相关工作：S01（严格标准）、S02（页面冒烟）、E55–E57（历史编号）。

## 请核查什么

`artifacts/goal/semantic-micro/bench-v1.jsonl`：120 条 `(goal, fact, verdict)` 人工读评样本。其中 `verdict` 是语义 Agent 按 S01 给的标签（yes 3 / partial 6 / no 111）。

请做**盲读**：只看 `goal` 与 `fact`，按 `design/research/S01-task-achievement-standard.md` 的五条标准独立给 `yes / partial / no`；不要先看 `verdict`、`llm`、`committed` 字段。

## 交付

- 在 `experiments/semantic-micro/bench-v1-platform.jsonl`（gitignored）或单独分支写：`id, platform_verdict, note`。
- 汇总：一致数、分歧数、分歧样本列表。
- 不要修改 `bench-v1.jsonl` 原文件；分歧由双方并排记录。

## 分歧处理

1. 按世界目标文本逐条对照 S01 五条标准。
2. 仍不一致的样本标 `disputed`，交给用户裁决；不擅自改标准。
3. 一致样本进入 v2 金标；分歧样本不进入训练。

## 后续

bench-v1 正例不足（只有 3 条 yes）。语义侧会从 73 个世界任务设计「达成 / 部分 / 未达成 / 否定」输入跑真实回合，新增样本先给平台 Agent 同样盲读，再合并。

**Files.** `bench-v1.jsonl`、`S01-task-achievement-standard.md`、`S02-goal-stage-smoke.md`。
