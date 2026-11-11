# 05 按点叙事队列交接（2026-11-11）

## 提交与基线

- 05 工作树：`D:\others\Jity\.local\parallel-local-game\worktrees\05-point-pipeline`
- 分支：`goal/local-05-point-pipeline`
- 基线：`a7dbf94ac021ef2d59e740279b338bc8e1cac7b8`
- 实现提交：`d5ddd00e61d46be4d2aff4fd60238fba9f40571a`
- 取消归属测试提交：`803c9613d1cd7f38ae05605e06ddd5301a95d356`
- 旧 `05-kernel` 树未改动。

实现提交在基线之上改了 05 独占文件，并附带两个只针对 06 文件的补丁，外加一个针对已合入 06 的 `session.ts` 的增量补丁：

```text
frontend/src/lib/world-engine/schedule.ts
frontend/src/lib/world-engine/controller.ts
frontend/src/lib/world-engine/local/transport.ts
frontend/src/lib/world-engine/local/point-narration/queue.ts       (new)
frontend/src/lib/world-engine/local/point-narration/queue.test.ts  (new)
frontend/src/lib/world-engine/local/point-narration/overlap.test.ts (new)
design/parallel-handoff/05-point-pipeline-06-session.patch
design/parallel-handoff/05-point-pipeline-06-game-model.patch
design/parallel-handoff/05-point-pipeline-06-session-followup.patch
```

06 已合入 `d5ddd00e`（`6ca1d7a3`）；增量补丁 `05-point-pipeline-06-session-followup.patch` 让 06 的 `start()` 对回合内 pending head 也走同点恢复，并避免新 root 在 `create_world` 前抢占。该补丁已对 06 当前 `HEAD`（`f4893c53`）做 `git apply --check` 通过。

## 机制

### 1. 提交后冻结一个点，并启动该点的正文作业

`commit_point` 成功、控制器把响应 adopt 进 served state 后，控制器把新 head 的 `pointId` 放进 `PointNarrationQueue`。队列只接收 pointId；它自己按点读取：

1. `narration_get(pointId)` 确认还没有 ready；
2. `get_context` 判断该点现在是 head 还是历史点，选择 `head` / `history` claim；
3. `get_state(pointId)` 得到该点自己的 `after`、`previousPointId`、`timeAdvance`、`entityDeltas`；
4. 若有前一点，再 `get_state(previousPointId)` 得到 `before`；
5. `assembleNarrationInput` 后调用 `model.generate('narration', pointId, input)`；
6. 模型文本原样提交给该 pointId 的 `narration_submit`。

队列按 commit 顺序串行处理点，因此正文提交顺序与点顺序一致；一个点没结束时不会开始下一个点的正文。正文只写 `record.narrations[pointId]`，不 apply point、不改 head、不写 controller memory。

状态结算仍由原来的 controller 循环推进。两者共享同一个 `LocalWorldTransport`；transport 把写操作串行化（`writeTail`），所以结算提交与正文提交不会互相覆盖记录。读仍立即返回，可能读到旧快照；claim/submit 对 `claim_expired` / `claim_fenced` / `version_mismatch` 会重新取同一点的 claim，然后用**同一段已生成文本**提交，不重新调用模型。

### 2. 为什么下一时间点可以在正文生成时结算

只有下面全部成立时，scheduler 才允许状态计算穿过 pending gate：

- `narrationBusy = true`（队列确实在处理已提交点）；
- 当前有 active advance（不是新的玩家回合）；
- gate 是 pending；
- `blockedReasons` 只有 `narration_pending`。

此时 `scheduleNext` 跳过旧的内联 narration 分支，允许 `modelBlocked` 的状态任务继续；`commit_point` 的 expected head/version/checkpointRevision 仍由当前 served state 绑定，所以两个点仍严格按顺序提交。暂停、租约失效、head 正文失败等其它 blocked reason 都不会被绕过；新的玩家 advance 仍要求 head ready。

`LocalGameSession` 的终态仍会等队列清空再返回，因此旧的 `await`/handoff 语义不变；等待发生在状态结算已经结束后，不是把正文挪到下一段串行阶段。

### 3. 恢复、晚到、空文本与错误

- 冷启动/刷新时，controller 用 `list_points` + 每点 `narration_get` 找出所有仍为 `pending` 的点，按 sequence 重新入队。`failed`、`missing` 不自动重生成，避免刷新时偷偷重抽正文。
- 队列的 job 以 pointId 为唯一归属。p1 的模型晚到、或 p1 的 claim 在 p2 提交后过期，都只重取 p1 claim 并提交 p1 文本；不会贴到 p2 head。
- 空字符串/全空白提交为 `failed`，`failureReason=empty_model_output`，text 为 null；不写程序正文。
- 模型抛错提交为 `failed`，原因保留；取消/abort 的 `ModelCancelledError` 不提交失败，点保持 pending，便于同一回合恢复。
- `get_state` 缺字段（读能力不完整）提交为 `failed`，`narration_read_incomplete`，不把空增量当事实。
- 控制器在队列写出后通过一次 `get_context` 刷新 served head/control，防止旧 pending gate 被内联 narration 再 claim 一次。

## 06 接线补丁

两个补丁都是相对 `a7dbf94a` 的普通 `git apply` 补丁；06 合入时请用 3-way 或先在其锁定提交上检查。

### `05-point-pipeline-06-session.patch`

`frontend/src/lib/world-engine/local/session.ts`：

- 新增 `LocalGameOptions.narrationOverlap`，产品 session 默认 true；
- 把 `ControllerDriver` 的 `narrationOverlap` 打开；
- controller 的 `onCommit` 包装成：先调用页面原有 `options.onCommit`，再在 `committed` 阶段调用 `productModel.onPointCommitted(pointId)`；
- `start()` 对当前 head 的 failed，或回合内（`round`/`advance` 存在）的 pending 状态调 `driver.retryNarration()`：failed 是页面已有的恢复重试，pending 是模型 abort 后对同一点的恢复；都不重新结算。新建世界的 root 仍走正常 bootstrap。

### `05-point-pipeline-06-game-model.patch`

`frontend/src/lib/world-engine/local/game-model.ts`：

- 在 `results` 收到 `pointId` 时，累计该点的结果行；用事实文本去重，累计该点的事实；
- `onPointCommitted(pointId)` 冻结该点的 `resultsText`、`facts`、`playerInput`；
- `narration` 优先读该点快照，并把它传给 in-model prompt 和 candidate runner；
- 这样 p1 的正文不会读 p2 的 `lastResultsText` / `lastSettledFacts` / 新回合的 `lastPlayerInput`。

`schedule.ts` 只有在 `narrationOverlap=true` 时才在 `results` 输入里加 `pointId`；B3/harness 的旧输入 fixture 完全不变。

### 页面

不需要改 `page.tsx` 的 narration 回调。页面继续按 `pointId` 收 `onNarrationProgress` / `onNarrationComplete`，正文来源标签和 evidence 都保留。若页面绕过 `LocalGameSession` 直接构造 `ControllerDriver`，必须自己传 `{ narrationOverlap: true }` 并在 commit 时调用 model 的 `onPointCommitted`；产品路径不需要。

## 验证

本地命令（frontend 目录）：

```bash
node node_modules/typescript/bin/tsc --noEmit --pretty false
node node_modules/vitest/vitest.mjs run src/lib/world-engine/local/point-narration --maxWorkers=1
node node_modules/vitest/vitest.mjs run src/lib/world-engine --maxWorkers=1
node node_modules/vitest/vitest.mjs run --maxWorkers=1
```

结果：

- `tsc --noEmit`：通过。
- point-narration：4/4 通过。`overlap.test.ts` 用真实 `LocalWorldTransport` + `ControllerDriver`：p1 正文被 deliberately hold，p2 仍完成 commit；释放 p1 后 p1 文本只落在 p1，p2 保持自己的文本；从中间 record 恢复只补正文、不发 action，不重复 commit。
- world-engine：`966 passed / 3 skipped`。
- 完整 frontend（**临时应用两个 06 补丁后**）：`1046 passed / 3 skipped`，74 个测试文件 72 通过、2 跳过。未应用补丁时同样 1046 通过；补丁只改变产品 session/game-model 路径，不改变既有测试预期。
- 没有启动服务、模型、GPU 或真实页面；真实双引擎/首段/恢复测试仍由 09 执行。

## 未完成 / 边界说明

- **同引擎内部串行**：队列与结算可以重叠，但同一个 `InferenceEngine` 仍按其自身串行；不同引擎的并发只由 09 真实量测，不在 05 的受控测试里声明。
- **恢复后的 per-point 结果缓存**：06 的冻结快照是内存态；刷新后新 game-model 没有旧点结果文本，narration 仍只用点自身的 `before/delta/after`，不会读后点，也不会伪造结果。若产品要求刷新后仍保留“该点结算结果句子”给候选，需要另做持久化（本次未做）。
- **failed/pending 正文的自动重试**：队列不自动重试 failed；`start()` 只对当前 head 的 failed 或 pending 做一次显式恢复重试，空文本/推理错误仍需要页面已有的用户恢复路径。pending 恢复只续同一点，不重掷骰点或重结算。
- **取消**：服务端 `checkHeadReady` 对 pending head 的 cancel 仍然拒绝，页面原有的“先补正文再取消”流程不变；队列在模型 abort 时让该点保持 pending，不重新结算，也不改写其它点。没有把 cancel 变成可绕过正文生成的路径。
- **旧存档兼容**：只把仍为 `pending` 的点加入恢复队列；旧的 `missing` 不自动生成，`failed` 不偷偷重抽。`narrationOverlap` 关闭时 controller 维持原有串行 narration 行为。
- **未在 05 宣布产品验收**：60s 首段/性能、真实页面、自动轮连续 3/10/20 回合、真实双引擎仍待 06 接线后由 09 采证。
