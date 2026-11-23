# Design: goal-narr-v5-acceptance

- 页面 `/world-local`，五回合 s02–s06；`narrationModel=qwen3-1.7b-narr-lora&schedHandback=player&offscreenPolicy=skip&settlementUnknownRule=1`；`--fresh`。
- 判定按 `acceptance.md` 4.2 人工读评 + 扩展检查器。

## 结果

- s02 忠实（结算给两人，正文写两人）；s03 规则阅读归因（结算只给诺诺）；s04 时间数字；s05 凭空「侧身挡住视线」；s06 结算中止（3 次 `results_unknown_entity`）。
- 检查器 1 命中（s05 band）；人工硬错 s03/s05；未达 5/5。
