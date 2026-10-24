/** wllama adapter. The engine is browser-only (the loader imports the built
 * bundle from /wllama at runtime); Node tests inject a fake instance through
 * the factory and only ever exercise the option mapping, never the wasm.
 * Cancellation is forwarded natively: wllama's createCompletion takes an
 * abortSignal and stops generation. */
import type { Wllama } from '@wllama/wllama';
import { createWllama } from '../../benchmark/wllama-loader';
import type { CompleteOptions, EngineInfo, InferenceEngine } from './engine';

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
  private instance: Wllama | null = null;
  private loading: Promise<void> | null = null;

  constructor(
    private readonly options: WllamaEngineOptions = {},
    private readonly factory: () => Promise<Wllama> = createWllama,
  ) {}

  async load(options?: { signal?: AbortSignal; modelUrl?: string }): Promise<void> {
    if (this.instance) return;
    this.loading ??= (async () => {
      const instance = await this.factory();
      const modelUrl = options?.modelUrl ?? this.options.modelUrl;
      if (!modelUrl) throw new Error('wllama engine needs a modelUrl');
      options?.signal?.throwIfAborted();
      await instance.loadModelFromUrl(modelUrl, {
        n_ctx: this.options.contextSize ?? 4096,
        n_gpu_layers: 0,
      });
      this.instance = instance;
      this.info.modelId = modelUrl.split('/').pop() ?? modelUrl;
    })();
    return this.loading;
  }

  async complete(prompt: string, options?: CompleteOptions): Promise<string> {
    const instance = this.instance;
    if (!instance) throw new Error('wllama engine is not loaded');
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
    const instance = this.instance;
    this.instance = null;
    this.loading = null;
    this.info.modelId = null;
    await instance?.exit();
  }
}
