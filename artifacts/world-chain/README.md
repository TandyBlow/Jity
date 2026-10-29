# 真实模型小世界验收报告：混合首轮 + 二十次输入 + B3 结算任务基线（§798 阶段 5/6）

日期：2026-10-28/29。分支 `world-browser`。本目录的原始记录与角色：

- `first-round.json` —— 首轮（harness `122ccef`）。动作场景段经复核为真；
  chain 段是真实单 run 记录但其主证据库已被 B 侧误删，**不作证据引用**
  （存证与溯源见 `evidence-note-first-round-db.md`）。
- `first-round-v2.json` —— 记录修复后的复跑（harness `4ca93d8`）。chain 段
  的 completion 证据为空（polisher 缓存 bug，见〇·二轮第 1 条）——动作
  场景段的证据完整。
- `first-round-v3.json` —— **chain 段的 canonical 记录**（harness
  `ae67b86`）：token 级证据、逐世界骰点、全量轨迹齐备且可复验。
- `twenty-round.json` —— 二十次输入首轮（2026-10-29）。复核不通过存档：
  C 段重建世界致输入跨世界分布、逐 commit fold 跳过刚提交点（`ok:null`）、
  链输入成本未切片、缓存重生成只盖头点——**不作验收证据引用**。
- `twenty-round-v2.json` + `twenty-run-db-v2/` —— **二十次输入验收
  canonical（2026-10-29，见第五节）**：单世界连续 21 输入、逐 commit 全链
  折算（缺读即败）、成本全切片、头点+历史点双重缓存重生成；原始 SQLite
  （3.4MB）与 server.log 随报告留存。首轮证据保留于 `twenty-run-db/`。
- `b3-baseline-v1.json` + `b3-run-db/` —— B3 第一版归档（2026-10-29，
  harness `ed3eb0b`）：13 项旧契约探针。经复核后**冻结，不作基线引用**；
  其证据被重新判分如下一条。
- `b3-rescore-v1.json` / `-v1-j3` / `-v1-j4` —— v1 证据的历次重评分
  （judge v2 / v3 / v4）。**正式口径 j4**：parsed 12/12、codec 10/12、
  5 pass / 6 fail / 1 review，总体 41.7%。旧结论「7/12 语义」撤回。
- `b3-baseline-v2.json` + `b3-run-db-v2/` —— B3 第一次修正后的 canonical
  运行（2026-10-29）：17 项探针 + 两场景。报告内嵌 judge v2 判定；**正式
  口径用 `b3-rescore-v2-j4.json`**（parsed 17/17、codec 14/17、pass 2 /
  fail 10 / review 5，总体 11.8%）。两个场景仍在提交前停止，**不得读作
  整链验收通过**。
- `b3-baseline-v5.json` + `b3-run-db-v5/` —— **复核 20 三项修复后的第一份
  干净基线**（`75061b6` 干净树，2026-10-29，judge v5）：探针总体 29.4%、
  两场景各跑满 3/4 轮提交后止于 harness 步数上限。sha256 逐文件标注口径
  （blob = `git show <commit>:<path>` 的字节；工作树检出经
  `core.autocrlf=true` 会变 CRLF，文本文件两者可能不同）：报告
  `3ed2cf84b00f89a8…`（blob=文件一致）、`world.db` `3ff6a52a52a4110f…`
  （blob=文件一致，二进制不受换行转换影响）、`server.log` **blob**
  `03868486341996c2…`——初稿把工作树文件哈希 `7fff6fae0ad70fd7…` 误标为
  blob 口径，2026-10-29 复核校正。**止于 harness 步数上限而非模型
  handback，不作整链验收，见 6.6.1。**
- `b3-baseline-v6.json` + `b3-run-db-v6/` —— **有限轮预算对照基线**
  （2026-10-29，浏览器 `102f710`，judge v5 `12be98c8…` 同 v5；服务检出
  `dd345b8`（agent，已推 `origin/agent`）其 `backend/app` **提交内容**
  与 v5 的 `4e17025` 一致（git 层无差）；报告 serverSource 逐文件
  sha256 钉的是工作树字节，与 v5 归档相比 11 个文件因 LF/CRLF 字节
  不同）：固定
  5 轮停止界下两场景各跑满 5 轮提交（首轮 + 4 自动轮），第 5 轮
  continue 的原始判断已存，受界停止 `round_budget_exhausted`，cancel
  只进 cleanup，两类保险零触发。探针 29.4% 同 v5（17 项判定逐项相同）。
  sha256 逐文件标注口径：报告 `952d19861f3a7123…`（blob=文件一致）；
  `world.db` `f517d8e580b6bb5e…`（blob=文件一致）；`server.log` 文件
  `67ec044eeb973d93…` / blob `6f218674a564dd8a…`。初稿曾把
  `git hash-object` 的 SHA-1 对象名误当 blob 的 sha256 登记
  （`1d8bceba…` / `faa51c1b…`），2026-10-29 复核校正。
  **预算耗尽不算整链验收，见 6.6.2。**

脚本：`frontend/scripts/run-world-chain-full.mjs`（两场景，`--phase
action|chain|both`）；`frontend/scripts/run-world-twenty.mjs`（二十次输入，
单模式）。

**范围声明：这是「混合首轮」基线，不是全模型语义的整链验收。** 场景 A
结算=规则权威组件（action/targets/results/updates/continuation 零模型
调用）；场景 B 结算=脚本候选；两场景只有叙事走真实模型（同一
narration-polisher + checkFactNarration 门）。结算组件的模型化属 B3 独立
批次（第六节；B3 修正后基线仍未通过，不得与本节「PASS_BOTH」混读）；
文中「PASS_BOTH」指两场景在该混合边界下通过，不覆盖
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

**→ 上述 1–5 已全部由第五节的二十次输入验收覆盖（2026-10-29，v2）。**

## 五、二十次输入验收结果（2026-10-29；harness run-world-twenty.mjs）

**PASS_TWENTY（canonical=`twenty-round-v2.json`）：单世界（world_1）连续
21 次玩家输入、四阶段、全部 hard assert 通过。** 首轮（`twenty-round.json`）
经复核存在两项 P1（链场景重建世界致输入跨世界分布；逐 commit fold 跳过
刚提交点）与两项 P2（链输入成本未切片；缓存重生成只盖头点），已全部修正
并按新证据目录复跑；首轮记录与库（`twenty-run-db/`）原样保留存档。
范围口径同第四节：端到端+持久化+真实叙事；结算语义留 B3。

| 阶段 | 内容 | v2 结果 |
| --- | --- | --- |
| A | RuleWorldSession，输入 1–8（任务达成/被拒/未识别/移动） | 全部 world_complete；约 10–16s/条；9 次模型尝试（根+8）全首稿过门 |
| B | 外部 checkpoint_pause → 服务进程重启（停机 2.7s）→ resume → 恢复会话 attach | paused 跨重启存活 ✓；状态 parity 全等 ✓ |
| C | 同世界接管：脚本化共同结算（真实 d20，发起人=冻结顺序 order[0]）→ 空 linked 续段 → continue×2 自动轮 → handback（输入 9） | roll_66=19 一次准入（person_c→person_a，动态发起人）；2 条 continue 链；走链 52.1s |
| D | 恢复规则会话，输入 10–21（12 条）+ 双重缓存重生成 | 全部 world_complete；头点 point_136（mode=head，gen 1→2）与非头历史点 point_130（mode=history，gen→3）各走 claim→删→读→真实模型重生成→回填 |

逐项交付证据（均在 `twenty-round-v2.json`）：

- **单世界连续 ≥20 次玩家输入**：21 条全部在 world_1（断言：各阶段
  worldId 一致 + 全程 `create_world` 恰 1 次 + 留存 SQLite `worlds` 表恰
  一行）。逐输入 terminal/判定/叙事/wallMs/模型尝试（facts+completion
  证据）/wireCaptures/serverOps 全落盘，链输入（输入 9）按 C 阶段切片。
- **多条自动推进链**：`continuationLog` = continue → continue →
  handback；两个自动轮普通点真实模型叙事。
- **至少一次连锁共同结算**：真实服务端 d20（roll_66，result 19 ≥ target
  11 准入）；结算候选为脚本（B3 边界），因果三件套（任务+人格+理智）整体
  挂 pending 任务的 owner。
- **共同结算后的空 linked 续段**：point_60（kind instant，同轮
  round_56）——`linked_from_point_id = point_57` 由留存 SQLite
  `world_points` 列直接核验；零行动、纯时间扫描、真实模型叙事。
- **暂停续接与服务重启**：见上表 B 行；重启发生在世界中部（A 与 C/D
  之间），重启后的状态直接接入后续输入。
- **每次提交后从 S₀ 重建一致状态（严格）**：每个 commit_point 回执上先
  get_state 缓存刚提交 head 的读取，再全链折算（root 状态 + Σ 各点
  recorded timeAdvance/entityDeltas 与各点 served state 逐一深比较）；
  **缺读即失败**——25 次 fold 全 ok 且零 `no_recorded_read`（每条
  commit fold 都实际比较了最新点），终局再全量一次。
- **清除叙事缓存后重生成（两头覆盖）**：头点 mode=head 与非头历史点
  mode=history 各走 claim→narration_delete（status missing）→narration_get
  missing→claim→真实模型重生成（同一判分门）→submit→ready，generation
  递增（history 模式绑定 {mode:'history'} 不携带 lease）。
- **token 级证据**：27 次模型尝试 / 27 条 completion 证据，全局断言零
  缺失（链段、根叙事、重生成全部在内）。

本轮钉档：browser pin 与 server pin（156 文件 sha256）在 artifact 头部。

### 首轮修正记录（二轮复核 2P1+2P2）

1. **[P1→已修]** 单世界连续性：C 不再重建世界；未准入尝试在同一世界内
   整轮 cancel（任意阶段合法：置 phase=complete、清 advance），重新开局
   下一尝试。本轮骰运一次准入（无弃轮），弃轮路径由 `abandonedRounds`
   结构承载。
2. **[P1→已修]** 逐 commit fold 严格化：`afterCommit` 先 get_state 缓存
   刚提交 head 再折算，缺读即失败；transport 钩子与 raw commit 共用。
   首轮的 `ok:null/no_recorded_read` 跳过路径已删除（24 次提交检查此前
   全部漏掉最新点）。
3. **[P2→已修]** 成本切片与全局断言：输入 9 的 modelAttempts/serverOps/
   wire 按 C 阶段切片（原为空数组+累计值）；终局断言改为**全局**校验
   全部模型尝试的 completion 证据（原只遍历输入切片）。
4. **[P2→已修]** 缓存重生成覆盖非头历史点（mode=history 全流程）。

### 本批发现（按发现顺序；✚ = 修正轮新增）

1. **[harness 缺陷，已修]** `list_points` 的 limit 上限是 100（schema
   硬约束）——fold 钩子用 200 触发 ProtocolError 污染驱动器终态。
2. **[语义确认]** `ControllerDriver.getMemory()` 返回深拷贝——外部
   prepareSuccessor 注入必须走恢复计划路径（recovery 原生携带 prepared
   successor：plan=[current, successor]，commit 后服务端自动提升）。
3. **[语义确认]** commit 后服务端直接进 `assess_continuation`（轮随
   commit 结束，游标耗尽时）——共同结算吞满 roster 游标，空 linked
   续段必须走 prepare_successor 预绑定+恢复提升，而不是同轮 plan。
4. **[语义确认]** 轮内第一个点必须 kind='normal'、后续点必须非 normal；
   instant/linked 点必须 boundary='instant'（instant 另要 duration 0，
   T08 s7 录制形状）。
5. **[语义确认]** 租约生命周期：handback 不释放租约；lease_acquire 在
   任何存活租约上拒绝（lease_held）；lease TTL=1h；恢复路径对 held
   lease 做 lease_renew。raw 操作需要 token 同步与 lease_invalid 自愈。
6. **[wire 形状]** narration_delete 是查询串模型（无 worldId/pointId
   字段、pointId 走路径）；narration_get 客户端无 requestSchema（body
   必须为空）；list_points 投影不含 linkedFromPointId/trigger/timeAdvance。
7. **[稳定性]** wllama wasm 偶发崩溃（chat template assert）毒化模块级
   引擎缓存——harness 崩溃错误做新模块实例（cache-bust）重载+单次重试。
8. **✚[语义确认，修正轮]** 冻结顺序随理智变化：`finish_operation` 在
   start_advance 后按（理智值，ID）升序重排——A 阶段改变理智后链发起人
   不再可预设，必须从 get_context 的 round.order 动态读取（首轮问题 2
   在同世界延续下的显形）。
9. **✚[语义确认，修正轮]** 结算因果两硬约束叠加：units.py 裁定（2026-10-22）
   人格变化必须搭配新达成任务、sanities 键集与 personalities 配对；
   committed-narration 投影要求**每个实体**的 tasksAchieved/
   personalityChanges/sanitySet 三者同有同无——三件套必须整体挂到
   pending 任务 owner 名下，不能按发起人拆开。
10. **✚[语义确认，修正轮]** 未准入尝试的同世界重试=整轮 cancel（Registry
    只要求 head 叙事 ready+lease valid，任意阶段含未提交工作均可取消）。

## 六、B3 结算任务基线（两轮复核修正后，2026-10-29）

**批次状态：未关闭。** 2026-10-29 的两轮独立复核驳回了「12/12 结构、7/12
语义」作为可信语义基线。原 7/12 结论撤回；当前结论是：**模型能稳定产出
可解析 JSON，但修正后的契约与判分下结算语义不达标，两场景均在提交前停止。**

### 6.1 第一轮复核（P1×3、P2×1）与修正

1. **提示词改变职责**：action 把 `consumed` 写成「所有角色必须 skip」，
   原设计只有主角不得重复执行玩家命令（§6.1）；continuation 把「任务未完成」
   等同于继续，原设计要求同时判断「大概率发生」与「与主角有关」（§8.1）；
   results 遗漏输入中的骰点判定。→ 提示词全部按设计重写；continuation 的
   拟行动与主角关联只作判断产物，端口在返回 wire 结论前剥离。
2. **判分只查结构**：荒诞结果、空任务更新、无因果 `sanitySet=99`、错人物
   行动都被判通过。→ 判分改为 `pass | fail | review`，`review` 不计通过；
   新增归属、目标句、复执命令、目标选择、结果溯源/骰点、更新归属/阶段/
   因果/变化预期、continuation 两条件检查。
3. **task-only 被当作必须补齐三件套**：设计是「任务达成 → **可能**个性变化」。
   → 叙事投影取消三件套同有同无；task-only Δ 合法，个性仍需任务、理智仍需
   个性；事实按六阶段顺序产出。
4. **调用计数混入程序职责**：场景 9 条调用含 1 条程序 pointPlan。→
   `modelCalls` / `programCalls` 分列。

### 6.2 第二轮复核（P1×4、P2×2）与修正

1. **合法分阶段更新被因果检查误拒**：旧检查在每个阶段的单个 delta 内找
   任务/个性/理智，合法的 `tasks → personality → sanity` 被报「个性无任务、
   理智无个性」。→ 因果链按**整批累计**；拆分调用必须携带已确认的前序阶段
   证据（探针显式传入已应用的 tasks/personality；端口为分阶段调用记录前序
   证据，只收服务端工作态中真实存在的任务）。
2. **任务与个性被错误要求同属一人**：设计允许任何人物的任务达成影响任何
   人物。→ 叙事投影与判分改为：本批（或前序阶段）**任意人物**有任务达成，
   即可触发某人的个性变化；个性与理智仍按对应人物配对。
3. **场景 targets 仍用旧形状**：`{targetId}` 对象被直接和字符串名册比较。
   → 场景判分先映射到 id，再查名册/自指/重复；自测加入合法 `{targetId}` 正例。
4. **自由文本反应误放行**：「瞬移到火星并毁灭太阳」仍判 pass。→ 反应必须
   可溯源到发起行动或该人物的任务目标；不可溯源判 fail，可溯源仍归
   `review`；源行动上下文未归档时归 `review`（不能拿缺失证据判 fail）。
5. **P2 口径**：非法 stage、缺必填字段不再算「codec 结构通过」。→ 报表分列
   `parsed`（JSON 可解析）与 `codec`（形状/字段契约）；总体通过率 =
   `semanticsPass / probes`，`review` 不进分子但进分母，另列仅按可裁定样本
   的 `autoPassRate`。

**复核轮 19 的判分细化（judge v4）**：

- **stage 词表钉进 schema**：合并调用的数组项也必须 `enum` 六个阶段名，
  受控解码直接拒绝把字段名当 stage；提示词补一句「stage 只能取这六个名字」。
- **否定式成功措辞**：`未成功/没有成功/未能/没能/未达成` 属于失败措辞，
  不再是成功措辞；裸「未」已撤掉（会误伤“未来”）。
- **纯判定句**：剥掉人物名、标点与成败词后为空、且不含可造事件的句子
  （如未准入关系要求的「未成功」）免于可追溯性检查；无骰点成员的裸成败
  判定没有证据支撑，归 `review` 而不是通过。
- **骰点不符单独标注**：准入写成失败、未准入写成成功记 `[dice mismatch]`，
  与可追溯性失败分开；每个成员的错误全部收集，首个错误不再掩盖后续违规。
- 判分自测扩到 **27 项**，覆盖上述正反例；任一不符则运行状态为
  `JUDGE_SELF_TEST_FAILED`。

### 6.3 归档与重评分

- `b3-baseline-v1.json` + `b3-run-db/`：第一版归档（harness `ed3eb0b`，
  browser `a502a9b`，13 项旧契约探针）。**冻结，不作基线引用。**
- `b3-rescore-v1.json`、`b3-rescore-v1-j3.json`：judge v2/v3 的历史重评分。
- `b3-rescore-v1-j4.json`：**judge v4 重评分 v1**（12 项旧探针）：
  parsed 12/12、codec 10/12、**pass 5 / fail 6 / review 1**，总体 41.7%，
  可裁定样本 45.5%。
- `b3-baseline-v2.json` + `b3-run-db-v2/`：第一轮修正后的 canonical 运行
  （browser `88b59d`，干净树；server `4e17025`）：17 项探针 + 两场景；
  报告内嵌的是 judge v2 判定，**正式口径以 judge v4 重评分为准**。
- `b3-rescore-v2-j3.json`：judge v3 重评分 v2（历史记录）。
- `b3-rescore-v2-j4.json`：**judge v4 重评分 v2 原始输出**（正式口径）：
  parsed 17/17、codec 14/17、**pass 2 / fail 10 / review 5**，总体
  **11.8%**，可裁定样本 16.7%。原始模型输出与数据库原样保留。
- `b3-baseline-v3.json` / `b3-baseline-v4.json` + `b3-run-db-v4/`：
  enum 修复后的两次实测（见 6.6；`1355abd` 归档）。probes 率：v3 与 v4
  均 parsed 17/17、codec 16/17、pass 4 / fail 8 / review 5（v4 重评分
  `b3-rescore-v4-j5.json`，judge v5）。**不是同契约基线**：v3 的 judge
  源码无 hash、chain 死于协议 bug；v4 含被否决的顺序放宽。

配置：Qwen3-0.6B Q4_K_M；结算端口 context 2048、temperature 0、seed 42、
json_schema strict、maxTokens 64–384、timeout 110s；叙事仍是已交付
narration-polisher + checkFactNarration（本轮未触发）；真实 Edge headless、
跨源隔离；真实 Python 持久服务。v2 运行模型加载 11.7s。

### 6.4 v2 探针（judge v4 重评分；解析 17/17，codec 14/17，pass 2，fail 10，review 5）

| 探针 | codec | 判定 | 观察（原始输出） |
| --- | --- | --- | --- |
| action_pending | ✓ | review | 「转身进入走廊」——偏离命令但具体，待人工判断 |
| action_consumed_protagonist | ✓ | review | 「转身避开盒子」——未复执命令；自发行动待判断 |
| action_consumed_npc | ✓ | **pass** | 同一输出在林川名下合法（consumed 只是背景） |
| targets_directed | ✓ | fail | 点名林川，仍返回 `[]` |
| targets_solo | ✓ | pass | 空集 |
| reaction_joint | ✓ | review | 「林川将盒子稳稳地放在门框上」——可溯源于任务，内容待人工复核 |
| results_joint | ✓ | review | 两人均「没有成功」——无可造事件，但无骰点证据的裸判定待复核 |
| results_rejected_roll | ✓ | review | 有未准入骰点的一方是契约写法的纯判定；另一人无骰点的裸判定仍待复核 |
| results_admitted_roll | ✓ | fail | 准入一方写成「林川未成功」——`dice mismatch` |
| updates_merged | ✗ | fail | 把 `appearanceChanges/subtasksAdded/...` 当 stage 名 |
| updates_none_expected | ✗ | fail | 同批非法 stage；无变化场景仍产出任务变化 |
| updates_stage_tasks | ✓ | fail | `tasksAchieved:["person_1"]`——虚构任务 id，且归属 person_a |
| updates_stage_personality | ✗ | fail | 个性变化缺 `supersedes` |
| updates_stage_sanity | ✓ | fail | 给 person_a `sanitySet:90`——无该人物的个性变化 |
| continuation_likely_related | ✓ | fail | `plannedAction` 是目标句 |
| continuation_unrelated | ✓ | fail | 同上；`protagonistRelevance` 未提主角 |
| continuation_done | ✓ | fail | 无驱动仍 continue |

### 6.5 场景（v2 原始运行；judge v4 重评分）

两场景均为 `COMPLETED_WITH_FAILURES`，失败即证据，未用脚本候选替换。

**普通行动点（setup 0.3s，walk 86.8s，4 次模型调用 + 1 次程序 pointPlan）**

- person_a：action「转身进入走廊」（11.4s）→ targets `[]`（7.8s）→
  results「没有成功」（9.7s，无骰点证据的裸判定 → review）→ updates 57.0s
  输出非法 stage，端口在发往服务端前拒绝，控制器停止，round 整轮 cancel，
  head 仍 point_13。
- 未提交，因此没有叙事调用；task-only 投影只有单测证据。

**连锁共同结算（setup 1.4s，walk 69.7s，4 次模型调用）**

- 真实 d20：result 19 一次准入（person_a→person_c，roll_45）。
- reaction 复述发起行动（10.1s，判分 fail）→ targets `[]` → results
  两人均「没有成功」（准入一方 → `dice mismatch` fail）→ updates 非法
  stage（45.5s）；round cancel，未提交。
- 本轮同样未到达 commit/narration；task-only 叙事链尚未在真实模型输出上复验。

场景判分（v4 重评）：action 4/4 解析、3/4 codec、1 条语义错误
（updates 非法 stage）+1 条待复核（无骰点裸判定）；chain 4/4 解析、
3/4 codec、3 条语义错误（reaction 复述、结果骰点不符、updates 非法 stage）。
模型/程序调用分列为 `modelCalls`/`programCalls`。

### 6.6 复核轮 20：v3/v4 的实测、两层 action-stop 与 ①b 产品 sink（批次仍未关闭）

**并发运行的处置**：v3（15:42–15:49，pin `d33a1ca`）与 v4（15:57–16:13，
pin `99bea60`）由另一进程自行跑完并已归档（`1355abd`）。v3 没有 DB 快照；
**后续不再把 v3 当对照**。v1 的 DB 快照曾被中断运行短暂覆盖后已还原。

**99bea60 否决与顺序契约恢复（`1076c5b`）**：其「stage 顺序不是契约」的
前提不成立——`mergeUpdatesStages`（schedule.ts:356）对 `index <= last`
直接 throw，合并路径经 `checkUpdatesStages`（schedule.ts:382）必撞，
`schedule.test.ts:516` 钉住该 throw，设计 §6.3「六步生成顺序仍不改变」。
放宽只把失败从端口挪进产品运行时，且判分把顺序降级为 formatNotes（pass
分支还不带备注）。选择 **(a) 保持顺序契约**：prompt 恢复六阶段顺序要求；
judge 把 `index <= last` 记为语义失败（注明产品会 throw）；port audit 同步；
`formatNotes` 双标准删除。**provenance（`8878e97`）**：rescore 报告现在带
`judgeSource {path, sha256}`（v3/v4 的 j5 已重新生成，率不变），并记录源
归档是否钉过 judge（v3 = false，脏树）；新增
`scripts/b3-port-audit-fixture.mjs`——机械切片 port 的 audit 源码实跑 6 项
负例（乱序/重复/字段名冒充 stage/split 单对象），audit 源 sha256 打印在输出。

**action stop 的两层定性（复核确认）**：
- **直接原因（①a，harness）**：`group_29` 已在 point_16 consumed，自动轮
  point_21 复用被服务端拒（judgments.py:80）。模型无责；harness 已修
  （v4 后的调试验证 point_21/point_22 以新 group id 正常提交）。
- **产品缺口（①b，产品路径，`b673574` 已补）**：生产代码没有任何填充
  `roundAllocations` 的路径（只有场景/测试种子）；rule-session 的 pointPlan
  在 continue 后仍返回已消费的 point id；页面固定 handback 掩盖了两者——
  一旦接入模型 continue，页面会先撞 `point id is already committed`
  （control.py:659）、再到 group 复用。**B3 场景与产品整链分开写：B3 基线
  是 harness-scoped，不声明产品 continue→自动轮→handback 已通。**

**①b 产品 sink（`b673574`）**：`ControllerDriver.setRoundIdentitySink`——
每次确认的 continue 结论（服务端已切 automatic round 后恰好一次）收到
`(roundId, served order)`，由程序经 transport 分配新身份（§9.3），返回内存
补丁由驱动折进自己的唯一内存（recover 替换透明）；未注册/抛错记
`lastRoundIdentityError`，下一个 step 按产品拒绝走，绝不静默降级。触发点在
conclude 采纳分支（`execute()` transport 路径），单调用点。场景证据字段
`roundIdentityError` 随报告留存。

**实测（调试验证 + `.local` 探针运行；正式基线待 `7ea0f2d` 树全跑）**：
①a 修复后 action 场景跨轮提交正常（round_17/round_18 的 point_21/point_22
以新 group id 提交，updates 合法批次 `[]`，narration/继续继续工作）；
当前停点是**模型语义**——`plannedAction` 连续写成目标句（判分 fail），
模型持续 continue 直到 step limit，随后 harness 按整轮 cancel 收尾。这是
要进模型对照的样本，不是 harness 缺陷。prompt 已把顺序与「外观必须先于
任务、无空占位阶段」写明确（复核 20 的措辞）。

**口径**：603/603 与双 tsc 在 `b673574` 后全过；judge 自测 28/28；port
fixture 6/6。**下一步**：①a（修完）、①b（补完）→ 两场景干净基线（同 judge
hash、同 probe 集）→ 模型对照（提示词变体、更大模型）。

### 6.6.1 复核 20 三项修复与 v5 干净基线（`75061b6`，2026-10-29）

复核结论：provenance 与 port 夹具关闭；①b 三项中等问题不关闭。修复如下：

1. **sink 补丁曾是整包覆盖 → 现为增量折入**：`RoundIdentitySink` 返回的
   `ids`/`roundAllocations` 按 key 并进**当前**内存、`allocatedKeys` 取并集；
   驱动不再 `Object.assign` 整包。B3 两场景改回纯增量（删掉 `memoryRef`
   旧快照）。恢复出的 point/group 身份与既有 allocation key 不再被擦除
   （复核复现的正是「补丁从 recover 前内存整包构造」）。
2. **automatic 的 handback 误触发 → 改按确认结论判定**：挂点不再看
   `round.trigger`（handback 后服务端保留已结束 automatic 轮摘要），改为读
   conclude 回包的 `kind === 'continue'`，用服务端 `nextRoundId` 与采纳后新轮
   `order` 调 sink；回包缺 nextRoundId 记 `round_identity_target_missing`。
3. **未注册 sink 静默放行 → 记录 + 预置分配兼容规则**：无 sink 且该轮
   `roundAllocations[nextRoundId]` 已预置 → 合法（场景/测试的预置分配路径，
   由 `idlePointDecision` 作为一步发 allocate_ids，`controller.test.ts`
   「continue retires the old plan…」即此路径），不记错；其余记
   `round_identity_sink_missing:<roundId>`，下一步按产品拒绝走（复用 point/
   group id 被服务端拒），不静默降级。错误 sticky（成功不清），
   `lastRoundIdentityError` 注释同步。

**回归**：`controller.test.ts` 新增 4 项（delta 合并 / continue-only /
缺失 sink + 预置兼容 / sink 抛错保留身份）→ **607/607**；双 tsc 净；lint
0 error（既有 warning）。外部回归 `frontend/scripts/round-identity-regress.mjs`
（真实 `driver.recover` + 桩 transport，不调模型/不起服务，3 项全 PASS）
覆盖 recover 整包替换这条单测盖不到的路径；复核方脚本
`.local/review-b673574.cjs` 钉住的是修复前行为，现按设计在第一条断言失败
（`recovered_point` 不再被擦除）。

**v5 基线**（`75061b6` 干净树，judge v5 `12be98c8…`，17 探针 + 两场景）

- 探针：parsed 17/17、codec 16/17、语义 pass 5 / fail 7 / review 5 → 总体
  **29.4%**（auto-decided 12 项 41.7%）；judge 自测 28/28。
- action：**3 轮提交**（point_16 / point_21 / point_22）+ 3 段叙事
  （8.4–9.2s），21 次模型调用 + 4 次程序 pointPlan；第 4 轮 point 停在
  action/targets 之后。止于 harness **步数上限 80**，`roundIdentityError:
  null`，①a 的 `group_29` 复用未再出现。
- chain：**4 轮提交**（point_37 / 44 / 45 / 46）+ 4 段叙事（8.7–8.9s），
  19 次模型调用 + 3 次程序 pointPlan；第 5 轮停在 updates 之后。同样止于步数
  上限，`roundIdentityError: null`。
- 判分：action 语义错 3（continuation 目标句 ×3）+ review 4（results 裸
  判定）；chain 语义错 5（reaction 复述、results 骰点不符、continuation
  目标句 ×3）+ review 3。**两场景合计：continuation 语义错 6 条、results
  待复核 7 条**（复核校正补齐的合计口径）。两场景 `accepted=false`。
- v4→v5 不作改善口径：v4 在 point 内就停（updates 非法 stage），v5 是修复后
  第一次真正跑满多轮——**updates 本轮全解析通过**，停点是模型反复 continue
  撞上 harness 步数上限。

**边界（下一批先定界，再谈模型对照）**

- 两场景都**不是**模型 handback 收尾：步数上限（80 step）先于计划预算耗尽。
  要么放宽步数上限让场景跑到 harness 计划预算并定性为 harness 停，要么给
  场景定 round 预算并在报告里写死。
- 第 2 项（handback 不触发 sink）现有单测 + 外部脚本证据；**真实模型未走到
  handback**，因此「产品 continue→自动轮→handback 已通」仍不成立。
- ①a 的真实模型证据：两场景多轮 point 均以新 group id 提交，未再撞
  `point id is already committed` / group 复用。
- 取证瑕疵：v5 的 `--out ../artifacts/...` 被脚本按**仓库根**解析，实际写到
  仓库外（`D:\others\artifacts`）；报告、`world.db`、`server.log` 随后以同一
  磁盘 `mv` 原样移入本目录（未改写，sha256 见上条**blob 口径**），`retainedEvidence`
  保留的是原 flag 值。6.8 的命令与路径口径已同步修正。

**三项修复关闭（2026-10-29 审查方独立复跑确认）**：607/607、recover 回归
3/3、port 6/6、双 tsc 通过；v5 判分、judge hash、报告与 DB 哈希逐项一致。
①b 三项修复（sink 增量折入 / confirmed-continue 门 / 缺失 sink 记录+预置
兼容）就此关闭。

**停止界已定并实现（2026-10-29 审查建议，提交总指挥确认后跑下一份基线）**

固定 5 轮 = 首轮 + 4 个自动轮，由 `run-world-b3.mjs` 顶层的 `boundary`
冻结并随报告落盘（`report.boundary`，逐场景 `boundary`/`roundBudget` 镜像）：

- 每轮完整走完 commit、叙事与 continuation 判断；模型提前 handback 正常
  提交并核验交还完成（场景 `sceneEnd=model_handback`）。
- 第 5 轮仍 continue：保存模型原始判断（`roundBudget.exhausted.judgment`
  与调用记录 `roundBudgetExhausted`），不回填第 6 轮身份、不提交
  conclude，在开启第 6 轮前以 `round_budget_exhausted` 受界停止；场景
  清理的 cancel 单列在 `cleanup`，**不计模型 handback**。
- step 上限 80→400、控制器任务预算 40→240，均降为保险（v5 的 40 会在第 4
  轮前抢先截断）；触发时 `sceneEnd=insurance_step_limit` /
  `insurance_task_budget` 单独标记。初稿把后者称为「协议调用预算」——
  实际计数点在 `consumeModelOutput`（控制器消费的 model 决策产出，含程序
  pointPlan/time），非 HTTP 协议调用数，2026-10-29 复核改名。
- 对照各组冻结相同 round/step/任务预算与 judge hash；预算耗尽的运行记为
  `COMPLETED_ROUND_BUDGET_EXHAUSTED`，**不算整链验收通过**。

**停止界实现复核通过（2026-10-29）**：审查方以真实端口源码与驱动、模型/
transport 桩独立确认——第 5 次 continue 保存原始判断、不分配第 6 轮身份、
不提交 conclude；两场景 sentinel 均归类 `round_budget_exhausted` 且
`runError=null`；第 5 轮 handback 正常提交到达 `world_complete`；
`roundBudget=null` 的探针路径不受影响。复现脚本不入库（审查方留存）。
真实模型五轮运行与产品 handback 验收仍待实测；v6 执行按总指挥调度。

v5 保留为干净诊断记录（两场景止于旧 80 step 上限）；下一份按上述停止界
运行的记录作为**有限轮预算对照基线**。

### 6.6.2 v6：固定 5 轮停止界下的有限轮预算基线（2026-10-29）

总指挥批准的第一次按停止界运行的完整基线（浏览器 `102f710`，judge v5
`12be98c8…` 同 v5；服务检出 `dd345b8`，其 `backend/app` **提交内容**与
v5 的 `4e17025` 一致——git 层无差；serverSource 逐文件钉的是工作树字节，
145 个文件中 11 个因 LF/CRLF 与 v5 归档字节哈希不同）。运行约 19.5 分钟
（探针 211s + action 527s + chain 570s），全程未调提示词/判据；停止界
参数即 6.6.1 冻结值（round 5 / step 400 / 任务预算 240）。

- 停止方式：两场景都在第 5 轮 continuation 仍 continue 时受界停止——
  `sceneEnd=round_budget_exhausted`、`runError=null`、count 5/5，原始
  判断存 `roundBudget.exhausted.judgment`（两处 plannedAction 仍是目标
  句家族）；不分配第 6 轮身份、不提交 conclude；场景清理 cancel 分别
  关闭 round_20 / round_44（cleanup 单列，不计模型 handback）。
- 保险零触发：step 400 与任务预算 240（实际 used 38/33）都未接近——
  v5 的「步数上限抢先截断」不再发生，停止界按设计工作。
- 提交与调用：action 5 点（point_16/21/22/23/24），**结算模型调用 29
  次** + 程序 pointPlan 5 次；chain 5 点（point_38/45/46/47/48），**结算
  模型调用 25 次** + 程序 4 次（口径=报告 judged）。叙事两场景各 5 段
  （action 9.2–10.9s / chain 9.0–55.2s），零回退、completion 证据每场景
  5 条，另计不入结算——含叙事总量 34/30。初稿把端口总调用（34/29，含
  程序任务、不含叙事）误记为模型调用数，2026-10-29 复核改正。链场景
  首骰 roll_49=11 对目标 11 一次准入、无弃轮；`roundIdentityError` 两
  场景均 null。
- 判分（judge v5）：action 语义错 5（continuation ×5）+ review 6
  （results 裸判定 ×6）；chain 语义错 7（reaction 复述、results 骰点
  不符、continuation ×5）+ review 4（results ×4）。**两场景合计：
  continuation 语义错 10 条（本轮 10 次 continuation 判断全部为目标句
  ——温度 0 下该失败家族确定性复现）、results 待复核 10 条。** 两场景
  `accepted=false`。
- 探针：parsed 17/17、codec 16/17、语义 pass 5 / fail 7 / review 5 →
  总体 29.4%（auto-decided 41.7%）；17 项判定与 v5 **逐项相同**。
- v5→v6 读法：**judge 判据没有变化**（同 hash 同判据）；变化的是停止
  界（harness 步数上限抢先截断 → 轮预算受界停止）、覆盖轮数（3/4 轮 →
  满 5 轮）与样本量，continuation 判分数字随之不同（v5 6 条/7 轮 vs v6
  10 条/10 轮），**不作改善或恶化比较**。v6 是后续模型
  对照（提示词变体、更大模型）的冻结基线：round 5 / step 400 / 任务
  预算 240 / judge `12be98c8…` / probe 集 17 项。
- 边界事实保持：两场景仍**没有**走到模型 handback（第 5 轮全部
  continue），产品 continue→自动轮→真实模型 handback 的闭环仍未实测；
  预算耗尽不算整链验收通过。

### 6.7 结论与下一步

- 判分与因果边界已补齐并可回放（judge v5 + judgeSource hash；28 项自测；
  port fixture 6 项）；`review` 不计通过，旧归档可重评分。
- 产品侧新增：`RoundIdentitySink`（①b），continue 后新轮身份由程序分配；
  页面/会话产品路径不再被固定 handback 掩盖。**「产品 continue→自动轮→
  handback 已通」的声明仍以带模型 continue 的产品路径全跑为准。**
- 基线声明：v1（冻结）、v2（j4 口径 11.8%）为既有记录；v3/v4 是 enum 修复
  后第一批实测（v4 j5 23.5%）；**v5（`75061b6`，6.6.1）是复核 20 三项修复后
  的第一份干净基线**（29.4%），但两场景止于 harness 步数上限；**v6
  （`102f710`，6.6.2）是停止界落地后的有限轮预算对照基线**（29.4%，两场
  景各满 5 轮受界停止，保险零触发）。
- 当前已知的主要模型失败（同契约实测）：目标漏选、结果裸判定（review）/
  骰点不符、continuation 目标句冒充拟行动、updates 仪式化六阶段（含空
  changes 占位）、虚构任务 id、反应复述。
- **下一步**：停止界已定并实现（6.6.1，实现经审查方桩验证通过），v6 有
  限轮预算对照基线已落（6.6.2）→ 每模型 ≥1 次完整 run 的对照（提示词
  变体、更大模型；同 judge hash、同 probe 集、同冻结预算）→ 产品
  continue→自动轮→真实模型 handback 闭环实测 → 之后才谈 20 次输入验收。
  混合口径的 `twenty-round-v2` 仍是既有混合边界结论。

### 6.8 复跑

```powershell
cd frontend
# 路径按**仓库根**解析（不是 frontend）：--out artifacts/... 落在仓库内，
# 写成 ../artifacts/... 会落到仓库外（v5 就踩过，见 6.6.1）。
# 服务检出用 --server-checkout 指定（HEAD 与逐文件 sha256 由报告
# serverSource 钉住；v6 用的 agent 检出 HEAD=dd345b8，backend/app 与
# origin/world-server 一致）。停止界 round 5 / step 400 / 任务预算 240
# 冻结在脚本 boundary，随报告落盘。
# 完整基线（任务探针 + 两场景；v6 实测 探针 211s + 场景 527s/570s，约 19.5 分钟）
node scripts/run-world-b3.mjs --server-checkout <服务检出> `
  --out artifacts/world-chain/b3-baseline-v7.json `
  --db-snapshot artifacts/world-chain/b3-run-db-v7
# 只跑探针 / 只跑指定场景（迭代用，不作 canonical）
node scripts/run-world-b3.mjs --only none --out .local/probes.json
node scripts/run-world-b3.mjs --only chain --out .local/chain.json
# 用当前判分重放旧归档（不启动服务、不调模型）
node scripts/run-world-b3.mjs --rescore artifacts/world-chain/b3-baseline-v4.json `
  --out artifacts/world-chain/b3-rescore-v4-j5.json
# ①b sink 三项回归（不启服务/不调模型，真实 recover + 桩 transport）
node scripts/round-identity-regress.mjs
```

## 七、历史批次复跑（混合首轮与二十次输入）

```powershell
# 仓库根目录；服务检出默认 .local/world-server-worktree（sha256 钉档，
# 不依赖 head 记忆；钉住集 tracked 脏时脚本拒绝起跑）
cd frontend
node scripts/run-world-chain-full.mjs --out artifacts/world-chain/first-round-v3.json
#   [--phase action|chain|both] [--server-checkout 路径] [--python python]
#   [--allow-dirty-server] [--allow-dirty-browser]  # 按侧豁免脏钉住集（artifact 仍记录 status）

node scripts/run-world-twenty.mjs --out artifacts/world-chain/twenty-round-v2.json `
  --db-snapshot artifacts/world-chain/twenty-run-db-v2
#   [--server-checkout 路径] [--python python]  # 单模式；DB+日志自动留存到
#   # --db-snapshot 目录（每次运行覆盖，复跑前自行归档）
```
