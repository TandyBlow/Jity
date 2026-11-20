/** Repro: after a failed + cancelled turn, the restored history pairs inputs
 * with the wrong narration.
 *
 * Sequence on 06-head c1027684 (same behaviour on cef95c7e):
 *   1. turn 1 commits;
 *   2. turn 2's settlement throws; the page must cancel it (cancel() concludes
 *      the round without a point) — the failed sentence stays in commands;
 *   3. turn 3 commits normally.
 *
 * snapshot.commands = ['第一句', '第二句会失败', '第三句']
 * player points     = [point_round_3_1 (turn 1), point_round_17_1 (turn 3)]
 *
 * restoredEntries() pairs by list index, so it shows:
 *   第一句         <-> turn 1 text      (right)
 *   第二句会失败   <-> turn 3 text      (WRONG: the third command's narration)
 *   第三句         -> unfinished, ''    (WRONG: it did commit)
 *
 * The page's live view is right; only the restored view is wrong, because a
 * command that never produced a point shifts every later pair. The checklist
 * asks for entriesAfter == entriesBefore (input+text per turn).
 *
 *   LANE06_ROOT=../../06-recovery ./node_modules/.bin/jiti \
 *     ./scripts/parallel-sync/failed-turn-history-mapping-repro.ts
 *
 * 06's history/transport territory; 07 reports it, does not fix it.
 */
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const lane06 = process.env.LANE06_ROOT
  ?? 'D:/others/Jity/.local/parallel-local-game/worktrees/06-recovery';
const load = async (modulePath: string) =>
  import(pathToFileURL(join(lane06, modulePath)).href) as Promise<Record<string, unknown>>;

const sessionModule = await load('frontend/src/lib/world-engine/local/session.ts');
const historyModule = await load('frontend/src/lib/world-engine/local/history.ts');
const storeModule = await load('frontend/src/lib/world-engine/local/persistence/store.ts');
const memoryModule = await load('frontend/src/lib/world-engine/local/persistence/memory.ts');
const samples = await load('frontend/src/lib/world-engine/runtime/b3-short-samples.ts');

const LocalGameSession = sessionModule.LocalGameSession as {
  create(template: unknown, model: unknown, options: Record<string, unknown>): Promise<SessionLike>;
};
const restoredEntries = historyModule.restoredEntries as (snapshot: unknown) => Array<{
  input: string; text: string; unfinished?: boolean;
}>;
const createLocalProgressStore = storeModule.createLocalProgressStore as (backend: unknown) => unknown;
const MemoryProgressBackend = memoryModule.MemoryProgressBackend as new () => unknown;
const SHORT_STATE = samples.SHORT_STATE as { initial: { worldId?: string } };

interface SessionLike {
  snapshot: {
    commands: string[];
    transport: {
      points: Record<string, { id: string; sequence: number; advanceId: string; roundId: string }>;
      narrations: Record<string, { status: string; text: string | null }>;
    };
  };
  commandsPlayed: string[];
  start(): Promise<{ kind: string; reason?: string }>;
  submit(text: string): Promise<{ kind: string; reason?: string }>;
  cancel(reason?: string): Promise<{ kind: string; reason?: string }>;
}

function template() {
  const initial = structuredClone(SHORT_STATE.initial) as Record<string, unknown>;
  delete initial.worldId;
  return initial;
}

let failResults = false;
function scriptedModel() {
  return {
    async generate(task: string, key: string, input: Record<string, unknown>) {
      if (task === 'results' && failResults) {
        throw new Error('settlement_failed:results:simulated');
      }
      switch (task) {
        case 'pointPlan': {
          const round = (input as { round?: { roundId?: string } }).round;
          return [{
            pointId: `point_${round?.roundId ?? 'round'}_1`, kind: 'normal',
            timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } },
            actorIds: ['person_a', 'person_c'],
          }];
        }
        case 'action': return { kind: 'act', text: '我打开盒盖。' };
        case 'targets': return { targets: [] };
        case 'reaction': return '林川侧过身。';
        case 'results': return { person_c: '周宁掀开盒盖。' };
        case 'updates': return [{ stage: 'position', changes: {} }];
        case 'continuation': return { kind: 'handback', closedBy: 'model', cancelReason: null };
        case 'narration': {
          const pointId = (input as { pointId?: string }).pointId ?? String(key);
          return `对应${pointId}的正文。`;
        }
        default: throw new Error(`unexpected task ${task}`);
      }
    },
  };
}

const store = createLocalProgressStore(new MemoryProgressBackend());
const session = await LocalGameSession.create(template(), scriptedModel(), {
  storage: store, sessionId: 'mapping_repro', leaseHeartbeat: false,
});
await session.start();
await session.submit('第一句');
failResults = true;
let failure: string | null = null;
try {
  await session.submit('第二句会失败');
} catch (error) {
  failure = error instanceof Error ? error.message : String(error);
}
const cancelled = await session.cancel('player_abort');
failResults = false;
await session.submit('第三句');

const points = Object.values(session.snapshot.transport.points)
  .sort((left, right) => left.sequence - right.sequence);
const entries = restoredEntries(session.snapshot);
const report = {
  failure,
  cancelled,
  commands: session.commandsPlayed,
  points: points.map((point) => ({ id: point.id, advanceId: point.advanceId, roundId: point.roundId })),
  narrationByPoint: Object.fromEntries(points.map((point) => [
    point.id, session.snapshot.transport.narrations?.[point.id]?.text ?? null,
  ])),
  restoredEntries: entries.map((entry) => ({ input: entry.input, text: entry.text, unfinished: entry.unfinished ?? false })),
};
console.log(JSON.stringify(report, null, 2));

if (!failure) throw new Error('the model error did not propagate');
if (points.length !== 2) throw new Error(`expected 2 committed points, got ${points.length}`);
const pairs = entries.filter((entry) => !entry.unfinished);
const turn1 = pairs.find((entry) => entry.input === '第一句');
const turn3 = pairs.find((entry) => entry.input === '第三句');
const shift = pairs.find((entry) => entry.input === '第二句会失败');
if (!turn1 || !shift) throw new Error('the expected mispairing did not occur (the finding changed)');
if (turn1.text !== report.narrationByPoint[points[0].id]) throw new Error('turn 1 text is wrong too');
if (shift.text === report.narrationByPoint[points[1].id]) {
  console.log('OBSERVED: the third command\'s narration is shown under the failed sentence, and no entry has 第三句');
} else {
  console.log('OBSERVED: entries are not paired by list index any more');
}
if (turn3) console.log('NOTE: 第三句 now has its own entry');
