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
      writeLocal: true,
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
      writeLocal: true,
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

  it('no default product call writes the store or replaces local history', async () => {
    const store = typedStore();
    store.records.set('w1', { turn: 1, commands: ['a', 'b'], narrations: { p1: 'x', p2: 'y' } });
    let writes = 0;
    const originalSave = store.save.bind(store);
    store.save = async (worldId: string, snapshot: { turn: number }) => {
      writes += 1;
      return originalSave(worldId, snapshot);
    };
    let fetches = 0;
    const fetching = (async () => {
      fetches += 1;
      throw new TypeError('offline');
    }) as unknown as typeof fetch;
    const sync = createProductSync<{ turn: number }>({
      store,
      worldId: 'w1',
      baseUrl: 'http://127.0.0.1:9/local-progress',
      fetchImpl: fetching,
      sleep: async () => undefined,
    });

    // Every default call: save/push/flush/status/restore/choose.
    await sync.save({ turn: 2 }, { requestId: 'inv-1' });
    await sync.push({ turn: 2 }, { requestId: 'inv-2' });
    await sync.flush();
    await sync.status();
    const restored = await sync.restore();
    expect(restored.source).toBe('local');
    expect(restored.snapshot).toEqual({ turn: 1, commands: ['a', 'b'], narrations: { p1: 'x', p2: 'y' } });
    const beforeFetches = fetches;
    expect(writes).toBe(0);
    expect(store.records.get('w1')).toEqual({ turn: 1, commands: ['a', 'b'], narrations: { p1: 'x', p2: 'y' } });

    // A local save means restore must not go to the network at all: an older
    // remote copy can never replace newer local history.
    expect(fetches).toBe(beforeFetches);
  });

  it('restore still reaches the remote when there is no local save', async () => {
    const store = typedStore();
    let fetches = 0;
    const serving = (async (input: RequestInfo | URL) => {
      fetches += 1;
      const url = new URL(String(input));
      if (url.pathname.endsWith('/head')) {
        return new Response(JSON.stringify({ worldId: 'w1', headSnapshotId: 'snap-1', revision: 2 }),
          { status: 200, headers: { 'content-type': 'application/json' } });
      }
      return new Response(JSON.stringify({
        snapshotId: 'snap-1', worldId: 'w1', parentSnapshotIds: [], revision: 2,
        contentDigest: 'd', sizeBytes: 10, createdAt: '2026-01-01T00:00:00Z',
        payload: { turn: 7, commands: ['远程历史'] },
      }), { status: 200, headers: { 'content-type': 'application/json' } });
    }) as unknown as typeof fetch;
    const sync = createProductSync<{ turn: number }>({
      store,
      worldId: 'w1',
      baseUrl: 'http://sync.test/local-progress',
      fetchImpl: serving,
      sleep: async () => undefined,
    });
    const restored = await sync.restore();
    expect(restored.source).toBe('remote');
    expect(restored.snapshot).toEqual({ turn: 7, commands: ['远程历史'] });
    expect(fetches).toBe(2);
    // Default restore does not write the session-owned store either.
    expect(store.records.get('w1')).toBeUndefined();
  });

  it('uses the browser store automatically when storage is not passed', async () => {
    const memory = new Map<string, string>();
    const fake = {
      getItem: (key: string) => memory.get(key) ?? null,
      setItem: (key: string, value: string) => { memory.set(key, value); },
      removeItem: (key: string) => { memory.delete(key); },
    };
    const globals = globalThis as { localStorage?: unknown };
    const previous = globals.localStorage;
    globals.localStorage = fake;
    try {
      // Offline save with no `storage` option, then a fresh adapter (a reload)
      // must find the queued upload and the head it was based on.
      const first = createProductSync<{ turn: number }>({
        store: typedStore(), worldId: 'w1', baseUrl: 'http://127.0.0.1:9/local-progress',
        writeLocal: true, fetchImpl: offlineFetch, sleep: async () => undefined,
      });
      const saved = await first.save({ turn: 1 });
      expect(saved.outcome?.status).toBe('queued');

      let uploads = 0;
      const online = (async (input: RequestInfo | URL) => {
        const url = new URL(String(input));
        if (url.pathname.endsWith('/snapshots')) {
          uploads += 1;
          return new Response(JSON.stringify({
            snapshotId: 'snap-1', worldId: 'w1', parentSnapshotIds: [], revision: 1,
            contentDigest: 'd', sizeBytes: 1, createdAt: '2026-01-01T00:00:00Z', reused: false,
          }), { status: 201, headers: { 'content-type': 'application/json' } });
        }
        return new Response(JSON.stringify({ worldId: 'w1', headSnapshotId: null, revision: 0 }),
          { status: 200, headers: { 'content-type': 'application/json' } });
      }) as unknown as typeof fetch;
      const second = createProductSync<{ turn: number }>({
        store: typedStore(), worldId: 'w1', baseUrl: 'http://sync.test/local-progress',
        fetchImpl: online, sleep: async () => undefined,
      });
      const flushed = await second.flush();
      expect(flushed.uploaded + flushed.conflicts).toBe(1);
      expect(uploads).toBe(1);
    } finally {
      globals.localStorage = previous;
    }
  });

  it('keeps everything in memory when the caller passes storage: null', async () => {
    const memory = new Map<string, string>();
    const fake = {
      getItem: (key: string) => memory.get(key) ?? null,
      setItem: (key: string, value: string) => { memory.set(key, value); },
      removeItem: (key: string) => { memory.delete(key); },
    };
    const globals = globalThis as { localStorage?: unknown };
    const previous = globals.localStorage;
    const warnings: string[] = [];
    const originalWarn = console.warn;
    globals.localStorage = fake;
    console.warn = (...args: unknown[]) => { warnings.push(args.join(' ')); };
    try {
      const sync = createProductSync<{ turn: number }>({
        store: typedStore(), worldId: 'w1', baseUrl: 'http://sync.test/local-progress',
        storage: null, writeLocal: true, fetchImpl: offlineFetch, sleep: async () => undefined,
      });
      await sync.save({ turn: 1 });
    } finally {
      console.warn = originalWarn;
      globals.localStorage = previous;
    }
    expect(warnings).toHaveLength(0);
    expect(memory.size).toBe(0);
  });
});
