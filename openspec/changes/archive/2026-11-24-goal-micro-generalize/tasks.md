# Tasks: goal-micro-generalize

- [x] 1. 构建句对数据与留出切分（position 215 训练对 / 7 测试行，targets 114 / 22；每行 2 个硬负例）。
- [x] 2. 训练 MiniRBT 句对打分，导出 fp32 与 int8（10.55 MB）。
- [x] 3. 浏览器内同输入评估：seen 10/13、8/9；held 7/7、18/22；4t p50 3.83 ms、1t 6.52 ms。
- [x] 4. 结论写 `artifacts/goal/micro-generalize/conclusion-20261124.md`，D-030 已更新。
