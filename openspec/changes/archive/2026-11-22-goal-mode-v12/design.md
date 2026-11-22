# Design: goal-mode-v12

## Context

见 proposal。现行两份文本（`goal-mode-prompt.md` 12,551 字节；`goal-mode-short.md` 2,248 字节）把 v11 的 G1–G8 顺序写死，且不含移动端与「再次可行动 ≤60 秒」。Goal v12（`goal.md`）已改为终态文本，OpenSpec 归档 change 与 tag 仍是证据。

## Goals / Non-Goals

- Goals：短版可直接粘贴为 goal 设置；长版供执行 agent 完整阅读；两份文本都以终态为目标，并强制用 OpenSpec 管理工作包与文档。
- Non-Goals：不写阶段路线；不复制 `acceptance.md` 的流程细节；不替用户裁决 D-022/23/24。

## Decisions

1. **工作包命名改为 `goal-<slug>`**：v12 没有 G 编号，沿用 `goal-g<N>-<slug>` 会制造不存在的阶段。替代方案（保留 G 编号）与终态文本冲突。
2. **未决项作为闸门**：D-022/23/24 未裁决前，agent 不得自行推进对应改造；文本里逐项列出。
3. **短版必须自带 OpenSpec 段落**：设置入口只注入短版，不能依赖长版才看到强制流程。
4. **基线写 `c1f93c99` 与 tag `goal-v12-final-20261122`**：开工检查指向 Goal v12 文本的提交与标签。

## Risks / Trade-offs

- [短版过长被设置入口截断] → 控制在 4000 字内，实测字数后提交。
- [旧会话仍引用 G 编号] → 长版注明 v11 的 G 线已废弃，历史证据看归档 change 与 tag。
- [未决项被当成任务] → 单列「需要用户决定」，并写明未经批准不得动手。

## Migration Plan

1. 重写两份文本；2. `openspec validate --strict`；3. 归档并提交，打 tag `goal-mode-v12-20261122`。回滚：恢复 v11 文本。

## Open Questions

无。D-022/23/24 属于产品决策，不影响本次文本结构。
