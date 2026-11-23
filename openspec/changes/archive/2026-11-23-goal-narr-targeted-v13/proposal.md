# Proposal: goal-narr-targeted-v13

## Why

v12 在 run122 把在场的诺诺写成缺席，缺席模板从阿豹的合法失败样本过拟合。需要正例对照：找/问在场的 NPC 时，正文写明她在场并做她的动作。

## What Changes

- 10 条手写正例（五个基 × 两个变体）：诺诺/芬格尔/林亦舟在场并摇头、摊手、挪短枪、举相机；主角自问或清点，不替 NPC 行动。
- 检查器 0/10；`sft-v13` 348 行（v12 338 + 10）。
- 训练待触发；训练后五回合 + 20 输入验证。

## Capabilities

（无；手写训练数据。）

## Impact

- 本地 `.local/narr-train/targeted-v13*`、`sft-v13.jsonl`（gitignored）。
- 证据：`artifacts/goal/narration/read-v13-data-20261123.md`。
