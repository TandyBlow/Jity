# Proposal: goal-narr-projection

## Why

D-022 的剩余非换模型手段之一是叙事投影瘦身：run92 显示正文会把别人的物品、规则阅读搬到主角身上，怀疑是全量外观/物品清单在提示里提供了素材。需要实测瘦身后是否减少归因硬错，以及会丢失哪些细节。

## What Changes

- `instructNarrationInput` 增加 `compact` 参数：同一段指令，brief 去掉地点外观、房间物品与长相、在场其他人的外貌；保留玩家动作、结算结果、时间、位置、在场人名/位置、他人位置/任务/精神变化。
- `LocalGameModel` 增加 `narrationProjection`；页面通过 `?narrationProjection=compact` 暴露评估臂，并记入 `__worldArm`。
- 默认投影不变（`full`）；不换模型、不改门槛。

## Capabilities

（无；评估臂与测量。）

## Impact

- `frontend/src/lib/world-engine/local/prompt.ts`、`local/game-model.ts`、`app/world-local/page.tsx`。
- 证据：`artifacts/goal/narration/run96-17b-lora-v3-compact-10turn.json`、`read-compact-projection-20261123.md`。
