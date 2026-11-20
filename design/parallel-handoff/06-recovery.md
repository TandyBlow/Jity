# 06-recovery 交接：本地持久化、处理中恢复、多标签互斥

分支 `goal/local-06-recovery`，基线 `865ae64e0901a70c3db4f1d0eb2af60268943c53`。

## 1. 原来的问题（用一次刷新走一遍）

旧页面把 `LocalGameSnapshot` 整体 `JSON.stringify` 写进 localStorage，而且写了这一句：

```ts
if (snapshot.transport.work) return; // never persist a half-settled point
```

一次行动里浏览器要做二十来次写入：冻结行动、建点、发现组、锁目标、掷骰、准入、暂存候选、封点、提交点、写正文。`work != null` 覆盖了「建点之后、提交之前」的整段。于是：

1. 玩家输入「我打开盒盖」，页面先跳过保存，因为此时 `work` 已经有了。
2. 模型正在写结算或正文时玩家刷新。
3. 浏览器只留着一个阶段：上一次完整结算后的存档（`work` 为 null 的那次）。
4. 恢复后 `advance` 和 `work` 都不在了，玩家看到的正文退回上一轮，刚才的行动、已经掷出的骰、已经冻结的 NPC 行动全部消失；玩家再按一次行动，等于重开一局。

另外 localStorage 只有一个槽位、没有并发控制：两个标签页各跑一个会话，最后写入的那个静默覆盖另一个；写入配额失败时只有一句 `console.warn`，页面以为存住了。

## 2. 现在的机制（同一次刷新走一遍）

每个成功的 transport 写入之后、控制器的 `execute()` 返回之前，会话把整条记录写进 IndexedDB，并把这次写入的序号（revision）交给存储层做比较后写入（compare-and-set）：

1. 玩家输入「我打开盒盖」→ `submit()` 先把这份快照和新的行动日志存一次（revision 1）。
2. `checkpoint_start_advance` 成功 → 存（revision 2）——玩家的行动原文、advanceId、inputId 已经是磁盘事实。
3. `checkpoint_begin_point` 成功 → 存（revision 3）——工作点、时间推进、轮次游标已经是磁盘事实。
4. 主角行动冻结 → 存；目标锁定 → 存；**掷骰 → 存**（骰子结果和 `rollId` 进了 `rolls`）；准入 → 存；暂存候选 → 存。
5. 模型正在写正文时玩家刷新。
6. 新页面打开 IndexedDB，读到 revision 20 左右的记录：`work` 还在、上面那个 `pendingGroup` 关闭了、骰子有 `rollId`/`result`。
7. 会话用记录本身重建控制器记忆（冻结行动、骰点、已暂存单元、工作游标），只把模型没产出过的东西重新问一次：结算结果文本、状态变化、正文。**不会再问一次行动、不会再掷一次骰**；`commit_point` 只会提交一次（点号、版本号都从记录里读）。

因此「刷新会退回上一次完整结算」和「刷新后重跑已冻结的行动/骰点」这两个问题都关掉了。

## 3. 导出 API

### 3.1 存储仓库 `src/lib/world-engine/local/persistence/`

```ts
openLocalProgressStore(options?: OpenLocalProgressOptions): Promise<LocalProgressStore>
createLocalProgressStore(backend: ProgressBackend, options?: { now?: () => number }): LocalProgressStore
```

`LocalProgressStore`：

| 方法 | 说明 |
| --- | --- |
| `save(worldId, snapshot, options?)` | 写入 `LocalGameSnapshot`；`options.expectedRevision` 是乐观锁（0 = 该世界必须还不存在），`options.requireLease` + `options.sessionId` 要求写入方持有写锁，`options.digest` 顺带算整份快照的 canonical 摘要。返回 `ProgressMetadata`。 |
| `load(worldId)` | `{ metadata, snapshot } \| null` |
| `list()` | 所有世界的 `ProgressMetadata`（按保存时间倒序） |
| `delete(worldId, { sessionId, force })` | 默认拒绝删除别的标签页仍持锁的世界 |
| `close()` | 关闭数据库连接（不删数据） |
| `claimLease(worldId, holderId, ttlMs?)` | 抢/续写锁；被别的活锁占着返回 `{ acquired: false, holderId, expiresAtEpochMilli }` |
| `renewLease(worldId, holderId, ttlMs?)` | 续期（同 `claimLease`） |
| `takeoverLease(worldId, holderId, ttlMs?)` | 显式接管：即使对方还活着也把锁代次 +1 |
| `releaseLease(worldId, holderId)` | 只释放自己的锁 |
| `readLease(worldId)` | 读当前锁 |
| `backupLegacy(backup)` / `loadLegacyBackup(key)` | 旧档原文备份（只读回，不参与游戏） |

`store.kind` 是 `'indexeddb' | 'memory'`，`store.durable` 说明这次到底存没存进磁盘。`openLocalProgressStore({ backend: 'auto' })` 在没有 IndexedDB 的平台上退化成内存实现并如实把 `durable` 报成 `false`，不假装存住了。

`ProgressMetadata`（每次 save 新生成，不可变；07 可直接消费，**不是**第二套游戏事实）：

```ts
{ schemaVersion: 1, worldId, revision, savedAtEpochMilli, writerId,
  headPointId, version, checkpointRevision, phase, paused,
  hasWork, workPointId, workPhase, roundId, advanceId,
  narrationStatus, commands, stateDigest, snapshotDigest: string | null }
```

`ProgressConflictError` / `SessionLeaseHeldError` / `SessionLeaseLostError` / `SessionDeleteBlockedError` 都是可判别的类，页面据此提示。

### 3.2 旧存档迁移 `persistence/legacy.ts`

```ts
migrateLegacySnapshot(store, { storage?, sourceKey?, removeSource?, localStorageBackup?, now? })
  : Promise<{ status: 'migrated'|'absent'|'corrupt'|'already_saved'|'save_failed'|'unsupported', ... }>
```

- 先把 localStorage 原文整段备份进存储层（`legacy:<key>:<epoch>`），再解析。
- 解析失败 → `corrupt`，**原件不动、不删**，备份保留。
- 存储里已有该世界 → `already_saved`，同样不删原件。
- 只有显式 `removeSource: true` 才删 localStorage 原键。

### 3.3 会话 `local/session.ts`

`LocalGameSession.create / restore / restoreFromStore / open / start / submit / pause / resume / cancel / state` 全部保留旧签名，新增可选参数：

```ts
interface LocalGameOptions {
  storage?: LocalProgressStore;      // 传了才自动落盘
  sessionId?: string;                // 写锁身份（默认随机，每标签页一个）
  leaseTtlMs?: number;               // 写锁有效期（默认 30s）
  leaseHeartbeat?: boolean;          // 后台续期（默认开）
  autoSave?: boolean;                // 每次 transport 写入后落盘（默认开）
  requireLease?: boolean;            // 写入必须持锁（默认开）
  onEvent?: (event: LocalSessionEvent) => void;
  onPersist?: ...                    // 旧回调，保持
}
```

新增只读视图：

```ts
session.snapshot        // LocalGameSnapshot（含 checkpoint：本轮的模型点位计划）
session.progress        // 最近一次成功的 ProgressMetadata
session.persistence     // { state: 'off'|'saving'|'saved'|'error'|'conflict'|'lease_lost', revision, metadata, blocked }
session.commandsPlayed  // 已提交行动
session.flushPersistence(): Promise<void>
session.close(): Promise<void>   // 停心跳、flush、释放写锁
```

`onEvent` 事件：`{type:'checkpoint', metadata}`、`{type:'save_failed', error}`、`{type:'conflict', error, metadata}`、`{type:'lease_lost', error}`。

行为约束（已被测试固定）：

- 轮次进行中再 `submit()` → `{ kind:'stop', reason:'turn_in_progress' }`，行动日志不加第二条。
- 暂停中 `submit()` → `{ kind:'stop', reason:'paused' }`。
- 失去写锁后 `submit()` → `{ kind:'stop', reason:'progress_lease_lost' }`；进行中的轮次在下一个写入边界停下，不再算完一个没人会读的回合。
- `cancel(reason)` 在轮次进行中会真的把 `round_conclusion_cancel` 发到运行中的控制器，并且**丢弃**取消后回来的模型输出；轮次结束后 `advance` 为空、`round.conclusion.closedBy='cancel'`，下一轮可以正常开始。
- `cancel()` 在没有进行中的轮次时返回 `{ kind:'stop', reason:'nothing_to_cancel' }`，不会留下一个以后才触发的取消命令。
- 保存失败（配额等）不停游戏：记 `save_failed`，把最新快照留在待写队列，下一次写入/`flushPersistence()` 再试。
- 版本冲突（另一个标签页已经写了更高 revision）或写锁被接管：进入 `conflict` / `lease_lost`，停止写入，不再猜谁该赢。

## 4. 处理中的快照什么时候安全

| 时刻 | 磁盘上有什么 | 刷新后 |
| --- | --- | --- |
| 输入提交后、start_advance 前 | 行动原文 + 旧记录 | 行动还没开始，可重新驱动 |
| start_advance 之后 | `advance`（原文、advanceId、inputId、intentStatus）+ 轮次 | 行动文本不会再被问，也不会重复开 advance |
| begin_point 之后 | `work`（点位、时间、baseline、游标） | 从同一工作点继续 |
| 发现组/锁目标/准入之后 | `pendingGroup`（成员、冻结行动文本、目标规格） | 冻结行动不重问，已准入目标不重掷 |
| 掷骰之后 | `rolls`（`rollId`、`result`、`eligible`、`admitted`） | 同一 roll 重放，不重掷 |
| 暂存候选之后 | `work.units`（候选 + 结果文本） | 不再问结果/变化 |
| 封点之后 | `sealed=true`、`prefixDigest` | 直接预览 + `commit_point` |
| 提交点之后 | 新 head、`pointStates`、narration pending | 只补正文 |

即：任何一次成功写入之后都可以安全刷新；模型在跑、还没写回的那一步会重新生成（这是唯一会重复的模型调用，且它本来就还没成为事实）。

## 5. 恢复怎么接回 controller

`persistence/resume.ts`

```ts
rebuildSessionMemory({ record, context, memory, checkpoint? })
  : { memory, notes, groupSlots, resumeAllocationKey }
```

- 从记录读：lease token、行动原文、`roundChanges`、已提交点、`work.units`、`work.timeScan`、`pendingGroup`、`rolls`。
- 组内来源栈按「谁被哪次准入拉进组」从 `rolls` 回溯重建，已完成的帧直接退栈，不猜顺序。
- 未完成的组身份槽（还没行动的角色）在恢复时用 `allocate_ids` 一次性补齐并**立刻落盘**，所以连续刷新两次不会拿到两套身份。
- 本轮点位计划无法从记录推出（只有模型知道下一个点怎么切），所以快照里多存一个 `checkpoint: { roundId, plan, planIndex }`。恢复时逐条核对：已提交点必须是计划的前缀、在途工作点必须与计划下一项的点号/类型/时间一致；不一致就丢掉这个提示，按记录重建（在途点用记录本身、点已提交则按剩余角色补一个点），绝不拿过期计划去开新点。
- 恢复后控制器记忆里的 `workingState`、`lastResults`、`updatesCalls` 是空的——这些正是模型还没产出/尚未确认的部分，调度器会按原顺序重新问模型；已确认的部分不重问。

## 6. 调用示例（主 agent 接线用）

```ts
// 页面加载：一个标签页一个会话、一个写锁
const store = await openLocalProgressStore();            // 浏览器里 kind === 'indexeddb'
if (!store.durable) showWarning('当前浏览器不支持 IndexedDB，本次进度只在内存里');

const migration = await migrateLegacySnapshot(store);     // 一次性迁移旧 localStorage 存档
if (migration.status === 'corrupt') showWarning(`旧的本地存档无法解析，已保留原件与备份（${migration.backupKey}）`);

const model = new LocalGameModel(semantic, { narrationEngine: narration, ... });
let session: LocalGameSession;
try {
  ({ session } = await LocalGameSession.open(store, world, model, {
    sessionId: crypto.randomUUID(),        // 本标签页身份
    onEvent: (event) => {
      if (event.type === 'lease_lost') setWarning('另一标签页已接管这份存档，本页停止写入。');
      if (event.type === 'conflict') setWarning('存档已被另一标签页更新，请刷新。');
      if (event.type === 'save_failed') setWarning('本地存档暂时写入失败，会继续重试。');
    },
  }));
} catch (error) {
  if (error instanceof SessionLeaseHeldError) {
    // 另一标签页正在玩：给两个按钮
    //  1) 「刷新页面」——等它空闲
    //  2) 「在本页接管」——await store.takeoverLease(session.worldId, myId); 然后重新 open()
  } else throw error;
}

await session.start();                                 // 恢复：接着上次没写完的轮次
document.addEventListener('visibilitychange', () => { if (document.hidden) void session.flushPersistence(); });
window.addEventListener('pagehide', () => { void session.close(); });   // 释放写锁

// 行动 / 暂停 / 继续 / 取消
const status = await session.submit(text);             // turn_in_progress：按钮已经禁用了，说明有并发提交
await session.pause();                                  // 按钮「暂停」
await session.resume();                                 // 按钮「继续」
await session.cancel('player_abort');                   // 按钮「取消这次行动」——真的会停

// 存档面板
const { revision, metadata } = session.persistence;
```

页面侧要改的就是这些：把 `SAVE_KEY` 的 localStorage 读写换成 `openLocalProgressStore()` + `LocalGameSession.open()`，加一个「本页接管」入口，加暂停/继续/取消三个按钮，加 `visibilitychange`/`pagehide` 的 flush 与 close。

## 7. 验证

CPU（假模型、内存后端，`--maxWorkers=1`）：

```bash
cd frontend
npx vitest run src/lib/world-engine/local --maxWorkers=1
# 2 files, 17 tests
```

覆盖：写失败后继续玩并在下一次写入补存、中途刷新恢复（冻结行动/骰子不重跑）、模型输入丢失后从在途工作点续跑（恢复时的身份分配会落盘，连续刷新两次不冲突）、在「点已提交、轮次还没结论」的边界刷新后把本轮跑完、重复提交、取消丢弃在途模型输出且下一轮可正常开始、暂停→刷新→恢复暂停→继续同一份冻结工作、多标签夺锁（TTL 到期与显式接管两条路）、旧的 localStorage 存档迁移与损坏原件保留、规划器重复点名已提交点时的停转保护。

真实浏览器 + 真实 IndexedDB（不需要模型权重，系统 Edge）：

```bash
cd frontend
node scripts/parallel-persistence/run-indexeddb-check.mjs \
  --out D:/others/Jity/.local/parallel-local-game/results/06-recovery/indexeddb-evidence.json
# 38 steps, all pass; evidence: results/06-recovery/indexeddb-evidence.json
```

脚本用 rolldown 把 `scripts/parallel-persistence/browser-entry.ts` 打成单文件，Playwright 拦截 `https://local.test/` 在本机返回它（不需要 dev server、不碰 http 接口），两个真实标签页共用一个 IndexedDB：

- `store.kind=indexeddb`、metadata 字段（含 `stateDigest`、`snapshotDigest`）；
- 一次完整行动后记录里有 1 个 roll、version=1、行动日志正确；
- 模拟刷新（抛错）后记录 `hasWork=true`、冻结行动文本在、roll 在；新标签页等写锁 TTL 到期后接管，恢复并跑完，version 仍是 1、`rollId`/`result` 与刷新前一致、没再问行动/目标；
- 两个标签页：活锁时抢锁被拒；显式接管后代次 +1、旧标签页下一次保存被拒且磁盘 revision 不动、旧标签页拒绝开新轮；新标签页写入成功；
- 点已提交、轮次还没结论时刷新 → 恢复后补完结论与正文，点不会被提交两次；
- 暂停中……刷新……仍是暂停……继续后同一 roll 完成；
- 取消：在途模型输出被丢弃、`advance/work` 为空、`round.conclusion.closedBy='cancel'`，下一轮成功；
- 重复提交被拒且日志只有一条；
- localStorage 旧档迁移成功、原键保留、备份原文一致；损坏档不迁移、原件保留；
- `list` 与 `delete`（删除后记录消失，其余世界不动）。

类型与静态检查：`npx tsc -p tsconfig.world-contract.json`、`npx tsc --noEmit -p tsconfig.json`、`npx eslint`（本线文件 0 error；`local/transport.ts` 里 3 个 `no-explicit-any` 是基线原有，未改该文件）。

## 8. 限制

- 页面 `world-local/page.tsx` 未改（归主 agent）：在接线完成前，页面仍然用 localStorage 单槽存档，本节能力不会自动生效；旧存档在接线后用 `migrateLegacySnapshot` 一次性搬过来。
- 只测了 Edge（Playwright `channel: 'msedge'`，Chromium 内核）。Firefox/Safari 的 IndexedDB 事务行为未在本机验证。
- `transport.ts`（05 线）未改，也不需要新 hook：落盘挂在会话持有的 `WorldTransport` 包装上，`LocalWorldTransport` 的 `onPersist` 回调原样复用。
- 每次成功写入都存一次整份快照（一轮约 20 次、单份百 KB 级），能换来「任何写回都可安全刷新」。真机上如果测出卡顿，可以在 `CheckpointingTransport` 里按操作类型收窄，但不要退回「有 work 就不存」。
- 控制器对「同一请求被服务端反复拒绝」没有次数上限；本线在会话层加了 20 步无写入即 `stalled:<operation>` 的保护，没有改控制器语义（归公共模块）。
- 真实模型/GPU 链路未在本线跑（这些检查用脚本化模型端口）；真实模型的端到端验收按 root 安排。
- `commandsPlayed` 是「已提交行动日志」：若模型在 `allocate_ids` 之前崩溃，这条命令会留在日志里但没有对应的轮次，页面重试会产生第二条记录。
