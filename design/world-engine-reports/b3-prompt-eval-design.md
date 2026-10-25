# B3 提示词评测设计（B 侧）

状态：2026-10-25，分支 `world-browser`。批次一范围（用户指令）：替换占位编码器、冻结任务样本、评测 harness 分报结构正确率/语义质量（底线版）/调用次数/耗时。真机（wllama 实模型）数字随真机批；本批交付的 harness 引擎可注入——同一代码路径，脚本引擎确定性验收，真机引擎出数字，无需改动。

## 1. 提示词层（runtime/prompts.ts）

`buildTaskPrompt(task, key, input)` 取代 B2 占位编码器（model-port 的 `encodePrompt` 现为其别名再导出，既有确定性测试不变）。三段式：任务标签、输出契约、声明调用的序列化输入（updates 拆分调用附本调用阶段与单对象指令）。要点：

- **契约与 codec 对齐**：提示词教的形状就是 structured-output.ts 校验的形状（codec 是权威）；不发明第二种 schema 描述。
- **叙事/反应是文本任务**：指令显式「不要 JSON、不要标题、不要列表」——JSON 契约毒害小模型散文的结论不回潮。
- **updates 互斥契约**：契约表不含 updates——按调用模式动态选择互斥指令（批量教数组、拆分只教单对象并明说「不要数组」），不追加相反指令。
- **确定性**：纯函数于 (task, key, input)，评测重放稳定。

## 2. 冻结样本（runtime/b3-samples.ts）

20 份冻结样本（每任务 ≥2）：输入形状逐一取自 schedule.ts 的真实决策输入（action/targets/reaction/results 带 workingState；continuation/pointPlan 带 round+head；updates 双模式各一；time 含零时长 instant；narration 带 pointId+stateDigest）。workingState 为 T01 school 世界的紧凑形状真实片段（三角色/一物品/一任务），每样本溯源标注（T01 派生 + 冻结日期）。语料是提交内夹具，不随轨迹漂移。

## 3. 评测 harness（runtime/b3-eval.ts）

`runB3Evaluation(engine, samples, options)` 把样本逐一过**真实**模型端口（encode → 串行队列 → 引擎 → 结构化解码），逐样本记录**失败阶段**（`engine | structure | semantic`——加载失败/引擎异常与结构拒绝分档）、错误留档、语义底线（可插拔 judge）、队列计时——**结构拒绝保留已付的生成耗时**（端口在 decode 失败时把完成 timing 附于异常）。按任务聚合：结构率、底线率、实际引擎调用数（`InferenceEngine.callsMade?`，加载失败=0 次）、平均排队/推理毫秒（含结构拒绝的生成）；`formatB3Summary` 出单行控制台摘要。

**默认语义底线**（确定性，内容级语义质量随真机评测+更强 judge）：叙事 ≥10 字/反应 ≥4 字；action 文本 ≥2 字；targets 的 targetId、pointPlan 的 actorIds、continuation 的候选都必须在**该输入的名册**里——名册=workingState 的 characters/items/locations（live+initial）三元构造或 plan/continuation 的 round.order；results 至少一条；updates 增量实体必须在册；time/initial 顶层契约即可。judge 按 task 可覆盖注入。

## 4. 边界与下一步

本批不宣称：真机结构率/质量数字（引擎注入 wllama 后同 harness 出数）、内容级语义评分、提示词迭代结论（编码器可换，harness 不动）。恢复子批次/H2 仍持有授权恢复与未决对账。
