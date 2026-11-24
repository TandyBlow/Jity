# Design: goal-micro-quant

## 配置矩阵

- 模型：MiniRBT-H256（10.4M）+ 四头（targets/position/intent/judgment）；切分沿用 `train_ladder.py`（i % 5 == 0 且非对抗行，15/任务）。
- 精度：fp32 ONNX；`onnxruntime.quantization.quantize_dynamic` 动态 int8（QInt8 权重）。
- 输入：同一 512-id 语义 prompt 样本截断为 32/128/512；attention_mask 全 1。
- 运行时：ORT-web WASM、headless Edge、1/4 线程；5 次预热 + 30 次测量，p50/p95。
- 准确率：同一 holdout、ORT Python CPU，logits > 0 与标签逐行精确匹配；另记 fp32/int8 决策一致率。

## 判定

- 若 int8 在 32/128 token 下 ≤10 ms 且 holdout 每任务掉点 ≤1 行，则编码器路线的成本前提成立。
- 512 token 的数字单独记录，不与短输入混用；196.4 ms 保留为「fp32、512 token、单线程」的条件值。

## 风险

- 15 测试/任务、单机单浏览器；结论不外推到手机与其它运行时。
