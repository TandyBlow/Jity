# B2 运行层设计补充（B 侧）

状态：2026-10-24，分支 `world-browser`。批次一范围（用户指令）：HTTP transport 默认 fetch 绑定修复 + B2 串行推理队列、取消与结构化输出。本文是 [分工文档](../browser-world-state-work-split.md) §四 B2 行的实现层补充，只覆盖已交付与下一批边界，不宣称未实现的能力。

## 0. 交付边界

本批已交付：`http-transport` 默认 fetch 绑定修复（`83dbe3b`）；`src/lib/world-engine/runtime/` 下的串行队列、结构化输出校验、引擎接口与 wllama 适配器、模型端口（占位编码器）。全部在 Node 侧以确定性测试验收（fake 引擎控制时序）。

明确不在本批（后续批次）：双心跳与失效处理（下一批，用固定 transport + 可控时钟）；设备能力探测的运行层接线（探测函数已在 `benchmark/environment.ts`，本批不动）；真实提示词与独立质量评测（B3）；真实模型的浏览器端计时 harness（计时埋点本批已就位，实测需要浏览器与模型资产决策，随长推理/心跳批一起落）。

## 1. fetch 绑定（`83dbe3b`）

`HttpWorldTransport` 的默认 fetcher 原为 `= fetch`——Chromium 的原生 fetch 拒绝非全局接收者（`Illegal invocation`），而 `this.fetcher(...)` 调用点把 transport 实例当成了 `this`；Node undici 不挑接收者，显式注入 fetcher 的既有测试因此全部漏过。修复为 `= fetch.bind(globalThis)`，显式注入的 fetcher 语义不变（调用方自持）。测试用严格接收者桩在 Node 复现 Chromium 契约：接收者既非 undefined 又非 globalThis 即抛 `Illegal invocation`；篡改实验（把修复行还原为未绑定）确认该测试恰好转红。

## 2. 引擎接口与 wllama 适配器

`runtime/engine.ts` 定义引擎无关接口：`load()`、`complete(prompt, {signal, maxTokens, temperature, seed, stop})`、`dispose()`、`info {backend, modelId}`。取消是引擎契约的一部分——适配器必须把 signal 传给底层机制。

`runtime/wllama-engine.ts` 适配 `benchmark/wllama-loader.ts` 的 `createWllama()`（浏览器专用：运行时从 `/wllama/index.min.js` 动态导入，Node 不触 wasm）。`complete` 映射为 `createCompletion({prompt, max_tokens, temperature, seed, abortSignal})`；`load` 把调用方 signal 经引擎自有 AbortController 转发给 `loadModelFromUrl` 原生支持的 signal——下载中取消即通知底层。`dispose()` 是**终态**且中途安全：在途下载先被 abort（快速失败），加载完成后才落地的实例被立即 exit 而非登记——无复活路径，`exit` 恰一次或零次（下载失败则无事可清）。参数映射与中途 dispose 均有 Node 单测（注入 fake wllama 断言选项），不加载真实模型。

## 3. 串行推理队列（`runtime/inference-queue.ts`）

单一约束：**同一时刻至多一个推理在跑**，端侧内存预算不允许并发解码。`queue.run(entry)` FIFO 入队，返回 `Promise<QueuedResult<T>>`，`QueuedResult` 携带计时 `{queuedMs, runMs, totalMs}`——加载/推理/取消耗时测量用同一埋点。

取消语义三层，全部以调用方传入的 `AbortSignal` 为准（另有一条统一失败清理规则：`start()` 同步抛出走与引擎失败相同的路径——释放槽位并定局调用方，队列绝不滞留）：

1. **排队中取消**：立即以 `AbortError`（DOMException）定局，从未触达引擎，不占运行槽；
2. **运行中取消**：queue 为运行中 entry 构造 linked signal（调用方 signal 与 `dispose()` 汇合）传入引擎，引擎据此中止；
3. **迟到结果丢弃**：调用方 promise 一旦因取消定局，底层引擎 promise 的迟到 settle 被吞——既不产生 unhandledrejection，也不覆盖已定的 AbortError。迟到的值永远不可达。

`dispose()` 拒绝全部排队、中止在跑、之后拒绝新入队——页面卸载与 B4 交互层的停止按钮共用。

## 4. 结构化输出校验（`runtime/structured-output.ts`）

每个 `ModelTask` 一个 codec。**JSON 任务**（action/targets/results/updates/continuation/initial/time/pointPlan）：先剥 ```json 围栏与首尾空白（0.6B 常见输出形态），再 `JSON.parse`，再按消费端钉死的形状校验——形状全部来自 schedule/controller 的既有消费点，不是新发明：action `{kind:'act',text} | {kind:'skip'}`（schedule.ts:490）、targets `{targets:[{targetId,triggerKey,ruleVersion,target}]}`（:603）、results `Record<Id,string>`、updates **双形态**——批量模式消费调用数组、拆分模式（updatesStages）消费单个调用，均合法且不归一化穿透（controller.ts consumeModelOutput 按 mode push）、逐字段校验 EntityDelta 闭集（positionSet/appearanceChanges/sanitySet/tasksAchieved/subtasksAdded 及嵌套 Change/Position/Task，未知字段拒绝——mergeUpdatesStages 不会再遇到吞不下而 TypeError 的形状）、continuation 判别联合（types.ts:37）、initial `InitialTemplate`（含 engineVersion/schemaVersion 常量）、time `TimeAdvance`、pointPlan `PlannedPoint[]`（actorIds 允许为空——T03 无行动时间扫描点与空 linked 点）。**文本任务**（narration/reaction）：非空字符串原样，不做任何 JSON 解析——叙事质量结论（JSON 契约对 0.6B 叙事是毒药）不因校验层回潮。

失败抛 `StructuredOutputError {task, reason, raw}`，端口如实上抛。**本批不做修复重试**：输出质量与重试策略属 B3 提示词层，校验层只负责"形状不对绝不让它进入 controller memory"。

## 5. 模型端口（`runtime/model-port.ts`）

`RuntimeWorldModelPort implements WorldModelPort`（controller.ts 的三参接口；实现多带可选 `signal`，结构类型兼容，controller 不动）。`generate(task, key, input, signal?)`：encode(input) → prompt → queue.run(engine.complete) → decode(text) → 校验后的 Json。encode 本批是**占位编码器**（确定性 JSON 包装，标注 B3 替换），decode 是本批真交付。端口暴露队列计时与引擎 info。

## 6. 验收

Node 侧确定性测试：queue 的 FIFO/排队取消/运行取消/迟到丢弃/dispose/计时；校验器十任务正反例（含围栏剥离、形状破坏、闭集外值、空文本）；端口十任务 fake 引擎往返与 abort 透传；wllama 适配器参数映射。真实模型计时：埋点（QueuedResult.timing + 引擎 info）已就位，浏览器实测随长推理/心跳批交付。
