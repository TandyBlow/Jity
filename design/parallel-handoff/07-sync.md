# 07-sync handoff：进度同步服务与浏览器客户端

分支 `goal/local-07-sync`，工作树
`D:/others/Jity/.local/parallel-local-game/worktrees/07-sync`，基线
`865ae64e0901a70c3db4f1d0eb2af60268943c53`。

## 问题

浏览器本地游戏已经能在本地保存 `LocalGameSnapshot`，但两台设备之间无法
接续：没有内容身份、没有父链、没有条件写入，也没有把离线分支和在线分支
同时保留的机制。直接按时间戳“谁新用谁”会覆盖另一台设备已经玩过的进度。

本线只做“存取”：服务端保存不透明 payload 和同步元数据；游戏推理、状态
结算、掷骰和事实校验仍全部在浏览器/现有内核。06 负责本地仓库和会话，
本线只通过注入的 `load/save` 接口消费它，不直接改其存储。

## 状态范围、来源与上限（给 02/06 的交代）

**同步的是什么。** 06 的 `LocalGameSnapshot` 整份：`transport`（点位、每点正文
`narrations`、骰点、半结算 `work`、世界 `state`、head）加 `commands` 和可选
`checkpoint`。服务器把它当**不透明字节**存：算 SHA-256 内容摘要、记父子引用和
revision，**不解析 transport、不改写正文、不重算状态、不调模型**。所以：

| 问题 | 答案 |
|---|---|
| 谁是状态的唯一写入者 | 06 的 session。本模块默认只上传，`writeLocal:true` 只给没有 session 写入者的调用方 |
| 服务器能改正文吗 | 不能。它只比较摘要、校验父子关系和大小，原样返回 |
| 02 和同步的关系 | 02 的正文在 `narrations` 里随快照走；服务器不校验叙事质量，也不修正。正文是否合格仍由 01/02 的流程判定 |
| 分叉时谁决定 | 玩家。两条都保留、都可读；`choose()` 只移动“激活的头”，不删除另一条 |
| 能自动合并吗 | 不能。两边都前进就是 `diverged`，必须显式选择；不会静默覆盖 |
| 02/06 能拿它做重放吗 | 只能由 06 的 session 打开快照重放；服务器不提供“按回合重算”接口 |

**完整性：** 服务端保存的是不透明字节 + 规范化 JSON 的 SHA-256 + 字节数。每次读取都会
重算摘要和大小，和记录不一致就返回 `500 snapshot_corrupt`，不会把被改过的内容当成
玩家的世界交回去；读失败时客户端 `restore()` 报 `unavailable`，不会当成“远端是空的”。
（2026-11-10 加，pytest 覆盖改 payload 和改摘要/大小两种。）

**上限（默认值，均可用环境变量调整）：**

- 单快照 payload 4 MiB（`LOCAL_PROGRESS_MAX_PAYLOAD_BYTES`）；
- 单世界 5000 个快照（`LOCAL_PROGRESS_MAX_SNAPSHOTS`），graph 一次全量返回；
- 一个快照最多 64 个父（`LOCAL_PROGRESS_MAX_PARENTS`），正常线性推进只用 1 个；
- 幂等记录保留 30 天（`LOCAL_PROGRESS_IDEMPOTENCY_TTL_DAYS`）；
- token 是全局 Bearer（`LOCAL_PROGRESS_TOKEN`），不是每用户授权；世界 ID 由调用方生成；
- 没有压缩、加密、服务端 GC/备份；不做分页。

超过上限的请求会被拒绝并返回明确错误，不会截断后保存。

## 实现

### 服务端

- `backend/app/services/local_progress/store.py`
  - 独立 SQLite 文件，默认 `backend/data/local_progress.sqlite3`，环境变量
    `LOCAL_PROGRESS_DB` 可改；不迁移共享世界数据库。
  - 三张表：`progress_worlds`（活跃 head + revision）、
    `progress_snapshots`（父链 + 内容摘要 + 原始 payload JSON）、
    `progress_requests`（requestId 幂等响应）。
  - `contentDigest = sha256(canonical payload)`：内容身份只看 payload。
  - `snapshotId = snap_<sha256(worldId + contentDigest + 排序后的 parents)>`：
    一份保存文档的身份，绑定内容及其父链位置。同一 payload 在两条分支上是
    两个节点，不覆盖、不合并事实。
  - 父链、内容身份、revision 互相独立。revision 是服务端保存版本，每次
    实际写入（新增节点、切 head）加一；时间戳不参与覆盖判断。
  - 保存与当前 head 完全相同的 payload 是无操作，不新增节点、不加 revision。
  - 所有写事务 `BEGIN IMMEDIATE`，CAS 在事务内比较。
  - `activate:false` 只存分叉，不动 head；`select_head` 只移动 head，目标
    必须是分支叶子；另一份始终可读。
  - 同一 `requestId` 重试在 CAS 检查前命中幂等记录，返回原 snapshotId 和
    当前 head/revision；同 id 不同内容返回 409 `request_id_reused`。请求记录
    还保存这次 CAS 依据的 expectedHead/expectedRevision。
  - 拒绝父节点缺失、超过大小/节点数/父数上限的写入。
  - 只做 JSON 序列化、大小、标识符、父链和 CAS 检查，不 import world
    engine，不解析 `WorldState`。
- `backend/app/routers/local_progress.py`
  - 独立 `router`，prefix `/local-progress`，未改 `app/main.py`。
  - 可选 `LOCAL_PROGRESS_TOKEN` 全局 Bearer token；常量时间比较。
  - 409 返回 `{detail:{code,message,head,branches}}`，客户端可直接做选择。
- `backend/app/schemas/local_progress.py`：camelCase 请求/响应模型，payload
  类型为任意 JSON。
- `backend/app/services/local_progress/standalone.py`：可单独启动的 FastAPI
  app，已带 CORS。启动说明与协议见同目录 `README.md`。

接口：

```text
GET  /local-progress/health
GET  /local-progress/worlds/{worldId}/head
GET  /local-progress/worlds/{worldId}/graph
GET  /local-progress/worlds/{worldId}/snapshots/{snapshotId}
POST /local-progress/worlds/{worldId}/snapshots   # upload CAS / fork
POST /local-progress/worlds/{worldId}/head        # 显式选择分支
```

### 浏览器客户端

`frontend/src/lib/world-engine/local/progress-sync/` 导出：

```ts
ProgressSyncClient<P>
  head(worldId): Promise<HeadState>
  graph(worldId): Promise<GraphState>
  read(worldId, snapshotId): Promise<SnapshotEnvelope<P>>
  saveLocal(worldId, payload): Promise<boolean>       // 只写 06 的本地仓库
  loadLocal(worldId): Promise<P | null>
  save(worldId, payload, options?): Promise<SaveOutcome<P>>
      // 先本地保存；在线则 CAS 上传；断网/5xx 入队；409 返回 conflict。
      // 同一世界已有未同步保存时，新保存直接排在队尾，flush 时按序 rebase，
      // 不会让多条离线保存都拿同一个旧 head 去 CAS。
  uploadCAS(worldId, payload, options): Promise<UploadResult>
  fork(worldId, payload, options): Promise<UploadResult>
  selectBranch(worldId, snapshotId, options?): Promise<SelectHeadResult>
  pullLatest(worldId): Promise<PullResult<P>>         // 双设备恢复
  pullSnapshot(worldId, snapshotId): Promise<PullResult<P>>
  pending(): Promise<number>
  flush(): Promise<FlushOutcome<P>>
  dropQueued(requestId): Promise<boolean>
  resolveQueuedConflict(requestId, choice): Promise<ResolveResult<P>>
  resolveConflict(conflict, choice): Promise<ResolveResult<P>>
compareLineage(leftId, rightId, nodes): LineageComparison
MemoryQueueStore / createWebStorageQueueStore(key, storage)
```

`SaveOutcome` 是判别联合：`synced | local-only | queued | conflict`。
`resolveConflict` 的 `choice` 只有 `keep-remote` 和 `keep-local-fork`：
前者把远端 head 拉回本地；后者把本地 payload 作为旧基线的分叉存入，再
显式切到它，远端分支不删除。不会自动把两份游戏事实合并。

`compareLineage` 返回 `commonAncestor/sharedHistory/leftOnly/rightOnly/
diverged/leftIsAncestorOfRight/rightIsAncestorOfLeft`，所有路径按
祖先→叶排序，只看父链，不看时间戳。

## 存储/同步会不会覆盖正文历史（给 06 的排查结论）

刷新后条目从 2 变 0，先说历史存在哪：`LocalGameSnapshot` 里有三处。

- `snapshot.commands`：玩家提交过的输入，按顺序；
- `snapshot.transport.points`：已提交的点位（含 `trigger: 'player'`）；
- `snapshot.transport.narrations[pointId]`：每个点的正文和状态（`pending` → `ready`）。

页面 `restoredEntries()` 用后两处重建列表，再用 `commands[index]` 配输入。三处任何一处
缺失，历史就少。

同步这一侧做了什么，逐条列清楚：

| 调用 | 读/写 | 会不会改历史 |
|---|---|---|
| `sync.save(snapshot)`（默认） | 只读本地记录 + 上传 | 不会；不写 store |
| `sync.push(snapshot)` | 只上传 | 不会 |
| `sync.flush()` | 只读队列 + 上传 | 不会 |
| `sync.restore()`（默认） | 本地有就返回本地；本地没有才读远端 | 不会写 store；返回的快照交给会话打开 |
| `sync.status()` | 只读 | 不会 |
| `sync.choose(...)`（默认） | 服务端选分支 + 返回快照 | 不会写 store |
| `createProductSync({ writeLocal: true })` | 会写 store | 只有这一种会覆盖本地记录；产品不用它 |

拿 06 的真实存储实现跑过（`frontend/scripts/parallel-sync/session-owned-store-check.ts`，
内存后端，和 IndexedDB 同一套 `store.ts` 代码）。在 07 的 `frontend/` 下运行：

```bash
PROGRESS_SYNC_URL=http://127.0.0.1:8010 PROGRESS_SYNC_TOKEN=<token> \nLANE06_ROOT=../../06-recovery ./node_modules/.bin/jiti \n  ./scripts/parallel-sync/session-owned-store-check.ts
```

不带 `PROGRESS_SYNC_URL` 时只跑离线两种模式（也会复现旧行为和修复后的对比）：

- 会话先存一份带 2 条正文历史的快照（revision 1）；
- 页面回调按它的写法调 `sync.save(snapshot)`；
- 结果：revision 仍是 1，store 里 `commands` 3 条、`narrations` 3 条原样；会话下一次
  `expectedRevision: 1` 的保存成功；
- 同一个脚本的 `writeLocal: true` 分支仍能复现 04 撞到的 `progress_conflict`
  （revision 变 3，会话下一次保存冲突），说明这个检查确实测到了问题。

另外，真实服务上有往返测试（`real-server.test.ts`）：带 3 条命令、3 条 narration 和
checkpoint 的快照上传后读回，`toEqual` 完全一致。

所以按现有代码，**同步不会改正文历史**。2→0 最可能不是渲染丢字段，而是那一轮保存
根本没落盘：04 的证据里第一次提交就被 `progress_conflict` 拒了（`resultsCalls: 0`），
没有持久记录，刷新自然没有条目。双写已经在 `2b96e783` 从适配层默认值里去掉，06 升到
这个提交后，页面保存路径不用改代码；浏览器里队列和已知 head 现在默认用
`window.localStorage`（`storage: null` 才是只放内存），仍要补的是 `restore()`
和冲突选择。

### 用 06 自己的 session + store 走一遍“一回合 → 页面保存 → 刷新”（2026-11-10）

`frontend/scripts/parallel-sync/session-history-check.ts` 不经过页面，直接用 06 的
`LocalGameSession`、真实 `persistence/store.ts` 和一个按脚本回答每个任务的模型（和
06 自己的恢复测试同形），跑一回合后调用页面同样的 `sync.save(session.snapshot)`：

```
LANE06_ROOT=../../06-recovery ./node_modules/.bin/jiti ./scripts/parallel-sync/session-history-check.ts
```

实测（离线、无真实服务）：

- 提交后 revision 22；页面式 `save()` 之后仍是 22，`localSaved=false`，上传进入队列；
- 关闭旧标签页、用同一个 store 新开一个 session：`commandsPlayed` 仍是 `["我打开盒盖。"]`，
  1 个 player 点、1 条 `ready` 正文，正文与刷新前逐字相同，没有半结算的 work。

### 第三个 06 侧问题：失败回合之后的刷新会张冠李戴（2026-11-10）

`frontend/scripts/parallel-sync/failed-turn-history-mapping-repro.ts`，06 head `cef95c7e`：
第 1 回合成功、第 2 回合结算抛错后取消（该轮不产生点位）、第 3 回合成功。这时

- `commands` 有 3 条，已提交的 player 点位只有 2 个；
- 刷新后 `restoredEntries()` 按列表下标配对，得到：
  - 第一句 ↔ 第 1 回合正文（对）；
  - 第二句会失败 ↔ 第 3 回合正文（错，正文挪到了失败那句下面）；
  - 第三句 →  unfinished / 空（错，它其实提交了）。

页面内存里的列表是对的，只有刷新恢复错。原因是点位只带 `advanceId`，没有“哪条命令”
的标识，而 `commands` 又把没产出点位的命令也算进去。这会直接让 01 的 D1
（刷新前后每条输入和正文一致）失败，而且错得不容易看出来。已告诉 06：把命令标识
存到 advance/round/point 上，或者在无法配对时标成 undetermined，不要猜。

### 第二个会让页面卡住的 06 侧问题：失败的回合不会被收尾（2026-11-10）

`frontend/scripts/parallel-sync/failed-turn-advance-repro.ts`，06 head `c1027684`：

- 模型在 `results` 抛错，异常从 `submit()` 抛出；
- session 留下 `advance`（`intentStatus: 'pending'`，输入文字还在）、`work` 未结算、失败那句
  已进 `commands`；
- 页面 catch 写“本回合没有完成”，但因为 `commandsPlayed` 变了，不把输入还给玩家，也
  不调用 `start()`；
- 下一次提交被拒 `turn_in_progress`；手动 `start()` 却能把这一回合正常做完
  （2 个点、正文 ready）。

也就是说：页面说失败，session 其实还能完成；而且不重新打开页面就无法继续或重试。
和上面的“刷新后不规划”叠在一起，失败回合 + 刷新会让这个世界彻底走不动。已按同样格式
告诉 06；这属于 session/page，不是 07 修的。

### 十回合存储验收（2026-11-10）

`frontend/scripts/parallel-sync/ten-turn-sync-check.ts`，06 的真实 session + 真实服务：

- 前 5 回合在线保存，每回合 `localSaved=false`；
- 第 6、7 回合断网，两笔进入队列；
- 关闭再打开（等同刷新）：7 条命令和 revision 都还在；
- 重连 `flush()`：上传 2 笔、0 冲突、0 剩余，远端头正好带 7 条命令；
- 再打 3 回合：最终远端头正好带 10 条命令，session 从未被阻塞。

这说明“重连只上传后代、不覆盖、不双写”在十回合尺度上成立（存储层，不是页面、
不是模型正文）。

**同时发现一个不属于同步、但会卡住验收的问题**（已报 06/05）：只规划 1 个点位的
回合，刷新后下一条命令会被接受但永远不规划——模型根本没被再问一次
（`plannedAfterReopen=false`），`advance` 一直开着，之后每次提交都是
`turn_in_progress`。规划 2 个点位时同样流程正常，刷新前的 1 点位回合也正常，所以变量
在恢复出来的 round/memory 状态。复现脚本
`frontend/scripts/parallel-sync/refresh-next-turn-repro.ts`。验收计划里“第 6 回合后刷新”
正好会踩到它；页面没有 `await` 分支也没有恢复按钮。

**已定位到原因**（06 的代码，07 只报告不修）：回合结束后保存的快照里仍带着
`checkpoint: {roundId, plan, planIndex}`，而这时 plan 已经用完
（`planIndex === plan.length`）。`LocalGameSession.restore` 通过 `planUsable` 把它原样
恢复（该检查只核对已提交点是不是 plan 的前缀），于是 `memory.plan` 非空且
`planIndex >= plan.length`，调度器直接返回 `await/round_points_exhausted`，模型不再被
问一次。实验：同一份快照删掉 `checkpoint` 再 restore，下一条命令正常完成
（`stop/world_complete`，2 条命令）。建议 06 在 `currentCheckpoint()` 里，plan 用完且
没有未结算 work 时返回 null；`planUsable()` 也拒绝这种“已消耗的 plan”。

### 分叉：两台设备各走一步，重连冲突，玩家显式保留（2026-11-10）

`frontend/scripts/parallel-sync/fork-session-check.ts`，用 06 的真实 session 快照和真实服务：

1. A 打第 1 回合并上传；
2. B 恢复后打不同的第 2 回合并上传，激活头变成 B；
3. A 没看到 B，离线打自己的第 2 回合，重连 `flush()`：得到 1 个冲突、0 次上传，
   `status()` 为 `diverged`，冲突里列出 B 的分支；
4. 玩家选 `keep-local-fork`：A 的副本成为新头，B 的副本仍可读且内容和 B 的
   `commands` 一致，两份没有被合并或覆盖。

顺带修了一个会误导页面的行为：`status()` 原来只看“上次已知 head”和远端，离线存了
还没上传时也会报 `in-sync`/`remote-ahead`，页面就不会弹出选择。现在它把队列算进去，
同一 head 下有待传就是 `local-ahead`，远端也动了就是 `diverged`。这是只读判断，不写
任何存储，也不替玩家选。

### 两台设备、真实服务、06 的 session（2026-11-10）

`frontend/scripts/parallel-sync/two-device-session-check.ts`：A 用 06 的 session 打完一回合
上传到真实服务；B 没有任何本地存档，从远端恢复、写进自己的 store、用 `LocalGameSession.open`
打开（`created=false`），看到同一条输入和同一段正文；B 再打一回合，上传的父节点就是 A 的
快照。实测 B 的 `commandsPlayed` 为 `["我打开盒盖。"]`、正文逐字相同、父链包含 A。脚本还验证了
第二种打开方式（C）：不先写 store，直接 `LocalGameSession.restore(远端快照)`，历史一致，
上传挂在 B 的快照下；C 的 store 在 session 自己保存之前保持空（revision 为 null），
因为 `save()` 默认只上传。

```
PROGRESS_SYNC_URL=http://127.0.0.1:8010 PROGRESS_SYNC_TOKEN=secret LANE06_ROOT=../../06-recovery ./node_modules/.bin/jiti ./scripts/parallel-sync/two-device-session-check.ts
```

这是存储和分支关系的检查（模型是脚本），不是真实页面、不是模型正文、也不是质量通过。

这证明“存储/同步覆盖正文历史”在修好双写后不会发生；页面若仍少条目，问题在渲染或
恢复字段，不在同步。不是产品质量结论。

`__worldRestore` 的四个字段按什么算才算“真恢复”（06 当前实现里 `stateRestored`
只表示“打开了一条记录”，`entriesTotal` 用的是 `commands.length`，两处都容易把失败
显示成成功或反过来）：

| 字段 | 应为 | 说明 |
|---|---|---|
| `stateRestored` | 打开的是已有记录，且 `session.state()` 的摘要等于 head 点位记录的摘要 | 摘要不一致就是状态没真恢复，不能只看“有记录” |
| `entriesRestored` | `transport.points` 里 `trigger === 'player'`、且 `narrations[id].status === 'ready'` 且正文非空的点数 | 正文历史；程序降级正文也算，但要保留来源标记 |
| `entriesTotal` | 已提交的 player 点数 | 不是 `commands.length`：被取消/失败的输入没有点位，用 commands 做分母会让“恢复完整”永远不成立 |
| `inputConsumptionRestored` | 没有半结算的点（`transport.work == null` 或 work 的轮次等于当前轮）且 `advance.intentStatus !== 'pending'` | 只判 `intentStatus` 不够，半结算也会重复消费输入/骰点 |
| `overallRestored` | 以上三项都成立，且 `entriesRestored === entriesTotal` | 任一不成立就是没恢复，不能改布尔值让它消失 |

如果升级后刷新仍少条目，按顺序查这三处（都在 06 的代码里）：

1. `snapshot.transport.points` 里已提交点的 `trigger` 是不是 `'player'`（自动回合会被
   `restoredEntries` 过滤掉，而 `commands` 仍计入，索引会错位）；
2. `narrations[pointId].status` 是不是 `'ready'`（`'accepted'`、`'pending'` 都会显示成
   “正文没有保存成功”，但不是 0 条）；
3. 会话那次保存是否真的成功（`metadata.revision` 有没有递增），以及 `commands` 与
   player 点的数量是否一一对应。

## 接线

### 给 06：产品接入（2026-11-10 组织调整后）

06 的集成树里已有一份**旧版** `local/progress-sync/`（除换行外与旧提交相同），
已合入 `b4c9ea5b`。本线之后又加了只读 `status()`、`flush().conflictList`、
`peekHead/peekGraph`、`policy.avoidText`（成文侧）和 `product-wiring.test.ts`，
最新提交是 `267646de`（含 04 在真实页面撞到的双写修复），其后是真实服务回归测试。

06 在 `d293b3e2` 的接线是 `createProductSync({store, worldId, baseUrl})` +
开局 `flush()` + 保存时 `sync.save(snapshot)`。**双写问题已在适配层默认值里修掉**
（`267646de`）：`save()` 现在默认只上传，不写 06 的存储；所以 06 升到这个提交后，
保存路径不需要改代码，会话仍然是唯一写入者。`writeLocal: true` 只给没有会话
写入者的调用方用。

这套接线仍**缺三样东西**，测试固定了前两样的后果（`product-wiring.test.ts`）：

1. ~~没有传 `storage`~~：已从适配层补上默认值——浏览器里自动用
   `window.localStorage`，`storage: null` 才表示只放内存。显式传仍然更清楚，但不再是
   页面必须做的事。
2. **没有开局 `restore()`**：B 设备没有本地存档时不会去拉远端 head，因此
   “换设备继续”不成立。
3. **没有冲突选择界面**：保存冲突时页面只显示一句提示，玩家看不到两个副本，
   也没有调用 `choose()`。

产品接线只需要一个对象和四个调用点，不需要页面自己拼协议：

```ts
import { createProductSync } from '@/lib/world-engine/local/progress-sync';

const sync = createProductSync<LocalGameSnapshot>({
  store: progressStore,          // 06 的 LocalProgressStore（结构类型，无需改它）
  worldId,
  baseUrl: process.env.NEXT_PUBLIC_PROGRESS_URL ?? '',   // 空 = 只存本地
  token,                         // 可选
  storage: window.localStorage,  // 离线队列 + 上次已知远端 head
});
```

1. **每次 06 自己把进度写进 IndexedDB 之后**调 `sync.push(snapshot)`（或保持现有
   `sync.save(snapshot)`，默认行为一样：只上传）。**会话是唯一写入者**：06 的
   store 用 revision 校验，适配层再写一次会把 revision 推到会话后面，会话下一次
   保存就抛 `progress_conflict`，第一次玩家提交在被调模型前就被拒（04 的真实页面
   就是这样撞到的）。返回 `synced | queued | conflict`；`queued` 表示重连后
   `flush` 会补传。
2. **开局恢复**：先读 06 的本地记录；本地没有才 `await sync.restore()`。
   默认**不写** 06 的存储，只把远端快照返回给页面/会话来打开（`source:
   'remote'`）。`source` 有四种：`local` / `remote` / `none`（服务答了但没有
   head，确实是新世界）/ `unavailable`（联系不上或读不到，**不能**当成“远端是
   空的”去开新世界）。`restore().conflict` 出现时不要自动选，把两份分支交给玩家。
3. **冲突 UI**：`conflict.branches` 是两条叶子，`conflict.remote` 是远端 head。
   玩家点选后调 `sync.choose('keep-remote' | 'keep-local-fork', conflict)`；
   返回值里的 `snapshot` 由页面交给会话打开（默认不写存储）。两个副本都留在
   服务端，之后仍可用 `sync.read(snapshotId)` 读回。
4. **重连/页面回到前台**：`await sync.flush()`。同一次离线期间的多次保存会按
   顺序作为**后代链**上传（父节点指向前一条上传），不会并发拿同一个旧 head。
   第二次 flush 幂等，不新增快照。`flush().conflictList` 里是真正的冲突对象，
   页面要拿它让玩家选择，不能只看 `conflicts` 计数。
5. **保存冲突时**：`sync.save()`/`sync.flush()` 的 `conflictList` 里是完整冲突
   对象；用 `sync.read(branchId)` 读出两份正文给玩家看，玩家选择后才
   `sync.choose(...)`。这一步现在是缺的。
6. **判断要不要提示玩家**：`await sync.status()` 只读，返回
   `in-sync | remote-ahead | local-ahead | diverged | local-only | unknown`，
   另带 `remote`、`baseSnapshotId`、`branches`。它不会因为读了一次 head 就把
   自己当成已同步；`remote-ahead` 时页面应提示“另一台设备有新进度”，
   `diverged` 时提示选择，不要自动覆盖。

### 刷新后卡死的补丁（已验证，交 06 采用）

`design/parallel-handoff/07-fix-checkpoint-for-06.patch`，改 06 的三个地方：

1. `resume.ts planUsable()`：没有未结算 work 时，拒绝“已消耗完”的 checkpoint（
   `planIndex >= plan.length`）；
2. `resume.ts rebuildSessionMemory()`：round 已经 concluded 时，不恢复也不合成 plan，
   留给下一次命令让模型重新规划；
3. `session.ts currentCheckpoint()`：不持久化已经用完的 plan；
4. 加一条 `session-recovery.test.ts` 回归测试：模拟旧存档里的已消耗 checkpoint，刷新后
   下一条命令必须真正提交（没有修复时只提交 1 个点，测试失败）。

在 06 `3073e2f3` 的干净克隆上验证：补丁干净应用、`tsc` 0 错误、session/controller
59 passed；再把同步补丁一起打上 102 passed；`refresh-next-turn-repro.ts` 用
`EXPECT_OK=1` 跑出 NO STALL。这是 06/05 的代码，补丁只是提议，06 仍是 owner。

### 合并到 06 的树：在临时克隆里验证过（2026-11-10）

在 `.tmp/06-merge-check` 里 `git clone --shared` 了 06 的 `cef95c7e`，打上
`design/parallel-handoff/07-sync-for-06.patch`（`84d932cf..c4510286`，897 行）：

- `git apply` 干净；
- 06 自己的 `tsc -p tsconfig.json --noEmit`：0 错误；
- 带真实服务跑 progress-sync：43 passed；
- 跑他们整个前端测试：1147 passed、4 failed，失败全在 `src/app/styles.test.ts`，
  在**未打补丁**的同一提交上用 `git stash` 复跑得到同样的 4 个失败，所以是既有问题，
  不是这次合并带来的。

也就是说 06 只需要应用这一个补丁，不需要改页面，就能解除 `progress_conflict`；
`restore()`/`choose()` 的接线是另一件事。临时克隆在 `.tmp`，没有写 06 的工作树。

### 09 排页面之前先跑这个只读检查

`frontend/scripts/parallel-sync/page-wiring-audit.ts` 读 06 的 `page.tsx`（不写），逐条打印
接线前提和命中行号，四条必需项缺一条就退出码 1：

```
LANE06_ROOT=../../06-recovery ./node_modules/.bin/jiti ./scripts/parallel-sync/page-wiring-audit.ts
```

2026-11-10 的实测：`createProductSync` 在 `page.tsx:525`；`storage`、`restore`、`choose`
都还没有，结论 NOT READY。`avoidText` 只作提示，不拦页面——产品正文走 02 的模型，07 的
composer 只在降级时用它。等 06 接线后这里应变成 READY，再用 09 的浏览器证据。

### 给 06 的最小改动清单（页面不动归属，只贴做法）

现在 `page.tsx` 里的这一段：

```ts
const sync = createProductSync<LocalGameSnapshot>({ store, worldId: world.worldId, baseUrl: syncBase });
syncRef.current = sync;
void sync.flush().then(...)
```

需要补成下面四步（`storage` 是必须的，其余三步决定产品行为）：

```ts
const sync = createProductSync<LocalGameSnapshot>({
  store,
  worldId: world.worldId,
  baseUrl: syncBase,
  storage: window.localStorage,        // 离线队列 + 上次已知 head
});
syncRef.current = sync;

// 1) 没有本地存档时，先拉远端 head；有本地存档时不覆盖本地
const restored = await sync.restore();
if (restored.source === 'remote' && restored.snapshot) {
  // restore() 只读，不写 06 的 store。两种打开方式，选一种：
  // a) 先落一次基线（此时还没有 session，不存在双写），再 open
  await store.save(world.worldId, restored.snapshot);
  session = (await LocalGameSession.open(store, { worldId: world.worldId, initial },
    model, { sessionId, storage: store })).session;
  // b) 或者直接 LocalGameSession.restore(restored.snapshot, model, { storage: store });
  //    它读不到本地记录时 revision 记 0，之后第一次保存就是 revision 1。
  // 不要调用不存在的 openSnapshot()；也不要用 sync 去写 store。
}
if (restored.conflict) showConflict(restored.conflict); // 两份都读出来给玩家

// 2) 开局与重连都 flush（幂等）
const flushed = await sync.flush();
if (flushed.conflictList.length) showConflict(flushed.conflictList[0]);

// 3) 提示“另一台设备更新了”
const status = await sync.status();
if (status.relation === 'remote-ahead') setSyncLabel('另一台设备有更新的进度：刷新可载入');

// 4) 玩家点选后
await sync.choose('keep-remote', conflict);
```

`product-wiring.test.ts` 已经把“少传 storage”的后果固定成测试：断网保存后刷新，
队列为空、base 为 null，这一笔传不上去，重连时还会把已有世界当新世界。

服务端两种跑法，二选一：

- 嵌进现有后端：`app.include_router(local_progress_router)`（单独前缀
  `/local-progress`，与游戏路由无关）；
- 独立进程：`cd backend && python -m uvicorn
  app.services.local_progress.standalone:app --port 8010`，页面 baseUrl 指到
  `http://127.0.0.1:8010`，CORS 用 `LOCAL_PROGRESS_CORS_ORIGINS` 配置。

服务端**只**存 JSON、内容摘要、父链、requestId 幂等记录和 head/revision。
它不 import world engine、不校验 `WorldState`、不掷骰、不调模型。

### 早期接线说明（仍适用，但 `createProductSync` 已封装）


主 agent / 集成方需要做的只有：

1. 在 `backend/app/main.py` 增加：
   ```python
   from app.routers.local_progress import router as local_progress_router
   app.include_router(local_progress_router)
   ```
   或者单独运行 `python -m uvicorn app.services.local_progress.standalone:app --port 8010`。
2. 06 的本地仓库实现两个方法并注入：
   ```ts
   const localStore: LocalSnapshotStore<LocalGameSnapshot> = {
     load: (worldId) => repository.load(worldId),
     save: (worldId, snapshot) => repository.save(worldId, snapshot),
   };
   const sync = new ProgressSyncClient({ baseUrl, token, localStore, queueStore });
   ```
3. 每次本地进度落盘后调用 `sync.save(worldId, snapshot)`；`conflict` 时
   由页面让玩家选择 `sync.resolveConflict(conflict, 'keep-remote' | 'keep-local-fork')`；
   启动/恢复时调用 `sync.pullLatest(worldId)`；恢复网络后 `sync.flush()`。
   页面、session、全局路由不由本线修改。

## 验证

只跑本线相关，不重跑历史全基线。

```bash
cd backend
python -X utf8 -m pytest -q tests/test_local_progress_sync.py
# 14 passed：CAS 失败、幂等重放、祖先不能覆盖、离线分叉、分支选择、
# 双设备恢复、重启恢复、父链/大小/token/不透明 payload、同内容不同分支位置。

cd frontend
./node_modules/.bin/tsc -p tsconfig.world-contract.json --noEmit
./node_modules/.bin/vitest run src/lib/world-engine/local/progress-sync/ --maxWorkers=1
# 30 passed（无服务时 real-server 两个文件 skip）：客户端 CAS、离线队列/多离线
# 保存链、丢响应幂等、分叉/选择、双设备、队列冲突两种显式选择及依赖 rebase、
# web storage 队列、lineage 比较、product 适配器、push 不重复写本地、head 恢复。
PROGRESS_SYNC_URL=http://127.0.0.1:8010 PROGRESS_SYNC_TOKEN=secret   ./node_modules/.bin/vitest run src/lib/world-engine/local/progress-sync/ --maxWorkers=1
# 33 passed：再加真实 HTTP 的两个客户端 save→冲突→fork→选择→恢复，
# 以及离线两次保存→重连只上传后代链→第二次 flush 幂等→另一设备取回。

./node_modules/.bin/eslint src/lib/world-engine/local/progress-sync scripts/parallel-sync
# 0 errors
```

真实服务验证（2026-11-10 复跑，真实 HTTP、临时 SQLite）：

```bash
cd backend
LOCAL_PROGRESS_DB=<temp>/progress.sqlite3 LOCAL_PROGRESS_TOKEN=smoke-token \
  python -m uvicorn app.services.local_progress.standalone:app --port 18081
# 另一终端：
PROGRESS_SYNC_URL=http://127.0.0.1:18081 PROGRESS_SYNC_TOKEN=smoke-token \
  node frontend/scripts/parallel-sync/two-device-smoke.mjs
# 输出 root / 幂等重放 / 409 / A 分支 / B 分叉 / 两叶可读 / 切 B。

PROGRESS_SYNC_URL=http://127.0.0.1:18081 PROGRESS_SYNC_TOKEN=smoke-token \
  ./frontend/node_modules/.bin/vitest run \
  src/lib/world-engine/local/progress-sync/real-server.test.ts \
  src/lib/world-engine/local/progress-sync/reconnect-chain.test.ts --maxWorkers=1
# 3 passed：真实 HTTP 下两个客户端 save→pull→CAS 冲突→fork→选择→恢复，
# 以及离线链上传与分叉保留两副本。
```

### 给 06：页面补丁（2026-11-10，已验证，未写 06 的树）

`design/parallel-handoff/07-page-restore-for-06.patch` 在 06 `81d5507a` 上、
叠在同步补丁和 checkpoint 补丁之后应用：

1. 本机没有存档时才向进度服务要远端 head；`restore()` 返回
   `unavailable`（heads 读不到/断网）时显示重试提示，**不建新世界**；
2. 远端有存档时用 `LocalGameSession.restore(remote.snapshot, model, { storage: store })`
   打开，本地记录由会话自己的写入者保存；
3. `push()` 报冲突时保留冲突对象，页面显示“保留这一台 / 改用另一台”两个按钮；
   “改用另一台”会关掉当前会话、把选中的快照写进本地记录并刷新，
   “保留这一台”调用 `choose('keep-local-fork')` 把本机副本设为同步主线。
   两份副本在服务端都保留，页面不自动挑。

验证：干净克隆 `81d5507a` 上三个补丁一起 `git apply` 干净，`tsc` 0 错误，
本地引擎测试 489 passed | 1 skipped，`scripts/parallel-sync/page-wiring-audit.ts`
对打补丁后的页面返回 **READY**（同步调用、开局恢复、显式选择三项 required 全过）。
这是提给 06 的补丁，没有写入 06 工作树；真实页面还要 09 在 06 合入后跑。

## 限制

- 未修改页面、`session.ts`、`app/main.py` 或共享数据库；页面接入需要按上面
  的接线步骤完成，06 负责。本线没有在真实 `/world-local` 页面上跑过同步，
  双设备/断网/刷新的真实页面证据要由 09 在 06 接线后采集；请求已放在
  `results/product/browser-requests/07-sync-double-device-01.json`。
- `status()` 的 `localRevision` 目前恒为 null：远程 revision 与 06 本地记录
  revision 是两套编号，不混用；页面要显示本地版本时读 06 自己的 metadata。
- 未做真实模型/GPU 运行；本线不涉及推理，相关能力未验证。页面用 stub loader
  跑的成文证据只是程序路径，不能当作模型正文或产品质量通过。
- token 是全局 Bearer，不是每用户授权；世界 ID 由调用方生成。
- graph 一次返回一个世界全部节点，默认上限 5000；未做分页。
- 队列默认内存；提供 `createWebStorageQueueStore`，页面可选择用
  `localStorage` 持久化。队列存储失败时保留内存队列并暴露
  `queuePersistenceError`，不阻塞本地保存。
- 队列冲突不会自动丢弃或自动合并，必须由玩家显式选择；这是产品约束。
- 同一世界的多条离线保存会按顺序排队并在 flush 时 rebase；如果玩家对前一条
  选择 `keep-remote` 丢弃了本地基线，后续依赖它的保存不会自动合并到远端，
  会以 `dependency_missing` 留在队列，需另行选择或 `dropQueued`。
- 没有压缩、加密、服务端 GC/备份；幂等记录按 30 天惰性清理。
