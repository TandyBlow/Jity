/** Serial inference queue: at most one engine call runs at a time — the
 * on-device memory budget does not allow concurrent decodes. FIFO. Every
 * entry carries its own AbortSignal; the cancellation layers are:
 * queued entries settle immediately without ever touching the engine; a
 * caller abort (or dispose) settles the caller's promise at once while the
 * engine receives the linked signal — the caller is never made to wait for
 * the engine to honor it, mirroring the HTTP transport's rule that a timeout
 * settles even if the implementation ignores abort; and the engine promise's
 * late settle is discarded through handlers attached up front, so it can
 * neither reject unhandled nor overwrite the AbortError. The run slot is
 * released by the ENGINE settling, never by the caller aborting: the next
 * inference must wait until the device actually stopped computing. Timings
 * (queuedMs/runMs/totalMs) share one instrumentation point with load and
 * inference measurements. */
import { abortError, isAbortError } from './engine';

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

type Waiting<T> = QueueEntry<T> & {
  resolve: (result: QueuedResult<T>) => void;
  reject: (error: unknown) => void;
  enqueuedAt: number;
  settled: boolean;
};

interface Running {
  item: Waiting<never>;
  abortEngine: () => void;
  releaseSlot: () => void;
}

export class SerialInferenceQueue {
  private readonly waiting: Waiting<never>[] = [];
  private running: Running | null = null;
  private disposed = false;

  get depth(): number { return this.waiting.length + (this.running ? 1 : 0); }
  get runningLabel(): string | null { return this.running?.item.label ?? null; }

  run<T>(entry: QueueEntry<T>): Promise<QueuedResult<T>> {
    if (this.disposed) return Promise.reject(abortError());
    if (entry.signal?.aborted) return Promise.reject(entry.signal.reason ?? abortError());
    return new Promise<QueuedResult<T>>((resolve, reject) => {
      const item: Waiting<T> = { ...entry, resolve, reject, enqueuedAt: performance.now(), settled: false };
      const rejectQueued = () => {
        const index = this.waiting.indexOf(item as unknown as Waiting<never>);
        if (index !== -1) {
          this.waiting.splice(index, 1);
          item.settled = true;
          item.reject(entry.signal?.reason ?? abortError());
        } // else already running: the running-path listeners own cancellation
        entry.signal?.removeEventListener('abort', rejectQueued);
      };
      entry.signal?.addEventListener('abort', rejectQueued, { once: true });
      this.waiting.push(item as unknown as Waiting<never>);
      this.pump();
    });
  }

  /** Rejects every queued entry, aborts the running engine call and settles
   * its caller at once, then rejects all future entries. Page unload and UI
   * stop buttons share this path. The device slot itself frees when the
   * engine call actually settles. */
  dispose(): void {
    this.disposed = true;
    while (this.waiting.length > 0) {
      const item = this.waiting.shift()!;
      item.settled = true;
      item.reject(abortError());
    }
    const running = this.running;
    if (running) {
      running.abortEngine();
      this.settleAbortedRun(running.item);
    }
  }

  private pump(): void {
    if (this.running || this.disposed) return;
    const item = this.waiting.shift();
    if (!item) return;
    const abortController = new AbortController();
    const abortEngine = () => abortController.abort(item.signal?.reason);
    const settleAborted = () => this.settleAbortedRun(item);
    if (item.signal?.aborted) settleAborted();
    else item.signal?.addEventListener('abort', settleAborted, { once: true });
    item.signal?.addEventListener('abort', abortEngine, { once: true });
    const releaseSlot = () => {
      if (this.running?.item === item) this.running = null;
      item.signal?.removeEventListener('abort', settleAborted);
      item.signal?.removeEventListener('abort', abortEngine);
      this.pump();
    };
    if (item.signal?.aborted) {
      // Unreachable in the normal flow (pre-aborted entries never enqueue;
      // queued aborts are removed before pump), but never leave the slot idle.
      settleAborted();
      return this.pump();
    }
    this.running = { item, abortEngine, releaseSlot };
    const queuedMs = performance.now() - item.enqueuedAt;
    const runStarted = performance.now();
    const enginePromise: Promise<unknown> = item.start(abortController.signal);
    // Attached up front: a late engine rejection after a caller abort stays
    // handled and can never surface as unhandledrejection.
    void enginePromise.then(
      (value) => {
        releaseSlot();
        if (!item.settled) {
          item.settled = true;
          item.resolve({ value, timing: { queuedMs, runMs: performance.now() - runStarted, totalMs: performance.now() - item.enqueuedAt } } as QueuedResult<never>);
        }
      },
      (error: unknown) => {
        releaseSlot();
        if (!item.settled) {
          item.settled = true;
          item.reject(isAbortError(error) ? (item.signal?.reason ?? abortError()) : error);
        }
      },
    );
  }

  /** Caller abort or dispose: settle the caller now; the engine's late
   * settle is discarded by the pump() handlers. Does NOT free the run slot —
   * the next inference waits until the device actually stopped. */
  private settleAbortedRun(item: Waiting<never>): void {
    if (item.settled) return;
    item.settled = true;
    item.reject(item.signal?.reason ?? abortError());
  }
}
