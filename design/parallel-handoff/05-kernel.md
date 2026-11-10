# 05-kernel handoff

## 问题

浏览器本地 `WorldState` 内核与 transport 已有基础实现，但真实输入的契约面缺口集中在：

- 位置/槽位/相对引用只做部分检查；两点合并里的位置冲突用 `JSON.stringify` 比较，可选字段缺省与显式 null 会被误判为不同。
- 任务层级没有做新增任务环检测、父子层级排序；`tasksAchieved` 与 `subtasksAdded` 的同点折叠依赖调用方。
- `supersedes` 没有拒绝同点自 supersede、纯删除无 supersede、跨 appearance/personality 的重复 change id。
- 时间解析让 JS `Date` 把非法日期（如 2 月 30 日）静默滚到下个月，年份格式也没有按 Python `isoformat` 补零。
- 没有静态 `WorldState` 加载入口：页面只 `JSON.parse` 后取 `initial`，重复键、非法数字、Unicode、当前状态与 initial 不一致、登记摘要不一致都没有拒绝路径。
- transport 直接把请求里的候选组和 point 入库，没有按 Python `SettlementGroup` / `EntityDelta` 的规范形状做规范化，导致内容哈希和 point digest 与 Python 不可比。

## 实现

### `frontend/src/lib/world-engine/local/state.ts`

- `normalizeInitialState`：按 `WorldInitialState` 契约校验/规范化（实体 id、全局唯一、槽位、容器、相对引用、位置图无环、相对同房间、任务 id/owner/parent/无环、文本、sanity、时间、额外字段拒绝）。`buildInitialState` 现在先规范化，再构造 S0，所以缺省 `slots` 和 position null 会补成 Python `model_dump` 的形状。
- `normalizeWorldState`：针对完整 `WorldState` 规范化当前 locations/items/characters，检查注册表与 initial 一致、当前任务父子/无环、当前位置。
- `advanceTime`：严格 Gregorian 日期校验；月/年按月末截断；零时长只增加 `instantOrdinal`；年份 4 位补零；超出 1..9999 拒绝。
- `checkPositions` 保留原来的联合图检查；`pointEntityDeltas` 现在先规范化每个组，位置冲突用规范化后的 canonical 比较，任务做新增/达成折叠和层级排序，最后用 `normalizeEntityDelta` 产出 Python 兼容的投影（空字段省略）。
- `normalizeEntityDelta`：change id 跨 appearance/personality 唯一、supersedes 去重排序、拒绝同点 supersede/自 supersede/纯删除无 supersedes；新增任务 owner/parent/重复/环检查并按 level+id 排序；sanity 0..100。
- `normalizeTimelinePoint` / `replayWorld`：point kind/boundary/linked 规则、delta key 与 entityId 一致、实体 delta 规范化；回放逐点 `applyPoint`，不修改起始状态。
- `normalizeSettlementGroup`：按 Python 模型补显式 null、排序 identity set、拒绝空候选 map、时间扫描组不能有 actors/positions/appearances。

### `frontend/src/lib/world-engine/local/canonical.ts`

- 对象 key 的 ASCII 检查改为 Python `str.isascii()` 的等价范围（允许控制字符，之后按 `_string` 转义），并检查 key 里的孤立 surrogate。

### `frontend/src/lib/world-engine/local/transport.ts`

- 现有 `create/restore/execute/snapshot` 兼容不变；内部在 `begin_point` / `set_point_time` / stage unit / stage time scan / preview / commit 处调用规范化。
- 内容哈希用规范化后的 `SettlementGroup`；commit 用规范化后的 point 和 groups 做前缀绑定、deltas 相等、应用和持久化。失败仍由既有 draft-copy 事务丢弃，不留下半状态。
- 幂等 requestId 路径未改；新增测试覆盖“拒绝的 create 不改已提交记录”和“重复 pause 不重复加 revision”。

### `frontend/src/lib/world-engine/local/world-loader.ts`（新）

可调用入口：

```ts
loadStaticWorld(
  text: string,
  registration: { stateDigest: string; fileSha256Lf?: string; initialDigest?: string },
  options?: { requireS0?: boolean },
): Promise<LoadedStaticWorld>

readStaticWorldValue(value: unknown): {
  initial: InitialState; template: InitialTemplate; state: WorldState; s0: WorldState;
}

parseStaticWorldJson(text: string): unknown
```

`LoadedStaticWorld` 返回 `worldId / initial / template / state / s0 / stateDigest / s0Digest / initialDigest / fileSha256Lf / counts`。

拒绝语义：

- `parseStaticWorldJson`：重复对象 key、非整数或超安全整数、`1e999`、非 ASCII key、孤立 surrogate 转义、控制字符未转义、尾随字符。
- `readStaticWorldValue`：契约字段/引用/循环/任务/位置图/注册表校验；`StaticWorldError('schema', ...)`。
- `loadStaticWorld`：文件哈希（LF 归一化）、initial 摘要、state 摘要、S0 一致性。默认 `requireS0: true`；不一致抛 `StaticWorldError`，不是警告。
- 文件哈希使用 CRLF/CR → LF 归一化后的 UTF-8，匹配 git blob；原始工作树 hash 记录在 fixture 里。

## 接线示例

页面独占文件当前是：

```ts
const world = await (await fetch('/worlds/dragon-raja-free-day.world.json')).json();
...
LocalGameSession.create(world.initial, model, { worldId: world.worldId });
```

主 agent 改成：

```ts
const text = await (await fetch('/worlds/dragon-raja-free-day.world.json')).text();
const loaded = await loadStaticWorld(text, {
  stateDigest: '3f65452daf352c636ac4b24dcefcfb1cc8633ee811a6613a34ce5c43ef233f4e',
  fileSha256Lf: '6262d5fcf088959bb427fbd2dfef7472bcf2cbf78edb9c76b98d4ea2b25db92e',
  initialDigest: 'c82f058fda8fbe8000887b36b05a9b62a1bf5ae72672f3460472056381061ccb',
});
const session = await LocalGameSession.create(loaded.template, model, { worldId: loaded.worldId });
```

`loaded` 失败时不要 `start()`；把 `loaded.stateDigest` 写进存档元数据，供恢复/同步核对。`template` 不含 `worldId`，`worldId` 单独传入。

## 验证

```powershell
cd frontend
npx vitest run src/lib/world-engine/local/state.test.ts src/lib/world-engine/local/canonical.test.ts src/lib/world-engine/local/world-loader.test.ts src/lib/world-engine/local/local-transport.test.ts --maxWorkers=1
npx tsc --noEmit -p tsconfig.world-contract.json
npx tsc --noEmit -p tsconfig.json
```

结果：4 个测试文件、82 个测试通过；两个 typecheck 通过。CPU 测试未启动模型/浏览器 GPU。

差分来源：`fc60a603c7e0b57805fffea0458192bcfebf6ffc`；具体 Python 文件哈希、世界文件哈希和 fixture 哈希见 `frontend/scripts/parallel-kernel/README.md` 与 fixture 的 `source` 块。

## 限制

- 未改页面/主模型/公共 controller/schedule/types；页面接线由主 agent 完成。
- 未运行真实模型、浏览器页面或 GPU；本线只交付内核、transport、加载器和 CPU 差分。
- `validateStaticWorld` 保留为 initial-only 兼容 helper；完整静态文件入口是 `world-loader`。
- `replayWorld` 与 Python `replay_world` 一样只逐点应用，不额外验证 previousPointId/sequence 连续链；point 自身契约仍由 `normalizeTimelinePoint` 检查。
- transport 仍保留既有协议错误码映射（`id_unresolved` → `version_mismatch` 等），本次没有扩大 wire 错误码表。
- `fileSha256Lf` 是 LF 归一化后的文件哈希；如需逐字节哈希，调用方应自行计算并通过其他字段登记。
