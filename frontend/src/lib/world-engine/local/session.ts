/** One local game session: a ControllerDriver over the browser-local transport.
 * The driver owns scheduling, group freezing, dice admission and the six-stage
 * loop; the transport owns state. The session adds durable progress: every
 * transport write is checkpointed (IndexedDB by default) before the driver may
 * consume its response, a multi-tab writer lease fences stale tabs, and a
 * restored record rebuilds the controller's scheduler memory from the record
 * instead of replaying frozen actions or dice. */
import { ControllerDriver, initialMemory, type DriverStatus, type WorldModelPort } from '../controller';
import type { ControllerMemory, ModelTask } from '../schedule';
import type { Id, InitialTemplate, Json, RequestMap, Scope, Success, WorldOperation, WorldState } from '../types';
import type { WorldTransport } from '../transport';
import { LocalWorldTransport } from './transport';
import { DEFAULT_LEASE_TTL_MS } from './persistence/store';
import { rebuildSessionMemory, type LocalSchedulerCheckpoint, type ResumeServedState } from './persistence/resume';
import {
  ProgressConflictError, SessionLeaseHeldError, SessionLeaseLostError,
  type LocalProgressStore, type ProgressMetadata, type SavedLocalProgress,
} from './persistence/types';

/** How a point's narration was produced. The transport stores the text and its
 * status only; this page-owned side map keeps the honest label (accepted model,
 * mixed, program realization, or an unadopted draft) so a reload can still say
 * which one the player is reading. */
export interface NarrationSourceNote { source: 'model' | 'mixed' | 'program' | 'draft'; note?: string }

export interface LocalGameSnapshot {
  transport: ReturnType<LocalWorldTransport['snapshot']>;
  commands: string[];
  /** Resume hint: the model plan for the open round. Validated against the
   * transport record on restore; never a second source of game facts. */
  checkpoint?: LocalSchedulerCheckpoint;
  /** pointId → narration provenance. Never changes the committed text. */
  narrationSources?: Record<string, NarrationSourceNote>;
}

export type LocalPersistenceState = 'off' | 'saving' | 'saved' | 'error' | 'conflict' | 'lease_lost';

export type LocalSessionEvent =
  | { type: 'checkpoint'; metadata: ProgressMetadata }
  | { type: 'save_failed'; error: unknown }
  | { type: 'conflict'; error: ProgressConflictError; metadata: ProgressMetadata | null }
  | { type: 'lease_lost'; error: SessionLeaseLostError };

export interface LocalGameOptions {
  worldId?: Id;
  /** Legacy callback: sees every snapshot the session would persist. */
  onPersist?: (snapshot: LocalGameSnapshot) => void;
  roll?: () => number;
  /** Durable progress store. Without it the session keeps the historical
   * in-memory behaviour and the caller owns persistence via onPersist. */
  storage?: LocalProgressStore;
  /** Writer identity for the multi-tab lease (default: random per session). */
  sessionId?: string;
  leaseTtlMs?: number;
  /** Renew the writer lease in the background (default true with storage). */
  leaseHeartbeat?: boolean;
  /** Persist every transport write (default true with storage). */
  autoSave?: boolean;
  /** Require the held writer lease on every save (default true with storage). */
  requireLease?: boolean;
  onEvent?: (event: LocalSessionEvent) => void;
  /** Page-owned provenance for committed narration text (label only). */
  narrationSourceOf?: () => Record<string, NarrationSourceNote> | undefined;
}

interface ResolvedOptions extends LocalGameOptions {
  sessionId: string;
  worldId: Id;
}

export class ModelCancelledError extends Error {
  readonly name = 'ModelCancelledError';
  constructor() { super('model_output_discarded_by_cancel'); }
}

/** Drops a model answer that arrives after a cancel: the output was never
 * confirmed, so it must not reach the controller. */
class CancelGate implements WorldModelPort {
  private armed = false;
  constructor(private readonly inner: WorldModelPort, private readonly advanceActive: () => boolean) {}
  arm(): void { this.armed = true; }
  disarm(): void { this.armed = false; }
  isArmed(): boolean { return this.armed && this.advanceActive(); }
  async generate(task: ModelTask, key: string, input: Json): Promise<Json> {
    this.check();
    const output = await this.inner.generate(task, key, input);
    this.check();
    return output;
  }
  private check(): void { if (this.isArmed()) throw new ModelCancelledError(); }
}

/** Makes a transport write durable before its response reaches the driver, so
 * the controller never builds on a write a refresh could erase. */
class CheckpointingTransport implements WorldTransport {
  constructor(private readonly inner: WorldTransport, private readonly settle: () => Promise<void>) {}
  async execute<K extends WorldOperation>(operation: K, request: RequestMap[K], scope: Scope, signal?: AbortSignal): Promise<Success<K>> {
    const response = await this.inner.execute(operation, request, scope, signal);
    await this.settle();
    return response;
  }
}

function randomId(prefix: string): string {
  const cryptoApi = globalThis.crypto as Crypto | undefined;
  if (cryptoApi?.randomUUID) return `${prefix}_${cryptoApi.randomUUID().slice(0, 8)}`;
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

export class LocalGameSession {
  readonly transport: LocalWorldTransport;
  private readonly options: ResolvedOptions;
  private readonly gate: CancelGate;
  private readonly driver: ControllerDriver;
  private readonly commands: string[];
  private readonly storage: LocalProgressStore | null;
  private readonly sessionId: string;
  private readonly leaseTtlMs: number;
  private readonly requireLease: boolean;
  private readonly autoSave: boolean;

  private revision = 0;
  private metadata: ProgressMetadata | null = null;
  private persistState: LocalPersistenceState = 'off';
  private pendingSnapshot: LocalGameSnapshot | null = null;
  private draining: Promise<void> | null = null;
  private saveBlocked: 'conflict' | 'lease_lost' | null = null;
  private running: Promise<DriverStatus> | null = null;
  private cancelRequested = false;
  private cancelDelivered = false;
  private cancelReason = 'player_cancelled';
  private submitLock = false;
  private heartbeat: ReturnType<typeof setInterval> | null = null;
  private closed = false;
  /** Successful transport writes, used to notice a controller spin. */
  private writeCount = 0;

  private constructor(transport: LocalWorldTransport, model: WorldModelPort, initial: InitialTemplate | null,
    commands: string[], options: ResolvedOptions, state?: ResumeServedState, memory?: ControllerMemory) {
    this.transport = transport;
    this.options = options;
    this.commands = commands;
    this.storage = options.storage ?? null;
    this.sessionId = options.sessionId;
    this.leaseTtlMs = options.leaseTtlMs ?? DEFAULT_LEASE_TTL_MS;
    this.requireLease = options.requireLease ?? !!this.storage;
    this.autoSave = (options.autoSave ?? true) && !!this.storage;
    this.persistState = this.autoSave ? 'saving' : 'off';
    this.gate = new CancelGate(model, () => this.transport.snapshot().advance != null);
    const prefix = `local_${Math.random().toString(36).slice(2, 10)}`;
    const seed = memory ?? initialMemory(prefix, this.sessionId);
    // New worlds carry the template; restored worlds are seeded from context.
    if (initial) seed.initialTemplate = structuredClone(initial);
    const durable = new CheckpointingTransport(transport, () => this.flushPersistence());
    this.driver = new ControllerDriver({ transport: durable, model: this.gate }, seed, state ?? { world: null });
    if (this.storage && options.leaseHeartbeat !== false) this.startHeartbeat();
  }

  // ---------- construction / restore ----------

  static async create(initial: InitialTemplate, model: WorldModelPort, options: LocalGameOptions = {}): Promise<LocalGameSession> {
    const worldId = options.worldId ?? `world_local_${Date.now().toString(36)}_${Math.floor(Math.random() * 1e6).toString(36)}`;
    const sessionId = options.sessionId ?? randomId('session');
    if (options.storage) {
      const claim = await options.storage.claimLease(worldId, sessionId, options.leaseTtlMs);
      if (!claim.acquired) throw new SessionLeaseHeldError(worldId, claim.holderId, claim.expiresAtEpochMilli);
    }
    const commands: string[] = [];
    let session: LocalGameSession | null = null;
    let transport: LocalWorldTransport;
    try {
      transport = await LocalWorldTransport.create(initial, {
        worldId, roll: options.roll,
        onPersist: (snapshot) => { session?.queueSnapshot(snapshot); },
      });
    } catch (error) {
      await options.storage?.releaseLease(worldId, sessionId).catch(() => undefined);
      throw error;
    }
    session = new LocalGameSession(transport, model, initial ?? null, commands, { ...options, worldId, sessionId });
    await session.persistInitial();
    return session;
  }

  static async restore(snapshot: LocalGameSnapshot, model: WorldModelPort, options: LocalGameOptions = {},
    progress?: { revision?: number; metadata?: ProgressMetadata | null }): Promise<LocalGameSession> {
    const record = snapshot?.transport;
    if (!record || typeof record.worldId !== 'string' || !record.state || !record.pointStates || !record.control) {
      throw new Error('local_restore_invalid_snapshot');
    }
    const worldId = record.worldId;
    const sessionId = options.sessionId ?? randomId('session');
    const claimed = !!options.storage;
    if (options.storage) {
      const claim = await options.storage.claimLease(worldId, sessionId, options.leaseTtlMs);
      if (!claim.acquired) throw new SessionLeaseHeldError(worldId, claim.holderId, claim.expiresAtEpochMilli);
    }
    let session: LocalGameSession | null = null;
    let memory: ControllerMemory | null = null;
    let context: ResumeServedState | null = null;
    // A raw snapshot handed back without its metadata still has to line up
    // with whatever revision the store already holds, or its first save would
    // look like a conflict.
    const stored = progress ?? (options.storage ? await options.storage.load(worldId)
      .then((saved) => (saved ? { revision: saved.metadata.revision, metadata: saved.metadata } : undefined)) : undefined);
    try {
      const transport = await LocalWorldTransport.restore(record, {
        roll: options.roll,
        onPersist: (next) => { session?.queueSnapshot(next); },
      });
      context = await readContext(transport, worldId);
      memory = initialMemory(`local_${Math.random().toString(36).slice(2, 10)}`, sessionId);
      const rebuilt = rebuildSessionMemory({ record: transport.snapshot(), context, memory, checkpoint: snapshot.checkpoint ?? null });
      let resumeWrote = false;
      if (rebuilt.groupSlots.length && rebuilt.resumeAllocationKey) {
        if (!memory.leaseToken || context.world.lease == null) {
          const grant = await transport.execute('lease_acquire',
            { protocolVersion: 2, requestId: `${memory.requestId}_lease`, worldId, holderId: sessionId }, { worldId });
          memory.leaseToken = grant.data.leaseToken;
          context = await readContext(transport, worldId);
          resumeWrote = true;
        }
        const allocated = await transport.execute('allocate_ids', {
          protocolVersion: 2, requestId: `${memory.requestId}_resume`, worldId,
          leaseToken: memory.leaseToken!, fenceEpoch: context.world.lease?.fenceEpoch ?? 0,
          allocationKey: rebuilt.resumeAllocationKey, slots: rebuilt.groupSlots,
        }, { worldId });
        for (const allocation of allocated.data.allocations) memory.ids[allocation.slotKey] = allocation.id;
        memory.allocatedKeys = [rebuilt.resumeAllocationKey];
        resumeWrote = true;
      }
      session = new LocalGameSession(transport, model, null, [...(snapshot.commands ?? [])],
        { ...options, worldId, sessionId }, context, memory);
      // The resume's own allocation is a write like any other: checkpoint it so
      // the rebuilt identity survives another refresh.
      session.revision = stored?.revision ?? 0;
      session.metadata = stored?.metadata ?? null;
      if (stored?.metadata?.revision) session.persistState = 'saved';
      if (resumeWrote) await session.persistResume();
      return session;
    } catch (error) {
      // Never leave the writer lease behind when the restore itself failed.
      if (claimed) await options.storage!.releaseLease(worldId, sessionId).catch(() => undefined);
      throw error;
    }
  }

  /** Load the newest durable record for the world, if any. */
  static async restoreFromStore(store: LocalProgressStore, worldId: Id, model: WorldModelPort,
    options: LocalGameOptions = {}): Promise<LocalGameSession | null> {
    const saved: SavedLocalProgress | null = await store.load(worldId);
    if (!saved) return null;
    return LocalGameSession.restore(saved.snapshot, model, { ...options, storage: store },
      { revision: saved.metadata.revision, metadata: saved.metadata });
  }

  /** Restore when a record exists, otherwise start a new world. */
  static async open(store: LocalProgressStore, world: { worldId: Id; initial: InitialTemplate }, model: WorldModelPort,
    options: LocalGameOptions = {}): Promise<{ session: LocalGameSession; created: boolean }> {
    const restored = await LocalGameSession.restoreFromStore(store, world.worldId, model, options);
    if (restored) return { session: restored, created: false };
    const session = await LocalGameSession.create(world.initial, model, { ...options, worldId: world.worldId, storage: store });
    return { session, created: true };
  }

  // ---------- public view ----------

  get worldId(): Id { return this.transport.worldId; }
  get commandsPlayed(): string[] { return [...this.commands]; }
  get memory(): ControllerMemory { return this.driver.getMemory(); }
  get sessionIdUsed(): string { return this.sessionId; }
  get progress(): ProgressMetadata | null { return this.metadata; }
  get persistence(): { state: LocalPersistenceState; revision: number; metadata: ProgressMetadata | null; blocked: 'conflict' | 'lease_lost' | null } {
    return { state: this.persistState, revision: this.revision, metadata: this.metadata, blocked: this.saveBlocked };
  }

  get snapshot(): LocalGameSnapshot {
    const snapshot: LocalGameSnapshot = { transport: this.transport.snapshot(), commands: [...this.commands] };
    const checkpoint = this.currentCheckpoint();
    if (checkpoint) snapshot.checkpoint = checkpoint;
    // Provenance travels with every snapshot (public and persisted), otherwise
    // __worldSnapshot/restore lose the program/draft labels the transport does
    // not store.
    const sources = this.options.narrationSourceOf?.();
    if (sources && Object.keys(sources).length) snapshot.narrationSources = { ...sources };
    return snapshot;
  }

  async start(): Promise<DriverStatus> { return this.drive(); }

  /** A player command starts a new advance. The caller must await the result;
   * the promise resolves at handback/await, never mid-point. A second submit
   * while a turn runs is refused instead of queueing a duplicate. */
  async submit(text: string): Promise<DriverStatus> {
    if (this.saveBlocked) return { kind: 'stop', reason: this.saveBlocked === 'conflict' ? 'progress_conflict' : 'progress_lease_lost' };
    // A paused controller accepts no new command; queueing one would start it
    // silently on resume. The player resumes first, then submits.
    if (this.transport.snapshot().control.paused) return { kind: 'stop', reason: 'paused' };
    if (this.running || this.submitLock) return { kind: 'stop', reason: 'turn_in_progress' };
    const record = this.transport.snapshot();
    if (record.advance) return { kind: 'stop', reason: 'turn_in_progress' };
    this.submitLock = true;
    try {
      const plan = record.initial.characters;
      const order = Object.keys(plan).sort();
      const memory = this.driver.getMemory();
      const allocationKey = `command_${record.round ? record.round.roundId : 'new'}_${memory.requestId}`;
      const clear = Object.keys(memory.ids);
      this.driver.preparePlayerInput(text, order, {
        allocationKey,
        slots: [
          { slotKey: 'advance', kind: 'advance' }, { slotKey: 'input', kind: 'input' },
          { slotKey: 'round', kind: 'round' }, { slotKey: 'point', kind: 'point' },
          ...order.map((actor) => ({ slotKey: `group:${actor}`, kind: 'group' as const })),
        ],
      }, clear);
      this.commands.push(text);
      await this.persistCommands();
      return await this.drive();
    } finally {
      this.submitLock = false;
    }
  }

  async pause(): Promise<DriverStatus> {
    this.driver.deliver({ kind: 'pause' });
    if (this.running) return this.running;
    return this.drive();
  }

  async resume(): Promise<DriverStatus> {
    this.driver.deliver({ kind: 'resume' });
    if (this.running) return this.running;
    return this.drive();
  }

  /** Real cancellation: the running control receives round_conclusion_cancel,
   * and any model answer that finishes after the request is discarded instead
   * of being adopted. Nothing to cancel when no advance is active. */
  async cancel(reason = 'player_cancelled'): Promise<DriverStatus> {
    if (this.transport.snapshot().advance == null) return { kind: 'stop', reason: 'nothing_to_cancel' };
    this.cancelRequested = true;
    this.cancelReason = reason;
    this.gate.arm();
    if (!this.running) {
      this.deliverCancel();
      if (!this.cancelDelivered) {
        this.cancelRequested = false;
        this.gate.disarm();
        return { kind: 'stop', reason: 'nothing_to_cancel' };
      }
    }
    if (this.running) return this.running;
    return this.drive();
  }

  async state(): Promise<WorldState> {
    const response = await this.transport.execute('get_state', {}, { worldId: this.transport.worldId });
    return response.data.state;
  }

  /** Waits for every queued save (used by the page on visibility change). */
  async flushPersistence(): Promise<void> {
    while (this.draining) {
      const current = this.draining;
      await current;
      if (this.draining === current) break;
    }
    if (this.pendingSnapshot && !this.saveBlocked) await this.drain();
  }

  /** Flush, stop the heartbeat and release the writer lease. The store stays
   * owned by the caller. */
  async close(): Promise<void> {
    this.stopHeartbeat();
    await this.flushPersistence();
    this.closed = true;
    if (this.storage) await this.storage.releaseLease(this.worldId, this.sessionId);
  }

  // ---------- checkpointing ----------

  private currentCheckpoint(): LocalSchedulerCheckpoint | null {
    const round = this.transport.snapshot().round;
    if (!round) return null;
    const memory = this.driver.getMemory();
    if (!memory.plan || memory.plan.length === 0) return null;
    return { roundId: round.roundId, plan: memory.plan, planIndex: memory.planIndex };
  }

  private snapshotForPersist(record: LocalGameSnapshot['transport']): LocalGameSnapshot {
    const snapshot: LocalGameSnapshot = { transport: record, commands: [...this.commands] };
    const checkpoint = this.currentCheckpoint();
    if (checkpoint) snapshot.checkpoint = checkpoint;
    const sources = this.options.narrationSourceOf?.();
    if (sources && Object.keys(sources).length) snapshot.narrationSources = { ...sources };
    return snapshot;
  }

  private queueSnapshot(record: LocalGameSnapshot['transport']): void {
    this.writeCount += 1;
    if (this.closed) return;
    const snapshot = this.snapshotForPersist(record);
    this.options.onPersist?.(snapshot);
    if (!this.autoSave) return;
    this.pendingSnapshot = snapshot;
    void this.drain();
  }

  private async persistInitial(): Promise<void> {
    if (!this.autoSave) return;
    this.pendingSnapshot = this.snapshotForPersist(this.transport.snapshot());
    await this.drain();
  }

  private async persistResume(): Promise<void> {
    if (!this.autoSave) return;
    this.pendingSnapshot = this.snapshotForPersist(this.transport.snapshot());
    await this.drain();
  }

  private async persistCommands(): Promise<void> {
    if (!this.autoSave) return;
    this.pendingSnapshot = this.snapshotForPersist(this.transport.snapshot());
    await this.drain();
  }

  private drain(): Promise<void> {
    if (this.draining) return this.draining;
    const storage = this.storage;
    if (!storage || this.closed) return Promise.resolve();
    this.persistState = this.saveBlocked ?? 'saving';
    const run = (async () => {
      while (this.pendingSnapshot && !this.saveBlocked && !this.closed) {
        const snapshot = this.pendingSnapshot;
        this.pendingSnapshot = null;
        try {
          const metadata = await storage.save(this.worldId, snapshot, {
            expectedRevision: this.revision, sessionId: this.sessionId,
            requireLease: this.requireLease, writerId: this.sessionId,
          });
          this.revision = metadata.revision;
          this.metadata = metadata;
          this.persistState = 'saved';
          this.emit({ type: 'checkpoint', metadata });
        } catch (error) {
          if (error instanceof ProgressConflictError) {
            this.saveBlocked = 'conflict';
            this.persistState = 'conflict';
            this.emit({ type: 'conflict', error, metadata: error.current });
          } else if (error instanceof SessionLeaseLostError) {
            this.saveBlocked = 'lease_lost';
            this.persistState = 'lease_lost';
            this.emit({ type: 'lease_lost', error });
          } else {
            this.persistState = 'error';
            this.emit({ type: 'save_failed', error });
            // Neither conflict nor lost lease: the record can still be
            // written later. Keep the newest snapshot pending and stop this
            // pass instead of spinning on a broken storage.
            if (!this.pendingSnapshot) this.pendingSnapshot = snapshot;
            break;
          }
        }
      }
    })();
    this.draining = run;
    // Clear by identity, never from inside the body: a body that finishes
    // without awaiting would otherwise clear the field before this assignment.
    void run.then(() => { if (this.draining === run) this.draining = null; },
      () => { if (this.draining === run) this.draining = null; });
    return run;
  }

  private emit(event: LocalSessionEvent): void {
    try { this.options.onEvent?.(event); } catch (error) { console.warn('[world-local] persistence event handler failed', error); }
  }

  // ---------- driver loop ----------

  private drive(limit = 500): Promise<DriverStatus> {
    if (this.running) return this.running;
    let release!: () => void;
    const gateStart = new Promise<void>((resolve) => { release = resolve; });
    const running = (async () => {
      await gateStart;
      try {
        return await this.loop(limit);
      } finally {
        await this.flushPersistence();
        this.abandonCancel();
      }
    })().finally(() => { this.running = null; });
    this.running = running;
    release();
    return running;
  }

  private async loop(limit: number): Promise<DriverStatus> {
    let lastWrite = this.writeCount;
    let idle = 0;
    for (let index = 0; index < limit; index++) {
      // A tab without the writer lease cannot persist anything it computes.
      // Stop it at the next step boundary instead of finishing a turn nobody
      // will ever read back.
      if (this.saveBlocked) {
        return { kind: 'stop', reason: this.saveBlocked === 'conflict' ? 'progress_conflict' : 'progress_lease_lost' };
      }
      this.deliverCancel();
      let status: DriverStatus | undefined;
      try {
        status = await this.driver.step();
      } catch (error) {
        // A cancel discards whatever the in-flight model produced; the queued
        // cancel command then runs on the transport and closes the round.
        if (this.cancelRequested) { await this.flushPersistence(); continue; }
        throw error;
      }
      if (this.cancelDelivered && this.transport.snapshot().advance == null) this.abandonCancel();
      if (status) {
        if (this.cancelDelivered || this.cancelRequested) this.abandonCancel();
        return status;
      }
      if (this.writeCount !== lastWrite) {
        lastWrite = this.writeCount;
        idle = 0;
      } else if (++idle >= 20) {
        // Every scheduled step was refused without touching the record: the
        // scheduler would keep retrying the same rejected request forever.
        const decision = this.driver.pendingDecision();
        const detail = decision.kind === 'transport' ? decision.operation : decision.kind;
        return { kind: 'stop', reason: `stalled:${detail}` };
      }
    }
    return { kind: 'error', detail: 'driver step limit exceeded' };
  }

  /** Queue the cancel only once the advance is still active at that exact
   * step; the driver's command channel cannot be withdrawn afterwards. */
  private deliverCancel(): void {
    if (!this.cancelRequested || this.cancelDelivered) return;
    if (this.transport.snapshot().advance == null) {
      this.cancelRequested = false;
      this.gate.disarm();
      return;
    }
    this.driver.deliver({ kind: 'cancel', reason: this.cancelReason });
    this.cancelDelivered = true;
  }

  /** A cancel that did not land must not leave a stale command for a later
   * advance: replace it with a harmless idempotent resume before clearing. */
  private abandonCancel(): void {
    const stale = this.cancelDelivered && this.transport.snapshot().advance != null;
    if (stale) this.driver.deliver({ kind: 'resume' });
    this.cancelDelivered = false;
    this.cancelRequested = false;
    this.gate.disarm();
  }

  // ---------- writer lease ----------

  private startHeartbeat(): void {
    const interval = Math.max(500, Math.floor(this.leaseTtlMs / 3));
    const timer = setInterval(() => {
      void this.storage!.renewLease(this.worldId, this.sessionId, this.leaseTtlMs).then((claim) => {
        if (!claim.acquired) this.markLeaseLost(claim.holderId);
      }).catch((error) => this.emit({ type: 'save_failed', error }));
    }, interval);
    (timer as unknown as { unref?: () => void }).unref?.();
    this.heartbeat = timer;
  }

  private stopHeartbeat(): void {
    if (this.heartbeat != null) clearInterval(this.heartbeat);
    this.heartbeat = null;
  }

  private markLeaseLost(holderId: string): void {
    if (this.saveBlocked || this.closed) return;
    this.saveBlocked = 'lease_lost';
    this.persistState = 'lease_lost';
    this.emit({ type: 'lease_lost', error: new SessionLeaseLostError(this.worldId, holderId) });
  }
}

async function readContext(transport: LocalWorldTransport, worldId: Id): Promise<ResumeServedState> {
  const response = await transport.execute('get_context', {}, { worldId });
  return { world: response.world, control: response.control, work: response.work, activeInput: response.activeInput };
}
