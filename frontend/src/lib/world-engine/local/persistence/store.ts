/** Durable local progress store. The record is the existing
 * LocalGameSnapshot (transport record + command log + optional scheduler
 * checkpoint); everything else here is derived metadata, a writer lease or a
 * migration backup. */
import type { Id } from '../../types';
import { canonicalDigest } from '../canonical';
import type { LocalGameSnapshot } from '../session';
import type { ProgressBackend } from './backend';
import { IndexedDbProgressBackend, isIndexedDbAvailable, DEFAULT_DATABASE_NAME } from './indexeddb';
import { MemoryProgressBackend } from './memory';
import {
  PROGRESS_SCHEMA_VERSION, ProgressConflictError, SessionDeleteBlockedError, SessionLeaseHeldError, SessionLeaseLostError,
  type DeleteProgressOptions, type LeaseClaim, type LeaseInfo, type LegacyBackup, type LocalProgressStore,
  type OpenLocalProgressOptions, type ProgressMetadata, type SaveProgressOptions, type SavedLocalProgress, type StoredLease,
} from './types';

export const DEFAULT_LEASE_TTL_MS = 30_000;

function leaseInfo(lease: StoredLease): LeaseInfo {
  return { worldId: lease.worldId, holderId: lease.holderId, epoch: lease.epoch,
    renewedAtEpochMilli: lease.renewedAtEpochMilli, expiresAtEpochMilli: lease.expiresAtEpochMilli };
}

function assertSnapshot(worldId: Id, snapshot: LocalGameSnapshot): void {
  const transport = snapshot?.transport as { worldId?: Id; state?: unknown; pointStates?: unknown; control?: { revision?: unknown } } | undefined;
  if (!transport || transport.worldId !== worldId || !transport.state || !transport.pointStates
    || !transport.control || typeof transport.control.revision !== 'number') {
    throw new Error(`local_progress_snapshot_invalid:${worldId}`);
  }
}

function describeSnapshot(worldId: Id, snapshot: LocalGameSnapshot, revision: number, savedAtEpochMilli: number, writerId: string,
  snapshotDigest: string | null): ProgressMetadata {
  const transport = snapshot.transport;
  const head = transport.pointStates[transport.headPointId];
  const narration = transport.narrations[transport.headPointId];
  return {
    schemaVersion: PROGRESS_SCHEMA_VERSION, worldId, revision, savedAtEpochMilli, writerId,
    headPointId: transport.headPointId, version: transport.version, checkpointRevision: transport.control.revision,
    phase: transport.control.phase, paused: transport.control.paused,
    hasWork: transport.work != null, workPointId: transport.work?.pointId ?? null, workPhase: transport.work?.phase ?? null,
    roundId: transport.round?.roundId ?? null, advanceId: transport.advance?.advanceId ?? null,
    narrationStatus: narration?.status ?? 'missing', commands: snapshot.commands?.length ?? 0,
    stateDigest: head?.stateDigest ?? '', snapshotDigest,
  };
}

class Store implements LocalProgressStore {
  constructor(private readonly backend: ProgressBackend, private readonly now: () => number) {}
  get kind(): 'indexeddb' | 'memory' { return this.backend.kind; }
  get durable(): boolean { return this.backend.kind === 'indexeddb'; }

  async save(worldId: Id, snapshot: LocalGameSnapshot, options: SaveProgressOptions = {}): Promise<ProgressMetadata> {
    assertSnapshot(worldId, snapshot);
    const now = options.now ?? this.now();
    const snapshotDigest = options.digest ? await canonicalDigest(snapshot) : null;
    return this.backend.transact('readwrite', async (txn) => {
      const existing = await txn.getProgress(worldId);
      if (options.expectedRevision !== undefined) {
        const current = existing?.metadata.revision ?? 0;
        if (current !== options.expectedRevision) throw new ProgressConflictError(worldId, options.expectedRevision, existing?.metadata ?? null);
      }
      if (options.requireLease) {
        const lease = await txn.getLease(worldId);
        if (!lease || lease.holderId !== options.sessionId) throw new SessionLeaseLostError(worldId, lease?.holderId ?? null);
        // An expired-but-still-ours lease is recoverable: renew it, never
        // silently start a second writer.
        if (lease.expiresAtEpochMilli <= now) {
          await txn.putLease(worldId, { ...lease, renewedAtEpochMilli: now, expiresAtEpochMilli: now + DEFAULT_LEASE_TTL_MS });
        }
      }
      const metadata = describeSnapshot(worldId, snapshot, (existing?.metadata.revision ?? 0) + 1, now,
        options.writerId ?? options.sessionId ?? 'anonymous', snapshotDigest);
      await txn.putProgress({ metadata, snapshot });
      return metadata;
    });
  }

  async load(worldId: Id): Promise<SavedLocalProgress | null> {
    return this.backend.transact('read', (txn) => txn.getProgress(worldId));
  }

  async list(): Promise<ProgressMetadata[]> {
    const records = await this.backend.transact('read', (txn) => txn.listProgress());
    return records.map((record) => record.metadata).sort((a, b) => b.savedAtEpochMilli - a.savedAtEpochMilli);
  }

  async delete(worldId: Id, options: DeleteProgressOptions = {}): Promise<void> {
    const now = this.now();
    await this.backend.transact('readwrite', async (txn) => {
      const lease = await txn.getLease(worldId);
      if (!options.force && lease && lease.holderId !== options.sessionId && lease.expiresAtEpochMilli > now) {
        throw new SessionDeleteBlockedError(worldId, lease.holderId);
      }
      await txn.deleteProgress(worldId);
      await txn.putLease(worldId, null);
    });
  }

  async close(): Promise<void> { await this.backend.close(); }

  async claimLease(worldId: Id, holderId: string, ttlMs = DEFAULT_LEASE_TTL_MS): Promise<LeaseClaim> {
    const now = this.now();
    return this.backend.transact('readwrite', async (txn) => {
      const lease = await txn.getLease(worldId);
      if (lease && lease.expiresAtEpochMilli > now && lease.holderId !== holderId) {
        return { acquired: false, holderId: lease.holderId, expiresAtEpochMilli: lease.expiresAtEpochMilli };
      }
      // Expired lease or same holder: recover. A takeover bumps the fencing
      // epoch so the old tab can be told it was replaced.
      const recovered = !!lease && lease.holderId !== holderId;
      const sameHolder = !!lease && lease.holderId === holderId;
      const next: StoredLease = {
        worldId, holderId, epoch: lease ? (sameHolder ? lease.epoch : lease.epoch + 1) : 1,
        issuedAtEpochMilli: sameHolder ? lease!.issuedAtEpochMilli : now,
        renewedAtEpochMilli: now, expiresAtEpochMilli: now + ttlMs,
      };
      await txn.putLease(worldId, next);
      return { acquired: true, lease: leaseInfo(next), recovered };
    });
  }

  async renewLease(worldId: Id, holderId: string, ttlMs = DEFAULT_LEASE_TTL_MS): Promise<LeaseClaim> {
    return this.claimLease(worldId, holderId, ttlMs);
  }

  /** Explicit takeover (the page's "play in this tab" action): bumps the
   * fencing epoch even while another tab's lease is live, so the previous
   * writer's next save or renewal is refused instead of silently interleaving. */
  async takeoverLease(worldId: Id, holderId: string, ttlMs = DEFAULT_LEASE_TTL_MS): Promise<LeaseInfo> {
    const now = this.now();
    return this.backend.transact('readwrite', async (txn) => {
      const lease = await txn.getLease(worldId);
      const sameHolder = !!lease && lease.holderId === holderId;
      const next: StoredLease = {
        worldId, holderId, epoch: lease ? (sameHolder ? lease.epoch : lease.epoch + 1) : 1,
        issuedAtEpochMilli: sameHolder ? lease!.issuedAtEpochMilli : now,
        renewedAtEpochMilli: now, expiresAtEpochMilli: now + ttlMs,
      };
      await txn.putLease(worldId, next);
      return leaseInfo(next);
    });
  }

  async releaseLease(worldId: Id, holderId: string): Promise<void> {
    await this.backend.transact('readwrite', async (txn) => {
      const lease = await txn.getLease(worldId);
      if (lease && lease.holderId === holderId) await txn.putLease(worldId, null);
    });
  }

  async readLease(worldId: Id): Promise<LeaseInfo | null> {
    const lease = await this.backend.transact('read', (txn) => txn.getLease(worldId));
    return lease ? leaseInfo(lease) : null;
  }

  async backupLegacy(backup: LegacyBackup): Promise<void> {
    await this.backend.transact('readwrite', (txn) => txn.putLegacy(backup));
  }

  async loadLegacyBackup(key: string): Promise<LegacyBackup | null> {
    return this.backend.transact('read', (txn) => txn.getLegacy(key));
  }
}

/** Bind the store rules to an explicit backend (tests, custom storage). */
export function createLocalProgressStore(backend: ProgressBackend, options: { now?: () => number } = {}): LocalProgressStore {
  return new Store(backend, options.now ?? (() => Date.now()));
}

export async function openLocalProgressStore(options: OpenLocalProgressOptions = {}): Promise<LocalProgressStore> {
  const now = options.now ?? (() => Date.now());
  const backend = options.backend ?? 'auto';
  if (backend === 'memory') return new Store(new MemoryProgressBackend(), now);
  const factory = options.indexedDB ?? (typeof globalThis.indexedDB !== 'undefined' ? globalThis.indexedDB : null);
  if (isIndexedDbAvailable(factory)) {
    try {
      return new Store(await IndexedDbProgressBackend.open(factory!, options.databaseName ?? DEFAULT_DATABASE_NAME), now);
    } catch (error) {
      if (backend === 'indexeddb') throw error;
      // Fall through to the explicit non-durable backend; store.durable tells
      // the caller the difference instead of pretending the save is safe.
    }
  }
  return new Store(new MemoryProgressBackend(), now);
}

export { SessionLeaseHeldError };
export type { LocalProgressStore, ProgressMetadata, SavedLocalProgress, LeaseClaim, LeaseInfo };
