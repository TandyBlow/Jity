# Tasks: G8 交付验收与证据

## 1. 生产栈与输入

- [x] 1.1 `npm run build` 通过；`next start -p 3177` 服务 `/world-local`。
- [x] 1.2 `turns-20.json`（20 例）与 5 个四回合 chunk；驱动要求的数组格式已修正。
- [x] 1.3 跑完 5 块 20 输入；chunk1 在空闲宿主复跑（首段 27.1/19.1/17.4/16.9 秒）取代旧四例负载失败；汇总是 20/20 首段、20/20 回合上限、0 失败。

## 2. 离线与服务器关闭

- [x] 2.1 断网运行（复跑）：s05/s06 完成，首段 16.5/26.5 秒、reload 31.4 秒，failures 0；证据 `g8-offline-rerun-20261122.json`。
- [x] 2.2 `--block-api`（复跑）：s05/s06 完成，首段 40.4/25.0 秒，`/api` 请求 0 次，failures 0；证据 `g8-block-api-rerun-20261122-2026-11-21T1620-f746.json`。

## 3. 两设备分叉

- [x] 3.1 两个浏览器配置从同一快照出发，各自离线推进（B1/A2 各留一条离线保存）。
- [x] 3.2 并发上传检测分叉，`sync.choose` 选一支，另一支仍可恢复；证据 `artifacts/goal/sync/two-device-20261121.json`（2 分支、另一支 200 可读、刷新恢复）。
- [x] 3.3 页面接冲突分叉选择 UI：startup restore、重连自动 flush、远端头/分支面板、保留远端/保留本地并分叉；保留本地取 store 最新快照并清队列。

## 4. 交付物

- [x] 4.1 `artifacts/local-game-delivery/manifest.json`：代码 SHA、静态世界哈希、模型 bytes/sha256/license、复现命令（已生成；最终提交前重跑一次）。
- [x] 4.2 `design/world-engine-reports/local-game-acceptance.md`：逐项证据、失败项、D-019 说明（结论：未通过）。
- [x] 4.3 R01–R16 状态以 `design/goal/ledger.md` 为准逐项记录；未通过项（G5/G6）在验收报告与账本中保持未完成。

## 5. 收口

- [x] 5.1 `openspec validate "goal-g8-delivery" --strict`；归档；按路径 commit；打 G8 tag。
