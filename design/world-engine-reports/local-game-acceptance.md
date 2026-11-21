# Jity 本地交付验收报告（2026-11-21）

状态：**未通过**。技术证据已尽量收集；真机栈受宿主内存反复回收，离线与服务器关闭只跑到部分回合，两设备分叉未做。

## 1. 口径

- D-019（2026-11-21）：用户放弃签字与 10 次独立输入；G8 改为技术证据验收。
- 硬门槛不变：60 秒首段、300 秒单点、20 次真实页面输入、离线、服务器关闭、两设备分叉。
- 目标设备：RTX 4060 Laptop 8 GB + Edge（D-010）。本次验收使用生产构建（Next 15.5.19）+ Playwright Chromium。

## 2. 交付物

- 代码：`agent` 分支；manifest 记录 git head（见 `artifacts/local-game-delivery/manifest.json`）。
- 世界：`/worlds/dragon-raja-free-day.world.json`，stateDigest `3f65452d…f4e`，LF 文件哈希 `6262d5fc…92e`，26 地点/14 人物/74 物品/73 任务。
- 模型：语义 Qwen3-0.6B Q4（396,705,472 B，sha256 `ac2d9771…524a`）+ 叙事 Qwen3-1.7B Q4（1,107,409,472 B，sha256 `b139949c…1897`），Apache-2.0；获取 `node frontend/scripts/fetch-models.mjs`。
- 复现：`npm ci` → fetch-models → `npm run build` → `npx next start -p 3177` → 验收驱动。

## 3. 20 次页面输入

汇总：`artifacts/goal/acceptance/summary.json`（16/20 首段过、20/20 回合 <300 s、12 个回合靠 295 秒页面时限收尾）。

| chunk | 输入 | 首段 | 回合 | 结果 |
|---|---|---|---|---|
| chunk1 | s01–s04 | 63.5/154.2/73.1/112.5 s | 295–298 s | 4 例首段超 60（宿主负载），保留为失败 |
| chunk2 | s05–s08 | 18.0/18.1/39.7/34.5 s | 277–296 s | 干净，reload 4/4、state 恢复 |
| chunk3 | s09–s11 | 34.0/17.4/19.9 s | 163–298 s | 干净（s11 有页面内部注记） |
| chunk3b | s12–s16 | 1.3–22.7 s | 296–298 s | 干净，reload 5/5、state 恢复 |
| chunk5 | g8-t1..t4 | 18.3–32.1 s | 259–295 s | 干净，reload 4/4、state 恢复 |

结论：60 秒门在干净栈上通过（1.3–39.7 s）；chunk1 四例是宿主同时吃紧时的失败，重跑被内存回收、未取代。300 秒回合上限通过，但多数回合依赖 295 秒页面时限（judge 策略的代价，D-017/D-018）。

## 4. 离线

`g8-offline-20261121.json`（`--offline`，模型加载后断网，chunk2）：

- s05/s06 有正文（首段 19 s），本地保存在断网下工作。
- s07/s08 到 330 秒无正文（驱动 cap），记失败。
- reload 恢复 3/4，state 检查失败。
- 结论：离线可玩有部分证据，但不完整，不能宣布通过。

## 5. 服务器关闭

`g8-block-api-20261121-aborted-memory.json`（`--block-api`，两回合）：

- s05 有正文（首段 81 s，超 60），保存服务被拒时页面仍完成回合与本地保存。
- 第二回合并未跑完，run 被宿主回收。
- 结论：部分证据，不能宣布通过。

## 6. 两设备分叉

未做。页面目前只有 startup `sync.restore()` 与状态标签；冲突分叉选择 UI 与 `sync.choose` 的页面接线未实现，G7 验收证据 `artifacts/goal/sync/` 为空。

## 7. G5/G6 状态

- G5：技术自检不通过（2026-11-21 复核）。16 例技术读评 hard 13/style 3/clean 0；识别带、门状态、占位句、状态字段已加拒绝与回归；s06 judgment/fact 未修。change `goal-g5-semantics-followup`。
- G6：进行中。原样输出路径保持；16 例读评与 prompt 修复已记录；真机读评与阈值未冻结。

## 8. 结论与限制

- G8 未通过：20 输入与计时证据齐但含 4 例首段失败；离线/服务器关闭只到部分回合；两设备分叉缺失；用户签字按 D-019 豁免。
- 宿主内存是主因：生产栈（两模型约 1.5 GB 权重 + 浏览器）在宿主同时吃紧时被回收；干净窗口下 chunk2/3b/5 全部通过 60 秒门。
- 下一步：干净宿主上重跑 chunk1、补齐离线/block-api；实现 G7 冲突选择 UI 并跑两设备分叉；再更新本报告与 ledger。不得在缺证据时宣布完成。
