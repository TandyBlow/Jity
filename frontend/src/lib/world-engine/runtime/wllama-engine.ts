/** wllama adapter. The engine is browser-only (the loader imports the built
 * bundle from /wllama at runtime); Node tests inject a fake instance through
 * the factory and only ever exercise option mapping and lifecycle, never the
 * wasm.
 *
 * Cancellation is forwarded natively: both loadModelFromUrl and
 * createChatCompletion take an abortSignal. If the native path does not
 * settle within `abortGraceMs` after an abort request, the worker is
 * terminated (`exit()`), which is the only way to stop a wasm call that is
 * already inside a long native step. A terminated worker is a real stop, so
 * the caller settles after it — not before — and the model is marked
 * unloaded; the next load() starts a fresh one. dispose() aborts the active
 * generation before exiting, is terminal and idempotent, and always exits an
 * instance that landed after disposal instead of registering it.
 *
 * Loads are memoised by identity. A second load() with the same model URL is
 * free; a different URL is a configuration error instead of silently reusing
 * the old model. A failed or cancelled load exits the factory instance so a
 * leaked worker cannot keep wasm memory alive across retries.
 *
 * `chat()` is additive next to the InferenceEngine contract: `complete()`
 * sends a single user turn, which makes an instruct checkpoint use its own
 * default system prompt. Narrative candidates need their own system turn
 * (2026-11-10 candidate-model registration), so `chat()` forwards a real
 * message list and shares the same cancellation/evidence path.
 */
import type { Wllama } from '@wllama/wllama';
import { createWllama } from '../../benchmark/wllama-loader';
import { abortError, IncompleteGenerationError, type CompletionEvidence, type CompleteOptions, type EngineInfo, type InferenceEngine } from './engine';
import type { AbortCause, GenerationEvidence, ModelLoadEvidence } from '../local/runtime-diagnostics/types';

/** A chat turn for `chat()`. Mirrors the parts of the OpenAI message shape
 * the wllama adapter forwards; the GGUF's own template decides the rendering. */
export interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface WllamaEngineOptions {
  /** Default model source for load(); a per-call modelUrl overrides it. */
  modelUrl?: string;
  /** Split GGUF shards, in order. Takes precedence over modelUrl. wllama
   * renames the blobs to its canonical `model-00001-of-00002.gguf` names and
   * llama.cpp opens the siblings from the same virtual directory. Only the
   * directBlob browser path supports more than one file in wllama 3.8.1. */
  modelUrls?: string[];
  contextSize?: number;
  numThreads?: number;
  /** 0 keeps CPU-only; default offloads every layer to WebGPU when the
   * browser exposes it. */
  nGpuLayers?: number;
  /** Keep the GGUF in OPFS across reloads. Off by default because a large
   * model plus the browser's temporary files can exhaust the origin quota. */
  useCache?: boolean;
  /** Fetch the GGUF into a Blob and hand it to wllama directly. Avoids the
   * OPFS cache write, which can fail on a nearly-full origin even when the
   * model itself fits. */
  directBlob?: boolean;
  /** How long an abort request may stay unhonoured before the worker is
   * terminated. Default 2500 ms; 0 terminates as soon as the abort is
   * requested. A terminated worker drops the loaded model. */
  abortGraceMs?: number;
  /** Upper bound for one model load (fetch + parse + compile). Default
   * 120000 ms. A timeout aborts the load and exits the landing worker, so a
   * page can retry instead of showing a frozen first turn forever. */
  loadTimeoutMs?: number;
  /** Expected fetched size(s) in bytes, one per shard. A truncated or wrong
   * file is rejected before it reaches wllama instead of failing deep inside
   * the GGUF parser. The SHA-256 check belongs to the queue/host runner; this
   * is the cheap size check the page can do itself. */
  expectedBytes?: number | number[];
  /** Observability hook for load and generation evidence. Own structure:
   * the shared CompletionEvidence fields stay unchanged and extra timing is
   * additive. Observer exceptions never change the call result. */
  onEvidence?: (record: ModelLoadEvidence | GenerationEvidence) => void;
}

interface LoadedIdentity {
  modelUrls: string[];
  identity: string;
  contextSize: number;
  gpuLayers: number;
}

interface ActiveCall {
  controller: AbortController;
  cause: AbortCause | null;
  abortRequestedAt: number | null;
  deadline: ReturnType<typeof setTimeout> | null;
  grace: ReturnType<typeof setTimeout> | null;
  hardStop: Promise<void> | null;
  hardStopped: boolean;
  /** Resolves after the worker was terminated; never before. */
  stopSignal: Promise<void>;
  resolveStop: () => void;
  abort: (cause: AbortCause) => void;
  completed: Promise<void>;
  resolveCompleted: () => void;
}

interface RaceResult {
  kind: 'value' | 'error' | 'stopped';
  value?: unknown;
  error?: unknown;
}

function errorText(error: unknown): string {
  return error instanceof Error ? `${error.name}: ${error.message}` : String(error);
}

export class WllamaInferenceEngine implements InferenceEngine {
  readonly info: EngineInfo = { backend: 'wllama', modelId: null };
  private readonly contextSize: number;
  private readonly gpuLayers: number;
  private instance: Wllama | null = null;
  private loadedIdentity: LoadedIdentity | null = null;
  private loading: Promise<void> | null = null;
  private loadingUrl: string | null = null;
  private loadAbort: AbortController | null = null;
  private disposed = false;
  private disposePromise: Promise<void> | null = null;
  private loadCount = 0;
  private hardStops = 0;
  private generations = 0;
  private workersCreated = 0;
  private workersExited = 0;
  /** Last model a load was attempted for. Survives a hard stop, so the next
   * request reloads the same weights instead of erroring on a missing url. */
  private lastModelUrls: string[] | null = null;
  private readonly activeCalls = new Set<ActiveCall>();
  private readonly exited = new WeakMap<Wllama, Promise<void>>();

  constructor(
    private readonly options: WllamaEngineOptions = {},
    private readonly factory: () => Promise<Wllama> = createWllama,
  ) {
    this.contextSize = options.contextSize ?? 4096;
    this.gpuLayers = options.nGpuLayers ?? 99999;
  }

  /** Kept byte-compatible with existing harness assertions
   * (`deepEqual` against `{multithread,numThreads}`). New runtime state is
   * exposed by `runtime` instead. */
  get diagnostics(): { multithread: boolean; numThreads: number } | null {
    return this.instance ? { multithread: this.instance.isMultithread(), numThreads: this.instance.getNumThreads() } : null;
  }

  get runtime(): {
    backend: string;
    modelId: string | null;
    loaded: boolean;
    contextSize: number;
    gpuLayers: number;
    loadCount: number;
    hardStops: number;
    activeCalls: number;
    generations: number;
    workersCreated: number;
    workersExited: number;
    disposed: boolean;
    /** True when a model was loaded before, the worker is gone, and the
     * engine can reload the same weights (e.g. after a timeout hard stop). */
    needsReload: boolean;
    lastModelUrl: string | null;
    lastModelUrls: string[] | null;
  } {
    return {
      backend: this.info.backend,
      modelId: this.info.modelId,
      loaded: this.instance !== null,
      contextSize: this.contextSize,
      gpuLayers: this.gpuLayers,
      loadCount: this.loadCount,
      hardStops: this.hardStops,
      activeCalls: this.activeCalls.size,
      generations: this.generations,
      workersCreated: this.workersCreated,
      workersExited: this.workersExited,
      disposed: this.disposed,
      needsReload: !this.disposed && this.instance === null && this.lastModelUrls !== null,
      lastModelUrl: this.lastModelUrls?.[0] ?? null,
      lastModelUrls: this.lastModelUrls,
    };
  }

  private resolveModelUrl(configured: string): string {
    return typeof location !== 'undefined' ? new URL(configured, location.href).href : configured;
  }

  /** A single canonical first-shard URL (`...-00001-of-00002.gguf`) expands
   * to every sibling. The GGUF split naming already carries the count, so the
   * page/09 runner can pass one URL and the engine still loads all shards;
   * wllama renames the blobs to its own canonical names and llama.cpp opens
   * the siblings from the virtual models directory. */
  private expandShards(urls: string[]): string[] {
    if (urls.length !== 1) return urls;
    const match = /-(\d{5})-of-(\d{5})\.gguf$/i.exec(urls[0]!);
    if (!match) return urls;
    const total = Number(match[2]);
    if (!Number.isInteger(total) || total < 2 || total > 99) return urls;
    const prefix = urls[0]!.slice(0, match.index);
    return Array.from({ length: total }, (_, index) => `${prefix}-${String(index + 1).padStart(5, '0')}-of-${match[2]}.gguf`);
  }

  private resolveRequestedUrls(options?: { modelUrl?: string; modelUrls?: string[] }): string[] | null {
    const configured = options?.modelUrls ?? (options?.modelUrl ? [options.modelUrl] : null)
      ?? this.options.modelUrls ?? (this.options.modelUrl ? [this.options.modelUrl] : null)
      ?? this.lastModelUrls;
    if (!configured || configured.length === 0) return null;
    return this.expandShards(configured.map((url) => this.resolveModelUrl(url)));
  }

  async load(options?: { signal?: AbortSignal; modelUrl?: string; modelUrls?: string[] }): Promise<void> {
    if (this.disposed) throw abortError();
    const modelUrls = this.resolveRequestedUrls(options);
    if (!modelUrls) throw new Error('wllama engine needs a modelUrl');
    const identity = modelUrls.join('|');
    if (this.instance) {
      if (this.loadedIdentity?.identity !== identity) {
        throw new Error(`wllama engine is already loaded with ${this.loadedIdentity?.modelUrls.join(', ') ?? 'another model'}; dispose it before loading ${modelUrls.join(', ')}`);
      }
      return;
    }
    if (this.loading) {
      if (this.loadingUrl !== null && this.loadingUrl !== identity) {
        throw new Error(`wllama engine is already loading ${this.loadingUrl}; cannot also load ${identity}`);
      }
      return this.loading;
    }
    const inFlight = this.doLoad(modelUrls, options?.signal);
    this.loading = inFlight;
    this.loadingUrl = identity;
    // A load, failed or successful, releases its memo: a successful load is
    // served by the instance check above, and a failed/cancelled load must
    // be retryable, while concurrent callers of the SAME load still share
    // its fate. The side-channel handlers keep the rejection handled;
    // callers awaiting this.loading still see it reject.
    const settle = () => {
      if (this.loading === inFlight) this.loading = null;
      if (this.loadingUrl === identity) this.loadingUrl = null;
    };
    void inFlight.then(settle, settle);
    return inFlight;
  }

  /** Reload the last model after a hard stop, or no-op when the same model is
   * already live. A different explicit modelUrl is a configuration error.
   * This is the entry 06 should call before the first turn and after a
   * timeout/cancel that terminated the worker. */
  async ensureLoaded(options?: { signal?: AbortSignal; modelUrl?: string; modelUrls?: string[] }): Promise<void> {
    if (this.disposed) throw abortError();
    if (this.instance) {
      if (options?.modelUrl || options?.modelUrls) {
        const requested = this.resolveRequestedUrls(options);
        if (this.loadedIdentity?.identity !== requested?.join('|')) {
          throw new Error(`wllama engine is loaded with ${this.loadedIdentity?.modelUrls.join(', ') ?? 'another model'}; dispose it before loading ${requested?.join(', ') ?? 'another model'}`);
        }
      }
      return;
    }
    const modelUrls = this.resolveRequestedUrls(options);
    if (!modelUrls) throw new Error('wllama engine has no model to reload; pass modelUrl');
    await this.load({ signal: options?.signal, modelUrls });
  }

  /** Stop an in-flight load without disposing the engine. The load rejects
   * with AbortError, its landing worker is exited, and a later load() is
   * retryable. Returns false when no load is running. */
  cancelLoad(): boolean {
    if (!this.loading || !this.loadAbort) return false;
    this.loadAbort.abort();
    return true;
  }

  private async doLoad(modelUrls: string[], callerSignal?: AbortSignal): Promise<void> {
    const started = performance.now();
    this.lastModelUrls = modelUrls;
    const controller = new AbortController();
    this.loadAbort = controller;
    const loadTimeoutMs = this.options.loadTimeoutMs ?? 120_000;
    if (!Number.isFinite(loadTimeoutMs) || loadTimeoutMs <= 0) throw new Error('loadTimeoutMs must be positive and finite');
    let timedOut = false;
    let instance: Wllama | null = null;
    const deadline = setTimeout(() => {
      timedOut = true;
      controller.abort();
      // A load can sit inside a native compile step that ignores the abort.
      // Terminating the landing worker is the only guaranteed stop; the
      // pending loadModel/loadModelFromUrl then rejects and the catch path
      // reports a timeout. The page can retry with a fresh worker.
      if (instance) void this.exitInstance(instance);
    }, loadTimeoutMs);
    const onCallerAbort = () => controller.abort(callerSignal?.reason);
    if (callerSignal?.aborted) onCallerAbort();
    else callerSignal?.addEventListener('abort', onCallerAbort, { once: true });
    // The blob path needs a page URL to resolve a relative model path, so it
    // is the browser default; outside a browser the OPFS/url path is used.
    const directBlob = this.options.directBlob ?? (typeof location !== 'undefined');
    let fetchMs: number | null = null;
    let compileMs: number | null = null;
    let outcome: ModelLoadEvidence['outcome'] = 'failed';
    let failure: unknown = null;
    try {
      instance = await this.factory();
      this.workersCreated += 1;
      if (this.disposed || timedOut) {
        outcome = this.disposed ? 'discarded' : 'timeout';
        throw abortError();
      }
      const params = {
        n_ctx: this.contextSize,
        n_gpu_layers: this.gpuLayers,
        ...(this.options.numThreads !== undefined ? { n_threads: this.options.numThreads } : {}),
        signal: controller.signal,
      };
      if (directBlob) {
        const fetchStarted = performance.now();
        const blobs: Blob[] = [];
        const expected = this.options.expectedBytes === undefined
          ? null
          : Array.isArray(this.options.expectedBytes) ? this.options.expectedBytes : [this.options.expectedBytes];
        for (const [index, url] of modelUrls.entries()) {
          try {
            const response = await fetch(url, { signal: controller.signal });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const blob = await response.blob();
            if (expected && expected[index] !== undefined && blob.size !== expected[index]) {
              throw new Error(`size ${blob.size}, expected ${expected[index]}`);
            }
            blobs.push(blob);
          } catch (error) {
            // Keep an abort as an abort (the catch path classifies by signal),
            // but name the exact shard for a real fetch/body failure: a 2.5 GB
            // split otherwise reports only "Failed to fetch".
            if (controller.signal.aborted) throw error;
            const reason = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
            throw new Error(`model shard ${index + 1}/${modelUrls.length} fetch failed (${url}): ${reason}`);
          }
        }
        fetchMs = performance.now() - fetchStarted;
        const loadStarted = performance.now();
        await instance.loadModel(blobs, params);
        compileMs = performance.now() - loadStarted;
      } else {
        if (modelUrls.length > 1) {
          throw new Error('split models need the directBlob path; wllama 3.8.1 loadModelFromUrl takes one url');
        }
        const loadStarted = performance.now();
        await instance.loadModelFromUrl(modelUrls[0]!, { ...params, useCache: this.options.useCache ?? false });
        compileMs = performance.now() - loadStarted;
      }
      if (this.disposed) {
        // Dispose landed mid-load: clean up immediately and register
        // nothing — the produced instance must never resurrect.
        outcome = 'discarded';
        throw abortError();
      }
      this.instance = instance;
      this.loadedIdentity = { modelUrls, identity: modelUrls.join('|'), contextSize: this.contextSize, gpuLayers: this.gpuLayers };
      this.info.modelId = decodeURIComponent(modelUrls[0]!.split('/').pop() ?? modelUrls[0]!);
      this.loadCount += 1;
      outcome = 'loaded';
    } catch (error) {
      failure = error;
      if (outcome !== 'discarded') {
        outcome = this.disposed ? 'discarded'
          : timedOut ? 'timeout'
          : controller.signal.aborted || callerSignal?.aborted ? 'aborted' : 'failed';
      }
      // The factory instance is not registered unless load completed. Exit
      // it on every failure path: a dropped wllama instance still owns a
      // wasm worker and its model buffers.
      if (instance && this.instance !== instance) await this.exitInstance(instance);
      if (outcome === 'aborted' || outcome === 'discarded') throw abortError();
      if (outcome === 'timeout') {
        const timeoutError = new Error(`model load timed out after ${loadTimeoutMs} ms`);
        timeoutError.name = 'TimeoutError';
        failure = timeoutError; // evidence says timeout, not the abort that delivered it
        throw timeoutError;
      }
      throw error;
    } finally {
      clearTimeout(deadline);
      callerSignal?.removeEventListener('abort', onCallerAbort);
      if (this.loadAbort === controller) this.loadAbort = null;
      if (this.loadingUrl === modelUrls.join('|')) this.loadingUrl = null;
      this.emit({
        kind: 'load',
        modelUrl: modelUrls[0]!,
        modelUrls,
        modelId: outcome === 'loaded' ? this.info.modelId : null,
        contextSize: this.contextSize,
        gpuLayers: this.gpuLayers,
        numThreads: this.options.numThreads ?? null,
        useCache: this.options.useCache ?? false,
        directBlob,
        fetchMs,
        compileMs,
        totalMs: performance.now() - started,
        loadTimeoutMs,
        outcome,
        ...(failure !== null && outcome !== 'loaded' ? { error: errorText(failure) } : {}),
        at: performance.now(),
      });
    }
  }

  async complete(prompt: string, options?: CompleteOptions): Promise<string> {
    return this.generate([{ role: 'user', content: prompt }], options);
  }

  /** Chat completion with a real message list, so an instruct model receives
   * the caller's system prompt instead of the checkpoint's default system
   * turn. Additive to the InferenceEngine contract: the interface keeps
   * complete() and callers that only know the interface still work. */
  async chat(messages: ChatMessage[], options?: CompleteOptions): Promise<string> {
    if (messages.length === 0) throw new Error('chat needs at least one message');
    return this.generate(messages, options);
  }

  private async generate(messages: ChatMessage[], options?: CompleteOptions): Promise<string> {
    const instance = this.instance;
    if (!instance) throw new Error('wllama engine is not loaded');
    if (options?.signal?.aborted || this.disposed) throw abortError();
    const timeoutMs = options?.timeoutMs ?? 120_000;
    if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) throw new Error('timeoutMs must be positive and finite');
    const graceMs = this.options.abortGraceMs ?? 2500;
    if (!Number.isFinite(graceMs) || graceMs < 0) throw new Error('abortGraceMs must be finite and non-negative');
    const maxTokens = options?.maxTokens ?? 256;
    const cachePrompt = options?.cachePrompt ?? true;
    this.generations += 1;
    const started = performance.now();
    const evidence: GenerationEvidence = {
      kind: 'generation',
      outcome: 'error',
      raw: '',
      finishReason: null,
      firstTokenMs: null,
      wallMs: 0,
      firstChunkMs: null,
      firstReadableMs: null,
      maxStreamGapMs: 0,
      streamChunks: 0,
      promptTokens: null,
      contextSize: this.contextSize,
      cachedPromptTokens: null,
      maxTokens,
      cachePrompt,
      abortCause: null,
      abortRequestedMs: null,
      stoppedMs: null,
      hardStopped: false,
      at: 0,
    };
    let lastChunkAt: number | null = null;
    let resolveCompleted!: () => void;
    const completed = new Promise<void>((resolve) => { resolveCompleted = resolve; });
    let resolveStop!: () => void;
    const stopSignal = new Promise<void>((resolve) => { resolveStop = resolve; });
    const call: ActiveCall = {
      controller: new AbortController(),
      cause: null,
      abortRequestedAt: null,
      deadline: null,
      grace: null,
      hardStop: null,
      hardStopped: false,
      stopSignal,
      resolveStop,
      abort: () => undefined,
      completed,
      resolveCompleted,
    };
    const armAbort = (cause: AbortCause) => {
      if (call.cause) return;
      call.cause = cause;
      call.abortRequestedAt = performance.now();
      if (call.deadline) {
        clearTimeout(call.deadline);
        call.deadline = null;
      }
      call.controller.abort();
      // dispose() terminates the worker itself, immediately; there is no
      // value in waiting out the grace period during teardown.
      if (cause !== 'dispose') {
        call.grace = setTimeout(() => { void this.hardStop(call, instance); }, graceMs);
      }
    };
    call.abort = armAbort;
    this.activeCalls.add(call);
    const onCallerAbort = () => armAbort('caller');
    options?.signal?.addEventListener('abort', onCallerAbort, { once: true });
    call.deadline = setTimeout(() => armAbort('timeout'), timeoutMs);

    let enginePromise: Promise<unknown>;
    try {
      enginePromise = Promise.resolve(instance.createChatCompletion({
        messages: messages.map((message) => ({ role: message.role, content: message.content })),
        chat_template_kwargs: { enable_thinking: false },
        cache_prompt: cachePrompt,
        stream: true,
        max_tokens: maxTokens,
        temperature: options?.temperature ?? 0,
        ...(options?.seed !== undefined ? { seed: options.seed } : {}),
        ...(options?.stop !== undefined ? { stop: options.stop } : {}),
        ...(options?.jsonSchema !== undefined ? { response_format: {
          type: 'json_schema' as const, json_schema: { name: 'task_output', schema: options.jsonSchema, strict: true },
        } } : {}),
        abortSignal: call.controller.signal,
        onData: (chunk) => {
          const at = performance.now();
          const elapsed = at - started;
          if (evidence.streamChunks === 0) evidence.firstChunkMs = elapsed;
          if (lastChunkAt !== null) evidence.maxStreamGapMs = Math.max(evidence.maxStreamGapMs, at - lastChunkAt);
          lastChunkAt = at;
          evidence.streamChunks += 1;
          const choice = chunk.choices?.[0];
          const text = choice?.delta?.content ?? '';
          if (text) {
            if (evidence.firstTokenMs === null) evidence.firstTokenMs = elapsed;
            // The first non-whitespace fragment is what the player can
            // actually read; a leading newline is not readable content.
            if (evidence.firstReadableMs === null && text.trim().length > 0) evidence.firstReadableMs = elapsed;
            evidence.raw += text;
          }
          if (choice?.finish_reason) evidence.finishReason = choice.finish_reason;
          if (chunk.usage) evidence.usage = chunk.usage;
          if (chunk.timings) {
            evidence.timings = chunk.timings;
            if (typeof chunk.timings.prompt_n === 'number') evidence.promptTokens = chunk.timings.prompt_n;
            if (typeof chunk.timings.cache_n === 'number') evidence.cachedPromptTokens = chunk.timings.cache_n;
          }
          options?.onProgress?.({ raw: evidence.raw, elapsedMs: elapsed });
        },
      }));
    } catch (error) {
      enginePromise = Promise.reject(error);
    }

    try {
      const settled = await this.awaitGeneration(enginePromise, call);
      if (call.cause) {
        const stoppedAt = performance.now();
        evidence.stoppedMs = call.abortRequestedAt === null ? null : stoppedAt - call.abortRequestedAt;
        if (call.cause === 'timeout') {
          evidence.outcome = 'timeout';
          evidence.finishReason = 'timeout';
          throw new IncompleteGenerationError(evidence, 'generation deadline exceeded');
        }
        evidence.outcome = 'aborted';
        throw abortError();
      }
      if (this.disposed) {
        call.cause = 'dispose';
        evidence.outcome = 'aborted';
        throw abortError();
      }
      if (settled.kind === 'error') {
        evidence.outcome = 'error';
        evidence.error = errorText(settled.error);
        throw settled.error;
      }
      if (evidence.finishReason !== 'stop') {
        evidence.outcome = 'incomplete';
        throw new IncompleteGenerationError(evidence);
      }
      evidence.outcome = 'completed';
      return evidence.raw;
    } finally {
      if (call.deadline) clearTimeout(call.deadline);
      if (call.grace) clearTimeout(call.grace);
      options?.signal?.removeEventListener('abort', onCallerAbort);
      this.activeCalls.delete(call);
      evidence.wallMs = performance.now() - started;
      evidence.abortCause = call.cause;
      evidence.abortRequestedMs = call.abortRequestedAt === null ? null : call.abortRequestedAt - started;
      evidence.hardStopped = call.hardStopped;
      evidence.at = performance.now();
      this.emit(evidence);
      try {
        options?.onCompletion?.(evidence);
      } catch {
        // Observers are diagnostics; a throwing observer must never turn a
        // completed generation into a failed one.
      }
      call.resolveCompleted();
    }
  }

  /** Waits for the native call, or for a confirmed hard stop. The hard-stop
   * promise only resolves after the worker is terminated, so settling the
   * caller then is a real stop, not an ignored return value. */
  private async awaitGeneration(enginePromise: Promise<unknown>, call: ActiveCall): Promise<RaceResult> {
    const engine = enginePromise.then<RaceResult, RaceResult>(
      (value) => ({ kind: 'value', value }),
      (error: unknown) => ({ kind: 'error', error }),
    );
    const stopped = call.stopSignal.then<RaceResult, RaceResult>(() => ({ kind: 'stopped' }));
    return Promise.race([engine, stopped]);
  }

  /** Terminate the worker when abort did not settle. `exit()` terminates the
   * worker synchronously, which stops any wasm call in flight; the loaded
   * model is gone, so the next load() starts fresh. Idempotent per call. */
  private hardStop(call: ActiveCall, instance: Wllama): Promise<void> {
    if (call.hardStop) return call.hardStop;
    call.hardStopped = true;
    this.hardStops += 1;
    call.hardStop = (async () => {
      await this.exitInstance(instance);
      if (this.instance === instance) {
        this.instance = null;
        this.loadedIdentity = null;
        this.info.modelId = null;
      }
      call.resolveStop();
    })();
    return call.hardStop;
  }

  private exitInstance(instance: Wllama): Promise<void> {
    let exiting = this.exited.get(instance);
    if (!exiting) {
      exiting = (async () => {
        try {
          await instance.exit();
        } catch {
          // Worker termination is best effort; the device is stopped either
          // way. Never let a teardown hiccup mask the caller's abort.
        } finally {
          this.workersExited += 1;
        }
      })();
      this.exited.set(instance, exiting);
    }
    return exiting;
  }

  private emit(record: ModelLoadEvidence | GenerationEvidence): void {
    try {
      this.options.onEvidence?.(record);
    } catch {
      // Diagnostics must not alter runtime behavior.
    }
  }

  /** Stop every generation running on this engine without disposing it. The
   * caller promises reject with AbortError; the device slot frees when the
   * engine actually stops (or after abortGraceMs through worker termination).
   * A page stop button can call this on both engines directly, so the cancel
   * path does not depend on a signal being threaded through every task.
   * Returns the number of calls asked to stop. */
  cancelActive(): number {
    // The load is the first 30-45 s of a cold session; a stop button must
    // stop it too. cancelLoad() is non-terminal, so the page can retry.
    this.cancelLoad();
    const calls = [...this.activeCalls];
    for (const call of calls) call.abort('caller');
    return calls.length;
  }

  async dispose(): Promise<void> {
    if (this.disposePromise) return this.disposePromise;
    this.disposed = true;
    this.loadAbort?.abort(); // fail-fast an in-flight download
    const instance = this.instance;
    this.instance = null;
    this.loadedIdentity = null;
    this.info.modelId = null;
    const inFlight = this.loading;
    this.loading = null;
    this.loadingUrl = null;
    this.disposePromise = (async () => {
      const calls = [...this.activeCalls];
      for (const call of calls) call.abort('dispose');
      if (instance) await this.exitInstance(instance);
      // The worker is terminated, so the device is stopped: unblock the
      // hard-stop race before waiting for the callers' finally paths.
      for (const call of calls) call.resolveStop();
      if (calls.length > 0) await Promise.allSettled(calls.map((call) => call.completed));
      if (inFlight) {
        try {
          await inFlight; // doLoad exits the produced instance itself when disposed
        } catch {
          // a failed load has nothing left to clean up
        }
      }
    })();
    return this.disposePromise;
  }
}

/** Re-exported for callers that want to build their own evidence without
 * importing from the local diagnostics directory. */
export type { CompletionEvidence };
