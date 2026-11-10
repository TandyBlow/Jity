# 05 state invariants — handoff (2026-11-10)

## Scope and ownership

Role: `state-kernel-long-continuity`. Task:
`D:\others\Jity\.local\parallel-local-game\tasks\product-05-state.md`
(sha256 `82adb3aeed69f3348f563983a10d3af10d033e576bc175148a90310185ee8bcb`).

This lane keeps the existing kernel and does **not** create a second world
protocol. It owns the read-only verifier under
`frontend/src/lib/world-engine/local/state-invariants/`, the pinned Python
golden fixture under `frontend/scripts/parallel-kernel/`, and its own evidence.
06 remains the only product integrator; its page and session files are
read-only here. No product acceptance is claimed.

## What was added

- `state-invariants/index.ts`
  - rebuilds S0 from the recorded `initial` template;
  - replays every committed point through the existing `applyPoint` and
    `stateDigest`;
  - checks point sequence/previous chain, `version`, cached point state and
    digest, head, root and orphan point states;
  - checks task completion monotonicity, existing task-id re-adds and stored
    change-id repeats;
  - checks position/slot graph validity;
  - checks player-round roster/cursor/acted/visited consistency and the active
    advance/round/work baseline bindings.
- `state-invariants/guarded-restore.ts`
  - `verifyBeforeRestore` / `restoreVerified` reject a bad snapshot before the
    transport accepts it.
- `frontend/scripts/parallel-kernel/product-session-bridge.test.ts`
  - explicit local bridge only; drives 06's real `LocalGameSession` and
    `MemoryProgressBackend` for 10- and 20-turn chains, mid-settlement
    refresh, duplicate submit, cancel/restore;
  - verifies every checkpoint with the same read-only verifier;
  - not collected by the normal `src/**` include; run it with the dedicated
    `vitest.bridge.config.mts`.
- `state-invariants/verify-09-evidence.test.ts`
  - skipped unless `WORLD_STATE_EVIDENCE` is set; reads a real 09 JSON file or
    directory and prints per-record results.
- `state-invariants/README.md`
  - invariant list and commands.

## Verified locally

```text
npx vitest run src/lib/world-engine/local/state-invariants --maxWorkers=1
→ 1 file passed, 1 skipped; 7 tests passed, 1 skipped
npx vitest run --config scripts/parallel-kernel/vitest.bridge.config.mts --maxWorkers=1
→ 1 file, 5 bridge tests passed (requires the sibling 06 worktree)

npx vitest run src/lib/world-engine/local/state.test.ts src/lib/world-engine/local/canonical.test.ts src/lib/world-engine/local/world-loader.test.ts src/lib/world-engine/local/local-transport.test.ts --maxWorkers=1
→ 4 files, 83 tests passed

npx tsc --noEmit -p tsconfig.json
npx tsc --noEmit -p tsconfig.world-contract.json
→ both exit 0
```

These are CPU tests only. They do not measure model prose, page latency or user
acceptance.

## Counterexamples found (actual, not hypothetical)

1. **Restore trusts a tampered state.** `LocalWorldTransport.restore` calls
   `clone(snapshot)` without replay or digest verification. In the test,
   `person_c` was moved to `hall` in the cached state while the committed point
   replay kept them in `corridor`; raw restore and `LocalGameSession.restore`
   both accepted it. The verifier reports `state_mismatch`.
   - Source: `worktrees/06-recovery/frontend/src/lib/world-engine/local/transport.ts`
     (`restore`).
   - Patch: `results/product/evidence/05-kernel/patches/06-transport-invariants.patch`.

2. **A completed task can move backwards.** After `task_child` was achieved, a
   later point with `subtasksAdded[{id:'task_child',status:'pending'}]` was
   accepted by `applyPoint`, which overwrites `merged[task.id]`. The verifier
   and commit guard reject it with `task_duplicate_add` / `task_regressed`.
   - Source: `local/state.ts` (`applyTasks`).
   - The pinned Python reference (`fc60a60`) has the same overwrite shape; no
     golden record exercises it. The product guard is intentionally stricter.

3. **A discovery id can repeat.** A later point adding an appearance change with
   an id already stored on the entity is accepted and stored twice; the guard
   rejects it with `change_duplicate`.

4. **Restore-delete was observed earlier and is now fixed by 06.** At the
   observed current page hash, `page.tsx` opens a durable `LocalProgressStore`
   and `LocalGameSession.open`; on an open failure it archives the readable
   record with `store.backupLegacy`, and only deletes after a successful
   archive. The earlier `localStorage.removeItem(SAVE_KEY)` path is gone. The
   old patch is under `patches/superseded/` and must not be applied.

5. **Mid-turn work is saved when the IndexedDB store is durable.** At the
   observed current page hash, the page creates a durable store and passes it
   through `LocalGameSession.open`; `refresh` calls `session.flushPersistence`.
   The page `save` callback still returns early when `transport.work` is set, so
   the legacy localStorage fallback only stores settled points. 09 must confirm
   refresh/restore on a normal IndexedDB-capable browser.

6. **Room appearance change is stopped on the second turn.** 04's real-kernel
   repro shows `dangling_updates_refs:[{stage:appearance,entity:corridor,
   kind:change,id:change_7}]` because `schedule.ts::inputIds` registers item and
   character appearance ids but not `state.locations[*].appearanceChanges`.
   06's current `schedule.ts` already contains the location block; 04's current
   tree still needs `04-schedule-location-appearance.patch`, then 04 promotes
   its `it.fails` test (with the first-turn assertion caveat below).

7. **Same-tick page double-submit can still duplicate the visible input.**
   The page's guard is the asynchronous React `busy` state; two submit calls in
   the same tick both pass, append two entries, and the second is then refused
   by `session.submit` as `turn_in_progress`. State is consumed once, but the
   player sees a duplicate entry/error. Patch:
   `results/product/evidence/05-kernel/patches/06-page-submit-lock.patch`
   (synchronous `submitLockRef`). This is static reading, not a real-page
   reproduction; 09 should double-submit.

8. **Fixed handback was observed earlier and is addressed in 06's current
   tree.** The page no longer sets `maxAutoContinuations: 0`; `game-model.ts`
   delegates `continuation` to 04's settlement port and its comment says a
   policy stop is explicit, not a fabricated handback. 09 must still verify the
   real page's continuation behaviour.

8. 09's F1 (`/world-local` lacked COOP/COEP) is fixed in 06's current tree:
   `next.config.ts` sends the headers for `/world-local` and
   `/world-local/:path*`; the old 05 patch is under `patches/merged/`.

## Real 09 run found a sync-ownership conflict

The first real 10-turn page run (`results/product/evidence/09-product-10turn.json`,
product head `bc005e51`) stopped turn 1 with `progress_conflict` after 330 s and
committed no point. The page calls `sync.save(snapshot)`; the sync adapter writes
the session-owned IndexedDB record without `expectedRevision`, bumping its
revision, so the session's next checkpoint conflicts.

06's current tree fixes this with `ProductSync.push` plus `client.skipLocal`
and the page now calls `sync.push(snapshot)`; the session stays the sole local
writer. Commit `10c1407a` added the path and a test. The old 05 patch is under
`patches/merged/`. 09 must rerun the same 10 inputs on the current product
commit; the failed `bc005e51` run is not acceptance evidence. This was a
state/persistence failure, not a narration-quality finding.

## Current blockers and patches (2026-11-10T21:2x local)

- `/world-local` on 06 returned HTTP 500 at 21:15 local; 09's queue is blocked
  on 200 + textarea. 06 must restart/fix the dev server before the rerun.
- `06-transport-invariants.patch` (sha256 `3cfb90b5…`) regenerated for 06's
  LF transport; apply-check ok. It guards `commit` with continuity checks and
  `restore` with the full record verifier.
- `06-page-snapshot-hook.patch` (sha256 `38a1ab63…`) now returns
  `structuredClone(snapshot)`, a detached copy; apply-check ok.
- `06-merge-state-invariants.patch` remains `44081b89…`; merge first, then
  transport/hook.

## Merge bundle

`results/product/evidence/05-kernel/patches/06-merge-state-invariants.patch`
adds the whole verifier module, the 06-session bridge test/config and this
handoff to 06 without touching existing 06 sources; `git apply --check` passes
on the current 06 tree. After it lands, 06 still needs the transport guard and
the page snapshot hook.

## Patches for 06 (not applied by 05)

The active patches are checked with `git apply --check` in a read-only 06
worktree:

- `results/product/evidence/05-kernel/patches/06-transport-invariants.patch`
  - imports `verifyWorldRecord`, `RecordInvariantError`,
    `pointContinuityIssues` from `./state-invariants`;
  - verifies before `LocalWorldTransport.restore` clones;
  - calls `pointContinuityIssues(record.state, point)` before `applyPoint` in
    `handleCommitPoint` and refuses with `request_malformed`.
  - **Dependency:** merge `local/state-invariants/index.ts` first.
- `results/product/evidence/05-kernel/patches/06-page-restore-and-hook.patch`
  - combined page patch for 06's current `d0dfe99a`: a detached
    `window.__worldSnapshot()` (`structuredClone`), a synchronous submit lock,
    `entriesTotal` based on committed player points, and `overallRestored`.
    Apply-check and disposable typecheck pass. The separate component patches
    are under `patches/superseded/`.
- `results/product/evidence/05-kernel/patches/06-state-apply-guards.patch`
  - `state.ts` fix, not just a verifier: reject a second appearance change with
    the same id, a second added task with the same id, and task ids/owners/
    parents that break the world-global hierarchy. Applied in a disposable 05
    tree; 42 state/transport/guard tests pass. 06 must confirm the shared-file
    ownership before applying. 04's smaller legacy `state.ts` needs its own
    patch if it still uses that path.
- `results/product/evidence/05-kernel/patches/04-schedule-location-appearance.patch`
  - `inputIds` also registers `state.locations[*].appearanceChanges` ids and
    their `supersedes` ids. 06's current tree already contains the equivalent
    block; this patch is for 04's current tree, which still lacks it.
  - Validated in a disposable copy of 04's tree: without the patch the first
    run stops with `dangling_updates_refs ... change_7`; with it the run reaches
    `world_complete` and commits the room changes. 04's current test also has a
    first-turn assertion problem (its callback can replace its own first change
    in the same point); 04 should assert the absence of the dangling stop when
    promoting it.

The patches do not make the page durable and do not choose a UI for the
restore-failure state. 06 owns that integration.

## Page/session wiring status (06's current tree)

06's current tree already opens the IndexedDB store/session, archives a
corrupt record before deleting, and (commit `37e2aa38`) rebuilds visible
entries from committed player points plus `snapshot.narrations`. That replaces
the earlier 05 page-localStorage patch, which is now under
`patches/superseded/`. Three gaps remain and are recorded in
`results/product/ownership-requests/05-kernel.json`:

1. `restoredEntries` pairs `snapshot.commands[index]` with player points sorted
   by sequence. Failed/cancelled commands are intentionally retained (six
   existing resume/cancel tests depend on it), so after a failed turn the next
   committed point can show the wrong input. Pair at commit time or persist a
   command→point map; do not pop commands.
2. `__worldRestore` has no `overallRestored`, and `entriesTotal` is
   `commands.length`, not committed player points/history. The boolean must be
   the AND of state, entries and input-consumption restoration.
3. A terminal settlement failure leaves the advance in place; the next submit
   returns `turn_in_progress`, so the page cannot retry without cancel/refresh.
   This belongs to 06/04; 05's rejected command-popping patch is kept under
   `patches/superseded/` only as a counterexample.

## 09 evidence

Ask 09 to keep per-turn either the full `LocalGameSnapshot` or a before state +
committed point, plus input/advance/point ids, digest, timings, URL/commit/model.
Then run:

```bash
WORLD_STATE_EVIDENCE=<file-or-dir> \
  npx vitest run src/lib/world-engine/local/state-invariants/verify-09-evidence.test.ts --maxWorkers=1
```

The test is read-only, prints per-record errors/warnings, and fails on any
invariant violation. It does not accept a hand-written after state as a
settlement.

## Current evidence and limits

- The 09 run at product `0b173b6a` attempted two inputs: turn 1 committed a
  labelled program fallback after 272 s; turn 2 timed out at 330 s. Final
  refresh kept place/sanity/history=1 but entries went 2→0 (`entriesKept=false`,
  `storageChars=0`). The cause was React-only entries; 06's current
  `restoredEntries` addresses the display reconstruction, subject to the three
  gaps above.
- `results/product/evidence/09-product-10turn.json` is **not** acceptance
  evidence. `verify-09-evidence` on it reports only `visible-summary` +
  `evidence_shape`; no point could be replayed.
- `verifySnapshotSequence` (new in `369b9be9`) checks a turn-ordered series of
  full snapshots for version/points regression, a missing previous head, and a
  changed stored digest. The 09 test now accepts `snapshotAfter`/`snapshotBefore`.
- `verifyDisplayHistory` (new in `28883301`) counts committed player points and
  ready narration, errors when the command list is shorter than that history,
  and warns when commands outrun points (failed/cancelled inputs are retained
  for resume) or a point has no narration. The 09 evidence test prints these
  `display:*` issues and fails on the error case.
- Character gender evidence is delivered as
  `results/product/evidence/05-kernel/character-gender-evidence.json`: five
  characters have a direct, uniquely bound pronoun in the current world file
  (路明非/诺诺/楚子航/林亦舟/沈澄); the other nine stay unknown. No schema,
  world hash, or save-contract change.
- No real model/browser/GPU run in this lane; 09 owns that queue. The stricter
  task/change guards are not part of the pinned Python reference; they are
  product continuity checks, not a second state protocol.
