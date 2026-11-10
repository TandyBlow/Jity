/** Durable browser progress: the saved record, its immutable metadata and the
 * exclusive-write lease. Game facts live ONLY in the recorded
 * LocalGameSnapshot; metadata is derived from that snapshot at save time and
 * never becomes a second source of truth. */
import type { Id, Phase } from '../../types';
import type { LocalGameSnapshot } from '../session';

export const PROGRESS_SCHEMA_VERSION = 1 as const;

/** Frozen-at-save description of one record. Consumers (progress sync, UI)
 * may read this instead of deserialising the whole snapshot, but may not use
 * it to reconstruct game state. */
export interface ProgressMetadata {
  schemaVersion: typeof PROGRESS_SCHEMA_VERSION;
  worldId: Id;
  /** Monotonic per world; a save replaces revision n with n+1. */
  revision: number;
  savedAtEpochMilli: number;
  /** Session/tab that produced this revision. */
  writerId: string;
  headPointId: Id;
  version: number;
  /** control.revision at save time (checkpoint binding). */
  checkpointRevision: number;
  phase: Phase;
  paused: boolean;
  /** True while a point settlement is in progress (mid-turn checkpoint). */
  hasWork: boolean;
  workPointId: Id | null;
  workPhase: 'select_actor' | 'build_group' | 'settle_group' | null;
  roundId: Id | null;
  advanceId: Id | null;
  narrationStatus: string;
  /** Number of player commands retained in the snapshot. */
  commands: number;
  /** Committed head state digest (identity of the state this record holds). */
  stateDigest: string;
  /** world-canonical digest of the whole snapshot, only when requested. */
  snapshotDigest: string | null;
}

export interface SavedLocalProgress {
  metadata: ProgressMetadata;
  snapshot: LocalGameSnapshot;
}

export interface StoredLease {
  worldId: Id;
  holderId: string;
  /** Fencing generation: increments on every takeover (never on renewal by
   * the same holder). */
  epoch: number;
  issuedAtEpochMilli: number;
  renewedAtEpochMilli: number;
  expiresAtEpochMilli: number;
}

export interface LeaseInfo {
  worldId: Id;
  holderId: string;
  epoch: number;
  renewedAtEpochMilli: number;
  expiresAtEpochMilli: number;
}

export type LeaseClaim =
  | { acquired: true; lease: LeaseInfo; recovered: boolean }
  | { acquired: false; holderId: string; expiresAtEpochMilli: number };

export interface LegacyBackup {
  key: string;
  sourceKey: string;
  raw: string;
  capturedAtEpochMilli: number;
}

export interface SaveProgressOptions {
  /** Optimistic concurrency: 0 means "the world must not exist yet". Omit to
   * overwrite blindly (only migrations should do that). */
  expectedRevision?: number;
  /** Lease holder id; when requireLease is true a save by another holder (or
   * no holder) is refused as fenced. */
  sessionId?: string;
  requireLease?: boolean;
  writerId?: string;
  /** Compute a canonical digest of the whole snapshot (integrity check). */
  digest?: boolean;
  now?: number;
}

export interface DeleteProgressOptions {
  /** Deleting another holder's live progress is refused unless forced. */
  sessionId?: string;
  force?: boolean;
}

export class ProgressConflictError extends Error {
  readonly name = 'ProgressConflictError';
  constructor(readonly worldId: Id, readonly expectedRevision: number, readonly current: ProgressMetadata | null) {
    super(`progress_conflict:${worldId}: expected revision ${expectedRevision}, stored ${current?.revision ?? 'none'}`);
  }
}

export class SessionLeaseHeldError extends Error {
  readonly name = 'SessionLeaseHeldError';
  constructor(readonly worldId: Id, readonly holderId: string, readonly expiresAtEpochMilli: number) {
    super(`session_lease_held:${worldId}: held by ${holderId} until ${expiresAtEpochMilli}`);
  }
}

export class SessionLeaseLostError extends Error {
  readonly name = 'SessionLeaseLostError';
  constructor(readonly worldId: Id, readonly holderId: string | null) {
    super(`session_lease_lost:${worldId}: ${holderId ? `now held by ${holderId}` : 'no lease held'}`);
  }
}

/** A live lease held by another tab blocks deleting its progress. */
export class SessionDeleteBlockedError extends Error {
  readonly name = 'SessionDeleteBlockedError';
  constructor(readonly worldId: Id, readonly holderId: string) {
    super(`session_delete_blocked:${worldId}: held by ${holderId}`);
  }
}

export interface LocalProgressStore {
  /** 'indexeddb' is durable; 'memory' only exists for tests/unsupported
   * environments and is reported through `durable`. */
  readonly kind: 'indexeddb' | 'memory';
  readonly durable: boolean;
  save(worldId: Id, snapshot: LocalGameSnapshot, options?: SaveProgressOptions): Promise<ProgressMetadata>;
  load(worldId: Id): Promise<SavedLocalProgress | null>;
  list(): Promise<ProgressMetadata[]>;
  delete(worldId: Id, options?: DeleteProgressOptions): Promise<void>;
  close(): Promise<void>;
  claimLease(worldId: Id, holderId: string, ttlMs?: number): Promise<LeaseClaim>;
  renewLease(worldId: Id, holderId: string, ttlMs?: number): Promise<LeaseClaim>;
  takeoverLease(worldId: Id, holderId: string, ttlMs?: number): Promise<LeaseInfo>;
  releaseLease(worldId: Id, holderId: string): Promise<void>;
  readLease(worldId: Id): Promise<LeaseInfo | null>;
  backupLegacy(backup: LegacyBackup): Promise<void>;
  loadLegacyBackup(key: string): Promise<LegacyBackup | null>;
}

export interface OpenLocalProgressOptions {
  /** auto = IndexedDB when the platform exposes it, memory otherwise (the
   * caller can warn via store.durable). */
  backend?: 'auto' | 'indexeddb' | 'memory';
  databaseName?: string;
  indexedDB?: IDBFactory;
  now?: () => number;
}
