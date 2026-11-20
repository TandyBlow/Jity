# 04-settlement 聚焦验证

本目录只放本线可独立运行的检查，不启动整套前端测试、构建或真实模型推理。

```bash
node frontend/scripts/parallel-settlement/run-focused.mjs
```

测试文件：`frontend/src/lib/world-engine/local/semantics/settlement/settlement.test.ts`（语义单元）、`settlement-integration.test.ts`（真实 controller + 本地 transport 接线），以及 `frontend/src/lib/world-engine/local/turn-execution/real-world.test.ts`（真实 14 人/73 任务世界 + 17:37 无依据全达成回放）。

覆盖：

- 共同结果：多名成员共享事实、逐成员事实归属、未准入骰点不得写成目标反应；未声明 target 的 effect 会触发一次具名修复，修复仍失败就中止整点，不再编造“保守结果”。
- 六阶段：位置→外貌→任务→新增小任务→个性→理智的顺序；人物/物品移动；任务阶段改为“每个有任务的人物一条决定”，但提示只列本轮受影响人物（事实 actor/事实提到的实体/已确认场景/直接位置外貌变化/明确时间条件/全局事实）；全量 14 人/73 行由程序 `taskScope` 审计，未列出的行保留并记 no-dependency basis，不默认 pending 也不算模型已判断；全局事实展开全部，场外被事实点名的人物仍进入；缺整位受影响人物是覆盖失败；个性扫描触发任务所有者+事实/场景参与者，程序审计全 14；已完成任务不重做；个性变化与理智一一配对；任何阶段修复失败都会中止整次 updates，不提交部分六阶段。
- 时间扫描：跳过位置/外貌模型调用；任务提示只列有时间条件或全局触发的任务，其余由程序审计；没有个性变化就不写理智。
- 拆分阶段：返回单个 `UpdatesCall`；后序阶段从已应用的工作态读取；同批任务达成触发个性阶段。
- 结果事实：模型给出的结果事实若带“行动成功完成/成功完成/任务完成/任务达成/目标达成/成功执行行动”等任务或成功结论，结算器只删这些结论短语并保留可观察行动，证据记 `sanitizedFacts`；删空则触发修复，不生成默认事实。b7cd 的 `诺诺…行动成功完成` 和 21c3 的 `确认任务完成并检查…` 都走这条。
- 重复未变化组：位置/理智阶段只回显当前值的 delta 不算进展，从真实变化中剔除并在证据里记 `droppedNoopEntityIds`；单个位置条目的坏引用（21c3 的 `lane/slot_waist`）按条拒绝并记 `rejectedPositionEntries`，同一条里的有效移动保留；字面 placeholder 仍是修复契约，修不好就中止整点。
- 继续判断：likely+related 才继续；无候选交还；连续 2 轮无状态进展、或同一 accepted 候选重复 1 次即按策略交还（21c3 三条相同 nono 候选，只允许首个自动回合）；模型异常返回失败而不是交还；默认没有 0 次调用上限。
- 接线：脚本化 engine 经 `createSettlementHandlers` 驱动真实 `ControllerDriver` + `LocalWorldTransport`，results/updates/continuation 的输出形状被 controller 接受并提交一个完整回合。

## 提示词规模探针（L1，不跑模型）

```bash
cd frontend && node scripts/parallel-settlement/prompt-size.mjs
```

同一冻结世界、输入和代码版本下运行；root 已实跑约 1 秒，root 当时最大 4374 **字符**；本线加入在场人物持有物召回后重跑，当前最大 4656 **字符**（都是字符，不是 token），本次聚焦 59 通过 | 1 预期失败约 3 秒（以 `run-focused.mjs` 实际输出为准，不重复跑 root 基线）。脚本故意让每个模型调用失败以取出真实提示词，所以：

- 报告的是 `chars`，不是 token；没有分词器，禁止用 chars 除以 tok/s 报真实耗时。
- 失败会触发现有修复重试，`promptChars` 里包含这些**探针诱发的重试**；它不是成功产品的真实调用次数。
- 只用于和同一 fixture/阶段/版本的前后对比；不能证明模型决策、叙述质量或 60 秒时延。

探针取前 3 个排序角色和一条合成事实，prompt 只代表这个 fixture；真实页面仍以 09 的 L5 账本为准。

真实浏览器/模型推理未在本目录运行，需由主集成方在真实页面上复测。

## 真实页面账本检查（09 证据只读复核）

09 从 `/world-local` 收集到 `window.__worldSubmission` 之后，可以只读检查本线关心的不变量：

```bash
node scripts/parallel-settlement/check-run.mjs <09 的证据文件> --cast 14
node scripts/parallel-settlement/check-run.mjs <09 的证据文件> --timings
node scripts/parallel-settlement/check-run.mjs --self-test
```

接受的输入：单个提交对象、`{submissions:[...]}`、或 `{turns:[{submission:...}]}`。
检查项：每个提交是否真的跑了 results / 六阶段；阶段是否按 位置→外貌→任务→新增小任务→个性→理智 且不重复；任务覆盖是否等于全人物数（默认 14，自由一日世界）且 `taskRows`（世界任务行数，当前 73）不小于人物数；个性覆盖是否也为全人物；策略停止是否被误记成模型交还；`continuationDecision=failed` 是否只是可见失败而不是正常交还；整次提交起止时间是否存在。旧证据没有 `taskRows` 时只记软问题。
`--timings` 额外输出每次提交的 results 耗时、六阶段各自耗时合计和整次提交耗时，用来定位慢在哪个阶段。
硬失败退出码为 1，软问题（回退、策略停止、缺计时）只记录不拦截。它不判断文风，也不替代 01/09 的验收。
