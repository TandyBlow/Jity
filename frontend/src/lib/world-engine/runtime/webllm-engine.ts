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

  constructor(private readonly modelId: string, private readonly modelBase?: string, private readonly cacheBackend: 'cache' | 'indexeddb' | 'opfs' = 'indexeddb') {}

  async load(options?: { signal?: AbortSignal }): Promise<void> {
    if (this.engine) return;
    if (options?.signal?.aborted) throw abortError();
    if (!this.loading) {
      console.info('[world-local] webllm load start', this.modelId);
      const record = prebuiltAppConfig.model_list.find((item) => item.model_id === this.modelId);
      const modelList = this.modelBase && record
        ? [{ ...record, model: this.modelBase, low_resource_required: true }, ...prebuiltAppConfig.model_list.filter((item) => item.model_id !== this.modelId)]
        : prebuiltAppConfig.model_list;
      this.loading = CreateMLCEngine(this.modelId, {
        // The headless profile's Cache API quota is ~0 on this box; IndexedDB
        // is the fallback that still lets the prototype measure 4B. With a
        // local base the weights come from the page origin, not the HF CDN.
        appConfig: { ...prebuiltAppConfig, cacheBackend: this.cacheBackend, model_list: modelList },
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
    // WebLLM can wedge mid-stream; bound the call so a hung generation becomes
    // a visible error instead of a forever-pending turn.
    const timeoutMs = options.timeoutMs ?? 150_000;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const timeout = new Promise<never>((_, reject) => {
      timer = setTimeout(() => {
        try { this.engine?.interruptGenerate(); } catch { /* already gone */ }
        reject(new Error('webllm_generation_timeout'));
      }, timeoutMs);
    });
    try {
      // Two prompt shapes, matching the wllama path: settlement calls send the
      // bare prompt (completions API, no chat template); narration sends a
      // ChatML-wrapped user turn (chat API with thinking off, so Qwen3 does
      // not spend the output budget inside <think>).
      type Chunk = { choices?: { text?: string; delta?: { content?: string } }[] };
      const chatml = prompt.match(/^<\|im_start\|>user\n([\s\S]*?)<\|im_end\|>\n<\|im_start\|>assistant\n$/);
      let stream: AsyncIterable<Chunk>;
      if (chatml) {
        const createChat = this.engine.chat.completions.create.bind(this.engine.chat.completions) as unknown as (
          request: Record<string, unknown>,
        ) => Promise<AsyncIterable<Chunk>>;
        stream = await createChat({
          messages: [{ role: 'user', content: chatml[1] }],
          stream: true,
          max_tokens: options.maxTokens ?? 512,
          temperature: options.temperature ?? 0.2,
          extra_body: { enable_thinking: false },
          ...(options.stop ? { stop: options.stop } : {}),
        });
      } else {
        const create = this.engine.completions.create.bind(this.engine.completions) as unknown as (
          request: Record<string, unknown>,
        ) => Promise<AsyncIterable<Chunk>>;
        stream = await create({
          prompt,
          stream: true,
          max_tokens: options.maxTokens ?? 512,
          temperature: options.temperature ?? 0.2,
          ...(options.stop ? { stop: options.stop } : {}),
        });
      }
      const consume = (async () => {
      for await (const chunk of stream) {
        if (signal?.aborted || this.abort?.signal.aborted) {
          try { this.engine?.interruptGenerate(); } catch { /* already done */ }
          throw abortError();
        }
        const delta = chunk.choices?.[0]?.text ?? chunk.choices?.[0]?.delta?.content ?? '';
        if (!delta) continue;
        if (firstTokenMs == null) firstTokenMs = performance.now() - started;
        raw += delta;
        options.onProgress?.({ raw, elapsedMs: performance.now() - started });
      }
      })();
      await Promise.race([consume, timeout]);
    } finally {
      if (timer) clearTimeout(timer);
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
