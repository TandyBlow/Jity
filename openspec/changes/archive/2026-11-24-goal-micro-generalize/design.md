# Design: goal-micro-generalize

## 数据

- position：`事实：X\n当前：Y` 为文本，候选为地点；每条候选一对，正例=目的地点。
- targets：行动文本为文本，候选为在场人物；正例=标签集合中的 id 对应人名。
- 训练：v1–v4 且不含留出名字（position 63 行、targets 53 行）。
- 测试：seen = v5 且不含留出名字；held = 标签为留出名字的行（position 7、targets 22，跨批次）。

## 模型

- MiniRBT-H256 句对编码器，`[CLS] 文本 [SEP] 候选 [SEP]`，CLS 池化 + 线性标量头；BCE；40 epoch、lr 2e-5、打乱。
- 导出 fp32 ONNX，动态 int8（QInt8）。

## 评估

- 行级聚合：position 取最高分候选；targets 用阈值 0.5 取集合。
- 浏览器内：同一 int8 模型、同一预分词输入、WASM，逐对计时并算准确率。
- 判定：held 与 seen 的差距 ≤1–2 行（position 7 行、targets 22 行的样本）；32 token 文本 + 候选的延迟 5–9 ms。
