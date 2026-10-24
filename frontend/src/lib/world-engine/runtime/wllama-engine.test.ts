import { describe, expect, test } from 'vitest';
import type { Wllama } from '@wllama/wllama';
import { WllamaInferenceEngine } from './wllama-engine';

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
  const instance = {
    loadModelFromUrl: async (url: string, params: Record<string, unknown>) => {
      calls.loads.push({ url, params });
      if (holdLoads) await new Promise<void>((resolve) => loadGates.push(resolve));
      if (honorAbort && (params.signal as AbortSignal | undefined)?.aborted) throw new DOMException('Aborted', 'AbortError');
    },
    createCompletion: async (options: Record<string, unknown>) => {
      calls.completions.push(options);
      return { choices: [{ text: 'ok' }] };
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

  test('complete maps prompt, sampling options and the abort signal; extracts the text', async () => {
    const { instance, calls } = fakeWllama();
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf' }, async () => instance);
    await engine.load();
    const controller = new AbortController();
    const text = await engine.complete('PROMPT', { maxTokens: 64, temperature: 0.3, seed: 7, stop: ['\n'], signal: controller.signal });
    expect(text).toBe('ok');
    expect(calls.completions[0]).toEqual({
      prompt: 'PROMPT', max_tokens: 64, temperature: 0.3, seed: 7, stop: ['\n'], abortSignal: controller.signal,
    });
  });

  test('unset sampling options are omitted, missing choices yield an empty string', async () => {
    const { instance, calls } = fakeWllama();
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf' }, async () => instance);
    await engine.load();
    await engine.complete('P');
    expect(calls.completions[0]).toEqual({ prompt: 'P', max_tokens: 256, temperature: 0, abortSignal: undefined });
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
