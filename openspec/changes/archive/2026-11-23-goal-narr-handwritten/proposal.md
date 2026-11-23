# Proposal: goal-narr-handwritten

## Why

用户指出「数据没理由造不出来」，并裁决此后叙事训练数据全部手写（D-027）。此前工作流生成的目标出现复述与归属错误；因此由执行 agent 本人为 84 条真实提示各写两条替代正文，验证手写数据能否把验收回合的硬错压到零。

## What Changes

- 手写 168 条替代正文（每条提示两种写法），全部过扩展检查器；与原有 84 条合成 252 行 SFT，训练 v8。
- 五回合与十输入复测；评估臂指向 v8。

## Capabilities

（无；训练数据与测量。）

## Impact

- 本地 `.local/narr-train/alt-targets-*.txt`、`sft-v8.jsonl`、v8 权重（gitignored）。
- `frontend/src/app/world-local/page.tsx`（评估臂 sha 指向 v8）。
- 证据：`artifacts/goal/narration/run105-17b-lora-v8-5turn.json`、`run106-17b-lora-v8-10turn.json`、`read-v8-handwritten-20261123.md`。
