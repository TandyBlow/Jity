# Proposal: goal-micro-quant

## Why

micro-nlu 结论里的 196.4 ms 来自 fp32、512 token、单线程这一种配置，不能代表编码器在短输入与量化下的成本。仓库旧试验已有 int8 短输入 7.7–10.1 ms 的记录，但两轮从未在同一模型、同一运行时下做过受控对照；据此把编码器路线判为数百 ms–秒级，证据不足。

## What Changes

- 同一 MiniRBT-H256（10.4M）共享编码 + 四头，按固定切分训练，导出 fp32 并动态量化为 int8。
- 浏览器 ORT-WASM 矩阵：2 精度 × 3 输入长度（32/128/512 token）× 1/4 线程，记 p50/p95。
- 同一 15/任务 holdout 上比较 fp32 与 int8 的四任务精确匹配与决策一致率。
- 产出写 `artifacts/goal/micro-quant/`，在 `design/goal/decisions.md` 补配置边界更正；不动产品。

## Capabilities

（无；研究实验，不改产品默认。）

## Impact

- 只新增实验脚本与证据；不动产品路径。
- 风险：15 测试/任务样本小，结论只针对本机本运行时；真机仍无设备。
