/** The page's "keep the other device's copy" branch, on 06's real store.
 *
 * A plays turn 1 and uploads it. B restores that copy and plays a different
 * turn 2 while offline (queued). A then plays its own turn 2 and uploads it
 * (the head). B reconnects: the queued upload conflicts. The page's branch is
 * emulated exactly: choose('keep-remote'), archive the losing local record
 * under a fork: key, close the session, write the chosen snapshot, reopen.
 * A's copy must be the head and B's losing copy must still be readable from
 * the archive; neither history may absorb the other.
 *
 *   PROGRESS_SYNC_URL=http://127.0.0.1:8010 PROGRESS_SYNC_TOKEN=secret  *   LANE06_ROOT=../../06-recovery ./node_modules/.bin/jiti  *     ./scripts/parallel-sync/page-keep-remote-check.ts
 *
 * Storage check with a scripted model; no page, no quality claim.
 */
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

import { createProductSync } from '../../src/lib/world-engine/local/progress-sync/product';

const baseUrl = process.env.PROGRESS_SYNC_URL;
const token = process.env.PROGRESS_SYNC_TOKEN ?? '';
if (!baseUrl) {
  console.log('SKIP: PROGRESS_SYNC_URL is not set');
  process.exit(0);
}
const lane06 = process.env.LANE06_ROOT
  ?? 'D:/others/Jity/.local/parallel-local-game/worktrees/06-recovery';
const load = async (modulePath: string) =>
  import(pathToFileURL(join(lane06, modulePath)).href) as Promise<Record<string, unknown>>;

const sessionModule = await load('frontend/src/lib/world-engine/local/session.ts');
const storeModule = await load('frontend/src/lib/world-engine/local/persistence/store.ts');
const memoryModule = await load('frontend/src/lib/world-engine/local/persistence/memory.ts');
const samples = await load('frontend/src/lib/world-engine/runtime/b3-short-samples.ts');

const LocalGameSession = sessionModule.LocalGameSession as {
  create(template: unknown, model: unknown, options: Record<string, unknown>): Promise<SessionLike>;
  open(store: unknown, world: Record<string, unknown>, model: unknown): Promise<{ session: SessionLike; created: boolean }>;
};
const createLocalProgressStore = storeModule.createLocalProgressStore as (backend: unknown) => StoreLike;
const MemoryProgressBackend = memoryModule.MemoryProgressBackend as new () => unknown;
const SHORT_STATE = samples.SHORT_STATE as { initial: { worldId?: string } };

interface SessionLike {
  worldId: string;
  snapshot: { commands: string[] };
  commandsPlayed: string[];
  start(): Promise<unknown>;
  submit(text: string): Promise<{ kind: string }>;
  close(): Promise<void>;
}

interface StoreLike {
  save(worldId: string, snapshot: unknown): Promise<{ revision: number }>;
  load(worldId: string): Promise<{ snapshot: unknown; metadata: { revision: number } } | null>;
  backupLegacy(backup: { key: string; sourceKey: string; raw: string; capturedAtEpochMilli: number }): Promise<void>;
  loadLegacyBackup(key: string): Promise<{ key: string; raw: string } | null>;
}

function template() {
  const initial = structuredClone(SHORT_STATE.initial) as Record<string, unknown>;
  delete initial.worldId;
  return initial;
}

function scriptedModel() {
  return {
    async generate(task: string, key: string, input: Record<string, unknown>) {
      const data = input as {
        actor?: string;
        workingState?: { protagonistId: string };
        advance?: { inputText: string | null };
      };
      switch (task) {
        case 'pointPlan': {
          const round = (input as { round?: { roundId?: string } }).round;
          return [{
            pointId: `point_${round?.roundId ?? 'round'}_1`, kind: 'normal',
            timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } },
            actorIds: ['person_a', 'person_c'],
          }];
        }
        case 'action':
          return data.actor === data.workingState?.protagonistId
            ? { kind: 'act', text: data.advance?.inputText ?? '我走到门厅。' }
            : { kind: 'skip' };
        case 'targets':
          return key === 'person_c' ? { targets: [{ targetId: 'person_a' }] } : { targets: [] };
        case 'reaction':
          return '林川侧过身，让开半步。';
        case 'results':
          return { person_c: '周宁掀开盒盖。', person_a: '林川侧过身。' };
        case 'updates':
          return [{ stage: 'position', changes: {} }];
        case 'continuation':
          return { kind: 'handback', closedBy: 'model', cancelReason: null };
        case 'narration':
          return '门厅里安静下来，盒盖开着。';
        default:
          throw new Error(`unexpected task ${task}`);
      }
    },
  };
}

const adapter = (store: StoreLike) => ({
  async load(worldId: string) {
    const record = await store.load(worldId);
    return record ? { snapshot: record.snapshot } : null;
  },
  async save() {
    throw new Error('sync must not write the session store');
  },
});

const storage = () => {
  const memory = new Map<string, string>();
  return {
    getItem: (key: string) => memory.get(key) ?? null,
    setItem: (key: string, value: string) => { memory.set(key, value); },
    removeItem: (key: string) => { memory.delete(key); },
  };
};

const storeA = createLocalProgressStore(new MemoryProgressBackend());
const sessionA = await LocalGameSession.create(template(), scriptedModel(), {
  storage: storeA, sessionId: 'device_a', leaseHeartbeat: false,
});
await sessionA.start();
await sessionA.submit('我打开盒盖。');

// A is a long-lived page: its queue/head live in the same browser storage.
const storageA = storage();
const fetchA = (async (input: RequestInfo | URL, init?: RequestInit) => fetch(input, init)) as typeof fetch;
const syncA = createProductSync<unknown>({
  store: adapter(storeA), worldId: sessionA.worldId, baseUrl, token, storage: storageA,
  retry: { attempts: 1, baseDelayMs: 20 }, sleep: async () => undefined,
});
const firstUpload = await syncA.save(sessionA.snapshot, { requestId: `fork-a1-${sessionA.worldId}` });
if (firstUpload.outcome?.status !== 'synced') throw new Error(`A turn 1 upload failed: ${firstUpload.outcome?.status}`);
const snapA = firstUpload.outcome.upload.snapshotId;

// --- B restores A's copy and plays a different turn 2 while offline ---
const storeB = createLocalProgressStore(new MemoryProgressBackend());
const storageB = storage();
const syncB = createProductSync<unknown>({
  store: adapter(storeB), worldId: sessionA.worldId, baseUrl, token, storage: storageB,
  retry: { attempts: 1, baseDelayMs: 20 }, sleep: async () => undefined,
});
const restored = await syncB.restore();
if (restored.source !== 'remote' || !restored.snapshot) throw new Error('B could not restore A');
await storeB.save(sessionA.worldId, restored.snapshot);
const openedB = await LocalGameSession.open(storeB, { worldId: sessionA.worldId, initial: template() }, scriptedModel());
if (openedB.created) throw new Error('B started a new world');
await openedB.session.start();
const bTurn = await openedB.session.submit('我关上盒盖。');
if (bTurn.kind === 'error') throw new Error('B turn 2 failed');

const offlineB = createProductSync<unknown>({
  store: adapter(storeB), worldId: sessionA.worldId, baseUrl, token, storage: storageB,
  fetchImpl: (async () => { throw new TypeError('offline'); }) as unknown as typeof fetch,
  retry: { attempts: 0, baseDelayMs: 0 }, sleep: async () => undefined,
});
const queuedB = await offlineB.save(openedB.session.snapshot, { requestId: `keep-remote-b-${sessionA.worldId}` });
if (queuedB.outcome?.status !== 'queued') throw new Error(`B offline save not queued: ${queuedB.outcome?.status}`);

// --- A plays and uploads its own second turn; the head moves past B's base ---
const aTurn = await sessionA.submit('我踢了一下门框。');
if (aTurn.kind === 'error') throw new Error('A turn 2 failed');
const syncA2 = createProductSync<unknown>({
  store: adapter(storeA), worldId: sessionA.worldId, baseUrl, token, storage: storageA,
  retry: { attempts: 1, baseDelayMs: 20 }, sleep: async () => undefined,
});
const aUpload = await syncA2.save(sessionA.snapshot, { requestId: `keep-remote-a2-${sessionA.worldId}` });
if (aUpload.outcome?.status !== 'synced') throw new Error(`A turn 2 upload failed: ${aUpload.outcome?.status}`);
const snapA2 = aUpload.outcome.upload.snapshotId;

// --- B reconnects, sees the conflict, and the page chooses "the other copy" ---
const onlineB = createProductSync<unknown>({
  store: adapter(storeB), worldId: sessionA.worldId, baseUrl, token, storage: storageB,
  retry: { attempts: 1, baseDelayMs: 20 }, sleep: async () => undefined,
});
const flushedB = await onlineB.flush();
const conflict = flushedB.conflictList[0];
if (!conflict) throw new Error('B did not conflict; the page choice would never appear');
const before = await onlineB.status();
if (before.relation !== 'diverged') throw new Error(`expected diverged, got ${before.relation}`);

const bLocalBefore = await storeB.load(sessionA.worldId);
if (!bLocalBefore) throw new Error('B lost its local record before the choice');
const backupKey = `fork:${sessionA.worldId}:${Date.now()}`;
const resolved = await onlineB.choose('keep-remote', conflict);
if (!resolved.snapshot) throw new Error('keep-remote returned no snapshot');
// This is the page's order: archive the losing copy, close, write the chosen
// snapshot, then reload into it.
await storeB.backupLegacy({
  key: backupKey,
  sourceKey: `progress:${sessionA.worldId}`,
  raw: JSON.stringify(bLocalBefore.snapshot),
  capturedAtEpochMilli: Date.now(),
});
await openedB.session.close();
await storeB.save(sessionA.worldId, resolved.snapshot.payload);
const reopened = await LocalGameSession.open(storeB, { worldId: sessionA.worldId, initial: template() }, scriptedModel());
if (reopened.created) throw new Error('B reopened as a new world');
await reopened.session.start();

const backup = await storeB.loadLegacyBackup(backupKey);
if (!backup) throw new Error('the losing copy was not archived');
const backupCommands = (JSON.parse(backup.raw) as { commands: string[] }).commands;
const reopenedCommands = reopened.session.commandsPlayed;

console.log(JSON.stringify({
  snapA2,
  headAfter: resolved.head.headSnapshotId,
  chosenStatus: resolved.status,
  bCopyBeforeChoice: bLocalBefore.snapshot && (bLocalBefore.snapshot as { commands: string[] }).commands,
  reopenedCommands,
  archivedBCommands: backupCommands,
}, null, 2));

if (resolved.head.headSnapshotId !== snapA2) throw new Error('the remote copy did not stay the head');
if (JSON.stringify(reopenedCommands) !== JSON.stringify(sessionA.commandsPlayed)) {
  throw new Error(`reopened B does not show A's history: ${JSON.stringify(reopenedCommands)}`);
}
if (reopenedCommands.includes('我关上盒盖。')) throw new Error('the two histories were merged');
if (JSON.stringify(backupCommands) !== JSON.stringify(openedB.session.commandsPlayed)) {
  throw new Error(`the losing copy changed: ${JSON.stringify(backupCommands)}`);
}
if (backupCommands.includes('我踢了一下门框。')) throw new Error('the losing copy absorbed the remote branch');
console.log("OK: keep-remote kept A as head, B reopened onto it, and B's own copy stayed readable in the archive");
