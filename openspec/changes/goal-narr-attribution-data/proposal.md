# Proposal: goal-narr-attribution-data

## Why

D-022 的数据路线验证：v3 的十输入硬错是归因（把诺诺的规则阅读记到主角）与物品转移。用户主张「数据足够丰富即可」，因此在同域 84 条上补世界校验的归因变体，检验扩充数据能否降低硬错率。

## What Changes

- 新增 `.local/narr-train/make_variants.py`：只交换动作/观察类结算事实的主语（规则阅读、让路、观察、询问），跳过主角自己的事实、含他人归属物品的事实和所有移动/位置动词；目标句同步换主语。
- 生成 23 条变体，扩展检查器 0 命中；DPO 的 84 对与工作流 9 条变体因失败/归属错误不采用。
- 107 行 SFT 训练 v5，转换 GGUF，十输入复测。

## Capabilities

（无；训练数据与评估臂。）

## Impact

- 本地 `.local/narr-train/`（生成器、变体、v5 适配器，均 gitignored）。
- `frontend/src/app/world-local/page.tsx`（评估臂 sha 指向 v5）。
- 证据：`artifacts/goal/narration/run98-17b-lora-v5-10turn.json`、`read-v5-attribution-20261123.md`。
- 默认模型不变；不改门槛。
