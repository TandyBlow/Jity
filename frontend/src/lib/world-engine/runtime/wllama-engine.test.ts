import { afterEach, describe, expect, test, vi } from 'vitest';
import type { Wllama } from '@wllama/wllama';
import { WllamaInferenceEngine } from './wllama-engine';
import { IncompleteGenerationError, type CompletionEvidence } from './engine';
import type { GenerationEvidence, ModelLoadEvidence } from '../local/runtime-diagnostics/types';

interface FakeChunk {
  text?: string;
  finish?: string | null;
  delayMs?: number;
  usage?: Record<string, unknown>;
  timings?: Record<string, number>;
}

type FakeCompletionOptions = Record<string, unknown> & {
  abortSignal: AbortSignal;
  onData: (chunk: unknown) => void;
};

const abortDom = () => new DOMException('Aborted', 'AbortError');
const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** A controllable wllama stand-in. The wasm is never touched in Node; the
 * fake honours the forwarded abort signal like the real worker does, and can
 * also refuse to settle so the hard-stop escalation is observable. */
function fakeWllama() {
  const calls = {
    loads: [] as Array<{ url: string; params: Record<string, unknown> }>,
    blobs: [] as Array<{ size: number; files: number; params: Record<string, unknown> }>,
    completions: [] as FakeCompletionOptions[],
    exits: 0,
  };
  let holdLoads = false;
  let honorLoadAbort = true;
  let loadFailure: string | null = null;
  let chunks: FakeChunk[] = [{ text: 'ok', finish: 'stop' }];
  let mode: 'chunks' | 'hang-until-abort' | 'never' = 'chunks';
  interface LoadGate { resolve: () => void; reject: (error: unknown) => void }
  const loadGates: LoadGate[] = [];
  /** Holds a load until the test releases it, while still honouring a real
   * abort (the production fetch does; a wasm compile may not, which is why
   * the engine also terminates the landing worker). exit() rejects every
   * pending gate, exactly like a terminated worker rejecting its call. */
  const awaitLoadGate = async (params: Record<string, unknown>) => {
    if (!holdLoads) return;
    const signal = params.signal as AbortSignal | undefined;
    await new Promise<void>((resolve, reject) => {
      const gate: LoadGate = { resolve, reject };
      loadGates.push(gate);
      const onAbort = () => {
        if (!honorLoadAbort) return;
        const index = loadGates.indexOf(gate);
        if (index !== -1) loadGates.splice(index, 1);
        reject(abortDom());
      };
      if (signal?.aborted) onAbort();
      else signal?.addEventListener('abort', onAbort, { once: true });
    });
  };

  const runCompletion = async (options: FakeCompletionOptions) => {
    const signal = options.abortSignal;
    const emit = (chunk: FakeChunk) => {
      options.onData({
        choices: [{ delta: chunk.text ? { content: chunk.text } : {}, finish_reason: chunk.finish ?? null }],
        ...(chunk.usage ? { usage: chunk.usage } : {}),
        ...(chunk.timings ? { timings: chunk.timings } : {}),
      });
    };
    for (const chunk of chunks) {
      if (signal.aborted) throw abortDom();
      if (chunk.delayMs) await sleep(chunk.delayMs);
      emit(chunk);
    }
    if (mode === 'hang-until-abort') {
      await new Promise<void>((_resolve, reject) => {
        signal.addEventListener('abort', () => reject(abortDom()), { once: true });
      });
      return;
    }
    if (mode === 'never') await new Promise<void>(() => undefined);
    if (signal.aborted) throw abortDom();
  };

  const instance = {
    isMultithread: () => true,
    getNumThreads: () => 4,
    loadModelFromUrl: async (url: string, params: Record<string, unknown>) => {
      calls.loads.push({ url, params });
      await awaitLoadGate(params);
      if (loadFailure) throw new Error(loadFailure);
      if (honorLoadAbort && (params.signal as AbortSignal | undefined)?.aborted) throw abortDom();
    },
    loadModel: async (files: Blob[], params: Record<string, unknown>) => {
      calls.blobs.push({ size: files.reduce((sum, file) => sum + file.size, 0), files: files.length, params });
      await awaitLoadGate(params);
      if (loadFailure) throw new Error(loadFailure);
      if (honorLoadAbort && (params.signal as AbortSignal | undefined)?.aborted) throw abortDom();
    },
    createChatCompletion: async (options: FakeCompletionOptions) => {
      calls.completions.push(options);
      await runCompletion(options);
    },
    exit: async () => {
      calls.exits += 1;
      for (const gate of loadGates.splice(0)) gate.reject(new DOMException('Worker terminated', 'AbortError'));
    },
  } as unknown as Wllama;

  return {
    instance,
    calls,
    holdLoads(value: boolean) { holdLoads = value; },
    honorLoadAbort(value: boolean) { honorLoadAbort = value; },
    failLoad(message: string | null) { loadFailure = message; },
    releaseLoads() { for (const gate of loadGates.splice(0)) gate.resolve(); },
    chunks(value: FakeChunk[]) { chunks = value; },
    mode(value: 'chunks' | 'hang-until-abort' | 'never') { mode = value; },
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('WllamaInferenceEngine option mapping', () => {
  test('load is idempotent, carries the model url and context size, and names the model', async () => {
    let factories = 0;
    const fake = fakeWllama();
    const evidence: ModelLoadEvidence[] = [];
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/tales-0.6b.gguf', contextSize: 2048, nGpuLayers: 0, directBlob: false,
      onEvidence: (record) => { if (record.kind === 'load') evidence.push(record); } }, async () => {
      factories += 1;
      return fake.instance;
    });
    expect(engine.info.modelId).toBeNull();
    await engine.load();
    await engine.load(); // second call awaits the same, already-finished load
    expect(factories).toBe(1);
    expect(fake.calls.loads).toEqual([{ url: '/models/tales-0.6b.gguf', params: { n_ctx: 2048, n_gpu_layers: 0, signal: expect.any(AbortSignal), useCache: false } }]);
    expect(engine.info).toEqual({ backend: 'wllama', modelId: 'tales-0.6b.gguf' });
    // The legacy getter shape is unchanged (existing harnesses deepEqual it).
    expect(engine.diagnostics).toEqual({ multithread: true, numThreads: 4 });
    expect(engine.runtime).toMatchObject({ modelId: 'tales-0.6b.gguf', loaded: true, contextSize: 2048, gpuLayers: 0, loadCount: 1, hardStops: 0 });
    expect(evidence).toHaveLength(1);
    expect(evidence[0]).toMatchObject({ outcome: 'loaded', modelId: 'tales-0.6b.gguf', contextSize: 2048, gpuLayers: 0, directBlob: false });
    expect(evidence[0]!.compileMs).toBeGreaterThanOrEqual(0);
  });

  test('load without any model url is a configuration error and creates no instance', async () => {
    let factories = 0;
    const fake = fakeWllama();
    const engine = new WllamaInferenceEngine(undefined, async () => {
      factories += 1;
      return fake.instance;
    });
    await expect(engine.load()).rejects.toThrow(/modelUrl/);
    expect(factories).toBe(0);
  });

  test('a second load of a DIFFERENT model is rejected instead of silently reusing the loaded one', async () => {
    const fake = fakeWllama();
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/a.gguf', directBlob: false }, async () => fake.instance);
    await engine.load();
    await expect(engine.load({ modelUrl: '/models/b.gguf' })).rejects.toThrow(/loaded with/);
    expect(fake.calls.loads).toHaveLength(1);
    await engine.load({ modelUrl: '/models/a.gguf' }); // same identity stays idempotent
    expect(fake.calls.loads).toHaveLength(1);
  });

  test('a caller abort during load reaches the underlying download, rejects, and releases the worker', async () => {
    const fake = fakeWllama();
    const evidence: ModelLoadEvidence[] = [];
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf', directBlob: false,
      onEvidence: (record) => { if (record.kind === 'load') evidence.push(record); } }, async () => fake.instance);
    const controller = new AbortController();
    fake.holdLoads(true);
    const loading = engine.load({ signal: controller.signal });
    await sleep(5);
    const forwarded = fake.calls.loads[0]!.params.signal as AbortSignal;
    expect(forwarded.aborted).toBe(false);
    controller.abort();
    expect(forwarded.aborted).toBe(true);
    fake.releaseLoads();
    await expect(loading).rejects.toMatchObject({ name: 'AbortError' });
    expect(fake.calls.exits).toBe(1); // the abandoned factory instance was exited
    expect(engine.info.modelId).toBeNull();
    expect(evidence.at(-1)).toMatchObject({ outcome: 'aborted', modelId: null });
    expect(evidence.at(-1)!.error).toBeDefined();
  });

  test('a failed load exits the factory instance and stays retryable', async () => {
    const fake = fakeWllama();
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf', directBlob: false }, async () => fake.instance);
    fake.failLoad('compile exploded');
    await expect(engine.load()).rejects.toThrow(/compile exploded/);
    expect(fake.calls.exits).toBe(1);
    expect(engine.info.modelId).toBeNull();
    fake.failLoad(null);
    await engine.load();
    expect(engine.info.modelId).toBe('m.gguf');
    expect(fake.calls.loads).toHaveLength(2);
  });

  test('dispose mid-load aborts the download, exits the landing instance, and never registers it', async () => {
    const fake = fakeWllama();
    fake.holdLoads(true);
    fake.honorLoadAbort(false); // worst case: the load completes despite the abort
    const evidence: ModelLoadEvidence[] = [];
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf', directBlob: false,
      onEvidence: (record) => { if (record.kind === 'load') evidence.push(record); } }, async () => fake.instance);
    const loading = engine.load();
    await sleep(5);
    const disposing = engine.dispose();
    fake.releaseLoads();
    await disposing;
    await expect(loading).rejects.toMatchObject({ name: 'AbortError' });
    expect(fake.calls.exits).toBe(1);
    expect(engine.info.modelId).toBeNull();
    expect(evidence.at(-1)).toMatchObject({ outcome: 'discarded', modelId: null });
    await expect(engine.load()).rejects.toMatchObject({ name: 'AbortError' });
  });

  test('dispose mid-load with a cooperating download also exits once', async () => {
    const fake = fakeWllama();
    fake.holdLoads(true);
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf', directBlob: false }, async () => fake.instance);
    const loading = engine.load();
    await sleep(5);
    const disposing = engine.dispose();
    fake.releaseLoads();
    await disposing;
    await expect(loading).rejects.toMatchObject({ name: 'AbortError' });
    expect(fake.calls.exits).toBe(1);
    expect(engine.info.modelId).toBeNull();
  });

  test('a cancelled load is retryable: the next call starts a fresh download', async () => {
    let factories = 0;
    const fake = fakeWllama();
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf', directBlob: false }, async () => {
      factories += 1;
      return fake.instance;
    });
    const firstController = new AbortController();
    fake.holdLoads(true);
    const first = engine.load({ signal: firstController.signal });
    await sleep(5);
    firstController.abort();
    fake.releaseLoads();
    await expect(first).rejects.toMatchObject({ name: 'AbortError' });

    fake.holdLoads(false);
    const secondController = new AbortController(); // fresh, never cancelled
    await engine.load({ signal: secondController.signal }); // must actually retry, not replay the old AbortError
    expect(fake.calls.loads).toHaveLength(2);
    expect(engine.info.modelId).toBe('m.gguf');
    expect(await engine.complete('P')).toBe('ok');
    expect(factories).toBe(2); // the failed load released its memo; a new engine instance was created
    expect(fake.calls.exits).toBe(1); // the cancelled instance was cleaned up
  });

  test('the direct-blob path fetches once, reports fetch and compile separately, and names the model', async () => {
    const fake = fakeWllama();
    vi.stubGlobal('fetch', async () => new Response(new Blob([new Uint8Array([1, 2, 3, 4])])));
    const evidence: ModelLoadEvidence[] = [];
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/blob.gguf', directBlob: true,
      onEvidence: (record) => { if (record.kind === 'load') evidence.push(record); } }, async () => fake.instance);
    await engine.load();
    expect(fake.calls.blobs).toHaveLength(1);
    expect(fake.calls.blobs[0]).toMatchObject({ size: 4, params: { n_ctx: 4096, n_gpu_layers: 99999, signal: expect.any(AbortSignal) } });
    expect(evidence[0]).toMatchObject({ outcome: 'loaded', directBlob: true, modelId: 'blob.gguf' });
    expect(evidence[0]!.fetchMs).toBeGreaterThanOrEqual(0);
    expect(evidence[0]!.compileMs).toBeGreaterThanOrEqual(0);
  });

  test('split GGUF shards load as one ordered multi-blob call', async () => {
    const fake = fakeWllama();
    const urls = ['/models/m.gguf-00001-of-00002.gguf', '/models/m.gguf-00002-of-00002.gguf'];
    const fetched: string[] = [];
    vi.stubGlobal('fetch', async (url: string) => {
      fetched.push(url);
      return new Response(new Blob([new Uint8Array(url.includes('00001') ? 6 : 4)]));
    });
    const evidence: ModelLoadEvidence[] = [];
    const engine = new WllamaInferenceEngine({ modelUrls: urls, directBlob: true,
      onEvidence: (record) => { if (record.kind === 'load') evidence.push(record); } }, async () => fake.instance);
    await engine.load();
    expect(fetched).toEqual(urls);
    expect(fake.calls.blobs[0]).toMatchObject({ size: 10, files: 2 });
    expect(engine.info.modelId).toBe('m.gguf-00001-of-00002.gguf');
    expect(engine.runtime.lastModelUrls).toEqual(urls);
    expect(evidence[0]).toMatchObject({ outcome: 'loaded', modelUrl: urls[0], modelUrls: urls, directBlob: true });
    expect(await engine.complete('P')).toBe('ok');
  });

  test('a single first-shard url expands to all shards automatically', async () => {
    const fake = fakeWllama();
    const fetched: string[] = [];
    vi.stubGlobal('fetch', async (url: string) => {
      fetched.push(url);
      return new Response(new Blob([new Uint8Array([1])]));
    });
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m-00001-of-00002.gguf', directBlob: true }, async () => fake.instance);
    await engine.load();
    expect(fetched).toEqual(['/models/m-00001-of-00002.gguf', '/models/m-00002-of-00002.gguf']);
    expect(fake.calls.blobs[0]).toMatchObject({ files: 2, size: 2 });
    expect(engine.runtime.lastModelUrls).toEqual(fetched);
  });

  test('ensureLoaded reuses both cached shards of the same split model after a hard stop', async () => {
    const fakes: ReturnType<typeof fakeWllama>[] = [];
    let factories = 0;
    const urls = ['/models/m.gguf-00001-of-00002.gguf', '/models/m.gguf-00002-of-00002.gguf'];
    let fetches = 0;
    vi.stubGlobal('fetch', async () => {
      fetches += 1;
      return new Response(new Blob([new Uint8Array([1, 2, 3, 4])]));
    });
    const engine = new WllamaInferenceEngine({ modelUrls: urls, directBlob: true, abortGraceMs: 10 }, async () => {
      factories += 1;
      const fake = fakeWllama();
      if (factories === 1) {
        fake.chunks([{ text: 'partial' }]);
        fake.mode('never');
      }
      fakes.push(fake);
      return fake.instance;
    });
    await engine.load();
    expect(fetches).toBe(2);
    await expect(engine.complete('P', { timeoutMs: 10 })).rejects.toBeInstanceOf(IncompleteGenerationError);
    expect(engine.runtime).toMatchObject({ loaded: false, needsReload: true, lastModelUrls: urls });

    await engine.ensureLoaded();
    expect(factories).toBe(2);
    expect(fetches).toBe(2); // both shards came from the cache
    expect(fakes[1]!.calls.blobs[0]!.files).toBe(2);
    expect(engine.runtime).toMatchObject({ loaded: true, loadCount: 2, cachedModel: true, lastModelUrls: urls });
    expect(await engine.complete('P')).toBe('ok');
  });

  test('a truncated fetch is rejected by the expected size before wllama sees it', async () => {
    const fake = fakeWllama();
    vi.stubGlobal('fetch', async () => new Response(new Blob([new Uint8Array([1, 2, 3, 4])])));
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf', directBlob: true, expectedBytes: 9 },
      async () => fake.instance);
    await expect(engine.load()).rejects.toThrow(/size 4, expected 9/);
    expect(fake.calls.blobs).toHaveLength(0); // never reached loadModel
    expect(fake.calls.exits).toBe(1);
    expect(engine.runtime).toMatchObject({ loaded: false, workersCreated: 1, workersExited: 1 });
  });

  test('the expected size applies per shard', async () => {
    const fake = fakeWllama();
    const urls = ['/models/m-00001-of-00002.gguf', '/models/m-00002-of-00002.gguf'];
    vi.stubGlobal('fetch', async (url: string) => new Response(new Blob([new Uint8Array(url.includes('-00001-of-') ? 6 : 4)])));
    const engine = new WllamaInferenceEngine({ modelUrls: urls, directBlob: true, expectedBytes: [6, 5] },
      async () => fake.instance);
    await expect(engine.load()).rejects.toThrow(/model shard 2\/2 fetch failed .*size 4, expected 5/);
    expect(fake.calls.exits).toBe(1);
  });

  test('a failing second shard names the shard and exits the landing worker', async () => {
    const fake = fakeWllama();
    const urls = ['/models/m.gguf-00001-of-00002.gguf', '/models/m.gguf-00002-of-00002.gguf'];
    vi.stubGlobal('fetch', async (url: string) => {
      if (url.includes('-00002-of-')) throw new TypeError('Failed to fetch');
      return new Response(new Blob([new Uint8Array([1])]));
    });
    const engine = new WllamaInferenceEngine({ modelUrls: urls, directBlob: true }, async () => fake.instance);
    await expect(engine.load()).rejects.toThrow(/model shard 2\/2 fetch failed .*00002-of-00002\.gguf\): TypeError: Failed to fetch/);
    expect(fake.calls.exits).toBe(1);
    expect(engine.runtime).toMatchObject({ loaded: false, workersCreated: 1, workersExited: 1 });
  });

  test('a split load without the direct-blob path is a clear error, not a silent single-file load', async () => {
    const fake = fakeWllama();
    const engine = new WllamaInferenceEngine({ modelUrls: ['/models/m-00001-of-00002.gguf', '/models/m-00002-of-00002.gguf'], directBlob: false },
      async () => fake.instance);
    await expect(engine.load()).rejects.toThrow(/directBlob/);
    expect(fake.calls.exits).toBe(1);
    expect(engine.info.modelId).toBeNull();
  });

  test('a failing fetch is an error, not a silently resolved load', async () => {
    const fake = fakeWllama();
    vi.stubGlobal('fetch', async () => new Response('nope', { status: 503 }));
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/blob.gguf', directBlob: true }, async () => fake.instance);
    await expect(engine.load()).rejects.toThrow(/model shard 1\/1 fetch failed .*HTTP 503/);
    expect(fake.calls.exits).toBe(1);
  });

  test('chat template, no thinking, grammar and native EOS; keeps streaming evidence', async () => {
    const fake = fakeWllama();
    fake.chunks([
      { text: '' },
      { text: '好', finish: 'stop', usage: { prompt_tokens: 9, completion_tokens: 1, total_tokens: 10 },
        timings: { prompt_ms: 4, predicted_ms: 5, cache_n: 6, prompt_n: 42, predicted_n: 1 } },
    ]);
    const evidence: GenerationEvidence[] = [];
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf', directBlob: false,
      onEvidence: (record) => { if (record.kind === 'generation') evidence.push(record); } }, async () => fake.instance);
    await engine.load();
    const controller = new AbortController();
    let completion: CompletionEvidence | undefined;
    const progress: string[] = [];
    const schema = { type: 'object' };
    const text = await engine.complete('PROMPT', { maxTokens: 64, temperature: 0.3, seed: 7, stop: ['\n'], signal: controller.signal,
      jsonSchema: schema, onCompletion: (row) => { completion = row; }, onProgress: (row) => progress.push(row.raw) });
    expect(text).toBe('好');
    expect(fake.calls.completions[0]).toMatchObject({
      messages: [{ role: 'user', content: 'PROMPT' }], max_tokens: 64, temperature: 0.3, seed: 7, stop: ['\n'],
      abortSignal: expect.any(AbortSignal), stream: true, cache_prompt: true, chat_template_kwargs: { enable_thinking: false },
      response_format: { type: 'json_schema', json_schema: { name: 'task_output', schema, strict: true } },
    });
    expect(completion).toMatchObject({ raw: '好', finishReason: 'stop', usage: { prompt_tokens: 9 } });
    expect(completion!.firstTokenMs).toBeGreaterThanOrEqual(0);
    expect(progress).toEqual(['', '好']);
    expect(evidence).toHaveLength(1);
    expect(evidence[0]).toMatchObject({
      outcome: 'completed', streamChunks: 2, promptTokens: 42, cachedPromptTokens: 6, contextSize: 4096,
      maxTokens: 64, cachePrompt: true, abortCause: null, hardStopped: false,
    });
    expect(evidence[0]!.firstChunkMs).not.toBeNull();
    expect(evidence[0]!.firstReadableMs).not.toBeNull();
    expect(evidence[0]!.raw).toBe('好');
  });

  test('the engine reports the first READABLE fragment separately from the first token', async () => {
    const fake = fakeWllama();
    fake.chunks([{ text: '' }, { text: '\n' }, { text: '雨', finish: 'stop' }]);
    const evidence: GenerationEvidence[] = [];
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf', directBlob: false,
      onEvidence: (record) => { if (record.kind === 'generation') evidence.push(record); } }, async () => fake.instance);
    await engine.load();
    await engine.complete('P');
    const row = evidence[0]!;
    expect(row.raw).toBe('\n雨');
    expect(row.firstTokenMs).not.toBeNull(); // the newline is a token…
    expect(row.firstReadableMs).not.toBeNull(); // …but not readable text
    expect(row.firstReadableMs!).toBeGreaterThanOrEqual(row.firstTokenMs!);
    expect(row.streamChunks).toBe(3);
  });

  test('chat() forwards a real system turn and shares the completion contract', async () => {
    const fake = fakeWllama();
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf', directBlob: false }, async () => fake.instance);
    await engine.load();
    await engine.chat([
      { role: 'system', content: 'SYSTEM' },
      { role: 'user', content: 'USER' },
    ], { maxTokens: 32, temperature: 0.2 });
    expect(fake.calls.completions[0]).toMatchObject({
      messages: [{ role: 'system', content: 'SYSTEM' }, { role: 'user', content: 'USER' }],
      max_tokens: 32, temperature: 0.2, stream: true,
    });
    await expect(engine.chat([])).rejects.toThrow(/at least one message/);
  });

  test('text generation has no JSON grammar and uses bounded defaults', async () => {
    const fake = fakeWllama();
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf', directBlob: false }, async () => fake.instance);
    await engine.load();
    await engine.complete('P');
    expect(fake.calls.completions[0]).toMatchObject({ messages: [{ role: 'user', content: 'P' }], max_tokens: 256, temperature: 0 });
    expect(fake.calls.completions[0]).not.toHaveProperty('response_format');
  });

  test('length and missing finish reject with raw output, measured cost and an incomplete outcome', async () => {
    const fake = fakeWllama();
    const evidence: GenerationEvidence[] = [];
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf', directBlob: false,
      onEvidence: (record) => { if (record.kind === 'generation') evidence.push(record); } }, async () => fake.instance);
    await engine.load();
    for (const reason of ['length', null]) {
      fake.chunks([{ text: 'ok', finish: reason }]);
      const error = await engine.complete('P').catch((error) => error);
      expect(error).toBeInstanceOf(IncompleteGenerationError);
      expect(error.completion).toMatchObject({ raw: 'ok', finishReason: reason });
      expect(error.completion.wallMs).toBeGreaterThanOrEqual(0);
    }
    expect(evidence.map((row) => row.outcome)).toEqual(['incomplete', 'incomplete']);
  });

  test('generation deadline aborts device work, retains partial output, and records the stop latency', async () => {
    const fake = fakeWllama();
    fake.chunks([{ text: 'ok' }]);
    fake.mode('hang-until-abort');
    const evidence: GenerationEvidence[] = [];
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf', directBlob: false,
      onEvidence: (record) => { if (record.kind === 'generation') evidence.push(record); } }, async () => fake.instance);
    await engine.load();
    const error = await engine.complete('P', { timeoutMs: 10 }).catch((error) => error);
    expect(error).toBeInstanceOf(IncompleteGenerationError);
    expect(error.completion).toMatchObject({ raw: 'ok', finishReason: 'timeout' });
    expect((fake.calls.completions[0]!.abortSignal as AbortSignal).aborted).toBe(true);
    expect(evidence[0]).toMatchObject({ outcome: 'timeout', abortCause: 'timeout', hardStopped: false });
    expect(evidence[0]!.stoppedMs).toBeGreaterThanOrEqual(0);
    expect(evidence[0]!.abortRequestedMs).toBeGreaterThanOrEqual(0);

    const controller = new AbortController();
    const cancelled = engine.complete('P', { signal: controller.signal });
    controller.abort();
    await expect(cancelled).rejects.toMatchObject({ name: 'AbortError' });
    expect(evidence[1]).toMatchObject({ outcome: 'aborted', abortCause: 'caller' });
    expect(evidence[1]!.stoppedMs).toBeGreaterThanOrEqual(0);
  });

  test('a stuck native call is HARD STOPPED: the worker is terminated only then the timeout settles, and reload recovers', async () => {
    const fakes: ReturnType<typeof fakeWllama>[] = [];
    let factories = 0;
    const evidence: GenerationEvidence[] = [];
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf', directBlob: false, abortGraceMs: 10,
      onEvidence: (record) => { if (record.kind === 'generation') evidence.push(record); } }, async () => {
      factories += 1;
      const fake = fakeWllama();
      if (factories === 1) {
        fake.chunks([{ text: 'partial' }]);
        fake.mode('never'); // ignores abort and never settles, like a stuck wasm call
      }
      fakes.push(fake);
      return fake.instance;
    });
    await engine.load();
    const started = Date.now();
    const error = await engine.complete('P', { timeoutMs: 10, maxTokens: 1 }).catch((error) => error);
    expect(Date.now() - started).toBeLessThan(2000); // settled after the grace stop, not never
    expect(error).toBeInstanceOf(IncompleteGenerationError);
    expect(error.completion).toMatchObject({ raw: 'partial', finishReason: 'timeout' });
    expect(evidence[0]).toMatchObject({ outcome: 'timeout', abortCause: 'timeout', hardStopped: true, raw: 'partial' });
    expect(evidence[0]!.stoppedMs).toBeGreaterThanOrEqual(0);
    expect(fakes[0]!.calls.exits).toBe(1);
    expect(engine.runtime).toMatchObject({ loaded: false, hardStops: 1, loadCount: 1 });
    expect(engine.info.modelId).toBeNull();

    // The terminated model is gone; an explicit load starts a fresh instance.
    await engine.load();
    expect(factories).toBe(2);
    expect(engine.runtime).toMatchObject({ loaded: true, hardStops: 1, loadCount: 2 });
    expect(await engine.complete('P')).toBe('ok');
  });

  test('cancelActive stops the running generation without disposing the engine, and the next call works', async () => {
    const fake = fakeWllama();
    fake.chunks([{ text: 'partial' }]);
    fake.mode('hang-until-abort');
    const evidence: GenerationEvidence[] = [];
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf', directBlob: false,
      onEvidence: (record) => { if (record.kind === 'generation') evidence.push(record); } }, async () => fake.instance);
    await engine.load();
    const running = engine.complete('P', { timeoutMs: 60_000 });
    await sleep(5);
    expect(engine.cancelActive()).toBe(1);
    await expect(running).rejects.toMatchObject({ name: 'AbortError' });
    expect(evidence.at(-1)).toMatchObject({ outcome: 'aborted', abortCause: 'caller' });
    expect(engine.runtime).toMatchObject({ loaded: true, activeCalls: 0 });
    fake.mode('chunks');
    fake.chunks([{ text: 'ok', finish: 'stop' }]);
    expect(await engine.complete('P')).toBe('ok');
  });

  test('dispose mid-generation aborts the caller, exits exactly once, and is idempotent', async () => {
    const fake = fakeWllama();
    fake.chunks([{ text: 'partial' }]);
    fake.mode('never');
    const evidence: GenerationEvidence[] = [];
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf', directBlob: false,
      onEvidence: (record) => { if (record.kind === 'generation') evidence.push(record); } }, async () => fake.instance);
    await engine.load();
    const running = engine.complete('P', { timeoutMs: 60_000 });
    await sleep(5);
    const first = engine.dispose();
    const second = engine.dispose();
    await Promise.all([first, second]);
    await expect(running).rejects.toMatchObject({ name: 'AbortError' });
    expect(fake.calls.exits).toBe(1);
    expect(engine.info.modelId).toBeNull();
    expect(evidence.at(-1)).toMatchObject({ outcome: 'aborted', abortCause: 'dispose' });
    expect(engine.runtime.activeCalls).toBe(0);
  });

  test('onCompletion and onEvidence observer throws never change the generation result', async () => {
    const fake = fakeWllama();
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf', directBlob: false,
      onEvidence: () => { throw new Error('evidence observer'); } }, async () => fake.instance);
    await engine.load();
    const text = await engine.complete('P', { onCompletion: () => { throw new Error('completion observer'); } });
    expect(text).toBe('ok');
  });

  test('a load that exceeds its budget is a timeout, exits the worker, and is retryable', async () => {
    let factories = 0;
    const fakes: ReturnType<typeof fakeWllama>[] = [];
    const evidence: ModelLoadEvidence[] = [];
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf', directBlob: false, loadTimeoutMs: 20,
      onEvidence: (record) => { if (record.kind === 'load') evidence.push(record); } }, async () => {
      factories += 1;
      const fake = fakeWllama();
      if (factories === 1) fake.holdLoads(true); // compile hangs past the deadline
      fakes.push(fake);
      return fake.instance;
    });
    const first = engine.load();
    await expect(first).rejects.toMatchObject({ name: 'TimeoutError' });
    expect(fakes[0]!.calls.exits).toBe(1);
    expect(evidence.at(-1)).toMatchObject({ outcome: 'timeout', modelId: null, loadTimeoutMs: 20, error: expect.stringMatching(/TimeoutError/) });
    expect(engine.runtime).toMatchObject({ loaded: false, needsReload: true, workersCreated: 1, workersExited: 1, loadCount: 0 });

    await engine.ensureLoaded();
    expect(factories).toBe(2);
    expect(engine.runtime).toMatchObject({ loaded: true, needsReload: false, workersCreated: 2, workersExited: 1, loadCount: 1 });
    expect(await engine.complete('P')).toBe('ok'); // retry uses a fresh worker, not the timed-out one
  });

  test('cancelLoad stops an in-flight load without disposing the engine, and a later load works', async () => {
    let factories = 0;
    const fakes: ReturnType<typeof fakeWllama>[] = [];
    const evidence: ModelLoadEvidence[] = [];
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf', directBlob: false,
      onEvidence: (record) => { if (record.kind === 'load') evidence.push(record); } }, async () => {
      factories += 1;
      const fake = fakeWllama();
      if (factories === 1) fake.holdLoads(true);
      fakes.push(fake);
      return fake.instance;
    });
    const first = engine.load();
    await sleep(5);
    expect(engine.cancelLoad()).toBe(true);
    await expect(first).rejects.toMatchObject({ name: 'AbortError' });
    expect(evidence.at(-1)).toMatchObject({ outcome: 'aborted', modelId: null });
    expect(engine.runtime).toMatchObject({ loaded: false, disposed: false, needsReload: true });
    expect(engine.cancelLoad()).toBe(false); // nothing left to cancel

    await engine.ensureLoaded();
    expect(factories).toBe(2);
    expect(engine.runtime.loaded).toBe(true);
    expect(await engine.complete('P')).toBe('ok');
  });

  test('ensureLoaded reloads the per-call model url after a hard stop and rejects a different model', async () => {
    const fakes: ReturnType<typeof fakeWllama>[] = [];
    let factories = 0;
    const engine = new WllamaInferenceEngine({ directBlob: false, abortGraceMs: 10 }, async () => {
      factories += 1;
      const fake = fakeWllama();
      if (factories === 1) {
        fake.chunks([{ text: 'partial' }]);
        fake.mode('never');
      }
      fakes.push(fake);
      return fake.instance;
    });
    // No configured modelUrl: the per-call url must survive the hard stop.
    await engine.load({ modelUrl: '/models/m.gguf' });
    await expect(engine.complete('P', { timeoutMs: 10 })).rejects.toBeInstanceOf(IncompleteGenerationError);
    expect(engine.runtime).toMatchObject({ loaded: false, needsReload: true, lastModelUrl: '/models/m.gguf' });

    await engine.ensureLoaded();
    expect(factories).toBe(2);
    expect(engine.info.modelId).toBe('m.gguf');
    await expect(engine.ensureLoaded({ modelUrl: '/models/other.gguf' })).rejects.toThrow(/loaded with/);
  });

  test('a hard-stop reload reuses the fetched Blob, so no second 1.1 GB fetch is allocated', async () => {
    const fakes: ReturnType<typeof fakeWllama>[] = [];
    let factories = 0;
    const fetched: string[] = [];
    vi.stubGlobal('fetch', async (url: string) => {
      fetched.push(url);
      return new Response(new Blob([new Uint8Array([1, 2, 3, 4])]));
    });
    const evidence: ModelLoadEvidence[] = [];
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf', directBlob: true, expectedBytes: 4, abortGraceMs: 0,
      onEvidence: (record) => { if (record.kind === 'load') evidence.push(record); } }, async () => {
      factories += 1;
      const fake = fakeWllama();
      if (factories === 1) { fake.chunks([{ text: 'partial' }]); fake.mode('never'); }
      fakes.push(fake);
      return fake.instance;
    });
    await engine.load();
    expect(fetched).toHaveLength(1);
    expect(engine.runtime).toMatchObject({ cachedModel: true, cachedModelBytes: 4 });

    await expect(engine.complete('P', { timeoutMs: 10, maxTokens: 1 })).rejects.toBeInstanceOf(IncompleteGenerationError);
    expect(engine.runtime).toMatchObject({ loaded: false, needsReload: true, cachedModel: true });

    await engine.ensureLoaded();
    expect(fetched).toHaveLength(1); // the Blob was reused, not fetched again
    expect(fakes[1]!.calls.blobs).toHaveLength(1);
    expect(engine.runtime).toMatchObject({ loaded: true, loadCount: 2, cachedModel: true });
    expect(evidence.at(-1)).toMatchObject({ outcome: 'loaded', fromCache: true, fetchMs: 0 });
    expect(await engine.complete('P')).toBe('ok');
  });

  test('a rejected cached Blob drops the cache and allows a real refetch', async () => {
    const fake = fakeWllama();
    const fetched: string[] = [];
    vi.stubGlobal('fetch', async (url: string) => {
      fetched.push(url);
      return new Response(new Blob([new Uint8Array([1, 2, 3, 4])]));
    });
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf', directBlob: true, expectedBytes: 4, abortGraceMs: 0 },
      async () => fake.instance);
    await engine.load();
    fake.mode('never');
    await expect(engine.complete('P', { timeoutMs: 10, maxTokens: 1 })).rejects.toBeInstanceOf(IncompleteGenerationError);

    fake.failLoad('cached blob evicted');
    await expect(engine.ensureLoaded()).rejects.toThrow(/cached blob evicted/);
    expect(engine.runtime).toMatchObject({ loaded: false, cachedModel: false });

    fake.failLoad(null);
    await engine.ensureLoaded();
    expect(fetched).toHaveLength(2); // cache was dropped, the retry fetched for real
    expect(engine.runtime).toMatchObject({ loaded: true, loadCount: 2, cachedModel: true });
  });

  test('dispose releases the cached model bytes', async () => {
    const fake = fakeWllama();
    vi.stubGlobal('fetch', async () => new Response(new Blob([new Uint8Array([1, 2, 3, 4])])));
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf', directBlob: true, expectedBytes: 4 },
      async () => fake.instance);
    await engine.load();
    expect(engine.runtime).toMatchObject({ cachedModel: true, cachedModelBytes: 4 });
    await engine.dispose();
    expect(engine.runtime).toMatchObject({ cachedModel: false, cachedModelBytes: 0 });
  });

  test('one worker serves many turns without growth, and dispose closes exactly that worker', async () => {
    const fake = fakeWllama();
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf', directBlob: false }, async () => fake.instance);
    await engine.load();
    for (let turn = 0; turn < 6; turn += 1) expect(await engine.complete(`turn ${turn}`)).toBe('ok');
    expect(engine.runtime).toMatchObject({ workersCreated: 1, workersExited: 0, generations: 6, loadCount: 1 });
    await engine.dispose();
    expect(engine.runtime).toMatchObject({ workersCreated: 1, workersExited: 1, disposed: true, needsReload: false, loaded: false });
    expect(fake.calls.exits).toBe(1);
  });

  test('chat before ready rejects immediately instead of waiting for a model timeout', async () => {
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf', directBlob: false }, async () => fakeWllama().instance);
    const started = Date.now();
    await expect(engine.chat([{ role: 'user', content: 'P' }])).rejects.toThrow(/not loaded/);
    expect(Date.now() - started).toBeLessThan(50);
    await expect(engine.ensureLoaded()).resolves.toBeUndefined(); // the explicit recovery path
  });

  test('complete before load is an ordering error, and dispose is terminal', async () => {
    let factories = 0;
    const fake = fakeWllama();
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf', directBlob: false }, async () => {
      factories += 1;
      return fake.instance;
    });
    await expect(engine.complete('P')).rejects.toThrow(/not loaded/);
    await engine.load();
    await engine.dispose();
    expect(fake.calls.exits).toBe(1);
    expect(engine.info.modelId).toBeNull();
    await expect(engine.complete('P')).rejects.toThrow(/not loaded/);
    await expect(engine.load()).rejects.toMatchObject({ name: 'AbortError' }); // dispose is terminal
    expect(factories).toBe(1);
  });
});
