# 组件 I/O 字段说明与 commit-turn 设计稿（v2）

状态：v2 草案（2026-10-11 二轮评审修订，待评审）。v1 的七处修订：
重复提交引入 requestId 幂等；过期检查加 expectedVersion 双绑定；补提交
范围与事务边界；roll 移出候选、改绑父节点已存 option_checks；纠正
ITEM/TGT 试验范围的误用；统一 sanity/health_delta 职责；四个开放问题
裁决落定（含删除一项无证据的归因）。Needle 3 暂缓接入——先按 §9 用固定
候选实现并验证 commit-turn。

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

- `sanityDelta/healthDelta` **统一归本组件提议**（v2 修正：v1 在 2.4 与
  2.7 两处矛盾）：只有正文明确描写了血统/体力冲击才给非零值；系统负责
  clamp 与每回合自动恢复，组件不得把自动恢复写进增量（生产提示词既有
  约定）。
- **不做**：⛔ 不合并、不查重（同名合并与覆盖次序是后端 `merge_by_name`
  的职责）；⛔ 不自行认定变更合法（出处校验归提交前校验器，§6）。
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
- **权属与时序（v2 收紧）**：建议不落状态；记忆合并沿用后端
  `_memory_controller` 快照机制（随分支回滚），上下文注入（NSB/PCB/
  SCORE）走后端端点。**记忆控制器收到本回合正文与更新的时点在提交成功
  之后**（§4）——现产管线在提交前就喂正文（`on_turn_generated`），新入口
  不得照搬：提交失败的回合不能污染记忆。

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

### 3.1 幂等键 requestId（v2 新增）

客户端为**每次提交尝试**生成唯一 `requestId`（UUID）。后端持久保存
`(session_id, request_id) → {内容摘要, 结果}`：

| 情形 | 行为 |
|---|---|
| 同 requestId + 同内容摘要 | **返回原提交结果**（200），不重复合并、不再次移动会话头、不重复扣减任何数值 |
| 同 requestId + 不同内容摘要 | **拒绝**（409/422），报"requestId 已被不同内容使用"——防止重试包装了改过的载荷被误当成幂等重放 |
| 新 requestId | 正常提交流程 |

内容摘要 = 对 candidate + roll + expectedParentId + expectedVersion 的
规范化序列化哈希。存储位置设计为 `turn_submissions` 表（或 story_turns
冗余列，实现期定），**与 §4 的事务边界一致**：只有提交成功的 requestId
才产生持久记录；失败尝试的 requestId 记审计、不记结果（客户端换新
requestId 重试）。

### 3.2 请求体与绑定校验

```jsonc
{
  "requestId": "uuid",                // §3.1
  "expectedParentId": 123,            // 绑定一：父节点
  "expectedVersion": 57,              // 绑定二：会话版本（v2 新增）
  "playerAction": "我去调查巡夜学生的名单……",
  "candidate": { /* StoryOutput 同构；scenePrompt 恒空串；无 roll 字段 */ },
  "roll": { "optionIndex": 1, "result": 14 },   // §3.3，本回合有骰点时必填
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

### 3.3 roll：绑定父节点已存选项（v2 修订）

**时序事实**：当前提交流程生成的 options 是**下一回合**的选项；玩家刚
执行的行动属于**父节点**存档的选项。骰点校验必须用前者不是后者。

`roll = {optionIndex, result}` 是提交请求的**顶层字段**（`StoryOutput`
没有也不加这个字段）。后端校验链（确定性代码）：

1. 父节点（`expectedParentId` 指向的 `story_turns.output_json`）已存的
   `option_checks[optionIndex]` 存在；
2. 该项 `requires_check == true`（无需检定的选项掷骰 = 拒绝）；
3. 从该项 `difficulty` 重推导 target（`DIFFICULTY_TARGETS`）与表达式，
   不信任候选里的任何数值；
4. `result ∈ [1,20]` 整数；
5. 结果与推导的 target 比较得出成败，随合并一并生效并写审计。

前端掷骰沿用现有 `checks.ts` 的语义（`resolveOptionCheck` 读的正是**正在
游玩的那个 output** 的 `option_checks`）；父节点选项无需检定时不得携带
`roll` 字段。

### 3.4 后端处理顺序

每一步失败即整体失败，无半个回合：

1. **schema 校验**：候选转 `StoryOutput`，现有 validator 生效（等长对齐、
   难度派生、破折号净化）。前端不得预做推导。
2. **幂等查询**：按 §3.1 三分支处理。
3. **绑定校验**：`expectedParentId + expectedVersion` 双查（§3.2），
   失败 → 409（在 `apply_output` 之前，过期候选永不与新鲜状态合并）。
4. **提交前候选校验**：§6 出处校验，失败 → 422（带逐条详情）。
5. **单事务提交**：§4 的事务边界——`apply_output` 合并 + `story_turns`
   插入 + `model_outputs` 记录 + `campaign_progress`（含 npc_relations、
   锚点、回合/幕推进）在同一 SQLite 事务内成功或整体回退。
6. **提交后步骤**（事务外，允许失败与重试）：记忆控制器喂正文
   （`on_turn_generated`）与后台 maintain；跨幕 recap 生成（§4 的豁免
   条目）；审计导出。
7. **响应**：与现产 `GenerateResponse` 同构 + `requestId` 回显。前端据此
   刷新 Task State Store。

## 4. 提交范围与事务边界（v2 新增）

现产管线在 `commit_story_turn` **之前**就修改了多个共享对象，新入口不能
照搬这条顺序。逐项枚举（`ScenarioGenerator` / `post_generation.py` /
`agent_pipeline.py`）：

| 现产行为 | 时点 | 问题 | 新入口 |
|---|---|---|---|
| `_process_npc_relations_delta` → `update_npc_relations` | 合并后、提交前 | 异常被吞（logger.warning 后继续）；提交失败时关系已变 | **入事务** |
| `campaign_manager.record_turn`（指标/待定锚点） | 提交前 | 同上 | **入事务** |
| `db.add_model_output`（模型输出记录） | 提交前 | 提交失败留下孤儿 model_output | **入事务** |
| `_advance_campaign`（锚点提交、回合/幕推进） | 提交前 | 推进与回合节点可脱节 | **入事务**（计数与进度部分） |
| `advance_session`（跨幕：可能调 LLM 生成 recap） | 提交前 | LLM 调用不能进 DB 事务 | **拆两半**：幕/会话计数与边界状态入事务；recap 生成移到提交后，幂等可重试，recap 未生成前会话以"无 recap"可玩 |
| `memory_ctrl.on_turn_generated` + 后台 `maintain` | 生成阶段就喂正文 | 提交失败的回合污染记忆池 | **移到提交后**（§2.6） |
| `_memory_controller` 快照写入 state | 合并时 | 随 state_json 落库，本身事务安全 | 维持（入事务） |

**事务边界定义**：`story_turns` + `model_outputs` + `campaign_progress`
（含 npc_relations/锚点/幕进度）+ 会话头与 version —— 一个 SQLite 事务，
全成或全不成。**事务外**只允许两类东西：审计/诊断记录（它们的存在意义
就是记录失败，不携带游戏状态）与提交后派生步骤（记忆喂入、recap）。

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
409/422。

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

## 6. 提交前候选校验（v2 新增）

`merge_by_name` 只负责**写入顺序**（后到者胜），不核实变更是否有正文
依据。提交事务前增加一个确定性校验器（无模型）：

- **范围**：`itemsUpserted/itemsRemoved/npcsUpserted/questsUpserted/
  worldFactsUpserted/playerStatusPatch` 中的实体名，必须能在**过检正文
  （含 dialogue）或 `TurnContext` 名册（state/RAG/最近对话）**中找到出处
  （与输入解析同一套别名归一化精确比较，"钥匙"≠"铜钥匙"）；
- **失败行为**：422，逐条返回无出处的候选（字段、名称、建议），回合
  不提交——与"失败尝试不落半个回合"一致；前端可选择重跑输出解析或
  叙事组件。不做静默剥离（会掩盖模型缺陷；如需降级模式另议）；
- **数值范围**：`sanityDelta/healthDelta` 限幅检查（如 |delta| ≤ 30），
  超限 422。

## 7. 已裁决记录（2026-10-11 二轮评审）

1. options 归**决策组件**，且在正文过检后生成，读取正文与拟更新候选
   （§2.2）。v1 中"正文附带选项会降低质量"的表述删除——叙事试验同时
   改变多变量，不足以支撑该归因。
2. `scene_prompt` 运行时留空，背景沿用游玩前预生成资产（§2.7）。
3. `dialogue` 保留结构化数组，与 narration 一起检查、一起解析（§2.3/2.5）。
4. roll 由前端掷、后端确定性校验，绑定父节点已存 `option_checks`，作为
   提交请求顶层字段（§3.3）。
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

## 9. 下一轮：先实现并验证 commit-turn，再接模型调度（v2 新增）

实现顺序（用户裁定）：**用固定候选**（手写/夹具候选，不经任何模型）
实现 §3 的 commit-turn 端点与 §4 的事务边界，并验证四个场景：

1. **响应丢失后的重发**：同 requestId 重放 → 返回原结果，头只动一次；
2. **同文本不同请求**：两个 requestId、相同行动文本 → 一成一败；
3. **推进后回滚的迟到请求**：父节点 id 相同但 version 已递增 → 409；
4. **提交途中抛错后的完整回退**：在事务内任一步注入异常 → `story_turns`
   /`model_outputs`/`campaign_progress`/会话头全部回到提交前，无孤儿行。

提交行为验收通过后，才把模型调度（组件循环、Needle 3）接到这个入口上。
