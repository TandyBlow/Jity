# Runtime probe (08-runtime)

Real-browser evidence for the wllama adapter, the serial inference queue and
the stage-timing recorder. This script measures the device, not game quality.

## What it measures

- model load: WebGPU attempt, CPU fallback attempt, fetch vs compile split,
  duplicate `load()` cost, load identity/config in the evidence;
- real streaming: first onData chunk, first token, first **readable** text,
  stream chunk count, longest silence between chunks, whole segment wall time,
  prompt tokens and prompt-cache reuse;
- cancellation: abort as soon as readable text arrives, abort→settle latency,
  partial text retained, and an immediate follow-up generation on the same
  engine (busy-state check);
- deadline: `timeoutMs` abort, whether the native cancel settled or the worker
  had to be terminated (`hardStopped`), and whether a reload is required;
- queue: one queued generation through `SerialInferenceQueue`, with queue-wait
  and run-time evidence;
- dispose: first and second `dispose()` cost and terminal state.

The result JSON also contains the recorder snapshot (every load/generation/
queue event) and the source/model/wllama digests, so the numbers can be tied
to exact files.

## Run

Models are read read-only from the shared directory and served by the probe's
Vite middleware; nothing is copied into this worktree.

```bash
# from frontend/
python ../../.local/parallel-local-game/resource_lease.py acquire --lane 08-runtime --purpose "real wllama runtime probe"
node scripts/parallel-runtime/measure-wllama.mjs --out ../.local/parallel-runtime/measure.json
python ../../.local/parallel-local-game/resource_lease.py release --lane 08-runtime
```

Release the lease even when the run fails. Defaults: `Qwen3-0.6B-Q4_K_M.gguf`,
context 2048, 4 threads, 48 short-output tokens, 250 ms deadline, 2500 ms abort
grace. Override with `--model`, `--models`, `--context`, `--threads`,
`--max-tokens`, `--deadline-ms`, `--abort-grace-ms`, `--channel`, `--out`.

## Reading the output

`result.diagnostics.summary` separates `loads`, `generations`,
`cancellations` and `queue`. The raw records keep per-call values. Important
fields:

- `abortToSettleMs` / `completion.stoppedMs`: abort request → the engine
  promise settled (native cancel) or the worker was terminated (hard stop).
- `completion.hardStopped`: true only when the worker had to be terminated.
- `deadline.runtimeAfter.loaded`: false means the hard stop dropped the model;
  `timings.reloadAfterDeadlineMs` is the recovery cost.
- `samples[*].completion.cachedPromptTokens` / `promptTokens`: prompt-cache
  reuse on a warmed engine; the summary's `meanCacheHitRatio` is
  `cached / (processed + cached)`.
- `timer.maxGapMs`: worst tick/mark gap over the probe. The probe does not
  mark page stages, so this value includes the initial load wait; the page
  wiring should mark `model-ready`, `action-submitted` and `first-readable`.

A deadline is not a hard wall: the native cancel can only act at the
next result chunk, so `deadline.completion.stoppedMs` is the actual
abort→stop latency. If it ever exceeds `--abort-grace-ms`, the worker is
terminated (`hardStopped: true`) and `deadline.runtimeAfter.loaded` becomes
false; the next `load()` pays the model compile again.

## Scope

This is evidence for the runtime only. It does not benchmark narration
quality, does not replace the page acceptance, and must not be cited as a
whole-turn wait time: the page still has to wire the recorder/stop button and
the game-model call chain.
