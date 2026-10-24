import { describe, expect, test } from 'vitest';
import type { Wllama } from '@wllama/wllama';
import { WllamaInferenceEngine } from './wllama-engine';

/** Records every mapped call; the wasm is never touched in Node. */
function fakeWllama() {
  const calls = {
    loads: [] as Array<{ url: string; params: Record<string, unknown> }>,
    completions: [] as Array<Record<string, unknown>>,
    exits: 0,
  };
  const instance = {
    loadModelFromUrl: async (url: string, params: Record<string, unknown>) => {
      calls.loads.push({ url, params });
    },
    createCompletion: async (options: Record<string, unknown>) => {
      calls.completions.push(options);
      return { choices: [{ text: 'ok' }] };
    },
    exit: async () => {
      calls.exits += 1;
    },
  } as unknown as Wllama;
  return { instance, calls };
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
    expect(calls.loads).toEqual([{ url: '/models/tales-0.6b.gguf', params: { n_ctx: 2048, n_gpu_layers: 0 } }]);
    expect(engine.info).toEqual({ backend: 'wllama', modelId: 'tales-0.6b.gguf' });
  });

  test('load without any model url is a configuration error', async () => {
    const { instance } = fakeWllama();
    const engine = new WllamaInferenceEngine(undefined, async () => instance);
    await expect(engine.load()).rejects.toThrow(/modelUrl/);
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

  test('complete before load is an ordering error, dispose exits and resets', async () => {
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
    await engine.load(); // dispose reset the memoized load
    expect(factories).toBe(2);
  });
});
