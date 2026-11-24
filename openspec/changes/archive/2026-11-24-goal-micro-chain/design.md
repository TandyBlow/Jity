# Design: goal-micro-chain

## 输入构造

- targets 对 = `行动：…\n在场：…` + 候选名，与训练同格式。
- position 对 = `事实：…\n当前：…` + 候选地点；事实用结算事实，不是行动文本（按行动文本喂会掉到 3/8）。
- judgment = `行动：…\n目标：…\n骰点：…`；目标键由 targets 输出决定，预分词所有在场子集变体。
- intent = `角色：…\n任务：…\n现场：…`。

## 模型

- intent/judgment：t2 int8（共享 MiniRBT + 四头）。
- targets/position：pair-scorer int8（候选打分）。

## 指标

- 端到端（执行到的阶段全对）、每阶段准确率、错误传播（targets 对/错时的 judgment）、调用数、每回合耗时。
