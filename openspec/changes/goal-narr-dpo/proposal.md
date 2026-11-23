# Proposal: goal-narr-dpo

## Why

用户提出「小模型只要数据足够丰富就能满足需求」。为验证这条路线，在 v3 LoRA 上做一轮不用新模型的偏好训练（DPO）：同一提示，手写教师目标为 chosen，模型自己的同题输出为 rejected；同时用工作流生成「同一条事实换主语」的归因变体，检验数据扩充能否减少归因硬错。

## What Changes

- 生成 84 对 DPO 样本（v3 自采样）；DPO 训练 v3 适配器（beta 0.1、lr 5e-6、2 epochs），合并为 v4。
- 工作流生成归因变体：7 条基础提示 → 14 个候选 → 对抗校验接受 9 条。
- 十输入集复测 v4；评估臂随后恢复 v3。
- 结论写入 `read-dpo-v4-20261123.md` 与 D-022。

## Capabilities

（无；训练实验与数据。）

## Impact

- 本地 `.local/narr-train/`（DPO 脚本、v4 适配器、合并权重，均 gitignored）。
- `frontend/src/app/world-local/page.tsx`（评估臂 sha 切到 v4 后恢复 v3）。
- 证据：`artifacts/goal/narration/run97-17b-lora-v4-10turn.json`、`prose-facts-check-run97.json`、`read-dpo-v4-20261123.md`。
