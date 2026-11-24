# Tasks: goal-micro-nlu-collaboration

- [x] 1. 浏览器落盘语义 prompt（run138，20 输入）；抽 20 输入对应的调用样本。
- [x] 2. 四任务标注集（银标）：action 11、targets 41、position 15、results 31；行为分割无独立调用，记为缺；手标未做。
- [ ] 3. 规模阶梯训练：<1M 完成（0.52M，CV 32/41、action 常量）；10M MiniRBT 完成（CV 30/41，浏览器 196.4 ms）；100M MacBERT 训练中；0.6B 基线单次耗时已记录（桌面 2.37 s / 移动 7.73 s）。
- [ ] 4. 浏览器 harness：<1M 头已测（p50 0.10 ms / p95 0.20 ms）；10M/100M 待测。
- [ ] 5. 真机手机一轮（Chrome/Android）；对比模拟档。
- [ ] 6. 结论：哪些任务可换头、混合流水线是否可能进 60 秒；更新 D-023/D-030，提交证据。
