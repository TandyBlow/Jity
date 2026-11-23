# Proposal: goal-settle-rules-guard

## Why

run113/114 的 point 结算把「观察/清点」写成「路明非：看懂了规则牌」，叙事照写后被读成硬错。该事实无动作依据，属于结算层的伪事实。

## What Changes

- 结算层新增丢弃原因 `unsupported_action`：成员 action 不含「规则」时，写规则牌且不带否定词的事实丢弃。
- 单测 103 passed；run115 五回合 5/5 完成、35.2/47.6/33.2/45.7/31.8 s（5/5 ≤60 s），规则牌事实消失，s06 无事实且叙事写出交接失败，检查器 0。
- 剩余：两 point 重复叙述、0.6B 自造「故障短讯机」。

## Capabilities

（无；结算清理与验证。）

## Impact

- `frontend/src/lib/world-engine/local/semantics/settlement/results.ts`、`settlement.test.ts`。
- 证据：`artifacts/goal/narration/run115-17b-lora-v11-5turn.json`、`prose-facts-check-run115.json`、`read-run115-20261123.md`。
