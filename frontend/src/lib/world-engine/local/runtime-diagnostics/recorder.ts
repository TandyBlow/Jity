/** In-memory evidence recorder for the browser runtime. It is deliberately
 * small and dependency-free: the page (or a measurement script) passes
 * `record`/`onLoad`/`onGeneration` into the engine and `record` into the
 * inference queue, and can export `snapshot()` as JSON. The buffer is
 * bounded, so a long session cannot grow memory without limit; `dropped`
 * tells the reader how many old records were evicted. */
import type {
  GenerationEvidence,
  ModelLoadEvidence,
  QueueEvidence,
  RuntimeDiagnosticsRecord,
  RuntimeDiagnosticsSnapshot,
  RuntimeDiagnosticsSummary,
  TimingStats,
} from './types';

const EMPTY_STATS: TimingStats = { count: 0, minMs: null, meanMs: null, p50Ms: null, p95Ms: null, maxMs: null };

function round(value: number): number {
  return Math.round(value * 10) / 10;
}

/** Nearest-rank percentiles, rounded to one decimal so JSON stays stable. */
export function timingStats(values: Array<number | null | undefined>): TimingStats {
  const numbers = values.filter((value): value is number => typeof value === 'number' && Number.isFinite(value)).sort((a, b) => a - b);
  if (numbers.length === 0) return { ...EMPTY_STATS };
  const rank = (q: number) => Math.min(numbers.length - 1, Math.max(0, Math.ceil(q * numbers.length) - 1));
  const mean = numbers.reduce((sum, value) => sum + value, 0) / numbers.length;
  return {
    count: numbers.length,
    minMs: round(numbers[0]!),
    meanMs: round(mean),
    p50Ms: round(numbers[rank(0.5)]!),
    p95Ms: round(numbers[rank(0.95)]!),
    maxMs: round(numbers[numbers.length - 1]!),
  };
}

function outcomeCount(records: GenerationEvidence[], outcome: GenerationEvidence['outcome']): number {
  return records.filter((record) => record.outcome === outcome).length;
}

export interface RuntimeDiagnosticsOptions {
  /** Maximum retained records; older records are evicted (default 512). */
  limit?: number;
}

export class RuntimeDiagnostics {
  private buffer: RuntimeDiagnosticsRecord[] = [];
  private droppedCount = 0;
  private readonly limit: number;

  constructor(options: RuntimeDiagnosticsOptions = {}) {
    const limit = options.limit ?? 512;
    if (!Number.isInteger(limit) || limit <= 0) throw new Error('runtime diagnostics limit must be a positive integer');
    this.limit = limit;
  }

  /** Bound on purpose: the page can hand this straight to callbacks. */
  readonly record = (event: RuntimeDiagnosticsRecord): void => {
    this.buffer.push(event);
    if (this.buffer.length > this.limit) {
      this.droppedCount += this.buffer.length - this.limit;
      this.buffer.splice(0, this.buffer.length - this.limit);
    }
  };

  readonly onLoad = (event: ModelLoadEvidence): void => this.record(event);
  readonly onGeneration = (event: GenerationEvidence): void => this.record(event);
  readonly onQueue = (event: QueueEvidence): void => this.record(event);

  get records(): readonly RuntimeDiagnosticsRecord[] { return this.buffer; }
  get dropped(): number { return this.droppedCount; }

  reset(): void {
    this.buffer = [];
    this.droppedCount = 0;
  }

  summary(): RuntimeDiagnosticsSummary {
    const records = this.buffer;
    const loads = records.filter((record): record is ModelLoadEvidence => record.kind === 'load');
    const generations = records.filter((record): record is GenerationEvidence => record.kind === 'generation');
    const queue = records.filter((record): record is QueueEvidence => record.kind === 'queue');
    const lastLoad = loads.at(-1) ?? null;
    const cancellations = generations.filter((record) => record.abortCause !== null || record.outcome === 'timeout');
    const cacheRatios = generations
      .filter((record) => typeof record.cachedPromptTokens === 'number' && typeof record.promptTokens === 'number' && (record.promptTokens! + record.cachedPromptTokens!) > 0)
      .map((record) => record.cachedPromptTokens! / (record.promptTokens! + record.cachedPromptTokens!));

    return {
      loads: {
        count: loads.length,
        loaded: loads.filter((record) => record.outcome === 'loaded').length,
        failed: loads.filter((record) => record.outcome === 'failed').length,
        aborted: loads.filter((record) => record.outcome === 'aborted').length,
        discarded: loads.filter((record) => record.outcome === 'discarded').length,
        timeout: loads.filter((record) => record.outcome === 'timeout').length,
        lastModelId: lastLoad?.modelId ?? null,
        lastContextSize: lastLoad?.contextSize ?? null,
        total: timingStats(loads.map((record) => record.totalMs)),
        fetch: timingStats(loads.map((record) => record.fetchMs)),
        compile: timingStats(loads.map((record) => record.compileMs)),
      },
      generations: {
        count: generations.length,
        completed: outcomeCount(generations, 'completed'),
        incomplete: outcomeCount(generations, 'incomplete'),
        aborted: outcomeCount(generations, 'aborted'),
        timeout: outcomeCount(generations, 'timeout'),
        error: outcomeCount(generations, 'error'),
        hardStops: generations.filter((record) => record.hardStopped).length,
        firstChunk: timingStats(generations.map((record) => record.firstChunkMs)),
        firstToken: timingStats(generations.map((record) => record.firstTokenMs)),
        firstReadable: timingStats(generations.map((record) => record.firstReadableMs)),
        wall: timingStats(generations.map((record) => record.wallMs)),
        maxStreamGap: timingStats(generations.map((record) => record.maxStreamGapMs)),
        promptTokens: timingStats(generations.map((record) => record.promptTokens)),
        meanCacheHitRatio: cacheRatios.length === 0 ? null : round(cacheRatios.reduce((sum, value) => sum + value, 0) / cacheRatios.length),
      },
      cancellations: {
        count: cancellations.length,
        caller: cancellations.filter((record) => record.abortCause === 'caller').length,
        timeout: cancellations.filter((record) => record.abortCause === 'timeout').length,
        dispose: cancellations.filter((record) => record.abortCause === 'dispose').length,
        hardStops: cancellations.filter((record) => record.hardStopped).length,
        stopLatency: timingStats(cancellations.map((record) => record.stoppedMs)),
      },
      queue: {
        events: queue.length,
        enqueued: queue.filter((record) => record.state === 'queued').length,
        started: queue.filter((record) => record.state === 'started').length,
        resolved: queue.filter((record) => record.state === 'resolved').length,
        rejected: queue.filter((record) => record.state === 'rejected').length,
        abortedQueued: queue.filter((record) => record.state === 'aborted-queued').length,
        abortedRunning: queue.filter((record) => record.state === 'aborted-running').length,
        stopped: queue.filter((record) => record.state === 'stopped').length,
        maxDepth: queue.reduce((max, record) => Math.max(max, record.depth), 0),
        queued: timingStats(queue.filter((record) => record.state === 'started').map((record) => record.queuedMs)),
        run: timingStats(queue
          .filter((record) => record.state === 'resolved' || record.state === 'rejected' || record.state === 'aborted-running')
          .map((record) => record.runMs)),
      },
    };
  }

  snapshot(): RuntimeDiagnosticsSnapshot {
    return { generatedAt: new Date().toISOString(), records: this.buffer.slice(), summary: this.summary() };
  }

  toJSON(): RuntimeDiagnosticsSnapshot { return this.snapshot(); }
}

/** One-line, log-friendly view. Deliberately shows p50 and worst case —
 * a mean alone hides a stalled decode. */
export function formatDiagnostics(summary: RuntimeDiagnosticsSummary): string {
  const num = (value: number | null) => (value === null ? 'n/a' : `${value}ms`);
  const load = summary.loads;
  const gen = summary.generations;
  const cancel = summary.cancellations;
  return [
    `loads=${load.count} ${num(load.total.p50Ms)} (fetch ${num(load.fetch.p50Ms)}, compile ${num(load.compile.p50Ms)})`,
    `generations=${gen.count} firstToken=${num(gen.firstToken.p50Ms)} firstReadable=${num(gen.firstReadable.p50Ms)}`,
    `wall=${num(gen.wall.p50Ms)} maxGap=${num(gen.maxStreamGap.maxMs)}`,
    `cancels=${cancel.count} stop=${num(cancel.stopLatency.p50Ms)} hardStops=${cancel.hardStops}`,
    `queue=${summary.queue.events} run=${num(summary.queue.run.p50Ms)}`,
  ].join(' | ');
}
