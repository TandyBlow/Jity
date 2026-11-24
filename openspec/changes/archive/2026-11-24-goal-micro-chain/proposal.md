# Proposal: goal-micro-chain

## Why

单模型实验已把长度、精度、泛化分开测过；下一步要回答「四个头串起来能否可靠执行」。需要端到端成功率、错误传播、调用次数与总耗时，而不是单任务准确率。

## What Changes

- 12 回合手写数据（8 act / 4 skip），每回合含 NPC 意图输入、行动、在场、当前位置、候选、结算事实、骰点、四任务期望。
- 链：intent → skip 短路；act → targets 句对打分 → position 句对打分 → judgment（t2 int8，目标来自 targets 输出）。
- 浏览器内串行执行，逐调用计时；4/1 线程各跑一次。

## Capabilities

（无；研究实验。）

## Impact

- 只新增实验数据与 harness；风险：12 回合、单种子，传播结论只能作方向。
