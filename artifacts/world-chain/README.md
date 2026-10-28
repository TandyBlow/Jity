# 真实模型小世界两场景验收：混合首轮报告（勘误后）

日期：2026-10-28。分支 `world-browser`。两份原始记录都在本目录：

- `first-round.json` —— 首轮（harness `122ccef`），主数据经独立复核为真；
- `first-round-v2.json` —— 记录补齐后的复跑（harness `4ca93d8`），第〇节
  五项记录缺陷全部在 artifact 里可见。

脚本：`frontend/scripts/run-world-chain-full.mjs`（可复跑，`--phase
action|chain|both`）。

**范围声明：这是「混合首轮」基线，不是全模型语义的整链验收。** 场景 A
结算=规则权威组件（action/targets/results/updates/continuation 零模型
调用）；场景 B 结算=脚本候选；两场景只有叙事走真实模型（同一
narration-polisher + checkFactNarration 门）。结算组件的模型化属 B3 独立
批次；文中「PASS_BOTH」指两场景在该混合边界下通过，不覆盖
action/reaction/results/updates 的模型语义责任。

环境（两轮一致）：真实 Python 持久服务（SQLite，每轮独立库文件）+ 真实
Edge headless（跨源隔离，wllama 10 线程）+ Qwen3-0.6B Q4_K_M
（`frontend/public/models/`，temperature 0/0.7 分尝试，maxTokens 96）。
模型加载约 12.2 s（每页上下文一次）。**页面叙事沿用现有放行门
（checkFactNarration）与已补齐模板；新判分门未接入——符合本批边界。**
服务端应用代码在首轮 head（4a25f5f）与 v2 head（1200cbde）之间
`git diff -- backend/app` 为空（v2 起 156 文件逐文件 sha256 钉档）——两轮
数字可比。

## 〇、首轮勘误（2026-10-28 验收复核落地）

复核确认首轮主数据为真（603/603 测试、双 tsc 净、7 输入全对、8/8 叙事
首稿过门、narration-polisher 逐字一致且哈希匹配 `122ccef`），但五处陈述
超出 artifact 实际记录，另发现一处叙事误读。全部修正如下；记录管道已在
v2 补齐并以复跑验证：

1. **服务端钉档不实**：首轮 serverSource 只有 head+status（head 实为
   4a25f5f，本 README 曾写 7f00a42；backend/scripts 有一个脏脚本文件），
   没有 sha256——「双侧 sha256 钉档」实际只有浏览器侧。v2 起
   serverSource 逐文件钉住 `backend/app` 全部 156 个代码文件（含 1 份
   schema SQL，排除 `__pycache__`）；钉住集 tracked 脏时脚本拒绝起跑
   （`--allow-dirty-server`/`--allow-dirty-browser` 可豁免，artifact 仍
   如实记录 status）。落地中发现并修掉 `git()` 整串 trim 吃掉 status
   首行前导空格的解析 bug——它会让脏树守卫对首行失明；守卫先用脏树
   负例验证拒绝路径，再在净树上放行。
2. **玩家等待区间写错**：8.7s 是未识别命令那次输入的**模型耗时**（该输入
   wallMs=10.4s）。逐输入实际等待 **9.9–17.0s**。v2 起 totals 自动计算
   `inputWallRange`，不再手抄（v2 本轮为 10.7–22.6s）。
3. **「首骰 2 未准入 → 换世界重试」叙事不成立**：这是对 harness 循环
   退出值的误读。`attempts` 字段取的是 for 循环退出时的自增值（=实际
   尝试数+1；修复前一轮 3 个世界时打印 attempts=4）。首轮 artifact 的
   attempts=2 反推只有 **1 次尝试**。三重独立证据一致：① 首轮服务端
   SQLite 库 `worlds` 表恰好两行（world_1 动作场景 + world_48 链场景）；
   ② setup 415ms 只够单世界（v2 实测约 450ms/世界）；③ 首环骰
   roll_57 = 14、target 11、admitted=1。真实过程：**首骰 14 一次准入，
   从未换过世界**；「2」来自第二环拒绝骰（roll_59，person_c→person_a）。
   复核指出的记录缺陷本身属实并已修：setup 期 `api()` 直连
   `http.execute` 绕过记录管道（rollsRolled 只剩 walk 期一环、
   secondRoll 因过滤 sourceId==='person_a' 恒 null）+ 重试循环覆盖
   firstRoll。v2 起 setup 与驱动器共用管道，`worldAttempts` 逐世界尝试
   落盘骰点（v2 本轮：9、5 被拒，18 准入，第二环 9 被拒），attempts 改
   取实际尝试数。
4. **token 证据只存了数量**：`onCompletion` 证据（usage/timings/raw）
   此前只在内存，artifact 只有 `completionEvidence: 8`——应读作
   「未落盘」而非「已收集未逐尝试展开」。v2 起逐 modelAttempt 落盘
   completion 证据（含 prompt_n/predicted_n 等 token 计数与耗时分解），
   与叙事评测 harness 同口径。
5. **原始轨迹不完整**：setupOps 只在失败时返回；动作场景缺逐尝试事实包
   与提示词视图；链 modelTasks 缺各任务返回值；链 finalState 缺任务/
   人格/理智；成功路径缺原始 wire。v2 起全部落盘：setupOps/opLog 全量
   （链场景 28+48 条）、逐尝试 facts（含模型实际看到的首选短语）、
   modelTasks.returned（5/5）、finalState.characters 全量（位置/理智/
   任务/人格/外貌）、逐场景原始 netTrail（动作 134 条、链 52 条）、
   readPointIds。

复核同时确认了问题清单里的三个 A 侧事实——已在第三节逐条标注
「已确认」。

## 一、场景 A：普通行动点（页面同款会话，7 条玩家输入）

`RuleWorldSession`（规则权威结算：action/targets/results/updates/
continuation 全部零模型调用）+ 真实模型叙事（模型为主 → 判分门控 →
失败重生成一次 → 模板兜底）。命令序列：走到门厅 / 完成压力试验（被拒：
地点不符）/ 走到走廊 / 完成压力试验（10→8，任务+人格+理智联动）/
完成恢复练习（8→9）/ 上下打量四周（未识别）/ 走到门厅。

**每条输入都能正确完成；逐输入玩家等待 9.9–17.0 秒（含世界时间推进与
叙事；v2 起由 totals.inputWallRange 自动计算）。**

| 输入 | 判定 | 等待（首轮） | 模型尝试 | 采纳 |
| --- | --- | ---: | --- | --- |
| 走到门厅 | allowed | 10.8s | 1 次 9.6s | 首稿采纳 |
| 完成压力试验（门厅） | refused: milestone_location_mismatch | 9.9s | 1 次 8.9s | 首稿采纳 |
| 走到走廊 | allowed | 10.9s | 1 次 9.6s | 首稿采纳 |
| 完成压力试验（走廊） | allowed（10→8+人格+任务） | 16.3s | 1 次 14.2s | 首稿采纳 |
| 完成恢复练习 | allowed（8→9+人格+任务） | 17.0s | 1 次 14.7s | 首稿采纳 |
| 上下打量四周 | unparsed（仅时间推进） | 10.4s | 1 次 8.7s | 首稿采纳 |
| 走到门厅 | allowed | 11.3s | 1 次 8.9s | 首稿采纳 |

- 世界创建（含根叙事模型尝试 10.4s）：10.9 s。
- **8/8 叙事全部首稿通过判分门**（含被拒/未识别轮），0 重生成、0 模板
  回退；v2 复跑同为 8/8。
- 任务轮（4-5 事实）比移动/拒绝轮（2-3 事实）慢约 5s——模型成本随事实
  数增长；v2 的逐尝试 completion 证据（prompt_n 等）可直接量化。
- 终态正确：version 7、门厅、理智 9、两任务达成、两条人格变化；8 点位
  全部叙事就绪；每输入服务端操作 15–18 次（合计 124 次，明细在原始
  记录）。
- 结算组件确认为零模型调用：每输入的模型调用恰为 1 次（叙事）。

## 二、场景 B：连锁共同结算（完整驱动器 + 真实服务端 d20）

完整 `ControllerDriver` + 真实 HTTP + 服务端真实 d20 骰点。结算文本
（行动/反应/结果/更新候选）为脚本候选——**结算组件的模型化属 B3 独立
批次，不在本批**；叙事走与页面同一份 `narration-polisher` +
`narrateFromReads` 门。

链形状（world_short 双角色）：林川（person_a，发起人）推门示意 → 目标
周宁 → 真实 d20 **首骰 14 一次准入**（勘误 3：从未换世界重试）→ 周宁
反应被接受 → 周宁反指林川（驱动器运行时分配触发身份）→ 真实 d20 2 点
未准入 → 确认空目标 → 组关闭 → 结果/六步更新（任务+人格+理智）/
逐人判断/封点/提交/叙事（真实模型）/继续判断（handback）。

| 阶段 | 耗时（首轮） | 说明 |
| --- | ---: | --- |
| 引导（建世界+根叙事脚本引导） | 415ms | 单世界；v2 复跑约 450ms/世界 |
| 驱动器走链（结算+提交+真实叙事） | 16.0s | 其中模型叙事 1 次首稿采纳 |
| 合计（玩家视角的一次输入） | **≈16.4s** | 不含模型加载 12.2s（一次性） |

- 驱动器模型任务序列：targets / results / updates / narration /
  continuation（无 action——两角色均被覆盖；无 pointPlan——恢复进既有
  advance）；v2 起 modelTasks 连各任务返回值一并落盘。
- 提交恰 1 次；两环骰点：首环 14 准入、第二环 2 拒绝（首轮 artifact 只
  含 walk 期第二环——勘误 3 的记录缺陷；v2 起全量落盘）。
- 提交叙事为**模型文本**（6 条事实全对，首稿通过），非模板。

## 三、问题清单（按发现顺序；复核后状态已更新）

1. **[harness 缺陷，已修]** SQLite 库文件跨运行复用 → 新进程重造
   `world_1` 撞上旧幂等台账（`request_id_reused`）→ 会话误入
   lost_lease。修复=每次运行独立私有目录。非产品缺陷；
   review-world-page 因目录带时间戳从未触发。
2. **[已确认]** 持久层在 `checkpoint_start_advance` 后把轮次顺序按
   **（理智值，ID）升序** 重排（`SQLiteBaselineStore.finish_operation`）；
   `FixtureBaselineStore` 没有 `finish_operation`、保留传入的 order；
   `judgments.py` 的发起人校验（`initiatorId == order[cursor]`）是共享
   的。因此同一未排序 order 在内存层通过、SQLite 层拒绝。本场景 roster
   已是该序首位（不影响首轮结果）；scripted 场景的「可移植」需要 A 侧
   明确顺序契约（谁负责排序/校验）。
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
   SQLite 层）已由复核从代码坐实；内存/持久两 store 同判定的结论同
   问题 2，待 A 侧给顺序契约。
6. **[记录缺口，v2 已修]** token 级证据未落盘——v2 起逐尝试落盘
   completion 证据（勘误 4）。

## 四、通向 20 次输入验收（§798 阶段 5）的剩余工作

首轮回答了「一次输入能否正确完成、等多久」（能；9.9–17.0s）。

**范围口径：20 次输入验收 = 端到端正确性 + 持久化（重启回读）+ 真实
模型叙事。结算语义（action/reaction/results/updates 的模型化）仍属 B3
后置边界，不在该验收的责任范围内。**

1. 输入量扩到 ≥20 次（含多条**自动推进链**——linked 续段，本批未覆盖）；
2. 暂停/继续（页面刷新续接已在 review-world-page 覆盖，harness 化进本
   脚本）；
3. 历史回放（从 S₀ 重建相同状态）与**删除叙事缓存后的重新生成**；
4. 以共同结算收尾的 round 保留空 linked 续段并生成叙事（额外一次叙事
   调用计入串行等待，不计零成本）；
5. token 级成本展开已随 v2 落盘（问题 6），20 次跑直接产出；逐输入
   服务端操作明细表同由 opLog 直接聚合。

## 五、复跑

```powershell
# 仓库根目录；服务检出默认 .local/world-server-worktree（sha256 钉档，
# 不依赖 head 记忆；钉住集 tracked 脏时脚本拒绝起跑）
cd frontend
node scripts/run-world-chain-full.mjs --out artifacts/world-chain/first-round-v2.json
#   [--phase action|chain|both] [--server-checkout 路径] [--python python]
#   [--allow-dirty-server] [--allow-dirty-browser]  # 豁免脏钉住集（artifact 仍记录 status）
```
