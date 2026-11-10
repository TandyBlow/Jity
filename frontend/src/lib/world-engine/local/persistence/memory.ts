/** In-memory backend with the same serialisable transaction contract as
 * IndexedDB. Used by CPU tests and as the explicit non-durable fallback. */
import type { Id } from '../../types';
import type { ProgressBackend, ProgressTxn } from './backend';
import type { LegacyBackup, SavedLocalProgress, StoredLease } from './types';

interface MemoryState {
  progress: Map<Id, SavedLocalProgress>;
  leases: Map<Id, StoredLease>;
  legacy: Map<string, LegacyBackup>;
}

function copy<T>(value: T): T {
  return typeof structuredClone === 'function' ? structuredClone(value) : JSON.parse(JSON.stringify(value)) as T;
}

/** A write failure that leaves the stored record untouched, like a quota or
 * DataClone error in a real backend. */
export class SimulatedStorageWriteError extends Error {
  readonly name = 'SimulatedStorageWriteError';
  constructor(detail = 'simulated storage write failure') { super(detail); }
}

export class MemoryProgressBackend implements ProgressBackend {
  readonly kind = 'memory' as const;
  private state: MemoryState = { progress: new Map(), leases: new Map(), legacy: new Map() };
  private chain: Promise<unknown> = Promise.resolve();
  private failures = 0;

  /** Test hook: the next n writes throw and roll back. */
  failNextWrites(count = 1): void { this.failures = count; }

  seedProgress(record: SavedLocalProgress): void { this.state.progress.set(record.metadata.worldId, copy(record)); }
  seedLease(lease: StoredLease): void { this.state.leases.set(lease.worldId, copy(lease)); }
  peek(worldId: Id): SavedLocalProgress | null {
    const record = this.state.progress.get(worldId);
    return record ? copy(record) : null;
  }

  async transact<T>(mode: 'read' | 'readwrite', work: (txn: ProgressTxn) => Promise<T>): Promise<T> {
    const run = async (): Promise<T> => {
      const draft: MemoryState = { progress: new Map(this.state.progress), leases: new Map(this.state.leases), legacy: new Map(this.state.legacy) };
      const write = () => {
        if (this.failures > 0) { this.failures -= 1; throw new SimulatedStorageWriteError(); }
      };
      const txn: ProgressTxn = {
        async getProgress(worldId) { const record = draft.progress.get(worldId); return record ? copy(record) : null; },
        async listProgress() { return [...draft.progress.values()].map(copy); },
        async putProgress(record) { if (mode !== 'readwrite') throw new Error('read_only_transaction'); write(); draft.progress.set(record.metadata.worldId, copy(record)); },
        async deleteProgress(worldId) { if (mode !== 'readwrite') throw new Error('read_only_transaction'); write(); draft.progress.delete(worldId); },
        async getLease(worldId) { const lease = draft.leases.get(worldId); return lease ? copy(lease) : null; },
        async putLease(worldId, lease) { if (mode !== 'readwrite') throw new Error('read_only_transaction'); write(); if (lease) draft.leases.set(worldId, copy(lease)); else draft.leases.delete(worldId); },
        async getLegacy(key) { const backup = draft.legacy.get(key); return backup ? copy(backup) : null; },
        async putLegacy(backup) { if (mode !== 'readwrite') throw new Error('read_only_transaction'); write(); draft.legacy.set(backup.key, copy(backup)); },
      };
      const result = await work(txn);
      // Commit only after the whole read-modify-write succeeded.
      this.state = draft;
      return result;
    };
    const next = this.chain.then(run, run);
    this.chain = next.then(() => undefined, () => undefined);
    return next;
  }

  async close(): Promise<void> { await this.chain; }
}
