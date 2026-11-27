# E23 LLM fixed-event cell: the 0.6B's direct four-state answer

**Question.** The five-arm scoreboard lacked a fixed-event number for the
existing-LLM arm. Given the same frozen existence rows the heads answer, what
does the in-page 0.6B semantic model say when asked the same question directly?

**Setup.** `semantic-probe.json` = the frozen existence holdouts (env `sm6-` 9
rows, info `sm10-` 10 rows). A dev probe page loads
`/models/Qwen3-0.6B-Q4_K_M.gguf`, asks one prompt per row: "判断这回合的结算
事实是否为【环境|信息】字段提供了新的、可提交的状态内容。只输出 JSON…
{"label":"present"} 或 {"label":"absent"}", temperature 0, max 24 tokens.
Driver: `probe-semantic-llm.mjs` (Playwright, lease-guarded); answers saved to
`evidence-semantic-llm-probe-1.json`.

**Results (19 rows).**
- env (9): 0/8 positives, 1/1 negative → accuracy 1/9.
- info (10): 1/4 positives, 5/6 negatives (1 false positive) → accuracy 6/10.
- Overall 7/19 (36.8%), positive recall 1/12; every answer parsed cleanly.
- The existence heads on the same rows: env 8/9, info 9/10 (E15); overall
  17/19.

**Conditions.** One prompt, no few-shot, no product multi-actor context; the
rows are the same frozen projection the heads see. The model defaults to
"absent", which also matches the negative-heavy distribution of the rows, so
part of the score is the base rate. The product's LLM lane is not this prompt —
this is an LLM arm on the same fixed-event question, not the lane's turn
behaviour (E20 covers the lane end to end).

**Principle.** At fixed events the in-page LLM is far below the trained heads
at the same question (7/19 vs 17/19) and answers almost everything absent; the
heads' value is the positive recall the LLM cannot produce. The remaining gap
in the scoreboard is now only the rules/classifier page arms and real-device
mobile.

**Artifacts.** `semantic-llm-probe/page.tsx`, `probe-semantic-llm.mjs`,
`frontend/public/micro/semantic-probe.json`,
`evidence-semantic-llm-probe-1.json`, D-122.
