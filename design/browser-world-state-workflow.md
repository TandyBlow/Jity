# 浏览器端侧小模型游戏工作流开发方案

版本：v0.4.1（协议 v2 修订计划）。日期：2026-10-22。补齐点内多单元工作游标、冻结原文接续、时间候选锁定与逐操作 gate 门槛。具体决定见 [v2 修订清单](world-protocol/v2/README.md)；v1 基线为 26011c8，原 S1 候选为 07924f3。修订后的 S1 已经 B 对 11 决定/32 操作消费复核并正式验收，IF-05 已放行，证据及验收快照见 [change-list](world-protocol/v2/change-list.md#b-最终复核与-s1-正式验收2026-10-22通过)。A 下一步 IF-03/04a，B 下一步 IF-05；v2 SQL、轨迹、正式 transport 与运行服务仍待后续任务落实，完整接口基线尚未冻结。

依据：本次对话中用户提供的十一部分新设计及最后关于模型分工的补充。
本文是开发方案，尚未实施。文中“建议”“暂定”表示实施建议，不代表用户已经确定了对应规则。

## 一、开发目标与设计边界

开发一套以世界状态为基础的游戏系统。程序决定执行顺序、管理时间线、验证并应用变化；浏览器内的小模型负责人物判断、行动和结果生成、自然语言状态变化以及叙事表达。

世界演进遵循：

```text
初始世界 S₀
  → 玩家输入
  → 冻结人物行动顺序
  → 逐人物判断、生成行动、处理被迫行动、结算
  → 按固定顺序更新状态
  → 合并并提交时间点增量 Δₜ
  → 得到 Sₜ，生成本时间点叙事
  → 判断是否继续推进
  → 新的时间点，或交还玩家
```

必须保留以下规则：

1. 地点、物品、人物在开局时全部确定，运行中只能更新已有实体。任务允许在已有大任务下增加小任务。
2. 地点具有初始嵌套位置、自然语言外貌及所包含的地点、物品、人物；物品具有初始嵌套位置和自然语言外貌；人物具有初始嵌套位置、外貌、任务、个性、理智值及包含的物品。
3. 初始外貌和个性不可改写；后续保存变化。位置变化保存新的结构化位置。
4. 长期世界事实由 S₀ 与各时间点的 Δ 构成；当前状态、摘要和检查点只能作为可重建的缓存。
5. 每个时间点中，同一实体只保存一份合并后的变化。
6. 新的非关联时间点按理智值从低到高排序；关联时间点延续已冻结的顺序。
7. 被迫行动按骰点决定是否提前；共同结算组先确定全部人物及其行动，再统一结算。
8. 已完成行动的人物不会因后续攻击再次行动；骰点仍可影响攻击者的结果。
9. 更新顺序固定为位置、外貌、任务达成、新增小任务、个性、理智值。
10. 自动推进只由大概率发生且与主角关联的后续行动触发。
11. 每个完成的时间点都生成叙事；叙事只表达已结算的世界事实，不能反向修改世界。
12. 不维护独立的“人物已知信息”状态；人物认知由模型根据当前世界状态判断。
13. 自然语言行动描述只供本次分析使用，不另建长期行动历史。
14. 一项工作不等于一个模型。程序步骤、模型调用次数和实际加载的模型数量分别设计。

新方案替代旧稿作为新世界引擎的开发依据。旧版六组件划分、由正文抽取世界更新的路径、Needle 3 接入顺序，不自动继承为新方案要求。

本轮确定的开发处置：**CAMP Phase 6–8 暂停新增开发，不与新引擎并行推进**；保留旧引擎运行、存档和历史计划，既有缺陷不因切换方案而宣称已验收。当前开发入口改为本方案阶段 0，`CLAUDE.md` 与 `.planning/STATE.md` 同步标记；未来恢复 CAMP 需另行排期。

## 二、总体架构与现有代码的关系

建议保留现有 Next.js / React / TypeScript 前端、FastAPI / Python 后端和 SQLite，新增独立的世界引擎协议，先在独立实验页面完成闭环。

| 部分 | 职责 | 是否调用模型 |
|---|---|---|
| 浏览器工作流控制器 | 人物排序、行动游标、被迫行动队列、共同结算、自动推进、取消与恢复 | 通过固定接口调用 |
| 浏览器模型运行层 | 加载模型、约束输出、推理队列、取消、设备能力探测 | 是 |
| 世界状态内核 | ID 校验、位置图、任务树、增量合并、apply、状态重建 | 否 |
| 持久化与提交服务 | 初始世界、时间点、幂等、并发版本、工作流检查点 | 否 |
| 叙事与界面 | 根据已提交的状态生成并展示叙事、历史状态查看 | 叙事生成调用模型 |

模型没有直接写数据库或自由安排工具调用的入口。浏览器提出候选，后端在一个事务中验证结构、计算新状态并提交。确定性校验不应宣称证明了自然语言因果关系。

首个切片选择 **Python 为唯一状态计算权威**：apply、六步候选应用、增量合并和回放只在 Python 实现。浏览器控制人物与模型调用顺序，持有 Python 返回的只读工作状态；每个更新阶段调用无持久化副作用的 `preview` 接口，提交时由同一套 Python 函数从权威基线重新计算。TypeScript 只做协议类型、schema 检查和只读展示，不再写一套 apply。其网络开销纳入阶段 4 的整链测量；全离线和双语言内核移出首版范围。

现有代码的复用范围：

| 现有位置 | 处理方式 |
|---|---|
| `frontend/src/lib/benchmark/wllama-loader.ts` | 参考并提取模型加载适配；保持基准测试入口可用 |
| `frontend/src/lib/benchmark/runner.ts` | 复用设备信息、推理耗时、取消等测量方式 |
| `frontend/scripts/run-task-trial.mjs` | 复用结构化任务试验方法，新建符合本设计的数据集 |
| `frontend/next.config.ts` | 当前隔离响应头只覆盖 `/benchmark`；新推理页面需要单独配置并验证 |
| `backend/app/services/commit_turn.py` | 复用幂等、父节点与版本绑定、单连接事务的设计经验；新协议独立实现 |
| `backend/app/database/timeline.py` | 复用事务组织经验；旧表以完整快照和剧情树为中心，不直接当成新的增量时间线 |
| `backend/app/services/game_state/manager.py` | 旧版按名称合并、自动数值恢复、从正文推导事实的逻辑不适用于新引擎 |

旧存档继续走旧引擎。新世界显式标记 `engineVersion` 和 `schemaVersion`，首版不做无法保证无损的旧存档转换。当前分支旧提交链路的独立复验仍是旧模块自己的验收事项，不能用已有测试通过代替新引擎验收。

## 三、初始世界与实体结构

### 3.1 固定实体登记表

每个实体使用稳定 ID，名称只是展示字段。允许重名，模型引用实体时必须返回 ID。

```ts
type EntityId = string;
type TaskId = string;

interface WorldInitialState {
  engineVersion: string;
  schemaVersion: number;
  worldId: string;
  protagonistId: EntityId;
  initialTime: WorldTime;
  locations: Record<EntityId, InitialLocation>;
  items: Record<EntityId, InitialItem>;
  characters: Record<EntityId, InitialCharacter>;
}

interface InitialLocation {
  id: EntityId;
  name: string;
  parentLocationId: EntityId | null;
  initialAppearance: string;
  slots: SpatialSlot[];
}

interface InitialItem {
  id: EntityId;
  name: string;
  initialPosition: Position;
  initialAppearance: string;
  slots: SpatialSlot[];
}

interface InitialCharacter {
  id: EntityId;
  name: string;
  initialPosition: Position;
  initialAppearance: string;
  initialPersonality: string;
  initialSanity: number;
  tasks: Record<TaskId, Task>;
  slots: SpatialSlot[];
}

interface SpatialSlot {
  id: string;
  label: string;
}

interface Task {
  id: TaskId;
  ownerId: EntityId;
  parentTaskId: TaskId | null;
  goal: string;
  status: "pending" | "achieved";
}
```

包含人物、物品、子地点的列表由位置关系计算，可以在读取接口中一并返回。避免同时维护“钥匙属于外套”和“外套包含钥匙”两份独立真值。

死亡、损坏、耗尽等只能改变已有实体的状态或描述，不能删除其历史身份。实体计数包括这些实体，不能通过删除一个实体再创建另一个来绕过固定集合规则。

首版不引入用户未规定的整套生命值、伤害、经济和物理数值系统；行为能力首先由行动判断读取当前外貌等状态决定。后续若需要结构化生命状态，应作为明确的协议扩展设计。

### 3.2 嵌套位置与相对位置

建议使用“唯一包含父节点 + 可选局部位置 + 可选相对参照”，再由程序计算完整嵌套路径。

```ts
interface Position {
  containerId: EntityId;
  slotId: string | null;
  relativeTo: {
    entityId: EntityId;
    relation: "under" | "above" | "beside" | "in_front_of" | "behind";
  } | null;
}
```

例如，钥匙的直接位置为 `containerId=外套，slotId=左侧口袋`；外套位于主角身上，主角位于教室。读取时展开为：

```text
钥匙 → 左侧口袋 → 外套 → 主角 → 一号教室 → 二楼 → 学校
```

黑板下的钥匙则为 `containerId=一号教室，relativeTo={黑板, under}`。黑板若需要被独立交互或作为结构化参照，必须在开局登记为物品。口袋可以作为外套开局确定的局部位置，不增加第四类实体。

位置校验必须保证：父节点存在、局部位置属于指定父节点、相对参照在合法空间内。统一建立依赖图：地点 `地点→parentLocationId`、人物/物品 `实体→containerId`、相对位置 `实体→relativeTo.entityId`，对三类边的并集做环检测，禁止自环及跨边成环，不能只分别检查地点树和包含树。人物移动时，其携带物品的完整路径自动变化，不给每个后代伪造一次直接位置更新。

同一结算的多个位置变化必须在候选最终位置图上统一校验，支持同时交换位置。参照物移走时，依赖它的相对关系必须在同一候选中更新或明确清除，不能静默产生悬空关系。

例如“钥匙在黑板下”产生 `钥匙→黑板` 的参照边；随后把黑板放进钥匙会产生 `黑板→钥匙` 的包含边，必须拒绝。`relativeTo` 只登记单向定位依赖，不自动添加反向的“黑板在钥匙上方”边；物理关系的对称表达不能被误写成双向依赖。

地点树首版作为初始拓扑固定；用户规定的运行中位置更新对象为人物和物品。若后续需要移动建筑等能力，再扩展这一边界。

### 3.3 初始世界生成与封存

开局采用分阶段生成，避免要求小模型一次输出整个世界：

1. 根据世界设定生成地点树和人物、物品清单，分配 ID。
2. 分批补齐所有实体的初始位置和自然语言描述。
3. 生成每个人物的初始任务和个性，再根据个性生成理智值。
4. 验证位置图、任务树、引用完整性、字段覆盖及设定一致性。
5. 允许在开局草稿阶段修订；确认开始游戏后封存 S₀ 与实体登记表。

初始世界应当完整描述本局范围，不声称能穷尽无限世界。首个验证世界建议使用学校场景，约 6 个地点、10 个物品、4 个人物；这是实验规模，正式容量由测量决定。

运行中涉及新实体的行动应由模型倾向生成失败结果，也可以产生合理的部分失败后果。提交层始终禁止未知实体 ID。结构化输出引用合法 ID 只能防止结构越界，不能单独证明正文没有暗中创造新实体，需要模型评测与人工检查。

## 四、自然语言增量与任务变化

### 4.1 外貌、个性的变化记录

初始段落保持原样。每次新增变化使用稳定变化 ID，并引用被替代或解除的既有变化：

```ts
interface DescriptionChange {
  id: string;                 // 服务端程序分配，模型无权生成
  text: string | null;        // null 表示只解除旧变化
  supersedes: string[];
}

interface EntityDelta {
  entityId: EntityId;
  positionSet?: Position;
  appearanceChanges?: DescriptionChange[];
  personalityChanges?: DescriptionChange[];
  sanitySet?: number;
  tasksAchieved?: TaskId[];
  subtasksAdded?: Task[];
}
```

例如初始“面容清秀”不变；先追加“嘴角开始流血”，后来追加“嘴角已止血”，后者可以引用并解除前者的活动效果。所有历史变化保留，当前视图显示初始描述与当前有效变化。

`supersedes` 是为恢复、覆盖和相互矛盾变化提出的实施机制。涉及初始描述的变化可以直接表达“外套被脱下”“不再乐于助人”，不修改 S₀；首版不强迫模型把初始自然语言切成结构化断言。

持久化 `supersedes` 的规则固定如下：

- 只能引用同一世界、同一实体、同一字段中已存在的变化；外貌与个性不可交叉引用。
- 被引用变化必须来自严格更早的已提交时间点，并且在本次应用前仍然有效；拒绝未知、自身、未来、同点、已失效和重复引用。
- 同一实体同一字段的一个时间点内，每个旧变化最多被解除一次；不同新变化不能重复消费同一 supersedes 目标。
- 只解除不追加描述使用 `text: null`，且 `supersedes` 必须非空；`text: ""` 或纯空白文本始终非法。有文本时可以不替代旧变化，表示新增效果。
- 解除个性变化同样算个性发生变化，必须满足阶段 5 的任务触发条件并重算理智。初始描述不是变化记录，没有可供 supersedes 引用的 ID。

同一点内的中间变化使用程序分配的临时引用，只存在于工作态。合并时将临时引用折叠为最终记录：例如本点先流血再止血，只保留最终变化及其对更早时间点有效变化的解除引用，不能把临时引用或同点链写入 `supersedes`。不能产生与工作态等价的合并结果时拒绝提交并重算；这一组合行为单独设置夹具。

程序可以确定变化引用和生效顺序，不能完全理解“身体不适”是否已经被“恢复健康”涵盖。当前状态的自然语言一致性仍需单独评估。长文本摘要只作为派生缓存，保留源变化 ID，并允许丢弃重建。

### 4.2 任务树

初始大任务可以有任意数量的小任务。每个任务至多有一个父任务，任务树不得有环。新增任务必须挂在已经存在、属于同一人物的任务树中，不能运行中新增独立根目标。

新小任务是否有助于父任务，由模型给出简短关联依据供本次校验和评测使用。程序只验证父子结构及引用，不把“存在依据字段”当成目标有帮助的证明。

小任务达成不自动等于大任务达成；所有目标根据当前工作状态重新判断。首版建议达成状态单向变化，撤销达成需另定规则。任务层级是否只允许“大任务→小任务”两层，原稿未限制，建议数据结构支持多层，首个场景使用两层。

### 4.3 同一时间点的合并

在时间点内使用工作状态执行多次结算，最后按实体 ID 合并：

- 位置：保存本时间点最终位置；与时间点前相同则可省略。
- 外貌和个性：合并本时间点的有效变化及必要的替代引用，不覆盖此前历史。
- 理智值：保存最后一次合法值；与时间点前相同则可省略。
- 任务：tasksAchieved 只引用时间点开始前已存在的任务；本点新增任务只出现在 subtasksAdded，携带本点结束时的最终 status。本点新增又达成的 T 编码为 `subtasksAdded:[{...,id:T,status:"achieved"}]`，不得同时放入 tasksAchieved。同一 ID 重复、两集合交叉或新增记录覆盖旧任务均拒绝。
- 同一共同结算内部的相互冲突候选必须重算，不能按模型输出顺序随意“后者胜”。

合并器必须验证：对时间点前状态应用合并 Δ，结果与工作状态的“可提交投影”相同。投影由 Python 折叠本点临时变化、解析最终 ID、移除临时中间记录后得到；原始工作态的临时引用表不能直接参与状态摘要，也不能作为历史事实保存。比较必须覆盖所有当前实体属性、有效描述变化和任务，而不是只比较展示文本。同一时间点中的细小中间过程可能不再可还原，这符合状态回放不要求复原每个动作经过的要求。

同点新增父子任务的 ID 均由程序预分配，subtasksAdded 按父先子后的拓扑序排列；同层任务按 ASCII ID 升序打破平局，形成唯一编码。父任务可以来自旧状态或该数组中更早的新增记录；禁止环、跨人物挂接及重复 ID。合并后的 Δ 是最终状态变化编码，不是六个模型阶段的调用记录：apply 验证并原子构造整个候选任务树，再为旧任务应用 tasksAchieved；新增任务使用自身最终 status，不为它伪造第二次达成操作。六步生成顺序仍不改变。

阶段候选中新增任务一律为 pending，只有后续真实任务扫描才能把本点已新增任务判为 achieved；合并器才可生成上述最终 achieved 编码。提交时以阶段候选复算，确认相应达成曾触发本次个性/理智检查；不能仅凭合并记录的最终 status 跳过这些检查。纯 Δ 回放直接恢复已结算结果，不重跑阶段或模型。

## 五、时间线、冻结顺序与瞬时时间点

### 5.1 时间点和调度轮次分别记录

建议引入内部 `roundId` 表示一次冻结顺序的有效范围。一个 round 可以拆成多个关联时间点，不能把“一个人物行动”“一个时间点”“一次玩家输入”混成同一个计数器。`kind` 只说明本段形态；`trigger` 只说明整个 round 最初由玩家还是自动推进触发，同 round 所有点继承相同 trigger，删除与 linked 重叠的 continuation 值。

```ts
interface TimelinePoint {
  id: string;
  previousPointId: string;
  roundId: string;
  advanceId: string;
  kind: "normal" | "instant" | "linked";
  linkedFromPointId: string | null;
  trigger: "player" | "automatic";
  timeAdvance: TimeAdvance;
  entityDeltas: Record<EntityId, EntityDelta>;
  settlementGroups: { groupId: string; memberIds: EntityId[] }[];
}

type RoundPhase =
  | "select_actor"
  | "build_group"
  | "settle_group"
  | "continue_round"
  | "assess_continuation"
  | "complete";

interface PendingGroup {
  groupId: string;
  pointId: string;              // 所属 PointWork，禁止跨点挪用冻结工作
  inputProjectionHash: string;  // 本单元行动/目标实际读取的 Python 工作态摘要
  initiatorId: EntityId;
  memberIds: EntityId[];          // 集合：唯一、ASCII 排序；不是入组顺序
  frontierIds: EntityId[];
  analyzedSourceIds: EntityId[]; // 集合；包含已确认空目标集的源，避免刷新后再次采样
  reactions: {
    sourceId: EntityId;
    targetId: EntityId;
    triggerKey: string;
    rollId: string | null;        // 先保存模型目标；roll 创建后关联，不复制 admission
  }[];
  closed: boolean;
}

interface PointWork {
  pointId: string;              // 预分配，最终提交仍使用此 ID
  kind: "normal" | "instant" | "linked";
  basePointId: string;
  baseVersion: number;
  baseStateHash: string;
  predecessorWorkDigest: string | null; // 前点尚未提交时，绑定其封存工作前缀
  timeAdvance: TimeAdvance;
  timeLocked: boolean;
  sealed: boolean;              // 封存后不再接收新单元或改候选
  workingCursor: number;
  workingActedIds: EntityId[];   // 含已提交集合与本点已暂存的行动
  workingVisitedIds: EntityId[];
  workingIntentStatus: "pending" | "consumed" | "expired";
  timeScanCandidateDigest: string | null; // 空点的完整时间扫描候选
  settledUnits: {
    groupId: string;
    memberIds: EntityId[];
    candidateDigest: string;    // 指向已保存的结果和完整六步阶段候选
    inputProjectionHash: string;
    outputProjectionHash: string;
  }[];                         // 有序、只追加；不等于世界已提交
}

interface RoundCheckpoint {
  roundId: string;
  advance: AdvanceContext;
  trigger: "player" | "automatic";
  order: EntityId[];
  cursor: number;
  actedIds: EntityId[];
  visitedIds: EntityId[];
  phase: RoundPhase;
  paused: boolean;               // 与 phase 正交，暂停不改变控制器位置
  pendingGroup: PendingGroup | null;
  pointWork: PointWork | null;
  successorWork: PointWork | null; // 只允许一个已封存前缀的直接后继预约
  conclusion: RoundConclusion | null;
}

interface AdvanceContext {
  advanceId: string;
  inputId: string;
  inputText: string | null;       // 整条输入链结束后才可清除
  intentStatus: "pending" | "consumed" | "expired";
}

type RoundConclusion =
  | { kind: "continue"; closedBy: "model"; cancelReason: null;
      candidateCharacterIds: EntityId[]; nextRoundId: string }
  | { kind: "handback"; closedBy: "model"; cancelReason: null }
  | { kind: "handback"; closedBy: "cancel"; cancelReason: string };
```

`RoundCheckpoint` 是恢复执行的程序元数据，不是第四类世界实体，也不是自然语言行动历史。`cursor/actedIds/visitedIds/advance.intentStatus` 只表示已提交进度；PointWork 的 working 字段表示本点已确认但未提交的进度，绝不能用后者提前覆盖前者。每点开始经 begin_point 保存基线和时间；stage_unit 保存每单元结果与完整阶段候选、推进工作游标，再允许分析下一人物。points 才按这些候选复算，将工作进度原子提升为已提交进度。所有中间变化走 §9.2 的窄操作，不能任意 PUT 整份检查点。

一个点可以顺序结算多个单元，`settledUnits` 保存本点已结算但未提交的有序列表；最终 `settlementGroups` 必须与其 groupId、memberIds 和次序完全对应。每项 memberIds 是 ASCII 排序的集合；根点没有结算单元。普通单人行动也有独立 groupId，组与点不能共用一个身份。工作表中的行动、目标、结果和候选在 stage_unit 后继续保留，直到 point 提交或显式 cancel，不能把“暂存”当成“消费”。

`build_group` 和 `settle_group` 要求 pendingGroup 非空；`settle_group` 要求 closed=true 且 frontierIds 为空。发现组时先持久化模型提出的目标与冻结行动，再执行判定和扩张；`build_group` 期间成员只增不减，闭组后 `settle_group` 只读成员、目标及行动。stage_unit 将闭组及结果候选移入本点 settledUnits，清空唯一的活动 pendingGroup，并走 settle_group→select_actor；它只推进 working 集合和游标，不更新已提交 actedIds/cursor，不删除冻结工作。`apply_updates` 只是内存步骤，不是持久化 phase；尚未 stage 的结果及阶段候选可以重算，已确认行动、目标及已 stage 候选均不可暗中改写。其余非法阶段/字段组合由 v2 schema 与事务服务约束。

正常多单元路径为：begin_point(P1) → discover/extend/close(A) → stage_unit(A) → select_actor(B) → discover/extend/close(B) → stage_unit(B) → seal_point(P1) → points(P1)。B 读取 Python 按锁定时间与 A 的已保存阶段候选重放所得工作态；刷新后从 settledUnits 恢复 A，不重复生成 A 的行动、结果或阶段候选。skip 通过 record_skip 只推进工作访问集合与工作游标；遇到 workingActedIds 中已行动的槽位由服务端跳过，不能再次行动。空点也须完成时间相关的六步检查，以单独保存的时间扫描候选提交，settledUnits 可以为空。

最后一个普通段或关联续段提交时，若所有原顺序槽位已访问、无 pendingGroup 且没有尚需创建的关联段，必须在同一事务保存 phase=assess_continuation，并签发该点的叙事认领与 gate。instant 段保存 continue_round，以创建约定保留的 linked 续段，即使续段没有剩余人物；这个空续段提交后再保存 assess_continuation。尚有剩余人物而未创建后继 PointWork 时保存 continue_round；已有后继工作时保存其 select_actor/build_group 阶段。phase 始终表示下一计算位置，叙事 gate 未解除时禁止执行计算；暂停/恢复等控制操作按 §9.2 门槛表独立处理。

叙事 gate 和 paused 均与 phase 正交，不再持久化 await_narration、paused 阶段或 resumePhase。`checkpoint_revision` 只表示控制器位置、游标、工作组或暂停状态的变化：point、点工作态创建/时间修改/封存、组发现/扩张/闭合/暂存、工作 skip、普通暂停/恢复及 round 启动/结束按各自事务递增。gate 的签发、清空和懒失效、叙事 ready/failed、claim 续期与换代一律不改变它。暂停不冻结或延长 claim TTL；暂停/恢复写入均可穿过叙事 gate，恢复响应分别返回暂停状态和 blockedReasons，重生成 ready 后才继续计算，详见 §9.2 门槛表。

conclusion 仅在 complete 时非空；assess_continuation 表示人物槽位已全部处理、pendingGroup 为空，等待模型判断后调用原子 round-conclusion 接口。complete 的持久化写入点只有该接口，不要求再创建一个虚假时间点。continue 记录下一 round 身份并在同事务创建它；handback 记录交还玩家并结束输入链。详见 §8.1、§9.2。

closedBy/cancelReason 是 conclusion 本体的必填字段，不另建来源列。模型结论必须 closedBy=model、cancelReason=null；手动取消只能为 handback、closedBy=cancel，cancelReason 必须含非空白字符。取消不得伪装 continue；历史视图按 closedBy 区分模型交还和玩家取消。持久化 CHECK 与 JSON Schema 均约束这三种组合。

advance 是跨 round 的控制元数据，不是世界实体；删除旧的 round 级 playerIntentConsumed。一次玩家输入分配一个 advanceId/inputId，后续 automatic round 继承同一上下文，不再初始化 pending。主角在本链第一个 round 中处理该输入的行动机会时（包括 skip 或被迫反应占用该机会）将 intentStatus 置为 consumed，表示输入机会已处理，不表示行动成功；这一变化与对应时间点一起提交。未处理输入被取消或直接交还时可置 expired。自动 round 必须继承 consumed；不满足时拒绝创建，不能靠提示词防重放。

新的非关联时间点开始时读取所有人物的当前理智值，升序排列。理智相同时建议按稳定 ID 排序，保证可复现。关联点中即使个性和理智改变，仍然继续原顺序。

### 5.2 时间表示

建议使用结构化世界时间与明确的推进量，不把故事时间写成数据库创建时间。普通推进支持秒、分钟、小时、日、月、年；月和年需要固定的世界历法规则，不能简单当作相同秒数。

瞬间使用符号顺序表示，例如 `(世界历时间, instantOrdinal)`。关联点边界标记为 `instant`，不随意杜撰为一秒；普通跨度由模型提出、程序校验后应用。首版采用公历、整秒精度，精确格式与数值规范见 §9.6。

```ts
interface WorldTime {
  calendar: "gregorian";
  dateTime: string;             // 世界本地时间，YYYY-MM-DDTHH:mm:ss
  instantOrdinal: number;        // 同一历时间内的先后次序
}

interface TimeAdvance {
  boundary: "elapsed" | "instant";
  duration: {
    amount: number;
    unit: "second" | "minute" | "hour" | "day" | "month" | "year";
  };
}
```

边界描述进入本段的关系，duration 描述本段结算持续时间。amount 不允许负值；零持续时间的关联边界仍按 instantOrdinal 推进。建议首版共同结算段持续时间为零，其结果若需要更长过程，留到后续普通或关联续段表达；这是瞬时段的实施约定，不是对所有行动持续时间的预设。

`timeAdvance` 属于 Δ。实体变化为空但时间有推进的时间点是合法结果。所有人物都未行动也应完成本次玩家输入对应的时间点，不能因为实体 Δ 为空而丢弃时间流逝。

每段开始先根据输入、段形态与已有状态提出 timeAdvance，通过 begin_point 保存到 PointWork，并绑定预分配 pointId、基线头/版本/状态摘要；由 Python preview 把新的世界时间应用到工作态，然后才判断该段人物行动并执行六步更新。首次确认行动、目标、skip 或时间扫描阶段候选时，在同一事务设置 timeLocked=true；rolls 只接受已锁定时间与已确认目标的工作。新非关联 round 的顺序仍按开段前理智冻结，时间推进不重新排序。时间只应用一次，后续每个行动的 preview 复用同一时间候选；最终提交从旧时间重算一次，不重复累加。

timeLocked=false 且没有任何已确认时间相关工作时，才允许 set_point_time；变更递增控制器 revision，丢弃尚未确认的内存输出，从原基线重新 preview。锁定后同 pointId 的时间、kind 和基线不可修改，即使 Δ 尚未提交；返回 point_time_locked，不删除已确认目标、不使原 roll 失效，也不改判定键。关联拆段时，前段保留已锁定时长，瞬时组采用 instant/0，续段在开段时另定时长。首版不为同段内每个人物再累计时间，也不提供链内“改时长后重新采样”路径。

锁定后确需改变时长，须显式使用已有 round-conclusion.cancel 结束输入链：同事务将活动及预约工作标为 abandoned、清除其工作指针并记取消原因，未提交结果不进入世界；保留已分配 ID、判定键及 roll 作为终止记录，不复用给另一工作。该操作仍要求当前头叙事 ready。之后的新玩家链分配新 advance/round/point 身份，属于明确取消后的新执行，刷新/重试不能自动走此路径。跨提交的预约基线按 §5.3 验证，不能把 C/D 原工作静默重绑到新时间或新头。

### 5.3 关联点分段

原顺序为 A、B、C、D、E、F，C 和 D 形成共同结算时：

```text
P1：普通点，记录 A、B 的结算变化
  → 瞬间边界
P2：瞬时点，记录 C、D 共同结算的变化
  → 瞬间边界
P3：关联续点，继续 E、F
```

三个点共享 `roundId` 和冻结顺序。D 已在共同结算行动，到原来的 D 槽位时跳过。P3 内的剩余行动可以有自己的持续时间，必须区别于 P2→P3 的瞬间边界；建议用 `boundary` 与 `duration` 两个时间字段表达，避免把关联边界误当整段持续时间。

下面给出固定字段夹具。S₀ 时间为 `2026-01-01T12:00:00`、instantOrdinal=0，三个点均由同一次玩家输入触发：

| 点 | kind | trigger | linkedFromPointId | boundary | duration | 提交后世界时间 |
|---|---|---|---|---|---|---|
| P1（A/B） | normal | player | null | elapsed | 2 second | 12:00:02，ordinal=0 |
| P2（C/D） | instant | player | P1 | instant | 0 second | 12:00:02，ordinal=1 |
| P3（E/F） | linked | player | P2 | instant | 3 second | 12:00:05，ordinal=0 |

P3 进入时先在 12:00:02 增加瞬间序号，再消耗本段 3 秒；历时间前进后序号归零。P3 的 boundary 必须为 instant，不能因为其 duration 非零写成 elapsed。新的独立 round 首点必须为 normal、linkedFromPointId=null、boundary=elapsed；同 round 后续点必须为 instant 或 linked，引用同 round 的直接前驱，并使用 instant 边界。回放和提交使用相同约束。

首版默认严格串行：P1 提交 → P1 叙事 ready → begin_point(P2)、发现/扩张组、闭组、结算和提交 → P2 叙事 ready → P3 行动和提交。P1 提交不以 C/D 全组分析完成为条件。若要在 P1 前保存下一段 C 的工作，必须在 C 的行动调用前通过 prepare_successor 封存 P1 前缀并创建独立 successorWork；它绑定预分配 P1/P2 ID、P1 预计版本与 Python 复算的提交后状态摘要、完整前缀摘要，以及 P2 固定的 instant/0 时间候选。C 必须从这份预计 P1 状态再应用 P2 时间后的投影读取输入，确认时保存 inputProjectionHash 和相同的时间绑定；不能先按 P1 时长确认 C，再将它挪到 P2。

prepare_successor 后 P1 不再接收新单元或修改阶段候选。P1 前只允许保存这一边界源已有的行动/目标及其确定性判定，不继续调用成员反应模型或闭组结算；若无法事先给出该绑定，就使用 P1 ready 后发现组的默认路径，不持久化未绑定的跨段冻结工作。points(P1) 必须核对实际 P1 ID、版本、前缀内容摘要及状态摘要与预约一致，同事务将 successorWork 提升为当前 pointWork，保留其 pendingGroup 与冻结文本；有组则 phase 保留 build_group，否则为 select_actor。前缀内容摘要只编码 P1 的时间、已保存候选、有序单元与工作进度，不含后继、checkpoint revision、暂停、gate 或所有权字段；它不是含完整控制绑定的请求幂等摘要，避免循环引用和 C 入组后摘要自行失配。任一绑定不符则拒绝 P1 提交，不重新采样或重绑 C/D；显式 cancel 可解除。P1 的 gate ready 后才继续 P2 模型计算。

叙事 gate 阻塞期间不发起下一段角色、结果、状态模型调用，也不做 speculative preview；已持久化工作可读取恢复。不能先写入 C 的攻击结果再补 D 的防御。流水线化留到后续实测与独立协议设计；边界检测已有工作的耗时与等待后组扩张的耗时分别进入 §11.3 报告。

若共同结算发生在首位或末位，原稿没有明确是否保留空的前后关联点。建议保留合法的时间边界，允许实体 Δ 为空；这些点同样生成叙事，界面可以视觉分组。

### 5.4 一条世界时间线

首版按用户规则维护一条追加式线性时间线，历史读取只读，不默认沿用旧剧情树的分支写入。历史点重新生成叙事不会改变时间线头。

“回放后从旧状态继续游玩”涉及截断或另存分支，不属于本次已确定规则；首版只实现历史查看和叙事重生成功能。

## 六、人物行动与被迫行动算法

### 6.1 普通行动

轮到人物时，模型读取含本段新世界时间的最新工作状态、人物任务和个性、链级 advance 上下文，返回 `act` 或 `skip`。只有 `act` 才生成自然语言行动描述。

主角的行动受玩家输入约束，不能把玩家命令当成已经成功发生的事实。排在主角前的人物可能使其原行动失效，主角行动时应重新分析。只有 intentStatus=pending 才能把玩家输入作为待处理命令；consumed/expired 时只作为触发背景，自动 round 禁止重新消费。整链刷新恢复同一个 advanceId，而不是另建一次玩家输入。

行动自然语言描述和模型目标集作为可清除的未提交工作态写入工作表，受当前租约与 epoch 约束；提交只清除本点实际消费的结算单元，不清除整个 round。它们不进入长期行动历史、Δ 或世界状态摘要，也不参与世界回放。主动调试采样可临时导出，默认关闭。

### 6.2 共同结算组构建

建议使用人物集合、待分析队列和有向关系去重表，由程序控制扩张：

1. 生成发起者行动，经 discover_group 保存并冻结，进入组及待分析队列；在目标分析模型调用前必须先确认该行动。
2. 模型分析已确认行动可能迫使哪些人物反应，返回目标 ID 及本次判断依据；在使用结果前通过 extend_group 保存该源的完整目标集（包括空集）及分析完成标记，确认后不再采样同一源的目标。同一模型调用一次返回行动与目标时，可以通过 discover_group 原子确认两者。
3. 程序检查 ID 和已分析关系，先算 roll，再算 eligibility，以纯函数 admission=f(roll, eligibility, 已锁定规则) 决定是否准入；一条 INSERT 写入最终 roll、eligibility、admission，禁止先插 NULL admission 再 UPDATE。
4. 目标尚未行动且通过：加入组，生成其反应行动，继续分析新行动。
5. 未通过：不加入组，保留原顺序；发起行动的后果会先进入工作状态。
6. 目标已经行动：不加入组、不再生成反应，骰点只作为本组结果计算的输入。
7. 队列清空且每个成员的目标集已确认、全部判定已落库后，通过 close_group 封闭组，进入只读 settle_group，统一生成结果，然后统一更新状态。

同一个人物在同一 round 中最多实际行动一次，资格检查使用 pointWork 的 workingActedIds，包含已暂存但未提交的单元。A→B→C→A 的环不能再次生成 A 的行动。每个人物的行动文本生成并确认后即冻结；组内人物受到后续威胁时，不重写、不再生成第二次行动，新的威胁只进入共同结果计算。同 epoch 刷新直接复用冻结行动；交接后由服务端核验来源并原样复制旧工作，文本 UTF-8 字节不变。成员、目标、判定相同不足以证明行动语义相同，不能据此调用模型重建。actionVersion 与反应依赖重检不进入首版。

对同一威胁关系重复分析或重试时复用骰点，不重新掷到成功。不同关系是否允许对同一目标分别掷骰应由骰点规则确定；首版按 `(worldId, roundId, groupId, sourceId, targetId, triggerKey)` 去重，triggerKey 由程序分配，不能用模型每次重写的行动文本生成。

原稿没有规定骰种、阈值来源、平局、修正项。阶段 0–3 的固定骰点夹具使用 `reaction-fixture-v1`，骰点和阈值都由带版本的夹具确定。首个真实掷骰基线暂定 `reaction-d20-v1`：程序均匀生成 1–20 的整数，固定阈值 11，骰点大于等于 11 则通过，无属性修正、不沿用旧选项的大成功/大失败规则。规则版本、参数与结果一同锁定，修改规则必须换版本；模型不掷骰，也不决定阈值。该基线不宣称已验证游戏平衡。

### 6.3 行动结果与六步更新

本段 timeAdvance 已先应用到工作态。普通行动或封闭共同结算组生成一个结果候选，随后严格执行：

| 顺序 | 更新内容 | 依赖 |
|---|---|---|
| 1 | 所有人物、物品的位置 | 当前状态与完整行动结果 |
| 2 | 所有人物、物品、地点的外貌变化 | 已更新的位置及行动结果 |
| 3 | 所有人物的全部任务是否达成 | 更新后的状态 |
| 4 | 已有大任务可能新增的小任务 | 任务判断结果及当前状态 |
| 5 | 所有人物可能发生的个性变化 | 仅在存在新达成任务时执行，扫描所有人物 |
| 6 | 个性发生变化人物的理智值 | 本次个性变化后的当前个性 |

没有人物行动的时间点仍执行流水线：步骤 1、2 为无操作，步骤 3 使用推进后的世界时间扫描所有人物的任务，步骤 4 判断新增小任务，步骤 5、6 按任务达成/个性变化条件执行。实体 Δ 是否为空必须在这些检查后才能确定。例如 11:59 前进一分钟后，“坚持到中午”可以达成，即使没有人物行动。

没有个性变化则不自动调整理智值；不继承旧版“每回合自动恢复”。任何人物的任务达成都可能影响任何人物，不得只检查共同结算成员或在场人物。

本版明确选择“新任务达成 → 可能的个性变化 → 对应人物理智重算”这条路径；理智首版为 0–100 的整数。**目睹惨状本身不直接扣理智**，也不新增绕过任务触发条件的个性更新入口。若该事件达成已有任务，则可经阶段 5、6 产生影响。这是本版的规则限定，不是遗漏一个直接理智补丁；未来若要允许事件直接影响理智或个性，需要显式扩展触发与更新协议。

每次普通行动或共同结算完成后，按六步生成工作候选，经 stage_unit 验证并持久化后，才允许后续人物读取更新后的工作状态；时间点结束时一次合并提交世界 Δ。候选暂存与世界提交是两种写入，不能因“只提交一次 Δ”而只在内存保留前面单元的结果。

任务扫描与个性扫描允许分批调用，但每个阶段必须有完整人物覆盖清单。批处理只优化模型调用，不可用“相关人物筛选”漏掉原稿要求的全局检查。

## 七、模型工作与调用组织

### 7.1 按职责定义接口，暂不固定模型数量

| 工作接口 | 主要输入 | 候选输出 |
|---|---|---|
| 初始世界生成 | 世界设定、规模和已生成清单 | 初始世界各部分 |
| 行动判断与生成 | 工作状态、人物、任务、输入 | 是否行动及自然语言行动 |
| 被迫行动分析 | 工作状态、某人物行动、组与资格 | 可能反应的人物及依据 |
| 行动结果生成 | 结算前状态、全组行动、骰点 | 共同结果候选 |
| 状态变化生成 | 当前阶段状态、结果、允许更新字段 | 位置、外貌、任务、个性、理智候选 |
| 继续推进判断 | 主角、当前世界和本轮状态变化 | 是否有大概率关联行动及候选人物 |
| 叙事生成 | Sₜ₋₁、Δₜ、Sₜ、主角视角约束 | 叙事文本 |

这些是软件接口，不是七个模型，也不要求七次调用。首版建议一个常驻生成模型、多个固定提示词和输出 schema；模型运行层串行执行，避免多个大权重同时占用内存。

可比较的调用组织：

- 合并“是否行动 + 行动描述”，但 `skip` 时不生成行动描述。
- 位置与外貌候选可在一次调用内分字段生成，程序仍按 1→2 应用；如果位置会改变外貌判断，拆开调用。
- 任务扫描批量返回全体人物结果；新增小任务作为后续阶段。
- 个性变化与理智值可以同一次调用生成，程序验证有个性变化才接受对应理智值。
- 共同结算结果、叙事保持职责分离，防止叙事抢先决定世界事实。

合并是条件默认：只有候选能满足 §6.3 的逐步依赖时才合并。位置改变会影响外貌判断时，必须先应用位置，再单独生成外貌；不能仅凭 schema 可同时容纳六字段就固定“一次调用跑完六步”。阶段 4 的合并臂必须同时含可合并和必须拆分的标注样本，调用范围与统计口径见 §11.3。

先测单模型、多提示词基线，再根据失败样本决定是否需要专用分类器、抽取器或更大生成模型。旧实验只说明旧任务上的表现，不能直接证明本方案的任务达成、共同结算或个性更新可用。

### 7.2 浏览器运行层选择

优先评估已接入的 wllama，减少首轮迁移。官方资料确认其支持浏览器 Worker、WASM 和 WebGPU；WASM 多线程需要 COOP/COEP 配置。具体能力必须在项目锁定版本及目标浏览器中实测，不能把运行时文档能力直接当成项目已验证能力。[wllama 官方文档](https://github.ngxson.com/wllama/docs/)

WebLLM 作为对照候选，其官方文档提供 WebGPU 推理和 Worker 接入；仅在同一任务、设备和输出要求下比较后决定是否新增运行时。[WebLLM 官方文档](https://webllm.mlc.ai/docs/)、[Worker 接入说明](https://webllm.mlc.ai/docs/user/advanced_usage.html)

模型先使用仓库已经做过实验的 Qwen3-0.6B，建议以 Qwen3-1.7B 作为容量对照。这两者均有官方模型卡；其存在及标称能力不代表浏览器中文工作流质量达标。量化权重来源、文件校验、聊天模板和运行时兼容性另行锁定。[Qwen3-0.6B](https://huggingface.co/Qwen/Qwen3-0.6B)、[Qwen3-1.7B](https://huggingface.co/Qwen/Qwen3-1.7B)

已核对本地安装的 `@wllama/wllama` 3.8.1 类型声明：支持 GBNF `grammar` 和 OAI 兼容的 `response_format.json_schema`，可据此实现 generateStructured。Qwen3 调用统一设置 `chat_template_kwargs: { enable_thinking: false }`，沿用 `run-task-trial.mjs` 的现有方式；实际提示模板及参数进入运行记录。输出格式合法性由受约束解码及 schema 校验保障，语义正确性另行评测；约束生成中止或截断仍算失败，schema 通过不等于状态变化正确。

运行层需要统一提供：

- `load`、`generateStructured`、`generateText`、`cancel`、`unload`。
- 输出 schema、实际参数、模型标识和版本记录。
- 下载进度、缓存命中、加载失败、内存不足和设备丢失处理。
- 推理序列化、过期请求丢弃、UI 不阻塞。
- 结构化生成能力探测。若所用版本不支持指定 schema，显式暂停或更换适配，不静默接受自由文本为状态更新。

浏览器前台存活、Worker 存活和持久化提交是不同问题。不要依赖 Service Worker 永久存活来保证工作流完成；官方文档也说明浏览器可能终止它。[WebLLM Worker 生命周期说明](https://webllm.mlc.ai/docs/user/advanced_usage.html)

### 7.3 小上下文与逐步扩展

首个小世界完整输入，作为正确性基线。再按任务构造上下文：行动读取人物及邻近空间、相关物品和任务；全局任务扫描逐批覆盖每个人物；个性阶段读取新达成任务及全部人物的个性。

所有调用携带固定实体登记表的必要 ID 约束，并能按 ID 获取完整状态。不能因为世界大就静默删去任务或人物；若上下文容不下，分批或报告容量限制。

自然语言摘要不是新的世界真值。摘要丢失、模型切换或缓存失效后，仍必须能从 S₀ 和 Δ 重建输入。首版不建设独立角色知识库。

## 八、继续推进与叙事

### 8.1 自动推进

完成一个时间点并生成叙事后，先处理本 round 尚未完成的关联续段；关联续段属于原冻结顺序，不重新排序。人物槽位全部处理后进入 assess_continuation，先判断是否继续，再通过 round-conclusion 操作将本 round 原子标为 complete；不能先要求 complete 才允许写入结论。

继续判断应返回候选人物、拟发生的行动和与主角的联系，供控制器作出继续决策。判断必须同时满足“行动大概率发生”与“和主角有关”；这些候选只用于当前判断，不作为长期行动历史。

结论必须持久化为 RoundConclusion：continue 保存候选人物 ID 和预分配的 nextRoundId，handback 保存交还决定。判断使用的拟行动长文本不保存。continue 在同一事务中结束旧 round、按当前理智冻结下一 round 顺序并创建 automatic 检查点，继承 advance/input 身份及 consumed 状态；handback 在同事务结束当前 round 和输入链、清空活动指针并交还玩家。只有手动重试尚未确认的判断才可能重新调用模型，已确认结论刷新后直接恢复，不能重跑并翻转 continue/handback。

新的非关联点重新排序并判断行动，不把继续判断里的候选当成已经发生的动作。主角自己可能自发继续，但不能无限重复最初输入。

建议加入可配置的自动点数、模型调用数和总耗时预算。达到预算时保存已完成时间点，显示“推进已暂停”，允许继续；这与剧情上“没有关联行动，交还玩家”使用不同状态，不能用预算耗尽假装世界没有后续行动。

continue 已确认但预算不足时，可以将同事务创建的下一 round 保存为 phase=select_actor、paused=true；不得将它改写为 handback。结论尚未确认就遇到预算时，保存 phase=assess_continuation、paused=true；恢复后才进行判断。链处于活动或暂停状态时，不接受另一条新玩家输入链，需继续或显式结束当前链。

暂停、取消、重试都不能重新掷骰、重复消耗玩家输入或重复提交时间点。

### 8.2 叙事只读

叙事接口只接收状态和增量，不授予状态写入能力。允许选择性描述、隐藏秘密或作暗示，不能创造未结算的实体、物品获得、移动、任务完成或具体对话承诺。

“叙事不能改库”可以确定性保证；“叙事没有说出虚构事实”不能只靠 schema 保证。需要状态对齐样本评测和人工抽查；必要时增加校验调用，失败则只重生文本。不能从叙事抽出新变化补回 Δ。

时间点提交时，同一事务将该点 `narration_status=pending`、`narration_generation=1`，签发 head claim（令牌、有效期、当前 fenceEpoch），写入世界 gate，并保存下一控制器 phase。提交后通过叙事任务接口取回已签发认领再调用浏览器模型；该读取不换代。生成失败时将点标记 failed，phase 不变，下一段仍须等当前头叙事 ready；重试只签发新叙事代次，不重跑已完成行动。

状态只允许 `pending → ready/failed`；重试、失效重领和重新生成时增加 narration_generation 并回到 pending。写回必须匹配当前代次、任务令牌和签发 epoch，旧代次成功或异常都不能覆盖新代次。ready 确认只更新叙事状态、缓存及匹配 gate，不改 phase 或 checkpoint_revision；历史点叙事重生成也不修改当前 round。具体表及接口见 §9。

主动重生成或删除当前头的 ready 叙事只允许在完整时间点之间的稳定边界，并校验推进租约及检查点 revision；操作本身只更新叙事代次、认领和 gate，不改 phase 或 revision。正在计算且尚未 stage 的内存候选必须先丢弃；已 stage 前缀、冻结行动/目标、时间锁与所属基线保留，不能边推进边更换其叙事门槛。历史点重生成不设置当前 round 的叙事门槛。首次 POST /worlds 在同一事务创建 S₀、根点、初始头、初始推进租约与 generation=1 的 head claim/gate；响应返回有效租约及认领身份。根点 previousPointId/roundId/trigger 为空且没有 Δ，不存在无人签发的 generation=0 等待态。TimelinePoint 类型表示根点之后的推进点，根点使用单独 schema。

当 Δ 只记录时间流逝、没有留下动作证据时，叙事允许只描述时间和当前状态，不要求重现“敲门但无人回应”等具体经过。若将来要求精确复述失败动作，必须另行决定是否增加可保存的结果信息，不能偷偷保留完整行动历史。

时间推进也可能产生 tasksAchieved 及个性/理智变化，不需要有动作证据才允许叙述。叙事可以写“时间过去，目标已经达成”，并表达 Δ 中确有的联动变化；不得为解释达成而编造未结算的行动或具体经过。

## 九、持久化、提交与回放

### 9.1 建议数据表

| 表 | 主要内容 |
|---|---|
| `worlds` | S₀、实体集合摘要、版本、当前头、当前状态派生缓存、active_round_id、checkpoint_revision；可空 gate `(point_id, generation, claim_token)`，与 phase 正交 |
| `world_points` | 单条时间线的序号、kind、前驱、round/advance、关联信息、时间增量、实体 Δ、提交后状态摘要、按结算次序的 settlementGroups；`narration_status`（pending/ready/failed）、`narration_generation`、`narration_claim_token`、`narration_claim_expires_at`、`narration_claim_mode`（head/history）、可空的 `narration_claim_fence_epoch` 和错误码 |
| `world_submissions` | 世界、请求 ID、operation_kind、advance_id、候选摘要、提交结果，唯一约束 `(world_id, request_id)` 保证不同操作也不能复用同 ID |
| `world_round_checkpoints` | 每 round 一行，联合主键 `(world_id, round_id)`；revision、冻结顺序、trigger、已提交游标/已行动/已访问集合、advance、phase、paused、pendingGroup、当前/预约 PointWork 引用与已确认工作清单、conclusion；保留 complete 行，每世界仅一个活动指针 |
| `world_point_work` | 持久化 PointWork：点形态、基线/时间及锁、working 游标/集合/输入消费状态、settledUnits 的有序结果与完整阶段候选、空点时间扫描候选、封存前缀摘要、预约前驱绑定；提交/废弃后的身份和判定引用保留最小终止记录 |
| `world_group_work` | 未提交结算单元的成员行动与逐源目标集；world/advance/round/point/group/member、fence_epoch、不可变 attempt、输入投影/时间绑定、内容哈希及服务端接受记录；普通读取仅当前 epoch；接管由服务端按已确认清单原文复制，保留来源指针；不参与回放 |
| `world_rolls` | 服务端生成的 rollId、advance_id、完整判定键、规则版本、骰点、阈值、资格基线与最终 eligibility/admission；一条 INSERT 定稿、不可更新；不保存行动长文本 |
| `world_leases` | `world_id` 主键、`holder_id`、随机 `lease_token`、单调递增 `fence_epoch`、`expires_at`；每世界一行，过期也保留 epoch |
| `world_id_allocations` | 世界、`allocation_key`、种类、程序分配的 ID；唯一约束 `(world_id, allocation_key, kind)` 使重试返回同一 ID |
| `world_narrations` | 可删除的文本缓存，主键 `(world_id, point_id, generation)`；存文本、模型与提示词版本，状态真值只在 world_points |
| `world_state_checkpoints` | 可删除重建的稀疏状态缓存，可在较后阶段实现 |

world_state_checkpoints 是可重建的世界状态快照；world_round_checkpoints、PointWork 及其活动冻结清单是控制恢复真值，不能当作可删除缓存。它们不改变世界事实仍由 S₀ 与 Δ 定义这一规则，但未提交执行无法只靠世界回放重建。

world_leases 的获取和续约在短事务内完成：服务端时钟判断有效期，初次领取或过期交接分配新令牌并递增 epoch；同一持有者续约必须匹配令牌和 epoch，不能只凭 holder_id 续约。释放只清空持有者并使令牌失效，epoch 不回退。world_points、world_submissions、world_rolls、分配记录和检查点均使用对应世界的联合约束，禁止跨世界引用。

根点与推进点共用 world_points，不另建根表。根点行 kind=root、序号=0，previous_point_id/round_id/advance_id/trigger/linked_from_point_id/time_advance/entity_deltas 均允许且要求为 NULL，settlementGroups 为空，S₀ 只存 worlds；普通行序号>0，前驱/round/advance/trigger/time_advance/entity_deltas 必须非 NULL，kind 为 normal/instant/linked。用 CHECK 明确区分两种行，而不是给 round_id 全表加 NOT NULL。联合唯一键 `(world_id,id)` 支持同世界前驱外键；根点使用部分唯一索引 `UNIQUE(world_id) WHERE kind='root'`，推进点使用 `UNIQUE(world_id,previous_point_id) WHERE previous_point_id IS NOT NULL` 保证每个前驱只有一个后继；另外唯一约束 `(world_id,sequence)`。创建世界、根行、初始头、租约、根点认领及 gate 在一个事务完成，根点叙事 ready 前不创建首个 round。v1 的 round_requires_ready_head 触发器不能直接搬到 v2：过期/失效认领须由事务入口 resolve_gate 处理，ready 检查与完整控制器约束在同一服务事务内完成，并用 SQL 集成测试证明根点门槛不会被绕过。

推进租约默认 TTL=120 秒，每 20 秒续约一次。叙事认领默认 TTL=180 秒，同样每 20 秒独立续期；同一 lease 的成功续约不改变 epoch，同一 claim 的成功续期不改变 token/generation。head 模式 claim 签发时持久化当前 fence_epoch，确认与续期时要求它等于当前有效租约的 epoch，且 leaseToken、claimToken、generation 均匹配；history 模式签发时 epoch 为 NULL，仅受自身认领控制。认领模式签发后不能根据确认时是否仍为当前头而切换。

租约到期但未交接也不能原 epoch 续命；重新领取会增加 epoch，旧 head claim 随即失效。新持有者可立即重领已失效 epoch 的 claim，无需等其 180 秒到期，换 token、增加 generation 并记录新 epoch；旧代次成功或异常不改状态。正常推理期间两套心跳独立运行，避免长生成反复因 TTL 过期重启。若浏览器被挂起导致续约中断，则暂停并重领，不承诺后台任务永远存活。

head 表示签发时的世界头，不表示必须存在 advance。根点使用 head claim，advanceId=null、fenceEpoch 必须非空；普通头点的 advanceId 指向该点所属链。根点确认只开启首个 round 的叙事门槛，不访问不存在的 round 检查点。history claim 的 advanceId 也可为空（历史根点），但 fenceEpoch 必须为空。原 v0.3 的 advance 认领模式名不再用于新 schema。

叙事缓存可删除，不是恢复世界的依赖；删除当前代次缓存必须同事务将 ready 改为 pending、增加代次并废弃旧令牌；当前头同步签发新 claim/gate，历史点保持 history 模式。发现缓存意外缺失时由叙事任务接口执行同样的原子失效，GET 只返回 cache_missing，不悄悄写库。正常长期存档不保存完整提示词、模型推理过程和行动文本；未提交工作文本按结算单元清理。

玩家输入上下文存在 world_round_checkpoints，不新增输入链表。当前活动 round 是该 advance 的最新控制状态；continue 事务将 advanceId/inputId/inputText/consumed 完整复制到下一行，旧 complete 行保留已确认结论。原始输入正文保留至整条 advance 链 handback 或显式结束，不能在某个 round 完成时删除；链结束事务清除该 advance 各行的 inputText，保留身份、消费状态及结论用于追溯。暂停不清除正文。world_points/world_submissions/world_rolls 都带 advance_id 便于跨 round 关联；这些控制信息不参与世界状态摘要，回放也不执行输入。

### 9.2 新接口

建议采用 `/worlds` 命名空间，不复用旧 `StoryOutput` 请求结构：

```text
POST /worlds                         封存已验证的初始世界
GET  /worlds/{id}/context            获取头、版本、状态及调度检查点
PUT  /worlds/{id}/checkpoint         绑定头、revision 与租约，启动/暂停/恢复或执行组工作态窄操作
POST /worlds/{id}/round-conclusion   原子保存 continue/handback、结束旧 round，并创建后继或交还玩家
POST /worlds/{id}/lease              获取或在到期后接管推进租约
PUT  /worlds/{id}/lease              匹配令牌与 epoch 后续约
DELETE /worlds/{id}/lease            释放匹配的租约
POST /worlds/{id}/ids                幂等分配 advance/input/round/group/task/change/point/trigger ID
POST /worlds/{id}/preview            Python 计算候选工作状态，不持久化世界变化
POST /worlds/{id}/rolls              按判定键生成或取回固定骰点
POST /worlds/{id}/points             提交一个完整时间点的增量与检查点
GET  /worlds/{id}/points             读取时间点列表
GET  /worlds/{id}/state?point=...     重建历史状态
POST /worlds/{id}/points/{pointId}/narration-jobs
                                    取回已签发认领；仅失效重领/失败重试/重生成时换代
PUT  /worlds/{id}/points/{pointId}/narration-claim
                                    绑定认领及签发 epoch 后续期，不改变代次或令牌
PUT  /worlds/{id}/points/{pointId}/narration
                                    匹配 generation、claimToken 后提交文本或失败码
GET  /worlds/{id}/points/{pointId}/narration
                                    读取叙事状态、代次与当前代次文本
DELETE /worlds/{id}/points/{pointId}/narration
                                    删除缓存并使对应代次失效，不删除世界事实
```

preview 请求携带基线头/版本、本段此前各阶段的状态候选及当前阶段候选。Python 从库中权威基线按固定阶段重新应用，返回 workingState、可提交的 pointProjection、合并增量以及 pointProjection 的状态摘要；不接受浏览器自行声明的工作状态作为基线。候选只含状态更新，没有自然语言行动历史。points 提交使用同一函数重算并与候选摘要比对，不信任 preview 已经成功这一事实。首版允许重复计算未提交阶段候选；行动与目标集另存工作表，不建立第二套 apply。

基线读取抽象为 Python 的 BaselineStore。阶段 2 使用服务端进程内的 FixtureBaselineStore：启动时装载阶段 0 封存的 S₀、fixtureVersion 和内容摘要，建立根点及模拟头；固定候选确认后只更新进程内头和检查点，重启即丢弃实验进度，不声称支持崩溃恢复。最小 preview 路由按 worldId 读取这一基线，客户端不能上传任意 S₀ 替代它；fixtureVersion/摘要不匹配则拒绝。阶段 3 切换 SQLiteBaselineStore，preview 与提交复用同一组纯函数；生产环境不开放任意夹具装载入口。

preview 每请求默认最多重算 32 个结算单元（每单元含六步候选）、请求 JSON 上限 512 KiB、服务端计算预算 2 秒；任一超限返回明确的 preview_budget_exceeded，不部分应用、不改变基线或检查点。阶段 2 先用小世界验证；若实际规模超过预算，应调整配置或设计后续分段，不能静默截断人物/任务。预算版本及实际消耗进入性能报告。

checkpoint 写入绑定世界头/版本、expectedCheckpointRevision、有效 leaseToken/fenceEpoch 和 requestId；工作操作还须绑定 pointId 与已保存输入投影。除成功幂等重放外，改变控制状态才递增 checkpoint_revision。除启动玩家链及暂停/恢复外，只开放以下工作操作，不接受任意检查点覆盖：

- `begin_point`：在 select_actor（首点）或 continue_round（后继点）且没有当前工作时，保存预分配 pointId、合法 kind、基线头/版本/摘要与 timeAdvance；工作进度从已提交进度初始化，phase=select_actor。不能覆盖已有工作。
- `set_point_time`：仅在 timeLocked=false 且无已确认行动/目标/skip/阶段候选/roll 时修改时间；否则返回 point_time_locked。首次确认这些依赖工作与 timeLocked=true 同事务生效。
- `discover_group`：只允许 select_actor→build_group；原子保存预分配 groupId、所属点与输入投影、发起者行动、pendingGroup，并锁定时间。目标集若由同行动一次调用返回可一并保存，否则稍后由 extend_group 确认。已提交 cursor/order/actedIds/visitedIds/advance 消费状态和工作游标均不变；实体必须来自封存登记表，group/trigger 等新增 ID 必须来自当前作用域的分配记录。
- `extend_group`：仅在 build_group 内保存一个源的完整目标集或新准入成员行动及判定引用；新成员行动确认后才能分析其目标。已确认目标和行动不可改写，成员只增不减，不推进游标、不消费结果。工作写入与检查点 revision 在同事务更新；没有目标也须保存分析完成标记。
- `close_group`：所有目标分析完成、判定可复用且 frontierIds 为空时，原子置 closed=true 并只允许 build_group→settle_group。闭组的成员、目标及行动只读；允许 stage_unit 暂存其结算候选，只有 points 才能正式消费。
- `stage_unit`：仅从 settle_group 接受一次完整结果和六步阶段候选。Python 从 PointWork 的锁定基线、时间及全部已暂存单元复算，核对该组输入/输出投影和冻结工作清单；按顺序追加 settledUnits，更新 workingActedIds/workingVisitedIds/workingCursor/workingIntentStatus，清空活动 pendingGroup，phase 回到 select_actor。相同 requestId 返回原结果，同 groupId 改候选拒绝；保留组工作原文。后续单元读取复算后的工作态，绝不提前写世界 Δ 或已提交集合。
- `record_skip`：仅在 select_actor 记录当前合法槽位的 skip，锁定时间并推进工作访问集合、游标及必要的工作输入消费状态；不会给跳过人物增加 workingActedIds，已在该集合的人物槽位由程序直接跳过。
- `stage_time_scan`：仅在本点无活动组、settledUnits 为空且已到合法点边界时，验证并保存无行动点的完整时间扫描阶段候选，锁定时间，不增加 workingActedIds；不能以空点为由跳过任务/个性/理智检查。
- `seal_point`：仅在 select_actor 且无本点活动组时封存当前工作前缀，之后不能再追加/改候选；空点必须先保存完整时间扫描候选。`prepare_successor` 同时执行封存并创建 §5.3 的一个直接后继预约，不能覆盖已有预约；它不推进已提交游标。预约前驱提交前，不允许 stage_unit、record_skip 或成员反应模型推进后继。
- `restore_group_work`：接管者以有效租约和完整绑定请求服务端按已确认清单接续冻结工作，覆盖 pendingGroup 及已 stage 单元的引用；服务端验证来源行后，将行动原文、目标与已保存结果/候选逐字节复制到当前 epoch，记录 sourceEpoch/sourceAttempt/contentHash。浏览器不能提供替代原文或指定未确认旧行；只改变所有权副本，不改组、时间、游标、phase 或控制器 revision，请求不接受目标 attempt，由服务事务在 `(worldId,pointId,groupId)` 范围内跨 epoch 单调分配，并在成功 data 返回 pointId/groupId/fenceEpoch/attempt。请求主键为 `(worldId,requestId)`；业务去重绑定目标 epoch 与已接受来源清单（pointId/groupId/sourceEpoch/sourceAttempt/按 memberId 排序的 manifest），换 requestId 仍复用首次副本及 attempt。缺失或哈希不符返回 frozen_work_missing/frozen_work_corrupt，不能调用模型补写。

这些操作都不更新世界头/状态，不允许推进已提交集合、标记 complete 或跳过计算门槛。stage_unit/record_skip 只推进显式 working 字段；发现组或冻结文本本身不记人物已行动。每个工作写入、封存和时间绑定的变化都与控制器 revision 同事务递增，原文副本接续例外。第一次人物/模型调用前仍须记录 advance 身份、输入及冻结顺序；人物调用前还须保存其 PointWork 时间与基线。创建玩家链要求没有活动链、此前 round 已结束且当前头叙事 ready；automatic round 只能由结论事务创建。

工作操作按请求 pointId 或 pendingGroup.pointId 选择当前/预约 PointWork，不能混用工作游标。prepare_successor 将后继 working 字段从已封存前驱的最终 working 进度初始化，并立即锁定后继时间；前驱尚未提交时，只允许这个后继的边界源 discover/extend 及对应 rolls，不执行其他模型计算或 stage。此时事务请求仍绑定数据库当前真实世界头，后继预计基线另存预约字段；P1 提交后只将预约确认为已落地，不改变它原先的输入状态投影。

round-conclusion 请求绑定 `worldId + advanceId + roundId + expectedPointId + expectedVersion + requestId + expectedCheckpointRevision`，携带 `leaseToken + fenceEpoch`。事务先做成功请求的幂等查询，再核对绑定和有效租约，要求当前头叙事 ready、当前 phase=assess_continuation、所有槽位已访问且无 pendingGroup。continue 要求非空合法候选人物集合、预分配未用的 nextRoundId、intentStatus=consumed；同事务保存旧行 conclusion/complete，使用 Sₜ 的理智值冻结新顺序、创建继承 advance 的 automatic 行并切换活动指针。handback 保存结论并 complete，未消费意图置 expired，结束输入链并清除正文。两者均推进 checkpoint_revision、保存幂等结果，不移动世界头、不新增 Δ。刷新直接读取已确认结论及后继，不能再次调用模型改写结果；同 requestId 不同结论拒绝。

手动取消活动链使用同一端点的显式 cancel 操作：仍要求当前头叙事 ready、有效租约及全部绑定，从最近完整提交点结束输入链。事务将当前与预约 PointWork、全部未提交 settledUnits 及 pendingGroup 标为 abandoned 并清工作指针，记录 handback 与 cancel 原因、标记 complete，不改变已提交人物行动或世界状态；其 ID/roll/判定身份保留终止记录，旧请求不能复活这些工作。冻结工作副本在失去全部活动引用后才可清理。它可以结束 paused round，但不伪装成模型判断。正常 conclude 不允许绕过 assess_continuation，叙事未完成时可以持久化暂停但不能靠取消跳过叙事门槛。

叙事任务绑定已提交的 point、状态摘要、代次、固定认领模式及签发 epoch。首次认领均已由 points 或 POST /worlds 在创建点时签发 generation=1；narration-jobs 对有效认领只取回，不提供 0→1 领取路径。到期、失效 epoch、显式失败重试或请求重新生成时才增加代次并换令牌。正常长生成使用 narration-claim 续期，不以创建新代次充当心跳。head 模式取回/确认/续期核对有效推进租约与签发 epoch；history 模式只核对点级认领且不占用推进租约。文本缓存写入、point 变 ready 与匹配 gate 清除在同一事务完成，完全不修改控制器 phase 或 revision；根点无 round 也走相同路径。相同代次同文本重发可返回原成功，改变文本拒绝，旧代次或旧 epoch 一律不能改新状态。

`resolve_gate` 是事务内公共步骤，挂在 checkpoint、points、round-conclusion、narration-jobs 四个入口。先读成功幂等结果，再验证请求绑定、revision（适用时）及推进/head 操作的有效租约，然后用当前代次与 claimToken 核验 gate；history 认领只操作该历史点，不要求推进租约，也不清当前头 gate。ready 可清 gate；到期或 epoch 失效则记录 claim_expired/claim_fenced 并清匹配 gate；有效 pending 在 `blockedReasons` 中返回 `narration_pending`，并带 `gate.status=pending`。它只解析与清理门槛，不通用拒绝所有业务写入；调用方按下表决定操作权限。解析、清 gate 及认领换代均不递增 checkpoint_revision，因此不会撤销调用方自己的 revision 前提，也不另加 gate revision。

| 操作 | 叙事 pending/failed/失效时 | paused=true 时 | 成功写入与返回 |
|---|---|---|---|
| checkpoint.pause | 允许 | 已暂停则幂等不变 | paused=true；实际改变时 revision 递增，保留 phase/工作/gate；返回 blockedReasons 与 gate |
| checkpoint.resume | 允许；先执行 resolve_gate | 允许 | paused=false；实际改变时 revision 递增；返回 paused、revision、blockedReasons、canCompute，不因叙事未 ready 回滚恢复 |
| restore_group_work、只读 context | 允许接续/读取，不执行模型 | 允许 | 只做受控原文复制/读取；canCompute=false 直至 ready 且未暂停 |
| begin_point/set_point_time/discover/extend/close/stage_unit/record_skip/stage_time_scan/seal_point/prepare_successor、rolls、points、普通 conclude | 拒绝计算或推进，返回明确门槛状态 | 拒绝计算或推进 | 仅当当前头叙事 ready、gate 已解除且 paused=false 时执行；都仍需各自 phase/绑定校验 |
| round-conclusion.cancel | 仍要求当前头 ready | 允许 | 显式终止及废弃工作，不消费未提交结果 |
| narration-jobs、认领续期、叙事确认 | 按认领协议允许 | 允许 | 可取回/重试/完成叙事；不自动恢复计算、不改控制器 revision |

清 gate 仅表示没有有效在途认领，不把 failed/cache_missing 当成 ready。pause/resume 响应可以同时成功记录控制状态并报告 claim_expired，UI 显示“该段叙事已失效，可重新生成”；恢复不是启动计算的授权，canCompute 还必须检查 ready、paused、合法 phase 与有效租约。若纯推进操作被叙事门槛拒绝，已合法完成的失效清理仍提交，推进业务写入不执行；其他绑定/租约校验失败则不清理。暂停本身不冻结、续期或延长 claim TTL；已 ready 的文本不因旧 claim TTL 到期失效。

模型推理发生在浏览器。骰点建议由程序在服务端生成并按键记录，浏览器负责请求和展示，便于跨刷新、重复提交和多标签页保持一致；这不引入后端模型推理。若以后做全离线版本，应给本地骰点和存储实现相同接口，首版不并行开发两套存储。

提交必须绑定 `worldId + advanceId + expectedPointId + expectedVersion + requestId + roundId + expectedCheckpointRevision`，并携带有效的 `leaseToken + fenceEpoch`。流程为：

1. 开事务，先查幂等键；同内容重发返回原结果，不先因旧版本拒绝成功请求的重放。
2. 核对世界头、版本、round 检查点 revision 和当前租约令牌/epoch/有效期，执行 resolve_gate；当前头叙事未 ready 时不接受下一个时间点，gate 清理不改变本请求的 revision 前提。
3. 要求 PointWork 已封存且无属于本点的 pendingGroup，核对 settlementGroups 与 settledUnits 的身份、成员和次序；请求不得替换已确认的结果或阶段候选。验证所有实体、任务、描述变化引用及位置图和阶段约束；若有预约后继，校验 §5.3 的前缀和状态绑定。
4. 先应用 PointWork 锁定时间，再按已保存的有序阶段候选复算并归一化，空点使用已保存时间扫描候选；最后通过纯 apply 验证 Δ、实体集合不变、时间单调、摘要及工作游标推进合法性。
5. 同一事务保存时间点、settlementGroups、版本推进、当前状态缓存，将本点 working 游标/集合/输入消费状态提升为已提交进度，保存下一控制位置及 revision 递增、generation=1 的 head claim/gate 和幂等结果；只清理该点实际消费组的冻结文本/候选并保留最小身份记录。若有预约后继，同事务提升其指针并保留原有时间/输入投影绑定，不能清掉它。
6. 提交后才生成叙事、继续后续工作。

不同内容复用请求 ID 拒绝；过期候选拒绝并要求从新状态重算。未知 ID 或非法位置不是可忽略的小错误，不能悄悄删字段后提交。

字段权限按实体类型限制：地点只接收外貌变化，物品接收位置与外貌变化，人物接收位置、外貌、任务、个性和理智变化。人物出现个性变化时，生成流程必须完成理智重算；没有任何新达成任务时不接受该结算引出的个性变化。新增任务 ID 由程序分配，不能被模型拿来替代或覆盖已有任务。

### 9.3 ID 分配与判定身份

所有身份均由程序生成：worldId、初始实体/槽位 ID、advanceId、inputId、roundId、pointId、groupId、taskId、DescriptionChange.id 和 triggerKey 由服务端分配；requestId 由浏览器控制器生成并在该请求整个重试周期保持不变。rollId 不走 ids 预分配，由 rolls 接口在首次创建唯一判定行的同事务中生成并返回，同键重试返回原 rollId。模型只能引用已有 ID，不能生成持久化新 ID 或改变判定身份。

运行中的新增身份通过 ids 接口预分配。控制器使用稳定的 allocation_key，包含 round、段序号、工作种类、处理对象和逻辑输出槽位；同一槽位的重试沿用键，服务端返回同一 ID。威胁槽位按源/目标等稳定身份确定，不能因模型输出数组重新排序就变成新威胁。分配记录绑定世界和作用域，候选中错误种类、未分配、跨实体或已被别处消耗的 ID 拒绝。模型新增记录时返回受约束的输出槽位，由控制器将预分配 ID 填入，supersedes 则只能从已给出的有效历史 ID 中选择。

groupId 在第一次分析该组前分配，分析结果使用前由 discover_group 纳入 pendingGroup。triggerKey 在第一次请求某条威胁判定前分配并保存在已确认目标集中；规则版本与首次骰点同时锁定。完整判定键为 `(worldId, roundId, groupId, sourceId, targetId, triggerKey)`，world_rolls 上建立联合唯一约束。同键更改目标、规则或阈值拒绝，不能因重写行动文本而取得一次新的同义判定机会。

eligibility 由该组 inputProjectionHash、锁定时间/基线、确认时的 workingActedIds 快照和资格规则确定，包含此前已 stage 的行动，不能只读 round 已提交 actedIds。已入组的去重另行处理，不因恢复时已存在于 memberIds 就翻转原准入。服务端先计算 roll，再计算 eligibility 与 admission，用一条 INSERT 定稿；同键读取原行，不再 UPDATE。目标工作态保存规则/资格基线引用和 rollId，不复制 admission；恢复从同一快照与固定 roll 重算并核对原最终结果。预约组引用已存在的 PointWork 身份及预期前驱内容，不要求提前存在 world_points 行；P1 提交后只确认该引用已落地，不能换基线或重掷。若基线缺失或不匹配，明确报错，不能拿最新状态代替。

未提交候选被重算时可以复用其尚未消耗的分配；已提交 ID 永不重新分配给另一条记录。临时工作态引用和最终持久化记录种类区分，前者不允许出现在提交的 supersedes 中。

### 9.4 失败与恢复边界

原始行动描述不长期保存，但在未提交期间有受围栏保护的工作表。未 stage 的结果和阶段候选失败可从 Python 重放已保存工作前缀后重算，不能丢掉 A 再重新分析已读取 A 结果的 B。同 epoch 刷新复用已确认行动、目标、已 stage 结果及候选；未确认输出可以重试。行动确认前不得调用其目标分析，目标确认前不得 rolls 或扩张；同一结算单元内部的未确认阶段候选可顺序计算，但必须经 stage_unit 确认后才能供下一人物使用。分配的判定键和骰点不变，锁定时间不因重算而解锁。

恢复先读取活动指针及其 advanceId/inputId/intentStatus、输入正文和已确认结论，再决定继续哪个 round；不能只凭最新时间点创建一次新的玩家输入。旧 round 已 complete 且结论为 continue 时，恢复原 nextRoundId；handback 时不恢复自动推进。完成链的输入正文可以被清除，身份、消费状态和结论仍保留。

若组在 P1 提交后发现，discover_group 是其独立落库点；若在 P1 前发现，则 P1 保留其未消费工作。C 行动及目标已确认、D 已入组而 P2 尚未提交时，pendingGroup、phase 和工作表必须足以恢复，不能仅断言“前段提交时已保存”。roll 已插入但扩张尚未确认时，恢复按已保存目标与固定 roll 补做幂等扩张；尚未生成的 D 行动继续生成，已确认目标不得重新采样。settle_group 只重算结果与阶段候选，不能改变闭组成员或目标。

所有工作表写入（包括重试、删除和清理）在事务内检查 leaseToken/fenceEpoch 及检查点 revision；attempt 由服务端单调分配，已接受行不可覆盖。普通读取先限定当前有效 epoch，再取每个 `(world, round, point, group, member)` 最大已接受 attempt，不能先跨 epoch 取 max。每次确认工作时，服务端同事务记录其清单引用：身份、sourceEpoch/sourceAttempt、输入投影/时间绑定、原文及完整载荷 contentHash，并以当前检查点/settledUnits 引用为准，不能只凭表里存在一行就认领它。

接管使用 restore_group_work：服务端专门读取清单指定的旧行，核对其确由有效租约事务接受、仍被当前未提交工作引用、未消费/未废弃、作用域及全部哈希绑定一致，然后原样复制至当前 epoch。冻结文本逐 UTF-8 字节相同，结果/阶段候选也保持原值；复制与新来源记录原子完成，普通读取仍不暴露旧 epoch。来源行缺失/损坏则返回 frozen_work_missing/frozen_work_corrupt 并阻止继续，保留工作以待修复或显式 cancel，不能调用模型推测“相同语义”。当前 epoch 后续新写入仍受租约与 revision 保护，旧持有者的成功或失败清理均拒绝。被活动清单引用的旧行不得在交接或后台 GC 时删除，只有提交消费或显式废弃后才可清理。

首版每个世界同时只有一个有效推进租约，由 world_leases 承载。除成功请求的幂等结果读取及 POST /worlds 的初始租约创建外，所有推进写入（含 ID 分配、骰点分配、工作表、检查点改变）都必须在写事务内核对令牌、epoch 和有效期。租约交接后旧持有者的成功响应或失败清理都不能更新新持有者的工作；世界版本与检查点 revision 另行兜底。

### 9.5 状态回放

先实现无缓存的参考重建：`S₀ → Δ₁ → … → Δₜ`。再增加稀疏检查点，要求缓存路径和参考路径得到相同的规范化状态摘要。

读取某个历史点的叙事时，重建其 Sₜ₋₁ 与 Sₜ，读取 Δₜ，再调用只读叙事接口。不需要重跑人物判断、骰点、行动生成或任务结算，模型版本变化也不应改变已保存的世界状态。

### 9.6 规范化与状态摘要（world-canonical-v1）

阶段 0 固定如下规范，后续不得以库默认 JSON 输出替代。摘要为 `SHA-256(UTF-8(canonicalJson))` 的小写十六进制，同时保存 `canonicalVersion="world-canonical-v1"`。

1. 先按对应 schema 校验、展开默认值，拒绝未知字段、重复 JSON 键、非法 Unicode 代理项以及 NaN/Infinity。所有 schema 键与记录 ID 限定为 ASCII；字符串值保留原始 Unicode、空格和换行，不做 trim、NFC 或换行替换。
2. 首版所有数值均为有限安全整数，范围为 `[-(2^53-1), 2^53-1]`；理智另限 0–100，持续时间与 instantOrdinal 为非负整数。拒绝非整数；输入 `1.0` 归一为整数 1，负零归一为 0，不输出小数、指数或加号。dateTime 固定为世界本地公历 `YYYY-MM-DDTHH:mm:ss`，年份 0001–9999，不携带浏览器时区；月/年推进遇不存在的日取目标月最后一天，越界拒绝。
3. 对象键递归按 ASCII 升序输出。字符串用双引号；仅转义双引号、反斜杠和 U+0000–001F，控制字符统一写成小写 `\u00xx` 六字符形式；其余合法 Unicode 直接编码为 UTF-8，不转义斜杠、中文或 U+2028/U+2029。键值和数组元素间无空白，文件无 BOM、无末尾换行。
4. 数组默认保留顺序；order、settlementGroups 的结算单元次序和按时间追加的描述变化不能排序。schema 明确为集合的字段（例如 memberIds、actedIds、visitedIds、supersedes、tasksAchieved、candidateCharacterIds）先去重校验再按 ASCII 排序，重复输入拒绝；memberIds 不编码入组顺序，需要时从判定记录及扩张记录恢复，不依赖其数组位置。按 ID 表示的实体和任务使用对象映射，展示时的列表不参与摘要。
5. 完整状态规范化后不省略空字段：position 的 slotId/relativeTo 无值时为 null，各变化/任务集合为空时为 [] 或 schema 规定的 {}。增量 EntityDelta 则省略无操作可选字段（空变化/任务数组、没有实际变化的位置或理智），保留 `DescriptionChange.text=null` 这一有意义操作。任务按 §4.3 归一化：本点新增且达成只在 subtasksAdded 中携带 achieved，禁止同时出现在 tasksAchieved；新增树按父先子后、同层 ASCII ID 排序。时间导致的真实任务达成是有效变化，即使没有动作也不能当作无操作删掉。先验证引用合法性，再消除无操作，不能借规范化藏掉非法候选。
6. 状态摘要投影包含 engineVersion、schemaVersion、worldId、protagonistId、世界时间、完整初始实体描述与当前实体状态、任务和描述变化生效信息。未提交工作态先按 §4.3 产生 pointProjection，排除本点临时引用和已折叠中间记录；已提交状态直接使用相同的持久化形状。另排除世界头 ID、库行版本、租约、round 检查点、叙事、缓存、模型参数和墙钟时间，保证从同一初始世界和 Δ 回放得到相同摘要。
7. 提交内容摘要使用同一编码算法但不同 schema，包含候选、阶段候选序列、绑定、round 检查点及请求意图，排除所有权凭证 leaseToken/fenceEpoch 与叙事缓存。不同投影不混用；规范版本变化必须迁移或拒绝旧摘要，不静默重新解释。幂等结果只保存操作结果身份、状态及绑定摘要，不缓存 inputText，避免清理链正文后又从旧响应恢复它；需要当前上下文时重新 GET context。

Python 为规范化及摘要唯一权威。阶段 0 的 golden fixtures 必须覆盖乱序键、中文与 emoji、控制字符、1/1.0、负零、空字段、省略字段、集合排序与有序数组差异，并锁定规范字节与哈希。缓存路径、增量路径、重建路径、preview 与最终提交均对照这些固定向量，不只互相比较“看起来相同的对象”。

## 十、实施阶段与验收门槛

### 阶段 0：规则夹具与协议确定

产物：初始世界 JSON、实体与任务 schema、增量 schema、时间与关联点示例、固定人物行动和骰点夹具；phase/paused/pendingGroup 组合约束、独立 gate、组工作态窄操作、ID 分配规则、租约及叙事协议、world-canonical-v1 的规范字节/哈希夹具。v2 的 schema/SQL/测试必须成套更新；v1 现有通过记录不证明 v2 已通过。必须包含以下闭环规格：

- P0：末段提交保存 assess_continuation 与 gate → 叙事 ready 清 gate（revision 不变）→ 原子结论 → complete → 后继 round 或交还玩家的全部写入点、绑定和幂等结果。
- P1：advanceId/inputId/intentStatus 的跨 round 继承、输入正文整链保留及恢复协议；时间先应用、纯时间任务扫描及联动更新夹具。
- P2：同点新增又达成任务的唯一编码、新增父子拓扑顺序与 apply/workingProjection 等价夹具。
- 根点 NULL 列、CHECK、部分唯一约束及首个 round 的启动路径；lease/claim TTL、续期、签发 epoch 和交接规则。
- FixtureBaselineStore 的封存 S₀ 版本、摘要、进程内头更新协议及 preview 重算预算。
- 行动生成即冻结的首版规则，以及“C 拉入 D 后又遇到第二个威胁”的反例夹具；具体控制器在阶段 2 实现。
- 1b 与 5 一起冻结：PointWork 的已提交/working 游标分离、discover/extend/close/stage_unit/record_skip 的完整路径、目标集恢复、工作表清理粒度及 settlementGroups 的有序外层/集合成员规范。
- 2b 与 1c：gate 所有写入不改控制器 revision；POST /worlds 同事务签发根点 claim/gate，禁止根点停在无人领取的 generation=0。
- roll 单 INSERT 定稿、工作表 epoch 可见性、暂停后 claim_expired 的 UI 状态及故障注入夹具。
- 本轮四处封口：A/B 逐单元 stage 后合并提交；已确认清单与接管原文复制；时间锁及预约前缀跨 P1 提交验证；gate 门槛按暂停/恢复/计算分别定义。每项须有成功、响应丢失重试和绑定冲突夹具。

先用学校和钥匙示例确定包含路径，用 A→B→C→D 示例确定共同结算，用 A/B 前段、C/D 瞬时、E/F 后段确定分段。

验收：十一部分规则各有可执行示例；本文最后列出的实施参数有明确默认值和版本。明确 Python 是唯一 apply/merge/preview/replay 权威，TS 不实现状态计算；CAMP Phase 6–8 标记暂停。规范化算法与固定向量锁定后才进入阶段 1。此阶段不训练模型，不把旧任务语料直接当作新任务验收集。

### 阶段 1：纯世界状态内核

产物：Python 的 ID 登记表、位置联合依赖图、任务树、描述变化解析、时间先行、任务增量归一化、增量合并、apply、preview 纯函数、回放与规范化参考实现。TS 此阶段只定义协议和夹具读取，不实现第二份状态内核。

验收：实体集合固定；三类位置边联合无环；父容器移动正确传播；supersedes 作用域、生效条件和纯解除均正确；同点临时变化折叠后不引用同点记录，合并结果与工作状态摘要一致；本点新增又达成及新增父子任务符合唯一编码；规范字节符合阶段 0 固定向量；时间先行、纯时间任务达成及联动合法。

### 阶段 2：固定候选工作流

产物：无模型的 TS 控制器、人物游标、行动资格、反应关系去重、共同结算队列、冻结行动、六步更新调度、自动推进和预算暂停。最小 Python preview 路由读取 FixtureBaselineStore 中封存 S₀ 及进程内模拟头；固定候选点和 round-conclusion 在内存确认，SQL 持久化在下一阶段补齐。TS 读取 preview 返回值，不自行 apply。

验收：用手写候选完整跑通普通行动、失败反应、成功反应、连锁反应、已行动目标、多次关联点、理智变化不重排；A stage 后能回到 select_actor 并让 B 读取 A 的新工作态，提交 P1 前已提交游标保持原值。通过原子结论创建下一 round 并重排，handback 正常交还；自动 round 不重复消费输入。验证 C 拉入 D 后再遇第二威胁不改写 C 或撤销既有依赖。严格执行段间叙事门槛，不在等待时计算下一段，但 pending 时允许持久化暂停/恢复；未完成共同组时不写入组内部分结果。

### 阶段 3：事务持久化与恢复

产物：新增表、完整 `/worlds` API、幂等与并发控制、带 advance/pendingGroup/conclusion 的检查点、PointWork 及工作游标、组暂存窄操作、当前 epoch 工作表及已确认清单、原文副本接续、时间锁/预约前缀验证、原子 round-conclusion、ID 分配、一次定稿的骰点、租约令牌及 epoch、根点/推进点认领签发、逐操作 gate 门槛、叙事续期与缓存读写、历史回放；基线适配切换为 SQLiteBaselineStore。

验收：同请求重发只产生一个点；版本或检查点冲突不混入过期结果；真实 SQL 故障不留下半份变化；A stage 后刷新不重跑 A，B 正常继续，只有 P1 提交才提升已提交进度。结论重发不重复建 round，跨自动 round 刷新不重放输入；根点创建即有有效 claim/gate；resolve_gate 不使 points 的 revision 自冲突。P1 清 A/B 后保留已绑定的 C/D；跨提交基线不符拒绝，锁定时间修改拒绝。接管副本原文/候选哈希不变，普通读取隔离旧 epoch，迟到写入/失败清理均拒绝，缺失原文不允许模型补写。pending 期间暂停成功，过 TTL 后恢复写入仍成功但 canCompute=false，UI 提示重生成；叙事失败、缓存删除与旧代次迟到可恢复，已提交点不依赖行动文本。preview、提交、无缓存回放与缓存读取须得到 world-canonical-v1 相同摘要。

### 阶段 4：浏览器模型与任务实验

产物：运行层适配、独立实验页面、任务样本和人工评分表、单模型基线报告、调用合并/拆分对照。合并臂必须包含“位置变化影响外貌判断”的强制拆分反例，记录条件命中与实际调用数，不能用配置固定一次/结算后再宣称测得七次。

先检查已安装运行时的 schema、取消和线程能力，再测候选模型。逐项接入行动、反应、共同结果、六步更新、继续推进、叙事，最后接初始世界分批生成。

验收：每项任务有独立成功定义；报告格式合法率与语义正确率分别统计；给出实际设备、浏览器、模型、量化、上下文、输出长度、重试及延迟。模型不能达标时保留程序内核与夹具，不以降级静默改规则。

### 阶段 5：完整可玩闭环

产物：初始世界确认、玩家输入、连续时间点展示、共同结算展示、暂停/继续、历史状态查看与叙事重新生成。

验收：在已声明支持的桌面浏览器和设备上，使用初始小世界完成至少 20 次玩家输入；覆盖多个自动推进链和至少一次连锁共同结算；每次提交后都可从 S₀ 重建相同状态；人为删除叙事缓存后仍可查看历史。以共同结算收尾的 round 保留空 linked 续段并生成叙事，明确计入额外一次叙事调用及串行等待，不将这段当作零成本。

### 阶段 6：容量与质量改进

产物：上下文分批、派生摘要缓存、稀疏检查点、设备适配和失败样本修复。

在相同用例上比较单模型、多提示词与多专用模型的真实收益，再决定是否训练或增加模型。世界规模每次只增加一个维度，记录正确性和等待时间如何变化。

验收：优化不能改变固定实体、全人物任务检查、全人物个性影响和冻结顺序规则；优化版与参考内核状态一致。首版不承诺手机端、所有浏览器或任意大世界实时运行。

## 十一、必要测试与模型评估

### 11.1 确定性核心测试

| 测试情形 | 必须结果 |
|---|---|
| 创建新人物、新物品或新地点的候选 | 结构提交拒绝；模型可重算为失败或部分失败 |
| 钥匙在外套口袋，人物移动教室 | 钥匙展开位置随人物移动，直接位置仍为外套口袋 |
| 两件物品互相包含 | 拒绝；同时交换合法容器可以成功 |
| 钥匙参照黑板，黑板又被放入钥匙 | 三类位置边并集成环，拒绝 |
| 同一点人物被多次影响 | 实体只有一份合并 Δ，结果与顺序应用一致 |
| 本点新增任务 T，后续行动使 T 达成 | T 只在 subtasksAdded 中带 achieved；tasksAchieved 不含 T；apply 等于工作态投影 |
| 同点新增父子任务或同 ID 同时出现在新增/达成列表 | 父先子后并稳定排序；交叉 ID 和任务环拒绝 |
| 外貌流血后止血、个性先信任后多疑 | 历史保留，当前读取不把失效变化当作仍有效 |
| supersedes 跨实体/字段、同点/未来、无效旧变化或重复解除 | 拒绝；纯解除仅允许 text=null 且至少一个合法目标 |
| 同点先产生后解除变化、模型自行生成 change/group/trigger ID | 前者折叠为合法最终变化；未分配 ID 拒绝 |
| 子任务引用不存在父任务或形成任务环 | 拒绝 |
| 小任务完成但根目标尚未满足 | 不自动标记根目标完成 |
| 场外人物因他人任务完成改变个性 | 被完整扫描，可有变化，并更新其理智值 |
| 目睹惨状但无任务达成、只提交 sanitySet | 不产生直接理智变化，候选拒绝 |
| 反应成功/失败、目标已行动 | 分别提前并组/保留原顺序/仅影响结果 |
| A→B→C→A、多个威胁指向同一人物 | 有限终止，不产生重复行动，不反复掷骰 |
| C/D 共同结算前后理智改变 | E/F 延续原顺序，新 round 才重排 |
| 无实体变化但时间流逝 | 保存时间点并生成叙事 |
| 11:59 推进一分钟、无人物行动 | 先到 12:00，再检查“坚持到中午”并执行个性/理智联动；叙事不编造动作 |
| 未确认工作前改时长、确认行动/skip/目标/时间扫描或 roll 后改时长 | 前者 set_point_time 后清未确认输出并重新 preview；后者返回 point_time_locked，原文/目标/roll 不变；时间只应用一次 |
| 锁定后显式 cancel，再启动新链 | 原工作 abandoned、旧 ID/roll 留终止记录，不进入世界；新链用新身份，旧请求不能复活工作，刷新不能自动取消重采样 |
| 只有不相关 NPC 想行动 | 停止自动推进 |
| 预算耗尽、叙事失败、刷新、迟到响应 | 明确暂停，可恢复，无重复提交 |
| A 结算完成、B 尚未分析，P1 未提交 | stage_unit(A) 只追加 settledUnits/推进 working 游标并清活动 pendingGroup，回到 select_actor；B 读取 A 的输出投影，已提交 actedIds/cursor 不动 |
| stage_unit(A) 响应丢失重发、B 中途刷新、points(P1) 重发 | A 只暂存一次，冻结候选不变；恢复 A 后继续 B；最终一个 P1 原子消费 A/B，工作进度只提升一次 |
| B 试图让已 stage 的 A 再行动、points 替换 A 的候选或省略 A | workingActedIds 阻止重复行动；已确认候选/单元清单不一致时拒绝 |
| P1 已提交，C 行动和目标已确认、D 已入组、P2 未提交时刷新 | 从 discover_group/extend_group 保存的 pendingGroup、phase 和工作表恢复；不重采样目标、不重复掷骰，未结算成员不误记为已行动 |
| 目标确认前崩溃、确认后 roll 前崩溃、roll 后扩张前崩溃 | 未确认输出未被消费；已确认目标复用；已有 roll 定稿可补做幂等扩张；不出现 NULL admission 半行 |
| discover_group 越权改游标、未分配 group/trigger ID、闭组后改目标/删成员 | 全部拒绝；只允许规定的 phase 边和组字段写入 |
| P1 提交清理 A/B，同时存在尚未消费的 C/D | 只清理本点 settlementGroups；C/D 的冻结行动及目标保持可恢复 |
| 交接后旧持有者写入工作文本或执行失败清理 | 租约/epoch 校验拒绝；当前 epoch 内按每成员最大 attempt 读取，不见旧 epoch 行 |
| 接管“推开 D”的工作，却提交相同目标/骰点的“刺伤 D”替代文本 | restore_group_work 只从服务端已确认清单复制原文；替代文本拒绝，复制前后 UTF-8 字节/载荷哈希相同 |
| 接管副本来源未确认、已废弃、已消费、跨点，或原文缺失/损坏 | 全部拒绝，不以最新 attempt 自动认领、不模型重建；被活动引用的原文不得 GC |
| P1 前预约 P2，P1 实际提交后恢复 C/D | 前缀摘要、P1 ID/版本/状态、P2 时间/输入投影全部匹配才同事务提升；不符拒绝，不静默重绑或重掷 |
| 同 round 的 P1/P2/P3 和新 round 首点 | trigger 继承；P2/P3 边界为 instant，新首点为 elapsed |
| P1 叙事尚未 ready | 禁止下一段角色/结算/preview 调用；已有 pendingGroup/行动/目标必须持久化，P1 不等待全组闭合 |
| 末段叙事完成、continue/handback 分别确认 | phase 已为 assess_continuation，ready 只清 gate、不改 revision；结论原子结束 round；continue 只创建一个后继，handback 交还玩家 |
| 四个入口执行 resolve_gate、points 携带原 expectedCheckpointRevision | gate 签发/清空/懒失效均不改 revision，不产生本事务自冲突；失败叙事清 gate 后仍明确要求重生成 |
| 结论确认响应丢失后刷新/重发、同 ID 改结论 | 读取原结论和 nextRoundId，不重跑判断；改结论拒绝 |
| cancel 与模型 handback 的历史记录 | kind 均可为 handback，但 closedBy/cancelReason 明确区分；非法组合拒绝 |
| 第二个 automatic round 刷新 | 恢复同 advance/input 和 consumed，正文仍在，不重放原命令 |
| 根点、首个推进点、第二个根点或同前驱第二个后继 | 前两者可插入；重复根或重复后继被联合/部分唯一约束拒绝 |
| POST /worlds 成功、事务失败、成功响应丢失重发 | 世界/根点/租约/claim/gate 同生同灭；幂等重发取回同一世界，根点 generation=1，claim 为 head 且 epoch 非空 |
| 根点叙事未 ready 时创建首个 round | 拒绝；head claim 可无 advance，但必须有有效 epoch；v2 服务事务门槛替换 v1 触发器时不能失守 |
| 同一输入链中段出现纯时间点 | advance/input/consumed 继承；任务扫描与叙事门槛均不能跳过 |
| C 的反应拉入 D 后，C 又遭遇第二威胁 | C 文本不变、D 及既有依赖不被撤销；新威胁只影响共同结果 |
| 推进租约到期交接、旧持有者迟到成功或失败 | epoch/令牌不匹配，写入及释放均拒绝 |
| 长叙事期间续约、claim 续期与交接 | 续约不改 epoch、续期不改代次，同 epoch 确认成功；交接后新持有者立即可重领旧 epoch claim |
| 叙事缓存缺失、重试后旧代次返回 | 仅新代次可完成，时间线不重新结算 |
| 用户在叙事仍 pending 时暂停五分钟后恢复，claim TTL 为 180 秒且未续期 | pending 时 pause 成功落库；重新取得有效推进租约后 resume 也落库，认领失效且 gate 清除；响应 paused=false、canCompute=false 并报告失效原因；UI 提示重新生成，ready 前不能计算；gate 清理不增 revision |
| pending 时 resume、paused 时叙事 ready、重复 pause/resume | resume 可成功但 canCompute=false；ready 不清 paused、不自动启动计算；仅 paused 实际变化增 revision，同请求幂等重放不重复递增 |
| 相同 memberIds 使用不同排列、外层 settlementGroups 交换单元 | 成员规范字节/提交摘要相同；外层次序改变则摘要不同；重复成员拒绝 |
| 键顺序、整数表示、空字段与 Unicode 不同编码形式 | 对照固定规范字节与哈希；有序数组差异保留 |
| 删除当前状态和叙事缓存后回放 | 仅凭初始世界和增量恢复相同世界 |
| 阶段 2 装载 S₀ 夹具、fixture 摘要变更、preview 超预算 | 基线来自服务端封存夹具；版本不符或超预算明确拒绝，不改变内存头 |

### 11.2 模型任务数据集

建议先构建 80 个独立标注样本与 10 条短链场景，覆盖有效/无效行动、反应链、共同冲突、任务层级、跨人物个性影响、时间选择和叙事忠实度。保留未用于调提示词的测试部分，统计链级成功率，不能仅报告单步准确率。

合并/拆分对照必须包含位置不影响外貌、位置影响外貌两类样本，标注预期依赖和强制拆分原因；后者例如移动到雨中后判断淋湿。合并臂不得删掉该类反例或绕过位置应用后的外貌调用。任何新增样本是否达标仍依据完整六步结果及覆盖清单，而不是调用数更少。

结构化输出指标与语义指标分开：

- 结构：JSON/schema 成功率、非法 ID 比例、漏字段率、程序拒绝率、重试率。
- 行为：是否行动、反应对象、共同结果是否考虑全组、任务是否真的达成。
- 更新：六步覆盖是否完整、变化是否有结算依据、个性与理智是否同步。
- 推进：是否错误持续推进、是否漏掉明显与主角关联的后续行动。
- 叙事：是否捏造新事实、隐藏信息是否合理、中文可读性。
- 链路：完成一次玩家输入及其全部自动推进所需时间、调用数和失败率。

不把模型自评当唯一正确答案。固定规则由测试判定，含语义的样本由人工标注和复核。初始模型是否晋升以实验结果决定，本文不宣称已有模型通过这些新任务。

### 11.3 性能报告

按冷启动和热运行分别测量，至少报告加载时间、首 token、完整调用 p50/p95、完整时间点 p50/p95、一次玩家输入的总等待、输入/输出 token、可获得的内存数据和失败情况。

总成本近似为所有调用的输入处理、输出生成、校验重试和提交之和；不能把一个大调用拆成多个后，忽略重复输入处理开销。全人物任务与个性扫描是主要扩展成本，应优先研究批处理。

纯时间点也不是零模型调用：每点至少一次覆盖所有人物任务的扫描；分批时调用数至少为完整覆盖所需批次数，此外还可能需要新增小任务、个性、理智及叙事调用。整链报告单独列出纯时间点成本。首版段间严格串行，n 段等待包括各段叙事之和，不以“提交串行但计算可并行”估算延迟；记录 preview 重算单元数、传输字节及预算拒绝次数。

本轮评审的七个结算单元用例，六步更新合并臂按 `7 + k` 次计，k 是“位置影响外貌”而必须拆分的单元数（0–7），因此为 **7–14 次**；该用例其余工作按既定口径计 19–21 次，总计 **26–35 次**，不得写成固定 7 次或总计 26–28 次。这是该用例在给定合并条件下的估算区间，不是任意世界的总上限；额外的阶段依赖、上下文分批、重试和叙事校验调用须另计。报告列出每单元的拆分条件与实际调用数。

P1 的等待包含自身结算、已经发生的边界检测工作、提交与叙事；未完成的 C/D 组扩张留在 P1 ready 之后，不把闭组当作 P1 提交前置条件。逐段记录边界检测、组扩张、六步更新、工作确认/stage_unit 写事务次数与往返延迟、接管副本字节数、提交及叙事耗时，避免预先分析整组或忽略中间持久化却只报告提交后延迟。

交互延迟目标在阶段 4 根据目标设备实测后确定。任何毫秒或秒数承诺都应附设备和场景条件，不沿用旧试验的单项耗时作为完整工作流速度。

## 十二、建议文件组织与首个交付切片

两人并行实施按 [两人开发分工](browser-world-state-work-split.md) 执行：A 负责 Python 契约、状态内核、事务/API 及共同 CI，B 负责浏览器控制器、模型运行、实验界面及前端消费检查命令。共同轨迹定义固定值、动态捕获/引用、语义断言及摘要匹配；接口变更须通过双方自动检查。A2＋B1 提前跑普通点 HTTP，A3 后跑刷新/接管，最后完成真实服务全部轨迹及模型整链合并验收；具体文件归属、交付任务及接口变更方式见分工文档。

近期执行 [A0＋B0 共同接口基线实施计划](world-protocol/v2/interface-baseline-plan.md)：先完成 IF-01 差异及接口清单，再发布供 B 消费的候选快照，双方检查通过后冻结共同基线。

```text
design/browser-world-state-workflow.md
frontend/src/lib/world-engine/
  types.ts                 状态和候选类型
  state-view.ts            接收 Python 工作状态、只读位置展示，不实现 apply
  preview-client.ts        调用 Python preview，绑定基线与候选阶段
  scheduler.ts             固定流程、冻结顺序和自动推进
  reactions.ts             被迫行动和共同组构建
  model-tasks.ts           任务接口与提示词版本
  runtime/                 浏览器推理适配
  fixtures/                固定世界、候选和骰点
frontend/src/app/world-lab/ 独立验证入口
backend/app/schemas/world/ 新协议
backend/app/services/world/ 唯一的校验、apply、preview、合并、规范化、提交、回放
backend/app/routers/worlds.py
backend/app/database/world_store.py
```

前后端维护同一协议，使用共同 JSON 夹具验证 TS 编解码不丢字段；Python 单独实现状态计算与摘要，浏览器只保存并展示其返回的只读工作状态。阶段 1 的纯内核、阶段 2 的 preview、阶段 3 的提交和回放均复用这一实现；本版不建立 TS/Python 双份 apply。

首个交付切片建议为：**手写学校世界 + 固定候选 + 一个普通段、一个共同结算瞬时段、一个关联续段 + 增量持久化与回放**。先验明规则，再逐步替换固定候选为端侧模型输出；运行时能力实验可以提前开展，但不代替状态内核验收。

## 十三、实施参数与待验证解释

以下事项原稿没有给出唯一答案。其中已在本轮确定的规则直接写入协议，其余建议在具体实现前锁定默认值和夹具；实施选择与用户原始设计要求分别标记。

| 事项 | 建议默认或处理方式 |
|---|---|
| 理智范围、触发与同值排序 | 本版确定为 0–100 整数；仅任务达成引起个性变化后重算；同值按稳定 ID；模型映射质量通过样本检查 |
| 骰点规则版本 | 阶段 0–3 使用 reaction-fixture-v1；首个真实掷骰基线为 reaction-d20-v1（d20≥11 通过，无修正）；变更必须换版本 |
| 推进租约 TTL | 默认 120 秒，服务端时钟判断到期；交接递增 fence_epoch |
| 租约续约间隔 | 默认 20 秒，匹配令牌和 epoch，成功续约不递增 epoch |
| 叙事 claim TTL | 默认 180 秒，head claim（含根点）固定绑定签发 epoch；失效 epoch 可立即重领 |
| 叙事 claim 续期间隔 | 默认 20 秒，独立心跳；续期不改 token/generation，不替代推进租约续约 |
| preview 重算预算 | 默认每请求 32 个结算单元、512 KiB JSON、2 秒服务端计算；超限明确拒绝且无部分应用 |
| 段间执行 | 首版串行等待每段叙事 ready；已有行动与目标经窄操作落库，不要求 P1 提交前闭组 |
| pendingGroup 写入 | 采用 A：discover_group 只允许 select_actor→build_group；extend_group 只增不减，close_group 后只读；所有操作绑定 revision 与租约 |
| 点内多结算单元 | stage_unit 保存完整结果/候选并回 select_actor；working 游标与已提交游标分离，points 才原子提升并消费 |
| 接管冻结工作 | 仅服务端验证已确认来源后原文复制，缺失/损坏明确阻断；普通读取继续隔离旧 epoch，不能模型重建 |
| 跨提交基线 | 提前工作先 prepare_successor 封存前缀并锁定后继基线/时间；P1 提交逐项验证，不符拒绝、不重绑 |
| gate 与控制操作 | pause/resume/原文副本接续可穿过 gate；计算/提交要求 ready 且未暂停，恢复成功不等于 canCompute |
| 控制器 revision | 只随控制位置/游标/组工作态/暂停变化递增；gate/claim/叙事 ready 不改 revision |
| 根点认领 | POST /worlds 同事务创建租约并签发 generation=1 的 head claim/gate；不保留根点 0→1 特例 |
| 未提交工作清理与围栏 | 按本点消费的 groupId 清理；有效 leaseToken+fenceEpoch 写入，当前 epoch 每成员最大 attempt 可见 |
| 六步合并臂 | 条件合并；七单元用例为 7–14 次，总计 26–35 次，强制拆分反例必须进数据集 |
| 已跳过槽位但尚未实际行动的人物是否可被迫反应 | 建议仍允许一次反应，区分 visited 与 acted；已实际行动则禁止第二次 |
| 同时受到多个威胁 | 行动文本生成即冻结；后续威胁仅影响共同结果，不重写反应，不重新掷同一骰点 |
| 无前段/无后段的瞬时组 | 建议保留空实体变化的边界点，界面分组，避免破坏关联结构 |
| 关联边界与行动持续时间 | 分别记录瞬间边界和该段持续时间，不能只用一个含混字段 |
| 六步更新的执行时机 | 每独立行动/共同组后执行并经 stage_unit 持久化候选，下一人物读更新后的工作态，时间点结束合并提交 |
| 完成任务能否撤销、是否允许多层小任务 | 首版达成单向，结构支持多层；后续另定撤销规则 |
| 自然语言变化失效 | 使用新变化引用并解除旧变化，初始描述不改写 |
| 精确对话及失败动作的历史复现 | 首版不保证；只重建已保存状态，不新增长期行动记录 |
| 长跨度与中途事件 | 模型提出跨度时检查是否跳过明显关联行动；涉及重大中途反应时缩短跨度 |
| 暂停与正常交还玩家 | 使用不同状态；预算暂停允许继续原工作流 |
| 历史点继续游玩 | 首版只读回放；截断、分支或另存需后续设计 |
| CAMP 与新引擎的开发关系 | 本轮确定 CAMP Phase 6–8 暂停，不并行新增开发；旧运行路径保留 |
| 状态内核权威 | 本轮确定 Python 唯一实现，TS 调用 preview 并持有只读工作状态 |
| 输入消费及结论 | advanceId/inputId 跨 round 继承，automatic 一律 consumed；正文保留到整链结束；continue/handback 原子确认后不可翻转 |
| 时间更新时机 | begin_point 保存时间与基线；首次确认时间相关工作时锁定，之后改时长拒绝；确需改变先显式取消链，原判定不删不复用 |
| 同点任务最终编码 | 新增又达成只写 subtasksAdded 的 achieved；新增父先子后，禁止与 tasksAchieved 交叉 |

实际开发顺序以阶段 0–3 的固定候选闭环为起点，阶段 4 的任务实验决定模型及调用组织，随后进入可玩闭环。当前不需要先接通通用 Agent 调度器，也不需要先为每个步骤训练独立模型。
