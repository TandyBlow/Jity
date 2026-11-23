# Proposal: goal-narr-v6-weighting

## Why

v5 的硬错剩两个形状（规则阅读归因、未结算移动）。为验证「重复相关样本即可修正」，把对应样本加权复训 v6，检验硬错率是否继续下降。

## What Changes

- 在 v5 的 107 行上加权：问话+诺诺看规则的 7 条各 +4、未结算移动的 31/60 各 +7、诺诺看规则的 5 条各 +2 → 181 行；从 base 重训 v6。
- 十输入复测；评估臂随后恢复 v5。

## Capabilities

（无；训练实验。）

## Impact

- 本地 `.local/narr-train/`（v6 适配器与权重，gitignored）。
- `frontend/src/app/world-local/page.tsx`（评估臂切 v6 后恢复 v5）。
- 证据：`artifacts/goal/narration/run99-17b-lora-v6-10turn.json`、`read-v6-weighting-20261123.md`。
