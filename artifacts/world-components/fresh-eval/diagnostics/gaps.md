# 覆盖缺口：叙事投影（交对应模块处理，c8 不修）

每条：合法输入 → 抛错位置 → 影响 → 需要谁改 → 补上之后的要求。

| 编号 | 维度 | 抛错 | 影响 |
|---|---|---|---|
| g02 | 空间相对位置（beside / behind / under / above / in_front_of） | `frontend/src/lib/world-engine/runtime/committed-narration.ts:49 → unsupported_narration_position` | ‘站在门旁边／躲在桌下’这类状态无法进入已提交叙事事实；页面只能拒绝整点，不会部分降级 |
| g03 | 外貌变化（人物 / 地点 / 物品） | `committed-narration.ts:28 → unsupported_narration_world_change（地点/物品）；:51 → unrecorded_appearance_change（人物）` | 外貌改写、衣物被雨打湿、黑板写满字、地点变暗等全部无法叙述；‘外貌’类覆盖在页面路径上不可测 |
| g04 | 任务树新增（subtasksAdded） | `committed-narration.ts:35 → unsupported_committed_delta` | 新增子任务无法叙述，玩家看不到任务树扩张；已登记夹具 task-normalization.json 的整条路径在页面上不可达 |
| g03b | 部分数值因果（只有任务达成、没有理智/人格） | `committed-narration.ts:38 → narration_requires_complete_numeric_cause` | 只达成任务、没有数值变化或人格变化的点无法进入页面叙事；三臂对照里的 nv-task-only-1 正是这种手写包，与投影规则不一致 |

## 明细

### g02 空间相对位置（beside / behind / under / above / in_front_of）

- 合法输入：EntityDelta.positionSet.relativeTo = {entityId, relation}；A 侧 apply_point 的 _check_positions 接受并校验引用与房间共处
- 触发条件：position.slotId != null 或 position.relativeTo != null
- 抛错位置：`frontend/src/lib/world-engine/runtime/committed-narration.ts:49 → unsupported_narration_position`
- 影响：‘站在门旁边／躲在桌下’这类状态无法进入已提交叙事事实；页面只能拒绝整点，不会部分降级
- 需要：投影需要新增相对位置事实类型（含目标实体名与关系词），并定义关系词的中文表达与歧义处理
- 补上之后：补上后必须重新核验来源独立性；不得自动晋升为正式评测题
- 证据：committed-narration.ts sha256 309ca19f…；A 侧 apply.py 005ea5b

### g03 外貌变化（人物 / 地点 / 物品）

- 合法输入：EntityDelta.appearanceChanges（人物、物品、地点均合法），内核 _extend_changes 维护 supersedes 链与 sourcePointId
- 触发条件：before.state.items / locations 与 after 不相等；或人物 appearanceChanges 数组发生变化
- 抛错位置：`committed-narration.ts:28 → unsupported_narration_world_change（地点/物品）；:51 → unrecorded_appearance_change（人物）`
- 影响：外貌改写、衣物被雨打湿、黑板写满字、地点变暗等全部无法叙述；‘外貌’类覆盖在页面路径上不可测
- 需要：投影需要支持三类实体的外貌事实，并规定只述当前生效描述（折叠 supersedes 链）还是同时述变化
- 补上之后：补上后必须重新核验来源独立性；不得自动晋升为正式评测题
- 证据：committed-narration.ts 第 28、51 行；design/world-protocol/v1/fixtures/description-changes.json 提供了已登记的三类变化样例

### g04 任务树新增（subtasksAdded）

- 合法输入：EntityDelta.subtasksAdded = [Task]；内核校验同 owner、必须有父任务、不允许环、按层级排序
- 触发条件：delta 的键不在 ['entityId','positionSet','sanitySet','tasksAchieved','personalityChanges'] 内
- 抛错位置：`committed-narration.ts:35 → unsupported_committed_delta`
- 影响：新增子任务无法叙述，玩家看不到任务树扩张；已登记夹具 task-normalization.json 的整条路径在页面上不可达
- 需要：投影需要支持新增子任务事实，并先确定产品口径：新增子任务要不要进叙事、以什么粒度（父任务下新增一条还是一条条列）
- 补上之后：补上后必须重新核验来源独立性；不得自动晋升为正式评测题
- 证据：committed-narration.ts 第 35 行；design/world-protocol/v1/fixtures/task-normalization.json

### g03b 部分数值因果（只有任务达成、没有理智/人格）

- 合法输入：EntityDelta.tasksAchieved 单独出现（内核允许）
- 触发条件：tasksAchieved / personalityChanges / sanitySet 三者未同时出现
- 抛错位置：`committed-narration.ts:38 → narration_requires_complete_numeric_cause`
- 影响：只达成任务、没有数值变化或人格变化的点无法进入页面叙事；三臂对照里的 nv-task-only-1 正是这种手写包，与投影规则不一致
- 需要：需要产品口径：纯任务达成是否必须伴随理智/人格变化；若不必，投影应放宽为一类事实单独成立
- 补上之后：改口径后要重跑旧题剔除范围（nv-task-only-1 与该规则冲突，可能需要重写或降级）
- 证据：committed-narration.ts 第 38 行

