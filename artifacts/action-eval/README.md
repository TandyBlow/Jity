# Action/targets/reaction evidence

Real on-device runs: headless Edge + wllama + `Qwen3-0.6B-Q4_K_M.gguf`, COOP/COEP,
temperature 0, seed 42, max 160 tokens per call. Each archive records, per case:
the exact prompt, the raw completion, the decoded value, `source`/`fallback`,
every guard issue (including rejected repair attempts), call timings and the scene
(visible/absent/items) the handler saw.

| archive | code state | result |
|---|---|---|
| `dry-prompts.json` | current | no model; 17 scenes/prompts dumped to prove the runnable interface |
| `run-1-unguarded.json` | first committed handlers | 17 cases, 16 calls, mean 6.3s, p50 7.1s, max 11.3s |
| `run-2-guarded.json` | after run-1 findings | see the archive and the handoff §4 |

Run 1 failures that changed the code:

1. **Paraphrase echo accepted** (A1). The model restated the player's action with
   the subject dropped ("靠在巷口墙边，确认护目镜是否起雾") and the verbatim-span
   guard missed it. Added in-order coverage check (`sharedSubsequence` ≥ 80%).
2. **Task goals accepted as actions** (A4b, A6, A7). The model copied its own
   pending task goal verbatim ("换上相机备用电池，拍到有辨识度的争旗场面").
   Added `action_is_task_goal` / `reaction_goal_copy` guards and a prompt rule.
3. **Spurious targets accepted with a warning** (T3, T4, T5). The model picked the
   only present character for a movement action (T5), an absent-person visit (T3)
   and an action addressed to someone else (T4). `target_unmentioned` became an
   error with one repair; a second failure falls back to an empty target set
   (precision first: a phantom target forces a roll and a fabricated reaction).
4. **Player echo repaired, not prevented** (A2 first attempt, A3 twice). The model
   duplicated the player's sentence; the repair worked for A2, A3 fell back to
   inaction. Prompt now shows the legal dialogue form (`诺诺回答：“……”`).
5. **Reaction invented item behaviour** (R1, R3): the belt "闪烁/发烫", the radio
   moved on its own. Prompt now forbids uncommitted item state changes; this
   remains a review item (no program guard).

Reproduce:

```bash
python D:/others/Jity/.local/parallel-local-game/resource_lease.py acquire --lane 03-actions --purpose "action probe"
cd frontend
node scripts/parallel-actions/run-action-eval.mjs \
  --assets D:/others/Jity/.local/world-narration-worktree/frontend/public \
  --out ../artifacts/action-eval/run.json
python D:/others/Jity/.local/parallel-local-game/resource_lease.py release --lane 03-actions
```
