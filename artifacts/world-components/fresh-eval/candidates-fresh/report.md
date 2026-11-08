# 首批候选逐条报告（自动生成，勿手改）

夹具：`c8-eval-geothermal-v1`（模板 sha256 `241fde2bf18a8215…`）；数据库 sha256 `04878c4f6ca9f39b…`。

## `c8e01` 三项转运，各有起终点

- 覆盖：多人物、多地点；视角：omniscient；90 秒
- 提交：`world_1/point_7`，before `b21a870bddb3…` → after `2f959cc71861…`（读回校验通过）
- 变化事实 3 条，现状引用 14 条
- R1 v1/v2：candidate / candidate
- R2：零命中；R3：`moved*3|3|90s`
- 页面投影：支持

变化事实：

- `moved` fe_shao · `state.characters.fe_shao.position`
- `moved` fe_wen · `state.characters.fe_wen.position`
- `moved` fe_yu · `state.characters.fe_yu.position`

## `c8e02` 两栋建筑，视角只在校准间

- 覆盖：多人物、多地点、可见性；视角：protagonist；45 秒
- 提交：`world_11/point_17`，before `4a66f7b59b67…` → after `3567903a6678…`（读回校验通过）
- 变化事实 2 条，现状引用 15 条
- R1 v1/v2：candidate / candidate
- R2：零命中；R3：`moved*2|2|45s`
- 页面投影：支持

变化事实：

- `moved` fe_shao · `state.characters.fe_shao.position`
- `moved` fe_wen · `state.characters.fe_wen.position`

## `c8e03` 父子任务同时校准，另有人完成转移

- 覆盖：任务、多人物、多地点；视角：protagonist；180 秒
- 提交：`world_20/point_26`，before `42a882b7851a…` → after `70aed1eb2002…`（读回校验通过）
- 变化事实 6 条，现状引用 12 条
- R1 v1/v2：candidate / candidate
- R2：零命中；R3：`moved*2+personality_changed*1+sanity_changed*1+task_achieved*2|2|180s`
- 页面投影：支持

变化事实：

- `moved` fe_nie · `state.characters.fe_nie.position`
- `moved` fe_wen · `state.characters.fe_wen.position`
- `sanity_changed` fe_wen · `state.characters.fe_wen.sanity`
- `task_achieved` fe_wen · `state.characters.fe_wen.tasks.ft_check.status`
- `task_achieved` fe_wen · `state.characters.fe_wen.tasks.ft_mark.status`
- `personality_changed` fe_wen · `state.characters.fe_wen.personalityChanges`

## `c8e04` 持有人与参照物，明确空间关系

- 覆盖：关系、多人物；视角：protagonist；30 秒
- 提交：`world_30/point_36`，before `fa68255f5936…` → after `581bfbf50e57…`（读回校验通过）
- 变化事实 2 条，现状引用 16 条
- R1 v1/v2：candidate / candidate
- R2：零命中；R3：`moved*1+moved_entity*1|2|30s`
- 页面投影：不支持（见能力条目）

变化事实：

- `moved` fe_wen · `state.characters.fe_wen.position`
- `moved_entity` fi_gauge · `state.items.fi_gauge.position`

## `c8e05` 封签的持有转移和外貌变化

- 覆盖：关系、多人物、外貌；视角：protagonist；60 秒
- 提交：`world_38/point_44`，before `49b240cc657c…` → after `4bc218e24ec7…`（读回校验通过）
- 变化事实 3 条，现状引用 16 条
- R1 v1/v2：candidate / candidate
- R2：零命中；R3：`appearance_changed*1+moved*1+moved_entity*1|2|60s`
- 页面投影：不支持（见能力条目）

变化事实：

- `moved` fe_wen · `state.characters.fe_wen.position`
- `moved_entity` fi_seal · `state.items.fi_seal.position`
- `appearance_changed` fi_seal · `state.items.fi_seal.appearanceChanges`

## `c8e06` 关注指令与世界事实分开

- 覆盖：玩家关注、任务、多人物；视角：omniscient；120 秒
- 提交：`world_47/point_53`，before `e5e81ecfd5f7…` → after `a29e1dacef48…`（读回校验通过）
- 变化事实 3 条，现状引用 14 条
- R1 v1/v2：candidate / candidate
- R2：零命中；R3：`moved*2+task_achieved*1|2|120s`
- 页面投影：不支持（见能力条目）

变化事实：

- `moved` fe_shao · `state.characters.fe_shao.position`
- `task_achieved` fe_shao · `state.characters.fe_shao.tasks.ft_relay.status`
- `moved` fe_wen · `state.characters.fe_wen.position`

