# G2 内核操作定案（32 个 v2 操作）

状态：G2（2026-11-20）。运行期权威：`frontend/src/lib/world-engine/local/transport.ts`；Python 只作差分预言机。

## 定案表

| 组 | 操作 | 状态 | 产品语义 |
|---|---|---|---|
| 世界 | `create_world` | 实现 | 从静态 S0 建世界；重复建同一世界按幂等拒绝 |
| 上下文 | `get_context` | 实现 | 返回 world/control/work/activeInput；`recovery` 恒 `null`（见下） |
| 上下文 | `get_state` | 实现 | 读取已提交点的状态与摘要 |
| 上下文 | `list_points` | 实现 | 只读历史点（分页参数保留） |
| 租约 | `lease_acquire` / `lease_renew` / `lease_release` | 实现 | 写者租约 + fence epoch；过期可接管 |
| 分配 | `allocate_ids` | 实现 | 按 allocationKey 幂等分配 advance/input/round/group/point 槽 |
| 推进 | `checkpoint_start_advance` | 实现 | 要求 head 叙述 ready；冻结全 roster |
| 推进 | `checkpoint_begin_point` | 实现 | normal/instant/linked；时间先锁 |
| 推进 | `checkpoint_set_point_time` | 实现 | linked/instant 后继时间 |
| 组 | `checkpoint_discover_group` / `checkpoint_extend_group` / `checkpoint_close_group` | 实现 | 冻结组、目标集、准入成员 |
| 组 | `checkpoint_stage_unit` / `checkpoint_record_skip` / `checkpoint_stage_time_scan` | 实现 | 候选单元、跳过、时间扫描 |
| 组 | `checkpoint_seal_point` / `checkpoint_prepare_successor` | 实现 | 封点与后继准备 |
| 恢复 | `checkpoint_restore_group_work` | **非产品语义** | 恒拒 `frozen_work_missing`；产品恢复走本地 checkpoint，不使用组工作恢复（D-015） |
| 恢复 | `checkpoint_pause` / `checkpoint_resume` | 实现 | 保存冻结工作；恢复后继续 |
| 预览/骰 | `preview_point` / `create_rolls` / `commit_point` | 实现 | preview 投影；骰点程序持有；整笔提交先 checkpoint |
| 回合 | `round_conclusion_conclude` / `round_conclusion_cancel` | 实现 | 结论/取消；cancel 关闭 advance 并清 work |
| 叙述 | `narration_claim` / `narration_claim_renew` / `narration_submit` / `narration_get` / `narration_delete` | 实现 | claim/generation 门；正文不可变；delete 使代次前进 |

合计 32：31 实现，1 声明非产品语义。

## 骰点协议（冻结）

- 规则 `reaction-d20-v1`：结果由注入的 `roll()` 产生（浏览器程序持有，非模型）；其它规则版本结果为 1。
- 阈值来自请求的 `target`；同一 `sourceId|targetId|triggerKey` 已有骰点时必须复用，规则或阈值变化拒绝 `request_malformed`。
- 骰点存 `record.rolls`，`rollSeq` 单调；恢复不重掷，恢复后同一键返回原结果。
- 测试锚点：`local-transport.test.ts`、`turn-execution` 套件。

## 恢复语义

- `checkpoint_restore_group_work` 拒绝：产品没有「从组工作恢复」的入口；恢复只走 IndexedDB checkpoint / `__worldRestore`。
- `get_context.recovery` 恒 `null`：本地恢复不依赖服务端 recovery；不是缺失字段。
- `LocalGameSession.restore` 在取得写者租约后、应用状态前调用 `verifySessionSnapshot`；不变量失败抛 `local_restore_invariant:<codes>`，不写回。

## 差分向量

- 冻结夹具：`frontend/scripts/parallel-kernel/fixtures/kernel-differential.json`（Python `fc60a603` 生成，含 canonical/positions/tasks/supersedes/time 与 normal 提交向量；LF sha256 `7d68a392…f977`，工作树 CRLF sha256 `f43cbb6c…78c7`）。
- TS 断言：`canonical.test.ts`、`state.test.ts`、`local-transport.test.ts`、`world-loader.test.ts`、`state-invariants/verify.test.ts`。
- 证据：`artifacts/goal/kernel-diff.json`。
