# Proposal: goal-micro-generalize

## Why

现有四个头都是固定词表分类：targets 5 个人、position 11 个地点。新战役出现新名字就要改头，跨世界泛化未被证明。复核轮建议改成候选打分：给 (文本, 候选) 打分，不学固定类别。另有两个测量缺口：准确率在 FP32 ONNX + Python CPU 上测、延迟在浏览器 WASM + 合成输入上测；32 token 后收益有限，应转向泛化与协同。

## What Changes

- position 与 targets 改成 MiniRBT 句对打分：`[CLS] 文本 [SEP] 候选 [SEP]` → 标量。
- 留出名字：position 留出医护附楼、跨溪小桥；targets 留出秦越、林亦舟；训练行不含留出名字（position 63 行、targets 53 行），留出测试 7 / 22 行。
- 浏览器内同输入评估：预分词后把测试对写 JSON，浏览器加载 int8 模型逐对打分，按行聚合，同时出准确率与延迟。
- 产出 `artifacts/goal/micro-generalize/`；不动产品。

## Capabilities

（无；研究实验。）

## Impact

- 只新增实验脚本与证据；风险：留出测试行少（position 7、targets 22）。
