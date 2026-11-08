# c9 · 浏览器 T5 运行探测（77M r3-direction）

本目录只回答运行问题：这份 77M T5 编解码模型能不能在真实浏览器里跑起来、跑一次多少钱、中断能不能停、内存能不能还、输出和离线是否一致，以及 int8 图换来多少体积/时间/内存、代价是哪些 token 变了。
不判断文本质量，不训练，不接正式页面，不改 `frontend/src`、`backend/app` 或共享契约。所有输入权重、分词器、夹具都按原位置只读引用，本目录不复制模型。

## 文件

| 文件 | 作用 |
| --- | --- |
| `assets.py` | 登记输入：找到现有的 77M 权重、fp32/int8 ONNX 图、分词器、已登记夹具，算 sha256/大小/参数量/解码参数 → `runs/assets.json` |
| `offline_reference.py` | 离线参照：ORT-python 按与浏览器相同的贪心循环跑同一批已登记输入，`--graphs fp32\|int8` → `runs/offline-reference[-int8].json` |
| `t5_adapter.mjs` | 浏览器侧运行器：`createTokenizer()`（sentencepiece-js + 真实 spiece.model）与 `T5Browser`（encoder 一次 + decoder 逐步、自注意力 KV、贪心）分开；带分段计时、逐步回调、`generateFromIds()`、`release()` |
| `probe.html` | 页面探测：冷启动各阶段 → 首推理 → 热推理 → 关掉宏任务让出的对照 → 7 个用例 → 两种取消（记录「发出取消→抛错」） → 复用 → 释放 |
| `run_probe.mjs` | 页面探测驱动：固定路由本地服务器（COOP/COEP，不节流）+ headless Edge，`--graphs fp32\|int8`、`--mem` |
| `t5_worker.mjs` | 把模型搬进 DedicatedWorker 的运行时：只收 id、只回 id 与计时，`cancel` 以消息形式到达 |
| `worker_probe.html` | worker 探测：A 初始化 → 推理 → 取消 → 采样 → terminate（立即 / +0.8 s / +5 s，每次记录测量起止时刻）→ B 重建跑 7 用例 → 再 terminate |
| `run_worker_probe.mjs` | worker 探测驱动，`--graphs`、`--mem`，`--rss`（1 s 粒度采进程树工作集）、`--no-rebuild`（终止 A 后只采样，用于回收时点；该轮无用例结果且计时不可用） |
| `wllama_probe.mjs` / `.html` | wllama 一支：三个只改 `general.architecture` 的最小 GGUF 头喂给 wllama，记录加载与生成返回 |
| `expectations.json` | 钉住的验收前提：夹具/分词表/参数/两套图哈希、7 个用例名、最少运行组数。`compare.py` 缺任何一项即失败 |
| `compare.py` | 判定：先查 `expectations.json` 与每组运行的用例完整性（缺数据不放过），再比 fp32↔离线 fp32、int8↔离线 int8（同图），另列与 fp32 的量化差异；判决本身也是 check，`allChecksPass` 决定退出码 → `runs/comparison.json` |
| `distill.py` | 汇总成可提交的证据文件 `artifacts/world-components/browser-t5-runtime-r4.json`（含 acceptance 全量 check、RSS 三轮摘要、int8 同图对照） |

`runs/` 是机器本地原始输出（大文件、不提交）；结论与哈希在被 `distill.py` 汇总的证据文件里。

## 复现

```bash
cd frontend && npm ci          # @playwright/test / onnxruntime-web / sentencepiece-js
cd ..

node experiments/world-components/parallel/browser_t5/run_probe.mjs --stamp p1              # 页面, fp32, 计时轮
node experiments/world-components/parallel/browser_t5/run_probe.mjs --stamp p2 --mem         # 页面, fp32, 内存轮（每次采样约 18 s）
node experiments/world-components/parallel/browser_t5/run_probe.mjs --stamp i1 --graphs int8 # 页面, int8
node experiments/world-components/parallel/browser_t5/run_probe.mjs --stamp i2 --graphs int8 --mem

node experiments/world-components/parallel/browser_t5/run_worker_probe.mjs --stamp w1            # worker, fp32
node experiments/world-components/parallel/browser_t5/run_worker_probe.mjs --stamp w2 --mem       # worker, fp32 + 内存/终止
node experiments/world-components/parallel/browser_t5/run_worker_probe.mjs --stamp w3 --mem --graphs int8
node experiments/world-components/parallel/browser_t5/run_worker_probe.mjs --stamp w4 --rss                                        # 回收时点（1 s 分辨率）
node experiments/world-components/parallel/browser_t5/run_worker_probe.mjs --stamp w5 --rss --no-rebuild                          # 纯回收时点（不重建 worker B）

D:/software/Anaconda/python.exe experiments/world-components/parallel/browser_t5/assets.py
D:/software/Anaconda/python.exe experiments/world-components/parallel/browser_t5/offline_reference.py
D:/software/Anaconda/python.exe experiments/world-components/parallel/browser_t5/offline_reference.py --graphs int8
D:/software/Anaconda/python.exe experiments/world-components/parallel/browser_t5/compare.py
node experiments/world-components/parallel/browser_t5/wllama_probe.mjs w4
```

`--mem` 那一轮里每次 `performance.measureUserAgentSpecificMemory()` 会强制全量 GC，单次约 18 s，所以默认关闭：计时轮只读便宜的 JS 堆数字。

## 结论在哪

- 报告：`design/world-engine-reports/components/browser-t5-runtime-v1.md`
- 证据：`artifacts/world-components/browser-t5-runtime-r4.json`（前三轮为 `…-r3.json` / `…-r2.json` / `…-r1.json`）
- 原始：`runs/{run1,run2,run3,mem1,fp32-r2,fp32-r3,int8-r1,int8-mem1,w-fp32-1,w-fp32-mem1,w-int8-mem1,wllama1,wllama2}/`

一句话：fp32 走 ORT-web 已验证（页面 6 轮 + worker 2 轮，42+14 次逐 token 与离线一致）；页面内 `release()` 不还内存，但把模型放进 worker 后 `terminate()` 把 973 MB 还到 4.46 MB；回收时点只能说到「0.8 s 出现首次大幅下降、15 s 左右稳定」，**整体释放的完成时刻未确定**；重建后输出不变；int8 把两图从 376.96 MB 降到 220.46 MB、会话创建 13.7 s → 8.7 s、内存 973 MB → 713 MB，代价是 2/7 用例一处措辞不同，且这 2 处在与浏览器同图的 ORT-python int8 参照上完全一致（浏览器 int8 21/21 与离线 int8 逐 token 相同）；取消延迟按「发出取消→抛错」为 53–266 ms，上界是在飞 ORT 调用的剩余时间；wllama 因缺真实 T5 GGUF 判为未验证。
