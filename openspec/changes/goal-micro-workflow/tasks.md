# Tasks: goal-micro-workflow

- [x] 1. targets 微型端口：`microTargets` 契约、source=`micro`、弃权/拒绝/失败原因、单元测试（41 通过，tsc 干净）。
- [x] 2. 页面开关与模型加载：JS 分词器（Python 对照 24/24）、ORT-WASM 运行时（缓存/release/计时）、int8 打分器与 vocab 资产；`?micro=1`，默认关。
- [x] 2b. 真实回合 targets 规则路径：1 输入 COMPLETED，6 次 `micro_targets`，1 次非空目标；模型打分路径未触发。
- [x] 2c. 任务级浏览器探针（10 例）：原始打分器 5/10，否定/代词/复合过报；改为「规则提议 + 打分器校验 + 弃权回 LLM」，并记 `probe-scores.json`。
- [x] 4a. 单回合任务耗时分布：results 97.8 s / action 81.4 s / updates 55.1 s / targets 6 ms；下一步优先 results 与 updates。
- [x] 4b. 真实语义输入/输出采集（`?record=1`）：一轮 79 对（results 21、updates 18、action 24、targets 11、reaction 1、continuation 4）；拆分与训练计划见 `task-decomposition.md`。
- [x] 4c. 校验感知采集：每调用记录 raw/value/issues；一轮 133 调用 99 有效 / 34 无效；位置槽位校验抓出 `lu@lane/slot_body` 类无效标签；`training.jsonl`/`training-report.json`。
- [ ] 5. 按任务训练专用微型头（共享编码器）：results 5 类、act/skip、updates 移动/位置、continuation likely；回合切分评估。样本量不足，先补 2–3 轮采集并抽查。
- [ ] 6. 集成 `?micro=1` 路由并统计比例/耗时；完整回合 A/B。
- [ ] 3. results/updates/continuation 微型路径（规则产出 + 现有校验 + LLM 回退原因）。
- [ ] 4. 统计：每任务 rules/micro/LLM 次数与耗时；首载 vs 回合耗时。
- [ ] 5. 真实 20 输入对照（开/关）：回合耗时、结算错误、检查器、叙事质量。
- [ ] 6. action/reaction 拆分：规则解析 + 专用头 + LLM 回退；开放式文本仍用 LLM。
