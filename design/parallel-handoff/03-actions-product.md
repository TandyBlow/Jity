# 03 actions/targets/reactions — product wiring

2026-11-10. Role: `actions-targets-reactions` (task `tasks/product-03-actions.md`,
sha256 `89d2f9defe45ef33a36b73b73db81da33b19e1ae2e91eb8c6c35512a5c1672da`).
06 is the sole integrator; this document is the exact merge/wiring request, not a
product-completion claim. Files live in worktree `worktrees/03-actions`, branch
`goal/local-03-actions`.

## What is delivered

Commit `c217b007` (branch `goal/local-03-actions`):

- `frontend/src/lib/world-engine/local/action-execution/order.ts`
  - `roundOrder(state)` → every registered character, ascending sanity, id tiebreak.
  - `orderSubset(state, ids)` → same rule for automatic-round candidates; unknown id throws.
  - `isFreshRoundOrder(state, order)` → check a stored player-round order without rewriting a linked one.
- `frontend/src/lib/world-engine/local/action-execution/port.ts`
  - `createActionExecutionModel(delegate, engine, options)` implements `WorldModelPort`:
    answers `action` / `targets` / `reaction` with the guarded handlers in
    `local/semantics/actions/**`; every other task goes to `delegate` unchanged
    (`pointPlan`, `results`, `updates`, `continuation`, `narration`, `time`, `initial`).
  - `options.onTask(task, key, detail)` reports `{ms, fallback, error, raw, promptChars, issues, source}`.
- Tests: `order.test.ts`, `port.test.ts`, `round.test.ts` (13 tests, 64 with the
  existing action suite) — including a full round through the real
  `ControllerDriver` + `LocalWorldTransport`.

## Why the product needs it

`local/game-model.ts` currently answers the three tasks inline:

```ts
// action
if (roomOf(state, actor) !== roomOf(state, state.protagonistId)) return { kind: 'skip' };
if (!this.lastPlayerInput.includes(actorName) || !INTERACTION.test(this.lastPlayerInput)) return { kind: 'skip' };
// targets
if (source === state.protagonistId && !INTERACTION.test(data.actionText ?? '')) return { targets: [] };
```

That is a name/verb rule, not a semantic judgement: an unnamed same-room NPC can
never act, and a player line that does not match the regex can never force a
reaction. `maxAutonomousActors:0` is already gone from the current tree, but the
name check reproduces the same loss. The port replaces exactly those three
answers; the controller, transport, dice, group freeze and settlement do not
change.

## Merge

06's tree (`e83af87a`) already imports `createActionHandlers` and routes
`action`/`targets`/`reaction` through it, so the semantic handlers are wired.
What is still missing is the new module and the latest handler rule:

```bash
cd D:/others/Jity/.local/parallel-local-game/worktrees/06-recovery
git cherry-pick c217b007 2ec616ab 3a9ad607 33697da8
```

- `c217b007` adds `local/action-execution/**` (order + port + tests).
- `2ec616ab` adds the shipped-free-day-world test.
- `3a9ad607` is a handoff edit (no code).
- `33697da8` changes `semantics/actions/index.ts` + `types.ts` + tests: a
  consumed protagonist opportunity is a program skip, never a model
  continuation.

Dependency: 06's `local/semantics/actions/**` is byte-identical to the
pre-`33697da8` copy (only `fixtures.ts` differs with slot support), so the
cherry-pick is conflict-free. Run `npx tsc --noEmit -p tsconfig.json`,
`npx vitest run src/lib/world-engine/local/action-execution --no-file-parallelism`
and the action suite after it; the round test uses the current
`LocalWorldTransport` snapshot shapes (`state`, `rolls`, `points`).

> **Blocking review findings (06's files)**: (1) `app/world-local/page.tsx:204`
> still passes `maxAutonomousActors: 0`, the exact defect this lane exists to
> remove — every non-protagonist is skipped before any model judgement; (2)
> `local/game-model.ts:171-189` also skips an NPC whose name is not in the
> player's sentence (`scene_budget_unnamed`). Even with a positive budget the
> name gate keeps the old rule. Evidence, cost check and exact patches are in
> `results/product/reviews/03-actions-game-model-name-gate.md`.

## Wiring (06-owned files)

### 1. `local/session.ts` — freeze sanity order for a player round

```ts
import { roundOrder } from './action-execution/order';

// inside submit(text), replacing `const order = Object.keys(plan).sort();`
const order = roundOrder(record.state);
```

`record` is already `this.transport.snapshot()`. `record.state.characters[*].sanity`
is the committed S₀ value. No other line changes.

### 2. `local/transport.ts` — automatic round order

`handleConclude`, `kind === 'continue'`:

```ts
import { orderSubset } from '../action-execution/order';

record.round = {
  roundId: conclusion.nextRoundId, trigger: 'automatic',
  order: orderSubset(record.state, conclusion.candidateCharacterIds),
  cursor: 0, actedIds: [], visitedIds: [], conclusion: null,
};
```

This is the authoritative freeze: the model names *who may act*, the program
orders them by current sanity (design §5.1: continue 在同一事务里按 Sₜ 理智冻结
下一 round 顺序). Linked points never call either helper — they keep the stored
`round.order`.

### 3. `local/game-model.ts` — remove the name gate, not add another layer

06 already delegates the three tasks to `createActionHandlers` (line ~191).
No port composition is needed there. Delete the `scene_budget_unnamed` block
instead; the handlers already scope to the protagonist's room and never write
the player's character. If a crowd bound is ever needed, make it a
deterministic same-room budget, not a name test.

### 3b. Optional: `createActionExecutionModel` for other callers

The port remains available for tests, probes or a caller that does not already
have `LocalGameModel`:

```ts
import { createActionExecutionModel } from '@/lib/world-engine/local/action-execution';
const model = createActionExecutionModel(base, semantic, { attempts: 2, offscreenPolicy: 'skip' });
```

`recentEvents` is optional and left unset here: `LocalGameModel.lastResultsText`
is private, so wiring it would need a public getter on 06's file. The action
prompt already carries the scene, the actor's tasks and the same-room people;
recent events are a quality extra, not a requirement of the task contract.

Keep `base` for every other task. The page's existing `onTask` labels the stage
and marks narration fallbacks; action-family reports now also arrive there with
`fallback`/`source`/`issues`, so 09 can tell a program skip from a model answer.

## What the round test proves (automated, fake engine)

`round.test.ts` runs the real controller and local transport on the hermetic
world:

- `round.order` is `['servant','ally','hero','rival']` (sanity 40/55/60/70), not
  alphabetical, and the cursor visits every slot.
- The protagonist's text is frozen verbatim (`source: program`) although it
  matches no command list.
- 阿宁 acts from her own pending task without being named (`source: model`).
- 老周 (another room) is a scope skip (`source: program`), not a name rule.
- The protagonist's action names 阿宁, who already acted: the roll is stored
  `eligible:false, admitted:false`, no reaction call is made, and the roll still
  travels into the group results as `rollRefs` for the source member.
- Both groups settle inside one point and one atomic `commit_point` request
  (`settlementGroups` = `[['ally'], ['hero']]`), so no partial group result is
  written.

### 4. Transport: consume the input at the protagonist's opportunity, not at the first unit

`local/transport.ts` currently turns `intentStatus: 'pending'` into `consumed` in
`stageWorking`/`skipWorking` for **any** character:

```ts
function consume(status: Working['intentStatus']): Working['intentStatus'] {
  return status === 'pending' ? 'consumed' : status;
}
```

The design says the player input is consumed when the **protagonist's** action
opportunity is processed (including a skip or a forced reaction), not when the
first NPC settles a unit. Today the product uses one point per round, so the
protagonist's slot is inside that point and still sees `pending`; but once
04/06 split a round into linked points (or defer a slot), the protagonist's
later slot sees `consumed`, and the action port then has to skip the player's
command instead of freezing it.

Concrete patch (06's file):

```ts
function consume(status: Working['intentStatus'], actorIds: readonly Id[], protagonistId: Id): Working['intentStatus'] {
  return status === 'pending' && actorIds.includes(protagonistId) ? 'consumed' : status;
}
// stageWorking: consume(working.intentStatus, actors, record.state.protagonistId)
// skipWorking:  consume(working.intentStatus, [slotActor], record.state.protagonistId)
```

`advance.intentStatus` is still committed from the working state, so an
automatic round inherits `consumed` and cannot re-consume a player input.

### 5. The protagonist is never model-written

`semantics/actions/index.ts` now answers a protagonist `action` call as:

- `intentStatus: 'pending'` + non-empty text → the text verbatim (`program`);
- anything else → `{kind: 'skip'}` with `protagonist_command_consumed` (`program`), zero model calls.

Before this, a consumed protagonist slot asked the model to "continue the same
thing"; that could replay the old command in an automatic round or invent a new
player action. The goal-copy guard tests were rewritten accordingly; an NPC
still covers the all-character goal guard. This matches the earlier G5
composition decision (commit `54f630ca`, "let consumed action opportunities skip
without an input binding"): a consumed opportunity skips, it is never
adjudicated.

## 06 minimal patch list (current tree, `2333d880`)

Line numbers are from `2333d880`; the semantic direction is in sections 1–4
above. These are the only product-tree edits this lane is asking for.

**a. `local/session.ts`** (currently line 290):

```ts
-      const plan = record.initial.characters;
-      const order = Object.keys(plan).sort();
+      const order = roundOrder(record.state);
```

with `import { roundOrder } from './action-execution/order';` at the top.

**b. `local/transport.ts`** (currently line 744, inside `handleConclude`,
`kind === 'continue'`):

```ts
-    record.round = { roundId: conclusion.nextRoundId, trigger: 'automatic', order: [...candidates], cursor: 0, actedIds: [], visitedIds: [], conclusion: null };
+    record.round = { roundId: conclusion.nextRoundId, trigger: 'automatic', order: orderSubset(record.state, candidates), cursor: 0, actedIds: [], visitedIds: [], conclusion: null };
```

with `import { orderSubset } from '../action-execution/order';`.

**c. `local/semantics/actions/index.ts` + `types.ts` + tests**: cherry-pick
`33697da8` (a consumed protagonist opportunity is a program skip). This matters
now that 06 routes continuation through 04's port: an automatic round can
revisit the protagonist's slot with the old command text still bound to the
same advance, and the pre-fix handler asks the model to continue it.

**d. `local/game-model.ts`** `reportAction` (line ~202): add the source so the
submission log can tell a model answer from a program decision:

```ts
 this.options.onTask?.(result.task, result.key, {
-  ms: result.elapsedMs, fallback: result.fallback, error, raw: result.raw,
+  ms: result.elapsedMs, fallback: result.fallback, error, raw: result.raw, source: result.source,
 });
```

and add `source?: 'model' | 'program' | 'fallback';` to `GameModelOptions.onTask`'s
detail type (optional; the settlement port callers ignore it). Then the page can
push `{task, key, ms, fallback, source, error}` for `action`/`targets`/`reaction`
into the per-submission ledger it already exposes on `window.__worldSubmission`
(06's `2333d880` ledger currently accounts only results/updates/continuation).
Without this, 09 cannot distinguish "no NPC acted because the model judged
skip" from "the program skipped the scene".

## Open trade-offs (not silently decided here)

1. **Off-screen actors.** `offscreenPolicy: 'skip'` means a character outside the
   protagonist's room gets a program skip, not a model judgement of its own room.
   `'judge'` is implemented (scene hides the protagonist's move) and is the full
   simulation the design describes, but it is roughly one 5–10 s call per
   off-screen character; the free-day world has 12 off-screen characters, which
   does not fit the 60 s first-readable budget on the current CPU/WebGPU runs.
   Default is `'skip'`; switching is one option, not a code change. 06/08 should
   choose with measured runtime numbers.
2. **Point segmentation.** `planPoints` still returns one normal point per round;
   a mid-round group is settled and committed inside that point (proved above).
   The design's §5.3 split (instant point for the joint settlement, linked point
   for the remaining actors) is not implemented. It is 04/06's call: the current
   form keeps atomicity and the frozen order, but the whole round shares one time
   advance. If the split is required, `checkpoint_prepare_successor` already
   exists; the trigger belongs in `planPoints`/controller, not in this module.
3. **`maxAutoContinuations` / `closedBy`.** 04 owns continuation semantics. This
   module never sets `maxAutoContinuations` and never labels a program handback
   as `closedBy:model`.

## Real-page evidence status

Not yet executed. The action-family tasks are only provable on the real
`/world-local` page with a real model. Request `results/product/browser-requests/
03-actions-<id>.json` asks 09 to run, after 06 merges `c217b007`:

- one free-day round where the player names nobody (`我把护目镜推上去，盯着巷口`)
  and 诺诺 is in the same room: expect one model action call for 诺诺 plus a
  program-frozen player action, no name rule;
- one round where a player action names 诺诺 and she already acted: expect the
  roll in the results and no second reaction;
- the same two rounds after a refresh, expecting the same frozen order.

Queued ≠ executed. 09's report is the only acceptance evidence for these.
