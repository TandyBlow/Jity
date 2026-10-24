import { describe, expect, test } from 'vitest';
import { isAbortError, type CompleteOptions, type InferenceEngine } from './engine';
import { RuntimeWorldModelPort, encodePrompt } from './model-port';
import { StructuredOutputError } from './structured-output';
import type { Json } from '../types';
import type { ModelTask } from '../schedule';

/** Scripted engine: pops one raw output per complete(). While `hold` is set,
 * completions stay pending until flush() — deterministic observation of
 * serialization and aborts. */
function fakeEngine(outputs: string[]) {
  const calls: Array<{ prompt: string; options: CompleteOptions | undefined }> = [];
  const pending: Array<() => void> = [];
  let loads = 0;
  let disposed = 0;
  let hold = false;
  let loadPromise: Promise<void> | null = null; // the InferenceEngine contract: load is idempotent
  const engine: InferenceEngine = {
    info: { backend: 'fake', modelId: 'fake.gguf' },
    load: () => {
      loadPromise ??= (async () => {
        loads += 1;
      })();
      return loadPromise;
    },
    complete: (prompt, options) => {
      calls.push({ prompt, options });
      const text = outputs.shift() ?? '';
      if (!hold) return Promise.resolve(text);
      return new Promise<string>((resolve) => pending.push(() => resolve(text)));
    },
    dispose: async () => {
      disposed += 1;
    },
  };
  return {
    engine,
    calls,
    get loads() { return loads; },
    get disposed() { return disposed; },
    hold(value: boolean) { hold = value; },
    flush() { for (const settle of pending.splice(0)) settle(); },
  };
}

const VALID: Partial<Record<ModelTask, { input: Json; output: string }>> = {
  action: { input: { actor: 'person_a', workingState: {} }, output: '{"kind":"act","text":"推门"}' },
  targets: { input: { sourceId: 'person_a', actionText: '推门' }, output: '{"targets":[{"targetId":"person_b","triggerKey":"group:person_b","ruleVersion":"reaction-d20-v1","target":11}]}' },
  results: { input: { groupId: 'group_a', workingState: {} }, output: '{"person_b":"门开了"}' },
  updates: { input: { groupId: 'group_a', mode: 'group', workingState: {} }, output: '[{"stage":"position","changes":{"person_a":{"positionSet":{"containerId":"corridor","slotId":null,"relativeTo":null}}}}]' },
  continuation: { input: { round: {} }, output: '{"kind":"handback","closedBy":"model","cancelReason":null}' },
  narration: { input: { pointId: 'p1', stateDigest: 'd' }, output: '走廊尽头传来翻动声。' },
  initial: { input: null, output: '{"engineVersion":"world-engine-v1","schemaVersion":1,"protagonistId":"person_c","initialTime":{"calendar":"gregorian","dateTime":"2026-01-01T08:00:00","instantOrdinal":0},"locations":{},"items":{},"characters":{}}' },
  time: { input: { point: {} }, output: '{"boundary":"instant","duration":{"amount":0,"unit":"second"}}' },
  pointPlan: { input: { round: {}, head: {} }, output: '[{"pointId":"p1","kind":"instant","timeAdvance":{"boundary":"instant","duration":{"amount":0,"unit":"second"}},"actorIds":["person_a"]}]' },
};

describe('RuntimeWorldModelPort', () => {
  test('every declared task decodes through the queue with timings', async () => {
    const scripted = Object.entries(VALID) as Array<[ModelTask, { input: Json; output: string }]>;
    const fake = fakeEngine(scripted.map(([, spec]) => spec.output));
    const port = new RuntimeWorldModelPort(fake.engine);
    for (const [task, spec] of scripted) {
      const value = await port.generate(task, 'key-1', spec.input);
      const expected = task === 'narration' ? spec.output : JSON.parse(spec.output); // text tasks are never JSON
      expect(value).toEqual(expected);
    }
    expect(fake.loads).toBe(1); // load is queued and memoized, not repeated per call
    expect(fake.calls).toHaveLength(scripted.length); // completes only; load went through the queue as its own entry
    expect(fake.calls.every((call) => call.options?.temperature === 0)).toBe(true);
  });

  test('a shape-invalid output is rejected as StructuredOutputError with the raw text', async () => {
    const fake = fakeEngine(['{"kind":"flee"}']);
    const port = new RuntimeWorldModelPort(fake.engine);
    const error = await port.generateDetailed('action', 'k', {}).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(StructuredOutputError);
    expect((error as StructuredOutputError).task).toBe('action');
    expect((error as StructuredOutputError).raw).toBe('{"kind":"flee"}');
  });

  test('generation is strictly serial across concurrent callers', async () => {
    const fake = fakeEngine(['{"kind":"skip"}', '{"kind":"skip"}']);
    fake.hold(true);
    const port = new RuntimeWorldModelPort(fake.engine);
    const first = port.generate('action', 'k1', {});
    const second = port.generate('action', 'k2', {});
    await new Promise((resolve) => setTimeout(resolve, 5));
    expect(fake.calls).toHaveLength(1); // second call queued behind the held first
    fake.flush();
    await new Promise((resolve) => setTimeout(resolve, 5));
    expect(fake.calls).toHaveLength(2);
    fake.flush();
    expect(await first).toEqual({ kind: 'skip' });
    expect(await second).toEqual({ kind: 'skip' });
  });

  test('aborting a running generation settles it and the signal reaches the engine', async () => {
    const fake = fakeEngine(['late']);
    fake.hold(true);
    const port = new RuntimeWorldModelPort(fake.engine);
    const controller = new AbortController();
    const first = port.generate('narration', 'k', {}, controller.signal);
    await new Promise((resolve) => setTimeout(resolve, 5)); // engine call in flight
    expect(fake.calls).toHaveLength(1);
    const linked = fake.calls[0]!.options?.signal; // the queue's linked signal, not the caller's raw one
    expect(linked).toBeInstanceOf(AbortSignal);
    expect(linked?.aborted).toBe(false);
    controller.abort();
    expect(linked?.aborted).toBe(true); // caller abort reaches the engine through the linked signal
    await expect(first).rejects.toSatisfy(isAbortError);
    fake.hold(false);
    fake.flush(); // late engine settle must not surface anywhere
    await port.dispose();
    expect(fake.disposed).toBe(1);
  });

  test('encodePrompt is deterministic in the declared call', () => {
    expect(encodePrompt('action', 'person_a', { actor: 'person_a' })).toBe(encodePrompt('action', 'person_a', { actor: 'person_a' }));
    expect(encodePrompt('action', 'person_a', {})).not.toBe(encodePrompt('results', 'person_a', {}));
  });
});
