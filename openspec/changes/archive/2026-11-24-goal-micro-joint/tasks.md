# Tasks: goal-micro-joint

- [x] 1. 批次切分与 test.json（v5，15/任务，测试标签全部在训练中出现）。
- [x] 2. 训练 T1 固定顺序、T2 打乱、T3 打乱 + 32 截断（40 epoch）。
- [x] 3. 评估：自然、截断 8/16/32/64/128、position 压缩输入（T2 natural 46/60）。
- [x] 4. 速度矩阵：T2 fp32/int8 × 5 长度 × 1/4 线程（32 token int8 4.57–7.83 ms）。
- [x] 5. 结论写 `artifacts/goal/micro-joint/conclusion-20261124.md`，D-030 已更新。
