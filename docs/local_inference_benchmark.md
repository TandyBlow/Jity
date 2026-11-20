# 端侧推理基准 harness 使用说明

对应试验目标里的资源要求：4 核 CPU / 8GB 内存设备、单模型 ≤1B、单组件推理 ≤4 秒。本文档说明 `/benchmark` 页面测什么、怎么跑、结果怎么读。

## 启动

```bash
cd frontend
npm run dev        # predev 钩子会把 wllama 的 wasm/js 资产拷进 public/
```

浏览器打开 `http://localhost:3100/benchmark`（3000 被旧实例占用时用 3100；端口无关紧要，页面不调后端）。

`next.config.ts` 只给 `/benchmark` 挂了 COOP/COEP 头，多线程 wasm 需要 `crossOriginIsolated=true`；没有隔离头时自动回退单线程（环境面板会标注，结果偏低）。正式测量必须在目标设备的正式浏览器（Chrome/Edge）里做。

## 模型

- **文件**：点选本地 `.gguf`（支持分片多选）。
- **URL**：同源最稳——把模型放进 `frontend/public/models/`（已 gitignore），填 `/models/xxx.gguf` 的绝对 URL。远端 URL 需要对方发 CORS 头。
- 推荐：Qwen3-0.6B GGUF Q4_K_M（候选档里中文最强的 ≤1B 模型家族）。仓库里已有一个 `public/models/stories260K.gguf`（1.2MB）只用于流程冒烟——它词表只有 512，中文全部走字节回退（约 3.4 token/字符），测出的速度**不代表真实候选模型**。
- 加载参数强制 `n_gpu_layers=0`（wllama 3.8 默认自动启用 WebGPU，必须显式关掉才是 CPU 路径）、`warmup=false`；`n_ctx`/`n_batch`/`n_ubatch`/线程数可在界面改。

## 测量什么

| 项 | 来源 | 说明 |
|---|---|---|
| 加载 | wall 时钟 | 从 `loadModel` 到可推理，含 wasm 初始化与上下文创建；下载走 wllama 缓存，二次加载基本免费。加载时的 n_ctx/n_batch/线程快照随模型信息入报告 |
| prefill | llama.cpp `timings.prompt_ms` | 每档位一遍校准探针 + N 遍重复；`usage.prompt_tokens` 记实测 token 数 |
| decode | llama.cpp `timings.predicted_ms` | 最大档位输入 + 固定生成长度；另有 chat 模板对照一行（模板处理开销） |
| 4 秒实测 | wall 时钟 | 勾选后每个档位组合跑一次**完整调用**（实际输入 + 实际生成 N token），按 wall ≤4000ms 判 ✓/✗——达标以此为准，页面上的外推投影只是参考 |
| 中断 | wall + `AbortSignal` | 每套件两次：200ms 短引信（预期落在输入处理）与实测 prefill+400ms（预期落在生成）；记录分类（按计划取消/提前完成/上下文超限/失败）、所在阶段、取消前回调块数与字符数、停机延迟；上下文超限会写明错误并自动缩小重试 |
| 内存 | `performance.memory`（JS 堆）+ `measureUserAgentSpecificMemory`（浏览器报告的**页面内存估算**——该 API 允许估算与不完整计量，breakdown 分类不等于物理归属，勿据此断定 KV cache 占比） | 加载后/套件后/卸载后三个检查点；精确值不可用时只记 JS 堆，**不能据此下 8GB 适配结论** |
| 卸载 | wall 时钟 | `exit()` 的耗时，供动态加载/卸载决策用 |

wall 时钟与 llama.cpp 计时**分开记录**：前者含分词、采样、worker 往返（llama-bench 不含这些，见其 README），后者可与 llama-bench 的 pp/tg 粗对量级。

**报告结构**：导出 JSON 为 `{environment, model, suites[], exportedAt}`。`model` 含加载参数快照，**卸载后保留**；每个套件独立记录（含开始时的配置与模型快照），多次运行互不清空；"停止"按钮会真正中断在执行的推理（用户取消在记录中单独标注）。

## 档位与提示词

总输入 512/1024/2048 × 记忆注入 256/512/1024（注入必须小于总数，无效组合自动跳过）。合成提示词按真实 PromptBuilder 的段落形状拼装（战役上下文 → 状态头 → 记忆注入 → 对话历史 → 玩家行动，规则段在对话前）。**预算是硬上限不是下限**：名义档位小于固定段骨架时，各段按比例裁剪到下限，小档位实测的就是小提示词。

wllama 不暴露分词器，档位只能逼近：第一遍 prefill 用 `usage.prompt_tokens` 校准"字符/token 比"，**校准结果贯通整个套件**（decode/4 秒实测/中断测试用同一比例）。每行的实测 token 数是权威值。每个套件有独立纪元混入 nonce：同一档位跨套件的提示词不同（防 KV 前缀缓存污染，备注列的"缓存命中"应为空），套件内同样互不相同。

## 目标设备复测清单（4 核 CPU / 8GB 设备）

背景：2026-10-08 在开发机 IAB（**单线程**，无跨源隔离）测得 Qwen3-0.6B Q4_K_M 真实中文提示词的**唯一实测点**：366 tok prefill 耗时 62.1s（5.9 tok/s）。由此外推 512 tok 输入处理约 86.8s——**这是外推值，不是实测**。生成速度（decode）当时未测；完整叙事耗时、输入解析耗时、线程倍率全部是待测假设，llama.cpp 官方对输入处理与文本生成分开计量，线程对两者的收益不同，不能用单一倍率代替复测。

步骤：

1. 拷贝到目标设备：本仓库（或至少 `frontend/`）+ `frontend/public/models/Qwen3-0.6B-Q4_K_M.gguf`（397MB，unsloth 源也可现场重下：`https://huggingface.co/unsloth/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q4_K_M.gguf`）。
2. 目标设备上：`cd frontend && npm ci && npm run dev`（Node 20+），用**正式 Chrome/Edge** 打开 `http://localhost:3000/benchmark`。
3. 核对环境面板：**跨源隔离必须是"是"**（真实 Chrome 会遵守 COOP/COEP → 多线程可用），wasm 线程检测"支持"且与实际线程数交叉核对一致。
4. 配置：模型 URL 填 `/models/Qwen3-0.6B-Q4_K_M.gguf`；n_ctx 4096；线程填 **4**；生成长度 128；prefill 遍数 1；勾选 **4 秒实测**、4s 生成 token **512**。
5. 跑完整套件（时长未知——单线程下仅 prefill 矩阵就要 30 分钟以上，多线程待实测；4 秒实测阶段最慢），**导出并保存原始 JSON**。
6. 记录并带回：CPU 型号、实际线程数（getNumThreads 的实测值，不是硬件并发数）、实测输入/输出 token 数、各档位 prefill 与 decode tok/s（分开看，不互相折算）、4 秒实测 ✓/✗ 与 wall、两个中断测试的阶段落点与停机延迟、内存检查点（跨源隔离下应出现**全页精确值**，含 WASM 分类）。

判定标准（复测前定死，防事后挪门柱）：**验收线保持 4 秒**——任何档位的完整负载（实际输入 + 实际生成 512 token）wall ≤ 4000ms 记该设备、模型、配置达标；超过即记未达标，**不得据此推断整个 CPU 方案不可行，也不得推断其他组件不能达标**——那需要每个组件类别各自的实测。12 秒只是"停止继续拉档位"的操作阈值（避免在注定超标的组合上烧时间），不是可行性结论。时间要求是否修订，在多设备实测数据齐之前不动。

## 对照实验记录（2026-10-08，i7-13700H，Qwen3-0.6B-Q4_K_M，4 线程，n_ctx 4096）

原始数据在 `artifacts/benchmark/`（native-*.json 为 llama-bench b11364 输出，target-retest-*.json 为浏览器套件导出）。

**原生 llama.cpp CPU 对照**（同构建 b11364/46ca246、同模型、同 -t 4、-b 2048 -ub 512，llama-bench 官方分开计量）：
- 纯输入处理：185.8 tok/s（2048 tok）～ 263.0 tok/s（366/512 tok）。
- 纯文本生成：43.9 tok/s（512 tok）～ 48.3 tok/s（128 tok）。
- 对照浏览器（Edge/WASM）：pp 10.1–15.5 tok/s、tg 1.5–3.4 tok/s → **浏览器运行时开销约 12–29×**，pp 与 tg 两个量级各自独立成立。

**取消停机延迟的粒度对照**（512/256 档，366 tok 提示词，200ms 引信取消）：

| n_batch | n_ubatch | prefill tok/s | 输入处理阶段停机延迟 |
|---|---|---|---|
| 2048 | 512 | 9.6 | 34.4s |
| 2048 | 64 | 13.1 | 33.8s |
| 128 | 64 | 13.2 | **7.7s** |

结论：停机延迟跟随 **n_batch**（366 tok 在 batch 2048 下是单批），不跟随 n_ubatch——"等当前 ubatch"假说被对照组证伪。降 batch/ubatch 到 128/64 后停机延迟降至一个 batch 时长，且 prefill 吞吐不降反升（小模型上小 ubatch 更优）。机制层面（worker 何时检查取消标志）仍未直接观测，只确立了参数相关性与操作方法：**需要快速取消时用小 n_batch**。

## 已知事项

- **合成提示词的规则段是占位填充文本**（"规则0/规则1…"，不是真实风格规则）。4 秒实测行虽然随记录保存实际提示词与生成全文（证据保全），但据此做风格/质量结论是无效的——真实规则下的叙事提示词迭代是后续独立步骤。
- **不要在 dev server 运行时执行 `npm run build`**——`.next/` 会被覆盖，dev server 报 manifest ENOENT。重启 dev server 即可恢复。
- wasm/JS 资产由 `scripts/copy-wllama-assets.mjs` 从 node_modules 拷贝（wllama 3.8.1 的 `main` 指向不存在的 `index.js`，webpack 会去解析它的 TS 源码，所以运行时加载 public 下的自包含 bundle 而不是走打包器）。
- 加载后修改 n_ctx/线程不会重配已加载的模型；面板会提示分歧，改动在下次加载生效。
- wasm 线程检测模块（共享内存 + atomic.load）有单测防回归；环境面板会把检测结果与加载后的实际线程交叉核对。
- Needle 3（调度模型）不在此 harness 范围内；它的浏览器引擎工件是否现成还待确认（见改造方案讨论记录）。
