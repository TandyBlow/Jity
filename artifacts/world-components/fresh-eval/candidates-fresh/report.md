# 首批候选逐条报告（自动生成，勿手改）

输入包 v3。夹具：`c8-eval-geothermal-v1`（模板 sha256 `241fde2bf18a8215…`）；数据库 sha256 `04878c4f6ca9f39b…`；N2 模块 sha256 `84a02c04d06e47d2…`。

## `c8e01` 三项转运，各有起终点

- 覆盖：多人物、多地点；视角：omniscient；90 秒
- 提交：`world_1/point_7`，before `b21a870bddb3…` → after `2f959cc71861…`（读回校验通过）
- 完整变化 3 条：必述 3、可提及 0、不进入输入 0
- N2：ok，must 3／may 0／invisible 0
- R1 v1/v2：candidate / candidate；R3 `moved*3|3|90s`
- 四段：状态已提交 是｜页面投影接受 Δ 是｜视角过滤 N2 已判（排除 0 条）｜叙事已生成 否

必述：

- `moved` fe_shao · `state.characters.fe_shao.position`（omniscient-focus-position）
- `moved` fe_wen · `state.characters.fe_wen.position`（omniscient-focus-position）
- `moved` fe_yu · `state.characters.fe_yu.position`（omniscient-focus-position）

## `c8e02` 两栋建筑，视角只在校准间

- 覆盖：多人物、多地点、可见性；视角：protagonist；45 秒
- 提交：`world_11/point_17`，before `4a66f7b59b67…` → after `3567903a6678…`（读回校验通过）
- 完整变化 2 条：必述 1、可提及 0、不进入输入 1
- N2：ok，must 1／may 0／invisible 1
- R1 v1/v2：candidate / candidate；R3 `moved*2|2|45s`
- 四段：状态已提交 是｜页面投影接受 Δ 是｜视角过滤 N2 已判（排除 1 条）｜叙事已生成 否

必述：

- `moved` fe_wen · `state.characters.fe_wen.position`（self-position）

不进入输入（答案侧保留）：

- `moved` fe_shao（other-location）

## `c8e03` 父子任务同时校准，另有人完成转移

- 覆盖：任务、多人物、多地点；视角：protagonist；180 秒
- 提交：`world_20/point_26`，before `42a882b7851a…` → after `70aed1eb2002…`（读回校验通过）
- 完整变化 6 条：必述 5、可提及 1、不进入输入 0
- N2：ok，must 4／may 2／invisible 0
- R1 v1/v2：candidate / candidate；R3 `moved*2+personality_changed*1+sanity_changed*1+task_achieved*2|2|180s`
- 四段：状态已提交 是｜页面投影接受 Δ 是｜视角过滤 N2 已判（排除 0 条）｜叙事已生成 否

必述：

- `moved` fe_wen · `state.characters.fe_wen.position`（self-position）
- `sanity_changed` fe_wen · `state.characters.fe_wen.sanity`（self-safety）
- `task_achieved` fe_wen · `state.characters.fe_wen.tasks.ft_check.status`（self-task）
- `task_achieved` fe_wen · `state.characters.fe_wen.tasks.ft_mark.status`（self-task）
- `personality_changed` fe_wen · `state.characters.fe_wen.personalityChanges`（self-state）

可提及：

- `moved` fe_nie（co-location）

## `c8e04` 持有人与参照物，明确空间关系

- 覆盖：关系、多人物；视角：protagonist；30 秒
- 提交：`world_30/point_36`，before `fa68255f5936…` → after `581bfbf50e57…`（读回校验通过）
- 完整变化 2 条：必述 2、可提及 0、不进入输入 0
- N2：ok，must 1／may 1／invisible 0
- R1 v1/v2：candidate / candidate；R3 `moved*1+moved_entity*1|2|30s`
- 四段：状态已提交 是｜页面投影接受 Δ 否｜视角过滤 N2 已判（排除 0 条）｜叙事已生成 否

必述：

- `moved` fe_wen · `state.characters.fe_wen.position`（self-position）
- `moved_entity` fi_gauge · `state.items.fi_gauge.position`（co-location）

## `c8e05` 封签的持有转移和外貌变化

- 覆盖：关系、多人物、外貌；视角：protagonist；60 秒
- 提交：`world_38/point_44`，before `49b240cc657c…` → after `4bc218e24ec7…`（读回校验通过）
- 完整变化 3 条：必述 3、可提及 0、不进入输入 0
- N2：ok，must 1／may 2／invisible 0
- R1 v1/v2：candidate / candidate；R3 `appearance_changed*1+moved*1+moved_entity*1|2|60s`
- 四段：状态已提交 是｜页面投影接受 Δ 否｜视角过滤 N2 已判（排除 0 条）｜叙事已生成 否

必述：

- `moved` fe_wen · `state.characters.fe_wen.position`（self-position）
- `moved_entity` fi_seal · `state.items.fi_seal.position`（co-location）
- `appearance_changed` fi_seal · `state.items.fi_seal.appearanceChanges`（co-location）

## `c8e06` 关注指令与世界事实分开

- 覆盖：玩家关注、任务、多人物；视角：omniscient；120 秒
- 提交：`world_47/point_53`，before `e5e81ecfd5f7…` → after `a29e1dacef48…`（读回校验通过）
- 完整变化 3 条：必述 2、可提及 0、不进入输入 1
- N2：ok，must 3／may 0／invisible 0
- R1 v1/v2：candidate / candidate；R3 `moved*2+task_achieved*1|2|120s`
- 四段：状态已提交 是｜页面投影接受 Δ 否｜视角过滤 N2 已判（排除 1 条）｜叙事已生成 否

必述：

- `moved` fe_shao · `state.characters.fe_shao.position`（omniscient-focus-position）
- `task_achieved` fe_shao · `state.characters.fe_shao.tasks.ft_relay.status`（omniscient-focus-goal）

不进入输入（答案侧保留）：

- `moved` fe_wen（omniscient-focus-position）

## 修订记录

### v2（2026-11-08）

触发：外部静态审查（第一轮）

改动：

- c8e02 远处移动移出必述
- c8e06 被推迟移动移出必述
- c8e05 物品位移补起止两端
- c8e04 参照对象补名称
- 能力拆四段
- currentState 不再吞 0

未改动：

- 夹具、数据库、六个提交点与摘要

### v3（2026-11-08）

触发：外部静态审查（第二轮）

改动：

- R1/R2/R3 回到完整变化集合，另存必述子集签名
- 视野筛选改由真实 N2 判定（不可见事实只留在 answer.json）
- c8e03 同一套 N2 判定：聂汀穗的移动为 may，不再当必述
- 能力判断按人物逐一检查任务/人格/理智三件套

未改动：

- 夹具、数据库、六个提交点与摘要
- R1 v1/v2、R2、R3 口径本身

