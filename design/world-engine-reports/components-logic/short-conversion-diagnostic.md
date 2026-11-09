# Qwen 转换定位与隔离行为诊断

本轮只处理转换阻塞。扩大训练、角色绑定修复、行动句式修复和整链实验暂停。`act/skip`、成员结果、U1–U6、A/B/C 公共边界没有修改。

## 对照协议

`short_qwen_diagnostic.py` 的原始定位批次 `conversion-localization-20261109-r5` 在观察新结果前固定了六个完整 development 输入：D01.1.name、D02.2.text、D04.1.text、D05.3.text、U4.2、D08.1.amount。输入为 213–3128 token，均不裁剪。它们来自同一个 gate 来源组，属于定位探针，不是独立泛化验收。当前监督数据没有 references 表示的 D02 文本例，因此不把本批写成专门的引用标记语法验收；人物、物品及任务归属仍逐项审查。

四段比较及额外控制分别记账：

1. 原始 r5 adapter＋原始基座 与 已保存合并模型：MPS、BF16、SDPA 保持一致；适配参数保持训练时 FP32。
2. 合并 PyTorch CPU FP32 eager 与 FP32 ONNX。另列 BF16/MPS→FP32/CPU 的精度和设备控制，不把它混入导出误差。逐层另比较原生与导出补丁 PyTorch，检查补丁影响。
3. 同一 FP32 图 与 本次生成的 q4f16 图：量化块 32、对称量化、保持 FP32 输入输出，CPU ORT 对照。量化前后不同阈值需求不能由当前最大误差反推。
4. 同一 q4f16 文件 CPU ORT 与 浏览器 ORT WebGPU。绑定文件 SHA、完整 tokens、掩码、positions、全部 KV 输入指纹、运行时和生成设置；实际 GPU 权重 kernel 证据与混合 CPU 节点未知项同时保存。

基座使用原始同款 Qwen3-0.6B 的固定 revision，经同一个导出、量化和输入流程，不能用社区已有 ONNX 替代这项控制。

固定 token 模式对每端强制相同草稿目标前缀，最多 16 个后续 token，记录每步 logits 全词表和各自缓存身份。自由生成使用 greedy、单束、无重复惩罚、最多 128 token，保留首发原文、EOS 或截断。固定模式可经过 EOS，因为其用途是数值探针；不把它的 EOS 计为自由生成正常结束。

逐层定位暴露现有 FP32 图的嵌入、各层 norm、Q/K/V、Q/K norm、attention 输出投影、MLP 和 residual 输出；不改算子或权重。分别跑本批冻结的随机张量、完整行动 prefill，以及由同一 PyTorch prefill 缓存构成的 cached decode。保存原图与暴露中间量图的输出对照，避免观测改变优化路径而误判。首次超限是“所观测模块边界”的定位，不自行断言唯一出错算子。

## 已定位的两类差异

FP32 导出与 q4f16 浏览器异常分开解释。基座和训练模型分别跑逐层原生／导出补丁、原图／观测图、完整 D02 prefill 与共享同一缓存的 decode。原生与导出补丁、原图与观测图都完全一致；共享缓存 decode 的 338 个模块边界均未超旧阈值。完整 prefill 的首个超限分别在基座第 3 层 k_norm、训练模型第 7 层 k_norm（代码下标 2、6），不能把最后一层最大误差当成原因。

对归一化算子继续拆解，基座首个非零差异出现在 ReduceMean；旧 r4 精确输入下为 1.7462298274040222e-10，随后经过倒平方根和乘法传播。实际因果掩码逐元素相同，旋转位置的 sin/cos 有约 5.96e-8 的浮点差异。外部 tokens、mask、positions、KV 张量身份均保存。`trace/historical_random` 是早期命名，实际指本批随机张量；它与旧 r4 的 attention_mask 不同，不能直接用两批失败计数判断修复。`controls/old_export_r4` 单独重放旧 r4 原始 NPZ，不混用。

真实 WebGPU 原始批的 6 项自由生成中，4 项达到 128 token 上限而未 EOS，2 项立即空输出。第一步 CPU／WebGPU 的完整输入与空缓存完全一致，logits 最大差达到 21.79296875，首选 token 已改变，发生在任何缓存累积之前。

进一步暴露首层及全模型 792 个算子输出：嵌入完全一致；在代码下标 3 的 input_layernorm，输入含 7752 左右的激活，FP16 平方超过 65504 而成为 inf。CPU 所记录的均值仍为有限数，WebGPU 的均值为 inf、倒平方根为 0，导致该 token 的归一化整行归零，并沿后续层放大。CPU 内部精度／转换消除使这类错误不能由本地能生成中文来排除。暴露输出会影响运行时优化，观测图的最终 logits 与原图并非逐比特相同；它用于定位机制，正式行为证据仍来自未插探针的原图。

修复候选保留每个完整 RMSNorm 与 RoPE 子图的连续 FP32 计算，仅在与 FP16 计算的外部边界转换。单纯逐算子 block list 会插入 FP32→FP16→FP32，仍在平方与均值之间溢出，不能视为修复。`short_qwen_precision.py` 只连接受保护算子之间的 FP32 边，保留其他边界转换；有包含 7752 输入、真实四位 MatMul 和运行时加载的数值回归测试。新候选以 `conversion-precision-20261109-r4` 身份验证，未改变旧数值阈值。其前序 r1 类型错误、r2/r3 加载失败及无效逐算子方案原件均保留。

## 隔离与证据

专用资产 schema 为 `jity-qwen-unqualified-diagnostic-assets-v1`，不是正常 model manifest。页面始终显示 **转换未合格**；独立 loopback 服务只接收数值与原始文本，不创建 `WebGPUProvider`，不返回 `Completion`，没有 D 编排或状态写入路由。正常 `verified_manifest` 入口继续拒绝诊断资产；原严格证明检查未放宽。活动选择的 `browserProvider` 继续为 null。

原 atol=1e-4、rtol=1e-5 保留。执行完成、数值通过、行为无退化、模型语义合格、生产准入是不同结论。旧 export-r1/r2/r3/r4 原件不改；新方案也不能追认旧批次。新增关键语义错误容许数预登记为 0，必须检查正常结束、实体／任务归属、行动覆盖、约束与事实方向；未审项不算通过。

大模型、NPZ 全词表、逐层输入和完整日志留在隔离 cache。小型交付索引绑定它们的真实 SHA，不把大文件提交到 Git。运行产物根目录：`~/.cache/jity-d-short-semantics-20261109/qwen/conversion-diagnostics/conversion-localization-20261109-r5/`。

## 运行入口

在 D 工作树使用原隔离 Qwen Python 环境：

```text
short_qwen_diagnostic.py freeze --run-id <新身份> --model <已训源模型清单>
short_qwen_diagnostic.py convert <plan.json> --kind base|trained
short_qwen_diagnostic.py run <plan.json> --engine <固定引擎名称>
short_qwen_diagnostic.py trace <plan.json> --kind base|trained
node short_webgpu/diagnostic_bundle.mjs <固定 runtime-r2 依赖目录> <新批目录/ort.mjs>
short_qwen_diagnostic_browser.py <plan.json>
short_qwen_diagnostic.py compare <plan.json>
```

先完成基座控制，再运行训练模型。`trace` 的 shared-cache 探针依赖对应 `base_fp32` 或 `merged_fp32` 运行保存的缓存。打开专用服务打印的本机 URL，点击开始，才加载模型；诊断页面没有正式准入按钮。所有重跑使用新身份，保留首发失败。

## 判据依据

[PyTorch 数值精度说明](https://docs.pytorch.org/docs/stable/notes/numerical_accuracy.html)说明数学等价的浮点运算不保证逐比特一致；这不能证明某次具体差异无害。[ORT 量化诊断说明](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html#quantization-debugging)建议比较权重与激活定位精度损失，而非仅凭最终误差大小判断。新容差须在误差机制、基座控制和配对语义证据具备后另立规则与批次；本轮不自动提高门槛。

## 验收边界

不把当前最大误差加一点余量作为新容差。本批六个探针仅来自一个来源组，不足以校准生产容差或证明全域语义正确。原数值门继续判定；修复后的逐对 token、EOS、引用／归属、行动覆盖与关键语义审查另列。后续容差规则需要在独立来源组上预先冻结校准／留出划分，分别约束 FP32 导出和混合精度量化的误差分布、首选 token／margin、固定后续误差增长、正常结束和新增关键错误为零，再用新批次验证。任一未审、未覆盖或失败项都不能被合并为准入通过。
