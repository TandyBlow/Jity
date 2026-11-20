import { describe, expect, test } from 'vitest';
import { formatDiagnostics, RuntimeDiagnostics, timingStats } from './recorder';
import type { GenerationEvidence, ModelLoadEvidence, QueueEvidence } from './types';

function load(overrides: Partial<ModelLoadEvidence> = {}): ModelLoadEvidence {
  return {
    kind: 'load', modelUrl: '/models/m.gguf', modelId: 'm.gguf', contextSize: 4096, gpuLayers: 99999,
    numThreads: 4, useCache: false, directBlob: true, fetchMs: 100, compileMs: 400, totalMs: 500,
    outcome: 'loaded', at: 0, ...overrides,
  };
}

function generation(overrides: Partial<GenerationEvidence> = {}): GenerationEvidence {
  return {
    kind: 'generation', outcome: 'completed', raw: '正文', finishReason: 'stop', firstTokenMs: 120,
    wallMs: 900, firstChunkMs: 100, firstReadableMs: 140, maxStreamGapMs: 60, streamChunks: 20,
    promptTokens: 300, cachedPromptTokens: 30, contextSize: 4096, maxTokens: 256, cachePrompt: true,
    abortCause: null, abortRequestedMs: null, stoppedMs: null, hardStopped: false, at: 0, ...overrides,
  };
}

function queue(overrides: Partial<QueueEvidence> = {}): QueueEvidence {
  return { kind: 'queue', label: 'action', state: 'resolved', queuedMs: 10, runMs: 400, depth: 0, at: 0, ...overrides };
}

describe('timingStats', () => {
  test('nearest-rank percentiles, mean, min and max over the finite values', () => {
    expect(timingStats([10, 20, 30, 40])).toEqual({ count: 4, minMs: 10, meanMs: 25, p50Ms: 20, p95Ms: 40, maxMs: 40 });
    expect(timingStats([5])).toEqual({ count: 1, minMs: 5, meanMs: 5, p50Ms: 5, p95Ms: 5, maxMs: 5 });
  });

  test('empty and null-only inputs stay null', () => {
    expect(timingStats([])).toEqual({ count: 0, minMs: null, meanMs: null, p50Ms: null, p95Ms: null, maxMs: null });
    expect(timingStats([null, undefined, Number.NaN])).toEqual({ count: 0, minMs: null, meanMs: null, p50Ms: null, p95Ms: null, maxMs: null });
  });
});

describe('RuntimeDiagnostics', () => {
  test('summarises loads, generations, cancellations and queue into one snapshot', () => {
    const diagnostics = new RuntimeDiagnostics();
    diagnostics.record(load({ fromCache: true }));
    diagnostics.record(load({ outcome: 'failed', modelId: null, totalMs: 50, compileMs: null, fetchMs: null, error: 'boom' }));
    diagnostics.record(generation());
    diagnostics.record(generation({ outcome: 'timeout', finishReason: 'timeout', abortCause: 'timeout',
      abortRequestedMs: 200, stoppedMs: 30, hardStopped: true, firstTokenMs: 100, firstReadableMs: 120 }));
    diagnostics.record(generation({ outcome: 'aborted', abortCause: 'caller', abortRequestedMs: 80, stoppedMs: 12, finishReason: null }));
    diagnostics.record(queue({ state: 'queued', runMs: null }));
    diagnostics.record(queue({ state: 'started', runMs: null }));
    diagnostics.record(queue({ state: 'resolved' }));

    const summary = diagnostics.summary();
    expect(summary.loads).toMatchObject({ count: 2, loaded: 1, failed: 1, cached: 1, lastModelId: null, lastContextSize: 4096 });
    expect(summary.loads.total.p50Ms).toBe(50); // nearest rank over [50,500]
    expect(summary.generations).toMatchObject({
      count: 3, completed: 1, timeout: 1, aborted: 1, hardStops: 1, meanCacheHitRatio: 0.1,
    });
    expect(summary.generations.firstReadable.p50Ms).toBe(140);
    expect(summary.cancellations).toMatchObject({ count: 2, timeout: 1, caller: 1, dispose: 0, hardStops: 1 });
    expect(summary.cancellations.stopLatency).toMatchObject({ count: 2, minMs: 12, maxMs: 30 });
    expect(summary.queue).toMatchObject({ events: 3, enqueued: 1, started: 1, resolved: 1, maxDepth: 0 });
    expect(summary.queue.run.p50Ms).toBe(400);
    expect(formatDiagnostics(summary)).toContain('firstReadable=140ms');
    expect(() => JSON.stringify(diagnostics.snapshot())).not.toThrow();
  });

  test('the ring buffer is bounded and reports evictions', () => {
    const diagnostics = new RuntimeDiagnostics({ limit: 2 });
    diagnostics.record(load());
    diagnostics.record(generation());
    diagnostics.record(queue());
    expect(diagnostics.records).toHaveLength(2);
    expect(diagnostics.dropped).toBe(1);
    expect(diagnostics.records[0]!.kind).toBe('generation');
    diagnostics.reset();
    expect(diagnostics.records).toHaveLength(0);
    expect(diagnostics.dropped).toBe(0);
  });

  test('handler properties stay bound when passed directly to callbacks', () => {
    const diagnostics = new RuntimeDiagnostics();
    const onLoad = diagnostics.onLoad;
    const onGeneration = diagnostics.onGeneration;
    const onQueue = diagnostics.onQueue;
    onLoad(load());
    onGeneration(generation());
    onQueue(queue());
    expect(diagnostics.records.map((record) => record.kind)).toEqual(['load', 'generation', 'queue']);
  });

  test('a bad limit is rejected instead of silently disabling the buffer', () => {
    expect(() => new RuntimeDiagnostics({ limit: 0 })).toThrow(/positive integer/);
  });
});
