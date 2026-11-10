/** Two devices, 06's real session and store, one real progress service.
 *
 * A plays a turn and uploads it. B has never seen this world: it restores the
 * remote copy, writes it into its own store, and opens a session from it. B
 * must see the same played command and the same prose, and its own first save
 * must be a child of A's snapshot rather than a fresh root.
 *
 *   PROGRESS_SYNC_URL=http://127.0.0.1:8010 PROGRESS_SYNC_TOKEN=secret \
 *   LANE06_ROOT=../../06-recovery ./node_modules/.bin/jiti \
 *     ./scripts/parallel-sync/two-device-session-check.ts
 *
 * Not a page run and not a quality claim: it checks storage and lineage.
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
  snapshot: unknown;
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

/** What the page would show: player points with ready prose. */
function history(snapshot: unknown) {
  const transport = (snapshot as {
    transport: {
      points: Record<string, { id?: string; trigger: string }>;
      narrations: Record<string, { status: string; text: string | null }>;
    };
    commands: string[];
  }).transport;
  const points = Object.values(transport.points ?? {}).filter((point) => point.trigger === 'player');
  return {
    commands: (snapshot as { commands: string[] }).commands,
    points: points.length,
    prose: points.map((point) => transport.narrations?.[point.id ?? '']?.text ?? null),
    ready: points.filter((point) => transport.narrations?.[point.id ?? '']?.status === 'ready').length,
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

// --- device A: one turn, uploaded ---
const storeA = createLocalProgressStore(new MemoryProgressBackend());
const sessionA = await LocalGameSession.create(template(), scriptedModel(), {
  storage: storeA, sessionId: 'device_a', leaseHeartbeat: false,
});
await sessionA.start();
await sessionA.submit('我打开盒盖。');
const aHistory = history(sessionA.snapshot);
const syncA = createProductSync<unknown>({
  store: adapter(storeA), worldId: sessionA.worldId, baseUrl, token, storage: null,
  retry: { attempts: 2, baseDelayMs: 50 }, sleep: async () => undefined,
});
const uploaded = await syncA.save(sessionA.snapshot, { requestId: `two-device-a-${sessionA.worldId}` });
if (uploaded.outcome?.status !== 'synced') throw new Error(`A upload failed: ${uploaded.outcome?.status}`);
const aSnapshotId = uploaded.outcome.upload.snapshotId;

// --- device B: no local save, restore the remote copy ---
const storeB = createLocalProgressStore(new MemoryProgressBackend());
const syncB = createProductSync<unknown>({
  store: adapter(storeB), worldId: sessionA.worldId, baseUrl, token, storage: null,
  retry: { attempts: 2, baseDelayMs: 50 }, sleep: async () => undefined,
});
const restored = await syncB.restore();
if (restored.source !== 'remote' || !restored.snapshot) throw new Error('B did not restore from the remote head');
const storedB = await storeB.save(sessionA.worldId, restored.snapshot);
const opened = await LocalGameSession.open(storeB, { worldId: sessionA.worldId, initial: template() }, scriptedModel());
const bHistory = history(opened.session.snapshot);

const report = {
  worldId: sessionA.worldId,
  a: aHistory,
  aSnapshotId,
  bCreated: opened.created,
  bStoreRevision: storedB.revision,
  b: bHistory,
  bCommandsPlayed: opened.session.commandsPlayed,
};
console.log(JSON.stringify(report, null, 2));

if (opened.created) throw new Error('B started a new world instead of opening the restored record');
if (JSON.stringify(bHistory.commands) !== JSON.stringify(aHistory.commands)) throw new Error('B lost the played commands');
if (bHistory.points !== aHistory.points || bHistory.ready !== aHistory.ready) throw new Error('B lost points or ready prose');
if (JSON.stringify(bHistory.prose) !== JSON.stringify(aHistory.prose)) throw new Error('B shows different prose');
if (JSON.stringify(opened.session.commandsPlayed) !== JSON.stringify(aHistory.commands)) throw new Error('B commandsPlayed differs');

// B's own next save goes to the same lineage: one parent, and it is A's upload.
await opened.session.close();
const bTurn = await (async () => {
  const s = opened.session as SessionLike;
  await s.start();
  return s.submit('我关上盒盖。');
})();
if (bTurn.kind === 'error') throw new Error('B could not play a turn');
const uploadedB = await syncB.save(opened.session.snapshot, { requestId: `two-device-b-${sessionA.worldId}` });
if (uploadedB.outcome?.status !== 'synced') throw new Error(`B upload failed: ${uploadedB.outcome?.status}`);
if (!uploadedB.outcome.upload.parentSnapshotIds.includes(aSnapshotId)) {
  throw new Error(`B's upload is not a child of A: ${JSON.stringify(uploadedB.outcome.upload.parentSnapshotIds)}`);
}
const bAfter = history(opened.session.snapshot);
if (bAfter.commands.length !== aHistory.commands.length + 1) throw new Error('B lost history when adding a turn');
console.log('OK: B restored A\'s world with its prose, and B\'s new turn descends from A\'s snapshot');
