# design 文档索引

状态：active。日期：2026-11-20。

新读者按这个顺序读：

1. [`goal/goal.md`](goal/goal.md)：最终目标、终态门槛、约束与未决项（只写终态，不写阶段路线）。
2. [`goal/architecture.md`](goal/architecture.md)：运行期权威、产品路径、静态 S0、模型资产、七项职责。
3. [`goal/decisions.md`](goal/decisions.md)：冲突裁决与已确认项。
4. [`goal/ledger.md`](goal/ledger.md)：R01–R16 状态与开放任务。
5. [`goal/acceptance.md`](goal/acceptance.md)：20 输入、计时、叙事、离线、两设备、证据格式。

## 状态标签

| 标签 | 含义 |
|---|---|
| active | 当前执行依据；冲突时以 `goal/decisions.md` 为准 |
| reference | 语义、协议或实验参考；不能单独作为当前验收证据 |
| historical | 历史记录；分支/工作树/基线可能已失效，保留证据价值 |
| superseded | 已被 `goal/` 取代；保留原文，运行期含义按新决策 |

## Active

| 路径 | 用途 |
|---|---|
| [`goal/goal.md`](goal/goal.md) | 唯一 goal 入口 |
| [`goal/goal-mode-short.md`](goal/goal-mode-short.md) | ≤4000 字短 goal（设置入口，指向长文） |
| [`goal/goal-mode-prompt.md`](goal/goal-mode-prompt.md) | goal 模式长文任务书 |
| [`goal/architecture.md`](goal/architecture.md) | 运行期与部署事实 |
| [`goal/decisions.md`](goal/decisions.md) | D-001–D-024 与已确认项 |
| [`goal/ledger.md`](goal/ledger.md) | R01–R16 唯一状态账本 |
| [`goal/acceptance.md`](goal/acceptance.md) | 验收协议 |
| [`goal/decision-brief-20261122.md`](goal/decision-brief-20261122.md) | D-022/D-023/D-024 的决策简报 |

## Reference

| 路径 | 用途 | 注意 |
|---|---|---|
| [`final-browser-game-design.md`](final-browser-game-design.md) | 产品语义：世界状态、地点/物品/人物、任务树 | 开局 S₀ 由静态文件构造，不是动态生成 |
| [`browser-world-state-workflow.md`](browser-world-state-workflow.md) | 十一部分原设计与规则语义 | Python 权威、延迟、A/B/C/D 段落已被取代 |
| [`world-protocol/v2/README.md`](world-protocol/v2/README.md) | v2 契约、规范编码、冻结向量 | 运行期权威是浏览器内核；Python 仅差分预言机 |
| [`world-engine-reports/components/README.md`](world-engine-reports/components/README.md) | N1–N5 组件契约、训练与实验 | 只作候选与历史证据，状态以 `ledger.md` 为准 |
| [`../data/worlds/README.md`](../data/worlds/README.md) | 静态世界 `dragon-raja-free-day` 的规模、哈希、读取方式 | 公开开发世界，不是未见终验世界 |

## Historical / Superseded

| 路径 | 状态 | 说明 |
|---|---|---|
| [`narration-single-model-goal.md`](narration-single-model-goal.md) | superseded（局部） | 保留 goal v10 的目标、静态 S0、raw-output、R 表与完成条件；分支/工作树/基线/部署细节被 `goal/` 取代 |
| [`world-engine-reports/full-design-implementation-direction.md`](world-engine-reports/full-design-implementation-direction.md) | superseded（局部） | 保留 R01–R14/R16 语义与 fail-fast 证据纪律；P0–P3、A/B/C 归属、Python 权威、动态 R15 作废 |
| [`browser-world-state-work-split.md`](browser-world-state-work-split.md) | superseded | A/B 分工与双工作树历史 |
| [`world-engine-reports/worktree-coordination.md`](world-engine-reports/worktree-coordination.md) | superseded | A/B/C/D 工作树协调历史 |
| [`world-engine-reports/component-boundary-audit-20261028.md`](world-engine-reports/component-boundary-audit-20261028.md) | historical | 2026-10-28 源码快照；契约哈希与边界未按当前树重跑 |
| [`parallel-handoff/`](parallel-handoff/) | historical | 2026-11-10–11-20 goal line 交接记录；分支/工作树已失效 |
| [`component-io-and-commit-turn.md`](component-io-and-commit-turn.md) | historical | CAMP/Needle 3 时期组件 I/O 设计稿 |
| [`world-engine-reports/server.md`](world-engine-reports/server.md) | historical | 服务与 A3-2 冻结记录；冻结范围独立有效，不作浏览器本地验收 |
| [`world-engine-reports/h2-recovery.md`](world-engine-reports/h2-recovery.md) | historical | H2 恢复记录；独立冻结范围 |
| `../artifacts/` | historical | 验收归档；旧 artifacts 不自动升级为当前验收证据 |

## 冲突处理

1. 先查 [`goal/decisions.md`](goal/decisions.md)。
2. 决策未覆盖的，按 `goal/goal.md` 的最终目标与硬门槛判断。
3. 仍不明确的，记 `pending-user`，不按文档日期新旧猜权威。
4. 旧文档保留原文；新增理解写在 `goal/`，不直接改写历史结论。
