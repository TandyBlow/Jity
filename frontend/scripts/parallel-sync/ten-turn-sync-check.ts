/** Ten consecutive turns on 06's real session, saved like the page saves:
 * five online turns, two saved while offline, a refresh (a new session object
 * on the same store), one reconnect flush, then three more online turns.
 *
 * The storage-layer acceptance for the progress_conflict blocker: no save may
 * write the session store behind the session, the reconnect may only upload
 * descendants of the last synced head, and the final remote head must carry
 * exactly the ten played commands.
 *
 *   PROGRESS_SYNC_URL=http://127.0.0.1:8010 PROGRESS_SYNC_TOKEN=secret \
 *   LANE06_ROOT=../../06-recovery ./node_modules/.bin/jiti \
 *     ./scripts/parallel-sync/ten-turn-sync-check.ts
 *
 * Scripted model (no GPU), no page, no narration-quality claim.
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
  persistence: { revision: number; state: string; blocked: string | null };
  start(): Promise<{ kind: string; reason?: string }>;
  submit(text: string): Promise<{ kind: string; reason?: string }>;
  close(): Promise<void>;
}

interface StoreLike {
  save(worldId: string, snapshot: unknown, options?: Record<string, unknown>): Promise<{ revision: number }>;
  load(worldId: string): Promise<{ snapshot: unknown; metadata: { revision: number } } | null>;
}

function template() {
  const initial = structuredClone(SHORT_STATE.initial) as Record<string, unknown>;
  delete initial.worldId;
  return initial;
}

let narrationCount = 0;
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
          return [1, 2].map((index) => ({
            pointId: `point_${round?.roundId ?? 'round'}_${index}`, kind: 'normal',
            timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } },
            actorIds: ['person_a', 'person_c'],
          }));
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
          narrationCount += 1;
          return `门厅里安静下来，盒盖开着。第${narrationCount}段。`;
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

/** Submit and keep advancing while the run is only paused between rounds. */
async function runTurn(target: SessionLike, text: string): Promise<{ kind: string; reason?: string }> {
  let status = await target.submit(text);
  for (let guard = 0; status.kind === 'await' && guard < 20; guard += 1) {
    status = await target.start();
  }
  return status;
}

const storage = () => {
  const memory = new Map<string, string>();
  return {
    getItem: (key: string) => memory.get(key) ?? null,
    setItem: (key: string, value: string) => { memory.set(key, value); },
    removeItem: (key: string) => { memory.delete(key); },
  };
};

const store = createLocalProgressStore(new MemoryProgressBackend());
const session = await LocalGameSession.create(template(), scriptedModel(), {
  storage: store, sessionId: 'ten_turn', leaseHeartbeat: false,
});
await session.start();
const worldId = session.worldId;
const storageShared = storage();
// One page adapter whose network comes and goes, like a real browser. Two
// adapters over the same storage would each cache their own queue view.
let network = true;
const online = createProductSync<unknown>({
  store: adapter(store),
  worldId,
  baseUrl,
  token,
  storage: storageShared,
  fetchImpl: (async (input: RequestInfo | URL, init?: RequestInit) => {
    if (!network) throw new TypeError('offline');
    return fetch(input, init);
  }) as typeof fetch,
  retry: { attempts: 1, baseDelayMs: 20 },
  sleep: async () => undefined,
});
const setNetwork = (value: boolean) => {
  network = value;
};

const turns = (index: number) => `第${index}回合：我打开盒盖。`;
const savedHeads: string[] = [];
let queuedWhileOffline = 0;
for (let index = 1; index <= 7; index += 1) {
  const submitted = await runTurn(session, turns(index));
  if (submitted.kind === 'error') throw new Error(`turn ${index} failed to submit`);
  if (index === 6) setNetwork(false);
  const saved = await online.save(session.snapshot, { requestId: `ten-${index}-${worldId}` });
  if (saved.localSaved !== false) {
    throw new Error(`turn ${index}: the sync call wrote the session store`);
  }
  if (index <= 5) {
    if (saved.outcome?.status !== 'synced') throw new Error(`turn ${index} not synced: ${saved.outcome?.status}`);
    savedHeads.push(saved.outcome.upload.snapshotId);
  }
  if (index === 6 || index === 7) {
    if (saved.outcome?.status !== 'queued') throw new Error(`turn ${index} not queued: ${saved.outcome?.status}`);
    queuedWhileOffline += 1;
  }
  if (session.persistence.blocked) throw new Error(`turn ${index}: the session save was blocked (${session.persistence.blocked})`);
  const commands = session.snapshot.commands.length;
  if (commands !== index) throw new Error(`turn ${index}: expected ${index} commands, snapshot has ${commands}`);
}

// A refresh while two saves are still queued.
const revisionBefore = session.persistence.revision;
await session.close();
const reopened = await LocalGameSession.open(store, { worldId, initial: template() }, scriptedModel());
if (reopened.created) throw new Error('the refresh started a new world');
if (reopened.session.commandsPlayed.length !== 7) {
  throw new Error(`the refresh kept ${reopened.session.commandsPlayed.length} commands, expected 7`);
}
setNetwork(true);
if (reopened.session.persistence.revision !== revisionBefore) {
  throw new Error(`the refresh changed the local revision: ${revisionBefore} -> ${reopened.session.persistence.revision}`);
}

// Reconnect: the two queued saves must upload as descendants, without conflict.
const flushed = await online.flush();
if (flushed.conflicts > 0) throw new Error(`the reconnect conflicted ${flushed.conflicts} times`);
if (flushed.remaining !== 0) throw new Error(`the reconnect left ${flushed.remaining} queued`);
if (flushed.uploaded < 1) throw new Error('the reconnect uploaded nothing');
const headAfterReconnect = await online.status();
if (headAfterReconnect.relation === 'diverged') throw new Error('the reconnect reported a fork');
const head = (await online.client.head(worldId)).headSnapshotId;
if (!head) throw new Error('no remote head after reconnect');
const headPayload = (await online.read(head)).payload as { commands: string[] };
if (JSON.stringify(headPayload.commands) !== JSON.stringify(reopened.session.commandsPlayed)) {
  throw new Error('the remote head does not carry the seven commands');
}
const graph = await online.client.graph(worldId);
const inside = graph.nodes.filter((node) => node.snapshotId === head || node.parentSnapshotIds.includes(head));
if (!inside.length) throw new Error('the head is not in the graph');

// Three more online turns, then the final head must carry all ten commands.
await reopened.session.start();
for (let index = 8; index <= 10; index += 1) {
  const submitted = await runTurn(reopened.session, turns(index));
  console.log('after refresh turn', index, JSON.stringify(submitted), reopened.session.snapshot.commands.length);
  if (submitted.kind === 'error') throw new Error(`turn ${index} failed after the refresh`);
  if (reopened.session.snapshot.commands.length !== index) {
    throw new Error(`turn ${index} did not add a command (${reopened.session.snapshot.commands.length})`);
  }
  const saved = await online.save(reopened.session.snapshot, { requestId: `ten-${index}-${worldId}` });
  if (saved.outcome?.status !== 'synced') throw new Error(`turn ${index} not synced after the refresh: ${saved.outcome?.status}`);
  if (saved.localSaved !== false) throw new Error(`turn ${index}: the sync call wrote the session store`);
}
const finalHead = (await online.client.head(worldId)).headSnapshotId;
const finalPayload = (await online.read(finalHead!)).payload as { commands: string[] };
const expected = Array.from({ length: 10 }, (_, index) => turns(index + 1));
const report = {
  worldId,
  queuedWhileOffline,
  refreshCommands: reopened.session.commandsPlayed.length,
  reconnect: { uploaded: flushed.uploaded, conflicts: flushed.conflicts, remaining: flushed.remaining },
  finalHead,
  finalCommands: finalPayload.commands.length,
  sameCommands: JSON.stringify(finalPayload.commands) === JSON.stringify(expected),
  sessionBlocked: reopened.session.persistence.blocked,
};
console.log(JSON.stringify(report, null, 2));
if (!report.sameCommands) throw new Error('the final remote head does not match the ten played commands');
if (report.sessionBlocked) throw new Error('the session is blocked');
console.log('OK: ten turns, a refresh with two queued saves, and a clean descendant-only reconnect');
