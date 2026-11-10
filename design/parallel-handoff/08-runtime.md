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
   OPFS/direct-blob mode, fetch/compile/total timings, `fromCache` (a
   hard-stop reload reused the fetched Blob, so fetchMs is 0) and outcome.
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
  loadTimeoutMs?: number,           // default 120000; timeout exits the landing worker
  expectedBytes?: number | number[],// per-shard fetched size check before wllama
  onEvidence?: (record: ModelLoadEvidence | GenerationEvidence) => void,
});
engine.load({ signal?, modelUrl? }): Promise<void>;   // unchanged contract
engine.ensureLoaded({ signal?, modelUrl? }): Promise<void>; // NEW: reload last model after a hard stop
engine.complete(prompt, options?): Promise<string>;   // unchanged contract; onCompletion unchanged
engine.chat(messages, options?): Promise<string>;     // NEW: real system turn for instruct models
engine.cancelActive(): number;      // NEW: stop running generations AND an in-flight load; keep the engine usable
engine.cancelLoad(): boolean;       // NEW: stop only the load; retryable
engine.dispose(): Promise<void>;    // terminal, idempotent
engine.diagnostics;                 // UNCHANGED shape {multithread,numThreads}|null
engine.runtime;                     // NEW: {backend,modelId,loaded,contextSize,gpuLayers,loadCount,hardStops,activeCalls,generations,workersCreated,workersExited,disposed,needsReload,lastModelUrl}
```

## Product runtime contract (reorganization 2026-11-10)

The model that is actually deployable on this machine, with the template that
was used in the real accepted runs:

| item | value |
|---|---|
| model | `qwen3-1.7b-q4km` = `Qwen3-1.7B-Q4_K_M.gguf`, SHA-256 `b139949c5bd74937ad8ed8c8cf3d9ffb1e99c866c823204dc42c0d91fa181897`, 1,107,409,472 bytes |
| path used by the real runs | `D:/others/Jity/.local/world-narration-worktree/frontend/public/models/Qwen3-1.7B-Q4_K_M.gguf` (read-only; 09 serves it from its own tree as `/models/Qwen3-1.7B-Q4_K_M.gguf`) |
| template | Qwen3 ChatML with `enable_thinking:false`; wllama applies the GGUF's own Jinja template. The residual `<think>` block is stripped by `ThinkingFilter` in `model-runtime/template.ts` |
| engine | `WllamaInferenceEngine` with `nGpuLayers: 99999`, `contextSize: 4096`, `directBlob` in browser, Edge `--force_high_performance_gpu` |
| adapter proof | `ggml_webgpu: adapter_info: vendor: nvidia | architecture: lovelace` plus `navigator.gpu.requestAdapter()` reporting `nvidia / lovelace`; `--gpu`/`nGpuLayers` alone is not proof |
| load time | 32-46 s cold on the RTX 4060 Laptop, one load reused across the following turns |
| generation | dev points first readable 1.5-2.2 s, 8-11 s wall; free-day opening first readable 15-27 s, 26-47 s wall |
| quality | NOT passed. Automatic fact checks accepted some runs, but the user/product review found gender, invented footsteps, item misattribution and cross-turn repetition in the same accepted texts. 02 owns generation, 01 owns quality; this lane only supplies the runtime/model |

Runtime states and what the page should do:

- `runtime.loaded === true`: the same weights are usable; do not reload per turn.
- `runtime.needsReload === true` (a timeout/cancel terminated the worker; the
  url is still known): call `await engine.ensureLoaded()` before the next
  turn. This is the same weights, not a silent model switch.
- `ensureLoaded({modelUrl})` with a different url while loaded throws: a
  request must not silently change weights mid-session.
- `cancelLoad()` stops the first 30-46 s of a cold session and remains
  retryable; `cancelActive()` stops both the load and running generations.
- `loadTimeoutMs` (default 120000) bounds the load; on expiry the landing
  worker is terminated, the load rejects with `name: 'TimeoutError'`, and the
  next `ensureLoaded()` starts a fresh worker. The page must show a retry,
  not a frozen turn.
- `workersCreated` / `workersExited` are the leak counters; across N turns
  with one load they stay at 1/0, and `dispose()` brings them to 1/1.
- `generations` counts model calls served by this engine, so a 10-turn log
  can show `generations: 10, loadCount: 1`.
- The engine holds no conversation state: the caller passes the full message
  list on every `chat()`. After a reload the KV cache is empty and the first
  call re-prefills; the page must keep the transcript, not assume the engine
  remembers the previous turn.
- Cold-start budget: the product target is submission-to-first-readable
  <= 60 s. The measured free-day opening was 39 s load + 15-27 s to first
  readable, i.e. 54-66 s if the load is inside the first submission. The page
  must start `ensureLoaded()` when the world opens (before the player submits)
  and show load progress; otherwise a cold free-day turn is at/over the
  budget. This is a page/06 requirement; the runtime exposes the split. The
  load itself is not shortened by the engine beyond the direct-blob path and
  the `loadTimeoutMs` bound.

## Ready / draft / verified timing (acceptance 2026-11-10)

The acceptance text forbids counting an unverified first token as the 60-second
"readable prose" pass. The runtime and the candidate now expose three distinct
timestamps:

| field | meaning | where |
|---|---|---|
| `GenerationEvidence.firstReadableMs` | first non-whitespace streamed fragment (may be a draft that later fails facts) | engine |
| `CandidateResult.timings.firstReadableMs` | same, per point, across all attempts | candidate |
| `CandidateResult.timings.acceptedFirstReadableMs` | first readable text **of the attempt that passed fact verification**; null if no attempt was accepted | candidate |
| `CandidateResult.timings.acceptedReadableMs` | when the accepted text finished verification (the first fact-verified prose the player can be shown); null if rejected | candidate |

09 must report `acceptedReadableMs` (or both accepted fields) for the 60 s /
300 s budget, and may report `firstReadableMs` only as draft latency.

**Ready gate:** `complete()` / `chat()` throw `wllama engine is not loaded`
synchronously when the engine is not ready — they never wait for a model
timeout (the old 152-second wait was a retry into a dead worker, fixed earlier).
The driver must `await engine.ensureLoaded()` (or `load()`) before generation;
a load failure is a request failure, not a generation timeout. Recovery is
explicit and bounded: at most one reload per request through `ensureLoaded()`;
there is no automatic reload loop, and a reload never switches weights because
a different URL throws while a model is loaded.

**4B split status:** the interface and files exist, both shards fetch as
`arrayBuffer` in Edge, and native llama.cpp loads/generates from them. That is
not browser proof. The 4B is not deployable or recommended until 09 records a
real load/generation with adapter and timings.

**Exploration lanes:** 11/12 do not get runtime priority. Their candidates reach
09 only after 10's offline screening and preregistration; 08 only supplies the
load/cancel/timing contract above, and does not take the 4060 ahead of the
product queue.

**Hard constraints for 11 model search** (checked before any 09 request):
GGUF readable by llama.cpp/wllama 3.8.1, a usable chat template (or an explicit
known template id), a license compatible with the product, and **total model
bytes ≲2 GB**, because the browser's Blob store fails when the aggregate held
by wllama exceeds roughly 2 GB (measured: 1.3 GB blob OK, +1.2 GB fails; 2.5 GB
single file fails). Splitting below 2 GiB per shard does **not** bypass the
aggregate cap. 11's 1.5 GB gate is aligned; the measured 1.7B Q4 is 1.11 GB.
The runtime does not accept safetensors, custom kernels, or a model that needs
a different engine.

**Queue/acceptance contract for 09** (one run, one request):
1. Resolve the model path, file size and SHA-256; confirm the declared catalog
   entry/template. A mismatch is a request failure, not a quality result.
2. `await engine.ensureLoaded()` with the load budget (120 s default; the page
   now sets 120 s). Pass `expectedBytes` for the known file/shard sizes so a
   truncated fetch fails before wllama parses it. On failure: `dispose()` the
   engine, release the lease in `finally`, record the failure; do not enter
   generation. The full SHA-256 check stays on the host/queue side (09 hashes
   the served file); hashing 1.1 GB in the page would double the read.
3. Generation: pass a deadline/signal; `complete`/`chat` before ready throw
   immediately instead of waiting. Cancellation settles only after the device
   stops (or the worker is terminated).
4. After a timeout/cancel hard stop: at most one explicit `ensureLoaded()` for
   the next request, same URL. No automatic reload loop, no silent weight
   switch.
5. Report `acceptedReadableMs` (fact-verified) separately from
   `firstReadableMs` (draft), plus load / first token / per-turn / whole
   submission. Dispose engines at the end and check
   `workersCreated === workersExited`.
6. Long-session growth (the 10→20-turn requirement): on the product page read
   `window.__worldTurns`. Within one page segment, a healthy run has, per
   engine, `loadCount === 1`, `workersCreated === 1`, `workersExited === 0`,
   `generations === turns`, and `cachedModelBytes` constant. A deliberate
   refresh (the 10-turn script refreshes after t6) starts a **new page**: it
   legitimately creates one new load/worker for each engine and resets the
   window counters; record the pre-refresh and post-refresh segments
   separately, and do not count that new load as a leak. If a turn hard
   stopped inside a segment, expect `loadCount`/`workersCreated` to increase by
   exactly one and the reload evidence `fromCache: true, fetchMs: 0`; any other
   growth is a leak/reload bug, not a quality result. Record the per-turn
   `acceptedMs`/`draftMs`/`programMs`, the stop latency, and (if exposed)
   `promptTokens` vs `contextSize`; a prompt near the context limit needs a
   larger context or trimming, not a model change.
7. Readiness: before the first submission the page must be `ready` and both
   engines `loaded` (the submit button is disabled while loading). A
   `complete`/`chat` before load must reject immediately; it must never wait
   for the 120 s load deadline (the `complete-before-ready` check proves this).
8. Server readiness: Next dev returns **500 Internal Server Error on every
   route while it is still starting/compiling** after a clean `.next` (observed
   13:02–13:17, then 200 after `Ready in 7.7 s` and `Compiled / in 55.3 s`).
   Wait for `GET /world-local` to return 200 and a textarea to render before
   launching the browser; a run against the 500 is an invalid startup record,
   not a product result. A `next build` sharing `.next` with the live dev
   server can also corrupt it; stop/clean/restart after a build.
9. Fresh-run isolation: clearing only `localStorage` is not a fresh run. The
   page persists through IndexedDB (and may use Cache Storage/OPFS); a stale
   record makes the first save stop with `progress_conflict`. The runner must
   delete every IndexedDB database plus Cache Storage/OPFS and assert they are
   empty before loading the page. A stop must also end the turn visibly: clear
   the busy/stage state and show a message, or the acceptance waits until its
   whole-turn timeout even though the turn ended in 168 ms (observed in the
   first official 10-turn attempt; neither engine had failed).

## Load-timing reconciliation (2026-11-10)

The same 1.7B has recorded loads of 174.5 s (02 probe, no adapter proof,
no fetch/compile split), 44.7 s (08 candidate, NVIDIA proof, no split) and
70.0 s (09 runtime, NVIDIA proof, fetch 52.6 + compile 17.3). Same sha256,
context 4096, ngl 99999, threads 6. The 174.5 s is **not** a valid NVIDIA
cold-load fact; the 44.7 vs 70 gap is not attributed because 08's split is
missing. Full table and unknowns: `results/quality/load-reconciliation-08.md`.
Use the existing candidate runner with `--load-only` for one split load
(no generation, no new runner): `results/product/browser-requests/08-runtime-load-reconcile.json`.
Cold-load differences do not prove hot-generation failure.

### 10-turn runtime observation (2026-11-10T13:34Z)

`results/product/evidence/09-product-10turn.json` FAILED on content/lifecycle,
not on loading: both engines held `loadCount=1`, `workersCreated=1`,
`workersExited=0` across t1/t2; no hard stop, reload or worker leak. t1 took
272 s and made 14 semantic + 4 narration calls before a labelled program
fallback (undeclared target / unknown id / coverage); t2 then stopped in 158 ms
with `turn_in_progress` and 0 model calls, but the page stayed
`结算中：继续判断` for the 330 s harness timeout. Do not attribute these to the
runtime; 04/03 own the settlement/action failures and 06 owns the visible stop
and retry path. The runtime load/worker contract held.

## 02/06 integration entry points

- 06 per-engine load timing: include `lastLoadMs`, `lastLoadFetchMs`,
  `lastLoadCompileMs`, `lastLoadFromCache` from `engine.runtime` in
  `window.__worldTurns[i].engines`. The page-level ready time mixes page boot,
  two model loads and StrictMode; 09 needs the per-engine split to separate
  cold load from per-turn prefill/decode.
- Dev ready was ~142 s twice while per-engine loads summed 102 s then 61 s.
  That was StrictMode: the first mount started both loads, cleanup disposed
  them, the second mount started both again, and `__worldTurns` only saw the
  last engines. 06's `42712bc9` now restores state/history before the load and
  gates the cold load behind a 200 ms timer that the probe mount's cleanup
  cancels; verify the next ready reflects one round, not 142 s. Do not report
  the old dev ready as one model load.
- 94.9 s is one specified cold-load measurement (1.7B, load-only, NVIDIA
  proof), not a universal load time. The same product 1.5B narration measured
  38.1 s and 79.6 s in two runs. Use per-engine `lastLoad*` and observed
  ranges; prioritize same-instance reload/cache/restore lifecycle over another
  model sweep.
- 06 product page / game-model: construct one engine and call
  `await engine.ensureLoaded()` at session start, `engine.chat(messages, {signal,
  timeoutMs, maxTokens, temperature, onProgress})` per narration call,
  `engine.cancelActive()` from the stop button, `engine.dispose()` on leaving
  the world. For the candidate module use
  `generateCandidate({engine, committed, inputText, policy, onProgress, signal})`.
- 02 generation: `narration-candidates/model-runtime/` is the reference
  candidate (scene-first prompt, prose fact projection, repair with the prior
  draft, thinking strip). Its `NARRATOR_SYSTEM_PROMPT`, `renderNarrationUser`
  and `projectProseFacts` are the parts to compare against the training route;
  the engine/template above is fixed and should not be re-derived per run.
- 4B whole-file retry is closed: the 2.5 GB single GGUF fails `arrayBuffer()`
  in wllama 3.8.1 on both WebGPU and CPU. A **split-GGUF path now exists with
  technical feasibility evidence**, but it has not been browser-run yet:
  - `llama-gguf-split` 0.5.0-dev (build 11364) split the Q4_K_M into
    `...-00001-of-00002.gguf` (1,305,220,960 B, sha256 `a9a9557a…`) and
    `...-00002-of-00002.gguf` (1,192,060,352 B, sha256 `67020100…`), both
    under the 2 GiB whole-file limit. Metadata in shard 1 carries
    `split.count/split.no/split.tensors.count` and the chat template;
    shard 2 carries the remaining tensors.
  - the shards load and generate natively: `llama-cli -m <shard1> -p "用一句
    中文描写雨。" -n 8 -c 2048 -ngl 0` produced `雨丝如织，轻轻敲打着`
    (CPU 4.6 tok/s; the first attempt with the default 262144 context failed
    to allocate compute buffers, so a 2048-4096 context is required).
  - wllama 3.8.1 explicitly accepts multiple blobs (`loadModel`), renames them
    to its canonical `model-00001-of-00002.gguf` names, and passes every path
    to llama.cpp, which opens the siblings by that same naming.
  - this engine now expands one `-00001-of-00002.gguf` URL to all shards
    (per-call `modelUrl` or `modelUrls`), fetches every shard in the directBlob
    path, and unit tests cover two-blob load, auto-expansion, per-shard reload
    after a hard stop, and a clear error when the non-blob path sees a split.
  - **closed negative**: a fresh-page probe (`probe-two-shards.mjs`, blob
    mode, Edge 157) fetched shard 1 into a 1.305 GB Blob successfully
    (48.6 s), then shard 2 (HTTP 200, 1.192 GB) failed with
    `TypeError: Failed to fetch` after 34.2 s. `navigator.storage.quota` was
    10 GiB and the JS heap was ~1 MB, so the limit is the browser's Blob
    store (~2 GB aggregate), not disk or heap. wllama holds every shard as a
    Blob until loadModel finishes, so splitting does not make a 2.5 GB model
    loadable. The same probe in `arraybuffer` mode held both (2.38 GB heap of
    4.19 GB) but took 142.5 s + 140.3 s to fetch — already over the 300 s
    point budget before compile. **Do not propose, quantize or run a >2 GB
    total model on this Blob path.** A streaming/OPFS/FS-write loader is a
    separate project with no implementation.
  - 09's browser attempt matched this: shard 1 and shard 2 responses both 200,
    shard 2's body failed, and the retry failed even on shard 1 (Blob pressure
    persisted). The 4B split request is now closed; the shard files remain at
    `.local/models/qwen3-4b-split/` only as evidence and may be deleted.

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
// summary.loads.cached counts hard-stop reloads that reused the fetched Blob.
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
   happens, `engine.runtime.loaded === false` and `runtime.needsReload === true`;
   call `await engine.ensureLoaded()` before the next turn (same weights, one
   compile) instead of constructing a second engine. A direct `load()` without
   a url also falls back to the last attempted model, so a per-call url is not
   lost after a hard stop.

   **Cached weights.** The engine keeps the fetched model Blob(s) and feeds the
   same bytes to the new worker on reload (`runtime.cachedModel`,
   `runtime.cachedModelBytes`, `runtime.lastLoadFromCache`; load evidence
   `fromCache: true`, `fetchMs: 0`). The last successful load split is exposed
   as `runtime.lastLoadMs`, `lastLoadFetchMs`, `lastLoadCompileMs`; the page
   should put these in `window.__worldTurns[i].engines` so 09 can separate
   cold load from generation time.
   This is not an optimization detail; the real browser rejected a second
   1.1 GB fetch immediately after a hard stop with `TypeError: Failed to fetch`
   because the first Blob was still in the browser's Blob store, whose
   aggregate cap is about 2 GB (the same cap that closed the 4B path). A cached
   reload is compile-only and does not allocate a second Blob. `dispose()`
   clears the cache. `loadModel` failure on a cached Blob drops the cache, so a
   caller retry refetches for real.

   Consequence for sizing: all cached model bytes of the page count against
   that aggregate cap (0.6B + 1.5B ≈ 1.4 GB; fine). Do not keep a second large
   model cached, and keep total cached bytes well under 2 GB.

   Hard-stop checkpoint for 09 (not a new sweep; run when the shared queue has
   room): fresh page, load 1.7B, force `abortGraceMs 0` plus a short timeout,
   then `ensureLoaded()`. Expect `loadCount` 1→2, `fromCache: true`,
   `fetchMs: 0`, `cachedModelBytes` equal to the model size, and a working next
   generation.

6. `onCompletion` still receives `CompletionEvidence`. To read the new fields,
   import `GenerationEvidence` and cast (they are present at runtime):
   `firstChunkMs`, `firstReadableMs`, `maxStreamGapMs`, `streamChunks`,
   `promptTokens`, `cachedPromptTokens`, `abortCause`, `abortRequestedMs`,
   `stoppedMs`, `hardStopped`, `outcome`.

7. `LocalGameModel.narration` currently fabricates a `CompletionEvidence` with
   `firstTokenMs: null` for `onNarrationComplete`. To preserve the runtime
   timings end to end, pass `onCompletion: (evidence) => { completion =
   evidence; }` to the narration `complete` call and forward the measured
   fields (at least `firstTokenMs`, `usage`, `timings`) while keeping the
   validation verdict as `finishReason`. This is a main-owned-file change; the
   engine already emits the real values.

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
node scripts/parallel-runtime/measure-wllama.mjs --out ../.local/parallel-runtime/measure-final.json
```

Final run bound to commit `91136ede` (Edge 157.0.4341.42, Qwen3-0.6B-Q4_K_M,
context 2048, 4 threads, WebGPU, crossOriginIsolated): load 20.3 s = 9.2 s
fetch + 11.1 s compile (`Cache-Control: no-store`, first network acquisition;
three runs measured 14.3 s, 43.2 s and 20.3 s total — localhost transfer and
compile vary, so treat the split, not one total, as the finding); duplicate
`load()` 0.085 ms; first readable p50 732 ms (380–1292 ms over 6 streaming
calls); whole output p50 1.81 s (0.77–3.13 s); worst stream gap 225 ms;
7 generations = 5 completed, 1 aborted, 1 timeout, 0 errors. Warmed call
reused 40 cached prompt tokens (prompt_n 1), first readable 1292 ms → 380 ms.
Caller abort settled in 5 ms (evidence `stoppedMs` 4.6 ms), partial text kept,
next generation succeeded, no hard stop. 250 ms deadline stopped after 517 ms
(`stoppedMs`), model stayed loaded. Dispose 0.49 ms / second call 0.02 ms /
terminal. Queue: 0.2 ms wait, 2.6 s run.

Raw report: `D:/others/Jity/.local/parallel-local-game/worktrees/08-runtime/.local/parallel-runtime/measure-final.json`
(earlier runs kept as `measure-run1.json` and `measure.json`). The report binds
source digests, model/bundle/wasm hashes and the git status; `source.head` is
`91136ede` and only the untracked private goal doc appears in `git status`.

Real hard-stop run bound to `3fee94c7` (`--hard-stop`, report
`.local/parallel-runtime/measure-hardstop.json`): a second engine with
`abortGraceMs: 0` was aborted 10 ms into a long generation; the worker was
terminated, `completion.hardStopped` is true, `stoppedMs` 0.69 ms,
`runtime.loaded` false and `modelId` null. Reload took 17.0 s; the recovery
generation produced 17 characters with first readable at 912 ms. This is the
real-device proof of the termination path, not only the native cooperative
cancel (which still stops in ~5 ms and keeps the model loaded).

## Limitations / follow-ups

- The probe measures first network acquisition (no-store) plus direct-blob
  compile; it does not measure a warm page reload with HTTP/OPFS cache. The page
  currently uses `directBlob`, so a refresh re-fetches the GGUF; separating
  "first fetch" from "cached start" remains a page-level task.
- Two models are loaded sequentially by the page; observed single-model loads
  were 14.3–43.2 s across runs, not the whole page budget. The deadline is not
  a hard wall: native cancel can only act at the next result chunk (517 ms in
  the final run).
- Hard stop drops the loaded model and costs a compile-only reload (no refetch
  now that the fetched Blob is cached); a page must show a reload state or use
  the model-port path, which reloads automatically. The native cooperative
  cancel is much cheaper and is the normal path. Browser proof of the cached
  hard-stop reload is still pending 09 (see the checkpoint above).
- The page/game-model are not wired in this lane. `LocalGameModel` calls
  `complete` without a signal for most tasks (especially narration), so the
  page must use `cancelActive()` for the stop button (or thread a signal
  through game-model/controller later).
- `RuntimeWorldModelPort` still reloads per generation by design; the engine
  memo makes it cheap, but queue events will show a `load:` entry per call.
- Context use is recorded as `contextSize` plus the actual prompt/cache token
  counts (41 prompt tokens against 2048 in the cited runs). wllama 3.8.1 has no
  public tokenizer, so the engine cannot preflight an over-long prompt; it never
  truncates the prompt itself and leaves overflow handling to llama.cpp. The
  real runs only produced `finishReason: 'stop'`; length/missing-finish
  rejection is covered by the fake-runner tests.
