# Tasks: goal-micro-nlu-collaboration

- [ ] 1. 浏览器落盘语义 prompt（现有 trace 不存 prompt）；抽 20 输入对应的调用样本。
- [ ] 2. 四任务标注集：意图/act-skip、行为分割、实体/目标匹配、位置推断（现有 trace + 手标）。
- [ ] 3. 规模阶梯训练：<1M（fastText/char-CNN/线性头）、10M（MiniRBT-H256）、100M（蒸馏）；0.6B 基线。
- [ ] 4. 浏览器 harness：ORT-WASM 优先，记录 p50/p95 延迟、内存、准确率；笔记本一轮。
- [ ] 5. 真机手机一轮（Chrome/Android）；对比模拟档。
- [ ] 6. 结论：哪些任务可换头、混合流水线是否可能进 60 秒；更新 D-023/D-030，提交证据。
