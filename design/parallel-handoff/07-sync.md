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

## 接线

### 给 06：产品接入（2026-11-10 组织调整后）

06 的集成树里已有一份**旧版** `local/progress-sync/`（除换行外与旧提交相同）。
需要合入的提交：`b4c9ea5b`（`goal/local-07-sync`），它只改
`frontend/src/lib/world-engine/local/progress-sync/`，不改页面、会话、prompt
或任何共享文件。新增的是 `product.ts` 与 `reconnect-chain.test.ts`。

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

1. **每次 06 自己把进度写进 IndexedDB 之后**调 `sync.push(snapshot)`。
   不要再让适配层写第二遍本地记录：`push` 只上传，`save` 才是“本地+上传”
   （如果页面还没自己保存，就用 `save`）。返回 `synced | queued | conflict`；
   `queued` 表示已经本地存好，重连后 `flush` 会补传。
2. **开局恢复**：先读 06 的本地记录；本地没有才 `await sync.restore()`
   （它会拉远端 head 并写回本地）。`restore().conflict` 出现时不要自动选，
   把两份分支交给玩家。
3. **冲突 UI**：`conflict.branches` 是两条叶子，`conflict.remote` 是远端 head。
   玩家点选后调 `sync.choose('keep-remote' | 'keep-local-fork', conflict)`；
   两个副本都留在服务端，之后仍可用 `sync.read(snapshotId)` 读回。
4. **重连/页面回到前台**：`await sync.flush()`。同一次离线期间的多次保存会按
   顺序作为**后代链**上传（父节点指向前一条上传），不会并发拿同一个旧 head。
   第二次 flush 幂等，不新增快照。`flush().conflictList` 里是真正的冲突对象，
   页面要拿它让玩家选择，不能只看 `conflicts` 计数。
5. **判断要不要提示玩家**：`await sync.status()` 只读，返回
   `in-sync | remote-ahead | local-ahead | diverged | local-only | unknown`，
   另带 `remote`、`baseSnapshotId`、`branches`。它不会因为读了一次 head 就把
   自己当成已同步；`remote-ahead` 时页面应提示“另一台设备有新进度”，
   `diverged` 时提示选择，不要自动覆盖。

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
# 27 passed（无服务时 real-server 两个文件 skip）：客户端 CAS、离线队列/多离线
# 保存链、丢响应幂等、分叉/选择、双设备、队列冲突两种显式选择及依赖 rebase、
# web storage 队列、lineage 比较、product 适配器、push 不重复写本地、head 恢复。
PROGRESS_SYNC_URL=http://127.0.0.1:8010 PROGRESS_SYNC_TOKEN=secret   ./node_modules/.bin/vitest run src/lib/world-engine/local/progress-sync/ --maxWorkers=1
# 30 passed：再加真实 HTTP 的两个客户端 save→冲突→fork→选择→恢复，
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
