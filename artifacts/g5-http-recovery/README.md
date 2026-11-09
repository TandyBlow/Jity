# G5 真实 HTTP/SQLite 故障恢复验收（总指挥任务，2026-10-30）

结论：**PASS_G5_HTTP_RECOVERY**——五场景全过。基线：产品
`world-browser@54f630c`、服务检出 `agent@dd345b8`（`--expect-server-head`
钉前缀；两侧工作区在起跑与运行期间均干净，逐文件 sha256 钉在报告
`baselines`：浏览器 9 个运行层文件 + 服务端 `backend/app` 全部 156 个）。
独立 uvicorn 服务进程、独立 SQLite 文件（`world.db` 随报告留存）、独立
端口与输出目录；全程零模型调用，未触碰 v5/v6 冻结证据。

## 故障注入机制（不是预设桩）

回执丢弃注入在**客户端传输包装层**：包装器先完成**真实 HTTP 往返**
（服务端事务已在真实 SQLite 上提交），当场用只读连接读
`world_id_allocations` 表拿到本批行作为「已提交」证明，然后抛
`WorldTimeoutError` 丢弃成功回执——注入点严格位于**服务端提交之后、
客户端消费回执之前**。注入时刻的请求、响应身份表与 DB 行随报告落盘
（`scenarios.*.wire` 中带 `fault: receipt_dropped_after_server_commit`
的条目 + `S1/S2/S5.fault` 明细）。

## 场景 → 验收要求映射

| 场景 | 验收要求 | 结果 |
| --- | --- | --- |
| S1_committed_receipt_lost (2.3s) | ①已提交且回执丢失：服务端实际提交（注入时刻 DB 2 行=point_11/group_12），产品会话以可辨认原因阻断终态；**相同 requestId+相同正文**经裸 transport 重放，返回同批身份、DB 零新增 | PASS |
| S2_takeover_same_batch (2.6s) | ②换租约接管：阻断会话租约经 `lease_release` 释放，新会话（新租约 acquire、新会话命名空间 requestId）恢复，**allocationKey/slots 不变**业务幂等取回同批 point/group，自动轮在真实产品栈上跑完（`world_complete`，2 个非根点） | PASS |
| S3_two_idempotency_layers (0.5s) | ③两层分别核对：同 requestId+不同正文=`request_id_reused`；新 requestId+同 key/slots=业务重放原批（两层互不混淆） | PASS |
| S4_old_lease_rejection (0.7s) | ④旧租约+**新 requestId**=租约层拒绝（DB 零新增）；**单独记录**：同 requestId 逐字重放在旧租约下成功（请求级重放先于租约校验，服务端幂等序） | PASS |
| S5_post_fault_state (2.8s) | ⑤故障后状态：会话终态 `stopped`、重复 submit 均以 `rule_session_identity_blocked` 拒绝且不写输入、恢复后使用同批身份、失败前后库记录与消费计数（advances 零新增） | PASS |

窗口构造：每场景一个全新 world（同一服务/库，world_id 隔离计数），
真实产品控制器驱动第 1 轮（脚本化模型端口：全员 skip + 时间扫描 +
真实 preview/commit + 模板叙事），conclude(continue) 进入预分配的
automatic 轮后停止——即「轮已开、无点、身份未分配」的 G5 窗口
（窗口态在报告中逐场景断言：`round.trigger=automatic`、
`activePointId=null`、`phase=select_actor`）。

## 过程中发现并修复的产品缺陷（54f630c，随本验收送审）

**S2 首轮复现**：接管会话在自动轮首个 preview 后终止于 error——规则
端口 `requireScope()` 在 consumed 判定之前执行，而服务端仅在
`intentStatus == 'pending'` 时携带 `activeInput`（`control.py:1164-1168`），
consumed 窗口绑定不可得 → `rule_input_identity_missing`。产品的
continue→自动轮组合从未端到端跑通，该缺口因此一直被掩盖。修复
（`54f630c`）：§6.1 身份绑定保护的是对输入文本的**裁决**；skip 不使用
任何事实，非主角与 consumed 判定前移、无需绑定，pending 主角机会仍
复核服务端意图与逐字绑定。单测
（`rule-session-continue.test.ts`「consumed actions without an input
binding」）钉住：自动轮行动机会产生 `record_skip` 而非错误终止。修复后
S2/S5 全轮跑通即为端到端回归。

## 证据与复跑

- `g5-http-recovery.json` —— 全部 wire 流量（大响应按 op 修剪，allocate/
  lease/conclude 全量保留）、三次故障注入明细、逐场景断言、双基线哈希。
  request_id 与 lease token 均为本地临时标识符，非凭据，无需脱敏。
- `world.db` + `server.log` —— 运行库与服务日志原样留存（请求级幂等表
  与 `world_id_allocations` 可直接 SQL 复核）。
- 复跑（须先提交/暂存使工作树干净）：

  ```powershell
  cd frontend
  node scripts/review-g5-http-recovery.mjs --server-checkout .local/agent-worktree `
    --expect-server-head dd345b8 --out artifacts/g5-http-recovery/g5-http-recovery.json
  ```

  注意 `--out` 按仓库根解析（写 `../artifacts` 会落到仓库外，v5 已有先例）。

## 边界

未调用真实模型；v5/v6 冻结证据未修改；G4（continue 前 nextRoundId 的
程序分配）、产品真实模型 handback 闭环、二十次输入验收继续等待总指挥
另行调度。本轮以 `54f630c` 为产品侧验收基线（含该缺陷修复）。
