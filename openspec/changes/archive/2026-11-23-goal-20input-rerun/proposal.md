# Proposal: goal-20input-rerun

## Why

内存修复（语义 KV q8_0）后，用户批准重跑 20 输入套件。上次首批即被宿主回收；这次需要完整的 20 输入证据与回归结论。

## What Changes

- run121：5 个 chunk 顺序跑完，20/20 输入提交；18 回合无驱动问题、≤60 s（27.4–50.9 s）。
- 失败：s13 结果门误报中止（贪婪名字截取）、s14 自动链 330 s、s15 叙事张冠李戴（检查器命中）。
- 修 s13 误报：名字只在动作里的弱证据改为丢弃事实、不中止 point；全量 1258 passed。
- 记录 `read-20input-20261123.md` 与 5 份 chunk 证据。

## Capabilities

（无；验收运行与结算门修正。）

## Impact

- `frontend/src/lib/world-engine/local/semantics/settlement/results.ts`、`settlement.test.ts`。
- 证据：`artifacts/goal/narration/run121-20turn-chunk1..5.json`、`prose-facts-check-run121-chunk*.json`、`read-20input-20261123.md`。
