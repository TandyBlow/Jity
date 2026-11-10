# State invariants and long-chain continuity

Read-only checks for the browser-local world record. The verifier does not own
state and does not introduce a second world protocol: it rebuilds S0 from the
recorded initial template, replays the committed points through the same
`applyPoint`/`stateDigest` kernel, and compares every stored projection.

## Files

- `index.ts` — `verifyWorldRecord`, `verifySessionSnapshot`, `verifyTurnEntry`,
  `pointContinuityIssues`, `assertPointContinuity`.
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
record and fails on any invariant error. It does not accept a hand-written
before/after pair as a settlement: a turn entry must carry a real transport
snapshot, or a `before` state plus the committed point (the verifier replays it).

## Current limits

- The raw `LocalWorldTransport.restore` still trusts its input; the guarded
  restore and the patch in `results/product/evidence/05-kernel/` are the fix.
- The reference Python kernel also overwrites an existing task on
  `subtasksAdded` with the same id. The browser commit guard is intentionally
  stricter than that reference shape; no existing golden record exercises it.
- This suite is CPU-only. It says nothing about real model prose, page latency
  or user acceptance; 09 owns those runs.
