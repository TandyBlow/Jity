/** Storage backend contract. The store's correctness rules (revision
 * compare-and-set, lease fencing) run INSIDE one transaction, so a backend
 * must provide serialisable read-modify-write semantics per call. */
import type { Id } from '../../types';
import type { LegacyBackup, SavedLocalProgress, StoredLease } from './types';

export interface ProgressTxn {
  getProgress(worldId: Id): Promise<SavedLocalProgress | null>;
  listProgress(): Promise<SavedLocalProgress[]>;
  putProgress(record: SavedLocalProgress): Promise<void>;
  deleteProgress(worldId: Id): Promise<void>;
  getLease(worldId: Id): Promise<StoredLease | null>;
  putLease(worldId: Id, lease: StoredLease | null): Promise<void>;
  getLegacy(key: string): Promise<LegacyBackup | null>;
  putLegacy(backup: LegacyBackup): Promise<void>;
}

export interface ProgressBackend {
  readonly kind: 'indexeddb' | 'memory';
  transact<T>(mode: 'read' | 'readwrite', work: (txn: ProgressTxn) => Promise<T>): Promise<T>;
  close(): Promise<void>;
}
