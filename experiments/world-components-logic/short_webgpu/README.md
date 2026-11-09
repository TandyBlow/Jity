# Qwen3 WebGPU 运行后端

此目录仅为 D 实验提供浏览器计算后端；训练、计划冻结、监督与评分继续通过现有 `experiment.py`。它不修改 A/B/C，不提交世界，不生成固定答案，不回退到 Randeng、CPU 模型或远程服务。

当前资源：Transformers.js `3.8.1`，依赖由本目录 `package-lock.json` 锁定；ONNX Runtime Web `1.22.0-dev.20250409-89f8206ba4`。原厂基线为 `onnx-community/Qwen3-0.6B-ONNX@58ca03a5e7b354b480b1a82b34bde8dc7b854cc0`，仅取得 q4f16 ONNX、config、generation config、完整 tokenizer、special tokens、chat template。原模型许可证及来源见 manifest。此基线在 Jity 新任务上没有训练，`qualification=base_zero_shot`，不能写成已训能力。

首次真实浏览器分词探针发现 npm 的 `transformers.web.min.js` 保留 `onnxruntime-common`、`onnxruntime-web` 包名导入，不能直接作为独立浏览器脚本。该失败及旧 `runtime/` 原样保留。当前 `runtime-r2/` 用固定 esbuild `0.25.5` 将锁定依赖打包为独立 browser ESM，拒绝 metafile 中仍有外部导入；新 manifest 登记编译器、lock、全部输入文件与产物 SHA。没有修改原 runtime manifest 或首次失败记录。

本地依赖、模型和生成 manifest 均在 `.local/world-components-logic/webgpu/`。运行 `prepare.py --runtime --model` 只准备资源，不加载模型；新旧字节有差异时拒绝覆盖已登记 manifest。权重下载先按固定提交的 LFS SHA/git blob SHA 校验，再记录 SHA-256。运行时文件及 npm lock 同样绑定身份。原始 `.pt` 或其他量化模型不被自动接受。

Python 接口：

```python
bridge = BrowserBridge(model_manifest, runtime_manifest, checkpoint=journal)
url = bridge.start()  # loopback-only独立端口，URL fragment携带会话token
ready = bridge.wait_ready(120, require_model=True)
provider = WebGPUProvider(bridge, binding=binding, timeout_ms=120000,
                         max_input_tokens=32768, max_new_tokens=128)
provider.checkpoint = journal
# provider(component, full_payload) -> Completion
# provider.identity 为公开完整身份字典；provider.model_identity 为 ModelIdentity。
```

浏览器先“连接实验”，然后“核对分词”（只加载 tokenizer、不创建 GPU 设备），最后在获分配的 GPU 窗口内“加载模型”。固定材料为 `tokenizer-parity-cases-v2.json`；服务器核验 codec 与完整输入并独立比较返回的每个 token，不能只相信浏览器自报通过。连接本身不加载模型。初始化没有模拟文本前向；冷加载及首次真实生成编译成本分别记录，仍计入外层总墙钟。`wait_ready` 只证明分词一致和初始化完成；返回包含 status、connected、workerBound、modelLoaded、tokenizerParityPassed、deviceIdentity、initializationElapsedMs，失败返回 incomplete 与原因。实际 CUA 浏览器测试由协调者进行；Node/Python 测试只用显式工程夹具。

所有自然语言 primitive 共用 `short_qwen_codec.prompt_packet`。完整原始 payload 与 messages 均携带 SHA。Worker 使用冻结 tokenizer 的 chat template，`enable_thinking=false`、无截断、无跨请求 KV 缓存；生成配置为 greedy 单束（独立实验选择，不能把它说成 Qwen 官方推荐最优设置）。输出上限缺 EOS 是 incomplete。只从输出 token 序列移除结构性终止 EOS 后解码正文；保留 `rawTokenIds`、含 EOS 的 `rawDecodedText`、原文空白。正文不 strip、不修 JSON、不补语义。

实际 r3 首次模型初始化在 Apple metal-3 非回落设备通过硬件检查后，被严格 `disable_cpu_ep_fallback='1'` 拒绝：图包含分配给默认 CPU EP 的节点。该批 14 项未开始、生成 0 次，原始失败和配置保持不变。

当前新策略是 `webgpu_preferred_cpu_nodes_allowed_profiled_v1`：仍以 `executionProviders=['webgpu']` 优选 GPU，显式设置 `disable_cpu_ep_fallback='0'` 允许需要的 CPU 节点；要求非回落硬件 adapter、`shader-f16`、`timestamp-query`。混合策略 SHA 同时绑定 provider、请求和响应，不与旧严格批混用。缺 feature、设备丢失或无实际 GPU 权重证据仍返回 incomplete。

使用 [ORT profiling API](https://onnxruntime.ai/docs/api/js/interfaces/Env.WebGpuFlags.html) 的 `mode='default'` 和 `ondata`，保留每个实际 GPU kernel 的类型、节点名、程序名、张量形状及起止 timestamp。固定版本 [backend-webgpu.ts](https://github.com/microsoft/onnxruntime/blob/89f8206ba4/js/web/lib/wasm/jsep/backend-webgpu.ts) 的 `flush()` 通过 GPU query buffer 的 `mapAsync()` 读回并发出这些记录，时间单位是纳秒。每次真实 generate 必须观察到本请求至少一个正时长 `MatMulNBits`（量化权重乘法）记录；只有 `device='webgpu'`、Cast 或普通 MatMul 不足以通过。内存只保留 64 行批缓冲和至多 8 个权重证据，全部原始 kernel 按顺序批量写入日志。证据说明观察到真实 GPU 权重运算，不证明全部权重或全部节点都在 GPU 上。

每次 generate 前后等待该设备的 `queue.onSubmittedWorkDone()`。按 [WebGPU Promise Ordering](https://www.w3.org/TR/webgpu/#promise-ordering)，同队列此前的 `mapAsync()` 在该完成边界之前结束；之后才切换 profile owner。额外检查 GPU timestamp 不早于前次已排空区间，迟到或错误记录拒绝通过。错误生成也保存已有原文、token 和 GPU trace。profile/drain 开销分别记录并包含在完整墙钟中；CPU 节点数量、耗时和比例未测，保持 null/unknown，不能填 0。分词、调度和通信仍由 CPU JavaScript 完成。

固定 ORT `1.22.0-dev.20250409-89f8206ba4` 的实际 JSEP 路径与当前 `onnxruntime-common` 的 device setter 文档不同：[wasm-core-impl.ts](https://github.com/microsoft/onnxruntime/blob/89f8206ba4/js/web/lib/wasm/wasm-core-impl.ts) 读取 `env.webgpu.adapter`，上述 `backend-webgpu.ts` 自行调用该 adapter 的 `requestDevice()`，随后把实际 device 和 adapter 发布为不可配置、不可写的属性。r4 实测因此拒绝了“预建 device 与模型 device 相等”的旧假设；原始 `runtime_device_mismatch_or_lost` 记录保留，14 项未启动、0 次生成，不能计为模型结果。

修复后只预选和登记非 fallback adapter，不再创建独立探针 device。模型加载后读取 ORT 的实际只读 device/adapter，验证其来源和 adapter 对象一致性、设备自身所启用的 feature、可用的 `device.adapterInfo`、设备丢失状态，再使用该实际 device 的队列进行排空。页面及服务端 readiness/结果都要求这个绑定证据；实际模型生成仍必须另有每请求 GPU 权重 kernel 证据。此修复的 Node/Python 检查是工程夹具；需另行冻结和执行浏览器批次验证。

页面在第一次本机接口失败或 10 秒接口超时后结束当前连接、停止轮询并终止 Worker；最近结果独立保留。未获服务端确认的输出明确标为待确认，断连不产生完成结果。不会自动重连或无限覆盖原始错误；新实验需要重新打开其登记 URL。

每请求绑定模型、runtime、页面代码、输入、消息、版本、generation、预算；超时、取消、设备丢失、缺适配器、超上下文、异常和迟到输出全部 incomplete。原始 token 进度先写日志，迟到最终输出仍保存但不采纳。同一桥只接受一个浏览器和一项在途任务。加载与生成都有外层终止期限，无法合作停止的 Worker 被终止；模型加载失败不产生空结果。

完整证据写外层 append-only journal；默认仅保留 128 条环形事件摘要及至多 128 个已结束请求身份，释放原始请求/响应的内存。当前 case 只收到 requestId、generation、binding/input hash 一致的前向事件，旧 case 的迟到原文仍留全局日志，不计入新 case 计算或推进门槛。

内存记录明确区分可读的 JS heap 与未测的 GPU 分配/峰值；标准 WebGPU 的 adapter limits 不是实际使用量。模型磁盘体积同样不能当显存或峰值。

本地微调导出通过 `prepare.register_local(directory, provenance=..., out=新路径)` 登记同格式资源。provenance 必须明确底座、训练步数、任务清单、adapter/合并/导出身份与能力状态；更换权重需新 manifest、桥和浏览器 Worker，不能在旧缓存/版本内热换。训练后的浏览器量化导出需重新验证，旧量化基线成绩不代表新导出。

工程检查：`node --test test_core.mjs` 与 `tests/test_short_webgpu.py`。所有合成响应明确只验证 transport/completion，不能算 Qwen3 能力、浏览器性能或完整 500 毫秒成绩。

## 显式 profiling 对照接口

默认 `BrowserBridge(..., allow_profiling_comparison=False)` 和 `WebGPUProvider(..., profiling_mode='default')` 保持每请求正时长 MatMulNBits 审计。独立性能对照可以显式创建允许比较的 bridge，再让 `profiling_mode='default'` / `'off'` 两个 provider 共用该 bridge。off 仅允许先前成功 on 请求的同完整输入、语境绑定、generation、提示/分词、模型、运行代码、解码预算及同实际设备 session；Python 和 Worker 独立检查。重载 Worker、取消、更换任何绑定均失效。缓存只保留至多 16 份校准身份，不缓存语义答案。

off 用独立 placement policy 身份并写入 `perRequestGpuProof=false`，GPU kernel 数量/时长为 null，明确引用先前校准请求。没有校准或 off 仍意外发出 kernel trace 时返回 incomplete。模式只在请求尚未生成且实际 queue 排空后切换；两个模式都保留完整模型 token、EOS、原文、错误和完整墙钟。默认路径不会自动使用 off。

[profile_comparison.py](profile_comparison.py) 直接复用 `experiment.execute_plan`、`AppendJournal`、`ModelSession` 及代码快照，不创建另一套监督器。已登记的两个工作负载是原 r5 的完整 `D01.1.slot_label` 和 `U4.2` 输入，各固定 on/off/on/off，共八槽，重复测量而非挑答案重试。第一项包含该输入的首次编译/缓存条件，顺序没有平衡，必须保留这种热状态偏差。比较统计逐槽 token/文本、设备、generate 及完整墙钟；这两个工作负载不是数值头，不能声称测得数值头误差。

模型导出和 codec v3 分词材料齐备后，`profile_comparison.py freeze --run-id <new-id> --source-plan <r5-plan> --model-manifest <trained-model-manifest> --runtime-manifest <runtime-manifest> --parity <tokenizer-parity-cases-v3.json> --venv <python>` 冻结实际字节；只接受有这两个任务真实训练登记的资产。随后 `profile_comparison.py execute <new-plan>` 启动公共监督下的独立本地页面；运行日志打印该批 URL，由实际浏览器连接。默认比较资源为单请求 120 秒、附着 180 秒、监督 1200 秒、Python RSS 1024 MiB，不代表浏览器 GPU 内存上限。GPU 窗口仍由协调人分配。

已训练资产还必须携带实际训练来源的 `provenance.codec` 与 `provenance.codecSha256`，分别等于当前 codec 版本和提示源文件字节 SHA。仅步数大于零不能取得新提示接口的训练资格；旧 v2、缺 SHA、同版本改了提示源均拒绝。导出端应从训练计划/代码快照继承这些值，不能在导出时用当前文件替旧训练记录代签。零步基座仍可显式诊断，但其 `trainedComponents` 对外为空，不能声明任务已训练。

训练后资产另需 `provenance.strictValidation`，schema 为 `jity-qwen-onnx-strict-validation-v1`，status 为 `passed`，scope 为 `float_export_numerical`，并指向 `proofPath`/`proofSha256`。登记、桥初始化、provider 身份及请求边界都会检查证明。证明必须绑定实际导出计划、源训练计划、codec、验证过的浮点图，以及当前完整最终资源文件的路径、字节数和 SHA；`expectedOutputNames` 与逐输出 `checks.name` 必须一一覆盖。每项有限值、形状与 allclose 判断均须明确通过，阈值须对应冻结计划且不得宽于 atol=1e-4、rtol=1e-5。最大绝对误差单独保留，不替代包含相对项的 allclose 判据。

该证明仅表示浮点导出数值门通过，不表示最终 q4f16 的数值、浏览器推理或语义质量通过。Optimum 的 `do_validation=True`、训练步数、配置或外层 `diagnostic_completed` 均不能替代它。原 export r1 缺此证明，即使旧登记 manifest 仍存在，也会明确拒绝；原件和首发失败记录不改写。

比较的完整输入上限固定为 8192、输出 128；v1 工作负载登记的 32768 上限已在执行前撤换，原件保留，当前为 v2 登记。结果日志、阶段快照和 settled 日志各自实际计时；完整测量到 settled 日志结束，最终元数据保存仍包含在监督墙钟中，不以固定 0 代替未测开销。


独立 profiling 比较的 `freeze` 默认 `--qualification task_trained`，训练后资产须通过上述严格证据门。若训练后导出尚未合格，可明确选 `--qualification base_zero_shot_diagnostic --trained-export-failure <失败导出记录或更正文件>`；此例外仅接收已经登记的固定社区 Qwen 基座（identity `31fb901fe876af0b3fff2c6a519dd8fe75fab495ccf1875908b2d6a8ac125c81`，0 训练步），不会接收被拒绝的训练后权重。计划/结果绑定失败证据 SHA，并明确 `trainingEffectEvidence=false`、`trainedWeightsExportQualified=false`。其他完整输入、8 槽次序、资源限制、当前请求 GPU 证据要求及同输入 off 校准限制保持不变；尚未执行的比较不能当性能证据。
