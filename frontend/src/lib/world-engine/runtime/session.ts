/** WorldSession: the composition root that wires the controller driver, the
 * runtime model port and the dual heartbeat into ONE session. The session
 * owns the single driver loop (repeat run() calls share the in-flight
 * promise; heartbeats survive across runs — the lease must stay alive while
 * awaiting player input). Every exchange the driver makes — success or
 * error envelope — passes an observation layer that feeds heartbeat
 * credentials and server-receipted expiries automatically: lease grants
 * start the lease heartbeat, envelope lease views update it, fresh head
 * claims start/update the claim heartbeat (a different point restarts it),
 * submit/delete and the fenced/expired/stale error families stop them.
 * A heartbeat lease loss is session-fatal for in-flight work: the inference
 * signal aborts immediately, so a model output can never be consumed from a
 * dead lease (the queue discards the engine's late settle). stop()/dispose()
 * raise the session epoch: late transport responses are refused, observers
 * go silent, and nothing from the old session writes back. */
import { ControllerDriver, initialMemory, type ControllerIo, type DriverStatus, type WorldModelPort } from '../controller';
import type { WorldTransport } from '../transport';
import { WorldApiError } from '../transport';
import type { ControllerMemory, HarnessCommand } from '../schedule';
import type { ClaimHeartbeatState, HeartbeatClock, HeartbeatLoss, LeaseHeartbeatState } from './heartbeat';
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
  onLeaseLost?(loss: HeartbeatLoss): void;
  onClaimLost?(loss: HeartbeatLoss): void;
}

export interface WorldSessionOptions {
  clock?: HeartbeatClock;
  heartbeatLeadMs?: number;
  retryBackoffMs?: number;
  createDriver?: DriverFactory;
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

export type SessionStatus = 'idle' | 'running' | 'stopped';

export class WorldSession {
  private readonly rawTransport: WorldTransport;
  private readonly port: RuntimeWorldModelPort;
  private readonly scheduler: HeartbeatScheduler;
  private readonly hooks: WorldSessionHooks;
  private readonly driver: DriverLike;
  private inference = new AbortController();
  private epoch = 0;
  private loopPromise: Promise<DriverStatus> | null = null;
  private stopping = false;
  private status: SessionStatus = 'idle';
  private lease: { token: Id; fenceEpoch: number } | null = null;
  private claimPointId: Id | null = null;

  constructor(transport: WorldTransport, port: RuntimeWorldModelPort, options: WorldSessionOptions = {}) {
    this.rawTransport = transport;
    this.port = port;
    this.hooks = options.hooks ?? {};
    const clock = options.clock ?? new SystemHeartbeatClock();
    let requestId = 0;
    this.scheduler = new HeartbeatScheduler({
      renewLease: (request, scope) => this.rawTransport.execute('lease_renew', request, scope) as Promise<Success<'lease_renew'>>,
      renewClaim: (request, scope) => this.rawTransport.execute('narration_claim_renew', request, scope) as Promise<Success<'narration_claim_renew'>>,
    }, {
      leadMs: options.heartbeatLeadMs ?? 30_000,
      retryBackoffMs: options.retryBackoffMs ?? 5_000,
      clock,
      nextRequestId: () => `hb_session_${++requestId}`,
    }, {
      onLeaseRenewed: () => {},
      onClaimRenewed: () => {},
      onLost: (loss) => this.onHeartbeatLoss(loss),
    });
    const observed: WorldTransport = {
      execute: async <K extends WorldOperation>(operation: K, request: RequestMap[K], scope: Scope) => {
        const epochAtCall = this.epoch;
        try {
          const response = await this.rawTransport.execute(operation, request, scope);
          if (epochAtCall !== this.epoch) throw new Error('WorldSession closed: late response refused');
          this.observe(operation, request, scope, response as unknown as AnyEnvelope, false);
          return response;
        } catch (error) {
          if (epochAtCall === this.epoch && error instanceof WorldApiError) {
            this.observe(operation, request, scope, error.response as unknown as AnyEnvelope, true);
          }
          throw error;
        }
      },
    };
    const boundModel: WorldModelPort = {
      generate: (task, key, input) => port.generate(task, key, input, this.inference.signal),
    };
    const createDriver = options.createDriver ?? ((io: ControllerIo) => new ControllerDriver(io, initialMemory('req_session', 'browser'), { world: null }, {}));
    this.driver = createDriver({ transport: observed, model: boundModel });
  }

  get sessionStatus(): SessionStatus { return this.status; }

  /** Single-flight driver loop. Repeat calls while running share the same
   * promise; after a terminal status the session can run again (await
   * boundary). Rejected once stopped or disposed. */
  run(): Promise<DriverStatus> {
    if (this.status === 'stopped') return Promise.reject(new Error('WorldSession is stopped'));
    if (this.loopPromise) return this.loopPromise;
    if (this.inference.signal.aborted) this.inference = new AbortController();
    this.status = 'running';
    const epochAtStart = this.epoch;
    this.loopPromise = this.loop(epochAtStart);
    return this.loopPromise;
  }

  private async loop(epochAtStart: number): Promise<DriverStatus> {
    try {
      for (let step = 0; step < 500; step++) {
        if (epochAtStart !== this.epoch) return this.stopping ? { kind: 'stop', reason: 'session_stopped' } : { kind: 'error', detail: 'session superseded' };
        const terminal = await this.driver.step();
        if (terminal) {
          this.hooks.onStatus?.(terminal);
          return terminal;
        }
      }
      return { kind: 'error', detail: 'session step limit exceeded' };
    } catch (error) {
      if (this.stopping && epochAtStart !== this.epoch) return { kind: 'stop', reason: 'session_stopped' };
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

  /** Stops heartbeats, aborts in-flight inference and settles the loop. The
   * raised epoch refuses late transport responses and silences observers —
   * nothing from the old session writes back. Terminal. */
  stop(): void {
    if (this.status === 'stopped') return;
    this.epoch += 1;
    this.stopping = true;
    this.status = 'stopped';
    this.scheduler.stop();
    this.inference.abort();
    this.lease = null;
    this.claimPointId = null;
  }

  /** stop() plus engine disposal. */
  async dispose(): Promise<void> {
    this.stop();
    await this.port.dispose();
  }

  private onHeartbeatLoss(loss: HeartbeatLoss): void {
    if (loss.kind === 'claim') {
      this.claimPointId = null;
      this.hooks.onClaimLost?.(loss);
      return; // the controller re-claims on its own path; the session continues
    }
    // A lost lease is fatal for in-flight work: the generation result could
    // only be committed against a fence the client no longer holds.
    this.hooks.onLeaseLost?.(loss);
    this.inference.abort();
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
        this.scheduler.updateLease({ worldId: world.worldId, leaseToken: this.lease.token, fenceEpoch: world.lease.fenceEpoch, expiresAtEpochMilli: world.lease.expiresAtEpochMilli });
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
