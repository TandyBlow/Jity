/** Opt-in integration test against a real progress-sync service.
 *
 * Run the standalone router (see backend/app/services/local_progress/standalone.py)
 * and execute:
 *
 *   PROGRESS_SYNC_URL=http://127.0.0.1:8010 \
 *   PROGRESS_SYNC_TOKEN=secret \
 *   npx vitest run src/lib/world-engine/local/progress-sync/real-server.test.ts
 *
 * Without PROGRESS_SYNC_URL the suite is skipped, so ordinary unit runs do not
 * require a running server.
 */

import { describe, expect, it } from 'vitest';

import { ProgressSyncClient, type LocalSnapshotStore } from './index';

const baseUrl = process.env.PROGRESS_SYNC_URL;

class MemoryLocalStore implements LocalSnapshotStore<unknown> {
  readonly values = new Map<string, unknown>();
  async load(worldId: string): Promise<unknown | null> {
    return this.values.get(worldId) ?? null;
  }
  async save(worldId: string, payload: unknown): Promise<void> {
    this.values.set(worldId, structuredClone(payload));
  }
}

const snapshot = (turn: number, text: string) => ({
  transport: { worldId: 'integration', round: turn, state: { characters: { a: { position: 'hall' } } } },
  commands: [text],
});

describe.skipIf(!baseUrl)('real progress-sync service', () => {
  it('runs two clients through save, conflict, fork, choice and recovery', async () => {
    const worldId = `integration_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
    const token = process.env.PROGRESS_SYNC_TOKEN;
    const make = () => {
      let counter = 0;
      const local = new MemoryLocalStore();
      const client = new ProgressSyncClient<unknown>({
        baseUrl: baseUrl!,
        token,
        fetchImpl: fetch,
        localStore: local,
        retry: { attempts: 1 },
        idFactory: () => `real-${++counter}`,
      });
      return { client, local };
    };

    const deviceA = make();
    const root = await deviceA.client.save(worldId, snapshot(1, 'root'), { requestId: 'real-root' });
    expect(root.status).toBe('synced');
    if (root.status !== 'synced') throw new Error('root save failed');

    const deviceB = make();
    const pulled = await deviceB.client.pullLatest(worldId);
    expect(pulled.snapshot?.payload).toEqual(snapshot(1, 'root'));

    const a2 = await deviceA.client.save(worldId, snapshot(2, 'A'), { requestId: 'real-a2' });
    expect(a2.status).toBe('synced');
    if (a2.status !== 'synced') throw new Error('A save failed');

    const stale = await deviceB.client.save(worldId, snapshot(2, 'B'), {
      requestId: 'real-b',
      expectedHead: root.upload.snapshotId,
      expectedRevision: root.upload.revision,
    });
    expect(stale.status).toBe('conflict');
    if (stale.status !== 'conflict') throw new Error('expected stale conflict');

    const resolved = await deviceB.client.resolveConflict(stale.conflict, 'keep-local-fork');
    expect(resolved.status).toBe('local-fork');
    expect(resolved.snapshot?.payload).toEqual(snapshot(2, 'B'));

    const graph = await deviceB.client.graph(worldId);
    expect(new Set(graph.branches)).toEqual(new Set([a2.upload.snapshotId, resolved.upload!.snapshotId]));
    expect(graph.nodes).toHaveLength(3);
    expect((await deviceB.client.read(worldId, a2.upload.snapshotId)).payload).toEqual(snapshot(2, 'A'));

    const recovered = await deviceA.client.pullLatest(worldId);
    expect(recovered.snapshot?.payload).toEqual(snapshot(2, 'B'));
    expect(deviceA.local.values.get(worldId)).toEqual(snapshot(2, 'B'));
  });
});
