/** Opt-in integration test against a real progress-sync service: reconnect.
 *
 * Two-device requirement this covers:
 *   - device B plays offline and saves twice;
 *   - when the service comes back, B uploads only its own descendant chain
 *     (each snapshot's parent is the previous upload), not a whole rewrite;
 *   - a second flush is idempotent and does not create extra snapshots;
 *   - the other device pulls the newest descendant and keeps it locally.
 *
 * Run the standalone router (backend/app/services/local_progress/standalone.py)
 * and execute:
 *
 *   PROGRESS_SYNC_URL=http://127.0.0.1:8010 \
 *   PROGRESS_SYNC_TOKEN=secret \
 *   npx vitest run src/lib/world-engine/local/progress-sync/reconnect-chain.test.ts
 *
 * Without PROGRESS_SYNC_URL the suite is skipped.
 */

import { describe, expect, it } from 'vitest';

import {
  MemoryQueueStore, ProgressSyncClient, createProductSync,
  type HeadStateStore, type LocalSnapshotStore,
} from './index';

const baseUrl = process.env.PROGRESS_SYNC_URL;
const token = process.env.PROGRESS_SYNC_TOKEN;

class MemoryLocalStore implements LocalSnapshotStore<unknown> {
  readonly values = new Map<string, unknown>();
  async load(worldId: string): Promise<unknown | null> {
    return this.values.get(worldId) ?? null;
  }
  async save(worldId: string, payload: unknown): Promise<void> {
    this.values.set(worldId, structuredClone(payload));
  }
}

class MemoryHeadStore implements HeadStateStore {
  readonly values = new Map<string, { worldId: string; headSnapshotId: string | null; revision: number; updatedAt?: string | null }>();
  async load(worldId: string) {
    return this.values.get(worldId) ?? null;
  }
  async save(worldId: string, head: { worldId: string; headSnapshotId: string | null; revision: number; updatedAt?: string | null }) {
    this.values.set(worldId, structuredClone(head));
  }
}

const snapshot = (turn: number, text: string) => ({
  transport: { worldId: 'reconnect', round: turn, state: { characters: { a: { position: 'hall' } } } },
  commands: [text],
});

describe.skipIf(!baseUrl)('real progress-sync service: offline reconnect', () => {
  it('uploads only the descendant chain and is idempotent on a second flush', async () => {
    const worldId = `reconnect_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
    const local = new MemoryLocalStore();
    const queue = new MemoryQueueStore();
    // The product persists the last known head next to the local save; a
    // reload restores it, so an offline save still descends from the remote head.
    const heads = new MemoryHeadStore();
    const make = (url: string, prefix: string) => {
      let counter = 0;
      return new ProgressSyncClient<unknown>({
        baseUrl: url,
        token,
        fetchImpl: fetch,
        localStore: local,
        headStore: heads,
        queueStore: queue,
        retry: { attempts: 1 },
        idFactory: () => `${prefix}-${++counter}`,
      });
    };

    const online = make(baseUrl!, 'root');
    const root = await online.save(worldId, snapshot(1, 'root'), { requestId: 'reconnect-root' });
    expect(root.status).toBe('synced');
    if (root.status !== 'synced') throw new Error('root save failed');

    // Device B is offline: a closed port is a real network failure, not a mock.
    const offline = make('http://127.0.0.1:9', 'offline');
    const first = await offline.save(worldId, snapshot(2, 'offline-1'), { requestId: 'reconnect-o1' });
    expect(first.status).toBe('queued');
    const second = await offline.save(worldId, snapshot(3, 'offline-2'), { requestId: 'reconnect-o2' });
    expect(second.status).toBe('queued');
    expect(await offline.pending()).toBe(2);
    expect(local.values.get(worldId)).toEqual(snapshot(3, 'offline-2'));

    // Reconnect: the same queue is flushed by a client that can reach the service.
    const back = make(baseUrl!, 'flush');
    const flush = await back.flush();
    expect(flush.offline).toBe(false);
    expect(flush.failures).toEqual([]);
    expect(flush.conflicts).toEqual([]);
    expect(flush.remaining).toBe(0);
    expect(flush.uploaded).toHaveLength(2);

    const [one, two] = flush.uploaded;
    // Only descendants: the second snapshot's parent is the first upload.
    expect(one.parentSnapshotIds).toEqual([root.upload.snapshotId]);
    expect(two.parentSnapshotIds).toEqual([one.snapshotId]);
    expect(two.snapshotId).not.toBe(one.snapshotId);

    const graph = await back.graph(worldId);
    expect(graph.headSnapshotId).toBe(two.snapshotId);
    expect(graph.nodes).toHaveLength(3);
    expect(graph.branches).toEqual([two.snapshotId]);
    expect((await back.read(worldId, two.snapshotId)).payload).toEqual(snapshot(3, 'offline-2'));
    expect((await back.read(worldId, one.snapshotId)).payload).toEqual(snapshot(2, 'offline-1'));

    // A second flush must not re-upload anything.
    const again = await back.flush();
    expect(again.uploaded).toEqual([]);
    expect(again.remaining).toBe(0);
    const settled = await back.graph(worldId);
    expect(settled.nodes).toHaveLength(3);

    // The other device pulls the newest descendant into its own local store.
    const deviceA = make(baseUrl!, 'device-a');
    const pulled = await deviceA.pullLatest(worldId);
    expect(pulled.snapshot?.payload).toEqual(snapshot(3, 'offline-2'));
    expect(pulled.localSaved).toBe(true);
  });

  it('keeps both copies when two devices save from the same base and the player chooses', async () => {
    const worldId = `diverge_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
    const make = (prefix: string) => {
      let counter = 0;
      return new ProgressSyncClient<unknown>({
        baseUrl: baseUrl!,
        token,
        fetchImpl: fetch,
        localStore: new MemoryLocalStore(),
        retry: { attempts: 1 },
        idFactory: () => `${prefix}-${++counter}`,
      });
    };

    const a = make('div-a');
    const b = make('div-b');
    const root = await a.save(worldId, snapshot(1, 'root'), { requestId: 'div-root' });
    if (root.status !== 'synced') throw new Error('root save failed');
    await b.pullLatest(worldId);

    const fromA = await a.save(worldId, snapshot(2, 'A-keeps-going'), { requestId: 'div-a2' });
    expect(fromA.status).toBe('synced');
    const fromB = await b.save(worldId, snapshot(2, 'B-fork'), {
      requestId: 'div-b2',
      expectedHead: root.upload.snapshotId,
      expectedRevision: root.upload.revision,
    });
    // Never a silent overwrite of A's copy.
    expect(fromB.status).toBe('conflict');
    if (fromB.status !== 'conflict') throw new Error('expected conflict');

    // Both copies exist before the player chooses anything.
    const before = await b.graph(worldId);
    expect(before.nodes).toHaveLength(2);
    expect((await b.read(worldId, before.headSnapshotId!)).payload).toEqual(snapshot(2, 'A-keeps-going'));

    const kept = await b.resolveConflict(fromB.conflict, 'keep-local-fork');
    expect(kept.status).toBe('local-fork');
    const after = await b.graph(worldId);
    expect(new Set(after.branches)).toEqual(new Set([(fromA as { upload: { snapshotId: string } }).upload.snapshotId, kept.upload!.snapshotId]));
    expect(after.nodes).toHaveLength(3);
    expect((await b.read(worldId, (fromA as { upload: { snapshotId: string } }).upload.snapshotId)).payload).toEqual(snapshot(2, 'A-keeps-going'));

    // Choosing the other copy is a head move only; nothing is rewritten.
    await a.selectBranch(worldId, (fromA as { upload: { snapshotId: string } }).upload.snapshotId);
    const selected = await b.graph(worldId);
    expect(selected.headSnapshotId).toBe((fromA as { upload: { snapshotId: string } }).upload.snapshotId);
    expect(selected.nodes).toHaveLength(3);
    expect((await b.read(worldId, kept.upload!.snapshotId)).payload).toEqual(snapshot(2, 'B-fork'));
  });

  it('lets a session-owned, revision-checked store stay the only writer', async () => {
    const worldId = `owned_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
    // 06's durable store checks the revision the session holds. A second writer
    // moves it behind the session and the session's next save fails as a
    // conflict before any model call, which is exactly what 04 hit on the page.
    const records = new Map<string, { snapshot: unknown; revision: number }>();
    const store = {
      records,
      async load(id: string) {
        return records.get(id) ?? null;
      },
      async save(id: string, payload: unknown, options?: { expectedRevision?: number }) {
        const current = records.get(id);
        const expected = options?.expectedRevision;
        if (expected !== undefined && current && current.revision !== expected) {
          throw new Error('revision_conflict');
        }
        const next = { snapshot: structuredClone(payload), revision: (current?.revision ?? 0) + 1 };
        records.set(id, next);
        return { revision: next.revision };
      },
    };
    const sync = createProductSync<unknown>({
      store,
      worldId,
      baseUrl,
      token,
      storage: null,
      retry: { attempts: 2, baseDelayMs: 10 },
      sleep: async () => undefined,
    });

    // The session saves with the revision it owns, then asks for an upload.
    await store.save(worldId, snapshot(1, 'session-write'), { expectedRevision: 0 });
    const uploaded = await sync.save(snapshot(1, 'session-write'), { requestId: `owned-${worldId}-1` });
    expect(uploaded.localSaved).toBe(false);
    expect(uploaded.outcome?.status).toBe('synced');
    expect(records.get(worldId)?.revision).toBe(1);

    // The session keeps saving against its own revision, with no conflict.
    await expect(store.save(worldId, snapshot(2, 'session-continues'), { expectedRevision: 1 }))
      .resolves.toBeTruthy();
  });

  it('continues a restored history instead of replacing it', async () => {
    const worldId = `continue_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
    const history = (entries: string[]) => ({
      transport: {
        worldId,
        points: Object.fromEntries(entries.map((entry, index) => [
          `p${index + 1}`, { id: `p${index + 1}`, sequence: index + 1, trigger: 'player' },
        ])),
        narrations: Object.fromEntries(entries.map((entry, index) => [
          `p${index + 1}`, { status: 'ready', text: entry },
        ])),
        state: { characters: { lu: { position: 'lane' } } },
      },
      commands: entries,
    });
    // The product store returns a record; keep the payload here instead.
    const productStore = () => {
      const values = new Map<string, unknown>();
      return {
        values,
        async load(id: string) {
          return values.has(id) ? { snapshot: values.get(id) } : null;
        },
        async save(id: string, payload: unknown) {
          values.set(id, structuredClone(payload));
        },
      };
    };
    const a = createProductSync<unknown>({
      store: productStore(), worldId, baseUrl, token, storage: null,
      retry: { attempts: 2, baseDelayMs: 10 }, sleep: async () => undefined,
    });
    const first = await a.save(history(['第一回合', '第二回合']), { requestId: `cont-a-${worldId}` });
    expect(first.outcome?.status).toBe('synced');

    // A second device has no local save: it restores the remote copy, appends
    // one turn and saves. The result must be a child of A's snapshot and keep
    // both earlier entries.
    const b = createProductSync<unknown>({
      store: productStore(), worldId, baseUrl, token, storage: null,
      retry: { attempts: 2, baseDelayMs: 10 }, sleep: async () => undefined,
    });
    const restored = await b.restore();
    expect(restored.source).toBe('remote');
    const restoredHistory = restored.snapshot as { commands: string[] };
    expect(restoredHistory.commands).toEqual(['第一回合', '第二回合']);
    const grown = await b.save(history(['第一回合', '第二回合', '第三回合']), { requestId: `cont-b-${worldId}` });
    expect(grown.outcome?.status).toBe('synced');
    if (grown.outcome?.status !== 'synced') throw new Error('second device save failed');
    expect(grown.outcome.upload.parentSnapshotIds).toHaveLength(1);

    const reader = new ProgressSyncClient<unknown>({
      baseUrl: baseUrl!, token, fetchImpl: fetch, localStore: new MemoryLocalStore(),
    });
    const graph = await reader.graph(worldId);
    const leaf = await reader.read(worldId, graph.headSnapshotId!);
    const payload = leaf.payload as { commands: string[] };
    expect(payload.commands).toEqual(['第一回合', '第二回合', '第三回合']);
    expect(leaf.parentSnapshotIds).toContain(grown.outcome.upload.parentSnapshotIds[0]);
  });
});
