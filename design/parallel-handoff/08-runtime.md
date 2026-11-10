# 08-runtime handoff

Branch `goal/local-08-runtime`, base `865ae64e0901a70c3db4f1d0eb2af60268943c53`.
Scope: the existing wllama adapter, the serial inference queue, runtime
diagnostics and the parallel-runtime probe. `runtime/engine.ts`,
`local/game-model.ts`, the page, `controller.ts`/`schedule.ts`/`types.ts` and
dependencies are untouched.

## Problems fixed

1. **Cancellation did not guarantee a stop.** `complete()` forwarded the signal
   to wllama but disposed the worker only after the native promise settled; a
   stuck native step could keep computing indefinitely. The engine now starts
   an `abortGraceMs` timer on every abort (caller, deadline or dispose). If the
   native path has not settled by then, it terminates the worker with
   `exit()` — which the wllama worker implements as `worker.terminate()` — and
   only after that confirms the stop does the caller settle. A terminated
   worker drops the model (`runtime.loaded=false`); the next `load()` starts
   fresh. A cooperative native abort settles as before, with no reload.
2. **Abort evidence was opaque.** Every generation now records first chunk,
   first token, first readable text, stream chunk count, longest stream gap,
   abort cause, abort-request→confirmed-stop latency, hard-stop flag, prompt
   tokens, cached prompt tokens, context size and cache flag. The shared
   `CompletionEvidence` fields are unchanged; the additions are in our own
   `GenerationEvidence` type.
3. **Dispose could leak a factory instance and did not abort generations
   first.** Failed/cancelled loads now `exit()` the instance produced by the
   factory, so a failed WebGPU attempt cannot leave a wasm worker and its model
   buffers alive across a CPU retry. `dispose()` aborts active generations
   before terminating the worker, waits for their finally/evidence paths, is
   idempotent, and never registers an instance that lands after disposal.
4. **Load identity was silent.** `load()` is memoised, but a call with a
   different model URL used to return success while the old model stayed
   loaded. It now rejects with an explicit configuration error (same URL stays
   idempotent); concurrent loads of different URLs are rejected too. Load
   evidence records `modelId`, URL, context size, GPU layers, threads,
   OPFS/direct-blob mode, fetch/compile/total timings and outcome.
5. **The queue had no non-terminal stop and no abort timing.** Added
   `cancelPending()` (reject queued, abort running, keep the queue usable),
   queue evidence (`queued/started/resolved/rejected/aborted-running/stopped/
   disposed`), stats, and the abort→device-stop latency on `stopped`. Rejection
   errors carry a best-effort `timing` (the event stream carries per-entry
   timings even when one reason object is shared). Dispose is idempotent.
6. **No trustworthy stage timing exists for the page.** Added a bounded
   `RuntimeDiagnostics` recorder (loads/generations/cancellations/queue,
   p50/p95/max) and `StageTimer` (marks, per-chunk ticks, longest silence).
   Both export plain JSON. The probe in `scripts/parallel-runtime/` drives the
   real engine and prints/lists the same evidence.

## Exported API (all additive; old calls keep working)

`frontend/src/lib/world-engine/runtime/wllama-engine.ts`

```ts
new WllamaInferenceEngine({
  modelUrl, contextSize, numThreads, nGpuLayers, useCache, directBlob,
  abortGraceMs?: number,            // default 2500; 0 = terminate on abort at once
  onEvidence?: (record: ModelLoadEvidence | GenerationEvidence) => void,
});
engine.load({ signal?, modelUrl? }): Promise<void>;   // unchanged contract
engine.complete(prompt, options?): Promise<string>;   // unchanged contract; onCompletion unchanged
engine.cancelActive(): number;      // NEW: stop running generations, keep the engine loaded
engine.dispose(): Promise<void>;    // terminal, idempotent
engine.diagnostics;                 // UNCHANGED shape {multithread,numThreads}|null
engine.runtime;                     // NEW: {backend,modelId,loaded,contextSize,gpuLayers,loadCount,hardStops,activeCalls}
```

`frontend/src/lib/world-engine/runtime/inference-queue.ts`

```ts
new SerialInferenceQueue(onEvent?: (event: QueueEvidence) => void);
queue.run(entry): Promise<QueuedResult<T>>; // unchanged
queue.cancelPending(reason?: unknown): void; // NEW: pause/cancel without closing
queue.dispose(): void;                      // unchanged semantics, idempotent
queue.stats;                                // NEW
```

`frontend/src/lib/world-engine/local/runtime-diagnostics/index.ts`

```ts
new RuntimeDiagnostics({ limit?: number });
diagnostics.record / onLoad / onGeneration / onQueue; // bound handlers
diagnostics.summary(); diagnostics.snapshot(); diagnostics.toJSON();
new StageTimer(now?);
timer.mark(stage, detail?); timer.tick(); timer.maxGapMs; timer.snapshot();
```

Evidence types (`ModelLoadEvidence`, `GenerationEvidence`, `QueueEvidence`,
`RuntimeDiagnosticsSummary`) live in `runtime-diagnostics/types.ts`.

## Main-agent wiring (small, page/game-model side)

1. Create one recorder and one timer per page session, and pass the recorder
   into both engine constructors (the page's `loadEngine` helper needs the
   recorder as an argument or a module-level instance):

```ts
const diagnostics = new RuntimeDiagnostics({ limit: 512 });
const timer = new StageTimer();
const engine = new WllamaInferenceEngine({ ..., onEvidence: diagnostics.record });
```

2. Stop button: the page already holds the engines, so cancellation needs no
   controller/game-model change:

```ts
const stopped = semanticRef.current?.cancelActive() ?? 0;
narrationRef.current?.cancelActive();
queueRef.current?.cancelPending(); // if a RuntimeWorldModelPort queue is used
```

The running `complete` rejects with `AbortError`; the device work has either
been natively cancelled (usually milliseconds) or the worker was terminated
after the grace period. `cancelActive` returns how many calls were asked to
stop.

3. Stage timing: mark `model-ready`, `action-submitted`, `first-readable`
   (first non-empty `onNarrationProgress` raw), `segment-complete`; call
   `timer.tick()` on every progress chunk. Export
   `{ diagnostics: diagnostics.snapshot(), stages: timer.snapshot() }` with the
   debug log. `StageTimer.maxGapMs` is the worst silence; include the initial
   load as a mark if the waiting budget should start at page open.

4. Queue path (`RuntimeWorldModelPort`): construct the queue with the recorder
   (`new SerialInferenceQueue(diagnostics.record)`). `generateDetailed` already
   queues `load` before every generation, so a hard-stopped model recovers
   automatically. For a pause button call `queue.cancelPending()`; for page
   unload call `queue.dispose()` then `engine.dispose()`.

5. Hard stop is rare (native abort did not settle within `abortGraceMs`). If it
   happens, `engine.runtime.loaded === false`; the next direct `load()` pays the
   model compile again. The model-port path reloads by itself; a direct
   game-model call should check `runtime.loaded` and show a reload state.

6. `onCompletion` still receives `CompletionEvidence`. To read the new fields,
   import `GenerationEvidence` and cast (they are present at runtime):
   `firstChunkMs`, `firstReadableMs`, `maxStreamGapMs`, `streamChunks`,
   `promptTokens`, `cachedPromptTokens`, `abortCause`, `abortRequestedMs`,
   `stoppedMs`, `hardStopped`, `outcome`.

## Verification

Mock tests (Node, fake wllama; no GPU/speed claim):

```bash
cd frontend
npx vitest run src/lib/world-engine/runtime/wllama-engine.test.ts      # 20 passed
npx vitest run src/lib/world-engine/runtime/inference-queue.test.ts   # 13 passed
npx vitest run src/lib/world-engine/local/runtime-diagnostics         # 9 passed
npx vitest run src/lib/world-engine/runtime/b3.test.ts \
  src/lib/world-engine/runtime/model-port.test.ts \
  src/lib/world-engine/runtime/heartbeat.test.ts                      # 35 passed
npx tsc --noEmit -p tsconfig.json
npx eslint <the changed runtime/diagnostics files>
```

Covers: load idempotency and identity conflict, load abort/cleanup/retry,
dispose mid-load and mid-generation, direct-blob split, first-readable vs first
token, deadline/native abort, **hard stop only after worker termination + reload**,
`cancelActive`, cache/context evidence, queue FIFO/cancel/dispose/evidence,
recorder bounds/percentiles, stage gaps.

Real browser (leased `08-runtime`; Edge headless, WebGPU, COOP/COEP):

```bash
cd frontend
node scripts/parallel-runtime/measure-wllama.mjs --out ../.local/parallel-runtime/measure.json
```

Final run (Edge 157.0.4341.42, Qwen3-0.6B-Q4_K_M, context 2048, 4 threads,
WebGPU, crossOriginIsolated): load 43.2 s = 33.3 s fetch + 9.9 s compile
(`Cache-Control: no-store`, first network acquisition; the first run measured
8.0 s + 6.3 s — localhost transfer varies); duplicate `load()` 0.04 ms;
first readable p50 657 ms (296–1122 ms over 6 streaming calls); whole output
p50 1.67 s (0.76–2.59 s); worst stream gap 182 ms; 7 generations = 5 completed,
1 aborted, 1 timeout, 0 errors. Warmed call reused 40 cached prompt tokens
(prompt_n 1), first readable 1122 ms → 296 ms. Caller abort settled in 15.5 ms
(evidence `stoppedMs` 2.2 ms), partial text kept, next generation succeeded,
no hard stop. 250 ms deadline stopped after 496 ms (`stoppedMs`), model stayed
loaded. Dispose 0.13 ms / second call 0 ms / terminal. Queue: 0.4 ms wait,
1.67 s run.

Raw report: `D:/others/Jity/.local/parallel-local-game/worktrees/08-runtime/.local/parallel-runtime/measure.json`
(first run kept as `measure-run1.json`). The report binds source digests,
model/bundle/wasm hashes and the git status.

## Limitations / follow-ups

- The probe measures first network acquisition (no-store) plus direct-blob
  compile; it does not measure a warm page reload with HTTP/OPFS cache. The page
  currently uses `directBlob`, so a refresh re-fetches the GGUF; separating
  "first fetch" from "cached start" remains a page-level task.
- Two models are loaded sequentially by the page; the observed 43 s is one
  model on this run, not the whole page budget. The deadline is not a hard
  wall: native cancel can only act at the next result chunk (496 ms here).
- Hard stop drops the loaded model; its real reload cost is covered by mocks,
  not by a real stuck-device run.
- The page/game-model are not wired in this lane. `LocalGameModel` calls
  `complete` without a signal for most tasks (especially narration), so the
  page must use `cancelActive()` for the stop button (or thread a signal
  through game-model/controller later).
- `RuntimeWorldModelPort` still reloads per generation by design; the engine
  memo makes it cheap, but queue events will show a `load:` entry per call.
