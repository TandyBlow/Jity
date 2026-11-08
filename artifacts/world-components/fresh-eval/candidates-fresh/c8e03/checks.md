# `c8e03` 父子任务同时校准，另有人完成转移

- 覆盖：任务、多人物、多地点；视角：protagonist；时间：180 秒
- 提交点：`world_20/point_26`，after 摘要 `70aed1eb20028721…`
- 页面投影支持：是

## 适用范围说明

- 父子任务都已达成，事实同时给出人格与理智；不覆盖“父达成/子未达成”的情形。

## 人工核验项

- [ ] 必须成立：明确只达成 ft_check 与 ft_mark，不把 ft_seal 算入。
- [ ] 必须成立：给定事实中的理智是43→47，人格文本保留原意。
- [ ] 必须成立：不因未提输入未给的其他 pending 状态扣分。
- [ ] 必须不出现：把未提供的人物或地点写进叙述
- [ ] 必须不出现：把本点没有的变化写成发生
- [ ] 不要求（输入未提供）：完整状态里未进入 mustExpress/currentState 的任何字段

## 程序检查

- R1 v1：candidate；v2：candidate；是否翻转：否
- R2（new-world）：零命中
- R3 变化签名：`moved*2+personality_changed*1+sanity_changed*1+task_achieved*2|2|180s`

