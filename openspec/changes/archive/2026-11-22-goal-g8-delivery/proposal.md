# Proposal: G8 交付验收与证据

## Why

G1–G7 的机制已落地，但交付验收没有完成：20 次真实页面输入、60/300 计时、离线、服务器关闭、两设备分叉与 manifest 都没有齐全证据。D-019 已按用户决定取消用户签字与 10 次独立输入，G8 以技术证据为准；验收必须如实保留失败项，不得只留成功样本。

## What Changes

- 生产构建验收：`npm run build` 通过，`next start` 服务 `/world-local`；不再用 dev server 跑验收（dev 编译/HMR 的内存不在产品路径上）。
- 输入：`turns-20.json`（16 语义例 + 4 场景例），拆成 5 个四回合 session（`turns-20-chunk{1..5}.json`），每块留逐回合输入、前后状态、Δ、原始叙事与计时。
- 离线与服务器关闭：断网运行、`--block-api` 拒绝所有 `/api/**`，仍可游玩与本地保存。
- 两设备分叉：两个浏览器配置从同一快照出发、各自离线推进、并发上传检测分叉、选择一支、另一支可恢复；证据 `artifacts/goal/sync/`。
- 产 `artifacts/local-game-delivery/manifest.json` 与 `design/world-engine-reports/local-game-acceptance.md`，关闭 R01–R16 账本。
- D-019 记录：用户放弃签字与独立输入，报告如实写明。

## Capabilities

None. 本变更是交付验收与证据固化，不新增运行期能力；`skip_specs: true`。

## Impact

- 驱动：复用 `frontend/scripts/product-acceptance/accept-world-local.mjs`。
- 证据：`artifacts/goal/acceptance/`、`artifacts/goal/sync/`、`artifacts/local-game-delivery/`。
- 文档：`design/goal/ledger.md` R16/G8、验收报告。
