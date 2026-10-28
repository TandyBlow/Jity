# 固定组合 H2 验收记录

日期：2026-10-27。B=`6b809dca846b407ae24f545adeef7ae068fcf5b5`，
A=`0cb1951cd1b0181f6a0505026cdd9939dd668de9`。

**本轮约定的完整 H2 验收矩阵通过。** 正向路径在上述固定组合上重新取得证据，
三种损坏场景也重新运行；旧工作区报告不参与本轮判定。
本目录先归档入库，共同冻结记录随后引用该归档提交。

共同摘要与两侧 pin：

```text
902918016f2bf7eff4cd1afd52da4ca96defdb5ee4082f171fda987de86680c2
```

155 个共享文件逐字节一致。B 工作树干净，A tracked 工作树干净，保留原有
`?? backend/_proj_create.json`。本轮未修改 A/B 业务源码、共享物或 pin。
A 侧 v2 导出 `--check` 退出 0；归档哈希、凭证脱敏、启停配对和端口释放均已核对。

## 实跑结果

运行窗口：06:30:30–06:31:29 UTC。真实 HTTP、持久化 SQLite、真实
`ControllerDriver.recover`，模型由固定回答驱动，骰点采用服务端真实
`reaction-d20-v1`。10 个 phase 调用全部退出 0。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| main：多源与保存骰点/未掷威胁的 DFS 恢复、提交、叙事、continuation | PASS_MAIN | [report-main.json](report-main.json) |
| main：旧 claim 提交/续期拒绝、新 claim 成功、旧 epoch 迟到写入拒绝、跨 epoch 复制并提交封点 | PASS_MAIN | 同上，takeoverOps 含 restore/commit/narration/conclude |
| successor：两点各提交一次、原始 Δ 顺序完整、无重复掷骰/结算 | PASS_SUCCESSOR | [report-successor.json](report-successor.json) |
| post-restart：原租约续租，原 roll 身份、admitted 与 DFS 栈一致 | PASS_POST_RESTART | [report-post-restart.json](report-post-restart.json) |
| 当前引用的冻结载荷缺行 | PASS_FROZEN_MISSING | [report-frozen-missing.json](report-frozen-missing.json) |
| 冻结行动字节与已接受摘要不符 | PASS_FROZEN_CORRUPT | [report-frozen-corrupt.json](report-frozen-corrupt.json) |
| 活动组行动文本与已接受清单不符 | PASS_FROZEN_CORRUPT | [report-frozen-group.json](report-frozen-group.json) |

损坏恢复分别停止为 `recovery_refused:get_context:frozen_work_missing` 与
`recovery_refused:get_context:frozen_work_corrupt`，没有降格为生成或重掷。
main 本次造世界尝试两次，第二次原始 a→b 准入；successor 原骰点未准入；
重启场景原骰点准入。记录实际分支，不声称穷举随机分支。

用户此前独立验证的前端 532/532、双 tsc、A 侧相关测试 75/75 继续有效，
本轮没有重复运行未变动源码的这些检查。

## 服务启停与重启

[run-recorded.py](run-recorded.py) 与本次 `.local/run_h2_fixed.py` 字节相同。
脚本从自己的父目录推导 B 工作区，复跑时须复制到 B 的 `.local/`，
A checkout 须在 B 的 `.local/world-server-worktree`。

启动等价命令（A/backend；`$dbPath` 为新建隔离数据库的绝对路径）：

```powershell
$env:WORLD_SQLITE_PATH = $dbPath
python -X utf8 -m uvicorn app.world_app:create_persistent_world_app --factory --host 127.0.0.1 --port 18783 --workers 1
```

实际脚本用 `subprocess.Popen` 启动隐藏进程，轮询 `/openapi.json` 返回 200 后才跑 phase。
停止仅针对持有的进程句柄，调用 `terminate()` 并 `wait(timeout=15)`。
Windows 上是进程终止，本次停止退出码均为 1，属于受控停服，不是服务自发异常。

[lifecycle.json](lifecycle.json) 保存 8 次启动及对应的 8 次停止、PID、时间、数据库名、
phase 状态和注入行数。重启从 generation 1 切到 2，使用同一 `positive.db`，
不重建数据库、不重新造世界；已记录停止后、重启前的数据库 SHA-256。
post-restart 只验证 recover 读取，该世界未随后完整 run；提交证据来自 main/successor。

## 损坏注入

每个场景独立数据库及世界：build → 停服并等待退出 → SQL 注入并提交 →
重启相同数据库 → expect-frozen → 停服。每次注入恰好影响 1 行。
作用域来自本场景私有 state 的 worldId/pointId/groupId。

| 场景 | 停服后的 SQL 操作 | 预期错误 |
| --- | --- | --- |
| missing | 移除 `active_frozen_payload_retained`；按 `world_work_refs` 完整复合键删除对应 `world_frozen_work` 行 | frozen_work_missing |
| corrupt | 移除 `frozen_work_immutable`；按同一复合键修改 `action_bytes`，保留原 accepted 哈希 | frozen_work_corrupt |
| group | 只改 `world_group_payloads.group_json.actionTexts.person_a`，保留原 accepted 清单 | frozen_work_corrupt |

精确的参数化 SQL 见脚本 `damage()`。移除触发器仅用于离线注入；服务重启初始化
会重新创建保护触发器。损坏库不用于正向检查，不归档入仓。

## 复跑

Windows PowerShell，在拥有固定提交的仓库根目录执行。使用全新 checkout，
目标路径若已存在应另选新目录；所用 Python 环境须有 A/backend/requirements.txt 依赖。

```powershell
git worktree add --detach .local/h2-replay 6b809dca846b407ae24f545adeef7ae068fcf5b5
git -C .local/h2-replay worktree add --detach .local/world-server-worktree 0cb1951cd1b0181f6a0505026cdd9939dd668de9
Copy-Item -LiteralPath artifacts/h2-full-6b809dc-0cb1951/run-recorded.py -Destination .local/h2-replay/.local/run_h2_fixed.py
Push-Location .local/h2-replay/frontend
npm.cmd ci
Pop-Location
Push-Location .local/h2-replay
python -X utf8 .local/run_h2_fixed.py
Pop-Location
```

端口 18783 必须空闲。输出位于新 checkout 的 `.local/h2-fixed-20261027/`，
脚本拒绝复用既有输出目录。异常退出也在 finally 中停止服务。
main 最多用六个世界尝试取得准入分支；若均未准入，脚本失败并留证。

单 phase 调用格式（B/frontend；报告与 state 使用私有 .local 路径；A 为绝对路径）：

```powershell
node scripts/review-world-h2-full.mjs http://127.0.0.1:18783 main $reportPath $aCheckout
node scripts/review-world-h2-full.mjs http://127.0.0.1:18783 successor $reportPath $aCheckout
node scripts/review-world-h2-full.mjs http://127.0.0.1:18783 build-frozen-case $reportPath $aCheckout --state $statePath
# 停服后重启同一数据库
node scripts/review-world-h2-full.mjs http://127.0.0.1:18783 post-restart $reportPath $aCheckout --state $statePath
# 单独造世界、停服注入、重启后；kind 为 missing 或 corrupt
node scripts/review-world-h2-full.mjs http://127.0.0.1:18783 expect-frozen $reportPath $aCheckout --state $statePath --kind corrupt
```

## 脱敏、身份修正与边界

[manifest.json](manifest.json) 保存每份原始/脱敏报告的 SHA-256、执行脚本哈希、
来源组合、摘要及边界。报告递归将凭证字段值替换为 `[REDACTED]`，不收入原始
state、数据库、含租约授权的 stdout 或服务日志；保留源码哈希和实际 git 状态。
归档文本统一为 LF，`.gitattributes` 固定其检出换行；脱敏报告哈希按最终入库字节计算。

原固定脚本的两个报告字段有记账偏差，归档保留原值，另由
[database-evidence.json](database-evidence.json) 校正：

- `main.detail.walkedWorld` 原报 world_31，实际 world_12；roll_22 在 SQLite
  `world_rolls` 唯一映射至 world_12。world_31 是独立的围栏/接管世界。
- `main.detail.branch.attempts` 原报 3，实际 2；成功后 for-loop 再自增一次。

同份只读证据核对 main/围栏各提交一个非根点、successor 提交两个非根点；
三条已提交 appearance change ID 均关联到服务端 `kind=change` 分配记录。
上述修正不改变固定脚本或验收断言，没有静默改写原报告。

接管为 release/acquire 的 epoch 交接，未实等 120 秒 TTL 到期；后继断点为
“当前点已封、后继已预约但未 begin”的真实可达形态。结论限于本轮约定矩阵，
不扩展为真实模型、浏览器真机、B3 全量或所有 TTL 时序均已验收。
