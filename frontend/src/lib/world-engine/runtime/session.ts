/** WorldSession: the composition root that wires the controller driver, the
 * runtime model port and the dual heartbeat into ONE session. The session
 * owns the single driver loop (repeat run() calls share the in-flight
 * promise; heartbeats survive across runs — the lease must stay alive while
 * awaiting player input). Every exchange the driver makes — success or
 * error envelope — passes an observation layer that feeds heartbeat
 * credentials and server-receipted expiries automatically: lease grants
 * start the lease heartbeat, envelope lease views update it (only at the
 * epoch the held token belongs to — a foreign epoch means the token is
 * dead, never an upgrade of the old binding), fresh head claims
 * start/update the claim heartbeat (a different point restarts it),
 * submit/delete and the fenced/expired/stale error families stop them.
 *
 * Isolation is uniform: stop() and a lease loss are both TERMINAL — the
 * heartbeats stop, in-flight exchanges are cancelled and isolated, late
 * settles are discarded, and later run() calls are explicitly refused.
 * Authority recovery and the reconciliation of exchanges whose fate the
 * isolation left unresolved (a submit the server may have accepted) are a
 * later recovery batch / H2 — this session never resumes on a dead lease.
 * Both raise the session epoch — in-flight settles of EITHER
 * polarity are replaced by the isolation error, so the driver can neither
 * adopt a stale success nor react to a late error envelope (no followup
 * writes from a dead session), and new calls are refused at the wrapper
 * entry — also once the lease is lost. The call signal races every raw exchange, so a stop or a loss ends
 * transport waits promptly; the raw late settle stays discarded. A lost
 * lease also aborts in-flight inference — a model output can never be
 * committed against a fence the client no longer holds (the queue discards
 * the engine's late settle). */
import { ControllerDriver, initialMemory, type ControllerIo, type DriverStatus, type WorldModelPort } from '../controller';
import type { WorldTransport } from '../transport';
import { WorldApiError } from '../transport';
import type { ControllerMemory, HarnessCommand } from '../schedule';
import type { ClaimHeartbeatState, HeartbeatClock, HeartbeatLoss } from './heartbeat';
import { HeartbeatScheduler, SystemHeartbeatClock } from './heartbeat';
import type { RuntimeWorldModelPort } from './model-port';
import type { Id, RequestMap, Scope, Success, WorldOperation } from '../types';

/** The driver surface the session depends on; the real ControllerDriver
 * satisfies it and tests may substitute a scripted double. */
export interface DriverLike {
  step(): Promise<DriverStatus | undefined>;
  deliver(command: HarnessCommand): void;
  getMemory(): ControllerMemory;
}

export type DriverFactory = (io: ControllerIo) => DriverLike;

export interface WorldSessionHooks {
  onStatus?(status: DriverStatus): void;
  onLeaseLost?(code: string): void;
  onClaimLost?(loss: HeartbeatLoss): void;
}

export interface WorldSessionOptions {
  clock?: HeartbeatClock;
  heartbeatLeadMs?: number;
  retryBackoffMs?: number;
  createDriver?: DriverFactory;
  /** Identity namespace for every id this session mints (driver requestIds,
   * heartbeat ids). Defaults to a session-unique value: two default
   * sessions must never collide on a shared server's idempotency keys. */
  requestIdNamespace?: string;
  hooks?: WorldSessionHooks;
}

type AnyEnvelope = {
  world?: { worldId: Id; lease: { fenceEpoch: number; expiresAtEpochMilli: number } | null } | null;
  replayed?: boolean;
  data?: Record<string, unknown>;
  error?: { code: string };
};

const CLAIM_DEAD_CODES = new Set(['claim_fenced', 'claim_expired', 'cache_missing']);
const LEASE_DEAD_CODES = new Set(['stale_epoch', 'lease_invalid']);

/** Module-wide session counter: the default namespace is unique per session
 * instance even before any randomness (timestamp suffix breaks restarts). */
let sessionCounter = 0;

export type SessionStatus = 'idle' | 'running' | 'stopped' | 'lost_lease';

export class WorldSession {
  private readonly rawTransport: WorldTransport;
  private readonly port: RuntimeWorldModelPort;
  private readonly scheduler: HeartbeatScheduler;
  private readonly hooks: WorldSessionHooks;
  private readonly driver: DriverLike;
  private readonly namespace: string;
  private calls = new AbortController();
  private inference = new AbortController();
  private epoch = 0;
  /** Set by stop()/lease-loss while a loop is in flight; the loop converts
   * it into the terminal status when its isolation check trips. */
  private pendingTerminal: DriverStatus | null = null;
  private closed = false;
  private lostLeaseCode: string | null = null;
  private loopPromise: Promise<DriverStatus> | null = null;
  private status: SessionStatus = 'idle';
  private lease: { token: Id; fenceEpoch: number } | null = null;
  private claimPointId: Id | null = null;


  constructor(transport: WorldTransport, port: RuntimeWorldModelPort, options: WorldSessionOptions = {}) {
    this.rawTransport = transport;
    this.port = port;
    this.hooks = options.hooks ?? {};
    sessionCounter += 1;
    // Entropy makes the default namespace unique across module instances
    // (two tabs start their own counter at zero in the same millisecond).
    const entropy = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID().slice(0, 8)
      : Math.random().toString(36).slice(2, 8);
    this.namespace = options.requestIdNamespace ?? `s${sessionCounter}_${Date.now().toString(36)}_${entropy}`;
    const clock = options.clock ?? new SystemHeartbeatClock();
    let heartbeatId = 0;
    this.scheduler = new HeartbeatScheduler({
      renewLease: (request, scope) => this.rawTransport.execute('lease_renew', request, scope) as Promise<Success<'lease_renew'>>,
      renewClaim: (request, scope) => this.rawTransport.execute('narration_claim_renew', request, scope) as Promise<Success<'narration_claim_renew'>>,
    }, {
      leadMs: options.heartbeatLeadMs ?? 30_000,
      retryBackoffMs: options.retryBackoffMs ?? 5_000,
      clock,
      nextRequestId: () => `hb_${this.namespace}_${++heartbeatId}`,
    }, {
      onLeaseRenewed: () => {},
      onClaimRenewed: () => {},
      onLost: (loss) => this.onHeartbeatLoss(loss),
    });
    const observed: WorldTransport = {
      execute: async <K extends WorldOperation>(operation: K, request: RequestMap[K], scope: Scope) => {
        if (this.closed || this.lostLeaseCode) throw new Error(this.isolationReason());
        const epochAtCall = this.epoch;
        // The raw exchange races the session call signal: a stop or a lease
        // loss ends the wait promptly; the raw late settle stays discarded.
        const guarded = (async () => {
          try {
            const response = await this.raceIsolation(
              this.rawTransport.execute(operation, request, scope, this.calls.signal) as Promise<unknown>);
            if (epochAtCall !== this.epoch) throw new Error(this.isolationReason());
            this.observe(operation, request, scope, response as AnyEnvelope, false);
            // observe() itself may raise the epoch (a foreign lease epoch is
            // a session-level loss): this receipt must NOT reach the driver.
            if (epochAtCall !== this.epoch) throw new Error(this.isolationReason());
            return response;
          } catch (error) {
            // Neither a stale success nor a late error envelope may steer
            // the driver: an isolated settle becomes the isolation error, so
            // no errorReaction followup (e.g. lease_acquire) can fire.
            if (epochAtCall !== this.epoch) throw new Error(this.isolationReason());
            if (error instanceof WorldApiError) this.observe(operation, request, scope, error.response as unknown as AnyEnvelope, true);
            throw error;
          }
        })();
        void guarded.catch(() => {}); // if the race is lost, the late settle stays handled
        return guarded as never;
      },
    };
    const boundModel: WorldModelPort = {
      generate: (task, key, input) => port.generate(task, key, input, this.inference.signal),
    };
    const createDriver = options.createDriver ?? ((io: ControllerIo) => new ControllerDriver(io, initialMemory(`req_${this.namespace}`, 'browser'), { world: null }, {}));
    this.driver = createDriver({ transport: observed, model: boundModel });
  }

  get sessionStatus(): SessionStatus { return this.status; }

  /** Diagnostic: the identity namespace this session mints ids under. */
  get idNamespace(): string { return this.namespace; }

  /** Single-flight driver loop. Repeat calls while running share the same
   * promise; after an await boundary the session can run again. Rejected
   * once stopped, disposed, or after a lost lease (terminal). */
  run(): Promise<DriverStatus> {
    if (this.closed) return Promise.reject(new Error('WorldSession is stopped'));
    if (this.lostLeaseCode) return Promise.reject(new Error('WorldSession lost its lease; recovery is a later batch (H2)'));
    if (this.loopPromise) return this.loopPromise;
    if (this.calls.signal.aborted) this.calls = new AbortController();
    if (this.inference.signal.aborted) this.inference = new AbortController();
    this.pendingTerminal = null;
    this.status = 'running';
    this.loopPromise = this.loop(this.epoch);
    return this.loopPromise;
  }

  private async loop(epochAtStart: number): Promise<DriverStatus> {
    try {
      for (let step = 0; step < 500; step++) {
        if (epochAtStart !== this.epoch) return this.pendingTerminal ?? { kind: 'error', detail: 'session superseded' };
        const terminal = await this.driver.step();
        if (terminal) {
          this.hooks.onStatus?.(terminal);
          return terminal;
        }
      }
      return { kind: 'error', detail: 'session step limit exceeded' };
    } catch (error) {
      if (epochAtStart !== this.epoch) return this.pendingTerminal ?? { kind: 'error', detail: 'session superseded' };
      const detail = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
      const status: DriverStatus = { kind: 'error', detail };
      this.hooks.onStatus?.(status);
      return status;
    } finally {
      this.loopPromise = null;
      if (this.status === 'running') this.status = 'idle';
    }
  }

  deliver(command: HarnessCommand): void {
    this.driver.deliver(command);
  }

  getMemory(): ControllerMemory {
    return this.driver.getMemory();
  }

  /** Terminal: stops heartbeats, isolates every in-flight exchange (either
   * polarity), aborts inference and settles the loop. The raised epoch
   * refuses late responses and new calls; observers go silent. */
  stop(): void {
    if (this.closed) return;
    this.closed = true;
    this.epoch += 1;
    this.pendingTerminal ??= { kind: 'stop', reason: 'session_stopped' };
    this.status = 'stopped';
    this.isolateInFlight();
  }

  /** stop() plus engine disposal. */
  async dispose(): Promise<void> {
    this.stop();
    await this.port.dispose();
  }

  private isolationReason(): string {
    if (this.closed) return 'WorldSession closed';
    if (this.lostLeaseCode) return `lease lost: ${this.lostLeaseCode}`;
    return 'session superseded';
  }

  private isolateInFlight(): void {
    this.scheduler.stop();
    this.calls.abort();
    this.inference.abort();
    this.lease = null;
    this.claimPointId = null;
  }

  /** Races the raw exchange against the call signal so a stop or a loss
   * settles the caller promptly; the raw settle afterwards is discarded by
   * the caller's guard (its own catch is attached up front). */
  private raceIsolation<T>(promise: Promise<T>): Promise<T> {
    let onAbort: (() => void) | null = null;
    const aborted = new Promise<never>((_, reject) => {
      onAbort = () => reject(new Error(this.isolationReason()));
      if (this.calls.signal.aborted) onAbort();
      else this.calls.signal.addEventListener('abort', onAbort, { once: true });
    });
    const detach = () => {
      if (onAbort) this.calls.signal.removeEventListener('abort', onAbort);
    };
    void promise.then(detach, detach);
    return Promise.race([promise.then((value) => { detach(); return value; }, (error) => { detach(); throw error; }), aborted]) as Promise<T>;
  }

  private onHeartbeatLoss(loss: HeartbeatLoss): void {
    if (loss.kind === 'claim') {
      this.claimPointId = null;
      this.hooks.onClaimLost?.(loss);
      return; // the controller re-claims on its own path; the session continues
    }
    // A lost lease is fatal for in-flight work: the generation result could
    // only be committed against a fence the client no longer holds. The
    // lost-lease state is TERMINAL: both heartbeats stop, in-flight
    // exchanges are isolated (either polarity), inference aborts, and later
    // run() calls are refused. Authority recovery and reconciling exchanges
    // of unknown fate belong to a later recovery batch / H2.
    this.enterLeaseLost(loss.code);
  }

  /** The unified lost-lease entry: marks the state, isolates the in-flight
   * chain (both settle polarities) and settles the running loop. */
  private enterLeaseLost(code: string): void {
    if (this.lostLeaseCode) return;
    this.lostLeaseCode = code;
    if (this.status !== 'stopped') this.status = 'lost_lease'; // terminal
    this.epoch += 1;
    this.pendingTerminal ??= { kind: 'error', detail: `lease lost: ${code}` };
    this.isolateInFlight();
    this.hooks.onLeaseLost?.(code);
  }

  /** The observation layer: heartbeat state follows envelope content alone. */
  private observe(operation: WorldOperation, request: unknown, scope: Scope, envelope: AnyEnvelope, isError: boolean): void {
    if (operation === 'lease_renew' || operation === 'narration_claim_renew') return; // the heartbeat consumes its own receipts
    if (isError && envelope.error) {
      const code = envelope.error.code;
      if (LEASE_DEAD_CODES.has(code)) {
        this.scheduler.stopLease();
        this.scheduler.stopClaim();
        this.lease = null;
        this.claimPointId = null;
      } else if (CLAIM_DEAD_CODES.has(code)) {
        this.scheduler.stopClaim();
        this.claimPointId = null;
      }
    }
    const data = envelope.data;
    if (!isError && (operation === 'create_world' || operation === 'lease_acquire') && data) {
      const grant = data.lease ?? data; // create_world nests the grant; lease_acquire's data IS the grant
      const lease = grant as { leaseToken: Id; fenceEpoch: number; expiresAtEpochMilli: number } | undefined;
      const worldId = (scope.worldId ?? (request as { worldId?: Id }).worldId ?? data.worldId) as Id | undefined;
      if (lease?.leaseToken && worldId) {
        this.lease = { token: lease.leaseToken, fenceEpoch: lease.fenceEpoch };
        this.scheduler.startLease({ worldId, leaseToken: lease.leaseToken, fenceEpoch: lease.fenceEpoch, expiresAtEpochMilli: lease.expiresAtEpochMilli });
      }
    }
    if (!isError && operation === 'narration_claim' && data && envelope.replayed === false) {
      const worldId = scope.worldId as Id;
      const pointId = data.pointId as Id | undefined;
      const claimToken = data.claimToken as Id | undefined;
      const expiresAtEpochMilli = data.expiresAtEpochMilli as number | undefined;
      if (worldId && pointId && claimToken && expiresAtEpochMilli !== undefined && data.mode === 'head' && this.lease) {
        const state: ClaimHeartbeatState = {
          worldId, pointId, claimToken,
          generation: data.generation as number,
          issuedAtEpochMilli: data.issuedAtEpochMilli as number,
          leaseToken: this.lease.token, fenceEpoch: this.lease.fenceEpoch,
          expiresAtEpochMilli,
        };
        if (this.claimPointId !== null && this.claimPointId !== pointId) this.scheduler.stopClaim(); // a different point's claim restarts the heartbeat
        if (this.claimPointId === pointId) this.scheduler.updateClaim(state);
        else this.scheduler.startClaim(state);
        this.claimPointId = pointId;
      }
    }
    if (!isError && (operation === 'narration_submit' || operation === 'narration_delete')) {
      this.scheduler.stopClaim();
      this.claimPointId = null;
    }
    const world = envelope.world;
    if (!isError && world && this.lease) {
      if (world.lease) {
        // Bind only at the epoch the held token belongs to. A HIGHER epoch
        // means the server moved on and our token is dead — that is a lost
        // lease, never an upgrade of the old binding; a lower epoch is a
        // stale envelope and is ignored (the update guard would drop it
        // anyway).
        if (world.lease.fenceEpoch === this.lease.fenceEpoch) {
          this.scheduler.updateLease({ worldId: world.worldId, leaseToken: this.lease.token, fenceEpoch: world.lease.fenceEpoch, expiresAtEpochMilli: world.lease.expiresAtEpochMilli });
        } else if (world.lease.fenceEpoch > this.lease.fenceEpoch) {
          // A foreign epoch fences every held credential: the unified
          // lost-lease path — full isolation, and the epoch re-check in the
          // wrapper keeps this very receipt from reaching the driver.
          this.enterLeaseLost('stale_epoch');
        }
      } else {
        // The lease is gone from the served world: every held claim is fenced.
        this.scheduler.stopLease();
        this.scheduler.stopClaim();
        this.lease = null;
        this.claimPointId = null;
      }
    }
  }
}
