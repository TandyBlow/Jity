# 任务：完成 rules 叙事臂的剩余验收

工作目录 `D:\others\Jity`。前端已经构建好（`npm run build` 已完成），不要重新构建，不要修改
`frontend/src` 或 `frontend/scripts` 里的代码，不要 git commit，不要动其他 agent 的文件。

## 1. 启动产品服务器

```
cd D:\others\Jity\frontend
node node_modules/next/dist/bin/next start -p 3177
```

后台运行，日志写到 `D:\others\Jity\artifacts\goal\lab\server-3177-pi.log`。等到
`http://127.0.0.1:3177/world-local` 返回 200 再继续。

## 2. 运行三条验收（都在 `D:\others\Jity\frontend` 目录执行）

每一轮开始前先看租约：

```
cd D:\others\Jity
python -X utf8 resource_lease.py status
```

如果 `status` 是 `held` 且 `stale` 说明持有进程已死，用返回里的 token 释放：

```
python -X utf8 resource_lease.py release --lane 09-ui --token <token>
```

不要按进程名杀浏览器；只清理你自己启动的进程。

a) 离线 3 回合 + 重新生成：

```
cd D:\others\Jity\frontend
node scripts/product-acceptance/accept-world-local.mjs --base http://127.0.0.1:3177 --turns ../artifacts/goal/narration-rules/turns-3.json --query "narrationCandidate=rules" --out ../artifacts/goal/narration-rules/offline-rules.json --intent smoke --fresh --allow-program --offline --regenerate-last
```

b) 移动端仿真 3 回合 + 重新生成：

```
node scripts/product-acceptance/accept-world-local.mjs --base http://127.0.0.1:3177 --turns ../artifacts/goal/narration-rules/turns-3.json --query "narrationCandidate=rules" --out ../artifacts/goal/narration-rules/mobile-rules.json --intent smoke --fresh --allow-program --mobile --regenerate-last
```

c) 二十输入 + 重新生成：

```
node scripts/product-acceptance/accept-world-local.mjs --base http://127.0.0.1:3177 --turns scripts/product-acceptance/turns-20.json --query "narrationCandidate=rules" --out ../artifacts/goal/narration-rules/turns20-rules-full.json --intent 20-turn --fresh --allow-program --regenerate-last
```

每条命令最多约 25 分钟；单回合超时由 `--turn-timeout-ms` 默认 330 秒控制。若某条失败，
记录失败原因后继续下一条，不要重试超过一次。

## 3. 收尾

三条都结束后停掉 3177 服务器（只停你自己启动的那个进程）。然后打印每份 evidence 的：

- `status`、`turns.length`、`failures`
- 每回合 `problems`
- `refreshRestore.overallRestored`
- `regeneration.clicked` 与 `regeneration.narrationEventsAfter > narrationEventsBefore`
- `network.modelRequests`（应只有 `Qwen3-0.6B-Q4_K_M.gguf`）

最后把三条的摘要写入 `D:\others\Jity\artifacts\goal\narration-rules\pi-run-summary.json`。
