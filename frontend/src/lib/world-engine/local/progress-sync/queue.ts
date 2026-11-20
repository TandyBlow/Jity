/** Offline queue stores for ProgressSyncClient.
 *
 * A queue item keeps the original requestId. Retrying after a lost response
 * therefore hits the server's idempotency row instead of creating a second
 * snapshot or a spurious CAS conflict.
 */

import type { OfflineQueueStore, QueuedUpload } from './types';

export class MemoryQueueStore implements OfflineQueueStore {
  private items: QueuedUpload[] = [];

  async load(): Promise<QueuedUpload[]> {
    return this.items.map((item) => structuredClone(item));
  }

  async save(items: readonly QueuedUpload[]): Promise<void> {
    this.items = items.map((item) => structuredClone(item));
  }
}

/** Minimal Storage surface (window.localStorage and test fakes both fit). */
export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

/** Persist the queue in browser storage so a reload does not lose offline saves. */
export function createWebStorageQueueStore(key: string, storage: StorageLike): OfflineQueueStore {
  return {
    async load(): Promise<QueuedUpload[]> {
      const raw = storage.getItem(key);
      if (!raw) return [];
      try {
        const parsed = JSON.parse(raw) as unknown;
        if (!Array.isArray(parsed)) return [];
        return parsed.filter((item): item is QueuedUpload => Boolean(item)
          && typeof item === 'object'
          && typeof (item as QueuedUpload).request?.requestId === 'string');
      } catch {
        return [];
      }
    },
    async save(items: readonly QueuedUpload[]): Promise<void> {
      storage.setItem(key, JSON.stringify(items));
    },
  };
}
