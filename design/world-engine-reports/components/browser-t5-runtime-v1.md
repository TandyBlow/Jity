# c9 浏览器 T5 运行验证（77M r3-direction）

日期：2026-11-08。对象：**冻结的 N4 成句组件 `r3-direction`**（Randeng-T5-77M 全参微调，77,440,384 参数）的 fp32 ONNX 导出。范围只有运行：加载、一次推理、取消、内存、浏览器与离线一致性。**不判断文本质量，不训练，不接正式页面**；`frontend/src/app/world/page.tsx`、`backend/app`、共享契约均未改动。

结论分三类标注：**已证明**（有可复跑的原始输出）、**已失败**、**无法判断**。`undetermined` 不算通过。

- [x] **已证明**：这套 T5 编解码在真实 Edge 里能加载、能推理；4 轮 × 7 用例共 **28/28 与离线 ORT-python 逐 token 一致**；取消在步边界生效；取消后会话仍可用且输出不变。
- [x] **已证明**（成本）：冷启动（导入运行时到两个会话就绪）中位数 **14.1 s**；热推理 **50.3 ms/步**（离线 41.1 ms/步）；整页可归因内存 **约 973 MB**，`release()` 之后不回收。
- [ ] **无法判断**：wllama 能否端到端跑 T5——仓库里没有真实 T5 GGUF，也没有 HF→GGUF 转换器，跑不了。见 §7，这不算通过。

## 1. 这一轮谁给了谁什么

参与者只有三个：一个本地静态服务器、一个 Edge 页面、一份已冻结的模型文件。

1. **服务器**按固定路由把文件递给页面，不做算术：`/graphs/encoder.onnx`（142.4 MB）、`/graphs/decoder_kv.onnx`（234.5 MB）、`/graphs/spiece.model`（680 KB，分词表）、`/fixtures/probe_inputs.json`（7 个已登记用例）、`/ort/*`（onnxruntime-web 1.30.0 的 wasm）、`/sp/index.js`（sentencepiece-js 1.1.0）。同一份文件也可以从磁盘直接读，路由只是让浏览器能 `fetch`。本轮共传输 388.3 MiB，localhost 不节流。
2. **页面**做三件事，顺序固定：先用 sentencepiece-js 把用例文本切成 id 并在末尾补 `</s>`=1；把 id 喂给 encoder 图换出 `encoder_hidden_states`；然后从 `<pad>`=0 起步，每步喂一个 token 给 `decoder_kv.onnx`，取最后一格 logits 的最大值作为下一个 token，遇 1 停止。解码器图只缓存自注意力 K/V，交叉注意力 K/V 每步在图内重算（`decoder_kv.onnx` 的输入契约）。
3. **结果**：页面把每一步的毫秒数、token id、文本、取消结果、内存采样写进 `window.__C9_RESULT__`；驱动脚本把它连同浏览器版本、CDP 指标、每个 URL 的字节数落到 `runs/<stamp>/browser-result.json`。`compare.py` 再把它和离线参照逐位比对，写 `runs/comparison.json`。

一个完整例子（用例 `n4h-loc-01`，冻结留出）：

| 环节 | 值 |
| --- | --- |
| 输入文本 | `叙事生成任务。\n事实：\n1. 位置：陆知微 从柳堤到药圃\n2. 时间推进：约九分钟\n正文：` |
| 分词 | 35 个 id（含尾部 `</s>`=1），与夹具里烘焙好的 id 逐位相同 |
| encoder | 一次前向，热态 **141.2 ms** |
| decoder | 17 次前向（16 个 token + 1 次撞到 `</s>`），热态 **54.7 ms/步**，合计 929.6 ms |
| 输出 id | `259, 9375, 2894, 3786, 2772, 5650, 23880, 6043, 6094, 29782, 297, 25525, 24952, 3415, 2405, 297` |
| 文本 | 陆知微由柳堤进入药圃。前后大约九分钟。 |
| 与离线 | 16 个 id 全同，文本全同 |

「17 次前向 / 16 个 token」的差别是最后那步：模型输出 `</s>`，循环在那一步停下，所以步数比 token 数多 1。

## 2. 输入登记（哈希来自 `runs/assets.json`）

| 对象 | 位置（工作树外，只读） | sha256 | 大小 |
| --- | --- | --- | --- |
| encoder | `.local/world-components-worktree/experiments/world-components/assets/n4-onnx/r3-direction/encoder.onnx` | `b49b3ad2…6b1bcc7324` | 142,418,864 B |
| decoder_kv | 同上 | `6905fc88…7c4a2d1a` | 234,545,169 B |
| 分词表 | `…/assets/n4-finetune/r3-direction/spiece.model` | `c65feffa…46a3a12f` | 680,811 B |
| 夹具 | `experiments/world-components/browser_probe/probe_inputs.json` | `2f0babc8…` | 7 个用例 |
| 基座快照（参数核对） | `.local/models/model.safetensors` | 77,440,384 参数 | — |

两张 ONNX 图的哈希与 `export_manifest.json` 里记的一致（`exportManifestMatchesDisk: true`）。解码参数固定：贪心、`max_new_tokens=64`、`eos=1`、`pad=0`、`decoder_start=0`、6 头、`d_kv=64`、`d_model=512`、词表 32,596、8+8 层。夹具的 7 个用例 ID 与 `/s` 尾 token 的分词结果全部逐位相同（28/28 次检查）。

## 3. 冷启动与推理耗时

四轮同机同浏览器（Edge 157.0.0.0 headless，onnxruntime-web 1.30.0，wasm 单线程，`numThreads=1`）。`run1` 是机器首次读取这些文件（磁盘未热），后三轮是热磁盘。

| 阶段 | run1（冷磁盘） | run2 | run3 | mem1 | 中位数 |
| --- | --- | --- | --- | --- | --- |
| 导入 ORT 运行时 | 2381.3 ms | 54.6 | 58.9 | 71.6 | 60.3 ms |
| 取分词表 + 分词 bundle | 328.5 ms | 61.3 | 59.5 | 55.3 | 58.9 ms |
| 分词器初始化 | 279.0 ms | 245.1 | 248.6 | 292.8 | 270.8 ms |
| encoder 会话创建 | 10184.8 ms | 5456.0 | 5507.3 | 6715.6 | 6110.8 ms |
| decoder 会话创建 | 7946.6 ms | 7334.2 | 7609.6 | 7663.7 | 7636.7 ms |
| **合计** | **21120.2 ms** | **13151.2** | **13483.9** | **14799.0** | **14141.5 ms** |

推理（同一用例 `n4h-loc-01`）：

| 量 | 浏览器 | 离线 ORT-python（CPU，单线程） |
| --- | --- | --- |
| 首次 encoder（进程内第一枪） | 285.6–473.0 ms | 89.5 ms |
| 热态 encoder | 113.8–150.2 ms | 89.5 ms |
| 每解码步（7 用例 28 次采样） | 中位 50.3 ms（35.6–72.1） | 中位 41.1 ms（36.5–55.2） |
| 17 步合计（热） | 929.6–1001.8 ms | 650.5 ms |

浏览器每步比离线慢约 1.22 倍。逐步让出宏任务（取消要用）实测没有可分辨的代价：run2 热推理 54.7 ms/步，关掉让出的对照 48.9 ms/步，方向不稳定，落在噪声里。

整页从导航到全部用例跑完：计时轮 27.6–28.8 s；冷盘轮 172.8 s（其中包含被内存采样拖慢的部分）。

## 4. 取消

两步真实做过的事：

| 场景 | 触发方式 | 结果 |
| --- | --- | --- |
| 定时取消 | 120 ms 后 `AbortController.abort()` | 抛 `AbortError`，已跑完 **2** 步，从发起到抛出 **397 ms**，不返回部分文本 |
| 步边界取消 | 第 5 步回调里 `abort()` | 抛 `AbortError`，已完成 **5** 步，耗时 **575 ms**，不返回部分文本 |

取消的粒度是「一步」：ORT 单次 `run()` 不可中断，只在步与步之间检查信号。取消后再用同一会话跑同一用例，输出 id 与冷态完全相同（4 轮都如此），说明取消不会污染 KV 缓存状态——因为它根本不复用上一次的缓存，每轮都从零长缓存重来。

## 5. 内存

`mem1` 轮，`performance.measureUserAgentSpecificMemory()`（COOP/COEP 同源隔离下才有），它统计的是**整个页面可归因的字节**，包括取下来的 388 MiB 图文件和 wasm 线性内存，不是「模型本体占用」。

| 时刻 | 可归因字节 | JS 堆 |
| --- | --- | --- |
| 创建前 | 1.10 MB | 1.45 MB |
| 两个会话创建后 | **973.3 MB** | 242.6 MB |
| 热推理后 | 973.8 MB | 14.8 MB |
| 释放前 | 973.9 MB | 15.7 MB |
| `release()` 后 300 ms | **973.9 MB** | 15.1 MB |

两件事要看清：一是峰值在创建阶段就到位（约 973 MB），推理过程几乎不再增长；二是 `release()` 之后没有任何回收——wasm 线性内存只增不减，页面要真正释放只能重载。JS 堆那 242 MB 是创建阶段的临时数组，GC 后回落到 11–16 MB。

## 6. 一致性

判定方式：`offline_reference.py` 在同一台机器用 ORT-python 1.25.1、单线程、同样的贪心循环和同样的 id，重跑 7 个用例；浏览器侧用 sentencepiece-js 重新分词（不直接喂烘焙 id），再从零缓存跑一遍。

| 轮 | 用例 | token 与离线一致 | 与夹具存的 `referenceIds` 一致 | 文本一致 |
| --- | --- | --- | --- | --- |
| run1 / run2 / run3 / mem1 | 7×4 | **28/28** | 28/28 | 28/28 |

离线侧自己也与夹具存的 `referenceIds` 逐 token 相同（7/7），说明夹具没有被改动过。这组一致性的意义是：**同一份 ONNX、同一份分词表、同一套贪心规则，走 wasm 和走 CPU 原生运行时得到逐位相同的 token**，浏览器不需要额外的数值容忍。

## 7. wllama 这一支：做了什么、看到什么、为什么判不了

任务里写明「不默认 wllama 能执行 T5」，所以单独查了一轮。

已做的两件事：

1. **符号层**：`.local/llama-cpp/llama.dll` 与 wllama 3.8.1 自带的 `wllama.wasm` 里都能找到架构名 `t5encoder`；`wllama.wasm` 里还留有 `!cross->seq_ids_enc.empty() && "llama_encode must be called first"` 这条断言文本。也就是说 llama.cpp 核心里有编解码的编码入口。
2. **架构分发实测**：手写三个最小 GGUF v3 头，只有一个元数据键不同（`general.architecture` = `t5` / `t5encoder` / `notanarch`），分别喂给 `llama-cli.exe` 和 wllama 3.8.1。

`llama-cli.exe` 的返回（`runs/wllama-arch-cli-*.txt`）：

| 架构名 | 加载器返回 |
| --- | --- |
| `t5` | `key not found in model: t5.context_length` —— 认识这个架构，往下查超参 |
| `t5encoder` | `key not found in model: t5encoder.context_length` —— 同样认识 |
| `notanarch` | `unknown model architecture: 'notanarch'` —— 不认识的架构确实会拒绝 |

wllama 的返回则没有区分度：三个文件全都 `loadModel` 成功、`isModelLoaded()=true`，随后 `createCompletion` 全部抛同一个 `RuntimeError: Invalid typed array length: 1163217991`，连假架构也一样。这说明 wllama 在这个极薄的文件上根本没走到原生加载逻辑，**它的返回不能当证据**，正反都不能。

因此这一支的结论是：**无法判断**。缺的那一步很具体——仓库里没有任何真实 T5 GGUF，也没有 HF→GGUF 转换器（`.local/llama-cpp` 只有 `llama-gguf-split.exe`）。要关闭这个问题，得先把 r3-direction 或基座 77M 转成 `t5` 架构的 GGUF，再在浏览器里重跑一次加载 + 一次生成。这一步没有做，所以 wllama 路线不计入「可行」。

## 8. 没有做 / 不能断言

- **质量**：本轮只比 token 是否一致，不比句子好不好。7 个用例里 4 个是冻结留出、3 个是批次扩展输入，样本量不足以支撑任何质量结论。
- **网络口径**：全部在 localhost 上跑，388.3 MiB 没有经过真实网络，冷启动的 14 s 里不含下载时间。
- **int8**：只跑了 fp32。`r3-direction-int8` 图存在但本轮未测，量化损失是另一个问题。
- **页面接线**：没有碰 `frontend/src/app/world/page.tsx`，也没有测与其它模型共存的加载/切换开销。
- **其它浏览器**：只测了 Edge 157（Chromium 内核 headless）。Firefox / Safari 未测。
- **取消语义的边界**：单步 `run()` 不可中断，所以最大响应延迟等于一步耗时（本机 35–72 ms）；轮到下一个 token 的等待没有优化。

## 9. 复现

命令与文件作用见 `experiments/world-components/parallel/browser_t5/README.md`。四轮原始输出在 `runs/{run1,run2,run3,mem1}/`（不提交），汇总证据在 `artifacts/world-components/browser-t5-runtime-r1.json`，含每轮的阶段计时、逐用例 token、取消结果、内存采样和 wllama 的原始返回。

浏览器与运行时：Edge `157.0.0.0`（headless，`--enable-precise-memory-info`）、Playwright `1.63.0`、onnxruntime-web `1.30.0`（wasm，`numThreads=1`）、sentencepiece-js `1.1.0`、Node `v22.20.0`、win32 x64。
