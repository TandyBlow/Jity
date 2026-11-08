# c9 · 浏览器 T5 运行探测（77M r3-direction）

本目录只回答一个问题：**这份 77M T5 编解码模型能不能在真实浏览器里跑起来，跑一次多少钱，中断能不能停，内存多少，输出和离线是否逐 token 一致。**
不判断文本质量，不训练，不接正式页面，不改 `frontend/src`、`backend/app` 或任何共享契约。所有输入权重、分词器、夹具都按原位置只读引用，本目录不复制模型。

## 文件

| 文件 | 作用 |
| --- | --- |
| `assets.py` | 登记输入：找到现有的 77M 权重、ONNX 图、分词器、已登记夹具，算 sha256/大小/参数量/解码参数 → `runs/assets.json` |
| `offline_reference.py` | 离线参照：用 ORT-python 按与浏览器相同的贪心循环跑同一批已登记输入 → `runs/offline-reference.json` |
| `t5_adapter.mjs` | 浏览器侧运行器：sentencepiece-js 分词 + encoder 一次 + decoder 逐步（自注意力 KV 缓存）+ 贪心；加分段计时、逐步回调、`release()` |
| `probe.html` | 页面：冷启动各阶段计时 → 首推理 → 热推理 → 关掉让出宏任务的对照 → 7 个用例 → 两种取消 → 复用 → 释放 |
| `run_probe.mjs` | 驱动：固定路由的本地静态服务器（COOP/COEP，不节流）+ headless Edge，落 `runs/<stamp>/browser-result.json` 与 `console.log` |
| `wllama_probe.mjs` / `.html` | wllama 一支：三个只改 `general.architecture` 的最小 GGUF 头喂给 wllama，记录加载与生成的返回 |
| `compare.py` | 判定：浏览器 token 与离线参照逐位比较，汇总跨运行的计时/内存/取消结论 → `runs/comparison.json` |
| `distill.py` | 汇总成可提交的证据文件 `artifacts/world-components/browser-t5-runtime-r1.json` |

`runs/` 是机器本地原始输出（大文件、不提交）；结论与哈希在被 `distill.py` 汇总的证据文件里。

## 复现

```bash
cd frontend && npm ci          # 需要 @playwright/test / onnxruntime-web / sentencepiece-js
cd ..
node experiments/world-components/parallel/browser_t5/run_probe.mjs --stamp t1        # 计时轮
node experiments/world-components/parallel/browser_t5/run_probe.mjs --stamp m1 --mem  # 内存轮（慢，~165 s）
D:/software/Anaconda/python.exe experiments/world-components/parallel/browser_t5/assets.py
D:/software/Anaconda/python.exe experiments/world-components/parallel/browser_t5/offline_reference.py
D:/software/Anaconda/python.exe experiments/world-components/parallel/browser_t5/compare.py
node experiments/world-components/parallel/browser_t5/wllama_probe.mjs w1
```

`--mem` 那一轮里每次 `performance.measureUserAgentSpecificMemory()` 会强制全量 GC，单次约 18 s，所以默认关闭：计时轮只读便宜的 JS 堆数字。

## 结论在哪

- 报告：`design/world-engine-reports/components/browser-t5-runtime-v1.md`
- 证据：`artifacts/world-components/browser-t5-runtime-r1.json`
- 原始：`runs/{run1,run2,run3,mem1}/`、`runs/wllama{1,2}/`

一句话：ORT-web fp32 这条路 4 轮 × 7 用例共 28/28 与离线逐 token 一致，取消与复用可用；冷启动约 14 s、热推理约 50 ms/步、整页内存约 973 MB 且释放后不回收；wllama 这一支因为仓库里没有真实 T5 GGUF，判为未验证，不算通过也不算失败。
