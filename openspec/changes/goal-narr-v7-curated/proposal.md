# Proposal: goal-narr-v7-curated

## Why

用户选择「手工造数百条样本」。按世界登记表生成 199 条变体提示，用写作/校验工作流写目标，检验归因与未结算移动两个形状能否在 1.7B 上压到零。

## What Changes

- 199 条变体（swap 149、unsettled 48、move 2）；工作流 107 接受；过滤长复述/主角事实交换后 50 条，检查器再筛 5 条，45 条新样本 + 84 原有 = 129 行 SFT。
- 训练 v7，五回合与十输入复测；评估臂随后恢复 v5。

## Capabilities

（无；训练数据与测量。）

## Impact

- 本地 `.local/narr-train/`（变体、目标、v7 权重，gitignored）。
- `frontend/src/app/world-local/page.tsx`（评估臂切 v7 后恢复 v5）。
- 证据：`artifacts/goal/narration/run101-17b-lora-v7-5turn.json`、`run102-17b-lora-v7-10turn.json`、`read-v7-curated-20261123.md`。
