# Proposal: goal-narr-v12-rejected

## Why

v12 数据（10 条 NPC 放置物品样本）训练完成后需要真实页面验证。run122 暴露新回归：在场的诺诺被写成缺席。

## What Changes

- 集群作业 276342 训练（5 epoch、loss 0.34）；适配器回传、本地量化（Q4_K_M `6a31ad0f…`）。
- run122 五回合 5/5、40.9/48.4/39.9/34.9/33.6 s、检查器 0；但 s02/s03/s05 写「找诺诺…巷里却没有诺诺」，与在场状态矛盾。
- 拒绝 v12，回退 v11（`f6b01bc1…`）；数据保留，下一步 v13 正例对照。

## Capabilities

（无；训练验证与拒绝。）

## Impact

- `frontend/src/app/world-local/page.tsx`（arm sha 回退）。
- 证据：`artifacts/goal/narration/run122-17b-lora-v12-5turn.json`、`prose-facts-check-run122.json`、`read-v12-rejected-20261123.md`。
