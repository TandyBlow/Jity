/** Repro: a settlement exception leaves the advance open, and the page has no
 * path that resumes it.
 *
 * What the page's submit handler does on a thrown error: it labels the turn
 * failed, sets phase error and stops — it never calls session.start(). What the
 * session actually left behind on 06-head (observed 2026-11-10):
 *
 *   after the throw:   transport.advance = { inputText: <that turn>, intentStatus: 'pending' },
 *                      transport.work != null, commands has the failed sentence
 *   next submit:       { kind: 'stop', reason: 'turn_in_progress' } (refused, input handed back)
 *   a manual start():  { kind: 'stop', reason: 'world_complete' } — the turn finishes
 *
 * So the page says "本回合没有完成" while the session can still commit it, and
 * until something calls start()/cancel() every further command is refused. The
 * error path also does not hand the sentence back, because commandsPlayed grew.
 *
 *   LANE06_ROOT=../../06-recovery ./node_modules/.bin/jiti \
 *     ./scripts/parallel-sync/failed-turn-advance-repro.ts
 *
 * 06's session/page territory; 07 reports it, does not fix it.
 */
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

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
};
const createLocalProgressStore = storeModule.createLocalProgressStore as (backend: unknown) => StoreLike;
const MemoryProgressBackend = memoryModule.MemoryProgressBackend as new () => unknown;
const SHORT_STATE = samples.SHORT_STATE as { initial: { worldId?: string } };

interface Status { kind: string; reason?: string }
interface SessionLike {
  snapshot: {
    commands: string[];
    transport: {
      advance: { advanceId: string; intentStatus: string; inputText?: string } | null;
      work: unknown;
      points: Record<string, unknown>;
      narrations: Record<string, { status: string; text: string | null }>;
    };
  };
  commandsPlayed: string[];
  start(): Promise<Status>;
  submit(text: string): Promise<Status>;
}

interface StoreLike { load(worldId: string): Promise<unknown> }

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
        failResults = false;
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
        case 'narration': return `第${String(key)}点正文。`;
        default: throw new Error(`unexpected task ${task}`);
      }
    },
  };
}

const store = createLocalProgressStore(new MemoryProgressBackend());
const session = await LocalGameSession.create(template(), scriptedModel(), {
  storage: store, sessionId: 'failure_repro', leaseHeartbeat: false,
});
await session.start();
const first = await session.submit('第一句');
failResults = true;
let failure: string | null = null;
try {
  await session.submit('第二句会失败');
} catch (error) {
  failure = error instanceof Error ? error.message : String(error);
}
const afterFailureCommands = [...session.commandsPlayed];
const advance = session.snapshot.transport.advance;
const workOpen = session.snapshot.transport.work != null;
const pointsAfterFailure = Object.keys(session.snapshot.transport.points).length;

// The page's actual next step: the player retries.
const retry = await session.submit('第二句会失败');

// A manual start() is what the page never does.
const resumed = await session.start();
const pointsAfterResume = Object.keys(session.snapshot.transport.points).length;
const narration = Object.values(session.snapshot.transport.narrations ?? {})
  .filter((entry) => entry.status === 'ready').length;
const report = {
  firstTurn: first,
  failure,
  commandsAfterFailure: afterFailureCommands,
  advanceAfterFailure: advance,
  workOpen,
  pointsAfterFailure,
  retrySubmit: retry,
  manualStart: resumed,
  pointsAfterResume,
  readyNarrations: narration,
  commandsPlayed: session.commandsPlayed,
};
console.log(JSON.stringify(report, null, 2));

if (!failure) throw new Error('the model error did not propagate');
if (!advance) throw new Error('the advance was not left open (the finding changed)');
if (retry.reason !== 'turn_in_progress') throw new Error(`the retry was not refused: ${JSON.stringify(retry)}`);
if (resumed.kind === 'error') throw new Error('start() did not finish the turn');
if (pointsAfterResume <= pointsAfterFailure) {
  console.log('NOTE: start() concluded without committing a new point');
}
console.log('OBSERVED: the failed turn stays open, retries are refused, and start() completes it while the page says it failed');
