# Proposal: goal-prose-attribution

## Why

run92 的人工读评发现两类硬错，开发期检查器完全没有类别可命中：主角拿了别人的物品（路明非被写成握诺诺的短枪）、正文把主角放到与已提交状态不符的地点（状态仍在西侧服务巷，正文写到二层平台）。现有 `check-prose-facts.mjs` 只覆盖识别带、门、回声、占位、元注记、凭空感官与未知实体，导致 run92 的检查器报 0 而实际 6/9 有正文回合硬错。

## What Changes

- 新增 `place_claim`：从叙事提示抽取「路明非现在在 X」，若正文用移动动词把路明非放到另一个登记地点（同一建筑群除外）则命中。
- 新增 `item_owner_claim`：若提示把某物品归给某角色、且没有任何句子把同一物品归给主角，而正文让主角使用该物品（含「枪口」等别名）则命中。
- 两个门都只在开发期脚本里，不进产品路径；用教师数据 84 条与 run89 干净回合验证不误报。

## Capabilities

（无；纯开发期检查器。）

## Impact

- `frontend/scripts/product-acceptance/check-prose-facts.mjs`。
- 证据：`artifacts/goal/narration/prose-facts-check-run92.json`、`read-17b-lora-v3-10turn-20261123.md`。
- 不改产品契约、默认模型或门槛。
