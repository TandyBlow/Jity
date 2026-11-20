# Design: G4 单机可玩页面接线

## Context

`app/world-local/page.tsx` 现在自己渲染输入、条目、状态与按钮，但 `components/world-local/` 的 `GameControls`、`HistoryPanel`、`ProgressStatus`、`WorldStatusPanel`、`NarrationView` 一个都没接。G2 已修内核 cancel 与页面 stop/failure 恢复、`__worldBusy`、驱动回合边界；G4 负责把这些交互接到产品页并加 e2e。

## Decisions

### 1. 组件接线方式

- 组件是展示层：props 由页面状态映射，组件不发请求、不读缓存、不写快照。
- `HistoryPanel` 的数据来自 `transport.points` + `transport.narrations`，映射用 `historyEntriesFromPoints`（`view-model.ts` 已有）。
- `onSelect` 只设置 `selectedPointId` 并展示该点的状态/正文；不改 head、不调 apply。
- `onRegenerate` = `narration_delete`（mode=head 或 claim）→ `session.start()` 重新声明/生成；状态摘要前后必须一致。

### 2. 暂停/恢复

`GameControls` 的 pause/resume 调 `session.pause()/resume()`；按钮可用性用 `controlAvailability`。恢复不重掷骰：会话的 checkpoint 已保存 frozen work 与 roll 记录。

### 3. 隔离自检

页面启动时读 `crossOriginIsolated`，false 时显示持久 warning（不是一次性 toast），并写入 `__worldGpu`/证据。COOP/COEP 由 `next.config` 的 `/world-local` 头提供。

### 4. 恢复与空回合

- `turn_in_progress` 分支保持 G2 的 phase ready + 文本归还；G4 补按钮状态与提示。
- 结算失败后保留已提交点正文；无提交则归还输入、删占位。
- 自动轮重复与 `position_invalid` 按 G2/G4 测试修；不新增运行时叙事检查。

### 5. e2e

`frontend/e2e/world-local.spec.ts` 用 Playwright 驱动真实 `/world-local`：启动 → 3 次输入 → 暂停 → 刷新 → 继续 → 历史选中 → 删除叙事 → 重生成 → 断言状态摘要不变；`--block-api` 场景断言只有静态资源与可选 `/local-progress`。

## Risks / Trade-offs

- [页面重构破坏既有证据钩子] → 保留 `__worldTurns/__worldArm/__worldBusy/__worldSnapshot/__worldRestore`，e2e 断言它们存在。
- [历史选中误改状态] → 选中只读，不调用 transport 写操作。
- [重生成读到旧正文] → delete 后重新 claim，输入投影只读已提交状态；e2e 断言摘要不变。

## Non-Goals

- 不改内核 apply/merge/commit/replay（G2 已完成）。
- 不加运行时叙事检查或程序补写。
- 不做两设备同步（G7）。
