# 真机手机验收流程（待执行）

状态：procedure ready，尚无真机证据。模拟移动条件不能替代本页。

## 1. 前置

- 笔记本与手机同一局域网；笔记本防火墙放行 3443。
- 产品服务：冻结构建的 `next start`（本平台用 3180 隔离构建；脚本
  `scripts/phone-https-proxy.mjs` 目前把上游写死 3177，若用 3180 先改 `UPSTREAM.port`）。
- 证书：`.local/phone-tls/{key,cert}.pem` 已存在；不存在时按
  `openssl req -x509 -newkey rsa:2048 -nodes -days 7 -subj "/CN=<LAN-IP>"` 生成。
- 模型：页面需要的 GGUF/ONNX 已在 `frontend/public/models` 与 `frontend/public/micro`。

## 2. 起服务与代理

```bash
# 冻结构建（HEAD 快照）；记录 BUILD_ID 与 git HEAD
cd frontend && node node_modules/next/dist/bin/next start -p 3180
# 代理：https://<LAN-IP>:3443 -> http://127.0.0.1:3177
node scripts/phone-https-proxy.mjs
```

代理打印的 LAN 地址即手机访问地址。若改用 3180，把 `UPSTREAM.port` 改成 3180 并重启代理。

## 3. 手机操作

1. 打开 `https://<LAN-IP>:3443/world-local`，接受自签证书。
2. 确认页面顶部模型身份：语义/叙事模型文件名与 sha256 与
   `artifacts/goal/model-manifest.json` 一致；WebGPU adapter 名称记下来。
3. 依次输入 `artifacts/goal/platform/eval/turns-holdout-v1.json` 的 4 条输入；每条记录：
   - 提交时间（秒表/屏幕录制）；
   - 首段可读正文出现时间；
   - 正文结束时间；
   - 控制权交还（输入框可再次提交）时间；
   - 屏幕截图（正文 + 状态面板）。
4. 第 4 条后刷新页面，确认进度恢复；再关闭网络，确认仍可输入一回合并本地保存。
5. 若可用 USB DevTools：在控制台执行
   `JSON.parse(JSON.stringify(globalThis.__worldTurns))` 导出回合记录；否则以截图为准。

## 4. 证据文件

写到 `artifacts/goal/platform/phone/<YYYYMMDD>-<device>.json`：

```json
{
  "device": "phone model / OS / browser",
  "lanUrl": "https://...",
  "buildId": "...",
  "gitHead": "...",
  "webgpu": {"adapter": "...", "available": true},
  "models": [{"role": "semantic|narration", "file": "...", "sha256": "..."}],
  "turns": [
    {"id": "hold-v1-01", "inputAt": "...", "firstReadableMs": 0, "textFinishedMs": 0,
     "controlReturnedMs": 0, "text": "...", "screenshot": "..."}
  ],
  "offline": {"turns": 1, "saved": true},
  "refresh": {"restored": true, "history": 4}
}
```

## 5. 通过口径

- 首段可读 ≤60 s、单点正文完成 ≤300 s（与笔记本同口径，D-023 未裁定移动档质量门槛前只记录）。
- 正文与页面记录逐字一致；不出现程序正文冒充模型。
- 刷新恢复、离线保存、模型身份核验三项必须有证据。
- WebGPU 崩溃（E25 的 Mali Valhall）按失败记录，不改口径。

## 6. 已知限制

- 代理上游默认 3177；与别的 lane 共用时先确认租约与服务身份。
- iOS Safari 的 IndexedDB/WebGPU 行为需单独记录，不能与 Android 混为一份证据。
- 模拟器（CPU 节流 + gpu-lite）只作回归，不能计入真机通过。
