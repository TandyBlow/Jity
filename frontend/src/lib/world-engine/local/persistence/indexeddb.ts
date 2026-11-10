/** IndexedDB backend. One database holds progress records, writer leases and
 * legacy-migration backups; every read-modify-write runs in a single
 * readwrite transaction, so revision checks and lease fencing are atomic
 * against other tabs. */
import type { ProgressBackend, ProgressTxn } from './backend';
import type { LegacyBackup, SavedLocalProgress, StoredLease } from './types';

export const DEFAULT_DATABASE_NAME = 'jity-local-progress';
const DB_VERSION = 1;
const PROGRESS_STORE = 'progress';
const LEASE_STORE = 'leases';
const LEGACY_STORE = 'legacy';

function request<T>(value: IDBRequest<T>): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    value.onsuccess = () => resolve(value.result);
    value.onerror = () => reject(value.error ?? new Error('indexeddb_request_failed'));
  });
}

function openDatabase(factory: IDBFactory, name: string): Promise<IDBDatabase> {
  return new Promise<IDBDatabase>((resolve, reject) => {
    const open = factory.open(name, DB_VERSION);
    open.onupgradeneeded = () => {
      const db = open.result;
      if (!db.objectStoreNames.contains(PROGRESS_STORE)) db.createObjectStore(PROGRESS_STORE, { keyPath: 'metadata.worldId' });
      if (!db.objectStoreNames.contains(LEASE_STORE)) db.createObjectStore(LEASE_STORE, { keyPath: 'worldId' });
      if (!db.objectStoreNames.contains(LEGACY_STORE)) db.createObjectStore(LEGACY_STORE, { keyPath: 'key' });
    };
    open.onsuccess = () => resolve(open.result);
    open.onerror = () => reject(open.error ?? new Error('indexeddb_open_failed'));
    open.onblocked = () => reject(new Error('indexeddb_open_blocked'));
  });
}

function transactionFacade(tx: IDBTransaction): ProgressTxn {
  const store = (name: string) => tx.objectStore(name);
  return {
    async getProgress(worldId) {
      return (await request(store(PROGRESS_STORE).get(worldId) as IDBRequest<SavedLocalProgress | undefined>)) ?? null;
    },
    async listProgress() {
      return (await request(store(PROGRESS_STORE).getAll() as IDBRequest<SavedLocalProgress[]>)) ?? [];
    },
    async putProgress(record) { await request(store(PROGRESS_STORE).put(record)); },
    async deleteProgress(worldId) { await request(store(PROGRESS_STORE).delete(worldId)); },
    async getLease(worldId) {
      return (await request(store(LEASE_STORE).get(worldId) as IDBRequest<StoredLease | undefined>)) ?? null;
    },
    async putLease(worldId, lease) {
      if (lease) await request(store(LEASE_STORE).put(lease));
      else await request(store(LEASE_STORE).delete(worldId));
    },
    async getLegacy(key) {
      return (await request(store(LEGACY_STORE).get(key) as IDBRequest<LegacyBackup | undefined>)) ?? null;
    },
    async putLegacy(backup) { await request(store(LEGACY_STORE).put(backup)); },
  };
}

export class IndexedDbProgressBackend implements ProgressBackend {
  readonly kind = 'indexeddb' as const;

  private constructor(private readonly db: IDBDatabase) {}

  static async open(factory: IDBFactory, name = DEFAULT_DATABASE_NAME): Promise<IndexedDbProgressBackend> {
    return new IndexedDbProgressBackend(await openDatabase(factory, name));
  }

  /** The transaction stays alive across awaits because every awaited promise
   * resolves from an IndexedDB request event; a rejection aborts it, so a
   * failed save never leaves half a record behind. */
  async transact<T>(mode: 'read' | 'readwrite', work: (txn: ProgressTxn) => Promise<T>): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      let tx: IDBTransaction;
      try {
        tx = this.db.transaction([PROGRESS_STORE, LEASE_STORE, LEGACY_STORE], mode === 'read' ? 'readonly' : 'readwrite');
      } catch (error) {
        reject(error);
        return;
      }
      let settled = false;
      let result: T;
      tx.oncomplete = () => { if (!settled) { settled = true; resolve(result); } };
      tx.onabort = () => { if (!settled) { settled = true; reject(tx.error ?? new Error('indexeddb_transaction_aborted')); } };
      tx.onerror = () => { if (!settled) { settled = true; reject(tx.error ?? new Error('indexeddb_transaction_failed')); } };
      const fail = (error: unknown) => {
        if (settled) return;
        settled = true;
        try { tx.abort(); } catch { /* already finished */ }
        reject(error);
      };
      try {
        Promise.resolve(work(transactionFacade(tx))).then((value) => { result = value; }, fail);
      } catch (error) {
        fail(error);
      }
    });
  }

  async close(): Promise<void> { this.db.close(); }
}

export function isIndexedDbAvailable(factory?: IDBFactory | null): boolean {
  if (factory) return true;
  return typeof globalThis.indexedDB !== 'undefined' && globalThis.indexedDB !== null;
}
