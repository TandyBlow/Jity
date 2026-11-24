# Tasks: goal-micro-quant

- [x] 1. 按固定切分训练共享 MiniRBT + 四头，导出 fp32 ONNX 与 32/128/512 token 样本（243 训练行）。
- [x] 2. 动态量化为 int8：41,258,293 → 10,558,349 bytes，sha256 已记录。
- [x] 3. 浏览器 ORT-WASM 矩阵：2 精度 × 3 长度 × 1/4 线程，记 p50/p95（`browser.log`）。
- [x] 4. holdout 上比较 fp32 与 int8：每任务精确匹配相同，决策一致 55/57（`accuracy.json`）。
- [x] 5. 结论写 `artifacts/goal/micro-quant/conclusion-20261124.md`，D-030 加配置边界更正。
