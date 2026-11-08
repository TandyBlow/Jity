# 首批候选逐条报告（自动生成，勿手改）

输入包 v2。夹具：`c8-eval-geothermal-v1`（模板 sha256 `241fde2bf18a8215…`）；数据库 sha256 `04878c4f6ca9f39b…`。

## `c8e01` 三项转运，各有起终点

- 覆盖：多人物、多地点；视角：omniscient；90 秒
- 提交：`world_1/point_7`，before `b21a870bddb3…` → after `2f959cc71861…`（读回校验通过）
- 必述 3 条；可不提 0 条；现状引用 14 条
- R1 v1/v2：candidate / candidate；R3 `moved*3|3|90s`
- 四段：状态已提交 是｜页面投影接受 Δ 是｜视角过滤已执行 否｜叙事已生成 否

必述事实：

- `moved` fe_shao · `state.characters.fe_shao.position`
- `moved` fe_wen · `state.characters.fe_wen.position`
- `moved` fe_yu · `state.characters.fe_yu.position`

## `c8e02` 两栋建筑，视角只在校准间

- 覆盖：多人物、多地点、可见性；视角：protagonist；45 秒
- 提交：`world_11/point_17`，before `4a66f7b59b67…` → after `3567903a6678…`（读回校验通过）
- 必述 1 条；可不提 1 条；现状引用 15 条
- R1 v1/v2：candidate / candidate；R3 `moved*1|1|45s`
- 四段：状态已提交 是｜页面投影接受 Δ 是｜视角过滤已执行 否｜叙事已生成 否

必述事实：

- `moved` fe_wen · `state.characters.fe_wen.position`

可不提（提则受限）：

- `moved` fe_shao — offstage-perspective：限知视角：不在主体可见容器内的变化可以不提；若要提，不得写成主体亲眼所见或亲耳听到。

能力不支持：

- P5-no-perspective-filter：页面叙事路径不做视角过滤：世界为真的远处变化会被照写，本条的限知/推迟要求只能由 N2 规则臂或人工判定

## `c8e03` 父子任务同时校准，另有人完成转移

- 覆盖：任务、多人物、多地点；视角：protagonist；180 秒
- 提交：`world_20/point_26`，before `42a882b7851a…` → after `70aed1eb2002…`（读回校验通过）
- 必述 6 条；可不提 0 条；现状引用 12 条
- R1 v1/v2：candidate / candidate；R3 `moved*2+personality_changed*1+sanity_changed*1+task_achieved*2|2|180s`
- 四段：状态已提交 是｜页面投影接受 Δ 是｜视角过滤已执行 否｜叙事已生成 否

必述事实：

- `moved` fe_nie · `state.characters.fe_nie.position`
- `moved` fe_wen · `state.characters.fe_wen.position`
- `sanity_changed` fe_wen · `state.characters.fe_wen.sanity`
- `task_achieved` fe_wen · `state.characters.fe_wen.tasks.ft_check.status`
- `task_achieved` fe_wen · `state.characters.fe_wen.tasks.ft_mark.status`
- `personality_changed` fe_wen · `state.characters.fe_wen.personalityChanges`

## `c8e04` 持有人与参照物，明确空间关系

- 覆盖：关系、多人物；视角：protagonist；30 秒
- 提交：`world_30/point_36`，before `fa68255f5936…` → after `581bfbf50e57…`（读回校验通过）
- 必述 2 条；可不提 0 条；现状引用 16 条
- R1 v1/v2：candidate / candidate；R3 `moved*1+moved_entity*1|2|30s`
- 四段：状态已提交 是｜页面投影接受 Δ 否｜视角过滤已执行 否｜叙事已生成 否

必述事实：

- `moved` fe_wen · `state.characters.fe_wen.position`
- `moved_entity` fi_gauge · `state.items.fi_gauge.position`

能力不支持：

- P1-non-character-delta：物品位移不在页面叙事投影的支持范围内
- P4-position-slot-or-relative：relativeTo 会被投影拒绝（unsupported_narration_position）

## `c8e05` 封签的持有转移和外貌变化

- 覆盖：关系、多人物、外貌；视角：protagonist；60 秒
- 提交：`world_38/point_44`，before `49b240cc657c…` → after `4bc218e24ec7…`（读回校验通过）
- 必述 3 条；可不提 0 条；现状引用 16 条
- R1 v1/v2：candidate / candidate；R3 `appearance_changed*1+moved*1+moved_entity*1|2|60s`
- 四段：状态已提交 是｜页面投影接受 Δ 否｜视角过滤已执行 否｜叙事已生成 否

必述事实：

- `moved` fe_wen · `state.characters.fe_wen.position`
- `moved_entity` fi_seal · `state.items.fi_seal.position`
- `appearance_changed` fi_seal · `state.items.fi_seal.appearanceChanges`

能力不支持：

- P1-non-character-delta：物品位移不在页面叙事投影的支持范围内
- P2-appearance-change：实体外貌变化不在支持范围内

## `c8e06` 关注指令与世界事实分开

- 覆盖：玩家关注、任务、多人物；视角：omniscient；120 秒
- 提交：`world_47/point_53`，before `e5e81ecfd5f7…` → after `a29e1dacef48…`（读回校验通过）
- 必述 2 条；可不提 1 条；现状引用 14 条
- R1 v1/v2：candidate / candidate；R3 `moved*1+task_achieved*1|1|120s`
- 四段：状态已提交 是｜页面投影接受 Δ 否｜视角过滤已执行 否｜叙事已生成 否

必述事实：

- `moved` fe_shao · `state.characters.fe_shao.position`
- `task_achieved` fe_shao · `state.characters.fe_shao.tasks.ft_relay.status`

可不提（提则受限）：

- `moved` fe_wen — deferredByInstruction：玩家指令要求本轮暂不展开该角色：可以不提；若要提，不得写成关注对象，也不得据此推出任务达成。

能力不支持：

- P3-incomplete-numeric-cause：任务/人格/理智未同时出现，投影会拒绝
- P5-no-perspective-filter：页面叙事路径不做视角过滤：世界为真的远处变化会被照写，本条的限知/推迟要求只能由 N2 规则臂或人工判定

## 修订记录

### v2（2026-11-08）

触发：外部静态审查（未运行测试）

改动：

- c8e02：远处移动不再进入 mustExpress，改为 mayMention/offstage-perspective
- c8e06：被指令推迟的移动不再进入 mustExpress，改为 mayMention/deferredByInstruction
- c8e05：物品位移补全 fromId/from 与 toKind、holderChanged
- c8e04：relativeTo 补全可读名称
- 全部：能力拆成四段状态，页面路径是否满足预期单独判定
- 全部：currentState 取值不再用 or 链，0 不会被吞成 null

未改动：

- 夹具、数据库、六个提交点与摘要未动（输入包是派生物）
- R1 v1/v2、R2、R3 口径未动；六条仍然零命中

