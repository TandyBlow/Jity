# Tasks: G2 浏览器状态内核收口

## 1. 失败回合可终止

- [x] 1.1 在 `controller`/`local-transport` fixture 中复现：结算失败（updates 语义拒绝）→ cancel → 新 submit；断言当前 `turn_in_progress`。
- [x] 1.2 回归测试转绿：cancel 在结算失败后关闭 advance，下一次 submit 被接受；`checkpoint_start_advance` 仍要求 head ready。failed head 放宽不在本变更加。
- [x] 1.3 页面 `turn_in_progress` 分支恢复 `phase='ready'` 并归还输入；验证按钮重新可点。

## 2. 未决操作定案

- [x] 2.1 `checkpoint_restore_group_work`：声明非产品语义，保留 `frozen_work_missing`；写入 `decisions.md`。
- [x] 2.2 `get_context.recovery:null`：声明本地恢复不依赖服务端 recovery；写入 `decisions.md`。

## 3. Restore 不变量

- [x] 3.1 session restore 前调用 `state-invariants/guarded-restore`；失败拒绝并报告代码。
- [x] 3.2 corrupt-restore 夹具（point 链断裂）被拦下，状态不应用、不写回。
- [x] 3.3 正常存档恢复仍通过既有 `session-recovery.test.ts`。

## 4. 差分向量

- [x] 4.1 Python 生成器输出 `artifacts/goal/kernel-diff.json`：S0、逐点 Δ、期望 digest、拒绝样例。
- [x] 4.2 覆盖空列表、0、嵌套位置、物品移动、任务层级、非 BMP 排序、拒绝路径。
- [x] 4.3 TS 测试逐字节断言 `buildInitialState`/`applyPoint`/`pointEntityDeltas`/`replayWorld`/canonical digest。
- [x] 4.4 证据 `artifacts/goal/kernel-ops.md` 记录 32 操作定案与向量结果。

## 5. 骰点与恢复

- [x] 5.1 冻结骰点阈值、程序持有、requestId 去重；测试锁定。
- [x] 5.2 补 linked/instant successor time 测试。`state.test.ts` 覆盖 instant 边界/零时长/拒绝，`controller` 场景覆盖 instant 点；全量套件复核。
- [x] 5.3 多标签租约、刷新、重复提交、取消恢复测试。
- [ ] 5.4 全量 `npx vitest run` 与两套 typecheck 全绿。

## 6. 解锁 G3

- [ ] 6.1 用修复后的内核重跑 `turns-10.json`，补足 10 个正常点并更新 `timing-baseline.json`。

## Workflow follow-up

- 更新 `design/goal/ledger.md`、`decisions.md`、`design/README.md`。
- `openspec validate "goal-g2-kernel-diff" --strict`，归档，按路径 commit，打 G2 tag。
