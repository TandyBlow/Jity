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
- `b3-rescore-v1.json` / `b3-rescore-v1-j3.json` —— v1 证据的两次重评分
  （judge v2 / v3）。v3：parsed 12/12、codec 10/12、4 pass / 6 fail /
  2 review，总体 33.3%。旧结论「7/12 语义」撤回。
- `b3-baseline-v2.json` + `b3-run-db-v2/` —— B3 第一次修正后的 canonical
  运行（2026-10-29）：17 项探针 + 两场景。报告内嵌 judge v2 判定；正式
  口径用 `b3-rescore-v2-j3.json`（parsed 17/17、codec 14/17、pass 2 /
  fail 12 / review 3，总体 11.8%）。两个场景仍在提交前停止，**不得读作
  整链验收通过**。该文件见 `b3-rescore-v2-j3.json`。

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
   `review`（内容合理性不自动放行）。
5. **P2 口径**：非法 stage、缺必填字段不再算「codec 结构通过」。→ 报表分列
   `parsed`（JSON 可解析）与 `codec`（形状/字段契约）；总体通过率 =
   `semanticsPass / probes`，`review` 不进分子但进分母，另列仅按可裁定样本
   的 `autoPassRate`。

判分自测扩到 **22 项**（含：合法三阶段批次、跨人物任务触发、拆分调用带前序
证据、合法 `{targetId}`、荒诞反应不得自动通过、非法 stage 记为 codec 失败），
全部按预期；任一不符则运行状态为 `JUDGE_SELF_TEST_FAILED`。

### 6.3 归档与重评分

- `b3-baseline-v1.json` + `b3-run-db/`：第一版归档（harness `ed3eb0b`，
  browser `a502a9b`，13 项旧契约探针）。**冻结，不作基线引用。**
- `b3-rescore-v1.json`：judge v2 对 v1 的首次重评分（历史记录）。
- `b3-rescore-v1-j3.json`：**judge v3 重评分 v1**（12 项旧探针）：
  parsed 12/12、codec 10/12、**pass 4 / fail 6 / review 2**，总体 33.3%，
  可裁定样本 40.0%。
- `b3-baseline-v2.json` + `b3-run-db-v2/`：第一轮修正后的 canonical 运行
  （browser `88b59d`，干净树；server `4e17025`）：17 项探针 + 两场景；
  报告内嵌的是 judge v2 判定，**正式口径以下一条 v3 重评分为准**。
- `b3-rescore-v2-j3.json`：**judge v3 重评分 v2 原始输出**：parsed 17/17、
  codec 14/17、**pass 2 / fail 12 / review 3**，总体 **11.8%**，可裁定样本
  14.3%。原始模型输出与数据库原样保留。

配置：Qwen3-0.6B Q4_K_M；结算端口 context 2048、temperature 0、seed 42、
json_schema strict、maxTokens 64–384、timeout 110s；叙事仍是已交付
narration-polisher + checkFactNarration（本轮未触发）；真实 Edge headless、
跨源隔离；真实 Python 持久服务。v2 运行模型加载 11.7s。

### 6.4 v2 探针（judge v3 重评分；解析 17/17，codec 14/17，pass 2，fail 12，review 3）

| 探针 | codec | 判定 | 观察（原始输出） |
| --- | --- | --- | --- |
| action_pending | ✓ | review | 「转身进入走廊」——偏离命令但具体，待人工判断 |
| action_consumed_protagonist | ✓ | review | 「转身避开盒子」——未复执命令；自发行动待判断 |
| action_consumed_npc | ✓ | **pass** | 同一输出在林川名下合法（consumed 只是背景） |
| targets_directed | ✓ | fail | 点名林川，仍返回 `[]` |
| targets_solo | ✓ | pass | 空集 |
| reaction_joint | ✓ | review | 「林川将盒子稳稳地放在门框上」——可溯源于任务，内容待人工复核 |
| results_joint | ✓ | fail | 「没有成功」——不可溯源到冻结行动/任务 |
| results_rejected_roll | ✓ | fail | 「周宁未成功」——同上 |
| results_admitted_roll | ✓ | fail | 「周宁未成功」——同上 |
| updates_merged | ✗ | fail | 把 `appearanceChanges/subtasksAdded/...` 当 stage 名 |
| updates_none_expected | ✗ | fail | 同批非法 stage；无变化场景仍产出任务变化 |
| updates_stage_tasks | ✓ | fail | `tasksAchieved:["person_1"]`——虚构任务 id，且归属 person_a |
| updates_stage_personality | ✗ | fail | 个性变化缺 `supersedes` |
| updates_stage_sanity | ✓ | fail | 给 person_a `sanitySet:90`——无该人物的个性变化 |
| continuation_likely_related | ✓ | fail | `plannedAction` 是目标句 |
| continuation_unrelated | ✓ | fail | 同上；`protagonistRelevance` 未提主角 |
| continuation_done | ✓ | fail | 无驱动仍 continue |

### 6.5 场景（v2 原始运行；judge v3 重评分）

两场景均为 `COMPLETED_WITH_FAILURES`，失败即证据，未用脚本候选替换。

**普通行动点（setup 0.3s，walk 86.8s，4 次模型调用 + 1 次程序 pointPlan）**

- person_a：action「转身进入走廊」（11.4s）→ targets `[]`（7.8s）→
  results「没有成功」（9.7s，不可溯源）→ updates 57.0s 输出非法 stage，
  端口在发往服务端前拒绝，控制器停止，round 整轮 cancel，head 仍 point_13。
- 未提交，因此没有叙事调用；task-only 投影只有单测证据。

**连锁共同结算（setup 1.4s，walk 69.7s，4 次模型调用）**

- 真实 d20：result 19 一次准入（person_a→person_c，roll_45）。
- reaction 复述发起行动（10.1s，判分 fail）→ targets `[]` → results
  两人均「没有成功」→ updates 非法 stage（45.5s）；round cancel，未提交。
- 本轮同样未到达 commit/narration；task-only 叙事链尚未在真实模型输出上复验。

场景判分（v3 重评）：action 4/4 解析、3/4 codec、2 条语义错误；
chain 4/4 解析、3/4 codec、3 条语义错误。模型/程序调用分列为
`modelCalls`/`programCalls`。

### 6.6 结论与下一步

- 判分与因果边界已补齐并可回放；`review` 不计通过，旧归档可重评分。
- 0.6B 在修正后的契约下：JSON 可解析率 17/17，codec 14/17，语义总体
  通过率 11.8%；主要失败是目标漏选、结果不可溯源、updates 非法 stage/
  虚构任务/因果不成立、continuation 用目标句当拟行动。
- 评测缺口仍在：初始世界生成未覆盖；自由文本结果/反应的「是否编造事件」
  只做部分自动检查，其余归人工复核；合法 updates 未出现，叙事 gate 与
  task-only Δ 的真实链路未复验；continue→自动轮→handback 整链未跑。
- **下一步（按用户裁定）**：以同一契约、同一判分开展模型对照（提示词变体、
  更大模型），并在出现合法 updates 的场景中复验 task-only 叙事；之后才谈
  20 次输入验收。混合口径的 `twenty-round-v2` 仍是既有混合边界结论，B3
  未通过前不得宣称全模型整链。

### 6.7 复跑

```powershell
cd frontend
# 完整基线（任务探针 + 两场景，约 4 分钟；输出与 DB 随报告留存）
node scripts/run-world-b3.mjs --out ..\artifacts\world-chain\b3-baseline-v2.json `
  --db-snapshot ..\artifacts\world-chain\b3-run-db-v2
# 只跑探针 / 只跑指定场景（迭代用，不作 canonical）
node scripts/run-world-b3.mjs --only none --out ..\.local\probes.json
node scripts/run-world-b3.mjs --only chain --out ..\.local\chain.json
# 用当前判分重放旧归档（不启动服务、不调模型）
node scripts/run-world-b3.mjs --rescore ..\artifacts\world-chain\b3-baseline-v1.json `
  --out ..\artifacts\world-chain\b3-rescore-v1-j3.json
node scripts/run-world-b3.mjs --rescore ..\artifacts\world-chain\b3-baseline-v2.json `
  --out ..\artifacts\world-chain\b3-rescore-v2-j3.json
```
## 七、复跑

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
