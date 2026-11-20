# 固定集成组合 H2／A3-2 验收记录

日期：2026-10-28。验收提交 **`d1d2de0`**（tree `6f16783c834b758d4f8a907f7a972e1836e0ed16`），
由 A=`1ef34e7`（`3734a52` + 联合验收记录）与 B=`21a95f0`（`552148c` + 两处 H2
harness 修复）合并而成，共同基点 `79f8120`。

**本目录是 A3-2「HTTP 刷新与接管联调」关闭标准的实跑证据**：真实 HTTP、隔离
SQLite 持久化服务、真实 `ControllerDriver.recover`，模型由固定回答驱动，骰点
用服务端真实 `reaction-d20-v1`。10 个 phase 调用、8 次启动与 8 次停止全部按预期，
运行窗口 07:13:03–07:14:00 UTC。

契约未改：摘要 `902918016f2bf7eff4cd1afd52da4ca96defdb5ee4082f171fda987de86680c2`，
149 个生成物，与 manifest 及前端 pin 一致。运行前后源码身份一致
（`source_unchanged_during_run.matchesBaseline=true`），工作树干净。

归档提交在本目录入库后另行记录；本目录的哈希由
[manifest.json](manifest.json) 按最终字节绑定，不随归档提交变化。

## 一、组合与身份

| 项 | 值 |
|---|---|
| 验收提交 | `d1d2de0cf2805d0f3ce1d182cde57821800d3bef` |
| 验收树 | `6f16783c834b758d4f8a907f7a972e1836e0ed16` |
| A 侧 | `1ef34e7`（`3734a52` + 联合验收/签字文档） |
| B 侧 | `21a95f0`（`552148c` + `f45cbdd`、`21a95f0` 两处 harness 修复） |
| 契约摘要 | `902918016f2bf7eff4cd1afd52da4ca96defdb5ee4082f171fda987de86680c2` |
| 环境 | Windows 11 / Python 3.12.3 / Node v22.20.0 / 全新 `npm ci`（385 packages） |
| 服务 | `app.world_app:create_persistent_world_app`，`--workers 1`，端口 18793 |
| 数据库 | 四个新建的隔离 SQLite：`positive.db`、`missing.db`、`corrupt.db`、`group.db` |

源码身份（完整哈希见 `manifest.json.sourceSha256`，此处为前 12 位）：

```text
browser recovery.ts            84e6d8df2534
browser controller.ts          ec97a1a0c050
browser schedule.ts            fc897c64f7c3
browser review-h2-full.mjs     428005caa9f5
server  world/control.py       cd3b6e5a297f
server  world/authority.py     5ef2417c02f7
server  world_frozen_repository.py  74471c58be73
```

## 二、验收矩阵

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| main：多源组的保存 DFS 检查点恢复、保存骰点参与 results、提交、叙事、continuation 恰好一次 | PASS_MAIN | [report-main.json](report-main.json) |
| main：旧 claim 提交/续期被拒（`claim_fenced`），新持有者取得新 claim，**旧 epoch 迟到写入被拒（`stale_epoch`）**，跨 epoch 复制并提交封点 | PASS_MAIN | 同上 `takeoverOps` |
| successor：当前点已封 + 后继已预约；两点各提交一次、原始 Δ 顺序完整、无重复掷骰/结算 | PASS_SUCCESSOR | [report-successor.json](report-successor.json) |
| post-restart：同一数据库重启后原租约续期，保存的 DFS 栈与骰点身份/准入结果不变 | PASS_POST_RESTART | [report-post-restart.json](report-post-restart.json) |
| 当前引用的冻结载荷缺行 | PASS_FROZEN_MISSING | [report-frozen-missing.json](report-frozen-missing.json) |
| 冻结行动字节与已接受摘要不符 | PASS_FROZEN_CORRUPT | [report-frozen-corrupt.json](report-frozen-corrupt.json) |
| 活动组行动文本与已接受清单不符 | PASS_FROZEN_CORRUPT | [report-frozen-group.json](report-frozen-group.json) |

损坏恢复分别停止为 `recovery_refused:get_context:frozen_work_missing` 与
`recovery_refused:get_context:frozen_work_corrupt`，没有降格为生成或重掷。

骰点为真实规则结果，分支由服务端决定并记录，不声称穷举：

- main 第二次造世界取得准入（`branch.attempts=2`，第一个世界 `a→b` 未准入）；
- successor 的保存骰点未准入（`branch.rolladmitted=false`），仍按「已封点 + 已预约
  后继」路径提交两个点，未重掷；
- restart、损坏三例的保存骰点均准入。

## 三、数据库证据（[database-evidence.json](database-evidence.json)）

只读查询四个数据库；不复制行动原文，只保存长度与哈希。

`positive.db` 共 6 个世界：

| 世界 | 角色 | 非根提交 | `commit_point` | `restore_group_work` | 副本 | 骰点 | 终端租约 epoch | 组状态 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `world_1` | main 第 1 次尝试（未准入） | 0 | 0 | 0 | 0 | 1（0 准入） | 1 | open |
| `world_12` | **main 正式走完**（`walkedWorld`） | 1 | 1 | 0 | 0 | 3（2 准入） | 1 | consumed |
| `world_31` | **围栏/接管世界**（`fenceWorld`） | 1 | 1 | 1 | 1 | 0 | **3** | consumed |
| `world_40` | **successor 世界** | 2 | 2 | 0 | 0 | 1（0 准入） | 1 | consumed |
| `world_52` | 冻结场景第 1 次尝试（未准入） | 0 | 0 | 0 | 0 | 1（0 准入） | 1 | open |
| `world_62` | **重启场景世界**（保存的冻结工作） | 0 | 0 | 0 | 0 | 1（1 准入） | 1 | open |

- **请求绑定**：每个世界的 `world_submissions` 行按操作计数；`requestId` 在本世界内
  唯一、无重复；`commit_point` 行数与非根提交数逐世界相等（1/1、1/1、2/2、0/0）；
  幂等结果中不出现 `inputText`/`claimToken`（SQLite 触发器
  `no_input_in_submission` 仍在，读取侧也逐行断言）。
- **世界创建幂等**：`world_creations` 行数 = 不同 `world_id` 数
  （positive 6/6、missing 2/2、corrupt 1/1、group 1/1），同一 `requestId` 不会
  创建第二个世界。
- **原文字节与候选哈希**：所有 `world_frozen_work` 行满足
  `sha256(action_bytes) == world_accepted_work.hashes_json.actionContentHash`；
  `candidates_json` 的 `world-canonical-v1` 摘要等于 `hashes_json.candidatesContentHash`；
  `world_settled_units.content_hash` 与按 `candidates_json` 重算的值一致
  （`actionBytesMatchAccepted`、`candidatesMatchAccepted`、`unitsOK` 全为 true）。
- **损坏库是唯一例外**：`corrupt.db` 的 `world_1` 因注入而
  `actionBytesMatchAccepted=false`，正是「冻结行动字节与已接受摘要不符」的证据；
  它不参与正向判定。
- **副本**：`world_31` 有 1 条 `world_copy_results`、`checkpoint_restore_group_work`
  恰 1 次，随后 `commit_point` 恰 1 次——跨 epoch 复制、重读原文、提交封点的
  顺序与 `takeoverOps` 一致。

报告与数据库交叉核对：

- `main.savedRollIds[0]` = `roll_22`，`world_rolls` 中属于 `world_12`，`admitted=1`；
- `successor.savedRollId` = `roll_50`，属于 `world_40`，`admitted=0`（未重掷）；
- `post-restart.rollId` = `roll_71`，属于 `world_62`，`admitted=1`；
- `main.walkedWorld`=`world_12`、`fenceWorld`=`world_31` 与上表对应
  （本组合修复了旧脚本把围栏世界写成 `walkedWorld` 的记账偏差）。

## 四、围栏与迟到写入

`report-main.json` 的 `takeoverOps` 是一次完整的跨 epoch 接管：

```text
lease_acquire → get_context → checkpoint_restore_group_work → get_context →
list_points → get_state → get_context → preview_point → commit_point →
narration_claim → get_state ×2 → narration_submit → round_conclusion_conclude
```

- 交接前：`claim_fenced`（旧 claim 的 `narration_submit`）、`claim_fenced`
  （旧 claim 的 `narration_claim_renew`）、`stale_epoch`（旧租约的
  `checkpoint_seal_point` 迟到写入）。
- 交接：`lease_release` 后 `lease_acquire`，`fenceEpoch` 由 1 升到 2；
  接管驱动再次 acquire，终端 epoch = 3（数据库 `world_31.lease.epoch=3`）。
- 接管驱动只做一次 `restore_group_work`、一次 `commit_point`，不产生任何
  `create_rolls`——不重掷骰点。

## 五、重启持久化

[lifecycle.json](lifecycle.json) 记录同一 `positive.db` 的两次启动：

- 停止后、重启前的数据库 SHA-256：
  `6a94b6f7f31a0c0f210e90931f04ccc5a2f0f4562033f6d3a5bb907fc2a12b06`；
- 重启用同一文件、同一世界，不重建数据库、不重新造世界（generation 1 → 2）；
- `post-restart` 读取到保存的 DFS 栈 `["person_a"]`、保存骰点 `roll_71`
  及其 `admitted=true`，说明恢复载荷不是按成员顺序重推的。

## 六、损坏注入

每个场景独立数据库、独立世界，流程为 build → 停服 → SQL 注入并提交 →
重启同一数据库 → `expect-frozen` → 停服；每次注入恰好影响 1 行。

| 场景 | 目标行 | 停服后操作 | 实际停止 |
| --- | --- | --- | --- |
| missing | `missing.db` / `world_11` / `point_17` / `group_18` | 移除 `active_frozen_payload_retained`，按 `world_work_refs` 复合键删除 `world_frozen_work` 行 | `frozen_work_missing` |
| corrupt | `corrupt.db` / `world_1` / `point_7` / `group_8` | 移除 `frozen_work_immutable`，改写 `action_bytes`，保留原 accepted 哈希 | `frozen_work_corrupt` |
| group | `group.db` / `world_1` / `point_7` / `group_8` | 只改 `world_group_payloads.group_json.actionTexts.person_a` | `frozen_work_corrupt` |

移除触发器只用于离线注入；服务重启初始化会重新创建保护触发器。损坏库与
原始数据库都不入仓。

## 七、启停与运行窗口

- 8 次启动 / 8 次停止严格配对（PID 相同），停止为 `terminate()` 受控停服，
  Windows 退出码均为 1，不是服务自发异常；`lifecycle.json` 记录每次 PID、
  数据库名、phase 状态与注入行数。
- 端口 18793 在每次启动前由脚本先绑定探测，运行结束后无监听残留。
- 输出目录必须是新建目录；脚本拒绝复用既有输出，异常退出也在 `finally`
  中停服。

## 八、本轮修复的两个 harness 缺陷

两处都不在产品代码、契约或共享夹具里，均在 B 的 `review-world-h2-full.mjs`；
失败证据保留在 `.local`，未入仓：

1. **重启场景夹具不按骰点分支（红 → 绿）。** 首次在 `c4fbb97` 上运行时，
   `build-frozen-case` 只造一次世界：`world_41 / point_47 / group_48 / roll_50`
   未准入，服务端 `progress.sourceStack=[]`（被拒骰点视为已处理），恢复正确
   返回空栈，而 `post-restart` 仍断言「保存的 DFS 栈必须存活」，报
   `the saved DFS frame must survive the restart`。修复 `f45cbdd`：夹具最多重试
   六个世界直到骰点准入，并记录实际分支；该提交内另补上循环首轮漏掉的
   `createWorld()`（红证据：`Cannot read properties of null (reading
   'leaseToken')`）。
2. **报告记账偏差（红 → 绿）。** 全量绿跑（`beeb510`、`2f93e8b`）通过全部 phase，
   但 `main.detail.walkedWorld` 在围栏世界创建后才取值，写成了围栏世界；
   `attempts` 把循环自增算进去，多报 1。修复 `21a95f0`：围栏前捕获
   `walkedWorld`，两处 `attempts` 去掉未执行的自增。

两处修复只改验收仪表，不改产品行为；本目录的 `run-integration-h2.py` 与
`review-world-h2-full.mjs`（B=`21a95f0`）就是产出本记录的字节。

## 九、对照 A3-2 关闭标准

关闭标准（`design/world-engine-reports/server.md`「A3 阶段划分」）：
**指定 A/B 提交组合完成 H2，保留请求绑定、原文字节/候选哈希和迟到围栏证据。**

| 关闭条件 | 本记录落点 | 状态 |
| --- | --- | --- |
| 指定 A/B 提交组合 | 固定 `d1d2de0`（A=`1ef34e7` + B=`21a95f0`），运行前后源码哈希一致 | 满足 |
| 完成 H2（刷新/接管/后继/重启/损坏） | 10 个 phase 全绿；刷新=post-restart，接管=main 的跨 epoch 段，后继=successor，损坏三例 | 满足，见第二节 |
| 请求绑定证据 | 每世界操作计数 + `requestId` 唯一 + `commit_point` 与非根提交相等 + 幂等表无 `inputText`/`claimToken` | 满足，见第三节 |
| 原文字节/候选哈希证据 | `sha256(action_bytes)` 与 accepted 哈希逐行相等；候选规范摘要与 accepted 相等；settled 单元哈希重算一致 | 满足，见第三节 |
| 迟到围栏证据 | `claim_fenced` ×2、`stale_epoch` ×1、新 claim 与新 epoch、旧持有者写入拒绝 | 满足，见第四节 |

边界（不由本记录宣告）：

- 接管采用 release/acquire 的 epoch 交接，**未实等 120 秒 TTL 到期**；
- 未运行真实浏览器页面、B3 全量评估与真实模型输出；
- A3-2 的关闭结论仍待用户复核；A3-1 的既有验收范围不变。

## 十、复跑

在拥有固定提交的仓库根目录执行；目标路径若已存在须另选：

```powershell
git worktree add --detach .local/h2-replay d1d2de0cf2805d0f3ce1d182cde57821800d3bef
Copy-Item -LiteralPath artifacts/h2-integration-d1d2de0/run-integration-h2.py -Destination .local/h2-replay/.local/run_integration_h2.py
Push-Location .local/h2-replay/frontend
npm.cmd ci
Pop-Location
Push-Location .local/h2-replay
python -X utf8 .local/run_integration_h2.py
Pop-Location
```

端口 18793 必须空闲；输出位于 `.local/h2-integration-run/`，脚本拒绝复用既有
目录。单 phase 调试格式（B/frontend，服务需已在跑）：

```powershell
node scripts/review-world-h2-full.mjs http://127.0.0.1:18793 main $reportPath <checkout>
node scripts/review-world-h2-full.mjs http://127.0.0.1:18793 post-restart $reportPath <checkout> --state $statePath
node scripts/review-world-h2-full.mjs http://127.0.0.1:18793 expect-frozen $reportPath <checkout> --state $statePath --kind corrupt
```

## 十一、脱敏

报告递归把 `leaseToken`/`claimToken` 值替换为 `[REDACTED]`；原始数据库、
state 文件、phase 日志与服务日志不复制、不入仓（它们含租约授权或可复原的
行动原文）。归档文本统一 LF，`.gitattributes` 固定其检出换行；
[manifest.json](manifest.json) 的哈希按最终入库字节计算，并绑定提交组合、
源码身份、启停与注入记录。
