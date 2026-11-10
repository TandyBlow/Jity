# parallel-persistence

线 06-recovery（本地持久化与处理中恢复）的浏览器验证脚手架。

- `browser-entry.ts`：页面侧场景集合，挂在 `window.PersistenceCheck` 上。用脚本化模型端口
  （不加载任何 GGUF 权重），把会话、IndexedDB 存储、多标签写锁、旧 localStorage 迁移、
  暂停/取消/恢复都跑一遍，每步记一条 `{name, ok, detail}`。
- `run-indexeddb-check.mjs`：用 rolldown 把上面的入口打成单文件，Playwright（系统 Edge）
  拦截 `https://local.test/` 在本地返回它，因此不需要 dev server、不需要 http 接口；
  两个真实标签页共用同一个 IndexedDB，用来验证写锁与接管。

```bash
cd frontend
node scripts/parallel-persistence/run-indexeddb-check.mjs   --out D:/others/Jity/.local/parallel-local-game/results/06-recovery/indexeddb-evidence.json
```

`--headed` 可以看着它跑；`PW_CHANNEL=chromium` 可换本机已下载的 Chromium（需要先
`npx playwright install`）。退出码非 0 表示有步骤失败，证据 JSON 里有 `failedSteps`。
