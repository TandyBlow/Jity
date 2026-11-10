/** Replay 04's real-page blocker against 06's actual durable store.
 *
 * 04's /world-local run stopped at turn 1 with `progress_conflict` before any
 * model call: the session and the page shared one revision-checked IndexedDB
 * store, and the page's sync.save() wrote it a second time without the
 * session's expectedRevision. This script uses 06's real store implementation
 * (memory backend, same code as IndexedDB) and this lane's adapter to show:
 *
 *   1. with the old local-writing behavior the session's next save conflicts;
 *   2. with the current default (upload only) the session stays the only
 *      writer and its next save succeeds.
 *
 *   LANE06_ROOT=../../06-recovery ./node_modules/.bin/jiti \
 *     ./scripts/parallel-sync/session-owned-store-check.ts
 *
 * No service is needed: the network is a fake that reports "offline", which is
 * also the path that used to queue the upload.
 */
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

import { createProductSync } from '../../src/lib/world-engine/local/progress-sync/product';

const lane06 = process.env.LANE06_ROOT
  ?? 'D:/others/Jity/.local/parallel-local-game/worktrees/06-recovery';
const load = async (modulePath: string) =>
  import(pathToFileURL(join(lane06, modulePath)).href) as Promise<Record<string, unknown>>;

const storeModule = await load('frontend/src/lib/world-engine/local/persistence/store.ts');
const memoryModule = await load('frontend/src/lib/world-engine/local/persistence/memory.ts');
const createLocalProgressStore = storeModule.createLocalProgressStore as (backend: unknown) => {
  kind: string;
  save(worldId: string, snapshot: Snapshot, options?: { expectedRevision?: number }): Promise<{ revision: number }>;
  load(worldId: string): Promise<{ metadata: { revision: number }; snapshot: Snapshot } | null>;
};
const MemoryProgressBackend = memoryModule.MemoryProgressBackend as new () => unknown;

interface Snapshot {
  transport: {
    worldId: string;
    state: Record<string, unknown>;
    pointStates: Record<string, { stateDigest: string }>;
    control: { revision: number; phase: string; paused: boolean };
    narrations: Record<string, unknown>;
    headPointId: string;
    version: number;
  };
  commands: Array<{ text: string }>;
}

const worldId = process.env.PROGRESS_SYNC_URL
  ? `w_owned_${Date.now().toString(36)}`
  : 'w_owned';
const snapshot = (revision: number, text: string): Snapshot => ({
  transport: {
    worldId,
    state: { characters: {}, locations: {}, items: {} },
    pointStates: { p1: { stateDigest: `digest-${revision}` } },
    control: { revision, phase: 'idle', paused: false },
    narrations: {},
    headPointId: 'p1',
    version: revision,
  },
  commands: [{ text }],
});

const offline = (async () => {
  throw new TypeError('fetch failed: offline');
}) as unknown as typeof fetch;

async function run(mode: 'old' | 'current' | 'online') {
  const store = createLocalProgressStore(new MemoryProgressBackend());
  const online = mode === 'online';
  const sync = createProductSync<Snapshot>({
    store,
    worldId,
    baseUrl: online ? process.env.PROGRESS_SYNC_URL : 'http://127.0.0.1:9/local-progress',
    token: online ? process.env.PROGRESS_SYNC_TOKEN : null,
    // The old behavior is still available for callers that have no session
    // writer; the product does not use it.
    writeLocal: mode === 'old',
    fetchImpl: online ? undefined : offline,
    retry: { attempts: 0, baseDelayMs: 0 },
    sleep: async () => undefined,
  });

  // The session opens the world and persists its first point (revision 1).
  await store.save(worldId, snapshot(1, 'initial'), { expectedRevision: 0 });
  // The page's refresh handler asks sync to save the same snapshot.
  const saved = await sync.save(snapshot(1, 'initial'), { requestId: `page-${mode}` });
  const after = await store.load(worldId);
  let sessionNext: 'ok' | 'conflict';
  try {
    await store.save(worldId, snapshot(2, 'turn-1'), { expectedRevision: 1 });
    sessionNext = 'ok';
  } catch {
    sessionNext = 'conflict';
  }
  return {
    mode,
    outcome: saved.outcome?.status ?? null,
    localSaved: saved.localSaved,
    storedRevisionAfterPageSave: after?.metadata.revision ?? null,
    sessionNextSave: sessionNext,
  };
}

const old = await run('old');
const current = await run('current');
const report: Record<string, unknown> = { old, current };
console.log(JSON.stringify(report, null, 2));

if (old.sessionNextSave !== 'conflict') {
  throw new Error('the old local-writing path no longer reproduces 04\'s blocker; check the store contract');
}
if (current.sessionNextSave !== 'ok' || current.storedRevisionAfterPageSave !== 1) {
  throw new Error('the session-owned store was written by the adapter: 04\'s blocker is not fixed');
}
if (current.outcome !== 'queued') {
  throw new Error(`an offline save should queue, got ${current.outcome}`);
}
console.log('OK: page-style save no longer writes the session-owned store');

if (process.env.PROGRESS_SYNC_URL) {
  // Same sequence, but the upload really reaches the service: the session still
  // owns the store and the snapshot is on the server.
  const online = await run('online');
  console.log(JSON.stringify({ online }, null, 2));
  if (online.sessionNextSave !== 'ok' || online.storedRevisionAfterPageSave !== 1) {
    throw new Error('the online save wrote the session-owned store');
  }
  if (online.outcome !== 'synced') throw new Error(`online save should sync, got ${online.outcome}`);
  console.log('OK: online save uploads without writing the store');
}
