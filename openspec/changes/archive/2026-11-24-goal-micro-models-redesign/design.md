# Design: goal-micro-models-redesign

## 上一轮的可复用结论

- 0.52M 哈希头：浏览器 ORT-WASM 单线程 p50 0.10 ms（1,292 grams）；微秒级成立。
- 10.4M MiniRBT（512 tokens、fp32、单线程）：196 ms；102M MacBERT：2,439 ms；0.6B 单次 2.37 s 桌面 / 7.7 s 移动。
- 但 512-token 整段 prompt 是错误输入；短输入（64 tokens）下编码成本约按 token 比例下降（~25 ms 量级，待测）。

## 共享编码协议

```
每回合输入（玩家句 + 场景短上下文，~64 tokens）
        |
        v
   一次编码（10M 级编码器，量化 + 多线程/WebGPU 上限待测）
        |
        +--> 头1 意图/act-skip（0.1 ms 级）
        +--> 头2 实体/目标（候选对打分）
        +--> 头3 位置/槽位（候选打分）
        +--> 头4 判定/归因（5 向/4 向）
        ... N 个微型头
        |
        v
   结构化动作记录 -> 规则结算 -> 事实记录 -> 叙事（结算后生成）
```

- 计时分开：encode / head / tokenize / tensor / 后处理。
- 长度扫描 8/16/32/64/128；每档记录 p50/p95 与准确率。
- 编码器选项：ONNX Runtime Web 的 WASM 多线程、SIMD、WebGPU；与单线程基线对照。

## 结构化契约

动作记录示例：

```json
{"actor":"player","action":"take","target":"key_01","source":"table_01","destination":"inventory","stealth":true}
```

- reaction：`{actor, response, target, kind}`。
- fact：`{actors[], action, outcome, source}`。
- 叙事：结算完成后由一个小生成模型成文；不是微头的职责。

## 阶梯与消融

- 0.1M/0.5M/2M/5M：MLP、CNN（字符卷积）、GRU；fastText 对照；MiniRBT 作上限。
- 消融：完整 prompt vs 去掉任务说明/示例/规则；记录准确率差。
- 精度：fp32 / int8 / q4；张量形状与输入构造耗时入表。

## 数据

- 手标平衡集（目标 ≥300 条，覆盖四任务），替代银标。
- 对抗性切分：换名、未见物品、改写/否定/指代/省略、相似干扰候选、多行为先后。
- 训练/测试按回合与按名称双重隔离，防泄漏。

## 判定

- 通过线（实验口径）：共享编码 + N 头在真实手机浏览器上总耗时进入 60 秒，且手标集准确率达到任务可用线（各任务分别定义）。
- 未达线：如实记录证伪，不宣称通过。
