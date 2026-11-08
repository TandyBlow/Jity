# `c8e05` 封签的持有转移和外貌变化

- 覆盖：关系、多人物、外貌；视角：protagonist；时间：60 秒
- 提交点：`world_38/point_44`，after 摘要 `4bc218e24ec7ec71…`（读回校验通过）
- 必述 3 条；可不提 0 条；现状引用 16 条

## 四段状态

| 段 | 状态 | 证据 |
|---|---|---|
| 世界状态已提交 | 是 | `point_44` + 读回 |
| 页面投影接受该 Δ | 否 | P1-non-character-delta、P2-appearance-change |
| 视角过滤已执行 | 否 | 页面路径无可见性判定 |
| 叙事已生成 | 否 | 本轮不调用模型 |

## 能力不支持（单列，不算模型失败）

- P1-non-character-delta：物品位移不在页面叙事投影的支持范围内（`committed-narration.ts:28`）
- P2-appearance-change：实体外貌变化不在支持范围内（`committed-narration.ts:51`）

## 适用范围说明

- 持有转移与外貌变化都在物品上；页面投影既不接受物品位移，也不接受外貌变化。

## 人工核验项

- [ ] 必须成立：转移的是封签，不是人物移动；持有人从闻澈岑变为聂汀穗。
- [ ] 必须成立：外貌变化归于封签，不归于持有人。
- [ ] 必须成立：持有关系不等于所有权、友谊或因果；当前页面投影不支持这类包。
- [ ] 必须不出现：把未提供的人物或地点写进叙述
- [ ] 必须不出现：把本点没有的变化写成发生
- [ ] 不要求：完整状态里未进入 mustExpress/currentState 的任何字段

## 程序检查

- R1 v1：candidate；v2：candidate；是否翻转：否
- R2（new-world）：零命中
- R3 变化签名：`appearance_changed*1+moved*1+moved_entity*1|2|60s`

