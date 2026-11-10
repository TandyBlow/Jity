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
  - `snapshotId = snap_<sha256(canonical payload)>`：内容身份只看 payload。
  - 父链、内容身份、revision 互相独立。revision 是服务端保存版本，每次
    实际写入（新增节点、合并父边、切 head）加一；时间戳不参与覆盖判断。
  - 所有写事务 `BEGIN IMMEDIATE`，CAS 在事务内比较。
  - `activate:false` 只存分叉，不动 head；`select_head` 只移动 head，目标
    必须是分支叶子；另一份始终可读。
  - 同一 `requestId` 重试在 CAS 检查前命中幂等记录，返回原 snapshotId 和
    当前 head/revision；同 id 不同内容返回 409 `request_id_reused`。
  - 拒绝父节点缺失、自环/祖先环、超过大小/节点数/父数上限的写入。
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
      // 先本地保存；在线则 CAS 上传；断网/5xx 入队；409 返回 conflict
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
# 13 passed：CAS 失败、幂等重放、祖先不能覆盖、离线分叉、分支选择、
# 双设备恢复、父链/环/大小/token/不透明 payload。

cd frontend
./node_modules/.bin/tsc -p tsconfig.world-contract.json --noEmit
./node_modules/.bin/vitest run src/lib/world-engine/local/progress-sync/progress-sync.test.ts --maxWorkers=1
# 16 passed：客户端 CAS、离线队列、丢响应幂等、分叉/选择、双设备、
# 队列冲突两种显式选择、web storage 队列、lineage 比较。

./node_modules/.bin/eslint src/lib/world-engine/local/progress-sync scripts/parallel-sync
# 0 errors
```

真实服务验证（本机 2026-10-28）：

```bash
cd backend
LOCAL_PROGRESS_DB=<temp>/progress.sqlite3 LOCAL_PROGRESS_TOKEN=smoke-token \
  python -m uvicorn app.services.local_progress.standalone:app --port 8019
# 另一终端：
PROGRESS_SYNC_URL=http://127.0.0.1:8019 PROGRESS_SYNC_TOKEN=smoke-token \
  node frontend/scripts/parallel-sync/two-device-smoke.mjs
# 输出 root / 幂等重放 / 409 / A 分支 / B 分叉 / 两叶可读 / 切 B。

PROGRESS_SYNC_URL=http://127.0.0.1:8019 PROGRESS_SYNC_TOKEN=smoke-token \
  ./frontend/node_modules/.bin/vitest run \
  src/lib/world-engine/local/progress-sync/real-server.test.ts --maxWorkers=1
# 1 passed：真实 HTTP 下两个客户端 save→pull→CAS 冲突→fork→选择→恢复。
```

## 限制

- 未修改页面、`session.ts`、`app/main.py` 或共享数据库；页面接入需要按上面
  的接线步骤完成，主集成方负责。
- 未做真实模型/GPU/浏览器页面运行；本线不涉及推理，相关能力未验证。
- token 是全局 Bearer，不是每用户授权；世界 ID 由调用方生成。
- graph 一次返回一个世界全部节点，默认上限 5000；未做分页。
- 队列默认内存；提供 `createWebStorageQueueStore`，页面可选择用
  `localStorage` 持久化。队列存储失败时保留内存队列并暴露
  `queuePersistenceError`，不阻塞本地保存。
- 队列冲突不会自动丢弃或自动合并，必须由玩家显式选择；这是产品约束。
- 没有压缩、加密、服务端 GC/备份；幂等记录按 30 天惰性清理。
