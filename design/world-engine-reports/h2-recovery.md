# H2：浏览器恢复与 SQLite 联调验收

当前状态：2026-10-28，**A3-2 关闭、本轮 H2 范围冻结**。完整 H2 矩阵已在固定
集成组合 **A=`1ef34e7`＋B=`21a95f0`**（merge `d1d2de0`）上跑过：main、successor、
post-restart 与三种损坏场景全绿，隔离 SQLite、真实 `ControllerDriver.recover`，
证据见[集成组合验收记录](../../artifacts/h2-integration-d1d2de0/README.md)；
[关闭签字](../../artifacts/a3-2-signoff-d1d2de0.md)与
[冻结记录](../../artifacts/h2-freeze-d1d2de0.json)绑定归档提交 `a41a9d4`。
冻结范围只含本轮约定矩阵：release/acquire 接管，不含 TTL 自然到期、真实
浏览器、B3 全量与真实模型整链。此前 2026-10-27 的冻结记录保留原范围。
此前 2026-10-27 的固定组合 **B=`6b809dc`＋A=`0cb1951`** 记录保留原范围如下。

### 2026-10-27 记录

固定组合的 main、successor、
post-restart 正向路径全部重跑通过，三种损坏场景也重新按声明码停止。
本轮约定的完整 H2 验收矩阵通过，执行步骤与脱敏证据已归档至
[固定组合验收记录](../../artifacts/h2-full-6b809dc-0cb1951/README.md)。
共享物 155 文件逐字节一致，摘要及两侧 pin 均为 `902918016f2bf7eff4cd1afd52da4ca96defdb5ee4082f171fda987de86680c2`。
归档已提交 `e377e46`，随后按用户授权完成上述 A/B 固定组合的
[共同冻结](../../artifacts/h2-freeze-6b809dc-0cb1951.json)，冻结记录绑定该归档提交及清单哈希。
接管采用 release/acquire，重启验证 recover 读取，
具体边界见归档；B3 全量仍暂缓，不新增长期行动历史。本轮未改运行时源码。

## 首批交付历史（以下为 2026-10-26 记录）

状态：2026-10-26。`d6dce8c` 用户复核通过，#7/#9 正常路径关闭。当前交付为 **H2 客户端首批及历史读取子检查**，不宣称完整 H2 刷新/接管 HTTP 验收通过。B3 全量继续暂缓，不新增长期行动历史。

用户在 `.local/` 下独立复跑的记录已落库为 [h2-history-http-review-independent.json](../../artifacts/h2-history-http-review-independent.json)（`world_1`，06:37:45）。B 自跑记录 [h2-history-http-review.json](../../artifacts/h2-history-http-review.json) 已在提交后用干净工作树重新生成：browser head `56e6774`、`status` 为空、`PASS_HISTORY_SUBCHECK`、原始 Δ 与独立期望一致、仅一次 `continuation`；它取代了此前挂在工作区 `d6dce8c` 上的脏树重跑。两者都只覆盖历史读取子检查。冻结工作恢复的现有证据仍是合同标本，不计作真实复制、接管或围栏验收。下一步先与 A 确定[骰点事实与组处理进度读取契约](h2-recovery-read-contract.md)，再推进 A3 与最终 SQLite 联调。下一步先与 A 确定[骰点事实与组处理进度读取契约](h2-recovery-read-contract.md)，再推进 A3 与最终 SQLite 联调。

提交：`cc70105` 是本批唯一代码提交，在干净树上重跑确认前端 519/519（recovery 35/35）、`tsc -p tsconfig.world-contract.json` 与 `tsc --noEmit` 均净；本轮未改任何运行时逻辑。历史子检查与上一句的 519/519 都是用户已完成过的复核，B 在提交后重跑只是把证据绑到提交上，不构成新的验收。

冻结前置的 B 侧唯一可自助核对项已通过：`python -X utf8 backend/scripts/export_world_protocol.py --version v2 --check` 在 `world-browser` 干净树上退出 0、无导出漂移，`design/world-protocol/v2/manifest.json` 的 `contractDigest` 与 A 工作树同为 `abda4555…`。因此 A 候选提交落地后若摘要变化，差值可归到 A 侧，而不是 B 侧残留旧导出。

## 恢复入口

`ControllerDriver.recover(worldId, heldLease?)` 只接受全新、尚未运行过的控制器。`WorldSession` 用 `recoverWorldId` / `recoveryLease` 选项在第一步调度前启动恢复；旧会话失租后的终态隔离仍有效，不能恢复运行旧会话。

- 刷新携带已有租约时，先 `lease_renew` 验证 token/epoch，并自动启动新会话心跳；不向仍被占有的世界申请覆盖式 acquire。
- 无已有授权时，使用新会话 holder/requestId 执行 `lease_acquire`。租约被占用/失效等确定拒绝即停，不循环重取授权。
- 读取 `get_context(includeRecovery=true, leaseToken, fenceEpoch)`。有活动工作却没有 recovery 载荷则停；无活动工作、无后继预约时可以仅恢复已提交点历史。
- `restore_required` 仅原样提交服务端提供的 sourceEpoch/sourceAttempt/manifest。请求不带替代行动原文、不指定目标 attempt；复制后必须重新读取 originals，不能用恢复回执拼造正文。
- 超时/`request_in_progress` 按同 ID/同载荷重发，共用有界重试预算。其他拒绝进入明确停止态，重复 `run()` 不会绕过停止而生成模型输出。

## 冻结工作与当前点

恢复仅保留当前点及已预约后继点的短期工作，不读取或建立已提交行动的长期记录。

- 暂存单元按 `settledUnits` 的顺序恢复其原候选和结果；已访问/已行动人物进入处理集合，不重新询问行动。
- 活动组的每条行动必须有原文。未确认目标的单来源组可从 `targets` 继续，使用逐字相同的行动，不调用 `action`。
- 已保存结果用于后续 updates，不重问 results；已保存完整候选则原样发 `stage_unit`，不通过模型或增量转换重建候选。
- 已封存点丢失本地提交载荷时，调用 Python `preview_point` 重新取得点投影，候选仍是服务端保存的原候选，再提交一次。
- 已预约后继点先复制并验证其载荷；前点提交后，只在服务端实际切到相同后继点时接续，否则停止。该路径尚待真实 A3 联调。
- 未确认的旧 pointPlan 不当作持久化事实恢复。活动点使用已保存身份/时间与冻结顺序继续，已预约后继保留；其后按最新游标重新规划。剩余未确认行动机会所需的 group 身份由程序幂等分配，不让模型生成身份。

## 本轮历史完整性

恢复不把本地新提交的后缀当成本轮全部变化。

1. `list_points` 从根点分页，直到捕获的 head；要求 sequence 从 0 连续、身份不重复、head ID/digest 匹配。短页不是 EOF；缺页、重复或缺序列立即停。
2. 筛出当前 round 的所有点，检查所属 advance、连续性及其末点为当前 head。
3. 每点按明确 `pointId` 调用 `get_state`，读取该点保存的原始 `timeAdvance/entityDeltas`，核对 version/digest/previousPointId。缺字段不当作空 Δ，不做状态差分重建。
4. 同时读取当前 head 状态。恢复尾部再次读取 context，核对 fence/head/round/advance/revision/工作载荷，发生迁移则整个恢复停止。
5. 只有完整验证后才写入新的控制器内存：`roundChanges` 按提交顺序排列；随后本驱动提交的新点继续追加。经完整读取证明本轮无提交点时才允许 `points=[]`。

## 验证

- 新增 `recovery.test.ts` 35 项：冻结原文保真、已确认候选原样暂存、封存后恢复提交及缺候选时停止、后继点的未来基线与身份分配、manifest 复制/重新读取、同载荷超时重试、确定拒绝、短页、跨 100 条分页、原始 supersedes、漏页/漏点/错误摘要/前驱、读取期间状态迁移、资料不全后重复运行仍停止，以及真实 session/driver/心跳接线。
- 前端全量 519/519（此前 484），`typecheck:world` 通过，生产构建通过（既有 warning）。本批未修改后端/共享协议，也未重跑后端全套或 B3 全量评估。
- 真实 HTTP 历史子检查：A `be87679800bdfd313fb9c7bf24bd1317136b81e9` 的 `FixtureBaselineStore` 服务经 HTTP 创建世界、同一轮顺序提交三个有不同 Δ 的点，再用全新 B 控制器恢复。continuation 收到三个点的原始 Δ，与独立手写期望逐字一致。只调用一次 continuation，没有结论写入。证据见 [h2-history-http-review.json](../../artifacts/h2-history-http-review.json)，含 A/B 提交、源文件哈希、契约摘要及操作顺序。

运行（A 服务为本地隔离实例，默认内存服务不代表 SQLite 验收）：

```powershell
# A checkout/backend
python -X utf8 -m uvicorn app.world_app:create_world_app --factory --host 127.0.0.1 --port 18769
# B checkout/frontend
node scripts/review-world-h2-history.mjs http://127.0.0.1:18769 ../artifacts/h2-history-http-review.json ../.local/world-server-worktree
# 注：`.local/world-server-worktree` 默认路径已退役——现行脚本 --server-checkout 必填，此处为历史记录原样保留。
```

## H2 依赖的关闭情况（2026-10-28）

原先列出的三项依赖在集成组合 `d1d2de0` 上均已实测：

1. **骰点读取事实**：恢复载荷现在携带逐成员 `rollRefs`（source/target/trigger/
   rollId）与 `group.rolls`（result/eligible/admitted/ruleVersion/target）、以及
   服务端保存的 `progress.sourceStack`/威胁状态；重启后原骰点身份与准入结果
   原样存活，客户端不再返回 `recovery_roll_outcomes_missing`。
2. **真实 A3 复制/围栏**：`world_31` 有 1 条 `world_copy_results`、1 次
   `checkpoint_restore_group_work`、随后 1 次 `commit_point`；旧持有者的
   `narration_submit`/`narration_claim_renew` 收 `claim_fenced`，旧租约的
   `checkpoint_seal_point` 收 `stale_epoch`，新持有者取得新 claim 与新 epoch。
3. **完整 H2 联调**：刷新（post-restart）、接管（main 的跨 epoch 段）、后继
   （successor）、重启持久化与三种损坏场景在同一固定提交上通过，原始
   行动字节/候选哈希与 accepted 记录逐行相等。

仍未覆盖，不得据上表扩大：120 秒 TTL 自然过期的接管时序、真实浏览器页面、
B3 全量评估与真实模型输出。

