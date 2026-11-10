/** A real fork between two devices, with 06's real session snapshots.
 *
 * A plays turn 1 and uploads it. B restores that copy, plays a different turn 2
 * and uploads it (the active head). A - which has not seen B's turn - plays its
 * own turn 2 against the old copy, saves offline, and reconnects: the upload
 * must come back as a conflict, not overwrite B. The player then explicitly
 * keeps the local copy as a fork; both branches must stay readable and the
 * chosen one becomes the head.
 *
 *   PROGRESS_SYNC_URL=http://127.0.0.1:8010 PROGRESS_SYNC_TOKEN=secret \
 *   LANE06_ROOT=../../06-recovery ./node_modules/.bin/jiti \
 *     ./scripts/parallel-sync/fork-session-check.ts
 *
 * Storage and lineage check with a scripted model; no page, no quality claim.
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

// --- B restores A's copy and plays a different second turn ---
const storeB = createLocalProgressStore(new MemoryProgressBackend());
const syncB = createProductSync<unknown>({
  store: adapter(storeB), worldId: sessionA.worldId, baseUrl, token, storage: storage(),
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
const bUpload = await syncB.save(openedB.session.snapshot, { requestId: `fork-b2-${sessionA.worldId}` });
if (bUpload.outcome?.status !== 'synced') throw new Error(`B upload failed: ${bUpload.outcome?.status}`);
const snapB = bUpload.outcome.upload.snapshotId;
if (!bUpload.outcome.upload.parentSnapshotIds.includes(snapA)) throw new Error('B did not descend from A');

// --- A, still on the old copy, plays its own second turn offline ---
const aTurn = await sessionA.submit('我踢了一下门框。');
if (aTurn.kind === 'error') throw new Error('A turn 2 failed');
const offline = createProductSync<unknown>({
  store: adapter(storeA), worldId: sessionA.worldId, baseUrl, token, storage: storageA,
  fetchImpl: (async () => { throw new TypeError('offline'); }) as unknown as typeof fetch,
  retry: { attempts: 0, baseDelayMs: 0 }, sleep: async () => undefined,
});
const queued = await offline.save(sessionA.snapshot, { requestId: `fork-a2-${sessionA.worldId}` });
if (queued.outcome?.status !== 'queued') throw new Error(`A offline save not queued: ${queued.outcome?.status}`);

// Reconnect: the queued upload must conflict with B, not overwrite it.
const online = createProductSync<unknown>({
  store: adapter(storeA), worldId: sessionA.worldId, baseUrl, token, storage: storageA,
  // Same requestId bookkeeping as the offline adapter, but reachable now.
  fetchImpl: fetchA, retry: { attempts: 1, baseDelayMs: 20 }, sleep: async () => undefined,
});
const flushed = await online.flush();
const conflict = flushed.conflictList[0];
const before = await online.status();
const report = {
  worldId: sessionA.worldId,
  snapA,
  snapB,
  flush: { uploaded: flushed.uploaded, conflicts: flushed.conflicts, remaining: flushed.remaining },
  relation: before.relation,
  conflictBranches: conflict?.branches ?? null,
  aCommands: sessionA.commandsPlayed,
  bCommands: openedB.session.commandsPlayed,
};
console.log(JSON.stringify(report, null, 2));
if (!conflict) throw new Error('no conflict was reported: B would have been overwritten');
if (before.relation !== 'diverged') throw new Error(`expected diverged, got ${before.relation}`);
if (!(conflict.branches ?? []).includes(snapB)) throw new Error('the conflict does not list the remote branch');

// --- The player explicitly keeps the local copy as a fork ---
await sessionA.close();
const chosen = await online.choose('keep-local-fork', conflict);
const headAfter = chosen.head;
const rereadA = await online.read(headAfter.headSnapshotId ?? '');
const rereadB = await online.read(snapB);
const rereadACommands = (rereadA.payload as { commands: string[] }).commands;
const rereadBCommands = (rereadB.payload as { commands: string[] }).commands;
console.log(JSON.stringify({
  chosenStatus: chosen.status,
  headAfter: headAfter.headSnapshotId,
  aCopy: rereadACommands,
  bCopy: rereadBCommands,
}, null, 2));
if (headAfter.headSnapshotId === snapB) throw new Error('the chosen fork did not become the head');
if (JSON.stringify(rereadACommands) !== JSON.stringify(sessionA.commandsPlayed)) {
  throw new Error(`A's copy changed: ${JSON.stringify(rereadACommands)}`);
}
if (JSON.stringify(rereadBCommands) !== JSON.stringify(openedB.session.commandsPlayed)) {
  throw new Error(`B's copy changed or was deleted: ${JSON.stringify(rereadBCommands)}`);
}
if (rereadBCommands.includes('我踢了一下门框。')) throw new Error('the two branches were merged without a choice');
console.log('OK: the reconnect conflicted, both copies stayed readable, and the explicit fork became the head');
