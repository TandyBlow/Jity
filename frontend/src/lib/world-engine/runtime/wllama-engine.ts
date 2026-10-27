/** wllama adapter. The engine is browser-only (the loader imports the built
 * bundle from /wllama at runtime); Node tests inject a fake instance through
 * the factory and only ever exercise the option mapping, never the wasm.
 * Cancellation is forwarded natively: both loadModelFromUrl and
 * createCompletion take an abortSignal and stop the underlying work.
 * dispose() is terminal and safe mid-load: an in-flight download is aborted,
 * and an instance that lands after dispose is exited instead of registered —
 * nothing resurrects. */
import type { Wllama } from '@wllama/wllama';
import { createWllama } from '../../benchmark/wllama-loader';
import { abortError, IncompleteGenerationError, type CompletionEvidence, type CompleteOptions, type EngineInfo, type InferenceEngine } from './engine';

export interface WllamaEngineOptions {
  /** Default model source for load(); a per-call modelUrl overrides it. */
  modelUrl?: string;
  contextSize?: number;
  numThreads?: number;
}

export class WllamaInferenceEngine implements InferenceEngine {
  readonly info: EngineInfo = { backend: 'wllama', modelId: null };
  private instance: Wllama | null = null;
  private loading: Promise<void> | null = null;
  private loadAbort: AbortController | null = null;
  private disposed = false;

  constructor(
    private readonly options: WllamaEngineOptions = {},
    private readonly factory: () => Promise<Wllama> = createWllama,
  ) {}

  get diagnostics(): { multithread: boolean; numThreads: number } | null {
    return this.instance ? { multithread: this.instance.isMultithread(), numThreads: this.instance.getNumThreads() } : null;
  }

  async load(options?: { signal?: AbortSignal; modelUrl?: string }): Promise<void> {
    if (this.disposed) throw abortError();
    if (this.instance) return;
    if (!this.loading) {
      const inFlight = this.doLoad(options);
      this.loading = inFlight;
      // A failed load (e.g. a cancelled download) must be retryable: clear
      // the memo so the next call starts fresh, while concurrent callers of
      // the SAME load still share its fate. The side-channel catch keeps the
      // rejection handled; callers awaiting this.loading still see it reject.
      void inFlight.catch(() => {
        if (this.loading === inFlight) this.loading = null;
      });
    }
    return this.loading;
  }

  private async doLoad(options?: { signal?: AbortSignal; modelUrl?: string }): Promise<void> {
    const controller = new AbortController();
    this.loadAbort = controller;
    const onCallerAbort = () => controller.abort(options?.signal?.reason);
    if (options?.signal?.aborted) onCallerAbort();
    else options?.signal?.addEventListener('abort', onCallerAbort, { once: true });
    try {
      const instance = await this.factory();
      const modelUrl = options?.modelUrl ?? this.options.modelUrl;
      if (!modelUrl) throw new Error('wllama engine needs a modelUrl');
      await instance.loadModelFromUrl(modelUrl, {
        n_ctx: this.options.contextSize ?? 4096,
        n_gpu_layers: 0,
        ...(this.options.numThreads !== undefined ? { n_threads: this.options.numThreads } : {}),
        signal: controller.signal,
      });
      if (this.disposed) {
        // Dispose landed mid-load: clean up immediately and register
        // nothing — the produced instance must never resurrect.
        await instance.exit();
        return;
      }
      this.instance = instance;
      this.info.modelId = modelUrl.split('/').pop() ?? modelUrl;
    } finally {
      options?.signal?.removeEventListener('abort', onCallerAbort);
      if (this.loadAbort === controller) this.loadAbort = null;
    }
  }

  async complete(prompt: string, options?: CompleteOptions): Promise<string> {
    const instance = this.instance;
    if (!instance) throw new Error('wllama engine is not loaded');
    if (options?.signal?.aborted || this.disposed) throw abortError();
    const timeoutMs = options?.timeoutMs ?? 120_000;
    if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) throw new Error('timeoutMs must be positive and finite');
    const controller = new AbortController();
    const callerAbort = () => controller.abort();
    options?.signal?.addEventListener('abort', callerAbort, { once: true });
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
    const started = performance.now();
    const evidence: CompletionEvidence = { raw: '', finishReason: null, firstTokenMs: null, wallMs: 0 };
    try {
      await instance.createChatCompletion({
        messages: [{ role: 'user', content: prompt }],
        chat_template_kwargs: { enable_thinking: false },
        cache_prompt: true,
        stream: true,
        max_tokens: options?.maxTokens ?? 256,
        temperature: options?.temperature ?? 0,
        ...(options?.seed !== undefined ? { seed: options.seed } : {}),
        ...(options?.stop !== undefined ? { stop: options.stop } : {}),
        ...(options?.jsonSchema !== undefined ? { response_format: {
          type: 'json_schema' as const, json_schema: { name: 'task_output', schema: options.jsonSchema, strict: true },
        } } : {}),
        abortSignal: controller.signal,
        onData: (chunk) => {
          const choice = chunk.choices?.[0];
          const text = choice?.delta?.content ?? '';
          if (text && evidence.firstTokenMs === null) evidence.firstTokenMs = performance.now() - started;
          evidence.raw += text;
          if (choice?.finish_reason) evidence.finishReason = choice.finish_reason;
          if (chunk.usage) evidence.usage = chunk.usage;
          if (chunk.timings) evidence.timings = chunk.timings;
          options?.onProgress?.({ raw: evidence.raw, elapsedMs: performance.now() - started });
        },
      });
      if (options?.signal?.aborted || this.disposed) throw abortError();
      if (timedOut) throw new IncompleteGenerationError(evidence, 'generation deadline exceeded');
    } catch (error) {
      if (options?.signal?.aborted || this.disposed) throw abortError();
      if (timedOut) {
        evidence.finishReason = 'timeout';
        throw new IncompleteGenerationError(evidence, 'generation deadline exceeded');
      }
      throw error;
    } finally {
      clearTimeout(timer);
      options?.signal?.removeEventListener('abort', callerAbort);
      evidence.wallMs = performance.now() - started;
      options?.onCompletion?.(evidence);
    }
    if (evidence.finishReason !== 'stop') throw new IncompleteGenerationError(evidence);
    return evidence.raw;
  }

  async dispose(): Promise<void> {
    this.disposed = true;
    this.loadAbort?.abort(); // fail-fast an in-flight download
    const current = this.instance;
    this.instance = null;
    const inFlight = this.loading;
    this.loading = null;
    this.info.modelId = null;
    if (current) await current.exit();
    if (inFlight) {
      try {
        await inFlight; // doLoad exits the produced instance itself when disposed
      } catch {
        // a failed load has nothing left to clean up
      }
    }
  }
}
