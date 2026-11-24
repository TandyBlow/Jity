# Tasks: goal-micro-workflow

- [x] 1. targets 微型端口：`microTargets` 契约、source=`micro`、弃权/拒绝/失败原因、单元测试（41 通过，tsc 干净）。
- [x] 2. 页面开关与模型加载：JS 分词器（Python 对照 24/24）、ORT-WASM 运行时（缓存/release/计时）、int8 打分器与 vocab 资产；`?micro=1`，默认关。
- [x] 2b. 真实回合 targets 规则路径：1 输入 COMPLETED，6 次 `micro_targets`，1 次非空目标；模型打分路径未触发。
- [ ] 3. results/updates/continuation 微型路径（规则产出 + 现有校验 + LLM 回退原因）。
- [ ] 4. 统计：每任务 rules/micro/LLM 次数与耗时；首载 vs 回合耗时。
- [ ] 5. 真实 20 输入对照（开/关）：回合耗时、结算错误、检查器、叙事质量。
- [ ] 6. action/reaction 拆分：规则解析 + 专用头 + LLM 回退；开放式文本仍用 LLM。
