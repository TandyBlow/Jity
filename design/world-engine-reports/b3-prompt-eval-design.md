# B3 提示词评测设计（B 侧）

当前进展（2026-10-27）：已完成“模型适配器修复＋三个任务的浏览器真机短测”，
实现 `c25ede4`。六条结构均过，逐条内容复核 action 2/2、updates 0/2、narration 1/2；
当前模型不能直接持有状态变化决定权。原始输出、耗时、分工与复跑方式见
[短测记录](../../artifacts/b3-short/README.md)。未重跑全量 B3，最小页面留待事实/规则边界接线。
以下保留批次一与旧基线的历史配置及结论。

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

`runB3Evaluation(engine, samples, options)` 把样本逐一过**真实**模型端口（encode → 串行队列 → 引擎 → 结构化解码）；harness 以**包装引擎**计数实际 `complete` 调用——显式四方法转发（info/load/complete/dispose，保持原接收者；对象展开会丢类实例的原型方法），不依赖引擎配合，加载失败=0 次。逐样本记录**失败阶段**（`engine | structure | semantic | judge`——judge 崩溃是评测基建故障：结构与耗时保留、仅缺底线裁决）、错误留档、语义底线（可插拔 judge）、队列计时——**结构拒绝保留已付的生成耗时**（端口在 decode 失败时把完成 timing 附于异常）。按任务聚合：结构率、底线率、实际引擎调用数（`InferenceEngine.callsMade?`，加载失败=0 次）、平均排队/推理毫秒（含结构拒绝的生成）；`formatB3Summary` 出单行控制台摘要。

**默认语义底线**（确定性，内容级语义质量随真机评测+更强 judge）：叙事 ≥10 字/反应 ≥4 字；action 文本 ≥2 字；targets 的 targetId 必须在**角色名册**（workingState characters 双区——触发目标不是物品或地点）、pointPlan 的 actorIds、continuation 的候选都必须在**该输入的名册**里（updates 用 characters/items/locations 三元实体名册，plan/continuation 用 round.order）；results 至少一条；updates 增量实体必须在册；time/initial 顶层契约即可。judge 按 task 可覆盖注入。

## 4. 边界与下一步

本批不宣称：真机结构率/质量数字（引擎注入 wllama 后同 harness 出数）、内容级语义评分、提示词迭代结论（编码器可换，harness 不动）。恢复子批次/H2 仍持有授权恢复与未决对账。

## 5. 批次二：浏览器真机基线（scripts/run-b3-baseline.mjs）

真机基线评测入口（B 侧自有，编排模式对齐 A 侧 H1）：临时 Vite（frontend root，hmr 关闭、随机端口）+ Playwright 真实 Edge headless + 页面内动态 import runtime 模块，**同一 harness** 跑 B3_SAMPLES 全量，报告落盘 `artifacts/b3-baseline.json`。

**固定基线配置**（写入报告，提示词迭代必须同配置对跑）：模型 `/models/Qwen3-0.6B-Q4_K_M.gguf`（本地资产，同源加载——benchmark 页已验证的路径）、contextSize 4096、maxTokens 1024、temperature 0、seed 42、真实 Edge headless（`--channel` 可换）。harness 新增：`B3EvalOptions.portOptions`（采样参数透传给 harness 自建的端口）、`B3SampleResult.raw`（每次 completion 的原始生成文本——基线证据，prompt 迭代据此判断改什么）。

单线程运行（无 COOP/COEP，与 benchmark 页现状一致）——首基线先取真实数字，多线程吞吐是后续优化。运行时长 20 样本预计 10–40 分钟，脚本后台执行、child server 在 finally 关闭。

**评审修正（2026-10-25）**：页面控制台日志改**全类型转发**（原只转 error——`onSample` 的进度走 console.log 不可见，慢与停滞无法区分，用户评审指出）；报告 `status` 由 'PASS' 改 **'COMPLETED'**——只表「评测执行完成」，质量判定看报告内各率，不在此字段混入。首轮运行因进度不可见被中止、未出报告；修正后重跑。另：本基线只回答**旧路径**（单模型自回归）每次调用成本，仅作参考；叙事表达拆分流水线各段的延迟须同输入/同输出要求/同设备实测，且拆段后的重复输入处理开销必须计入（见 narration-split-experiment-design.md §3）。

**短诊断与归因边界（2026-10-25，用户复核后收窄）**：全量长跑中止（5/20 样本，全部 structure 失败、单次 1027–1378s；raw 输出随进程丢失，stdout 日志保留阶段与耗时；runner 已加逐样本断点保存）。短诊断（scripts/diagnose-wllama-short.mjs，报告 artifacts/wllama-diagnostic.json）：原始路径（现适配器）prefill 696 tok 约 138s、`finish_reason="length"`、合法 JSON 后续写至长度上限；聊天模板＋关思考后 EOS 干净（18 tok）；加 json_schema＋前缀缓存 10.9s 且解析通过。**归因边界**：P3 同时开启 schema 与缓存（cached 707/708），提速不能分别归功，也不代表真实变化输入稳定命中同比例；长跑耗时组成为推测非逐次证实；P2/P3 对 person_a 提示词输出主角行动——格式改善≠语义正确。结论仅到「该配置下失败且极慢、失败模式可定位」，不据此承诺全量时长；**暂不重跑全量 B3**。适配器修复（模板/关思考/约束解码/maxTokens/cache_prompt/计时元数据）列为独立修复项，不挤占调用链对齐主线（见 model-task-alignment-fix-list.md §4）。
