import { describe, expect, test } from 'vitest';
import type { Wllama } from '@wllama/wllama';
import { WllamaInferenceEngine } from './wllama-engine';
import { IncompleteGenerationError, type CompletionEvidence } from './engine';

/** Records every mapped call; the wasm is never touched in Node. The load
 * can be held (deterministic observation of mid-load abort and dispose) and
 * honors the forwarded abort signal like the real loadModelFromUrl does. */
function fakeWllama() {
  const calls = {
    loads: [] as Array<{ url: string; params: Record<string, unknown> }>,
    completions: [] as Array<Record<string, unknown>>,
    exits: 0,
  };
  let holdLoads = false;
  let honorAbort = true;
  const loadGates: Array<() => void> = [];
  let finishReason: string | null = 'stop';
  let waitForAbort = false;
  const instance = {
    loadModelFromUrl: async (url: string, params: Record<string, unknown>) => {
      calls.loads.push({ url, params });
      if (holdLoads) await new Promise<void>((resolve) => loadGates.push(resolve));
      if (honorAbort && (params.signal as AbortSignal | undefined)?.aborted) throw new DOMException('Aborted', 'AbortError');
    },
    createChatCompletion: async (options: Record<string, unknown>) => {
      calls.completions.push(options);
      const onData = options.onData as (chunk: unknown) => void;
      onData({ choices: [{ delta: { content: 'ok' }, finish_reason: null }] });
      if (waitForAbort) await new Promise<void>((_resolve, reject) => {
        (options.abortSignal as AbortSignal).addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
      });
      onData({ choices: [{ delta: {}, finish_reason: finishReason }],
        usage: { prompt_tokens: 5, completion_tokens: 1, total_tokens: 6 } });
    },
    exit: async () => {
      calls.exits += 1;
    },
  } as unknown as Wllama;
  return {
    instance,
    calls,
    holdLoads(value: boolean) { holdLoads = value; },
    honorAbort(value: boolean) { honorAbort = value; },
    releaseLoads() { for (const gate of loadGates.splice(0)) gate(); },
    finish(reason: string | null) { finishReason = reason; },
    waitForAbort() { waitForAbort = true; },
  };
}

describe('WllamaInferenceEngine option mapping', () => {
  test('load is idempotent, carries the model url and context size, and names the model', async () => {
    let factories = 0;
    const { instance, calls } = fakeWllama();
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/tales-0.6b.gguf', contextSize: 2048 }, async () => {
      factories += 1;
      return instance;
    });
    expect(engine.info.modelId).toBeNull();
    await engine.load();
    await engine.load(); // second call awaits the same load
    expect(factories).toBe(1);
    expect(calls.loads).toEqual([{ url: '/models/tales-0.6b.gguf', params: { n_ctx: 2048, n_gpu_layers: 0, signal: expect.any(AbortSignal) } }]);
    expect(engine.info).toEqual({ backend: 'wllama', modelId: 'tales-0.6b.gguf' });
  });

  test('load without any model url is a configuration error', async () => {
    const { instance } = fakeWllama();
    const engine = new WllamaInferenceEngine(undefined, async () => instance);
    await expect(engine.load()).rejects.toThrow(/modelUrl/);
  });

  test('a caller abort during load reaches the underlying download and rejects the load', async () => {
    const { instance, calls, holdLoads, releaseLoads } = fakeWllama();
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf' }, async () => instance);
    const controller = new AbortController();
    holdLoads(true);
    const loading = engine.load({ signal: controller.signal });
    await new Promise((resolve) => setTimeout(resolve, 5)); // download in flight
    const forwarded = calls.loads[0]!.params.signal as AbortSignal;
    expect(forwarded.aborted).toBe(false);
    controller.abort();
    expect(forwarded.aborted).toBe(true); // the load cancellation was forwarded
    releaseLoads();
    await expect(loading).rejects.toSatisfy((error: unknown) => error instanceof Error && error.name === 'AbortError');
  });

  test('dispose mid-load aborts the download, and a landing instance is exited, never registered', async () => {
    const { instance, calls, holdLoads, honorAbort, releaseLoads } = fakeWllama();
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf' }, async () => instance);
    holdLoads(true);
    honorAbort(false); // the worst case: the download completes despite the abort
    const loading = engine.load();
    await new Promise((resolve) => setTimeout(resolve, 5));
    const disposing = engine.dispose();
    await new Promise((resolve) => setTimeout(resolve, 5));
    releaseLoads();
    await disposing;
    expect(calls.exits).toBe(1); // the landing instance was cleaned up…
    expect(engine.info.modelId).toBeNull(); // …and never registered
    await expect(engine.load()).rejects.toSatisfy((error: unknown) => error instanceof Error && error.name === 'AbortError');
  });

  test('dispose mid-load with a honoring download needs no exit — nothing landed', async () => {
    const { instance, calls, holdLoads, releaseLoads } = fakeWllama();
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf' }, async () => instance);
    holdLoads(true);
    const loading = engine.load();
    await new Promise((resolve) => setTimeout(resolve, 5));
    const disposing = engine.dispose();
    releaseLoads(); // download observes the aborted signal and fails
    await disposing;
    expect(calls.exits).toBe(0);
    expect(engine.info.modelId).toBeNull();
    await expect(loading).rejects.toSatisfy((error: unknown) => error instanceof Error && error.name === 'AbortError');
  });

  test('a cancelled load is retryable: the next call starts a fresh download', async () => {
    let factories = 0;
    const { instance, calls, holdLoads, releaseLoads } = fakeWllama();
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf' }, async () => {
      factories += 1;
      return instance;
    });
    const firstController = new AbortController();
    holdLoads(true);
    const first = engine.load({ signal: firstController.signal });
    await new Promise((resolve) => setTimeout(resolve, 5));
    firstController.abort();
    releaseLoads();
    await expect(first).rejects.toSatisfy((error: unknown) => error instanceof Error && error.name === 'AbortError');

    holdLoads(false);
    const secondController = new AbortController(); // fresh, never cancelled
    await engine.load({ signal: secondController.signal }); // must actually retry, not replay the old AbortError
    expect(calls.loads).toHaveLength(2);
    expect(engine.info.modelId).toBe('m.gguf');
    expect(await engine.complete('P')).toBe('ok');
    expect(factories).toBe(2); // the failed load released its memo; a new engine instance was created
  });

  test('chat template, no thinking, grammar and native EOS; keeps streaming evidence', async () => {
    const { instance, calls } = fakeWllama();
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf' }, async () => instance);
    await engine.load();
    const controller = new AbortController();
    let evidence: CompletionEvidence | undefined;
    const progress: string[] = [];
    const schema = { type: 'object' };
    const text = await engine.complete('PROMPT', { maxTokens: 64, temperature: 0.3, seed: 7, stop: ['\n'], signal: controller.signal,
      jsonSchema: schema, onCompletion: (row) => { evidence = row; }, onProgress: (row) => progress.push(row.raw) });
    expect(text).toBe('ok');
    expect(calls.completions[0]).toMatchObject({
      messages: [{ role: 'user', content: 'PROMPT' }], max_tokens: 64, temperature: 0.3, seed: 7, stop: ['\n'],
      abortSignal: expect.any(AbortSignal), stream: true, cache_prompt: true, chat_template_kwargs: { enable_thinking: false },
      response_format: { type: 'json_schema', json_schema: { name: 'task_output', schema, strict: true } },
    });
    expect(evidence).toMatchObject({ raw: 'ok', finishReason: 'stop', usage: { prompt_tokens: 5 } });
    expect(evidence!.firstTokenMs).toBeGreaterThanOrEqual(0);
    expect(progress[0]).toBe('ok');
  });

  test('text generation has no JSON grammar and uses bounded defaults', async () => {
    const { instance, calls } = fakeWllama();
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf' }, async () => instance);
    await engine.load();
    await engine.complete('P');
    expect(calls.completions[0]).toMatchObject({ messages: [{ role: 'user', content: 'P' }], max_tokens: 256, temperature: 0 });
    expect(calls.completions[0]).not.toHaveProperty('response_format');
  });

  test('length and missing finish reject with raw output and measured cost', async () => {
    const fake = fakeWllama();
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf' }, async () => fake.instance);
    await engine.load();
    for (const reason of ['length', null]) {
      fake.finish(reason);
      const error = await engine.complete('P').catch((error) => error);
      expect(error).toBeInstanceOf(IncompleteGenerationError);
      expect(error.completion).toMatchObject({ raw: 'ok', finishReason: reason });
      expect(error.completion.wallMs).toBeGreaterThanOrEqual(0);
    }
  });

  test('generation deadline aborts device work and retains partial output; caller abort stays AbortError', async () => {
    const fake = fakeWllama();
    fake.waitForAbort();
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf' }, async () => fake.instance);
    await engine.load();
    const error = await engine.complete('P', { timeoutMs: 10 }).catch((error) => error);
    expect(error).toBeInstanceOf(IncompleteGenerationError);
    expect(error.completion).toMatchObject({ raw: 'ok', finishReason: 'timeout' });
    expect((fake.calls.completions[0].abortSignal as AbortSignal).aborted).toBe(true);
    const controller = new AbortController();
    const cancelled = engine.complete('P', { signal: controller.signal });
    controller.abort();
    await expect(cancelled).rejects.toMatchObject({ name: 'AbortError' });
  });

  test('complete before load is an ordering error, and dispose is terminal', async () => {
    let factories = 0;
    const { instance, calls } = fakeWllama();
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf' }, async () => {
      factories += 1;
      return instance;
    });
    await expect(engine.complete('P')).rejects.toThrow(/not loaded/);
    await engine.load();
    await engine.dispose();
    expect(calls.exits).toBe(1);
    expect(engine.info.modelId).toBeNull();
    await expect(engine.complete('P')).rejects.toThrow(/not loaded/);
    await expect(engine.load()).rejects.toSatisfy((error: unknown) => error instanceof Error && error.name === 'AbortError'); // dispose is terminal
    expect(factories).toBe(1);
  });
});
