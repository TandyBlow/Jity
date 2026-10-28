# 真实模型小世界两场景验收：混合首轮报告（勘误后）

日期：2026-10-28/29。分支 `world-browser`。本目录的原始记录与角色：

- `first-round.json` —— 首轮（harness `122ccef`）。动作场景段经复核为真；
  chain 段是真实单 run 记录但其主证据库已被 B 侧误删，**不作证据引用**
  （存证与溯源见 `evidence-note-first-round-db.md`）。
- `first-round-v2.json` —— 记录修复后的复跑（harness `4ca93d8`）。chain 段
  的 completion 证据为空（polisher 缓存 bug，见〇·二轮第 1 条）——动作
  场景段的证据完整。
- `first-round-v3.json` —— **chain 段的 canonical 记录**（harness
  `ae67b86`）：token 级证据、逐世界骰点、全量轨迹齐备且可复验。

脚本：`frontend/scripts/run-world-chain-full.mjs`（可复跑，`--phase
action|chain|both`）。

**范围声明：这是「混合首轮」基线，不是全模型语义的整链验收。** 场景 A
结算=规则权威组件（action/targets/results/updates/continuation 零模型
调用）；场景 B 结算=脚本候选；两场景只有叙事走真实模型（同一
narration-polisher + checkFactNarration 门）。结算组件的模型化属 B3 独立
批次；文中「PASS_BOTH」指两场景在该混合边界下通过，不覆盖
action/reaction/results/updates 的模型语义责任。

环境：真实 Python 持久服务（SQLite，每轮独立库文件）+ 真实 Edge
headless（跨源隔离，wllama 10 线程）+ Qwen3-0.6B Q4_K_M
（`frontend/public/models/`，temperature 0/0.7 分尝试，maxTokens 96）。
模型加载：首轮 12.2s / v2 13.7s / v3 14.0s（每页上下文一次）。**页面叙事
沿用现有放行门（checkFactNarration）与已补齐模板；新判分门未接入——
符合本批边界。** 服务端应用代码在首轮 pin（4a25f5f）与 v3 pin（d4e0dd37）
之间 `git diff -- backend/app` 为空（v2 起 156 文件逐文件 sha256 钉档）——
各轮数字可比。

## 〇、勘误与复核记录

### 首轮勘误（2026-10-28 验收复核落地，harness 4ca93d8+77cb0af）

复核确认首轮主数据为真（603/603 测试、双 tsc 净、7 输入全对、8/8 叙事
首稿过门、narration-polisher 逐字一致且哈希匹配 `122ccef`），但五处陈述
超出 artifact 实际记录：

1. **服务端钉档不实**：首轮 serverSource 只有 head+status（head 实为
   4a25f5f，本 README 曾写 7f00a42；backend/scripts 有一个脏脚本文件），
   没有 sha256。v2 起 serverSource 逐文件钉住 `backend/app` 全部 156 个
   代码文件；钉住集 tracked 脏时脚本拒绝起跑，`--allow-dirty-server` /
   `--allow-dirty-browser` 按侧豁免（artifact 仍如实记录 status）。落地中
   修掉 `git()` 整串 trim 吃掉 status 首行前导空格的解析 bug——它会让
   守卫对首行失明；守卫先用脏树负例验证拒绝路径再放行净树。
2. **玩家等待区间写错**：8.7s 是未识别命令那次输入的**模型耗时**（该输入
   wallMs=10.4s）。逐输入实际等待 **9.9–17.0s**。v2 起 totals 自动计算
   `inputWallRange`。
3. **「首骰 2 未准入 → 换世界重试」叙事撤回**：这是对 harness 循环退出
   值的误读（`attempts` 字段=实际尝试数+1）。首轮实为**单世界一次准入**；
   「2」来自第二环拒绝骰。该结论的取证过程与主证据销毁事故见
   `evidence-note-first-round-db.md`；chain 叙事已按复核指令改用 v3 数据，
   首轮 14/2 数字不再进入验收叙事。
4. **token 证据只存了数量**：首轮应读作「未落盘」而非「已收集未展开」。
5. **原始轨迹不完整**：setupOps 只在失败时返回、缺逐尝试事实包、
   modelTasks 缺返回值、finalState 缺任务/人格/理智、成功路径缺原始
   wire。v2 起全部落盘。

### 二轮复核落地（2026-10-29，harness ae67b86+本轮 artifact）

1. **[阻断项，已修] chain 的 token 证据为空**：v2 里
   `chain.totals.completionEvidence = 0`、`completion = []`。根因=
   `narrationPolisher` 的缓存键含 `|evidence` 后缀，实例级 `onCompletion`
   在首个调用方创建实例时被闭包固定——chain 复用 action 的实例，chain
   的回调被忽略。修复=证据回调改为 `RuleNarrationPolisher` 的逐调用第 5
   参（options 级回调删除；页面 plain 调用与更少参数的测试实现天然兼
   容），action/chain 各自逐调用传入；harness 加断言
   （action/chain `completionEvidence < 1` 即失败）。v3 实证：chain 唯一
   一次 16.1s 模型调用带完整证据（prompt_n 307 / predicted_n 61 /
   prompt_ms 9094 / predicted_ms 6922 / finish stop）。
2. **[证据链] 首轮「拼接记录」质疑的解决**：质疑源于被删目录造成的
   时间线缺口——`recordedAt` 毫秒位（.994）与被删目录 1793202273993
   精确对应（±1ms），该库查询输出（worlds 恰两行、roll_57=14 准入、
   roll_59=2 拒绝）与 artifact chain 段逐一吻合，拼接理论不成立；但主
   证据已销毁、不可再独立复验，故按上表处置：v3 为 chain canonical，
   首轮 chain 段撤下。残存目录的完整时间线见存证 note。
3. **[措辞收敛]** `worldAttempts` 记录的是 setup 期各世界尝试的**首环**
   骰点；全量骰点（含驱动器驱动的第二环）在 `rollsRolled`。v2 起两者
   都落盘，「全部骰点落在 worldAttempts」的说法不准确。
4. **[小项]** `modelLoad` 各轮实值见环境行；`--allow-dirty-*` 旗标已拆分
   为按侧生效。

## 一、场景 A：普通行动点（页面同款会话，7 条玩家输入）

`RuleWorldSession`（规则权威结算：action/targets/results/updates/
continuation 全部零模型调用）+ 真实模型叙事（模型为主 → 判分门控 →
失败重生成一次 → 模板兜底）。命令序列：走到门厅 / 完成压力试验（被拒：
地点不符）/ 走到走廊 / 完成压力试验（10→8，任务+人格+理智联动）/
完成恢复练习（8→9）/ 上下打量四周（未识别）/ 走到门厅。

**每条输入都能正确完成；逐输入玩家等待（首轮）9.9–17.0 秒、（v2）
10.7–22.6 秒、（v3）11.2–24.8 秒——均由 totals.inputWallRange 自动计算，
含世界时间推进与叙事。**

| 输入 | 判定 | 等待（首轮） | 模型尝试 | 采纳 |
| --- | --- | ---: | --- | --- |
| 走到门厅 | allowed | 10.8s | 1 次 9.6s | 首稿采纳 |
| 完成压力试验（门厅） | refused: milestone_location_mismatch | 9.9s | 1 次 8.9s | 首稿采纳 |
| 走到走廊 | allowed | 10.9s | 1 次 9.6s | 首稿采纳 |
| 完成压力试验（走廊） | allowed（10→8+人格+任务） | 16.3s | 1 次 14.2s | 首稿采纳 |
| 完成恢复练习 | allowed（8→9+人格+任务） | 17.0s | 1 次 14.7s | 首稿采纳 |
| 上下打量四周 | unparsed（仅时间推进） | 10.4s | 1 次 8.7s | 首稿采纳 |
| 走到门厅 | allowed | 11.3s | 1 次 8.9s | 首稿采纳 |

- 世界创建（含根叙事模型尝试）：首轮 10.9s / v3 11.1s。
- **8/8 叙事全部首稿通过判分门**（含被拒/未识别轮），0 重生成、0 模板
  回退；v2/v3 复跑同为 8/8（v3 的 8 条 completion 证据齐备）。
- 任务轮（4-5 事实）比移动/拒绝轮（2-3 事实）慢约 5s——模型成本随事实
  数增长；逐尝试 completion 证据（prompt_n 等）可直接量化。
- 终态正确：version 7、门厅、理智 9、两任务达成、两条人格变化；8 点位
  全部叙事就绪；每输入服务端操作 15–18 次（合计 124 次，明细在原始
  记录）。
- 结算组件确认为零模型调用：每输入的模型调用恰为 1 次（叙事）。

## 二、场景 B：连锁共同结算（完整驱动器 + 真实服务端 d20；canonical=v3）

完整 `ControllerDriver` + 真实 HTTP + 服务端真实 d20 骰点。结算文本
（行动/反应/结果/更新候选）为脚本候选——**结算组件的模型化属 B3 独立
批次，不在本批**；叙事走与页面同一份 `narration-polisher` +
`narrateFromReads` 门。**以下数字取自 v3**（首轮 14/2 叙事已撤下，见
〇节与存证 note；v2 那轮的世界准入方差=9/5 被拒后 18 准入、第二环 9
拒绝，同样完整落盘）。

链形状（world_short 双角色）：林川（person_a，发起人）推门示意 → 目标
周宁 → 真实 d20 首环 **17 准入**（target 11；本轮单世界）→ 周宁反应被
接受 → 周宁反指林川（驱动器运行时分配触发身份）→ 真实 d20 **15 拒绝**
→ 确认空目标 → 组关闭 → 结果/六步更新（任务+人格+理智）/逐人判断/
封点/提交/叙事（真实模型 16.1s）/继续判断（handback）。

| 阶段 | 耗时（v3） | 说明 |
| --- | ---: | --- |
| 引导（建世界+根叙事脚本引导） | 517ms | 单世界；多世界准入轮的逐骰点见 worldAttempts |
| 驱动器走链（结算+提交+真实叙事） | 17.4s | 其中模型叙事 1 次 16.1s 首稿采纳 |
| 合计（玩家视角的一次输入） | **≈17.9s** | 不含模型加载 14.0s（一次性） |

- 驱动器模型任务序列：targets / results / updates / narration /
  continuation（无 action——两角色均被覆盖；无 pointPlan——恢复进既有
  advance）；各任务返回值随 modelTasks.returned 落盘。
- 提交恰 1 次；两环骰点：首环 17 准入、第二环 15 拒绝（rollsRolled 全量，
  worldAttempts 记 setup 期首环）。
- 提交叙事为**模型文本**（6 条事实全对，首稿通过），非模板；token 级
  证据（prompt_n 307 / predicted_n 61 / 分段耗时）在
  `modelAttempts[0].completion`。

## 三、问题清单（按发现顺序；状态已更新）

1. **[harness 缺陷，已修]** SQLite 库文件跨运行复用 → 新进程重造
   `world_1` 撞上旧幂等台账（`request_id_reused`）→ 会话误入
   lost_lease。修复=每次运行独立私有目录。非产品缺陷；
   review-world-page 因目录带时间戳从未触发。
2. **[已确认]** 持久层在 `checkpoint_start_advance` 后把轮次顺序按
   **（理智值，ID）升序** 重排（`SQLiteBaselineStore.finish_operation`）；
   `FixtureBaselineStore` 没有 `finish_operation`、保留传入的 order；
   `judgments.py` 的发起人校验（`initiatorId == order[cursor]`）是共享
   的。因此同一未排序 order 在内存层通过、SQLite 层拒绝。本场景 roster
   已是该序首位（不影响结果）；scripted 场景的「可移植」需要 A 侧明确
   顺序契约（谁负责排序/校验）。
3. **[已确认，影响面仍需决策]** committed 叙事投影**不支持外貌变化**：
   `committed-narration.ts` 对 appearance 键和
   `unrecorded_appearance_change` 都会抛错，`narrateFromReads` 出不了
   叙事（模板兜底同样拿不到 facts）。本轮脚本化更新改用任务+人格+理智
   组合。外貌变化点（T02 类）如何叙事：投影扩展还是叙事层绕行，需要
   独立决策。
4. **[已确认，建议 A 侧]** 服务错误信封不携带 `ServiceRefusal` 的
   message：`error_response` 只回 `error.details`，`detail` 文本未进入
   （本轮 details 为空）——定位 `request_malformed` 只能起进程内探针逐
   层复现，调试成本高。建议把 detail 放进 `error.details`（或专用字段）。
5. **[已确认，并入问题 2]** 行为分层差异（轮次重排、身份绑定校验只在
   SQLite 层）已由复核从代码坐实；结论同问题 2，待 A 侧给顺序契约。
6. **[harness 缺陷，已修（二轮）]** polisher 实例级证据回调被缓存吞掉 →
   chain completion 证据空；修复与 v3 实证见〇·二轮第 1 条。
7. **[流程缺陷，已检讨（二轮）]** 取证后删除原始数据目录（首轮运行
   私有库），导致复核期证据链断裂与时间线误拼；存证与教训见
   `evidence-note-first-round-db.md`。

## 四、通向 20 次输入验收（§798 阶段 5）的剩余工作

首轮回答了「一次输入能否正确完成、等多久」（能；逐输入约 9.9–17.0s 起，
各轮区间见第一节）。

**范围口径：20 次输入验收 = 端到端正确性 + 持久化（重启回读）+ 真实
模型叙事。结算语义（action/reaction/results/updates 的模型化）仍属 B3
后置边界，不在该验收的责任范围内。**

1. 输入量扩到 ≥20 次（含多条**自动推进链**——linked 续段，本批未覆盖）；
2. 暂停/继续（页面刷新续接已在 review-world-page 覆盖，harness 化进本
   脚本）；
3. 历史回放（从 S₀ 重建相同状态）与**删除叙事缓存后的重新生成**；
4. 以共同结算收尾的 round 保留空 linked 续段并生成叙事（额外一次叙事
   调用计入串行等待，不计零成本）；
5. token 级成本展开已随 v3 对 action/chain 双场景落盘（含逐尝试
   completion 证据与断言），20 次跑直接产出；逐输入服务端操作明细表同
   由 opLog 直接聚合。

## 五、复跑

```powershell
# 仓库根目录；服务检出默认 .local/world-server-worktree（sha256 钉档，
# 不依赖 head 记忆；钉住集 tracked 脏时脚本拒绝起跑）
cd frontend
node scripts/run-world-chain-full.mjs --out artifacts/world-chain/first-round-v3.json
#   [--phase action|chain|both] [--server-checkout 路径] [--python python]
#   [--allow-dirty-server] [--allow-dirty-browser]  # 按侧豁免脏钉住集（artifact 仍记录 status）
```
