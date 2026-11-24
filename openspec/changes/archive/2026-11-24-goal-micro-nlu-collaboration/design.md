# Design: goal-micro-nlu-collaboration

## 已核实的事实（2026-11-24）

- delcenjo/browser-runtimes-bench（单机：Ryzen 7 7435HS + RTX 3050 Laptop，Chrome 150，Ubuntu 24.04）：139,712 参数 MLP 在 raw onnxruntime-web WASM 单次 0.10 ms（p95 0.20 ms），WebGPU 4.50 ms（p95 5.31 ms）；MiniLM q8 WASM 12.05 ms、WebGPU 158.10 ms。
- 派发开销推算：WASM 每次约 0.08 ms、WebGPU 约 4.46 ms；小模型在浏览器里优先 WASM。
- TF.js 文档的「小模型 WASM 更快」对比对象是 WebGL，不是 WebGPU；WebGPU 未被该文档比较。
- 手机端：找到的是视觉小模型（Face Detector 21–28 ms WASM 等）与 TTS 声码器数据；**没有** ~10 万参数模型在手机浏览器上的 WASM/WebGPU 实测。
- 引用算术：300 × 0.115 ms = 34.5 ms；「1.5 秒」对应约 5 ms/次（WebGPU 派发量级）。
- 本仓库 MiniRBT-H256（10.4M）浏览器实测：int8 ONNX 10.6 MB，单次 6.6–7.7 ms（桌面 i7-13700H）。
- 待独立复核：TinyBERT（14.5M，GLUE 约 96.8% BERT-Base）、Ultra-Compact NLU（10KB 意图识别）、Needle 2（45M 工具调用）。

## 任务映射（哪些可换头）

| 调用 | 模型在做什么 | 可换头？ | 需要的契约变化 |
|---|---|---|---|
| targets | 闭集多标签 + 指代消解 | 是（cross-encoder 对打分） | 无（输出是 id 集） |
| position | 实体/容器/槽位抽取 | 是（分实体候选打分，512 token 切片） | prompt 需按实体切片 |
| results 判定/归因 | 5 向 + 4 向 + actor/target | 是（分类/抽取头） | fact 正文需模板或保留小生成模型 |
| act/skip | 二分类 | 是 | 无 |
| action/reaction/fact 正文 | 自由文本，且是状态载体 | 否 | 只能小 seq2seq 或结构化记录+模板（语义变更） |
| narration | 生成 | 否 | 保持生成模型 |

## 实验设计

- 四任务：意图/act-skip、行为分割、实体/目标匹配、位置推断；各 0.6B vs 100M vs 10M vs <1M。
- 数据：现有 trace（477 submission、1,394 results、3,042 updates、约 6,000 action / 2,000 targets 结果）转成标签；prompt 需新增落盘；另手标一小组。
- 运行时：ONNX Runtime Web WASM（1 线程）优先；记录单次延迟（p50/p95）、内存、准确率；笔记本 + 真机手机。
- 判定：若 10M 级在四任务上达到可用准确率且单次 ≤10 ms，则混合流水线（头 + 小生成模型）的移动端 60 秒才值得再评估；否则记录证伪。

## 风险

- 错误累积：头与头、头与状态机之间的错误会传播。
- 泛化：20 输入世界上的标签不代表未见世界。
- 数据量：四任务各自的标注规模远小于微调语言模型所需。
- 编码器成本：MiniLM 级编码器单次 12 ms，会吃回一部分收益；<1M 任务头需共享编码器或轻量词表。
