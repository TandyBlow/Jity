# Proposal: goal-narr-targeted-v12

## Why

run121 s15 暴露新形状：结算把「诺诺放置短讯机」写成路明非的动作（检查器 `item_owner_claim` 命中）。v11 数据覆盖了 NPC 看规则/短讯机/钥匙/枪，但没有覆盖「NPC 放置物品」。

## What Changes

- 10 条手写样本（五个基 × 两个变体）：NPC 放置短讯机/相机/演习枪，主角等待、清点或问话，从不接手 NPC 的物品。
- 检查器 0/10；`sft-v12` 338 行（v11 328 + 10）。
- 训练待用户触发；数据与检查器证据入库。

## Capabilities

（无；手写训练数据。）

## Impact

- 本地 `.local/narr-train/targeted-v12*`、`sft-v12.jsonl`（gitignored）。
- 证据：`artifacts/goal/narration/read-v12-data-20261123.md`；检查器结果见本地 `v12-check.json`。
