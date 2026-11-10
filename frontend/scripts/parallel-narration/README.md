# parallel-narration scripts

`run-real-narration.mjs` drives the committed-narration strategy through the
real browser stack (headless Edge + wllama + a user-provided GGUF). It is a
small representative probe, not a baseline and not a final acceptance run.

## Run

Local inference is an exclusive resource. Acquire the lease first and release
it in a `finally`/trap:

```bash
cd frontend
python D:/others/Jity/.local/parallel-local-game/resource_lease.py acquire \
  --lane 02-narration --purpose "real narration strategy probe"
trap 'python D:/others/Jity/.local/parallel-local-game/resource_lease.py release --lane 02-narration' EXIT
MSYS_NO_PATHCONV=1 node scripts/parallel-narration/run-real-narration.mjs \
  --model /models/qwen25-0.5b-narration-Q4_K_M.gguf \
  --out ../../../results/02-narration/real-model-legacy.json
```

Useful flags: `--threads`, `--max-tokens`, `--max-attempts`, `--min-chars`,
`--instruction "<caller task text>"`, `--channel`.

The GGUF and wllama assets are NOT in this worktree. The script serves them
from `MODEL_DIR` (default: the integration worktree's `frontend/public/models`)
and `node_modules/@wllama/wllama/esm`, without copying either into the
repository.

## What is recorded

For every scenario and every attempt: the exact prompt, raw completion,
cleaned text, finish reason, error, per-attempt wall time, first-token time,
streaming event count, `accepted`, and the full issue list (hard and soft), plus
the grader's coverage/violations/unverified/repetition. The scenario's ledger
(mandatory facts, licensed names, event license, time requirement) and the
end-to-end timings are recorded too. A failed run still writes a `FAILED`
record with the error.

## What it does not prove

Three scenarios on one checkpoint do not prove style quality, and an accepted
draft here is not a 35-case acceptance. Read the evidence for which facts were
missing or invented; do not treat a green `accepted` as a human quality review.
