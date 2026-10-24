import { describe, expect, test } from 'vitest';
import { isAbortError } from './engine';
import { SerialInferenceQueue } from './inference-queue';

function deferred<T = string>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

/** A controllable engine step: records the start order, resolves `started`
 * when the engine actually receives the call (observable without settling),
 * and hands the test the deferred that settles the underlying call. */
function step(log: string[], label: string) {
  const gate = deferred();
  const started = deferred<void>();
  const start = (signal: AbortSignal) => {
    log.push(label);
    started.resolve();
    void signal.addEventListener('abort', () => log.push(`${label}:aborted`), { once: true });
    return gate.promise;
  };
  return { start, gate, started: started.promise };
}

describe('SerialInferenceQueue', () => {
  test('runs FIFO, one at a time, and exposes slot state', async () => {
    const queue = new SerialInferenceQueue();
    const log: string[] = [];
    const a = step(log, 'a');
    const b = step(log, 'b');
    const first = queue.run({ label: 'a', start: a.start });
    const second = queue.run({ label: 'b', start: b.start });
    expect(queue.depth).toBe(2);
    expect(queue.runningLabel).toBe('a');
    a.gate.resolve('va');
    const firstResult = await first;
    expect(firstResult.value).toBe('va');
    expect(firstResult.timing.runMs).toBeGreaterThanOrEqual(0);
    await b.started; // started only after a settled
    expect(log).toEqual(['a', 'b']);
    b.gate.resolve('vb');
    expect((await second).value).toBe('vb');
    expect(queue.depth).toBe(0);
  });

  test('a queued entry aborts without ever touching the engine', async () => {
    const queue = new SerialInferenceQueue();
    const log: string[] = [];
    const a = step(log, 'a');
    const c = step(log, 'c');
    const first = queue.run({ label: 'a', start: a.start });
    const controller = new AbortController();
    const second = queue.run({ label: 'b', start: () => { log.push('b'); return Promise.resolve('vb'); }, signal: controller.signal });
    const third = queue.run({ label: 'c', start: c.start });
    controller.abort();
    await expect(second).rejects.toSatisfy(isAbortError);
    expect(queue.depth).toBe(2); // a running + c queued, b gone
    a.gate.resolve('va');
    await first;
    await c.started;
    expect(log).toEqual(['a', 'c']); // b never started
    c.gate.resolve('vc');
    expect((await third).value).toBe('vc');
  });

  test('a running entry settles on abort at once but holds the slot until the engine stops', async () => {
    const queue = new SerialInferenceQueue();
    const log: string[] = [];
    const a = step(log, 'a');
    const b = step(log, 'b');
    const controller = new AbortController();
    const first = queue.run({ label: 'a', start: a.start, signal: controller.signal });
    const second = queue.run({ label: 'b', start: b.start });
    controller.abort();
    await expect(first).rejects.toSatisfy(isAbortError);
    expect(log).toEqual(['a', 'a:aborted']); // engine received the linked signal
    expect(queue.runningLabel).toBe('a'); // slot NOT freed by the caller abort
    expect(queue.depth).toBe(2); // b still waiting behind the engine
    a.gate.reject(new DOMException('Aborted', 'AbortError')); // engine stops
    await b.started; // only now does b start
    expect(log).toEqual(['a', 'a:aborted', 'b']);
    b.gate.resolve('vb');
    expect((await second).value).toBe('vb');
  });

  test('a late engine resolve after a caller abort is discarded, not unhandled', async () => {
    const queue = new SerialInferenceQueue();
    const log: string[] = [];
    const a = step(log, 'a');
    const b = step(log, 'b');
    const controller = new AbortController();
    const first = queue.run({ label: 'a', start: a.start, signal: controller.signal });
    const second = queue.run({ label: 'b', start: b.start });
    controller.abort();
    await expect(first).rejects.toSatisfy(isAbortError);
    a.gate.resolve('late value the caller must never see');
    await b.started; // slot freed by the engine settle; b runs
    expect(log).toEqual(['a', 'a:aborted', 'b']);
    await expect(first).rejects.toSatisfy(isAbortError); // still the AbortError
    b.gate.resolve('vb');
    expect((await second).value).toBe('vb');
  });

  test('a late engine rejection after a caller abort stays handled', async () => {
    const queue = new SerialInferenceQueue();
    const log: string[] = [];
    const a = step(log, 'a');
    const b = step(log, 'b');
    const controller = new AbortController();
    const first = queue.run({ label: 'a', start: a.start, signal: controller.signal });
    const second = queue.run({ label: 'b', start: b.start });
    controller.abort();
    await expect(first).rejects.toSatisfy(isAbortError);
    a.gate.reject(new Error('late engine failure')); // must not become an unhandled rejection
    await b.started;
    expect(log).toEqual(['a', 'a:aborted', 'b']);
    b.gate.resolve('vb');
    expect((await second).value).toBe('vb');
  });

  test('dispose rejects queued and running callers now and future entries always', async () => {
    const queue = new SerialInferenceQueue();
    const log: string[] = [];
    const a = step(log, 'a');
    const b = step(log, 'b');
    const first = queue.run({ label: 'a', start: a.start });
    const second = queue.run({ label: 'b', start: b.start });
    queue.dispose();
    await expect(first).rejects.toSatisfy(isAbortError);
    await expect(second).rejects.toSatisfy(isAbortError);
    expect(log).toEqual(['a', 'a:aborted']);
    await expect(queue.run({ label: 'c', start: () => Promise.resolve('vc') })).rejects.toSatisfy(isAbortError);
    a.gate.resolve('late');
    expect(log).toEqual(['a', 'a:aborted']); // disposed pump never starts b
  });

  test('pre-aborted signals and spontaneous engine aborts settle as AbortError', async () => {
    const queue = new SerialInferenceQueue();
    const controller = new AbortController();
    controller.abort();
    await expect(queue.run({ label: 'a', start: () => Promise.resolve('va'), signal: controller.signal }))
      .rejects.toSatisfy(isAbortError);
    const log: string[] = [];
    const spontaneous = step(log, 'a');
    const first = queue.run({ label: 'a', start: spontaneous.start });
    spontaneous.gate.reject(new DOMException('engine aborted itself', 'AbortError'));
    await expect(first).rejects.toSatisfy(isAbortError);
  });

  test('timings separate queue wait from engine run', async () => {
    const queue = new SerialInferenceQueue();
    const hold = deferred();
    const first = queue.run({ label: 'hold', start: () => hold.promise });
    const second = queue.run({ label: 'timed', start: () => new Promise((resolve) => setTimeout(() => resolve('ok'), 30)) });
    hold.resolve('vh');
    await first;
    const result = await second;
    expect(result.value).toBe('ok');
    expect(result.timing.queuedMs).toBeGreaterThan(0); // waited behind the first call
    expect(result.timing.runMs).toBeGreaterThanOrEqual(25);
    expect(result.timing.totalMs).toBeGreaterThanOrEqual(result.timing.queuedMs + result.timing.runMs - 1);
  });
});
