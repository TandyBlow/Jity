# Design: goal-quality-baseline

## Context

见 proposal。检查器的 `unknown_entity_claim` 需要叙事提示里的已知名单；run27+ 的证据都有 `product.narration.prompt`，可以直接批量跑。run41 的套件证据有 s06 合法失败回合，会命中原名门。

## Goals / Non-Goals

- Goals：给出按类别、按回合的基线计数，作为 D-022 的统一尺子。
- Non-Goals：不把 dev 命中数当验收门槛；不重复跑模型。

## Decisions

1. **只用已有证据**：不新增模型调用；成本是一次 Node 扫描。
2. **按回合去重**：同一回合多类别命中只算「被标记回合」一次，类别分列。替代方案（按 flag 计总数）会放大重复输入的影响。
3. **写明重复夹具的偏差**：s06/s05 在多个 run 里重复，命中数不代表自然分布。

## Risks / Trade-offs

- [证据重复] → 报告同时给「回合数」与「不同夹具」两种口径。
- [检查器类别有限] → 基线只覆盖既有五个类别，不代表全部硬错。

## Migration Plan

不适用。

## Open Questions

无。
