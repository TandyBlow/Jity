# Proposal: goal-narr-targeted-v9

## Why

v8 的五回合仍有多回合「主角也看规则牌」的填充。用户要求继续手写数据并强调质量。按失败形状设计 52 条定向样本（四场景×九形状），用同一批真实状态块，正文全部手写。

## What Changes

- 52 条定向手写样本（问话+只有 NPC 看规则 / 只有主角看规则 / 两人都看 / 等待+NPC 短讯机 / 清点+NPC 看规则 / 移动+让路 / 交接失败 / 想上楼但留在原地 / 问话无结果），检查器 0 命中；与 v8 合成 304 行训练 v9。
- v10 再加 6 条「交接失败+NPC 看规则」样本（310 行），待训练。
- 评估臂指向 v9（`f32fada0…`）。

## Capabilities

（无；手写数据与测量。）

## Impact

- 本地 `.local/narr-train/targeted-v9*`、`sft-v9/v10`、v9 权重（gitignored）。
- `frontend/src/app/world-local/page.tsx`（评估臂 sha）。
- 证据：`artifacts/goal/narration/run111-17b-lora-v9-5turn.json`、`read-v9-targeted-20261123.md`。
