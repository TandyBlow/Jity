# 浏览器模型端口契约与 v6 接入缺口（C/D 组件设计依据）

日期：2026-10-29。分支 `world-browser`（代码引用基于提交 `0b488bb`）。
证据基线：**冻结的 v6 归档** `artifacts/world-chain/b3-baseline-v6.json`
（judge v5，`12be98c8…`，提交 `33b95b3`）与 `b3-run-db-v6/`。本文只整理
现有代码与归档，不引入新运行、不改提示词/判据/冻结报告。

逐条标注口径：

- 【现状】= 当前代码/归档里的真实行为（可追溯到 file:line 或 v6 证据）。
- 【设计】= 协议/设计文档已定的要求（§ 引用为 design/world-protocol 与
  browser-world-state-workflow.md 的既有结论）。
- 【假设】= 尚未被任何真实运行验证、组件设计不得当作既定事实的项。

---

## 〇、总览：一个接口、两个现实实现、四层输出

**接口**【设计】：`WorldModelPort.generate(task, key, input): Promise<Json>`
（`frontend/src/lib/world-engine/controller.ts:22`）。任务全集 `ModelTask =
action | targets | reaction | results | updates | continuation | narration |
initial | time | pointPlan`（`schedule.ts:13`）。决策由纯调度器产生
（`Decision = transport | read_working_state | model | await_command | stop`，
`schedule.ts:257-262`），驱动器执行 `step()` 时对 `kind:'model'` 调端口、
把输出经 `consumeModelOutput` 适配进内存（`controller.ts:430-463`）。跨端口
边界一律纯 JSON（`schedule.ts:281-284 asJson` 深拷贝；typed 快照不过桥）。

**两个现实实现**【现状】：

1. **B3 harness 端口**（`frontend/scripts/run-world-b3.mjs:507-718`，
   `H.b3Port`）——唯一有真实模型结算证据的实现（wllama + Qwen3-0.6B +
   json_schema 受控解码）。v6 两场景共 54 次结算模型调用 + 9 次程序任务
   + 10 段叙事全部走它。
2. **产品规则端口**（`frontend/src/lib/world-engine/runtime/rule-session.ts:197-249`）
   ——页面/会话在用的实现：结算六任务全部走规则权威（零模型），
   `continuation` 固定 `handback`，只有 `narration` 走真实模型（模板 +
   可选润色器 + 事实门）。另有通用 `RuntimeWorldModelPort`
   （`runtime/model-port.ts:50-112`，encode → 串行队列 → decode/validate）：
   其 encode 已是**真实提示词构造器**——调用 `prompts.ts` 的
   `buildTaskPrompt`，支持 `focused` 投影与 `committedReads`（`:45-48,71`；
   文件头「encode 是占位」的注释已过时，以代码为准）——**未接任何产品路径**。

**四层输出**（涉及分层的条目按此标注；B3 归档直接记录第 1 层）：

1. **归档层**：`modelTasks[].raw` = 受控解码的**原样文本**——唯一的原始
   层；`modelTasks[].output` = JSON 解析值经端口**就地回填后**的形态
   （回填直接改写解析对象、对象按引用随记录落盘，`b3.calls.push` 在
   `run-world-b3.mjs:367`），回填明细另记 `backfills`。例：v6 chain
   round_37 `raw` 里是 `"nextRoundId":"pending"`，`output` 已是
   `"round_41"`。读模型原始行为必须看 `raw`，读回填必须看 `backfills`。
2. **端口返回值**：任务分支对解析值校验/归一/裁剪后 `generate()` 实际
   返回给驱动器的值。
3. **驱动内存**：`consumeModelOutput`/调度器适配后的内存形态
   （`lastModel`/`lastTargets`/`lastResults`/`continuation` 等）。
4. **wire**：提交服务端的数据（`types.ts:75-108` RequestMap）。注意
   归档 `wire` 只存 HTTP ≥400 的错误回包（`run-world-b3.mjs:289-293`），
   正常写操作只见于 `ops` 序列——「X 上 wire」的归档证据仅在出错时存在，
   正常路径是代码推断。

两个易混实例（v6 归档可验）：**reaction** 归档 `output` 是 `{text}`
对象，端口返回的是纯字符串（`run-world-b3.mjs:596 return out.text`，
调度器按字符串校验，`schedule.ts:879`）；**continuation** 归档保留完整
判断文本（含 plannedAction/protagonistRelevance 与回填记录），端口返回
值已裁剪为 wire 形状的 Conclusion，`memory.continuation` 与 conclude
wire 都只见裁剪后字段。

---

## 一、实际输入输出表

公共机制（全部任务共用）：

- **调用计数**：`memory.budget.used++` 发生在 `consumeModelOutput`
  （`controller.ts:431`）——计的是控制器消费的 model 决策产出，**含程序
  pointPlan/time**（它们也经端口），不是 HTTP 调用数（v6 复核口径）。
- **预算门**：`STATE_COMPUTATION_TASKS = action/targets/reaction/results/
  updates/continuation`（`schedule.ts:266`）受 `modelBlocked` 约束
  （`schedule.ts:427-443`）：`used >= max` 时发 `checkpoint_pause` 并停在
  `local_budget_pause`。**narration 不受预算门**（`schedule.ts:428-431`）。
- **暂停/gate 门**：`scheduleNext` 里 gate（`:465`）与 paused（`:466`）
  检查位于相位分支之前——pointPlan/time 虽不受预算门限制，**同样被
  暂停/gate 挡住**（它们的决策只会在未暂停分支里到达）；唯一的例外是
  **narration**：`narrationDecision` 在 `:459-460` 先于 gate/paused 检查
  执行——叙事管线必须穿过暂停运行（T05）。
- **重试**：模型调用本身零重试——端口 throw 直接穿透 `step()`（见第二节）。
  传输层重试只针对 HTTP 超时/`request_in_progress`（同 requestId，默认
  3 次，`controller.ts:397-406`）。

### 1.1 action（行动判断）

| 项 | 内容 |
| --- | --- |
| 调度位置 | `selectActorDecision`（`schedule.ts:761-768`），按冻结顺序逐人判断（`nextActor`，`schedule.ts:696-709`；被后序点覆盖的槽位延后，已处理槽位不重问） |
| 输入 | `{ actor, advance: { inputText, intentStatus }, workingState }`；玩家文本身份绑定当前 advance（`actionAdvance`，`schedule.ts:715-720`：服务端 activeInput 或驱动器自己 start_advance 的原文，二者不跨 advance 泄漏） |
| 输出形状 | 四层：归档 `{ kind:'act', text }`（skip 原样带 `text:''`）→ 返回归一化（skip 去 text，`run-world-b3.mjs:540`）→ 内存 `lastModel.output` → wire `checkpoint_discover_group` 的 actionText / `checkpoint_record_skip`（无模型文本）。B3 schema enum 钉死、maxTokens 128（`:536-537`） |
| 校验 | 调度器：非 `act`/`skip` 或 act 空 text 直接 throw（`schedule.ts:744`）；B3 判据：目标句 `goal/plan is not an action` fail（`b3-judges.mjs:194`）、已消费输入后主角自发动 review（`:200`） |
| 程序回填 | 无改写；`{kind:'skip',text:''}` 归一化为 `{kind:'skip'}`（B3 `:540`） |
| wire 消费 | act → `checkpoint_discover_group`（actionText=模型文本，groupId 程序槽位 `group:<actor>`）；skip → `checkpoint_record_skip`（`schedule.ts:733-753`） |
| v6 证据 | 两场景 action 任务零判分错误（错误族仅 continuation/results/reaction，见第三节） |

【设计】只有主角受玩家命令约束；consumed 只是「输入机会已处理」，其他人物
按自身任务/个性判断（B3 提示词 `run-world-b3.mjs:527-535` 即按此写）。

### 1.2 targets（目标声明）

| 项 | 内容 |
| --- | --- |
| 调度位置 | `buildDecision`（`schedule.ts:891-895`），组内 DFS 的来源帧扩展前 |
| 输入 | `{ sourceId, actionText, workingState }` |
| 输出形状 | 四层：归档=模型原始 `{targets:[{targetId}]}` 列表 → 返回=过滤后同形（§校验行）→ 内存 `lastTargets {sourceId, targets}`（独立于 `lastModel` 存放——allocate 桥成功会清 `lastModel`，不能丢声明集，`controller.ts:449-455`）→ wire `checkpoint_extend_group` targets 带 triggerKey（键模型不可见）。产品 codec 形状，maxTokens 96（B3 `:555-558`） |
| 校验 | 调度器：必须带 targets 数组否则 throw（`controller.ts:449-455`）；B3 端口：畸形项记 `target_malformed`（`run-world-b3.mjs:564`）、不在名册记 `target_dropped_not_in_roster`（`:569`），两类均**丢弃并记 backfill**；自指/重复目标是语义错误**记 validationError 并 throw**，不静默改写冻结目标集（`:574-582`） |
| 程序回填 | 触发键与骰规则**模型不可见**：`triggerSlotKey = trigger:foldIdentity(groupId, sourceId, targetId)` 程序分配（§9.3，`schedule.ts:89-96`）；骰规则为程序常量 `PROGRAM_ROLL_RULE = reaction-d20-v1, target 11`（`schedule.ts:26`） |
| wire 消费 | 缺失 trigger 槽先 `allocate_ids`（`schedule.ts:845-860`），再 `checkpoint_extend_group targets:[{targetId, triggerKey}]`；roll 由 `create_rolls`（程序发起，ASCII 序，`controller.ts:66-70`） |
| v6 证据 | targets 未进错误族（漏选在探针层有历史记录，v6 场景零命中） |

### 1.3 reaction（被卷入者的反应）

| 项 | 内容 |
| --- | --- |
| 调度位置 | `buildDecision` DFS 等待分支（`schedule.ts:900-906`）：准入目标先完成整棵子树再滚下一个兄弟（T02-el） |
| 输入 | `{ sourceId, sourceActionText, memberId, rollId, workingState }`（读发起者的具体威胁） |
| 输出形状 | 模型原始输出（归档）`{text:"<反应行动>"}`；**端口返回纯字符串** `out.text`（`run-world-b3.mjs:596`）；B3 schema `{text}`、≤30 字、maxTokens 96（`:588-593`）。驱动内存 `lastModel.output` 即该字符串（调度器按 `typeof !== 'string'` 校验，`schedule.ts:879`） |
| 校验 | 调度器：非字符串 throw（`schedule.ts:879`）；必须绑定同一个 admitted roll（first-fit 同一威胁，`:871-877`）；B3 判据：与来源行动逐字/结构重复 → `reaction copies the source action` fail（`b3-judges.mjs:140,244`） |
| 程序回填 | 无；rollRefs 由程序从 admitted 条目构造 |
| wire 消费 | `checkpoint_extend_group admittedMember:{memberId, actionText, rollRefs}`（`schedule.ts:880-889`）；接受成员后其槽位标记已处理、源帧压栈（`controller.ts:742-758`） |
| v6 证据 | chain `reaction:person_a` 原始输出与来源行动**逐字相同**（`推开门厅深处的重门，示意同伴到门边一起撑住。`）→ fail，n=1 |

### 1.4 results（共同结算结果）

| 项 | 内容 |
| --- | --- |
| 调度位置 | `settleDecision`（`schedule.ts:972-993`），组关闭后 |
| 输入 | `{ groupId, members: [{ memberId, actionText, rollRefs（含未准入 roll） }], workingState }`——冻结行动与全部骰点判定来自 `memory.groupActions`（§7.1；`controller.ts:722-774` 维护）；**成员缺失时明确停止** `frozen_actions_missing`，不用空列表结算（`schedule.ts:979-982`） |
| 输出形状 | 四层同形：归档=返回=内存均为 `Record<memberId, string>`（每成员一句第三人称结算，无回填改写）；wire=`checkpoint_stage_unit` 的 `results` 原样。B3 schema 恰好含全部成员键、缺键 throw（`run-world-b3.mjs:608-614`）；maxTokens 128 |
| 校验 | B3 判据（`b3-judges.mjs:295-348`）：逐成员归属、骰点一致（未准入写成成功 / 准入写成失败 = fail，带 `[dice mismatch]`）、可追溯性、**无骰点证据的裸判定 = review（不计通过）** |
| 程序回填 | 无（结果文本逐字进 wire） |
| wire 消费 | `checkpoint_stage_unit { groupId, candidates, results }`（`schedule.ts:963-970`）——candidates 由 updates 输出组装（见 1.5），results 原样 |
| v6 证据 | 裸判定 review ×10（action group_29–34 六条、chain group_51–54 四条）；dice mismatch fail ×1（chain group_39：person_a roll 11/11 准入被写成「没有成功」，同组 person_c 裸「没有成功」） |

### 1.5 updates（世界状态更新，六阶段契约）

| 项 | 内容 |
| --- | --- |
| 调度位置 | `settleDecision` 尾部 / `updatesModelCall`（`schedule.ts:928-938,994-997`）；阶段切分由场景声明（`memory.updatesStages`，空 = 单次合并调用；阶段序列跨恢复保留，`controller.ts:185`） |
| 输入 | 组模式 `{ groupId, mode:'group', results, stage?, workingState }` / 空点模式 `{ mode:'time_scan', workingState }`；后序阶段**读前一阶段已应用的状态**（§6.3，stage 间经 `preview_point` 折入，`controller.ts:467-597` 含前向引用拆分应用） |
| 输出形状 | 合并模式 `UpdatesCall[]`（stage 顺序 position→appearance→tasks→subtasks→personality→sanity）；切分模式单 `{stage, changes}`；无变化输出 `[]` / `{stage,changes:{}}`；B3 schema 用 **enum 钉死 stage 名**（复核轮 19 修复，`run-world-b3.mjs:500-505`）、maxTokens 384。四层：归档=返回 `UpdatesCall[]`/单 `{stage,changes}` → 内存 `updatesCalls`（合并后 Δ）→ wire=`checkpoint_stage_unit` 的 `candidates`——**change/task 草稿 id 已被程序重写为分配 id**（见程序回填行），草稿 id 不上 wire |
| 校验 | 端口 audit：阶段顺序/字段白名单/名册/sanity∈[0,100]/tasksAchieved 归属（`run-world-b3.mjs:400-457`）；调度器 `checkUpdatesStages` 悬挂引用守卫 → stop `dangling_updates_refs`（`schedule.ts:387-400`）；判据：因果链（无新任务达成不得个性、无个性不得理智）、>30 理智跳变 review |
| 程序回填 | **change/task 身份全程序所有**：模型草稿 id 在 stage 发送前经 `allocate_ids` 重写（`collectCandidateIdentityWork`，`controller.ts:305-366`；槽键 fold 组+实体+草稿 id，重试零重分配）；恢复的已确认单元逐字 stage、重写被显式禁止（`:313-316`） |
| wire 消费 | `checkpoint_stage_unit` / `checkpoint_stage_time_scan`（coverage 规则：taskCoverage=全名册，personalityCoverage 有达成才全名册，positions 只来自 positionSet——`schedule.ts:1037-1059`）→ `preview_point` 共同投影 → `commit_point` |
| v6 证据 | updates 零判分错误（v5/v6 均全解析）；但 v6 每组样本量小、多数输出为 `[]`【假设：六阶段非平凡产出仍是 v4 失败族，未被 v6 复验】 |

### 1.6 continuation（继续推进判断）

| 项 | 内容 |
| --- | --- |
| 调度位置 | `continuationDecision`（`schedule.ts:590-622`），`assess_continuation` 相位 |
| 输入 | `{ round, head, workingState, roundChanges }`（§7.1 主角/当前世界/本轮变化；roundChanges 是本驱动器提交点 Δ 按序累计，`controller.ts:807-814`）；**依据缺失明确停止** `continuation_context_missing`，不得无据调模型（`schedule.ts:605-610`） |
| 输出形状 | 模型原始输出（归档，四层之第 1 层）：`{kind:'continue' \| 'handback', candidateCharacterIds, nextRoundId, plannedAction, protagonistRelevance, cancelReason}`，maxTokens 160（`run-world-b3.mjs:657-662`）；**端口返回值已裁剪**为 Conclusion `{kind, closedBy:'model', cancelReason:null, candidateCharacterIds, nextRoundId}`（`continue` 分支，`:717-723`）——归档与返回值不同（§〇 实例二） |
| 校验 | B3 判据：continue 必须 `plannedAction` 非空且**非目标句**（`isGoalSentence` → fail，`b3-judges.mjs:524-525`）+ 主角关联；handback 却带行动/关联 → review（`:510`） |
| 程序回填 | **`candidateCharacterIds` 是模型决策**：合法角色逐字保留进端口返回值与 Conclusion（v6 两名册场景模型选 `[person_a]` 即原样保留——归档 `output` 可证；归档 `wire` 只存错误回包、正常 conclude 不在其中，「上 wire」为代码路径推断）；程序只丢弃不在名册的非法项（记 backfill），**仅当过滤后为空**才回填整名册（`run-world-b3.mjs:695-704`）。`nextRoundId` 是程序分配：模型占位 `pending` 被预分配队列真 id 替换（backfill 记录在案；队列空 = `b3 next round id budget exhausted`）（`:705-710`）。B3 停止界：第 5 轮仍 continue 保存原始判断、**不回填第 6 轮身份、不提交 conclude**（`d4db44b`） |
| wire 消费 | `round_conclusion_conclude`，Conclusion **只含 kind/closedBy/cancelReason/candidates/nextRoundId**——`plannedAction/protagonistRelevance` 是判断产物不上 wire（§8.1，端口裁剪在 `run-world-b3.mjs:717-723`，wire 类型 `types.ts:37`）；conclude 回执 `{kind, roundId, nextRoundId}`（`types.ts:126`），confirmed continue 触发程序身份 sink（`controller.ts:276-282`） |
| v6 证据 | **10/10 判全为目标句**（温度 0 下确定性复现；例：raw `plannedAction:"林川需要观察盒子的状态，以确保守门任务的完成"`，同调用 `nextRoundId:"pending"` 被程序回填为 `round_41`）。服务端只收到合法 continue（裁剪后），**质量失败不影响 wire**——但 §8.1 两条件判断的实际质量因此完全不可验收 |

【现状】产品路径 `continuation` 固定返回 handback（`rule-session.ts:252`）——
页面上任何轮都以交还玩家收尾，自动轮链从未在产品路径打开。

### 1.7 narration（叙事）

| 项 | 内容 |
| --- | --- |
| 调度位置 | `narrationDecision`（`schedule.ts:500-562`，优先于一切相位）：claim → 目标点 get_state（取回 Δ 原始记录）→ 前驱 get_state → 组装 → 模型 → submit；**读能力不完整即停止**（`readIncomplete`/`narration_read_incomplete`，缺字段不得默认空 Δ） |
| 输入 | `{ pointId, before, delta:{timeAdvance, entityDeltas}, after, perspective }`（§7.1 Sₜ₋₁/Δₜ/Sₜ/视角，`assembleNarrationInput`，`schedule.ts:134-146`） |
| 输出形状 | 端口返回文本或 null（null = submit `outcome:'failed', failureReason:'model_failed'`，`schedule.ts:513-531`）；润色器 maxTokens 96、attempt1 温度 0 / attempt2 温度 0.7（`narration-polisher.ts:62-67`）。**归档来源不同于其它任务**：narration 不走 `b3.complete`、不在 `modelTasks` 里——归档字段是 `scenes[].narration[]`（`run-world-b3.mjs:1123,1282` 随场景返回），条目内才有 `attempts[]/completion/facts`（`narrationLog` 只是 harness 变量名） |
| 校验 | 产品与 B3 同一门：`narrateFromReads`（`rule-session.ts:99-143`）——模板为底，润色候选过 `selectFactNarration` 逐句事实门，**门拒后重生一次、仍败回模板**（§8.2）。重生实现的精确口径：attempt 2 是**同提示词、温度 0→0.7 的重采样**——`attempt.previous` 随类型传递但**未注入提示词**（更正文本会被小模型逐字复读，实测否定注入，`narration-polisher.ts:58-60`）；注入反馈属更强模型的待启用项。**判分层没有叙事事实复判**：`b3-judges.mjs:683-684` 对 `case 'narration'` 直接 break，归档判分只统计 polishFallback/未 polished 事件（`:691-693`）——事实门只存在于运行内 |
| 程序回填 | 模板是程序渲染；编号清单提示词把任务压到逐字复制形态（`narration-polisher.ts:53-57`） |
| wire 消费 | `narration_claim` / `narration_submit`（三元组 claimToken+generation+issuedAtEpochMilli；租约/围栏变化即弃 claim 重取，`controller.ts:660-668,672-677`） |
| v6 证据 | 两场景各 5 段、零回退、completion 证据各 5 条（逐调用回调——实例级回调会被模块缓存吞掉，整链验收 v2 教训，`rule-session.ts:62-64`） |

【现状】页面已接润色器（`page.tsx:145` 懒加载包装）；**B3 判分门（b3-judges）
未接页面**——已登记的未完成边界。

### 1.8 initial / time / pointPlan（程序供给，无模型证据）

| 任务 | 现状 |
| --- | --- |
| initial | 调度器在世界为空时可发 `{kind:'model', task:'initial', input:null}` → InitialTemplate → `create_world`（`schedule.ts:451-455`）。【现状】B3 明确出界（端口 throw，`run-world-b3.mjs:519`）；页面创建会话时以 `defaultInitialTemplate()` 播种（`page.tsx:306`；模板构造器在 `world-defaults.ts:28`，`rule-session.ts:189` 只是克隆 `options.initial`）。**两条现实路径都从未调模型 initial。** |
| time | 仅 T08 场景 prepareSuccessor 路径（`schedule.ts:799-813`），输入 `{head, workingState}`，输出 TimeAdvance → `checkpoint_prepare_successor`。【现状】B3 用程序常量 `instant 0s`（`:515-518`，source 记 `program`）；无真实模型证据。 |
| pointPlan | `idlePointDecision`（`schedule.ts:635-650`）：输入 `{round, head}`，输出 `PlannedPoint[]`（点切分 + actorIds 声明 + timeAdvance）；计划省略的槽位仍被逐人判断（§6.1，不是跳过）；continue 后 plan 清零、下一轮需新计划（`controller.ts:898-900`）。【现状】B3 = 程序预分配队列 shift（耗尽 throw）；产品 = 单点固定计划（全部角色、1 秒，`rule-session.ts:200-201`）。**无模型 pointPlan 证据；多轮/多点规划能力未测。** |

---

## 二、失败／取消／恢复语义（真实代码路径）

### 2.1 模型调用失败 → 终止，不重试

【现状】端口 throw（解析失败、schema 校验失败、语义校验 throw、引擎错误）
从 `step()` 的 `case 'model'` 直接穿透 `driver.run()`：

- B3 harness：场景 catch 记 `runError='model port threw'`（`run-world-b3.mjs:1084-1087`），失败即交付，不换候选。部分例外：narration 的**润色失败**（门拒、润色器异常）在端口内部被 `narrateFromReads` 吸收——重生一次后回模板，对驱动器仍是成功文本；但**模板回退只覆盖润色失败**——缺读（`narration_requires_saved_point_read` / 前驱缺失，`rule-session.ts:243-247`）、谱系或投影校验失败仍会 throw 并走本行终止路径。
- 产品：`WorldSession` catch 后返回 `{kind:'error', detail}` 并收尾本轮循环（`session.ts:219-225`）；不重试、不改写。
- 引擎层：wllama complete 110s 超时（B3 配置）/abort → 错误上抛；取消信号原生透传（`wllama-engine.ts`）。

### 2.2 传输层失败 → 按 18 码目录路由

【现状】HTTP 超时 15s（默认，`http-transport.ts:10`）→ `WorldTimeoutError`
→ `call()` 以**同一 requestId 与原载荷**重试，至多 `retryLimit`（默认 3）→
`retry limit exceeded on <op> (timeout)`（`controller.ts:397-406`）。
服务端 ErrorResponse 对照冻结目录校验后按 clientAction 路由
（`errorReaction`，`schedule.ts:311-329`；`applyErrorFollowup`，
`controller.ts:599-654`）：

| clientAction | 后继 | 终态？ |
| --- | --- | --- |
| retry_same_request | 原请求重发（唯一复用 requestId 的路径） | 否 |
| reacquire_lease | `lease_acquire` 后续跑 | 否 |
| refresh_context | `get_context` 采纳 + 丢弃全部 narration claim | 否 |
| wait_narration / regenerate_narration | `finish_own_narration`（弃 claim、留装配、重生成） | 否 |
| resolve_gate | await `resolve_gate` | 等待态 |
| pause | `checkpoint_pause` 后 stop `pause_and_stop:<code>` | 是 |
| fix_request / none | stop `fix_request:<code>` | 是 |

【现状】在途 split-updates 的 preview 拒绝是例外路径：**至多一次刷新 + 一次
重试**；刷新后核对工作基线未迁移（head 点已变即 stop
`updates_preview_baseline_moved`，`controller.ts:577-582`），仍拒即 stop
`updates_preview_refused:<code>`（`:584`）——候选性拒绝不进无限自愈循环。

### 2.3 预算与步数停止（保险语义）

【现状】四层，v6 仅第 4 层按设计触发（used 38/33，上限 240；step 400 未触及）：

1. 控制器任务预算（`memory.budget`，v6=240）：触顶 → `checkpoint_pause` →
   await `local_budget_pause`（`schedule.ts:433-441,466`）；外部命令
   `budget_exhausted` 走同一操作，localPause 归属规则在 `controller.ts:912-917`；`resume` 清除。
2. 驱动器步数 `driver.run(limit)`：v6=400 → `{kind:'error', detail:'driver
   step limit exceeded'}`（`controller.ts:236-242`）。v5 即此停止（80 步）。
3. 会话步数：`WorldSession` 循环 500 步 → `session step limit exceeded`
   （`session.ts:211-221`）。
4. B3 轮预算（harness 层，v6 主停止界）：第 5 轮 continue 保存原始判断、
   不分配第 6 轮、不提交 conclude，场景记 `round_budget_exhausted`；
   cancel 单列 cleanup（`run-world-b3.mjs` 端口 675-689 段 + 场景捕获）。

### 2.4 cancel 的作用范围与两种取消入口

【现状】`cancel` 命令 → `round_conclusion_cancel`（`controller.ts:226-233`）；
成功后 `clearRoundWork()`（`:909-911,930-939`）：清空未提交候选（staged/
stagedTimeScan/restoredUnit）、组冻结行动、continuation、roundChanges、
narration、plan——**已提交点与已分配身份（ids/roundAllocations/allocatedKeys）
不清**；服务端废弃开启中的 advance 并返回 `abandonedGroupIds`
（`types.ts:127`）。B3 场景停止后的清理 cancel 只关 advance（v6：round_20 /
round_44），**单列在 `cleanup` 字段，不计模型 handback**。

**两种取消入口必须区分**【现状】：

1. **`deliver(cancel)`（协议取消）**：命令只在其操作真正执行时被消费——
   送达发生在生成/请求在途期间时会**存活到当前 step 完成**，下一步才作为
   `round_conclusion_cancel` 发出（命令消费规则 `controller.ts:250-253,271-274`；
   捕获命令与在途完成之间送达的命令不被吞）。当前生成不受打断、其输出
   可能已被消费——取消不回滚已发生的 step。
2. **`WorldSession.stop()`（中止）**：提升 epoch、终态隔离——在途交换被
   abort/隔离、心跳停止、late settle 不复活（`session.ts:14-15,99-100,239-251`）。
   这是接管/关闭路径，不是协议轮取消。

### 2.5 recover 的三条铁律

【现状】`recover()` 只接受全新驱动器（`hasStepped`/未决请求/已有世界即拒绝，
`controller.ts:168-174`）：

1. **丢弃全部未确认输出**：`bootstrapRecovery` 用全新 `initialMemory` 播种
   （仅保留 requestId 前缀、budget.max、updatesStages），只采纳服务端已验证
   快照——崩溃前的模型输出/未提交候选一律不复活（`:176-198`）。
2. **已确认工作逐字恢复**：`recoverPoint`（`recovery.ts:48ff`）要求基线相等、
   payload available、组集合完整、成员一致；已 stage 单元以**原始候选**恢复
   为 `restoredUnit`，逐字重 stage、禁止重写身份——「从不要求模型重建已确认
   的文本/候选/骰点」（文件头注释）。恢复中断一律 `RecoveryStopped`
   （明确原因），绝不半恢复。
3. **未确认的未来计划不重建**：恢复点重提交后 `plan=null/planIndex=0`，
   由新一轮服务端游标重新规划（`controller.ts:837-842`）；successor 绑定在
   前驱重提交后恢复（`:827-836`）；`recoveryBarrier` sticky。

围栏/租约：任何 fenceEpoch 变化（含失去租约）立即作废 narration claim
（`controller.ts:660-668`）；`stop()`/失租是终态且隔离在途交换
（`session.ts:14-15,239-251`）。

程序身份 sink（①b）：confirmed continue 恰好触发一次，按 nextRoundId 与
服务端 order 分配点/组身份，**delta 折入**（键合并、并集，非整包替换——
复核 20-2）；未注册 sink 仅在预置分配路径合法，否则记 sticky
`round_identity_sink_missing:<roundId>`，后续 step 撞服务端对重用 id 的
产品拒绝（`controller.ts:110-158,276-282`）。

---

## 三、v6 接入缺口清单

逐项：证据（代码/归档）→ 归类 → 影响。归类轴：**端口**（提示词/适配/校验
层）、**harness**（验收脚本）、**产品接线**（页面/会话/驱动）、**模型能力**
（0.6B 模型本身）。

| # | 缺口 | 证据 | 归类 |
| --- | --- | --- | --- |
| G1 | **continuation 目标句 10/10**：plannedAction 全部是「需要/确保…」句式，judge 全 fail；§8.1 两条件判断质量完全不可验收 | v6 `roundBudget.exhausted.judgment` ×2 + 判分 10 条（`b3-judges.mjs:525`）；`artifacts/world-chain/README.md` §6.6.2 | **模型能力**为主；端口无生成前校验（目标句照常裁剪上 wire）——是否加端口内拒绝/重生属设计待决（见四.2） |
| G2 | **results 裸判定 ×10 review + 骰点不符 ×1 fail**：无骰证据的裸「没有成功」按设计只给 review；准入写成失败是硬错（group_39，roll 11/11） | v6 judged pendingReview 10 条 + `semanticErrors[1]`；判据 `b3-judges.mjs:319-335`；提示词已明示规则（`run-world-b3.mjs:604-607`） | **模型能力**（无视输入中的骰点证据）；端口/调度器在 stage_unit 前**没有**程序侧骰点一致性预检【现状】——是否补预检属设计待决 |
| G3 | **reaction 复述 ×1 fail**：原始输出与来源行动逐字相同 | v6 chain `reaction:person_a` raw；判据 `b3-judges.mjs:244` | **模型能力**；n=1，样本极小【假设：发生率未知】 |
| G4 | **产品结算路径零模型**：页面/RuleWorldSession 六任务全走规则权威（action=parseRuleCommand、未解析即 skip；targets 恒空；results=adjudicate；updates=deltas；continuation 恒 handback） | `rule-session.ts:197-249` | **产品接线**：B3 模型端口没有任何产品路径；`RuntimeWorldModelPort`（encode 已是真实 `buildTaskPrompt`，含 focused 投影）也未接任何产品路径 |
| G5 | **产品 continue 路径无身份 sink**：`setRoundIdentitySink` 仅 B3 两场景与回归脚本注册，产品运行时未注册 | grep 全仓：`controller.ts:122`（定义）、`round-identity-regress.mjs:54,86`、`run-world-b3.mjs:1068,1233`，产品运行代码零调用（仅测试 `controller.test.ts:1481,1499,1511,1537` 四处） | **产品接线**：当前因 G4（恒 handback）不可达；一旦接模型 continuation，continue 即记 `round_identity_sink_missing` 并在下一步撞服务端重用 id 拒绝 |
| G6 | **initial/time/pointPlan 无模型证据**：两条现实路径均程序/规则供给（§1.8） | `run-world-b3.mjs:509-518`、`rule-session.ts:189,200-201` | **端口+harness**：组件设计必须显式决定归属；多点规划能力（B3 预分配 5 点 vs 产品单点）未测【假设】 |
| G7 | **判分门未接页面**：narration 页面走 checkFactNarration 放行门 + 模板；B3 判分（b3-judges）只在 harness | 已登记边界（world-chain README 环境节、§6.7） | **产品接线** |
| G8 | **updates 非平凡产出未复验**：v6 updates 零错误但样本小、多数 `[]`；六阶段仪式化空 changes 是 v4 失败族 | v6 `modelTasks[task=updates]`（chain 5 次：group_39/51–54，输出 `[]` 为主）；v4 记录 | **模型能力**【假设：当前 n 不足以定性】 |

**程序职责现状归属**（组件不得假设这些可以拿走，见四.1）：骰规则与触发键
（程序常量/程序槽键，§9.3）、全部身份分配（allocate_ids + continue sink +
stage 候选身份重写）、服务端权威状态应用（客户端无 apply）、conclude 裁剪
（拟行动不上 wire）、恢复逐字性、§8.1 判断产物与 wire 结论的分离。

---

## 四、交给 C/D 的约束与待决问题

### 4.1 组件必须遵守的约束【设计，来源均为已冻结契约/已验收代码】

1. **接口形状**：实现 `WorldModelPort.generate(task, key, input): Promise<Json>`
   （或超集 `RuntimePortLike` + AbortSignal）。输入是纯 JSON 的决策 input
   （§1 各表）；输出必须是该任务契约形状——结构不符宁可 throw（驱动器/
   会话按 2.1 终止），**禁止静默改写**（B3 对 targets 自指/重复的处理即
   先例：validationError + throw，不换答案）。
2. **程序职责不可下放**：触发键/骰规则（`PROGRAM_ROLL_RULE`）、身份分配
   （allocate_ids/continue sink/候选身份重写）、恢复逐字性、conclude 裁剪
   （拟行动与关联不上 wire，`types.ts:37`）、判据与记账（`review` 永不计
   通过）。组件在这些字段上没有话语权：模型只声明语义（行动文本/目标
   id/结果句/更新 Δ/continue-hangback 判断），身份与规则由程序回填或裁剪。
3. **不漂白失败**：解析/校验失败上抛；「失败即交付」是 B3 的交付纪律
   （`run-world-b3.mjs` 文件头），组件层不得把失败替换为脚本候选再报成功。
4. **上下文输入**：各任务 input 已含其所需（§1 表）；组件不得要求额外
   读取世界状态——需要新上下文属契约变更，须走协议层。【现状】
   `focused` 收窄视图只存在于 narration（`narration-polisher.ts:48-57`）；
   结算任务的聚焦投影（`focused-input.ts`）在 eval 层有、生产端口未用
   【假设：聚焦输入对结算任务的收益未测】。
5. **失败报告**：端口 throw → 驱动器/会话 error 终态（2.1）；叙事例外
   （重生一次 → 模板兜底，§8.2）。若组件需要「可重试的语义失败」通道
   （如目标句拒绝后原模型重问），这是**新机制**，须与驱动器的零重试纪律
   和预算记账（每次消费计 1）一起设计——见待决 Q2。
6. **长生成与租约**：模型生成期间租约靠心跳维持（`WorldSession` 双心跳：
   心跳走 transport、与推理并发）。**B3 也有心跳**——探针段创建的
   bootstrap `RuleWorldSession`（`run-world-b3.mjs:810`）全程未停止，
   其心跳在两场景期间持续续租（v6 归档：action/chain 场景 ops 各记录
   **7 次 `lease_renew`**）。持久服务默认 lease TTL = **120 秒**
   （服务检出 A 树 `dd345b8`：`backend/app/database/world_store.py:38`
   `lease_ttl=120_000`、`backend/app/services/world/authority.py:12`
   `LEASE_TTL_MILLI`——这两个文件不在 `world-browser` 树，按服务检出
   引用；1h TTL 只属于非持久 fixture 的 `control.py:67`，持久路径被
   `initialize_world` 覆盖）。组件的 110s 级生成超时相对 120s TTL 只有
   一个心跳间隔的余量【现状：v6 未出现续租失败；生成与心跳竞争的边界
   未做压力组合】【假设】。

### 4.2 待决问题（需总指挥/C/D 方案决定，B 不预设答案）

- **Q1 组件粒度**：每任务独立小模型头（N2/N4/U3/U6 试验路线）还是共享
  骨干 + 任务头？§1 表显示各任务输入/输出/校验高度异构（字符串输出
  vs 结构 Δ vs 二分类），且程序回填的密度不同。
- **Q2 语义失败通道**：continuation 目标句（G1）在生成侧可判（`isGoalSentence`
  是确定性函数）——组件是否应在端口内「拒绝并重问」（预算怎么记、循环
  上限多少、失败形态如何上报 judge），还是保持现状（照常裁剪上 wire、
  只在判分层记 fail）？
- **Q3 results 的程序预检**：骰点一致性（G2 的 fail 半边）是确定性规则——
  是否在 `checkpoint_stage_unit` 前加程序侧预检（拒绝比事后判分便宜，
  但改变了「失败即交付」的证据形态）？裸判定（review 半边）没有确定性
  规则，只能靠模型给出带骰证据的表述——组件提示词/微调是否以
  「逐成员骰点引用」为输出契约？
- **Q4 initial/time/pointPlan 归属**（G6）：维持程序供给，还是进入组件
  范围？多点规划是否需要（产品单点 vs B3 五点）。
- **Q5 接线顺序**：G4/G5（产品结算模型化 + sink 注册）在 B 的接入批次里
  谁先谁后——sink 注册不依赖模型，可先行；模型 continuation 一旦接入，
  G5 从不可达变阻断。
- **Q6 判据复用**：N4 先例（评估判据复用语料门控识别器）提示组件验收
  直接复用 b3-judges 同源规则；判据 hash 需与运行记录一起冻结（v6 基线
  口径）。**范围注意**：b3-judges 只覆盖六个结算任务——`case
  'narration'` 直接 break（`b3-judges.mjs:683-684`），叙事侧没有可复用
  的判分层，只有运行内事实门（§1.7）；叙事组件的验收口径需另行确定。

### 4.3 明确不在本批范围

不启动新模型对照、产品 handback 闭环、20 次输入验收或组件接入；不修改
冻结报告/DB/提示词/判据。C/D 方案与候选验证成熟后，接入按总指挥调度
回 B 批次执行。

---

## 附：证据索引

- 代码：`frontend/src/lib/world-engine/{types,schedule,controller,recovery,
  transport,http-transport}.ts`、`runtime/{rule-session,session,model-port,
  wllama-engine}.ts`、`frontend/src/app/world/{page.tsx,narration-polisher.ts}`、
  `frontend/scripts/{run-world-b3,b3-judges}.mjs`（行号见文中，基于
  `world-browser@0b488bb`）。
- 冻结证据：`artifacts/world-chain/b3-baseline-v6.json`（judge v5
  `12be98c8…`）+ `b3-run-db-v6/`（提交 `33b95b3`）；登记与读法见
  `artifacts/world-chain/README.md` §6.6.2。
- 停止界：`d4db44b`（固定 5 轮 + 保险标记）、审查方桩验证与口径修正
  `102f710`、登记修正 `0b488bb`。
