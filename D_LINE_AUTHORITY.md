# D 线权威流程与接线

2026-11-10。权威分支：`codex/api-small-model-windows-20261110`。
本文件取代旧多小模型路线及 `scripts/hybrid/run.py` 两次 API 演示作为开发目标；旧实验及报告保留为历史。

## 实现入口

`frontend/src/lib/world-engine/runtime/d-line.ts` 的 `createDLineDriver` 组合原有
`ControllerDriver`、调度器和 A `WorldTransport`。不是另建一套世界状态机。

- API ①：当前工作状态下的 act/skip；资料不足明确 incomplete。
- D03：必须调用本地预测端口；不再额外调用目标 API，不按模型置信度自行宣布质量通过。
- 原调度器负责冻结、实际骰点、准入、深度优先扩组、已行动人物去重；每个新增反应一次 API。
- API ②：共同结果＋全部 U1—U6 候选一次生成。共同结果必须覆盖全组成员。
- 六阶段候选按顺序交原控制器预览，最后 U6 也须预览后才能暂存。字段不得跨阶段。
- 失败只重生成未通过后缀，使用最后成功的实际预览状态及已通过前缀；不重生成行动、结果或骰点。
  默认最多两次修复。非法结构、上下文缺失或预算耗尽明确停止，不生成空变化冒充成功。
- 整单元暂存后继续人物；原有 seal/commit 边界保持，C 仍由提交态叙事入口调用。
- 全部 skip/无人行动时仍生成一份完整时间扫描候选，依次预览。
- D07、D08 当前采用安全的独立调用，读取实际最新状态，不缓存预测性建议。
  D07 检查候选拟行动、发生可能性及主角关联的两个布尔判断；只有两者为真才交程序确认继续。
  新轮次 ID 必须由程序回调分配。没有分配器则 incomplete，不能让 API 发明正式 ID。
  附带建议优化尚未启用，因此不存在修复后沿用旧建议的问题。

正常预算以**一个行动结算单元**计：2 次 API；新增反应各 1 次。
skip 只需行动判断 1 次。D01、D07、D08、纯时间扫描、失败修复另计，C 叙事不计入 D 结算预算。

## D01

`runtime/d-initial.ts` 的 `generateDInitial` 接受设定、批次数量和初始时间。
程序先分配人物、地点、物品及任务 ID；API 分别填充地点、物品和人物（含外貌、个性、理智、任务）。
程序检查 ID 覆盖、位置图及任务树的未知引用/环、任务所有者。
返回草稿交原 `create_world`，A 完成深层 schema 校验并保存 S0。
初始模板或初始化函数只在无世界时调用，不放入每回合结算。

## 接到 A/B/C

```ts
import { createDLineDriver, dBridge } from './runtime/d-line';
import { generateDInitial } from './runtime/d-initial';

// 在本地桌面或可信服务端调用；不要把桥接令牌/API 密钥打包进网页。
const bridge = dBridge('http://127.0.0.1:8766', bridgeToken);
const { driver, port } = createDLineDriver({
  transport: authorityTransport, // 对应版本的 A WorldTransport
  memory: preparedControllerMemory, // B 原有冻结顺序/身份分配计划
  api: bridge.api,
  d03: bridge.d03,
  narration: committedNarrationPort, // C，仅接受正式提交的 before/delta/after
  initial: () => generateDInitial(bridge.api, initialOptions),
  allocateRound: allocateNextRoundFromA, // 按当前轮次幂等分配，并由 B 准备下一轮槽位
  repairBudget: 2,
});
await driver.run();
```

此组合复用 A/B 协议，不附带新的 A 服务实现，不更改其他分支，也不自动替换现有网页运行时。
调用者须提供匹配 A transport、B 身份/时间计划和 C 端口。刷新时使用原 driver.recover；服务端已确认的
单元直接恢复。未确认的合并响应只存在端口内存；缺失时明确停止，不能猜造候选或重掷已冻结骰点。

## 本地 MacBERT 桥接

```powershell
# 先按 DEVELOPMENT_WINDOWS.md 训练本机模型；令牌需使用随机私密值，至少32字符。
$env:JITY_BRIDGE_TOKEN = '<本机随机私密令牌>'
# JITY_API_KEY / JITY_API_MODEL / JITY_API_BASE_URL 保留在服务端环境。
.\.venv-d03\Scripts\python.exe scripts/hybrid/serve.py --model-run .local/d03-macbert/runs/my-gameplay-v1
```

服务仅监听 127.0.0.1，验证 Bearer 令牌，拒绝浏览器跨域请求，不提供任意文件访问。
`/api` 使用已有 JSON API 客户端；`/d03` 使用真实 `local_predict`，校验 checkpoint 哈希、冻结阈值、输入长度。
D03 当前训练支持 2–3 人，超过支持范围或 512 token 明确失败；不截断完整状态、不静默回退 API。
完整状态投影与原短文本训练数据分布不同，真实世界覆盖与质量仍需评测；此次接线不是模型质量验收。

## 验证

```sh
cd frontend
npm ci
npm run typecheck:world
npm test -- src/lib/world-engine
cd ..
python -m unittest discover -s scripts/hybrid -p 'test_*.py' -v
```

测试覆盖调用预算、skip/incomplete、本地失败、单反应、完整六阶段、非法字段、后缀修复、
纯时间扫描、输入变化拒绝、D01 身份、D07 双条件与程序分配，以及既有调度/冻结/提交机制。
受控替身验证编排，不能代替真实 A 服务、付费 API、完整 MacBERT 或浏览器整链验收。

## U5 中间预览与最终保存（2026-11-10 修订）

`preview_point.settlementGroups` 的最后一个单元可以使用独立类型 `U5PreviewGroup`，
必须带 `previewStage: "U5"`，包含非空个性变化，且 `sanities` 为空；其他单元仍必须完整配对。
仅这个显式类型获得例外。U6 完整预览不再带此标记。

`SettlementGroup` 的最终配对校验保留。`stage_unit`、`stage_time_scan`、`commit_point`、
恢复保存的候选都不接受 U5 类型；提交的 point.entityDeltas 也独立要求个性与理智成对，
避免复制临时投影并清空结算组绕过校验。位置、任务前置条件等共同检查仍执行。

控制器保留 U5 实际预览后的工作状态，清除该临时投影的 commitPayload。
U6 失败时将 U1–U5 原样传给定向修复，使用 U5 的实际状态，不重掷骰点、不重新生成行动。
成功后执行完整预览；预算耗尽明确停止。U5 临时状态不会作为存档提交。

真实验证包含：Python Pydantic 请求模型、A 的纯状态投影内核、前端 AJV/语义请求校验，
以及控制器失败/恢复测试。未声称已部署在线 A HTTP 服务或进行了真实付费 API 游戏。

### 复用来源及协议一致性

`backend/app/services/world/{apply,merge,state,timing,violations}.py` 来自
`world-server@fc60a603c7e0b57805fffea0458192bcfebf6ffc`，预览模块在该版本上增加显式 U5 请求验证；
没有合并整个分支或迁入其数据库/运行环境。

为保持重新导出的协议与既有接口一致，同步了该 A 版本已有的冻结骰点/DFS恢复模型和
get_context 错误登记，并修正 D 原源码中的版本混用：v2 响应信封为2，初始世界/WorldState与轨迹格式仍为1。
轨迹文件仅更新 contractDigest 绑定，不改业务步骤或预期答案。最终候选配对约束没有放宽。
