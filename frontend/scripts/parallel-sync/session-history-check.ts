/** Run 06's real session + store with a page-style sync save in between, then
 * restore like a refresh and count what the player would see.
 *
 * 04's blocker was a save conflict, so this check is about the storage layer,
 * not the model: a scripted model answers every task (same shape as 06's own
 * recovery tests), one player turn commits, the page callback calls
 * sync.save(snapshot), the session closes, and a new session is opened from the
 * same store.
 *
 *   LANE06_ROOT=../../06-recovery ./node_modules/.bin/jiti \
 *     ./scripts/parallel-sync/session-history-check.ts
 *
 * It asserts: the store revision did not move because of the sync call, the
 * restored session has the played command, the restored point has ready prose,
 * and the narration text is the one the scripted model produced.
 */
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

import { createProductSync } from '../../src/lib/world-engine/local/progress-sync/product';

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
  restoreFromStore(store: unknown, worldId: string, model: unknown, options: Record<string, unknown>): Promise<SessionLike | null>;
  open(store: unknown, args: Record<string, unknown>, model: unknown): Promise<{ session: SessionLike; created: boolean }>;
};
const createLocalProgressStore = storeModule.createLocalProgressStore as (backend: unknown) => StoreLike;
const MemoryProgressBackend = memoryModule.MemoryProgressBackend as new () => unknown;
const SHORT_STATE = samples.SHORT_STATE as { initial: { worldId?: string } };

interface SessionLike {
  worldId: string;
  snapshot: { transport: { points: Record<string, { trigger: string; sequence: number }>; narrations: Record<string, { status: string; text: string | null }> } ; commands: string[] };
  commandsPlayed: string[];
  start(): Promise<unknown>;
  submit(text: string): Promise<{ kind: string; reason?: string }>;
  close(): Promise<void>;
  persistence: { revision: number; state: string };
}

function playerPointsOf(target: SessionLike) {
  return Object.values(target.snapshot.transport.points ?? {}).filter((point) => point.trigger === 'player');
}

function playerProse(target: SessionLike): (string | null)[] {
  return playerPointsOf(target).map((point) => {
    const id = (point as { id?: string }).id ?? '';
    return target.snapshot.transport.narrations?.[id]?.text ?? null;
  });
}

interface StoreLike {
  load(worldId: string): Promise<{ metadata: { revision: number }; snapshot: { commands: string[]; transport: unknown } } | null>;
}

function template() {
  const initial = structuredClone(SHORT_STATE.initial) as Record<string, unknown>;
  delete initial.worldId;
  return initial;
}

/** The same task answers 06's own recovery test uses. */
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
          return key === 'p1' ? '门厅里安静下来，盒盖开着。' : '走廊里很安静，盒子还盖着。';
        default:
          throw new Error(`unexpected task ${task}`);
      }
    },
  };
}

const store = createLocalProgressStore(new MemoryProgressBackend());
const session = await LocalGameSession.create(template(), scriptedModel(), {
  storage: store, sessionId: 'tab_a', leaseHeartbeat: false, leaseTtlMs: 60_000, roll: () => 13,
});
await session.start();
const submitted = await session.submit('我打开盒盖。');
if (submitted.kind === 'error') throw new Error(`submit failed: ${JSON.stringify(submitted)}`);
const revisionAfterTurn = session.persistence.revision;

const sync = createProductSync<unknown>({
  store: {
    async load(worldId: string) {
      const record = await store.load(worldId);
      return record ? { snapshot: record.snapshot } : null;
    },
    async save() {
      throw new Error('the page-style save must not write the session store');
    },
  },
  worldId: session.worldId,
  baseUrl: 'http://127.0.0.1:9/local-progress',
  fetchImpl: (async () => { throw new TypeError('offline'); }) as unknown as typeof fetch,
  retry: { attempts: 0, baseDelayMs: 0 },
  sleep: async () => undefined,
});
const pageSave = await sync.save(session.snapshot, { requestId: `history-${session.worldId}` });
if (pageSave.localSaved !== false) throw new Error('page-style save wrote the store');
if (pageSave.outcome?.status !== 'queued') throw new Error(`expected a queued offline upload, got ${pageSave.outcome?.status}`);

const storedAfterPageSave = await store.load(session.worldId);
if (!storedAfterPageSave) throw new Error('no saved record');
if (storedAfterPageSave.metadata.revision !== revisionAfterTurn) {
  throw new Error(`the sync call moved the revision: ${revisionAfterTurn} -> ${storedAfterPageSave.metadata.revision}`);
}

const proseBeforeRefresh = playerProse(session);

// A refresh: the old tab is gone (it releases the writer lease), and a brand
// new session object opens the same store.
await session.close();
const reopened = await LocalGameSession.open(store, { worldId: session.worldId, initial: template() }, scriptedModel());
const restored = reopened.session;
const playerPoints = playerPointsOf(restored);
const ready = playerPoints.filter((point) => {
  const id = (point as { id?: string }).id ?? '';
  const narration = restored.snapshot.transport.narrations?.[id];
  return narration?.status === 'ready' && Boolean(narration.text);
});
const report = {
  submitted: submitted.kind,
  revisionAfterTurn,
  revisionAfterPageSave: storedAfterPageSave.metadata.revision,
  commandsPlayed: restored.commandsPlayed,
  playerPoints: playerPoints.length,
  pointsWithReadyProse: ready.length,
  prose: playerProse(restored),
  proseBeforeRefresh,
  pendingWork: Boolean((restored.snapshot.transport as { work?: unknown }).work),
};
console.log(JSON.stringify(report, null, 2));

if (report.commandsPlayed.length !== 1) throw new Error('the played command did not survive the refresh');
if (report.playerPoints !== 1) throw new Error(`expected 1 player point, got ${report.playerPoints}`);
if (report.pointsWithReadyProse !== 1) throw new Error('the committed prose is not ready after the refresh');
if (JSON.stringify(report.prose) !== JSON.stringify(proseBeforeRefresh)) {
  throw new Error(`the restored prose changed: ${JSON.stringify(proseBeforeRefresh)} -> ${JSON.stringify(report.prose)}`);
}
if (report.pendingWork) throw new Error('the restored session has a half-settled point');
console.log('OK: one played turn and its prose survive a page-style sync save and a refresh');
