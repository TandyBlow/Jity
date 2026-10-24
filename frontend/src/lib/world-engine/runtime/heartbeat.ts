/** Dual heartbeat: lease renewal and head-narration-claim renewal. The
 * schedule basis is always the SERVER-RECEIPTED expiry — the lease view of
 * a response envelope (or a renew's data), a claim's data.expiresAtEpochMilli
 * (CurrentClaim carries no expiry, so controller memory alone cannot schedule
 * this). Renewals fire at expiry − leadMs; a state update (any newer
 * token/epoch/expiry observation) reschedules and voids renewals still
 * in flight for the superseded state via a cycle counter.
 *
 * Heartbeats are TRANSPORT calls and deliberately bypass the inference
 * queue: they run concurrently with engine calls — that concurrency is the
 * long-inference keep-alive. Timeouts and retryable rejections back off with
 * the SAME requestId (renew idempotency replays the original data); a
 * definitive rejection is a loss: that heartbeat stops and onLost reports
 * the code and response, so the session can abort in-flight work — late
 * results are already discarded by the queue. Unexpected non-API errors are
 * treated as transient and retried; takeover correctness stays in H2. */
import { errorCatalog } from '../schedule';
import { WorldApiError, WorldTimeoutError } from '../transport';
import type { ErrorCode, ErrorResponse, Id, RequestMap, Scope, Success } from '../types';

export interface HeartbeatClock {
  now(): number;
  /** One-shot timer; returns its cancel. */
  set(delayMs: number, fire: () => void): () => void;
}

export class SystemHeartbeatClock implements HeartbeatClock {
  now(): number { return Date.now(); }
  set(delayMs: number, fire: () => void): () => void {
    const timer = setTimeout(fire, delayMs);
    return () => clearTimeout(timer);
  }
}

export interface LeaseHeartbeatState {
  worldId: Id;
  leaseToken: Id;
  fenceEpoch: number;
  expiresAtEpochMilli: number;
}

export interface ClaimHeartbeatState {
  worldId: Id;
  pointId: Id;
  claimToken: Id;
  generation: number;
  issuedAtEpochMilli: number;
  leaseToken: Id;
  fenceEpoch: number;
  expiresAtEpochMilli: number;
}

export interface HeartbeatIo {
  renewLease(request: RequestMap['lease_renew'], scope: Scope): Promise<Success<'lease_renew'>>;
  renewClaim(request: RequestMap['narration_claim_renew'], scope: Scope): Promise<Success<'narration_claim_renew'>>;
}

export type HeartbeatLoss = { kind: 'lease' | 'claim'; code: ErrorCode; response: ErrorResponse };

export interface HeartbeatHooks {
  onLeaseRenewed(expiresAtEpochMilli: number): void;
  onClaimRenewed(expiresAtEpochMilli: number): void;
  onLost(loss: HeartbeatLoss): void;
}

export interface HeartbeatOptions {
  /** Renew this long before the receipted expiry. */
  leadMs: number;
  /** Backoff for timeout/retryable rejections, same requestId. */
  retryBackoffMs: number;
  clock: HeartbeatClock;
  nextRequestId: () => Id;
}

interface LoopDeps<S extends { expiresAtEpochMilli: number }> {
  kind: 'lease' | 'claim';
  build: (state: S, requestId: Id) => RequestMap['lease_renew'] | RequestMap['narration_claim_renew'];
  scope: (state: S) => Scope;
  execute: (request: RequestMap['lease_renew'] | RequestMap['narration_claim_renew'], scope: Scope) => Promise<Success<'lease_renew'> | Success<'narration_claim_renew'>>;
  adopt: (state: S, response: Success<'lease_renew'> | Success<'narration_claim_renew'>) => { state: S; expiresAtEpochMilli: number };
  onRenewed: (expiresAtEpochMilli: number) => void;
}

class HeartbeatLoop<S extends { expiresAtEpochMilli: number }> {
  private state: S | null = null;
  private cancelTimer: (() => void) | null = null;
  private cycle = 0;

  constructor(private readonly options: HeartbeatOptions, private readonly deps: LoopDeps<S>, private readonly onLost: (loss: HeartbeatLoss) => void) {}

  get running(): boolean { return this.state !== null; }

  start(state: S): void {
    this.cycle += 1;
    this.state = state;
    this.schedule();
  }

  /** A newer observation replaces the schedule; renewals still in flight for
   * the superseded state settle into the void (cycle guard). */
  update(state: S): void {
    if (!this.state) return;
    this.cycle += 1;
    this.state = state;
    this.schedule();
  }

  stop(): void {
    this.cycle += 1;
    this.state = null;
    this.cancelTimer?.();
    this.cancelTimer = null;
  }

  private schedule(): void {
    this.cancelTimer?.();
    const state = this.state;
    if (!state) return;
    const delay = Math.max(0, state.expiresAtEpochMilli - this.options.leadMs - this.options.clock.now());
    const startedCycle = this.cycle;
    this.cancelTimer = this.options.clock.set(delay, () => this.fire(state, startedCycle));
  }

  private fire(state: S, startedCycle: number): void {
    if (startedCycle !== this.cycle) return; // superseded while the timer waited
    this.attempt(state, this.options.nextRequestId(), startedCycle);
  }

  private attempt(state: S, requestId: Id, startedCycle: number): void {
    const cycleAtSend = this.cycle;
    void this.deps.execute(this.deps.build(state, requestId), this.deps.scope(state)).then(
      (response) => {
        if (startedCycle !== cycleAtSend || startedCycle !== this.cycle) return; // superseded by update/stop
        const adopted = this.deps.adopt(state, response);
        this.state = adopted.state;
        this.deps.onRenewed(adopted.expiresAtEpochMilli);
        this.schedule();
      },
      (error: unknown) => {
        if (startedCycle !== cycleAtSend || startedCycle !== this.cycle) return; // superseded; the new cycle owns the schedule
        if (retryableError(error)) {
          this.cancelTimer = this.options.clock.set(this.options.retryBackoffMs, () => {
            if (startedCycle === this.cycle) this.attempt(state, requestId, startedCycle);
          });
          return;
        }
        if (error instanceof WorldApiError) {
          this.stop();
          this.onLost({ kind: this.deps.kind, code: error.response.error.code, response: error.response });
          return;
        }
        // Unexpected non-API errors are treated as transient: back off and
        // keep the heartbeat alive; surfacing them as a loss would silently
        // drop keep-alive on a transient transport hiccup.
        this.cancelTimer = this.options.clock.set(this.options.retryBackoffMs, () => {
          if (startedCycle === this.cycle) this.attempt(state, requestId, startedCycle);
        });
      },
    );
  }
}

function retryableError(error: unknown): boolean {
  if (error instanceof WorldTimeoutError) return true;
  if (error instanceof WorldApiError) return errorCatalog[error.response.error.code]?.retryable === true;
  return false;
}

export class HeartbeatScheduler {
  private readonly lease: HeartbeatLoop<LeaseHeartbeatState>;
  private readonly claim: HeartbeatLoop<ClaimHeartbeatState>;

  constructor(private readonly io: HeartbeatIo, private readonly options: HeartbeatOptions, hooks: HeartbeatHooks) {
    const onLost = hooks.onLost.bind(hooks);
    this.lease = new HeartbeatLoop<LeaseHeartbeatState>(options, {
      kind: 'lease',
      build: (state, requestId) => ({ protocolVersion: 2, requestId, worldId: state.worldId, leaseToken: state.leaseToken, fenceEpoch: state.fenceEpoch }),
      scope: (state) => ({ worldId: state.worldId }),
      execute: (request, scope) => io.renewLease(request as RequestMap['lease_renew'], scope),
      adopt: (state, response) => {
        const data = (response as Success<'lease_renew'>).data;
        return { state: { ...state, leaseToken: data.leaseToken, fenceEpoch: data.fenceEpoch, expiresAtEpochMilli: data.expiresAtEpochMilli }, expiresAtEpochMilli: data.expiresAtEpochMilli };
      },
      onRenewed: hooks.onLeaseRenewed.bind(hooks),
    }, onLost);
    this.claim = new HeartbeatLoop<ClaimHeartbeatState>(options, {
      kind: 'claim',
      build: (state, requestId) => ({
        protocolVersion: 2, requestId, worldId: state.worldId, pointId: state.pointId, mode: 'head' as const,
        claimToken: state.claimToken, generation: state.generation, issuedAtEpochMilli: state.issuedAtEpochMilli,
        leaseToken: state.leaseToken, fenceEpoch: state.fenceEpoch,
      }),
      scope: (state) => ({ worldId: state.worldId, pointId: state.pointId }),
      execute: (request, scope) => io.renewClaim(request as RequestMap['narration_claim_renew'], scope),
      adopt: (state, response) => {
        const data = (response as Success<'narration_claim_renew'>).data;
        return { state: { ...state, generation: data.generation, issuedAtEpochMilli: data.issuedAtEpochMilli, expiresAtEpochMilli: data.expiresAtEpochMilli }, expiresAtEpochMilli: data.expiresAtEpochMilli };
      },
      onRenewed: hooks.onClaimRenewed.bind(hooks),
    }, onLost);
  }

  startLease(state: LeaseHeartbeatState): void { this.lease.start(state); }
  /** Newer lease observation (any response envelope's world.lease). */
  updateLease(state: LeaseHeartbeatState): void { this.lease.update(state); }
  stopLease(): void { this.lease.stop(); }

  startClaim(state: ClaimHeartbeatState): void { this.claim.start(state); }
  stopClaim(): void { this.claim.stop(); }

  stop(): void {
    this.lease.stop();
    this.claim.stop();
  }
}
