# 组件 I/O 字段说明与 commit-turn 设计稿（v3）

状态：v3 草案（2026-10-11 三轮评审修订，待评审）。v2 → v3 变更：
幂等摘要补 playerAction 与存档、turn_submissions 表定案且幂等查询/写入入
事务；记忆改为"独立副本同步喂正文→快照随回合保存→提交后替换共享缓存"、
待处理任务落库可续跑；roll 补顶层 selectedOptionIndex、修正前后者倒置、
结果沿用四类；§6 更名"名称出处检查"并明确能力边界、删除无数值规则支撑
的限幅；事务实现明确共用同一连接；改正 record_turn 与 replace_em_dashes
两处记录；测试计划加四场景。Needle 3 继续暂缓——先按 §9 用固定候选
实现并验证 commit-turn。

方案 b 回顾：组件循环跑在前端；后端不参与推理，只负责 ① 校验 ② 确定性
状态合并（`apply_output`）③ 事务提交（`commit_story_turn`）。本稿把这条
边界落到字段级。

代码锚点（现行实现，设计尽量复用其语义）：

| 机制 | 位置 | 语义 |
|---|---|---|
| 确定性合并 | `backend/app/services/game_state/manager.py` `apply_output` | `merge_by_name`/`_remove_by_name` 合并物品/NPC/任务/事实，`_merge_player_status` 合并玩家状态，回合自增、血统稳定每回合 +1 并 clamp、`recent_events` 追加 key_event、`enforce_state_caps` 裁剪 |
| 事务提交 | `backend/app/database/timeline.py` `commit_story_turn` | 校验 `active_turn_id == expected_parent_id`（不匹配抛 `ConcurrentModificationError`）→ 插入 `story_turns` 子节点 → 原子移动会话头并 `version = version + 1` |
| 节点激活（回滚/分支切换） | `timeline.py` `activate_story_turn` | 恢复旧节点为会话头，同样 `version + 1` |
| 会话版本 | `game_sessions.version`（`schema.py`）+ `sessions.py` 的 `expected_version` 乐观并发 | 每次头变动（含回滚）递增；这是 v2 引入 `expectedVersion` 的现成机制 |
| 候选载荷 schema | `backend/app/schemas/game/story_output.py` `StoryOutput` | `option_checks` 等长对齐、difficulty→target/expression 派生（`DIFFICULTY_TARGETS`）、破折号净化在此层强制 |
| 会话级串行 | `ScenarioGenerator._generation_locks` | 每 session 一把 asyncio 锁 |

## 1. 核心原则：候选与状态的单向流

**没有任何模型组件拥有游戏状态的写权。** 六个组件的输出一律是"候选"；
候选进入回合提交载荷，由后端确定性合并进状态。这直接回答"谁负责修改
库存与任务"：**只有 `apply_output` 的合并器修改库存与任务**（物品
`items_gained/items_lost + memory_updates.items_*` 按声明顺序折叠、任务
`quests_updated + memory_updates.quests_upserted` 同理）；组件只提议，
合并器裁决，冲突时后到者胜（现行 `declared_updates` 语义）。

三条纪律：

1. 组件输出不经过 `state`——前端 Task State Store 里的"当前尝试上下文/
   组件结果/未提交草稿"不是游戏状态，丢弃不影响已提交历史。
2. 候选绑定生成时的快照：`expectedParentId + expectedVersion` 双绑定
   （§3、§5 场景三）。
3. 失败尝试不落半个回合：循环中断 = 无提交 = 数据库无痕（§4 的审计
   例外见该节说明）。

## 2. 六组件 I/O 契约

共享上下文快照（循环开始前从后端取一次，只读分发给各组件）：

```ts
interface TurnContext {
  sessionId: string;
  slotName: string;             // 所属存档
  expectedParentId: number;     // 提交绑定：timeline 节点
  expectedVersion: number;      // 提交绑定：会话版本（§3）
  state: SanitizedGameState;    // sanitized state_json 的只读视图
  campaignContext: string;      // 战役上下文 + 记忆注入（后端端点组装）
  recentMessages: ChatMessage[];
  playerAction: string;
}
```

约定：组件输入只有 `TurnContext` 与上游候选；输出都带 `provenance`
（模型标签、耗时、重试次数）供审计；所有输出都是候选语义，⛔ 字段组件
不得填写（归确定性代码或后端推导）。

**试验范围声明（v2 纠正）**：现有分类器/抽取器试验（MiniRBT 分类、span
标注 ITEM/TGT、CRF 对照）全部测的是**玩家行动文本**里的物品与目标。它们
的成绩只能支撑 §2.1 输入解析组件的选型讨论；**正文侧**的任务、世界事实、
状态变化、玩家状态补丁的抽取能力**没有任何实测证据**，本契约只定接口
不定模型。

### 2.1 输入解析（input-parser）

- **读**：`playerAction`、`state`（地点/NPC/物品名册）、`recentMessages`。
- **返回**：

```ts
interface InputParseCandidate {
  actionType: "move" | "inspect" | "item_use" | "npc_talk" | "other";
  itemUsed: string | null;   // 原文摘录，别名表归一化后比较
  target: string | null;
}
```

- **不做**：⛔ `feasible` 不由模型组件产出——归前端确定性代码（Examiner
  规则：任何非空 `itemUsed` 查持有；`target` 查在场 NPC / 已知地点）。
- 选型依据（限玩家行动范围）：分类器 11/12 @ ~9ms；字段抽取整块臂优于
  拆分臂（v6 证伪）；CRF 不晋升、训练暂停（2026-10-11 裁决）。

### 2.2 决策（director）

- **时机（v2 变更）**：本组件在**正文过检之后**运行，读取已过检的
  `NarrationCandidate` 与拟更新候选（`ExtractionCandidates`），据此产出
  下一回合玩家选项。选项与正文解耦生成，但内容上承接正文。
- **读**：过检正文、拟更新候选、`TurnContext`、输入解析结果、锚点进度。
- **返回**：

```ts
interface OptionsCandidate {
  options: string[];
  optionChecks: (OptionCheckCandidate | null)[];  // 与 options 等长对齐
}
// ⛔ target/expression 不填——后端提交时按 difficulty 重推导
//   （DIFFICULTY_TARGETS，单一事实源）。
```

- **不做**：⛔ 不产出剧情正文；⛔ 不写数值难度；⛔ 不处理本回合骰点
  （本回合的 roll 绑定父节点已存选项，见 §3.3）。

### 2.3 叙事生成（narrator）

- **读**：`TurnContext`、决策前置指令（方向）、可行性结果（成功/失败
  分支写法）、风格约束。
- **返回**：

```ts
interface NarrationCandidate {
  narration: string;                          // 第二人称正文
  dialogue: { speaker: string; text: string }[];  // 结构化数组（v2 裁决保留）
}
```

- `dialogue` 与 `narration` 一起过文本检查、一起被输出解析消费（v2 裁决）。
- **不做**：⛔ 不产出 options/option_checks（归决策组件，且在过检后）；
  ⛔ 不产出 memory_updates；⛔ 不写任何状态字段。
- 已知状态（记录，非本稿范围）：narration-only 形态在真实规则试验中
  语言形式优于 monolithic 形态，但剧情质量未过检（回归旧情节、未交代
  名单权限、第一人称、篇幅不足），端侧配置暂不接入正式回合（2026-10-11
  裁决）；试验同时改变多变量且未携带 response_format，不能归因单一因素。

### 2.4 输出解析（output-parser）

- **读**：**已过检的** `NarrationCandidate`（含结构化 dialogue）+
  `TurnContext`。消费的是将被提交的叙事，不是中间产物。
- **返回**（候选语义；字段与 `MemoryUpdates` 及 `StoryOutput` 现产字段对应）：

```ts
interface ExtractionCandidates {
  currentLocation?: string;
  sanityDelta: number;              // v2 统一：本组件唯一提议者（§2.7）
  healthDelta: number;
  itemsUpserted: ItemCandidate[];   itemsRemoved: ItemCandidate[];
  npcsUpserted: NpcCandidate[];     questsUpserted: QuestCandidate[];
  worldFactsUpserted: WorldFactCandidate[];
  playerStatusPatch: PlayerStatusCandidate;
  keyEvent: string;                 // ≤80 字，不复制 narration
}
```

- `sanityDelta/healthDelta` **统一归本组件提议**（v2 统一：v1 在 2.4 与
  2.7 两处矛盾）：只有正文明确描写了血统/体力冲击才给非零值；系统负责
  clamp 与每回合自动恢复，组件不得把自动恢复写进增量（生产提示词既有
  约定）。
- **每项变更候选附正文依据**（v3，§6）：支持该变更的原句/偏移或名册来源，
  供提交前名称出处检查核对。
- **不做**：⛔ 不合并、不查重（同名合并与覆盖次序是后端 `merge_by_name`
  的职责）；⛔ 不自行认定变更合法（出处检查只验名字与依据可定位，§6）。
- 能力现状：本组件（正文抽取）无实测成绩——span 标注试验测的是玩家
  行动，成绩不可迁移引用（§2 试验范围声明）。接口先定，模型与训练开放。

### 2.5 文本检查（text-checker）

- **读**：`NarrationCandidate`（narration + dialogue 一起）、
  `TurnContext`、上游候选。
- **返回**：

```ts
interface CheckVerdict {
  passed: boolean;                  // false → 循环回退叙事组件重试（计重试预算）
  modelChecks: {                    // 模型检查集中在这三项（决策已定）
    continuation: boolean;          // 承接
    relevance: boolean;             // 相关性
    consistency: boolean;           // 一致性
  };
  mechanical: {                     // 代码检查，无模型
    emDashCount: number; simileCount: number; sentenceCount: number;
    firstPersonDetected: boolean;   // 真实规则试验暴露的失败模式
    entityGrounding: { name: string; found: boolean }[];
  };
}
```

- **不做**：⛔ 不修改正文（重写是叙事组件的事）；软规则暂缓、先采真实
  失败样本再定（决策已定）。

### 2.6 记忆（memory）

- **读**：过检的 `NarrationCandidate` + `ExtractionCandidates` +
  `TurnContext`。
- **返回**：key_event 措辞候选、"值得长期记住"的信号。
- **权属与时序（v3 对齐 §4）**：建议不落状态；记忆合并沿用后端
  `_memory_controller` 快照机制（随分支回滚），上下文注入（NSB/PCB/
  SCORE）走后端端点。喂入时序：提交事务内在**独立副本**上同步执行
  `on_turn_generated`，副本快照随回合落库（快照因此包含本回合）；提交
  成功后副本才替换共享内存缓存；摘要与 recap 仍在提交后，待处理任务
  记录随回合落库（绑定存档与节点，可重启续跑）。现产管线在提交前就喂
  共享控制器的做法不得照搬——提交失败的回合不能污染记忆。

### 2.7 汇编成提交载荷

循环全部通过后，前端把候选汇编为 `TurnCandidate`（§3.2）。汇编规则：

- `narration/dialogue` ← 叙事组件；`memory_updates` ← 输出解析组件
  （key_event 措辞可被记忆组件建议覆盖，以最终过检版本为准）；
  `sanity_delta/health_delta` ← 输出解析组件（唯一来源，v2 统一）；
  `options/option_checks` ← 决策组件（过检后生成，作为**下一回合**的
  选项随本回合存档）；
- `scene_prompt`：**运行时留空**（v2 裁决）——背景图沿用游玩前预生成的
  准备资产，运行时不再产出英文场景描述；
- `roll` 不在候选里（§3.3）。

## 3. commit-turn 端点

统一提交入口：`POST /sessions/{session_id}/commit-turn`。生成在前端循环
完成后，一次性提交完整回合候选。

### 3.1 幂等键 requestId（v3 修订）

客户端为**一次完整提交尝试**生成唯一 `requestId`（UUID）；同一尝试的
网络重发沿用原 ID，改了任何内容再提交则是新尝试、换新 ID。

后端持久保存 `turn_submissions` 表（定案）：`UNIQUE(session_id,
request_id)`，列含**内容摘要**与**提交结果**。摘要覆盖五个维度——
`playerAction`、`slotName`、`candidate`、`roll`（含
`selectedOptionIndex`）、快照绑定（`expectedParentId + expectedVersion`）。
v2 漏了 `playerAction`：同一 requestId 改动作文本会被误判成重放而返回
旧结果，v3 修复。

| 情形 | 行为 |
|---|---|
| 同 requestId + 同内容摘要 | **返回原提交结果**（200），不重复合并、不再次移动会话头、不重复扣减任何数值 |
| 同 requestId + 不同内容摘要 | **拒绝**（409/422），报"requestId 已被不同内容使用" |
| 新 requestId | 正常提交流程 |

**时序（v3 定案）**：幂等查询与结果写入都发生在 §3.4 的提交事务**内**
（与绑定校验、状态读取、全部写入共用同一连接，§4）——放在事务外会有
并发窗口：两个同 ID 请求同时通过查询、双双走完提交流程。并发重发进
§9 测试计划。只有提交成功的 requestId 才产生持久结果记录；失败尝试的
requestId 记审计、不记结果（客户端换新 ID 重试）。

### 3.2 请求体与绑定校验

```jsonc
{
  "requestId": "uuid",                // §3.1
  "expectedParentId": 123,            // 绑定一：父节点
  "expectedVersion": 57,              // 绑定二：会话版本
  "playerAction": "我去调查巡夜学生的名单……",
  "candidate": { /* StoryOutput 同构；scenePrompt 恒空串；无 roll 字段 */ },
  "selectedOptionIndex": 1,           // §3.3：玩家本回合选的父节点选项下标；自由输入为 null
  "roll": { "result": 14 },           // §3.3：所选选项 requires_check 时必填
  "audit": { "componentCalls": [], "retries": {}, "pausedAt": null, "runtime": {} }
}
```

**双绑定（v2 核心修订）**：提交事务内同时校验
`active_turn_id == expectedParentId` **且** `game_sessions.version ==
expectedVersion`。只查父节点挡不住"推进后又回到旧节点"的迟到请求——
回滚（`activate_story_turn`）会恢复旧节点 id 但递增 version，父节点校验
通过而版本不匹配，照样拒绝（§5 场景三）。

上下文接口（`GET /sessions/{id}/turn-context`）一次性返回
`{expectedParentId, expectedVersion, slotName, state, campaignContext,
recentMessages}`——前端快照与提交绑定用同一组值，杜绝两读不一致。

### 3.3 selectedOptionIndex + roll：使用父节点已保存的选项（v3 修订）

**时序事实**：当前提交流程生成的 options 是**下一回合**的选项；玩家本
回合执行的行动属于**父节点**存档的选项。骰点校验一律使用**父节点已保存
的选项**（`expectedParentId` 指向的 `story_turns.output_json` 里的
`option_checks`），不使用候选里的任何选项数据。

v2 把选项下标藏在 `roll` 里，导致**省略 roll 时后端无法判断玩家是否跳过
了所选选项的检定**。v3 把两者拆开，都是请求顶层字段：

- `selectedOptionIndex`：玩家本回合选择的父节点选项下标；**自由输入时为
  null**（此时不得携带 roll）。
- `roll`：`{ result }`，仅当所选选项要求检定时存在。

后端校验链（确定性代码，按序）：

1. `selectedOptionIndex` 非 null 时，父节点 `option_checks` 中该下标存在，
   且提交的 `playerAction` 与该选项文本对应（前端把选项文本与判定结果
   拼进行动——`checks.ts` 的 `formatActionWithCheckResult` 已产出该格式；
   校验接受裸选项文本与其带 `[行动判定]` 后缀的形态）；
2. 该项 `requires_check == true` → `roll` 必须存在（**漏交骰点 = 422**，
   没有"后端替玩家免检"）；`requires_check == false` → `roll` 必须不存在
   （对无需检定的选项掷骰 = 拒绝）；
3. 从该项 `difficulty` 重推导 target（`DIFFICULTY_TARGETS`）与表达式，
   不信任任何上报数值；
4. `result ∈ [1,20]` 整数；结果沿用现有四类规则（`rules.ts getOutcome`）：
   20 = 大成功（critical）、1 = 大失败（fumble）、其余按 target 分成功/
   失败——后端以同一规则重算结果并随合并生效、写审计；
5. `selectedOptionIndex` 为 null 而携带 roll → 拒绝。

前端掷骰沿用现有 `checks.ts` 语义；本字段链路对"跳过检定"是显式的：
要么选了不检定的选项，要么自由输入——不存在"选了检定项却静默无骰点"
的提交。

### 3.4 后端处理顺序

每一步失败即整体失败，无半个回合：

1. **schema 校验**：候选转 `StoryOutput`，现有 validator 生效（等长对齐、
   难度派生）；随后**显式调用 `replace_em_dashes()`**——它是普通方法，
   转换与 pydantic 校验都不会自动净化（v3 记录改正），调用位置固定在此步、
   合并与出处校验之前。前端不得预做推导。
2. **绑定校验**：`expectedParentId + expectedVersion` 双查（§3.2），
   失败 → 409（在合并之前，过期候选永不与新鲜状态合并）。
3. **提交前候选校验**：§6 名称出处检查，失败 → 422（带逐条详情）。
4. **单事务提交**（§4）：开启**一个** SQLite 连接上的事务，依序完成
   幂等查询（§3.1 三分支，事务内防并发重发）→ `apply_output` 合并 →
   记忆副本快照随回合保存（§4）→ `story_turns` 插入 →
   `model_outputs` 记录 → `campaign_progress`（含 npc_relations、锚点、
   回合/幕计数）→ `turn_submissions` 结果落库 → 会话头与 version 原子
   移动。任何一步失败整体回退，同时丢弃战役与记忆的工作副本（§4）。
5. **提交后步骤**（事务外，允许失败与重试）：用已提交的记忆副本替换
   共享缓存；执行/派发待处理维护任务（§4，绑定存档与节点，可重启续跑）；
   跨幕 recap 生成；审计导出。
6. **响应**：与现产 `GenerateResponse` 同构 + `requestId` 回显。前端据此
   刷新 Task State Store。

## 4. 提交范围与事务边界（v2 新增，v3 修订）

现产管线在 `commit_story_turn` **之前**就修改了多个共享对象，新入口不能
照搬这条顺序。逐项枚举（`ScenarioGenerator` / `post_generation.py` /
`agent_pipeline.py`）：

| 现产行为 | 时点 | 问题 | 新入口 |
|---|---|---|---|
| `_process_npc_relations_delta` → `update_npc_relations` | 合并后、提交前 | 异常被吞（logger.warning 后继续）；提交失败时关系已变 | **入事务** |
| `campaign_manager.record_turn` | 提交前 | （v3 记录改正：它只**返回**统计值，不修改待定锚点）统计随 model_outputs 落库 | **入事务**（作为 model_outputs 行的列） |
| `db.add_model_output`（模型输出记录） | 提交前 | 提交失败留下孤儿 model_output | **入事务** |
| `_advance_campaign`（锚点提交、回合/幕推进） | 提交前 | 推进与回合节点可脱节 | **入事务**（计数与进度部分） |
| `advance_session`（跨幕：可能调 LLM 生成 recap） | 提交前 | LLM 调用不能进 DB 事务 | **拆两半**：幕/会话计数与边界状态入事务；recap 生成移到提交后，幂等可重试，recap 未生成前会话以"无 recap"可玩 |
| `memory_ctrl.on_turn_generated` + 后台 `maintain` | 生成阶段就喂正文 | 提交失败的回合污染记忆池 | 见下（v3 重排） |
| `_memory_controller` 快照写入 state | 合并时 | 快照在喂入之前导出 → **随回合保存的快照漏掉本回合**（v2 方案的缺陷） | **独立副本同步喂入**（见下） |

**记忆时序（v3 重排）**：

1. 提交事务内，在共享控制器的**独立副本**上同步执行
   `on_turn_generated`（喂入本回合正文与更新）；
2. 导出**副本**的快照随本回合 state_json 落库——快照因此包含本回合；
3. 提交成功后，用副本**替换共享内存缓存**；
4. 摘要类工作与 recap 仍在提交后执行，但**待处理任务记录随回合落库**
   （进 state_json 或独立列），每条任务**绑定存档（slot）与节点 id**，
   支持进程重启后从落库快照恢复控制器并续跑，任务执行幂等（重复执行
   无副作用）。

**同一连接（v3 定案）**：`update_npc_relations`、`write_campaign_progress`
等 store 方法**各自打开新连接**（`campaign_store.py` 每个 `with
self.connect()` 一个连接）——在外面套 `with db:` 无法让这些写入一起回退。
事务实现必须让**绑定校验、状态读取、全部写入、幂等结果保存共用同一个
SQLite 连接**（store 方法增加接受既有连接的变体，或提交流程内全部改走
该连接）。**事务失败时同时丢弃战役与记忆的工作副本**——内存里只留提交
前已确认的共享状态，防止半程副本污染后续请求。

**事务边界定义**：`story_turns` + `model_outputs` + `campaign_progress`
（含 npc_relations/锚点/幕进度）+ `turn_submissions` + 记忆快照（随
state_json）+ 会话头与 version —— 一个连接上的一个事务，全成或全不成。
**事务外**只允许两类东西：审计/诊断记录（它们的存在意义就是记录失败，
不携带游戏状态）与提交后派生步骤（缓存替换、待处理任务执行、recap）。

## 5. 三场景验证（v2 更新）

### 场景一：生成超时

**触发**：单组件请求超 4s×2 次重试仍失败，或一回合组件调用达 20 次上限
（防循环参数：超限暂停、不降级）。

**设计行为**：循环暂停在当前组件；`TurnCandidate` 未汇编完成 → 不调用
commit-turn；数据库无新节点、头与 version 不动。草稿保留在 Task State
Store 并标注暂停原因，可导出审计或丢弃重开。

**验证点**：(a) 任意时刻杀掉前端进程，库中无该回合痕迹；(b) 恢复后新
回合从原 `expectedParentId/expectedVersion` 正常开启；(c) 审计导出含
超时组件与尝试计数。

### 场景二：重复提交（v2 按 requestId 重写）

**触发与行为**（§3.1 三分支）：

- **响应丢失后重发**（同 requestId、同内容）：返回原结果，不再次移动
  会话头，状态数值只变化一次。
- **同文本、不同 requestId**：两次独立提交，父节点校验让第二个失败
  （头已前移）——旧设计"父节点+行动文本判成功"的启发式会把它误判成
  重放，v2 明确：文本相同不是幂等依据，**requestId 才是**。
- **同 requestId、不同内容**：拒绝，报摘要不匹配。

**验证点**：(a) 连续两次同载荷提交，第二次 200 且返回首次的
`timeline_node_id`，库中只有一个新节点；(b) 同文本两个 requestId →
一成一败（409），不产生双胞胎回合；(c) 改动候选后重放旧 requestId →
409/422；(d) **并发同 ID**：两个同 requestId 请求竞态 → 恰一个完成提交，
另一个返回原结果或 409，库中一个节点、`turn_submissions` 一行（唯一
约束兜底，幂等查询在事务内）。

### 场景三：读取过期状态（v2 加版本绑定）

**触发**：前端基于 `expectedParentId=123, expectedVersion=57` 跑完循环；
提交前会话头变动——可能是正常推进（124），也可能是**推进后又回滚到
123**（`activate_story_turn`：节点 id 回来了，version 已递增到 58+）。

**设计行为**：双绑定校验失败 → 409 + 当前头摘要（`active_turn_id`、
`version`、sanitized state 摘要）。**过期候选与新鲜状态永不合并**——
叙述是针对旧快照写的，静默 rebase 会产出剧情与状态脱节的回合。前端收到
409 后丢弃草稿或用新快照重跑循环（rebase = 重跑，不存在候选移植）。
版本绑定保证"父节点相同但版本过期"的迟到请求同样被拒。

**验证点**：(a) 正常推进后提交 → 409；(b) 推进后回滚到原节点再提交 →
仍 409（version 不匹配）；(c) 409 响应带足以重跑的线索（新
`expectedParentId + expectedVersion`）。

## 6. 名称出处检查（v3 更名并收窄声明）

`merge_by_name` 只负责**写入顺序**（后到者胜），不核实变更是否有正文
依据。提交事务前增加一个确定性校验器（无模型）。**能力边界必须诚实**：
名字出现在正文或库存里，**不能证明**获得、消耗或任务完成发生了——本
检查只验证"名字有出处"这一件事，**名称匹配通过 ≠ 变更合法**。

- **候选带依据（v3 新增）**：每项变更候选附**正文依据**字段——支持该
  变更的正文片段（narration/dialogue 的原句或偏移），或名册来源（state/
  RAG/最近对话）。输出解析组件产出依据，校验器只核对依据存在且真实
  可定位（依据文本确实出现在正文/名册中）；
- **当前能验证的**：① 实体名与依据可定位（与输入解析同一套别名归一化
  精确比较，"钥匙"≠"铜钥匙"）；② 变更方向与依据的动词搭配（标签跟动词
  走：upserted 的依据应是获得/观察到类表述，removed 的依据应是失去/
  消耗类表述——沿用标注规则的动词-字段搭配口径）；
- **当前不能验证的**（明确声明，不作为通过条件）：事件是否真的按正文
  发生、数量/状态语义是否正确、任务完成条件是否满足——这些归文本检查
  组件的一致性判定与后续人工/软规则；
- **失败行为**：422，逐条返回无出处或依据不可定位的候选（字段、名称、
  依据、建议），回合不提交——与"失败尝试不落半个回合"一致；前端可选择
  重跑输出解析或叙事组件。不做静默剥离（会掩盖模型缺陷；如需降级模式
  另议）；
- **数值限制**：不新增（v2 的 `|delta| ≤ 30` 无已定规则支撑，v3 删除；
  `sanity/health` 的 clamp 由 `apply_output` 既有逻辑负责）。

## 7. 已裁决记录（2026-10-11 二轮评审）

1. options 归**决策组件**，且在正文过检后生成，读取正文与拟更新候选
   （§2.2）。v1 中"正文附带选项会降低质量"的表述删除——叙事试验同时
   改变多变量，不足以支撑该归因。
2. `scene_prompt` 运行时留空，背景沿用游玩前预生成资产（§2.7）。
3. `dialogue` 保留结构化数组，与 narration 一起检查、一起解析（§2.3/2.5）。
4. roll 由前端掷、后端确定性校验，使用**父节点已保存的选项**；`selectedOptionIndex`
   （顶层，自由输入为 null）与 `roll` 分离，漏骰显式 422；结果沿用四类
   规则（20 大成功 / 1 大失败 / 其余按 target 分成功失败）（§3.3）。
5. 回合默认温度 0.35（已实现 0ae65b3：`PromptMeta` 默认值 + 移除
   builder 的 difficulty→0.7 旧钩子；显式传值仍生效）。
6. CRF 不晋升、抽取训练暂停；端侧叙事配置暂不接入正式回合（2026-10-11
   早前裁决，接口照定、模型开放）。

## 8. Needle 3 接缝（本稿验收后动工）

- 组件调用由 Needle 3 调度；I/O 走 §2 契约，调度语言中立（枚举 ID）。
- 每个组件调用 = 一次 schema 约束生成（json_schema + AbortSignal）；
  §2 候选接口即约束 schema 来源。
- 防循环参数挂调度层：每请求重试 2 次、一回合 20 次上限，超限走 §5
  场景一的暂停路径。
- 前置检查（既有开放项）：Needle 3 浏览器工件确认、中文路由测试。

## 9. 下一轮：先实现并验证 commit-turn，再接模型调度（v2 新增，v3 扩充）

实现顺序（用户裁定）：**用固定候选**（手写/夹具候选，不经任何模型）
实现 §3 的 commit-turn 端点与 §4 的事务边界，并验证八个场景：

1. **响应丢失后的重发**：同 requestId 重放 → 返回原结果，头只动一次；
2. **同文本不同请求**：两个 requestId、相同行动文本 → 一成一败；
3. **推进后回滚的迟到请求**：父节点 id 相同但 version 已递增 → 409；
4. **提交途中抛错后的完整回退**：在事务内任一步注入异常 → `story_turns`
   /`model_outputs`/`campaign_progress`/会话头全部回到提交前，无孤儿行，
   战役与记忆工作副本同时丢弃；
5. **并发重发**（v3）：两个同 requestId 请求竞态 → 恰一个提交成功，
   库中一个节点、`turn_submissions` 一行（唯一约束兜底）；
6. **改动作后重用 ID**（v3）：同 requestId、`playerAction` 不同 →
   409/422（摘要覆盖动作文本）；
7. **漏交骰点**（v3）：`selectedOptionIndex` 指向 requires_check 选项但
   无 roll → 422；requires_check=false 或自由输入带 roll → 拒绝；
8. **提交成功后重启的记忆恢复**（v3）：提交后重启进程 → 从落库快照恢复
   控制器，快照包含本回合，待处理任务绑定存档与节点可续跑且重复执行
   无副作用。

提交行为验收通过后，才把模型调度（组件循环、Needle 3）接到这个入口上。
