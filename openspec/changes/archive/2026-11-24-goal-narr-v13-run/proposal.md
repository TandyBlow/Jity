# Proposal: goal-narr-v13-run

## Why

v13 正例对照数据训练完成后需要真实页面验证：缺席回归是否消失，s13 的修复是否生效，20 输入是否仍被结算中止与自动链超时卡住。

## What Changes

- 集群作业 276368（5 epoch、loss 0.096）→ 适配器回传 → 本地 Q4_K_M `82e513db…`。
- run124：5/5、24.5–58.8 s、检查器 0；缺席回归消失。
- run125（20 输入部分）：chunk1/chunk3 干净；chunk2 s06 强门中止、s07 330 s；chunk4/5 被内存回收未跑。
- 强门改为重试耗尽后丢弃事实、不中止 point（`unknown_entity_named`）；全量 1259 passed。

## Capabilities

（无；训练验证与结算门修正。）

## Impact

- `frontend/src/lib/world-engine/local/semantics/settlement/results.ts`、`settlement.test.ts`、`frontend/src/app/world-local/page.tsx`（arm sha）。
- 证据：`run124-17b-lora-v13-5turn.json`、`run125-20turn-chunk1..3.json`、对应 prose-facts check、`read-v13-run-20261124.md`。
