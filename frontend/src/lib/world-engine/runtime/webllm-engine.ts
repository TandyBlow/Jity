/** WebLLM (MLC) engine adapter for the D-022 runtime prototype.
 *
 * The product port only needs load/complete/dispose; WebLLM brings its own
 * WebGPU runtime and cache, so weights are not fetched through the wllama blob
 * path. Default runtime stays wllama; the page selects this one by URL arm. */
import { CreateMLCEngine, prebuiltAppConfig, type MLCEngine } from '@mlc-ai/web-llm';
import { abortError, type CompleteOptions, type CompletionEvidence, type InferenceEngine } from './engine';

const progressText = (report: { progress: number; text: string }): string =>
  `${Math.round(report.progress * 100)}% ${report.text}`.slice(0, 120);

export class WebLlmInferenceEngine implements InferenceEngine {
  readonly info = { backend: 'webllm', modelId: null as string | null };
  private engine: MLCEngine | null = null;
  private loading: Promise<void> | null = null;
  private abort: AbortController | null = null;
  /** Last load progress, for the page's status line and evidence. */
  lastProgress: string | null = null;

  constructor(private readonly modelId: string) {}

  async load(options?: { signal?: AbortSignal }): Promise<void> {
    if (this.engine) return;
    if (options?.signal?.aborted) throw abortError();
    if (!this.loading) {
      console.info('[world-local] webllm load start', this.modelId);
      this.loading = CreateMLCEngine(this.modelId, {
        // The headless profile's Cache API quota is ~0 on this box; IndexedDB
        // is the fallback that still lets the prototype measure 4B.
        appConfig: { ...prebuiltAppConfig, cacheBackend: 'indexeddb' },
        initProgressCallback: (report) => { this.lastProgress = progressText(report); console.info('[world-local] webllm', this.lastProgress); },
      }).then((engine) => {
        this.engine = engine;
        (this.info as { modelId: string | null }).modelId = this.modelId;
        console.info('[world-local] webllm loaded', this.modelId);
      }).catch((error) => {
        console.warn('[world-local] webllm load failed', String(error));
        throw error;
      }).finally(() => { this.loading = null; });
    }
    await this.loading;
    if (options?.signal?.aborted) throw abortError();
  }

  async complete(prompt: string, options: CompleteOptions = {}): Promise<string> {
    if (!this.engine) await this.load({ signal: options.signal });
    if (!this.engine) throw new Error('webllm engine failed to load');
    const signal = options.signal;
    this.abort = new AbortController();
    const onAbort = () => { try { this.abort?.abort(); } catch { /* already gone */ } };
    if (signal) {
      if (signal.aborted) throw abortError();
      signal.addEventListener('abort', onAbort, { once: true });
    }
    const started = performance.now();
    let raw = '';
    let firstTokenMs: number | null = null;
    try {
      const stream = await this.engine.chat.completions.create({
        messages: [{ role: 'user', content: prompt }],
        stream: true,
        stream_options: { include_usage: true },
        max_tokens: options.maxTokens ?? 512,
        temperature: options.temperature ?? 0.2,
        ...(options.stop ? { stop: options.stop } : {}),
      });
      for await (const chunk of stream) {
        if (signal?.aborted || this.abort?.signal.aborted) {
          try { this.engine.interruptGenerate(); } catch { /* already done */ }
          throw abortError();
        }
        const delta = chunk.choices?.[0]?.delta?.content ?? '';
        if (!delta) continue;
        if (firstTokenMs == null) firstTokenMs = performance.now() - started;
        raw += delta;
        options.onProgress?.({ raw, elapsedMs: performance.now() - started });
      }
    } finally {
      if (signal) signal.removeEventListener('abort', onAbort);
    }
    const completion: CompletionEvidence = { raw, finishReason: 'stop', firstTokenMs, wallMs: performance.now() - started };
    options.onCompletion?.(completion);
    return raw;
  }

  cancelActive(): number {
    if (!this.abort) return 0;
    try { this.abort.abort(); } catch { /* already gone */ }
    this.abort = null;
    return 1;
  }

  async dispose(): Promise<void> {
    this.cancelActive();
    if (this.engine) {
      try { await this.engine.unload(); } catch { /* already gone */ }
      this.engine = null;
    }
  }
}
