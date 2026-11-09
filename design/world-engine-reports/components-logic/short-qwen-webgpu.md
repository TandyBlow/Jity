# Qwen 短语义与实际 WebGPU 验证

用户最新要求自然语言组件停用燃灯。本分支选择 **Qwen3-0.6B 非思考模式**；`LocalSemanticProvider` 已拒绝旧生成器加载，`MixedSemanticProvider` 的文本路线只有显式登记的 Qwen WebGPU 后端，没有燃灯或固定句子回退。MiniRBT 判别、引用和数值头继续分别登记。

选择依据是可核验的部署链，不是尚未成立的语义优胜：网易伏羲 [Yuyan-700M](https://huggingface.co/FUXI/yuyan-700m) 公开发布 Fairseq 权重，未核实可直接运行的浏览器包；[Qwen3-0.6B](https://huggingface.co/Qwen/Qwen3-0.6B) 有运行时维护方的 [ONNX 转换包](https://huggingface.co/onnx-community/Qwen3-0.6B-ONNX) 和 WebGPU 路线。

## 身份和分工

- 原厂训练来源：`Qwen/Qwen3-0.6B@c1899de289a04d12100db370d81485cdf75e47ca`，Apache-2.0，原始权重、分词和配置逐文件 SHA 登记。
- 浏览器基座转换包：`onnx-community/Qwen3-0.6B-ONNX@58ca03a5e7b354b480b1a82b34bde8dc7b854cc0`，q4f16。这是运行时维护方转换，不冒称 Qwen 原厂浏览器发布。
- 浏览器运行时固定 Transformers.js 3.8.1，真正打包的 ESM 使用固定 esbuild 0.25.5，锁文件、输入和输出哈希均保留。
- 训练与推理共享 `short_qwen_codec.py`：r5 浏览器证据使用 v2，后续 D08 修复已升级 v3，明确绑定 `timeChoice` 的既定单位/边界。新批需使用 v3 分词对照，不借用旧 v2 的通过结论。两个版本均保留完整 JSON 语境、明确组件指令、`enable_thinking=False`。自然名称与 `[[实体ID]]` 格式分别说明；后者仍没有独立训练覆盖，也没有晋升默认。
- 覆盖 12 个自然语言任务，以及 D08 两个时间数值文本任务，共 14 个生成任务。模型原文仅经过 EOS、输入身份和短输出契约核验，不被程序改写成“正确答案”。
- `require_trained=True` 是默认路线：任务需有真实训练登记、非零步数和相符数据身份。基座部署探针必须显式关闭此要求，仍标 `base_zero_shot`，不变成任务能力声明。

新权重与运行依赖使用任务专属的非云端本机缓存。Documents 中的旧来源和失败证据保留。曾遇到 macOS 的 `dataless` 占位读取延迟，完整读取与哈希验证后恢复；没有据此宣称 Git 数据物理损坏，也未修改全局云端设置。

## 已观察的首次失败

| 批次 | 实际观察 | 完成边界 |
|---|---|---|
| tokenizer probe v2 | 直接使用 npm 分发文件遇到未解析的 `onnxruntime-common`；改成完整本地 ESM 打包 | 无 GPU 模型生成；原错误保留 |
| WebGPU base r2 | 文本专测的 A 来源检查条件未同步，执行前拒绝 | 0 模型调用，14 未启动；修复后新批次 |
| WebGPU base r3 | 四份完整输入逐 token 一致；取得 Apple Metal 3 非软件回退适配器；禁止 CPU 节点使 ONNX session 拒绝创建 | 0 生成，14 未启动；实际墙钟 63.595 秒 |
| WebGPU base r4 | 混合执行配置通过前述限制，但“自建设备等于 ORT 模型设备”的校验失败 | 0 生成，14 未启动；实际墙钟 44.766 秒 |

固定 ORT 实现实际接收 adapter，然后自行创建并发布 device。修订版验证的是 **ORT 实际使用的 adapter/device**；先前的探针设备不能替代这个证据。代码修复和工程测试不等于真实模型运行已经通过，后续必须重新冻结并实测。

## GPU 证据和成本边界

执行策略明确允许 ORT 必要的 CPU 节点，不能据 `device='webgpu'` 声称全部算子在 GPU 上。每次真实生成必须记录本请求的 `MatMulNBits` GPU 正时间证据，缺失时保持未完成；分词和传输使用 CPU，CPU 节点数量和耗时比例未测时记未知。

证据来自固定运行时的 [WebGPU profiling](https://onnxruntime.ai/docs/api/js/interfaces/Env.WebGpuFlags.html) 与 [profiling 数据](https://onnxruntime.ai/docs/api/js/interfaces/Env.WebGpuProfilingDataV1.html)。要求真实设备支持 `shader-f16` 和 `timestamp-query`，生成前后排空同一设备队列，完整内核事件写日志；记录窗口与请求、版本绑定，旧 Worker 和迟到事件不能释放新门槛。

GPU 时间、生成调用墙钟、加载、浏览器附着等待、程序和日志开销分开登记。profiling 与排空开销包含在该实验墙钟中。Python RSS 监测不能冒称浏览器 GPU 或整个浏览器的峰值内存；未测部分保留未知。

训练原厂模型与训练后模型的同配置 MPS 比较，和浏览器转换包的部署比较，是两种范围。不同转换来源、量化路径或模型身份不能直接归因于训练。D 后端的局部测量仍缺正式 A/B 服务、真实 C、ready 等待和完整关联段/自动后续，**不能签完整请求 500 毫秒通过**。

训练及资源失败详见 [Qwen 训练记录](short-qwen-training.md)，基座初审见 [r2 初审](short-qwen-baseline-review-r2.md)，全部 D01—D08 契约及已接入范围见 [总交付](short-results.md)。

## base r5：首次真实 WebGPU 生成及完整对账

`qwen-webgpu-base-20261109-r5` 已按冻结的 14 项文本工作负载执行，零重试、零未启动。它是显式 `base_zero_shot` 部署诊断，没有使用本任务微调权重，也不是 D02→D06 或完整游戏请求。实际 ORT device/adapter 引用校验均通过：Apple `metal-3`、`isFallbackAdapter=false`，启用 `shader-f16` 和 `timestamp-query`，14 项使用同一个已核设备 session。四项分词对照逐 token 相符。

流式独立核对结果见 [技术审计](../../../artifacts/world-components-logic/qwen-short/webgpu-base-r5.technical-audit.json)：两个 append-only 日志的计划身份、逐行 SHA 链、顺序和完整结尾均通过；全部 14 个完整输入与冻结数据相等，token 进度与最终 token 一致，均由模型生成终止 EOS。全部 **2,167 个批次、138,328 条 GPU kernel** 原始记录与各请求 summary 对账，每个请求都有正时长 `MatMulNBits`，没有拿未归属的加载 kernel 替代请求证据。

浏览器输出层是 14 个 result；组件层是 **13 个 result、1 个 incomplete**。U5.2 的 Worker 完整执行约 69.925 秒，超过冻结的组件 60 秒预算，上层以 `case_deadline_late_primitive_output` 拒绝采用；迟到原文、token、GPU trace 仍完整保留。不能把 14 个浏览器 EOS 升格成 14 个组件按时完成。

实际监督墙钟 **316.269 秒**，其中浏览器附着、加载及 ready 共 **61.613 秒**；模型初始化本身 **3.230 秒**。14 个 case 墙钟合计 **249.270 秒**，中位 **9.431 秒**，范围 **0.969—70.017 秒**。14 次完整 `generate` 合计 **242.615 秒**；profiling 观察到的 GPU kernel 时间累计 **102.716 秒**。该累计数带有 profiling 对调度的影响，不能称为无追踪的“纯算力”，也不能把剩余时间全部归给 CPU 节点。

r5 的 case 字段测到模型调用和调用内证据记录；末尾结果日志/快照的 `resultJournalMs=0`、`snapshotEndMs=0` 是旧实现未分项测量的占位，不能解释为写盘没有成本。监督总墙钟实际包含它们。新的 profiling 比较分别实际测量这些开销，原 r5 记录不回写。

监督器所见 Python 子进程峰值 RSS **312.45 MiB**；浏览器进程和 GPU 峰值内存未测。浏览器 raw 为 **60,577,792 字节 / 5,396 事件**，case journal 为 **118,408,485 字节 / 5,027 事件**。同一个 kernel batch 当前保存为全局原件和 case 的包装/原子事件，重复日志及逐行 fsync 是可测量的后续热点，原始记录本批保持不变。全部局部 case 已超过 500 ms；正式服务、C、ready 等缺失成本不为零，整请求目标仍未测。

## r5 的 14 条语义初审

以下逐项读取了冻结完整输入和实际原文，按组件职责判断，**不使用 exact-match 作为语义裁决**。独立助手初审为 9 条明确不符、2 条局部满足、1 条需复核、2 条受输入契约缺陷限制；人工审查和来源核验仍为 0。U5.2 的语义判断只审保留原文，不改变其未完成状态。[完整逐条初审](../../../artifacts/world-components-logic/qwen-short/webgpu-base-r5.assistant-review.json) 保留输入哈希、原文及理由。

| 组件 | 实际输出或要点 | 初审 |
|---|---|---|
| D01.3 | 宋黎站在工作台面、持手柄、神情专注 | 不符：`entityId` 是控制室，却描述人物和动作，并添加未给状态。 |
| D01.5 | 宋黎需要确保闸保持关闭 | 不符：任务目标不是行动偏好。 |
| U2.2 | 宋黎和易安尝试插销、未完全插入、手柄卡阻 | 不符：要求 tool 的局部外貌；输出经过，并把向外扳手柄的易安改为共同插销。 |
| U4.2 | 将闸门手柄完全向外扳开 | 不符：给 a 新子任务却采用 b 的相反目标，违背 a 的保持关闭父任务。 |
| U5.2 | “Jity 的行动偏好”调整为确认任务 | 不符且超时未采纳：目标人物是 off/任澈，输出错主体并重述当前任务。 |
| D01.1.name | 防潮闸 | 需复核：要求地点，brief 明确地点为控制室/检修道；装置名称能否作地点借称尚不充分，不能仅因不同于草稿判错。 |
| D01.1.slot_label | 防潮闸控制室 | 不符：重复整个容器名称，没有给局部槽位。 |
| D01.4.goal | 目标：确保控制室中的闸门保持关闭 | 局部满足目标职责；不证明初始化整体。 |
| D02.2.text | 让防潮闸保持关闭 | 不符：只有目的，没有具体下一条尝试。 |
| D04.1.text | 宋黎插销但未能成功 | 不符：指定反应人物是 b/易安；错绑 a，还提前断言结果，没有形成反应约束。 |
| D05.3.text | 宋黎成功将销插入 | 不符：输入联合判断为 partial / not_achieved，输出将部分达成改为成功。 |
| D07.1.text | 拟行动：检查锁紧销卡住的原因 | 局部满足：符合正式新状态中的 pending 子任务；不证明可能性/关联性及自动后续轮。 |
| D08.1.amount | 0 | 输入契约缺陷：未提供先选定的时间单位和边界，不能仅凭草稿 1 判定 0 的时间语义。 |
| D08.2.time.amount | 0 | 同上；只有 normal 段类型不等于完整时间量纲，需要修复输入后独立复测。 |

## profiling 成本的下一次独立对照

固定 ORT `onRunStart()` 每次实际 session run 都重新执行 `setQueryType()`；在空闲、实际设备 queue 排空后把 `env.webgpu.profiling.mode` 从 `default` 改为 `off`，并固定 `env.trace=false` / `env.wasm.trace=false`，源码上可让下一次 run 使用 `queryType='none'`，无需更换权重或 session。`at-passes` 模式会每次 dispatch 结束 compute pass；关闭追踪可能改变调度本身，不能只减去日志耗时来估计。

后续必须先冻结同模型、同设备 session、相同完整输入、解码和固定交叉次序的 on/off 工作负载，再保留全部首次输出、EOS、数值/文本差异、完整墙钟及热/冷状态。默认审计模式仍要求每请求 kernel 证据；off 对照只报告实际 device/session 和先前同 session 校准证据，明确“本请求未测 kernel”，不能沿用 on 的通过标记或冒称整模型无 CPU 节点。模型、设备、精度、输入或实现身份改变后，旧校准不自动有效。

现已实现显式比较接口和共享监督入口 [profile_comparison.py](../../../experiments/world-components-logic/short_webgpu/profile_comparison.py)，尚未执行 GPU 比较。两份完整输入与八槽顺序在 [v2 工作负载登记](../../../artifacts/world-components-logic/qwen-short/profiling-comparison-workloads-v2.json) 保存，SHA `8635e89deef0ca3a6d1fcf8c5104c5189f2d738e3296c12f281592236fb85454`；输入预算与其余新实验一致为 8192，不截断。原 v1 的 32768 预算已明确登记为执行前撤换，原件保留、0 模型调用。每个输入固定 on/off/on/off；此顺序不是平衡实验，第一项的冷编译等条件必须单列。最终训练后模型、v3 codec/分词及运行代码仍需另行冻结，不能把这份工作负载登记冒充资产已齐或性能已测。


## 训练后 export r1：数值门失败与登记隔离

`qwen-short-time-export-20261109-r1` 已生成 ONNX 文件，但其浮点导出验证超过预注册的 atol=1e-4（日志最大绝对差约 8.597e-4）。Optimum 的 `main_export(do_validation=True)` 捕获 `AtolError` 后只输出 warning，旧包装据返回结果写下 `diagnostic_completed`，该状态不能作为数值验证通过证据。原始计划、记录、警告及模型字节保留，严格验证修复使用新的批次身份；没有放宽阈值。

两份提前登记的浏览器模型/provider manifest 已保持字节移至 [隔离索引](../../../artifacts/world-components-logic/qwen-short/quarantine-export-r1/index.json)，状态为 `quarantined_not_qualified`。它们没有被用于训练后 WebGPU 生成，也没有启动依赖评估。旧登记文件的存在不再赋予使用资格。

接入端现在要求训练后资产提供 `jity-qwen-onnx-strict-validation-v1` 证明，并核其原件 SHA、实际导出/源训练计划、codec、完整最终资源身份和全部输出检查；缺失、失败、输出遗漏、放宽阈值或陈旧资产均拒绝。实际旧 r1 派生登记已被 `trained_model_missing_strict_validation` 拦截。证明范围为 `float_export_numerical`，不替代最终 q4f16 的数值、真实浏览器输出或任务语义验证。登记、provider 身份与实际请求都保留这一门槛，四页 GPU 实现没有因此改变。


训练后严格数值门未通过时，profiling 入口允许另行冻结显式 `base_zero_shot_diagnostic`：仅使用固定、零训练步的社区基座，绑定失败导出证据，明确不提供训练效果证据。默认仍要求训练后严格证明；该例外不放行失败的训练权重，也不改变同输入 off 校准或完整计时规则。是否运行及结果须读取后续新计划和原始记录。


## base profiling r1：8 槽真实对照与证据归档

`qwen-webgpu-base-profile-20261109-r1` 使用固定社区基座、v3 codec，在同一 Apple `metal-3` 非 fallback 的实际 ORT device/session 完成 8/8 槽，0 重试、0 未启动、8 次均完整 EOS。它明确为 `base_zero_shot_diagnostic`，绑定训练后 export r4 的严格失败记录，不代表微调权重效果。两份输入均来自已经暴露过的 development `gate` 场景，四次重复测量不是四个独立语义样本。[封存摘要](../../../artifacts/world-components-logic/qwen-short/qwen-webgpu-base-profile-20261109-r1.summary.json)

逐行复核完整双日志的 SHA 链、计划身份和顺序，全部请求的完整输入、消息及 token 进度与最终输出相符，4 项 tokenizer 对照逐 token 通过。四次 on 的 **354 个批次、22,608 条 GPU kernel** 全数对账，均有本请求的正时长 `MatMulNBits`。四次 off 没有 kernel 观测，其 `perRequestGpuProof=false`，GPU 时长和 CPU 算子成本为未知；每次校准引用均核到同一输入、设备 session、身份和预算的前一次 on 原始记录。各请求的模型、runtime、四页代码与模式策略 SHA 也与冻结配置一致。[技术对账](../../../artifacts/world-components-logic/qwen-short/webgpu-base-profile-r1.technical-audit.json)、[身份补充核对](../../../artifacts/world-components-logic/qwen-short/webgpu-base-profile-r1.identity-audit.json)

| 完整工作负载 | 顺序 | case 墙钟 ms | 完整 generate ms | on 观测 GPU kernel ms |
|---|---|---:|---:|---:|
| D01.1.slot_label，196 输入 / 6 输出 token | on 1 | 1,258.728 | 898.460 | 572.850 |
| 同一短输入 | off 2 | 616.272 | 589.415 | 未测 |
| 同一短输入 | on 3 | 1,057.972 | 656.535 | 559.284 |
| 同一短输入 | off 4 | 602.550 | 540.820 | 未测 |
| U4.2，3,128 输入 / 13 输出 token | on 1 | 60,919.520 | 60,571.610 | 21,327.184 |
| 同一长输入 | off 2 | 85,911.424 | 85,834.445 | 未测 |
| 同一长输入 | on 3 | 86,069.738 | 85,788.595 | 22,650.225 |
| 同一长输入 | off 4 | 46,580.278 | 46,465.440 | 未测 |

8 个 case 墙钟合计 **283.016 秒**，包括实测结果日志、快照和 settled 遥测写入；完整 generate 合计 **281.345 秒**。监督总墙钟 **324.661 秒**，含附着、加载和 ready 阶段 **40.498 秒**，其中实际模型初始化 **3.232 秒**。模型只加载一次，各 case 的 `coldLoad=false`；第一短输入是加载后首次生成，长输入首次遇到另一种形状，着色器编译成本没有独立测量。Python 进程峰值 **43.328 MiB**，浏览器及 GPU 峰值未测。on 的 kernel 累计 **45.110 秒**不是无追踪纯算力，也不能据差额推算 CPU 算子时间。

短输入的 off 观测更快；长输入第一对 off 更慢、第二对 off 更快，未形成可归因于单一开关的稳定收益。次序固定为 on/off/on/off，没有平衡随机化；profiling 本身改变 compute-pass 边界。实验前虽恢复了本地文件保留，后台 iCloud 传输仍可能进行；系统并非受控空闲或恒温环境，温度和调度干扰没有测量。不能把上述差值称为纯日志开销，不能挑选最后 46.58 秒为通用性能结论；本轮没有据此实现或启用 session_calibrated。

同一输入的四次原文和 token 完全相同，但未比较 logits 数值。8 次技术 result 中，两类语义错误各重复四次：D01.1.slot_label 输出“防潮闸控制室”，重复整个容器名称而非局部槽位；U4.2 输出“- 将闸门手柄完全向外扳开。”，把人物 b 的开闸目标给了要求保持关闭的 a-task。独立助手按完整输入与组件职责判为 **2/2 独立输入不符、8/8 测量不符**，不是 exact-match 判分，人工复核/来源核验仍待完成。[逐条语义初审](../../../artifacts/world-components-logic/qwen-short/webgpu-base-profile-r1.assistant-review.json)

原 record、case journal、browser raw 和 process log 共 **32,082,292 字节**，全部保留；新增 gzip 共 **1,609,056 字节**，逐项解压 SHA 与原字节相同。只提交小索引，raw/压缩 raw 不入 Git。[无损存档索引](../../../artifacts/world-components-logic/qwen-short/qwen-webgpu-base-profile-20261109-r1.raw-archive.json)。运行完成依据 record 和双日志封存，不能把随后服务关闭的界面断连提示当模型失败或成功证据。所有局部 case 均超过 500 ms，正式 A/B、C 和 ready 的完整请求范围仍未测。
