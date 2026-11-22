# Proposal: goal-strict-entities

## Why

用户 2026-11-22 批准「程序级合法性校验」：结算事实里出现未登记实体时，程序判该次答案无效并带反馈重试，而不是只靠提示或换模型。这直接落实 R01「未知实体不能靠叙事变成事实」，针对 s06 的 4/5 结算误判。

## What Changes

- 新增默认开启的确定性校验 `strictKnownEntities`：从成员的 `actionText` 取「给/向/让/跟 + 2–3 字」引入名，若不在世界登记的人物/物品/地点名单里、却出现在任何 fact 文本中，抛 `results_unknown_entity:<name>`，走既有重试反馈；重试仍失败则该点中止（可见失败，不写假事实）。
- `SettlementOptions.strictKnownEntities` 与 `GameModelOptions.strictKnownEntities` 透传；页面 `strictKnownEntities=0` 可关闭用于 A/B，证据记录开关。
- 默认开启；`unknownEntityRule` 提示臂保持默认关闭。
- 重试反馈补一句「事实里不得出现未登记的人名、物品或地点」。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。结算内部校验；`.openspec.yaml` 设 `skip_specs: true`。

## Impact

- `frontend/src/lib/world-engine/local/semantics/settlement/{results,types}.ts`
- `frontend/src/lib/world-engine/local/game-model.ts`、`frontend/src/app/world-local/page.tsx`
- 证据：`artifacts/goal/semantics/run43-*.json`
