# 04-settlement 聚焦验证

本目录只放本线可独立运行的检查，不启动整套前端测试、构建或真实模型推理。

```bash
node frontend/scripts/parallel-settlement/run-focused.mjs
```

测试文件：`frontend/src/lib/world-engine/local/semantics/settlement/settlement.test.ts`（语义单元）与 `settlement-integration.test.ts`（真实 controller + 本地 transport 接线）。

覆盖：

- 共同结果：多名成员共享事实、逐成员事实归属、未准入骰点不得写成目标反应、模型连续无效时的保守无变化结果。
- 六阶段：位置→外貌→任务→新增小任务→个性→理智的顺序；人物/物品移动；全人物任务与个性覆盖；已完成任务不重做；跨人物任务达成；个性变化与理智一一配对；理智非法时不夹取、保留当前值并记录回退。
- 时间扫描：跳过位置/外貌模型调用，仍扫描全部任务；没有个性变化就不写理智。
- 拆分阶段：返回单个 `UpdatesCall`；后序阶段从已应用的工作态读取；同批任务达成触发个性阶段。
- 继续判断：likely+related 才继续；无候选交还；连续无状态进展或重复候选按策略交还；模型异常返回失败而不是交还；默认没有 0 次调用上限。
- 接线：脚本化 engine 经 `createSettlementHandlers` 驱动真实 `ControllerDriver` + `LocalWorldTransport`，results/updates/continuation 的输出形状被 controller 接受并提交一个完整回合。

真实浏览器/模型推理未在本目录运行，需由主集成方在真实页面上复测。
