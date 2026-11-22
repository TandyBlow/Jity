# Proposal: goal-latency-analysis

## Why

D-024 要求把「再次可行动 ≤60 秒」变成可测数字，但授权调度改造前需要先知道上界：如果玩家自己的点（计划里永远是第一点）完成得足够早，早交还就有意义；如果第一点本身就超过 60 秒，改造也救不了。现有 run27–run35 的逐点叙事时间已经记录，可以直接量出这个上界，不需要先写调度原型。

## What Changes

- 新增分析证据 `artifacts/goal/narration/latency-analysis-20261122.md`：从 run27–run35 的 `product.pointNarration` 提取每个回合第一点的开始/完成时间，对比整轮等待。
- 在 `design/goal/decisions.md` 的 D-024 追加测量结果：笔记本档早交还上界 18.7–50.8 秒（16 个回合全部 <60 秒）；移动模拟档第一点 39.7–150.2 秒，s05 已超 60 秒。
- 不修改产品代码、不改调度、不改门槛；D-024 的决定状态保持 `pending-user`。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。纯测量与文档；`.openspec.yaml` 设 `skip_specs: true`。

## Impact

- `artifacts/goal/narration/latency-analysis-20261122.md`（新增）
- `design/goal/decisions.md`（D-024 追加测量）
- 不涉及 `frontend/`、`backend/`、`openspec/specs/`。
