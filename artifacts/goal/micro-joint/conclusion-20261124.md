# micro-joint 结论（2026-11-24）

## 联合表（T2：v1–v4 训练、v5 测试、打乱、40 epoch；15/任务）

| 长度 | targets | position（截断 / 压缩） | intent | judgment | int8 1t | int8 4t | fp32 1t | fp32 4t |
|---|---|---|---|---|---|---|---|---|
| 8 | 0/15 | 1/15 | 5/15 | 7/15 | 2.78 | 2.43 | 4.11 | 2.89 |
| 16 | 11/15 | 6/15 | 12/15 | 10/15 | 4.33 | 2.92 | 6.26 | 3.40 |
| 32 | 13/15 | 9/15（10/15） | 12/15 | 11/15 | 7.83 | 4.57 | 10.87 | 5.34 |
| 64 | 13/15 | 10/15 | 12/15 | 11/15 | 14.50 | 7.34 | 20.64 | 8.33 |
| 128 | 13/15 | 10/15 | 12/15 | 11/15 | 30.30 | 12.13 | 42.62 | 14.40 |

- 延迟为 p50 ms，ORT-WASM、headless Edge、i7-13700H；样本是 512-id 前缀截断；加载 fp32 572–755 ms、int8 444–533 ms。
- 自然输入 = 128 行（v5 测试输入最长 42 token）；截断到 64/128 与自然一致。
- position 的「压缩」列是 15 条手写 ≤32 token 输入（保留事实/当前/候选），其余任务自然输入已 ≤32。

## 训练配置对比（natural test，合计 60 行）

| 配置 | 训练 | natural | 32 token（截断） | 32 token（压缩 position） |
|---|---|---|---|---|
| T1 | 固定顺序 | 43/60 | 43/60 | position 8/15 |
| T2 | 每 epoch 打乱 | **46/60** | **45/60** | position **10/15** |
| T3 | 打乱 + 训练截断 32 | 44/60 | 43/60 | position 10/15 |

- T2 明细：targets 13、position 10、intent 12、judgment 11；T1：14/8/10/11；T3：13/9/11/11。
- 训练打乱比固定顺序多 3 行（position +2、intent +2、targets −1），单种子、小样本。
- 训练时截断 32（T3）不比自然训练好：截断会切掉 position 的候选列表，压缩输入才是缩短的正确方式。
- 40 epoch 下三个配置的训练集都是 60/60（过拟合），测试 43–46/60；train/test 差距只作拟合描述，不作成因归因。

## 判定

- 在这批 15/任务样本上，32 token 达到与自然输入相同的准确率（targets/intent/judgment），position 截断掉 1 行、压缩输入补回；这是样本内结论，不是泛化结论。
- 16 token 开始掉点（targets 11、position 6、judgment 10）；8 token 崩（targets 0、position 1）。
- 300 次串行在 32 token、int8 四线程下约 1.37 s；共享编码是 1 次编码 + N 个头。
- 「≤10 ms」在 32 token 下三组配置成立（int8 1t/4t 7.83/4.57、fp32 4t 5.34）；fp32 单线程 10.87 ms 未达。

## 限制

- 15/任务、单种子、单机单浏览器；压缩只覆盖 position。
- 切分是批次（模板/场景）切分，不是实体留出：实体留出会把 qin/lin 等标签从训练里移除，变成零样本问题。
- 准确率在 FP32 ONNX + Python CPU 上测，延迟在浏览器 WASM + 合成截断输入上测；输入内容、精度、运行环境未完全统一（下一步做浏览器内同输入评估）。
- 分类头是固定实体/地点词表（targets 5、position 11）；新战役的新名字需要改头，候选打分是下一步。
- 无真机；无 static/QAT；无多模型协同。

## 复现

```bash
python artifacts/goal/micro-joint/train_joint.py --order fixed --epochs 40 --name t1
python artifacts/goal/micro-joint/train_joint.py --order shuffled --epochs 40 --name t2
python artifacts/goal/micro-joint/train_joint.py --order shuffled --train-len 32 --epochs 40 --name t3
python artifacts/goal/micro-joint/eval_joint.py --name t2 --model .local/micro-joint/t2.onnx
python artifacts/goal/micro-joint/quantize_joint.py --name t2
python artifacts/goal/micro-joint/make_samples.py
bash artifacts/goal/micro-joint/browser_lengths.sh
```
