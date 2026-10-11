# 组件 I/O 字段说明与 commit-turn 设计稿

状态：草案（待评审）。2026-10-11 用户指定范围：写清各组件读什么、返回什么、
谁负责修改库存与任务；用生成超时、重复提交、读取过期状态三个场景验证设计；
明确"叙事文字与抽取候选不直接写入游戏状态"；约定定稿后再接 Needle 3。

方案 b 回顾：组件循环跑在前端；后端不参与推理，只负责 ① 校验 ② 确定性状态
合并（`apply_output`）③ 事务提交（`commit_story_turn` + `expected_parent_id`）。
本稿的全部约定都是把这条边界落到字段级。

代码锚点（现行实现，设计不改变其语义）：

| 机制 | 位置 | 语义 |
|---|---|---|
| 确定性合并 | `backend/app/services/game_state/manager.py` `apply_output` | 按 `merge_by_name`/`_remove_by_name` 合并物品/NPC/任务/事实，`_merge_player_status` 合并玩家状态，回合自增、血统稳定每回合 +1 并 clamp、`recent_events` 追加 key_event、`enforce_state_caps` 裁剪 |
| 事务提交 | `backend/app/database/timeline.py` `commit_story_turn` | 校验 `active_turn_id == expected_parent_id`（不匹配抛 `ConcurrentModificationError`）→ 插入 `story_turns` 子节点 → 原子移动会话头 |
| 候选载荷 schema | `backend/app/schemas/game/story_output.py` `StoryOutput` | `option_checks` 与 options 等长对齐、difficulty 推导 target/expression、破折号净化（`replace_em_dashes`）都在此层强制 |
| 会话级串行 | `ScenarioGenerator._generation_locks` | 每 session 一把 asyncio 锁，防并发生成 |

## 1. 核心原则：候选与状态的单向流

**没有任何模型组件拥有游戏状态的写权。** 六个组件的输出一律是"候选"
（candidate）；候选进入回合提交载荷，由后端确定性合并进状态。这条原则
直接回答"谁负责修改库存与任务"：**只有 `apply_output` 的合并器修改库存与
任务**（物品 `items_gained/items_lost + memory_updates.items_*` 按声明顺序
折叠、任务 `quests_updated + memory_updates.quests_upserted` 同理）；组件
只提议，合并器裁决，冲突时后到者胜（现行 `declared_updates` 语义）。

由此推出的三条纪律：

1. 组件输出不经过 `state`——前端 Task State Store 里的"当前尝试上下文/
   组件结果/未提交草稿"（决策已定：Task State Store 在前端）不是游戏状态，
   丢失或丢弃不影响已提交历史。
2. 候选绑定生成时的父节点：组件循环读到的状态快照属于 `expectedParentId`，
   提交时后端校验的就是这个绑定（见 §4 场景三）。
3. 失败尝试不落半个回合（决策已定）：循环中断 = 无提交 = 数据库无痕。

## 2. 六组件 I/O 契约

共享上下文快照（循环开始前从后端取一次，只读分发给各组件）：

```ts
interface TurnContext {
  sessionId: string;
  expectedParentId: number;     // 提交时绑定的 timeline 节点
  state: SanitizedGameState;    // sanitized state_json 的只读视图
  campaignContext: string;      // 战役上下文 + 记忆注入（后端端点组装）
  recentMessages: ChatMessage[]; // 最近对话（session 边界内）
  playerAction: string;
}
```

约定：所有组件输入只有 `TurnContext` 与上游组件的**候选**；所有组件输出
都带 `provenance`（模型标签、耗时、重试次数）供审计；所有输出字段都是
候选语义，标 ⛔ 的字段组件不得填写（由确定性代码或后端推导）。

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

- **不做**：⛔ `feasible` 不由本组件（或任何模型组件）产出——归前端确定性
  代码（Examiner 规则移植：任何非空 `itemUsed` 查持有；`target` 查在场
  NPC / 已知地点）。组合轮的结论（拆分反而掉分、代码算 feasible）已固化
  为此契约。
- 运行时选型：行动分类走 MiniRBT 分类器路径（11/12 @ ~9ms，已验证）；
  字段抽取沿用整块提示词臂（拆分被证伪）。

### 2.2 决策（director）

- **读**：`TurnContext`、`InputParseCandidate`、可行性结果、锚点进度
  （campaign 通道）。
- **返回**：叙事方向指令（从哪推、压什么情绪、用哪些 NPC）；以及本回合
  玩家选项候选：

```ts
interface OptionsCandidate {
  options: string[];
  optionChecks: (OptionCheckCandidate | null)[];  // 与 options 等长对齐
}
// OptionCheckCandidate：requires_check/name/skill/system/difficulty/stakes
// ⛔ target/expression 不填——沿用 StoryOutput 的派生规则
//   （difficulty → DIFFICULTY_TARGETS → "1d20 ≥ target"），后端提交时重推导。
```

- **不做**：⛔ 不产出剧情正文；⛔ 不写数值难度。
- 检定骰：沿用冻结的 d20 语义（FYP 轮已统一）。骰点在前端掷并写审计，
  提交载荷带 `{optionIndex, roll}` 记录；后端只重推导 target/expression
  并校验 `roll ∈ [1,20]`，不重放 RNG（本地游戏，审计可查即诚实）。

### 2.3 叙事生成（narrator）

- **读**：`TurnContext`、决策组件的方向指令、可行性结果（成功/失败分支
  由它区分写法）、风格约束。
- **返回**：

```ts
interface NarrationCandidate {
  narration: string;                          // 第二人称正文
  dialogue: { speaker: string; text: string }[];
}
```

- **不做**：⛔ 不产出 options/option_checks（归决策组件）；⛔ 不产出
  memory_updates/scene_prompt；⛔ 不写任何状态字段。
- 试验结论锚定：narration-only 形态（1307 prompt tok、中文正文扣题、无
  复读）优于 monolithic 形态（2393 tok、JSON 契约下正文坍缩为英文元描述）；
  但剧情质量未过检（回归旧情节、未交代名单权限获取、第一人称、篇幅不足），
  端侧配置**暂不接入正式回合**——本组件的模型与提示词是开放项，接口先定。

### 2.4 输出解析（output-parser）

- **读**：**已通过文本检查的** `NarrationCandidate` + `TurnContext`。
  输入是过检正文这一点是硬约束：解析器消费的是将被提交的叙事，不是
  中间产物。
- **返回**（字段与 `MemoryUpdates` 一一对应，候选语义）：

```ts
interface ExtractionCandidates {
  currentLocation?: string;
  itemsUpserted: ItemCandidate[];   itemsRemoved: ItemCandidate[];
  npcsUpserted: NpcCandidate[];     questsUpserted: QuestCandidate[];
  worldFactsUpserted: WorldFactCandidate[];
  playerStatusPatch: PlayerStatusCandidate;   // condition/danger_level/current_goal/notes
  keyEvent: string;                 // ≤80 字，不复制 narration
}
```

- **不做**：⛔ 不合并、不查重、不去火——同名合并与覆盖次序是后端
  `merge_by_name` 的职责（"后到者胜"）；⛔ `sanity_delta/health_delta`
  不在此产出（见 2.5）。
- 运行时选型：span 标注路径时间达标（~9ms）但严格匹配未过 90% 线，CRF
  不晋升、抽取训练暂停（用户裁决 2026-10-11）；接口先定，模型开放。

### 2.5 文本检查（text-checker）

- **读**：`NarrationCandidate`、`TurnContext`、上游候选。
- **返回**：

```ts
interface CheckVerdict {
  passed: boolean;                  // false → 循环回退到叙事组件重试（计重试预算）
  modelChecks: {                    // 模型检查集中在这三项（决策已定）
    continuation: boolean;          // 承接：是否接住玩家行动与上一幕
    relevance: boolean;             // 相关性：是否偏航到无关任务
    consistency: boolean;           // 一致性：是否与已知状态/事实冲突
  };
  mechanical: {                     // 代码检查，无模型
    emDashCount: number;            // 现产 StoryOutput 层已有净化，此处前置拦截
    simileCount: number;            // 明喻句式计数
    sentenceCount: number;          // 篇幅对照（当前 observed 4 句 vs 目标 ~20 句）
    firstPersonDetected: boolean;   // "我"叙述检测（真实规则试验暴露的失败模式）
    entityGrounding: { name: string; found: boolean }[];  // 人名/地名/物品对名册与 RAG 出处
  };
}
```

- **不做**：⛔ 不修改正文（只判定，重写是叙事组件的事）；软规则暂缓、
  先采真实失败样本再定（决策已定）。

### 2.6 记忆（memory）

- **读**：过检的 `NarrationCandidate` + `ExtractionCandidates` +
  `TurnContext`。
- **返回**：记忆合并建议（key_event 措辞、MOOM/L1 摘要入池建议）。
- **权属关键**：**建议不落状态**。记忆的真正合并沿用后端现有
  `_memory_controller` 快照机制（决策已定：记忆随分支回滚），上下文注入
  （NSB/PCB/SCORE）走后端端点组装进 `campaignContext`。本组件在前端只做
  两件事：为 `keyEvent` 提供措辞候选、把"值得长期记住"的信号随提交载荷
  传给后端记忆管线。

### 2.7 汇编成提交载荷

循环全部通过后，前端把候选汇编为 `TurnCandidate`（§3）。汇编规则：

- `narration/dialogue` ← 叙事组件；`options/option_checks` ← 决策组件；
  `memory_updates` ← 输出解析组件（key_event 措辞可被记忆组件建议覆盖，
  以最终过检版本为准）；
- `sanity_delta/health_delta`：**候选保留但默认 0**，只有正文明确描写了
  血统/体力冲击才由输出解析组件提议（系统负责裁剪与自动恢复——生产
  提示词的既有约定，写进组件契约防重复计）；
- `scene_prompt`：开放项（背景图已定位为游玩前联网准备，是否保留运行时
  产出待裁决，见 §6）。

## 3. commit-turn 端点

统一提交入口。现产 `POST /sessions/{id}/generate` 是"生成+提交"一体；
方案 b 拆开后，生成在前端循环里完成，提交走：

```
POST /sessions/{session_id}/commit-turn
```

请求体：

```jsonc
{
  "expectedParentId": 123,            // 乐观并发锚点，必填
  "playerAction": "我去调查巡夜学生的名单……",
  "candidate": {                      // 与 StoryOutput 同构（camelCase 传输，后端转 pydantic）
    "narration": "……", "dialogue": [], "scenePrompt": "",
    "sanityDelta": 0, "healthDelta": 0,
    "options": [], "optionChecks": [],
    "currentLocation": "", "itemsGained": [], "itemsLost": [],
    "npcsEncountered": [], "questsUpdated": [],
    "memoryUpdates": { "...MemoryUpdates 同构..." },
    "roll": { "optionIndex": 1, "result": 14 }   // 本回合若有骰点
  },
  "audit": {                          // 审计随载荷上行（决策已定：本地记录+可回传）
    "componentCalls": [{ "component": "narrator", "model": "...", "wallMs": 0, "attempt": 1 }],
    "retries": { "narrator": 0 }, "pausedAt": null, "runtime": { "threads": 4 }
  }
}
```

后端处理顺序（每一步失败即整体失败，无半个回合）：

1. **schema 校验**：候选转 `StoryOutput`，让现有 validator 生效——
   `option_checks` 等长对齐、difficulty 推导 target/expression、破折号净化。
   前端不得预做这些推导（推导权在后端，避免两套实现漂移）。
2. **绑定校验**：`active_turn_id == expectedParentId`，不匹配 → 409
   `ConcurrentModificationError`（在 `apply_output` **之前**做，过期候选
   永远不与新鲜状态合并——见 §4 场景三）。
3. **确定性合并**：对**后端此刻读到的权威状态**执行 `apply_output`。
   前端循环中看到的状态只用于组提示词，永不作为合并基底。
4. **事务提交**：`commit_story_turn(expected_parent_id=…)` 原子落库并移动
   会话头。
5. **响应**：与现产 `GenerateResponse` 同构（`state` sanitized、
   `timeline_node_id`、`parent_timeline_node_id`、`memory`/`declared`/
   `caps`），前端据此刷新 Task State Store。

与现有代码的关系：不新增状态机——`apply_output`/`commit_story_turn`/
`ConcurrentModificationError` 原样复用；新代码只有"候选→StoryOutput 的
转接头"与路由。会话级 `_generation_locks` 语义同样适用于本端点。

## 4. 三场景验证

### 场景一：生成超时

**触发**：单组件请求超过 4s 预算重试 2 次仍失败，或一回合组件调用达
20 次上限（防循环参数，决策已定：超限暂停、不降级）。

**设计行为**：前端循环暂停在当前组件；`TurnCandidate` 未汇编完成 →
**不调用 commit-turn**；数据库无新节点、`active_turn_id` 不动。草稿
（已完成组件的候选 + 上下文快照）保留在 Task State Store，标注暂停原因
（哪个组件、第几次尝试、超时还是超限），可导出审计（`audit.pausedAt`）
或整体丢弃后重开回合。

**验证点**：(a) 任意时刻杀掉前端进程，库中无该回合痕迹；(b) 恢复会话后
新回合从原 `expectedParentId` 正常开启；(c) 审计导出包含超时组件与尝试
计数。

### 场景二：重复提交

**触发**：同一 `expectedParentId` 的载荷被提交两次（用户双击、网络重试
重放、前端 bug）。

**设计行为**：第一次成功后 `active_turn_id` 已前移；第二次提交在绑定
校验（§3 步骤 2）就被 `ConcurrentModificationError` 拒绝 → HTTP 409，
响应体带当前 `active_turn_id`。**不会**产生同一父节点下的第二个子节点，
不会重复扣血统/体力、不会重复推进回合数。

前端纪律：仅在"请求已发出但未收到响应"的窗口内允许重发一次，且重发前
先 `GET /sessions/{id}` 核对 `active_turn_id`——若头已前移且最新节点的
`player_action` 与载荷一致，视为已成功，不再重发。

**验证点**：(a) 连续两次同载荷提交，第二次 409 且状态数值只变化一次；
(b) 响应中的 `timeline_node_id` 是幂等凭据（第二次响应不复现新节点）。

### 场景三：读取过期状态

**触发**：前端基于快照 `expectedParentId=123` 跑完组件循环；提交前，该
会话状态被推进（另一设备提交了 124、或玩家在另一分支回滚后重开）。

**设计行为**：绑定校验失败 → 409 + 当前头摘要（`active_turn_id`、
sanitized `state` 摘要）。**过期候选与新鲜状态不合并**——叙述是针对旧
状态写的，静默 rebase 会产出剧情与状态脱节的回合（正是叙事试验暴露的
"剧情质量"失败模式在架构层的等价物）。前端收到 409 后丢弃草稿或提示
用户 rebase：rebase = 用新头的 `TurnContext` 重跑组件循环，不存在
"候选移植"。

**验证点**：(a) 提交过期候选返回 409 且库中无新节点；(b) 409 响应带
足以重跑循环的上下文线索（新 `expectedParentId`）；(c) 新旧两个候选
（不同父节点）各归各的分支节点，互不串写。

## 5. 与 Needle 3 的接缝（本稿定稿后动工）

- 组件调用由 Needle 3 调度；组件 I/O 走 §2 契约，调度 I/O 语言中立
  （枚举 ID，不传中文主张——Needle 官方无中文主张）。
- 每个组件调用 = 一次 schema 约束生成（json_schema + AbortSignal，
  wllama 3.8.1 已具备）；§2 的候选接口就是各组件的约束 schema 来源。
- 防循环参数挂在调度层：每请求重试 2 次、一回合 20 次上限，超限触发
  §4 场景一的暂停路径。
- 接入前置检查（既有开放项）：Needle 3 浏览器工件确认、中文路由测试。

## 6. 开放问题（评审时定）

1. **决策组件 vs 叙事组件产出 options**：本稿默认归决策组件（叙事纯正文，
   有 narration-only 试验支撑）；若叙事组件连选项一起产出，回到
   monolithic 形态的已知风险。
2. **scene_prompt 去留**：背景图定位为游玩前联网准备后，运行时是否还
   需要 scene_prompt 字段；保留则归叙事组件附带。
3. **对话候选的结构化程度**：`dialogue` 数组 vs 正文内联引号对话（影响
   输出解析组件的输入形态）。
4. **`roll` 记录的后端校验深度**：本稿只校验 `result ∈ [1,20]` 与 target
   重推导；是否需要更重的防作弊（本地单机场景可能不需要）。
