/** Per-point narration queue.
 *
 * A committed point owns an immutable narration job: pointId + the server's
 * saved before/delta/after read at claim time. Jobs are processed in commit
 * order while the controller's settlement loop keeps moving to the next
 * point. State writes remain the controller's serial business; this queue
 * never applies a point, rewrites a prior text, or feeds its output back into
 * settlement. The model's text is the product text unchanged — the only
 * outcomes synthesized here are empty text and an inference error.
 *
 * The queue deliberately does not share ControllerMemory: the next point's
 * settlement mutates that memory concurrently, and narration must not read a
 * later point's state or overwrite the current head's narration state.
 */
import type { WorldModelPort } from '../../controller';
import { assembleNarrationInput, initialNarrationAssembly, type NarrationAssembly } from '../../schedule';
import type { CurrentClaim, Id, Json, NarrationStatus, TimeAdvance, WorldContext, WorldState, RequestMap } from '../../types';
import { WorldApiError, type WorldTransport } from '../../transport';

export type PointNarrationOutcome =
  | { status: 'ready'; pointId: Id; text: string }
  | { status: 'failed'; pointId: Id; reason: string }
  | { status: 'skipped'; pointId: Id; reason: string };

interface Job { pointId: Id; }

export interface PointNarrationQueueOptions {
  transport: WorldTransport;
  model: WorldModelPort;
  worldId: Id;
  requestId: () => Id;
  /** The writer lease and epoch currently held by the controller. History
   * claims do not carry them; head claims do. */
  lease: () => { leaseToken: Id; fenceEpoch: number } | null;
  onOutcome?: (outcome: PointNarrationOutcome) => void;
}

export class PointNarrationQueue {
  private readonly queued: Job[] = [];
  private readonly known = new Set<Id>();
  private readonly retried = new Set<Id>();
  private running = false;
  private settling: Promise<void> | null = null;
  private releaseSettled: (() => void) | null = null;
  private worldId: Id;

  constructor(private readonly options: PointNarrationQueueOptions) {
    this.worldId = options.worldId;
  }

  setWorldId(worldId: Id): void { this.worldId = worldId; }

  /** Enqueue one point exactly once. Re-enqueueing a point that already has a
   * job (queued, running, ready or failed) is a no-op; an explicit retry uses
   * retry(). */
  enqueue(pointId: Id): void {
    if (this.known.has(pointId)) return;
    this.known.add(pointId);
    this.queued.push({ pointId });
    this.wake();
  }

  /** True while a point has queued/running narration. */
  get busy(): boolean { return this.running || this.queued.length > 0; }

  has(pointId: Id): boolean { return this.known.has(pointId); }

  /** Drop the one-shot guard for a point the player explicitly asks to retry
   * (a failed inference or an empty answer). The point keeps its identity;
   * this never re-settles state. */
  retry(pointId: Id): void {
    this.known.delete(pointId);
    this.retried.add(pointId);
    this.enqueue(pointId);
  }

  /** Resolves when every currently queued job has finished. A job enqueued
   * while draining is included in the same wait. */
  settled(): Promise<void> {
    if (!this.busy) return Promise.resolve();
    if (!this.settling) {
      this.settling = new Promise<void>((resolve) => { this.releaseSettled = resolve; });
    }
    return this.settling;
  }

  private wake(): void {
    if (this.running) return;
    this.running = true;
    const run = this.drain();
    this.settling = run;
    void run.then(() => {
      this.running = false;
      if (this.queued.length) {
        // A late enqueue landed after the drain loop checked the queue but
        // before running cleared: start the next drain in the same promise.
        this.wake();
        return;
      }
      this.settling = null;
      this.releaseSettled?.();
      this.releaseSettled = null;
    }, () => {
      this.running = false;
      this.settling = null;
      this.releaseSettled?.();
      this.releaseSettled = null;
    });
  }

  private async drain(): Promise<void> {
    while (this.queued.length) {
      const job = this.queued.shift()!;
      try {
        const outcome = await this.runJob(job.pointId);
        if (outcome) this.options.onOutcome?.(outcome);
      } catch (error) {
        // A failed job never blocks a later point: the failure belongs to its
        // own point. Transport/claim problems are reported, not retried
        // against another point.
        this.options.onOutcome?.({
          status: 'failed', pointId: job.pointId,
          reason: error instanceof Error ? error.message : String(error),
        });
      }
    }
  }

  private async runJob(pointId: Id): Promise<PointNarrationOutcome | null> {
    const current = await this.readNarration(pointId);
    // A ready text is immutable; a failed entry waits for an explicit retry.
    if (current.narrationStatus === 'ready') return { status: 'skipped', pointId, reason: 'already_ready' };
    if (current.narrationStatus === 'failed' && !this.retried.delete(pointId)) {
      return { status: 'skipped', pointId, reason: 'already_failed' };
    }

    const context = await this.context();
    if (!context.world) return { status: 'failed', pointId, reason: 'world_context_missing' };
    const mode: 'head' | 'history' = context.world.head.pointId === pointId ? 'head' : 'history';
    const claim = await this.claim(pointId, mode);
    const assembly = await this.readAssembly(pointId);
    const input = assembleNarrationInput(assembly);
    if (!input) {
      const reason = 'narration_read_incomplete';
      await this.submitFailure(pointId, mode, claim, reason);
      return { status: 'failed', pointId, reason };
    }

    let output: Json;
    try {
      output = await this.options.model.generate('narration', pointId, input);
    } catch (error) {
      // Cancellation/abort is not an inference failure: leave the entry
      // pending so the same point can be resumed after the control request.
      if (isCancellation(error)) return { status: 'skipped', pointId, reason: 'model_cancelled' };
      await this.submitFailure(pointId, mode, claim, errorMessage(error));
      return { status: 'failed', pointId, reason: errorMessage(error) };
    }
    if (typeof output !== 'string') {
      const reason = 'model_output_not_text';
      await this.submitFailure(pointId, mode, claim, reason);
      return { status: 'failed', pointId, reason };
    }
    if (output.trim() === '') {
      // Empty text is a status, never program-written prose.
      const reason = 'empty_model_output';
      await this.submitFailure(pointId, mode, claim, reason);
      return { status: 'failed', pointId, reason };
    }
    await this.submitText(pointId, mode, claim, output);
    return { status: 'ready', pointId, text: output };
  }

  private async context(): Promise<{ world: WorldContext | null }> {
    const response = await this.options.transport.execute('get_context', {}, { worldId: this.worldId });
    return { world: response.world ?? null };
  }

  private async readNarration(pointId: Id): Promise<{ narrationStatus: NarrationStatus; generation: number | null; text: string | null }> {
    const response = await this.options.transport.execute('narration_get', {} as RequestMap['narration_get'],
      { worldId: this.worldId, pointId });
    return response.data;
  }

  private async claim(pointId: Id, mode: 'head' | 'history'): Promise<CurrentClaim> {
    const lease = mode === 'head' ? this.options.lease() : null;
    if (mode === 'head' && !lease) throw new Error('narration_claim_without_lease');
    const response = await this.options.transport.execute('narration_claim', {
      protocolVersion: 2,
      requestId: this.options.requestId(),
      worldId: this.worldId,
      pointId,
      ...(mode === 'head'
        ? { mode: 'head' as const, leaseToken: lease!.leaseToken, fenceEpoch: lease!.fenceEpoch }
        : { mode: 'history' as const }),
      currentClaim: null,
    }, { worldId: this.worldId, pointId });
    const summary = response.data;
    if (!('claimToken' in summary) || !summary.claimToken) throw new Error('narration_claim_replayed_without_token');
    return {
      claimToken: summary.claimToken,
      generation: summary.generation,
      issuedAtEpochMilli: summary.issuedAtEpochMilli,
    };
  }

  private async readAssembly(pointId: Id): Promise<NarrationAssembly> {
    const assembly = initialNarrationAssembly(pointId);
    const target = await this.readState(pointId);
    if (target.pointId !== pointId || target.previousPointId === undefined
      || target.timeAdvance === undefined || target.entityDeltas === undefined || target.state === undefined) {
      assembly.readIncomplete = true;
      return assembly;
    }
    assembly.after = target.state;
    assembly.previousPointId = target.previousPointId;
    assembly.delta = { timeAdvance: target.timeAdvance, entityDeltas: target.entityDeltas };
    if (target.previousPointId != null) {
      const before = await this.readState(target.previousPointId);
      if (before.pointId !== target.previousPointId || before.state === undefined) {
        assembly.readIncomplete = true;
        return assembly;
      }
      assembly.before = before.state;
    }
    return assembly;
  }

  private async readState(pointId: Id): Promise<{
    pointId: Id; state: WorldState; previousPointId: Id | null;
    timeAdvance: TimeAdvance | null;
    entityDeltas: NonNullable<NarrationAssembly['delta']>['entityDeltas'];
  }> {
    const response = await this.options.transport.execute('get_state', { point: pointId }, { worldId: this.worldId });
    return response.data;
  }

  private async submitFailure(pointId: Id, mode: 'head' | 'history', claim: CurrentClaim, reason: string): Promise<void> {
    await this.submit(pointId, mode, claim, { outcome: 'failed', text: null, failureReason: reason });
  }

  private async submitText(pointId: Id, mode: 'head' | 'history', claim: CurrentClaim, text: string): Promise<void> {
    await this.submit(pointId, mode, claim, { outcome: 'ready', text, failureReason: null });
  }

  private async submit(
    pointId: Id, mode: 'head' | 'history', claim: CurrentClaim,
    outcome: { outcome: 'ready'; text: string; failureReason: null } | { outcome: 'failed'; text: null; failureReason: string },
  ): Promise<void> {
    try {
      await this.postSubmit(pointId, mode, claim, outcome);
      return;
    } catch (error) {
      if (!(error instanceof WorldApiError)) throw error;
      const code = error.response.error.code;
      if (code !== 'claim_expired' && code !== 'claim_fenced' && code !== 'version_mismatch') throw error;
      // The generated text is kept: a claim that expired or was fenced by a
      // newer head is re-acquired for the SAME point, then the same text is
      // submitted. No model re-roll and no attachment to the new head.
      const context = await this.context();
      const retryMode: 'head' | 'history' = context.world?.head.pointId === pointId ? 'head' : 'history';
      const retryClaim = await this.claim(pointId, retryMode);
      await this.postSubmit(pointId, retryMode, retryClaim, outcome);
    }
  }

  private async postSubmit(
    pointId: Id, mode: 'head' | 'history', claim: CurrentClaim,
    outcome: { outcome: 'ready'; text: string; failureReason: null } | { outcome: 'failed'; text: null; failureReason: string },
  ): Promise<void> {
    const lease = mode === 'head' ? this.options.lease() : null;
    if (mode === 'head' && !lease) throw new Error('narration_submit_without_lease');
    await this.options.transport.execute('narration_submit', {
      protocolVersion: 2,
      requestId: this.options.requestId(),
      worldId: this.worldId,
      pointId,
      ...(mode === 'head'
        ? { mode: 'head' as const, leaseToken: lease!.leaseToken, fenceEpoch: lease!.fenceEpoch }
        : { mode: 'history' as const }),
      claimToken: claim.claimToken,
      generation: claim.generation,
      issuedAtEpochMilli: claim.issuedAtEpochMilli,
      ...outcome,
    }, { worldId: this.worldId, pointId });
  }
}

function isCancellation(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false;
  const name = (error as { name?: string }).name;
  const message = (error as { message?: string }).message ?? '';
  return name === 'AbortError' || name === 'ModelCancelledError' || message.includes('model_output_discarded_by_cancel');
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

