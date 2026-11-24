# Tasks: goal-micro-models-redesign

- [ ] 1. 定义结构化动作/reaction/fact schema 与四任务的输入输出（短张量：句子 + 候选集）。
- [ ] 2. 手标平衡集（≥300 条/四任务合计），对抗性切分（换名、未见物品、改写/否定/指代、干扰、多行为）。
- [ ] 3. 阶梯训练：0.1M/0.5M/2M/5M MLP/CNN/GRU + fastText + MiniRBT；记录精度/量化/张量形状。
- [ ] 4. 共享编码 harness：encode 一次 + N 头；encode/head/tokenize/tensor/后处理分段计时；长度扫 8/16/32/64/128。
- [ ] 5. 运行时对照：ORT-WASM 单线程 / 多线程+SIMD / WebGPU；与单线程基线比。
- [ ] 6. 真机一轮（有设备才跑；无则记录）。
- [ ] 7. 结论：组合准确率与 60 秒是否成立；更新 D-023/D-030；归档。
