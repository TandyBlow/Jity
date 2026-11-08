# `c8e04` 持有人与参照物，明确空间关系

- 覆盖：关系、多人物；视角：protagonist；时间：30 秒
- 提交点：`world_30/point_36`，after 摘要 `581bfbf50e572ca3…`
- 页面投影支持：否（见下）

## 能力不支持（单列，不算模型失败）

- P1-non-character-delta：物品位移不在页面叙事投影的支持范围内（`committed-narration.ts:28`）
- P4-position-slot-or-relative：relativeTo 会被投影拒绝（unsupported_narration_position）（`committed-narration.ts:49`）

## 适用范围说明

- 空间相对位置（beside）只在夹具与内核层成立；页面投影拒绝该形状。

## 人工核验项

- [ ] 必须成立：量规是关系主体，聂汀穗是参照物，不反转。
- [ ] 必须成立：位置只支持 beside，不引申交付、所有权或长期人际关系。
- [ ] 必须成立：限于支持 position_relative 的模块，不计当前页面投影成绩。
- [ ] 必须不出现：把未提供的人物或地点写进叙述
- [ ] 必须不出现：把本点没有的变化写成发生
- [ ] 不要求（输入未提供）：完整状态里未进入 mustExpress/currentState 的任何字段

## 程序检查

- R1 v1：candidate；v2：candidate；是否翻转：否
- R2（new-world）：零命中
- R3 变化签名：`moved*1+moved_entity*1|2|30s`

