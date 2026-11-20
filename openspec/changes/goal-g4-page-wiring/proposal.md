# Proposal: G4 单机可玩页面接线

## Why

`components/world-local/` 已有 controls/history/status/progress 组件，但 `app/world-local/page.tsx` 一个都没用：暂停/恢复、历史选中、删除叙事重生、状态/进度展示、隔离自检都缺 UI 接线。G3 的计时还暴露了停止/失败后的 busy 状态与按钮恢复问题（部分已在 G2 前置修复）。G4 把这些交互接到唯一产品页，并加真实页面 e2e。

## What Changes

- 接入 `LocalGameSession.pause()/resume()`：可见的暂停/继续控件与状态标签。
- 接入 `HistoryPanel`：点选已提交点只读查看；`onRegenerate` 走 `narration_delete` + 重新声明/生成，正文不变状态、不读旧正文。
- 接入 `GameControls`、`ProgressStatus`、`WorldStatusPanel`、`NarrationView`（按现有 props 映射页面状态）。
- `crossOriginIsolated` 自检与持久告警；COOP/COEP 由 `next.config` 提供。
- 清理 `page.tsx` 头部过期注释（localStorage/0.5B），写清 IndexedDB、Qwen3-1.7B、无 HTTP 游戏 API。
- 修 `position_invalid`、narration 失败后的 `turn_in_progress`（G2 已修 cancel 主路径，这里补页面恢复与按钮状态）、自动轮重复、空占位回合。
- 新增 `frontend/e2e/world-local.spec.ts`：启动 → 3 次输入 → 暂停 → 刷新 → 继续 → 历史 → 删除叙事 → 重生成 → 状态不变。
- 服务器关闭（`--block-api`）运行通过；网络记录只有静态资源与可选 `/local-progress`。

## Capabilities

### New Capabilities

- `product-page`: `/world-local` 的交互契约：暂停/恢复、历史只读、叙事重生、隔离自检与离线可用。

### Modified Capabilities

None.

## Impact

- `frontend/src/app/world-local/page.tsx`、`frontend/src/components/world-local/*`（只按现有 API 接线，必要小改）。
- `frontend/e2e/world-local.spec.ts`、`next.config.*`（已有 COOP/COEP 头，不改）。
- 证据：`artifacts/goal/page/`（e2e 输出、截图、网络记录）。
