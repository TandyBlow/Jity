# Tasks: G4 单机可玩页面接线

## 1. 隔离与注释

- [ ] 1.1 页面启动读 `crossOriginIsolated`，false 显示持久告警并写入证据；`next.config` 头已存在。
- [ ] 1.2 清理 `page.tsx` 头部过期注释（localStorage/0.5B），写清 IndexedDB、Qwen3-1.7B、无 HTTP 游戏 API。

## 2. 组件接线

- [ ] 2.1 `HistoryPanel`：由 `historyEntriesFromPoints` 映射已提交点；`onSelect` 只读展示；断言 head/摘要不变。
- [ ] 2.2 `onRegenerate`：`narration_delete` → `session.start()` 重生；不读旧正文；状态摘要不变。
- [ ] 2.3 `GameControls`：pause/resume 接 `session.pause()/resume()`；恢复不重掷骰。
- [ ] 2.4 `ProgressStatus`/`WorldStatusPanel`/`NarrationView` 接页面状态与进度。

## 3. 恢复与回合边界

- [ ] 3.1 `turn_in_progress`/结算失败后按钮与输入恢复；空占位回合删除；已提交正文保留。
- [ ] 3.2 自动轮重复与 `position_invalid` 回归；失败保留。
- [ ] 3.3 刷新恢复：10/10 条目、head、摘要一致。

## 4. e2e

- [ ] 4.1 新增 `frontend/e2e/world-local.spec.ts`：启动 → 3 次输入 → 暂停 → 刷新 → 继续 → 历史 → 删除叙事 → 重生成 → 状态不变。
- [ ] 4.2 `--block-api` 运行通过；网络记录只有静态资源与可选 `/local-progress`。
- [ ] 4.3 `npm run build`、两套 typecheck、lint 全绿。

## Workflow follow-up

- 更新 `design/goal/ledger.md`、`decisions.md`、`design/README.md`。
- `openspec validate "goal-g4-page-wiring" --strict`，归档，按路径 commit，打 G4 tag。
