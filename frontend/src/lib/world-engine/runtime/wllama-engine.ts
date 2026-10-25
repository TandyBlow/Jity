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
import { abortError, type CompleteOptions, type EngineInfo, type InferenceEngine } from './engine';

/** The slice of wllama's completion response this adapter consumes; typed
 * locally like the benchmark does instead of importing build-time internals. */
interface CompletionResponse {
  choices?: Array<{ text?: string }>;
}

export interface WllamaEngineOptions {
  /** Default model source for load(); a per-call modelUrl overrides it. */
  modelUrl?: string;
  contextSize?: number;
}

export class WllamaInferenceEngine implements InferenceEngine {
  readonly info: EngineInfo = { backend: 'wllama', modelId: null };
  private completions = 0;
  private instance: Wllama | null = null;
  private loading: Promise<void> | null = null;
  private loadAbort: AbortController | null = null;
  private disposed = false;

  constructor(
    private readonly options: WllamaEngineOptions = {},
    private readonly factory: () => Promise<Wllama> = createWllama,
  ) {}

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

  /** Monotonic count of STARTED completions (the eval harness counts real
   * device work, not attempts). */
  callsMade(): number { return this.completions; }

  async complete(prompt: string, options?: CompleteOptions): Promise<string> {
    const instance = this.instance;
    if (!instance) throw new Error('wllama engine is not loaded');
    this.completions += 1;
    const response = (await instance.createCompletion({
      prompt,
      max_tokens: options?.maxTokens ?? 256,
      temperature: options?.temperature ?? 0,
      ...(options?.seed !== undefined ? { seed: options.seed } : {}),
      ...(options?.stop !== undefined ? { stop: options.stop } : {}),
      abortSignal: options?.signal,
    })) as CompletionResponse;
    return response.choices?.[0]?.text ?? '';
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
