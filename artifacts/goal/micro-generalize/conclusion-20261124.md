# micro-generalize 结论（2026-11-24）

## 方法

- MiniRBT 句对打分（`[CLS] 文本 [SEP] 候选 [SEP]` → 标量），训练 329 对（每行加 2 个硬负例），40 epoch，导出 fp32 41.2 MB、int8 10.55 MB。
- 切分：训练 = v1–v4 且不含留出名字（position 215 对、targets 114 对）；seen = v5 且不含留出名字；held = 标签为留出名字的行（position 医护附楼/跨溪小桥 7 行、targets 秦越/林亦舟 22 行）。
- 浏览器内同输入评估：同一 int8 模型、同一预分词输入、WASM；行级聚合 position 取最高分、targets 阈值 0。
- 基线：逐字匹配——候选名是否出现在行动文本里。

## 结果（int8，浏览器；与 fp32 Python 行级一致）

| split | position | targets | 基线 targets | p50 4t | p50 1t |
|---|---|---|---|---|---|
| seen | 10/13 | 8/9 | 9/9 | 3.83 ms | 6.52 ms |
| held | 7/7 | 18/22 | 21/22 | 3.83 ms | 6.52 ms |

- pair 输入中位 29 token、最大 36；加载 441–476 ms；p95 5.72 ms（4t）/ 8.67 ms（1t）。
- 留出名字没有掉点：position 7/7；targets 18/22（seen 8/9，样本不同，不作直接对比）。
- 硬负例是必要条件：无硬负例时模型大面积误报（链里 5/8 行把在场但未被点名的角色判为目标）；加入每行 2 个硬负例后误报降到 3/8。
- 基线唯一失败：row 187「把水递给两个人」——行动里没有名字，需要指代/省略推理；模型也只给出部分答案（诺诺，缺秦越）。
- 链的 12 回合上：基线 targets 8/8，模型 5/8（4 个空标签回合被误报）。

## 判定

- 候选打分去掉了固定词表（held position 7/7、targets 18/22），但在这批数据上逐字匹配更强或持平：seen 9/9 vs 8/9、held 21/22 vs 18/22、链 8/8 vs 5/8。
- 模型的价值只能在否定、指代、省略等非词面匹配的例子上体现；现有数据只有 1 个省略例，双方都失败。需要专门构造这类测试集，否则不应宣称模型优于程序。
- 同一输入、同一精度、同一浏览器同时测出准确率与延迟：4 线程 3.83 ms、1 线程 6.52 ms（中位 29 token）。
- 限制：held position 7 行、seen targets 9 行；单机单浏览器。

## 复现

```bash
python artifacts/goal/micro-generalize/build_pairs.py
python artifacts/goal/micro-generalize/train_pairs.py
python artifacts/goal/micro-generalize/quantize_pairs.py
python artifacts/goal/micro-generalize/make_test_data.py
bash artifacts/goal/micro-generalize/run_browser.sh
python artifacts/goal/micro-generalize/baseline_compare.py
```
