# 真实模型小世界整链验收：两场景首轮报告

日期：2026-10-28。分支 `world-browser`（本批提交见 git），服务检出
`.local/world-server-worktree` @ `7f00a42`（world-server 分支）。脚本：
`frontend/scripts/run-world-chain-full.mjs`（可复跑，`--phase action|chain|both`）；
原始记录：本目录 `first-round.json`（逐任务、逐尝试、逐网络操作的完整轨迹，
source sha256 钉住两侧代码）。

环境：真实 Python 持久服务（SQLite，每次运行独立库文件）+ 真实 Edge
headless（跨源隔离，wllama 多线程 10 线程）+ Qwen3-0.6B Q4_K_M
（`frontend/public/models/`，temperature 0/0.7 分尝试，maxTokens 96）。
模型加载 12.2 s（每页上下文一次）。**页面叙事沿用现有放行门
（checkFactNarration）与已补齐模板；新判分门未接入——符合本批边界。**

## 一、场景 A：普通行动点（页面同款会话，7 条玩家输入）

`RuleWorldSession`（规则权威结算：action/targets/results/updates/continuation
全部零模型调用）+ 真实模型叙事（模型为主 → 判分门控 → 失败重生成一次 →
模板兜底）。命令序列：走到门厅 / 完成压力试验（被拒：地点不符）/ 走到走廊 /
完成压力试验（10→8，任务+人格+理智联动）/ 完成恢复练习（8→9）/ 上下打量四周
（未识别）/ 走到门厅。

**每条输入都能正确完成；玩家等待 8.7–17.0 秒（含世界时间推进与叙事）。**

| 输入 | 判定 | 等待 | 模型尝试 | 采纳 |
| --- | --- | ---: | --- | --- |
| 走到门厅 | allowed | 10.8s | 1 次 9.6s | 首稿采纳 |
| 完成压力试验（门厅） | refused: milestone_location_mismatch | 9.9s | 1 次 8.9s | 首稿采纳 |
| 走到走廊 | allowed | 10.9s | 1 次 9.6s | 首稿采纳 |
| 完成压力试验（走廊） | allowed（10→8+人格+任务） | 16.3s | 1 次 14.2s | 首稿采纳 |
| 完成恢复练习 | allowed（8→9+人格+任务） | 17.0s | 1 次 14.7s | 首稿采纳 |
| 上下打量四周 | unparsed（仅时间推进） | 10.4s | 1 次 8.7s | 首稿采纳 |
| 走到门厅 | allowed | 11.3s | 1 次 8.9s | 首稿采纳 |

- 世界创建（含根叙事模型尝试 10.4s）：10.9 s。
- **8/8 叙事全部首稿通过判分门**（含被拒/未识别轮），0 重生成、0 模板回退。
- 任务轮（4-5 事实）比移动/拒绝轮（2-3 事实）慢约 5s——模型成本随事实数增长。
- 终态正确：version 7、门厅、理智 9、两任务达成、两条人格变化；8 点位全部
  叙事就绪；每输入服务端操作 15–18 次（合计 124 次，明细在原始记录）。
- 结算组件确认为零模型调用：每输入的模型调用恰为 1 次（叙事）。

## 二、场景 B：连锁共同结算（完整驱动器 + 真实服务端 d20）

完整 `ControllerDriver` + 真实 HTTP + 服务端真实 d20 骰点。结算文本
（行动/反应/结果/更新候选）为脚本候选——**结算组件的模型化属 B3 独立批次，
不在本批**；叙事走与页面同一份 `narration-polisher` + `narrateFromReads` 门。

链形状（world_short 双角色）：林川（person_a，发起人）推门示意 → 目标周宁 →
真实 d20（**首骰 2 未准入 → 换世界重试，第 2 次世界 14 点准入**）→ 周宁反应
被接受 → 周宁反指林川（驱动器运行时分配触发身份）→ 真实 d20 → 2 点未准入 →
确认空目标 → 组关闭 → 结果/六步更新（任务+人格+理智）/逐人判断/封点/提交/
叙事（真实模型）/继续判断（handback）。

| 阶段 | 耗时 | 说明 |
| --- | ---: | --- |
| 引导（建世界+根叙事脚本引导） | 415ms | 含 2 个世界的 d20 准入重试 |
| 驱动器走链（结算+提交+真实叙事） | 16.0s | 其中模型叙事 1 次首稿采纳 |
| 合计（玩家视角的一次输入） | **≈16.4s** | 不含模型加载 12.2s（一次性） |

- 驱动器模型任务序列：targets / results / updates / narration / continuation
  （无 action——两角色均被覆盖；无 pointPlan——恢复进既有 advance）。
- 提交恰 1 次；两环骰点（1 准入 1 拒绝）如实记录；无重复骰点。
- 提交叙事为**模型文本**（6 条事实全对，首稿通过），非模板。

## 三、本轮问题清单（按发现顺序）

1. **[harness 缺陷，已修]** SQLite 库文件跨运行复用 → 新进程重造 `world_1`
   撞上旧幂等台账（`request_id_reused`）→ 会话误入 lost_lease。修复=每次
   运行独立私有目录。非产品缺陷；review-world-page 因目录带时间戳从未触发。
2. **[服务端行为澄清，非缺陷]** 持久层在 `checkpoint_start_advance` 后把轮次
   顺序按 **（理智值，ID）升序** 重排（`world_store.finish_operation`）——
   discover 的绑定校验要求 `initiatorId == order[cursor]`，因此发起人必须是
   该序首位。场景改为林川（person_a）发起。注意：该重排在 SQLite 持久层；
   行为是否与内存层一致属 A 侧确认项（见问题 5）。
3. **[产品限制，影响面需决策]** committed 叙事投影**不支持外貌变化**
   （`projectCommittedNarration` 对 appearanceChanges 抛
   `unsupported_committed_delta`）——含外貌增量的点无法经 `narrateFromReads`
   出叙事（模板兜底同样抛错）。本轮脚本化更新改用任务+人格+理智组合。
   外貌变化点（T02 类）如何叙事：是投影扩展还是叙事层绕行，需要独立决策。
4. **[诊断缺口，建议 A 侧]** 服务错误信封不携带 `ServiceRefusal` 的 message
   （`error_response` 只回 code/details，本轮 details 为空）——定位
   `request_malformed` 只能起进程内探针逐层复现，调试成本高。建议把
   `_refuse` 的 detail 文本放进 `error.details`（或专用字段）。
5. **[待确认]** 行为分层：H2-full 探索轮（通过）与本轮的持久层差异
   （轮次重排、身份绑定校验只在 SQLite 层）——同一操作序列在内存/持久两种
   store 下是否同判定，需要 A 侧给一句结论；影响 scripted 场景的可移植性。
6. **[记录缺口]** 页面润色路径未采集 token 级 timings（prompt/completion
   tokens 已由 `onCompletion` 证据收集但未逐尝试展开）。下一批把证据展开进
   `modelAttempts`，与 B3 适配器的计时元数据对齐。

## 四、通向 20 次输入验收（§798 阶段 5）的剩余工作

首轮回答了「一次输入能否正确完成、等多久」（能；8.7–17.0s）。剩余：

1. 输入量扩到 ≥20 次（含多条**自动推进链**——linked 续段，本批未覆盖）；
2. 暂停/继续（页面刷新续接已在 review-world-page 覆盖，harness 化进本脚本）；
3. 历史回放（从 S₀ 重建相同状态）与**删除叙事缓存后的重新生成**；
4. 以共同结算收尾的 round 保留空 linked 续段并生成叙事（额外一次叙事调用
   计入串行等待，不计零成本）；
5. token 级成本展开（问题 6）与每次输入的服务端操作明细表。

## 五、复跑

```powershell
# 仓库根目录；服务检出默认 .local/world-server-worktree（world-server @ 7f00a42）
cd frontend
node scripts/run-world-chain-full.mjs --out artifacts/world-chain/first-round.json
#   [--phase action|chain|both] [--server-checkout 路径] [--python python]
```
