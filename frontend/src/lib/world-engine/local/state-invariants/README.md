# State invariants and long-chain continuity

Read-only checks for the browser-local world record. The verifier does not own
state and does not introduce a second world protocol: it rebuilds S0 from the
recorded initial template, replays the committed points through the same
`applyPoint`/`stateDigest` kernel, and compares every stored projection.

## Files

- `index.ts` — `verifyWorldRecord`, `verifySessionSnapshot`, `verifyTurnEntry`,
  `pointContinuityIssues`, `assertPointContinuity`, `verifyVisibleAcceptance`.
- `guarded-restore.ts` — `restoreVerified` / `verifyBeforeRestore`; validates a
  snapshot before `LocalWorldTransport.restore` accepts it.
- `verify.test.ts` — golden replay, corruption, task/change monotonicity and
  raw-restore gap counterexamples.
- `README.md` — this file.
- The real 06-session bridge lives at
  `frontend/scripts/parallel-kernel/product-session-bridge.test.ts`; it is an
  explicit local bridge, not part of the product suite.
- `verify-09-evidence.test.ts` — read-only verifier for 09's real product turn
  records. Skipped unless `WORLD_STATE_EVIDENCE` is set.

## Invariants

- S0 is rebuilt from `initial`; the root cached state and digest match it.
- Point sequence is 1..N with a single previous-point chain; `version` equals
  the number of committed points; no orphan point states.
- Every point's stored state/digest equals replay; `record.state` and the head
  cache equal replay; positions and slots pass the kernel's graph check.
- A completed task never returns to `pending`; a point cannot re-add an existing
  task id, achieve an already achieved task, or repeat a stored change id.
- Every task belongs to its character, has one id, and points at a parent that
  exists in the same character; the persisted roll ledger has unique ids,
  1..20 results and matching eligibility flags.
- Replayed clock time never moves backwards.
- Player rounds freeze the complete roster; `round.cursor` equals the visited
  prefix; acted/visited ids stay inside the frozen order.
- An active advance has an active round and a work baseline bound to the current
  head/version/digest; a completed round has a conclusion and no active work.
- A scheduler checkpoint is only a resume hint and must be structurally valid.

## Commands

```bash
cd frontend
npx vitest run src/lib/world-engine/local/state-invariants --maxWorkers=1
npx vitest run --config scripts/parallel-kernel/vitest.bridge.config.mts --maxWorkers=1
npx tsc --noEmit -p tsconfig.json
```

09 evidence (one JSON file or a directory):

```bash
WORLD_STATE_EVIDENCE=/path/to/09-turns.json \
  npx vitest run src/lib/world-engine/local/state-invariants/verify-09-evidence.test.ts --maxWorkers=1
```

The test prints `{file,label,ok,worldId,version,points,errors,warnings}` for each
record and fails on any invariant error. A full transport snapshot (or a real
`before` state plus the committed point) is replayed. A page-visible acceptance
summary without a snapshot gets a separate `visible-summary` check for history
and task monotonicity and the refresh marker, with an `evidence_shape` warning;
that is not a substitute for the replay.

## Current limits

- The raw `LocalWorldTransport.restore` still trusts its input in 06's current
  tree; `06-transport-invariants.patch` was validated in a disposable 06 copy
  and waits for 06 to merge. 06 already contains the location-appearance
  `inputIds` fix; 04 still needs `04-schedule-location-appearance.patch`.
- `state.ts` still overwrites an existing task and a reused change id;
  `06-state-apply-guards.patch` was validated in a disposable tree and waits
  for 06 to confirm shared-file ownership. The verifier rejects the resulting
  records even before that patch is applied.
- 09 cannot yet capture a full snapshot from the real page; 06 needs to apply
  `06-page-snapshot-hook.patch` (or an equivalent read-only hook).
- This suite is CPU-only. It says nothing about real model prose, page latency
  or user acceptance; 09 owns those runs.

## 09 snapshot series and display history

`verifySnapshotSequence(values)` accepts full `LocalGameSnapshot` values (or
transport records) in turn order. It replays each snapshot with the same S0 +
point rules and additionally rejects a later snapshot with an older version or
fewer points, a missing previous head, or a changed stored digest for the
previous head. `verifyTurnEntry`/the evidence test accept the hook fields as
`snapshot`, `snapshotAfter` or `snapshotBefore`.

The page's rendered `entries` are display data, not world truth. The real 09
run at `0b173b6a` restored the IndexedDB state but lost both entries
(`historyCount` stayed 1, `entriesBefore=2, entriesAfter=0`) because no code
persisted them. `06-page-entry-restore.patch` stores them beside the committed
snapshot, keyed by `worldId + headPointId`, and refuses to attach them after a
rollback/fork. It does not change `LocalGameSnapshot`, the world asset or the
save contract.
