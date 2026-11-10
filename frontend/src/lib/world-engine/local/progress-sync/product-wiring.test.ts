/** The exact wiring 06 has today vs the one that survives a reload.
 *
 * 06's page builds `createProductSync({store, worldId, baseUrl})` without
 * `storage`. The offline queue and the last known remote head then live only in
 * memory, so an offline save followed by a reload cannot be uploaded and the
 * remote base is forgotten. Both costs are product-visible, so this file pins
 * the difference instead of only documenting it.
 */

import { describe, expect, it } from 'vitest';

import { createProductSync } from './product';
import { ProgressSyncClient } from './client';
import type { StorageLike } from './client';

/** Just enough of window.localStorage for the adapter. */
function memoryStorage(): StorageLike & { dump(): Record<string, string> } {
  const map = new Map<string, string>();
  return {
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, value: string) => { map.set(key, value); },
    dump: () => Object.fromEntries(map),
  };
}

function typedStore() {
  return memoryStore() as {
    records: Map<string, unknown>;
    load(worldId: string): Promise<{ snapshot: { turn: number } } | null>;
    save(worldId: string, snapshot: { turn: number }): Promise<unknown>;
  };
}

function memoryStore() {
  const records = new Map<string, unknown>();
  return {
    records,
    async load(worldId: string) {
      const value = records.get(worldId);
      return value === undefined ? null : { snapshot: value };
    },
    async save(worldId: string, snapshot: unknown) {
      records.set(worldId, snapshot);
      return { revision: records.size };
    },
  };
}

const offlineFetch = (async () => {
  throw new TypeError('fetch failed: offline');
}) as unknown as typeof fetch;

describe('product wiring survives a reload only with browser storage', () => {
  it('without storage the offline queue and the head are lost on reload', async () => {
    const store = typedStore();
    const before = createProductSync<{ turn: number }>({
      store,
      worldId: 'w1',
      baseUrl: 'http://127.0.0.1:9/local-progress',
      fetchImpl: offlineFetch,
      sleep: async () => undefined,
    });
    const saved = await before.save({ turn: 1 });
    expect(saved.localSaved).toBe(true);
    expect(saved.outcome?.status).toBe('queued');
    expect(await before.pending()).toBe(1);

    const after = createProductSync<{ turn: number }>({
      store,
      worldId: 'w1',
      baseUrl: 'http://127.0.0.1:9/local-progress',
      fetchImpl: offlineFetch,
      sleep: async () => undefined,
    });
    expect(await after.pending()).toBe(0);
    expect(await after.client.lastKnownHead('w1')).toBeNull();
  });

  it('with storage the same reload keeps the queued upload and the head', async () => {
    const store = typedStore();
    const storage = memoryStorage();
    let fetchCalls = 0;
    const flakyFetch = (async () => {
      fetchCalls += 1;
      throw new TypeError('fetch failed: offline');
    }) as unknown as typeof fetch;

    const before = createProductSync<{ turn: number }>({
      store,
      worldId: 'w1',
      baseUrl: 'http://127.0.0.1:9/local-progress',
      storage,
      fetchImpl: flakyFetch,
      sleep: async () => undefined,
    });
    await before.save({ turn: 1 });
    expect(await before.pending()).toBe(1);
    expect(fetchCalls).toBeGreaterThan(0);

    const after = createProductSync<{ turn: number }>({
      store,
      worldId: 'w1',
      baseUrl: 'http://127.0.0.1:9/local-progress',
      storage,
      fetchImpl: flakyFetch,
      sleep: async () => undefined,
    });
    expect(await after.pending()).toBe(1);
    expect(Object.keys(storage.dump())).toContain('jity.progress-sync.queue.v1');
  });

  it('the head store is what the client consults, not an in-memory guess', async () => {
    const storage = memoryStorage();
    const client = new ProgressSyncClient<{ turn: number }>({
      baseUrl: 'http://127.0.0.1:9/local-progress',
      fetchImpl: offlineFetch,
      localStore: { load: async () => null, save: async () => undefined },
      headStore: {
        load: async (worldId) => (worldId === 'w1' ? { worldId, headSnapshotId: 'snap-9', revision: 4 } : null),
        save: async () => undefined,
      },
    });
    const head = await client.lastKnownHead('w1');
    expect(head).toMatchObject({ worldId: 'w1', headSnapshotId: 'snap-9', revision: 4 });
    expect(storage.dump()).toEqual({});
  });
});
