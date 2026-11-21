# Tasks: G8 交付验收与证据

## 1. 生产栈与输入

- [x] 1.1 `npm run build` 通过；`next start -p 3177` 服务 `/world-local`。
- [x] 1.2 `turns-20.json`（20 例）与 5 个四回合 chunk；驱动要求的数组格式已修正。
- [ ] 1.3 跑完 5 块 20 输入；逐回合证据落 `artifacts/goal/acceptance/`。chunk1 四例完成但全超 60 秒首段，run 在收尾时被宿主回收。

## 2. 离线与服务器关闭

- [ ] 2.1 断网运行：页面、模型、IndexedDB 保存可用。
- [ ] 2.2 `--block-api`：禁用 `/api/**` 后仍可游玩与本地保存；网络记录只有静态资源。

## 3. 两设备分叉

- [ ] 3.1 两个浏览器配置从同一快照出发，各自离线推进。
- [ ] 3.2 并发上传检测分叉，`sync.choose` 选一支，另一支仍可恢复；证据 `artifacts/goal/sync/`。
- [ ] 3.3 页面接冲突分叉选择 UI（当前只有 startup restore 与状态标签）。

## 4. 交付物

- [ ] 4.1 `artifacts/local-game-delivery/manifest.json`：代码 SHA、静态世界哈希、模型 bytes/sha256/license、复现命令。
- [ ] 4.2 `design/world-engine-reports/local-game-acceptance.md`：逐项证据、失败项、D-019 说明。
- [ ] 4.3 R01–R16 账本关闭或明确未完成。

## 5. 收口

- [ ] 5.1 `openspec validate "goal-g8-delivery" --strict`；归档；按路径 commit；打 G8 tag。
