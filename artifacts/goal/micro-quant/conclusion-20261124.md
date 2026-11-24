# micro-quant 结论（2026-11-24）

## 矩阵（ORT-WASM，headless Edge，i7-13700H；p50 / p95 ms，5 预热 + 30 测量）

| 长度 | fp32 1t | fp32 4t | int8 1t | int8 4t |
|---|---|---|---|---|
| 32 | 10.03 / 11.49 | 4.45 / 6.09 | 7.17 / 7.77 | 4.58 / 5.88 |
| 128 | 38.70 / 41.53 | 13.90 / 19.41 | 27.00 / 28.76 | 12.28 / 18.71 |
| 512 | 206.13 / 243.26 | 61.90 / 72.32 | 154.55 / 177.02 | 48.27 / 63.03 |

- 模型：`shared-split.onnx` 41,258,293 bytes，sha256 `9dae6e7e8bed8dd6b48b6a377fdb9f50b27fd5402bf08c2a52183ee598c20186`；int8 `shared-split-int8.onnx` 10,558,349 bytes，sha256 `6762ac3db5fdd1d7c8321c7c922635ad1f22773bb19a0a01ec7c2f9cde3747d9`。
- 加载：fp32 533–607 ms；int8 390–546 ms。
- 一致性：int8/32 token/1 线程 7.17 ms 与 2026-10 旧试验中位 7.73 ms 吻合；fp32/512 token/1 线程 206.1 ms 与 micro-nlu 的 196.4 ms 吻合（同一配置，差 5%）。
- 长度缩放接近线性：32→128（4× token）fp32 1t 3.9×；128→512（4×）5.3×（注意力项）。
- 量化收益 1.3–1.45×；线程收益 1.5–3.3×（长度越长收益越大）。

## 准确率（holdout，ORT Python CPU）

| 任务 | 行数 | fp32 | int8 |
|---|---|---|---|
| targets | 14 | 12/14 | 12/14 |
| position | 14 | 3/14 | 3/14 |
| intent | 15 | 11/15 | 11/15 |
| judgment | 14 | 7/14 | 7/14 |

- int8 与 fp32 决策一致 55/57（2 行预测不同，每任务命中数不变）。
- 测试行是 15 个候选里剔除铜哨/医护附楼对抗行后的 14/14/15/14；切分与 `train_ladder.py` 相同。
- 绝对质量无法归因：本轮数据区分不了训练轮数、模型容量、数据分布与输入信息量；int8 与 fp32 的一致只说明本轮未观察到总体准确率下降（小样本）。

## 判定

- 「≤10 ms」在 32 token 下成立：int8 单线程 7.2 ms、int8 四线程 4.6 ms、fp32 四线程 4.5 ms（fp32 单线程 10.03 ms，贴线）；128 token 单线程 27 ms、四线程 12.3 ms，未达 10 ms。
- 196.4 ms 是 fp32、512 token、单线程的条件值，本矩阵复现为 206.1 ms；短输入 + int8 是 7–10 ms。
- 300 次串行：32 token 下 fp32 3.0 s、int8 2.15 s；512 token fp32 61.8 s。共享编码是 1 次编码 + N 个微秒头。
- 量化未在本轮 holdout 上改变决策计数；质量上限的成因未分离（训练轮数、容量、分布、输入信息量）。

## 复核更正确认（2026-11-24）

- 32 token 下有四组配置 ≤10 ms（int8 1t/4t、fp32 4t），原判定写成「只 int8 单线程」有误。
- 质量归因撤回：训练轮数/容量/分布/输入信息量未分离；int8/fp32 相同仅表示本轮未见总体下降。
- 联合缺口：速度用 512-id 截断样本测，准确率用自然长度输入测；未在同一长度上同时验证。
- 输入长度实测：targets 中位 24（最大 33）、position 中位 37（最大 57）、intent 中位 22（最大 29）、judgment 中位 29（最大 41）；128 截断从未触发，position 的自然输入多数落在 32–64。

## 限制

- 15/任务的 holdout、单机单浏览器；手机未测。
- 长度扫描用同一 512-id 前缀截断，attention_mask 全 1，与真实短句的分词分布有差异。
- 量化是动态 int8（QInt8 权重），未测 static/QAT。

## 复现

```bash
python artifacts/goal/micro-quant/train_split.py
python artifacts/goal/micro-quant/quantize.py
python artifacts/goal/micro-quant/make_samples.py
bash artifacts/goal/micro-quant/browser_matrix.sh   # 写 browser.log
python artifacts/goal/micro-quant/eval_onnx.py      # 写 accuracy.json
```
