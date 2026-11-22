# Proposal: goal-sched-handback

## Why

D-024 已获批准（2026-11-22）：先做「玩家点交还」评估臂原型，量出真实交还时间，再决定是否改产品契约。测量显示笔记本档第一点叙事完成在 18.7–50.8 秒，而整轮等待 64.9–180.7 秒，差值就是玩家多等的尾部；原型要把这段尾部从玩家等待里拿掉。

## What Changes

- 新增 URL 评估开关（例如 `schedHandback=player`），只在显式开启时生效；默认行为不变。
- 开启后：回合计划在主角点结算并叙事完成后结束，不再等待后续自动链与继续判断；按 D-024 批准的范围，其余点后台结算或延后（原型先验证交还时点与状态一致性）。
- 新增验收驱动测量：提交→再次可行动的真实时间、交还后状态回放一致性、以及后台/延后点是否仍被正确结算或记录。
- 不改变默认调度、不改验收协议、不换模型。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。评估臂不进入产品默认路径；`.openspec.yaml` 设 `skip_specs: true`。

## Impact

- `frontend/src/lib/world-engine/`（controller、schedule、local/session 的最小改动，评估开关）
- `frontend/src/app/world-local/page.tsx`（URL 开关与证据字段）
- `frontend/scripts/product-acceptance/`（s05/s06 测量）
- 证据：`artifacts/goal/semantics/`
