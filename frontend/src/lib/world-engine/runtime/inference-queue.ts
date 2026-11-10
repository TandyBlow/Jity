/** Serial inference queue: at most one engine call runs at a time — the
 * on-device memory budget does not allow concurrent decodes. FIFO. Every
 * entry carries its own AbortSignal; the cancellation layers are:
 *
 * - a queued entry settles immediately and is removed without touching the
 *   engine;
 * - a caller abort (or cancelPending/dispose) settles the caller's promise at
 *   once while the engine receives the linked signal — the caller never
 *   waits for the engine to honour it;
 * - the run slot is released by the ENGINE settling, never by the caller
 *   aborting, so the next inference cannot start while the device is still
 *   computing. When that finally happens the queue emits a 'stopped' event
 *   carrying the abort→stop latency;
 * - the engine promise's late settle is discarded through handlers attached
 *   up front, so it can neither reject unhandled nor overwrite the
 *   AbortError.
 *
 * cancelPending() is the non-terminal stop used by a pause/cancel button: it
 * rejects queued work and aborts the running call, but the queue keeps
 * accepting entries afterwards. dispose() is terminal. Timings and evidence
 * share one instrumentation point so queue wait and device work stay
 * distinguishable. */
import { abortError, isAbortError } from './engine';
import type { QueueEvidence } from '../local/runtime-diagnostics/types';

export interface QueueTiming {
  queuedMs: number;
  runMs: number;
  totalMs: number;
}

export interface QueuedResult<T> {
  value: T;
  timing: QueueTiming;
}

export interface QueueEntry<T> {
  label: string;
  signal?: AbortSignal;
  start: (signal: AbortSignal) => Promise<T>;
}

export interface QueueStats {
  enqueued: number;
  started: number;
  resolved: number;
  rejected: number;
  abortedQueued: number;
  abortedRunning: number;
  cancelled: number;
  disposed: number;
  maxDepth: number;
}

type Waiting<T> = QueueEntry<T> & {
  resolve: (result: QueuedResult<T>) => void;
  reject: (error: unknown) => void;
  enqueuedAt: number;
  startedAt: number | null;
  settled: boolean;
  /** Set when a caller/cancel/dispose abort settled the caller. */
  abortedAt: number | null;
  detachQueued: (() => void) | null;
};

interface Running {
  item: Waiting<never>;
  abortEngine: (reason?: unknown) => void;
  releaseSlot: () => void;
}

export class SerialInferenceQueue {
  private readonly waiting: Waiting<never>[] = [];
  private running: Running | null = null;
  private disposed = false;
  private readonly counts: QueueStats = {
    enqueued: 0, started: 0, resolved: 0, rejected: 0, abortedQueued: 0,
    abortedRunning: 0, cancelled: 0, disposed: 0, maxDepth: 0,
  };

  /** The optional hook receives stage evidence; observer bugs must not change
   * queue behaviour, so events are emitted through a guarded helper. */
  constructor(private readonly onEvent?: (event: QueueEvidence) => void) {}

  get depth(): number { return this.waiting.length + (this.running ? 1 : 0); }
  get runningLabel(): string | null { return this.running?.item.label ?? null; }
  get stats(): Readonly<QueueStats> { return { ...this.counts }; }

  run<T>(entry: QueueEntry<T>): Promise<QueuedResult<T>> {
    if (this.disposed) return Promise.reject(abortError());
    if (entry.signal?.aborted) return Promise.reject(entry.signal.reason ?? abortError());
    const enqueuedAt = performance.now();
    this.counts.enqueued += 1;
    return new Promise<QueuedResult<T>>((resolve, reject) => {
      const item: Waiting<T> = {
        ...entry, resolve, reject, enqueuedAt, startedAt: null, settled: false, abortedAt: null, detachQueued: null,
      };
      const rejectQueued = () => {
        const index = this.waiting.indexOf(item as unknown as Waiting<never>);
        if (index === -1) return; // already running: the running-path listeners own cancellation
        this.waiting.splice(index, 1);
        item.settled = true;
        item.detachQueued?.();
        const now = performance.now();
        const timing = { queuedMs: now - enqueuedAt, runMs: 0, totalMs: now - enqueuedAt };
        this.counts.abortedQueued += 1;
        this.emit('aborted-queued', entry.label, { ...timing, error: 'aborted while queued' });
        item.reject(this.withTiming(entry.signal?.reason ?? abortError(), timing));
      };
      item.detachQueued = () => entry.signal?.removeEventListener('abort', rejectQueued);
      entry.signal?.addEventListener('abort', rejectQueued, { once: true });
      this.waiting.push(item as unknown as Waiting<never>);
      this.counts.maxDepth = Math.max(this.counts.maxDepth, this.depth);
      this.emit('queued', entry.label, {});
      this.pump();
    });
  }

  /** Stop the current round without closing the queue: reject queued entries,
   * abort the running engine call and settle its caller now. The queue keeps
   * accepting work; the next entry starts once the device actually stops. */
  cancelPending(reason: unknown = abortError()): void {
    // Settle the running call first so a shared reason object carries the
    // running timing; the event stream keeps per-entry timings regardless.
    const running = this.running;
    if (running) {
      if (!running.item.settled) this.counts.cancelled += 1;
      running.abortEngine(reason);
      this.settleAbortedRun(running.item, reason);
    }
    while (this.waiting.length > 0) {
      const item = this.waiting.shift()!;
      item.detachQueued?.();
      if (item.settled) continue;
      item.settled = true;
      const now = performance.now();
      const timing = { queuedMs: now - item.enqueuedAt, runMs: 0, totalMs: now - item.enqueuedAt };
      this.counts.abortedQueued += 1;
      this.counts.cancelled += 1;
      this.emit('aborted-queued', item.label, { ...timing, error: 'cancelled before start' });
      item.reject(this.withTiming(reason, timing));
    }
  }

  /** Rejects every queued entry, aborts the running engine call and settles
   * its caller at once, then rejects all future entries. Page unload and UI
   * stop buttons share this path. Idempotent. The device slot itself frees
   * when the engine call actually settles. */
  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.counts.disposed += 1;
    this.cancelPending(abortError());
    this.emit('disposed', 'queue', {});
  }

  private pump(): void {
    if (this.running || this.disposed) return;
    const item = this.waiting.shift();
    if (!item) return;
    item.detachQueued?.();
    item.detachQueued = null;
    if (item.signal?.aborted) {
      // Defensive: the queued-abort listener normally removed this entry
      // already. Never leave a stranded entry or an idle slot.
      item.settled = true;
      item.abortedAt = performance.now();
      const timing = { queuedMs: item.abortedAt - item.enqueuedAt, runMs: 0, totalMs: item.abortedAt - item.enqueuedAt };
      this.counts.abortedQueued += 1;
      this.emit('aborted-queued', item.label, { ...timing, error: 'already aborted at start' });
      item.reject(this.withTiming(item.signal.reason ?? abortError(), timing));
      return this.pump();
    }
    item.startedAt = performance.now();
    this.counts.started += 1;
    const queuedMs = item.startedAt - item.enqueuedAt;
    this.emit('started', item.label, { queuedMs, runMs: null });
    const abortController = new AbortController();
    const abortEngine = (reason?: unknown) => abortController.abort(reason ?? item.signal?.reason);
    const abortDevice = () => abortEngine();
    const settleAborted = () => this.settleAbortedRun(item);
    item.signal?.addEventListener('abort', settleAborted, { once: true });
    item.signal?.addEventListener('abort', abortDevice, { once: true });
    const releaseSlot = () => {
      const wasRunning = this.running?.item === item;
      if (wasRunning) this.running = null;
      item.signal?.removeEventListener('abort', settleAborted);
      item.signal?.removeEventListener('abort', abortDevice);
      if (wasRunning && item.abortedAt !== null) {
        const stoppedAfterAbortMs = performance.now() - item.abortedAt;
        this.emit('stopped', item.label, {
          queuedMs, runMs: performance.now() - item.startedAt!,
          stoppedAfterAbortMs,
        });
      }
      this.pump();
    };
    this.running = { item, abortEngine, releaseSlot };
    let enginePromise: Promise<unknown>;
    try {
      enginePromise = item.start(abortController.signal);
    } catch (error) {
      // A synchronously throwing start takes the unified failure path —
      // release the slot and settle the caller — or the queue would strand.
      releaseSlot();
      if (!item.settled) {
        item.settled = true;
        const now = performance.now();
        const timing = { queuedMs, runMs: now - item.startedAt, totalMs: now - item.enqueuedAt };
        this.counts.rejected += 1;
        this.emit('rejected', item.label, { ...timing, error: String(error) });
        item.reject(isAbortError(error) ? this.withTiming(item.signal?.reason ?? abortError(), timing) : this.withTiming(error, timing));
      }
      return;
    }
    // Attached up front: a late engine rejection after a caller abort stays
    // handled and can never surface as unhandledrejection.
    void enginePromise.then(
      (value) => {
        const now = performance.now();
        releaseSlot();
        if (!item.settled) {
          item.settled = true;
          this.counts.resolved += 1;
          const timing = { queuedMs, runMs: now - item.startedAt!, totalMs: now - item.enqueuedAt };
          this.emit('resolved', item.label, timing);
          item.resolve({ value, timing } as QueuedResult<never>);
        }
      },
      (error: unknown) => {
        const now = performance.now();
        releaseSlot();
        if (!item.settled) {
          item.settled = true;
          this.counts.rejected += 1;
          const timing = { queuedMs, runMs: now - item.startedAt!, totalMs: now - item.enqueuedAt };
          this.emit('rejected', item.label, { ...timing, error: String(error) });
          item.reject(isAbortError(error) ? this.withTiming(item.signal?.reason ?? abortError(), timing) : this.withTiming(error, timing));
        }
      },
    );
  }

  /** Caller abort or cancelPending: settle the caller now; the engine's late
   * settle is discarded by the pump() handlers. Does NOT free the run slot —
   * the next inference waits until the device actually stopped. */
  private settleAbortedRun(item: Waiting<never>, reason?: unknown): void {
    if (item.settled) return;
    item.settled = true;
    item.abortedAt = performance.now();
    this.counts.abortedRunning += 1;
    const startedAt = item.startedAt ?? item.abortedAt;
    const timing = { queuedMs: startedAt - item.enqueuedAt, runMs: item.abortedAt - startedAt, totalMs: item.abortedAt - item.enqueuedAt };
    this.emit('aborted-running', item.label, { ...timing, error: 'aborted while running' });
    item.reject(this.withTiming(reason ?? item.signal?.reason ?? abortError(), timing));
  }

  private withTiming(error: unknown, timing: QueueTiming): unknown {
    if ((typeof error === 'object' && error !== null) || typeof error === 'function') {
      const target = error as { timing?: QueueTiming };
      // cancelPending/dispose may reuse one reason object for several entries;
      // never let a later entry overwrite the first measured timing.
      if (target.timing !== undefined) return error;
      try {
        target.timing = timing;
      } catch {
        // A frozen/custom reason still rejects unchanged; timing is optional.
      }
    }
    return error;
  }

  private emit(state: QueueEvidence['state'], label: string, fields: Partial<QueueEvidence>): void {
    if (!this.onEvent) return;
    const record: QueueEvidence = {
      kind: 'queue', label, state, queuedMs: null, runMs: null, depth: this.depth,
      at: performance.now(), ...fields,
    };
    try {
      this.onEvent(record);
    } catch {
      // Observers are diagnostics; a throwing observer must not corrupt the
      // serialization guarantee.
    }
  }
}
