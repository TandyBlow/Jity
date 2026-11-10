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

```bash
cd D:/others/Jity/.local/parallel-local-game/worktrees/06-recovery
git cherry-pick c217b007
```

Dependency: `local/semantics/actions/**` already exists in 06's tree (identical
`index/checks/prompts/types/text`; only `fixtures.ts` differs with slot support),
so no other port of this module is needed. `frontend` typecheck and
`npx vitest run src/lib/world-engine/local/action-execution --no-file-parallelism`
must be run after the cherry-pick; the round test uses the current
`LocalWorldTransport` snapshot shapes (`state`, `rolls`, `points`).

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

### 3. `app/world-local/page.tsx` — delegate the three tasks

```ts
import { createActionExecutionModel } from '@/lib/world-engine/local/action-execution';

const base = new LocalGameModel(semantic, { /* existing options */ });
const model = createActionExecutionModel(base, semantic, {
  onTask: baseOptions.onTask,          // same reporter the page already has
  attempts: 2,                          // one repair, then explicit fallback
  offscreenPolicy: 'skip',              // see the trade-off below
  recentEvents: () => (base as { lastResultsText?: string }).lastResultsText
    ? [String((base as { lastResultsText?: string }).lastResultsText)]
    : [],
});
// use `model` for LocalGameSession.create/restore and modelRef
```

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
