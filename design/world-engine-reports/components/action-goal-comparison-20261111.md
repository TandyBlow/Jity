# Action-goal comparison and complete action evidence

User-authorized comparison on 2026-11-11: remove the 85% common-subsequence
branch from `action_is_task_goal`, retaining exact equality, the short-goal
contiguous-span branch and `allGoals` without threshold/scope changes.

The old predicate measured the share of the **action** covered by a longest
common subsequence. It preserves character order but does not require adjacent
characters. The 20ee rejection count is motivation for this comparison, not
proof that this branch caused all ten rejections. Exact copies can still fail.

Other common-subsequence uses remain: NPC/player paraphrase detection, its
scene-name-stripped comparison, and reaction-goal-copy detection. The latter
previously shared `taskGoalCopy`; it is retained explicitly at the reaction
call site so this change affects only the requested action predicate. Utility
and text tests still exercise the same algorithm.

The page now saves full `raw`, each attempt's `calls[].raw`, the final structured
`value`, and error `issueDetails` (`code`, `message`, `detail`) for action-family
results. Existing code-only issues stay for compatibility. `recordKind`
distinguishes per-model-call callbacks from final handler results; retries are
not extra actors. A repaired output retains the rejected attempt and its
matched goal rather than overwriting that evidence with the successful retry.
No narration inspection or state semantics are added.

Validation: six focused Vitest files / 56 tests pass, including a real-world
goal-fragment regression and an end-to-end LocalGameModel callback test proving
that both raw attempts and the matched goal reach the product evidence hook.
Command (from frontend):

```text
node node_modules/vitest/vitest.mjs run src/lib/world-engine/local/action-execution/product-world.test.ts src/lib/world-engine/local/semantics/actions/actions.test.ts src/lib/world-engine/local/semantics/actions/text.test.ts src/lib/world-engine/local/game-model-abort.test.ts src/lib/world-engine/local/point-narration/game-model-snapshot.test.ts src/lib/world-engine/local/game-model-action-evidence.test.ts
```

09 must verify the served build and compare the same input, seed, world and
models against run `2026-11-11T1419-20ee`. Report unique actors actually judged
by a model, unique actors with `action_is_task_goal` rejections, and final act
decisions, separately from retries, program skips, model skips and fallbacks.
These counts can overlap (a rejected actor can act after repair). Store complete
outputs. If the requested rejection reduction is absent, restore only this
action predicate in a new commit and retain the evidence changes. Do not
silently adjust thresholds. A goal belonging to the actor or another actor is
useful diagnostic context, not by itself proof of correctness or copying.

The real-model comparison is pending; passing these mechanism tests does not
establish a lower rejection rate, a livelier world or product quality.
