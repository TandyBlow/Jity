/** Repro: after a refresh, the next command can be accepted but never planned.
 *
 * Create a session, play one turn (the scripted plan has ONE point), close it,
 * reopen it from the same store (what the page does after a reload) and submit
 * a new command. Observed on 06-head 45d5b0d7..4757df61:
 *
 *   submit -> { kind: 'await', reason: 'round_points_exhausted' }
 *   the model is never asked for a pointPlan
 *   record.advance stays open (intentStatus 'pending')
 *   every later submit -> { kind: 'stop', reason: 'turn_in_progress' }
 *
 * With a two-point plan the same sequence completes, and a one-point plan
 * before the refresh also completes, so the restored memory/round state is
 * what changes the outcome. The page has no branch for `await` and no resume
 * control, so the player is stuck.
 *
 *   LANE06_ROOT=../../06-recovery ./node_modules/.bin/jiti \
 *     ./scripts/parallel-sync/refresh-next-turn-repro.ts
 *   EXPECT_OK=1 ...   exits 1 while the stall is present (for 06's fix check)
 *
 * This is 06/05 session territory; 07 reports it, does not fix it.
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
  open(store: unknown, world: Record<string, unknown>, model: unknown): Promise<{ session: SessionLike; created: boolean }>;
};
const createLocalProgressStore = storeModule.createLocalProgressStore as (backend: unknown) => StoreLike;
const MemoryProgressBackend = memoryModule.MemoryProgressBackend as new () => unknown;
const SHORT_STATE = samples.SHORT_STATE as { initial: { worldId?: string } };

interface SessionLike {
  worldId: string;
  snapshot: {
    commands: string[];
    transport: {
      advance: { advanceId: string; intentStatus: string } | null;
      round: { roundId: string; conclusion: unknown } | null;
      points: Record<string, unknown>;
    };
  };
  commandsPlayed: string[];
  start(): Promise<Status>;
  submit(text: string): Promise<Status>;
  close(): Promise<void>;
}

interface Status { kind: string; reason?: string }
interface StoreLike {
  load(worldId: string): Promise<{ snapshot: unknown } | null>;
}

function template() {
  const initial = structuredClone(SHORT_STATE.initial) as Record<string, unknown>;
  delete initial.worldId;
  return initial;
}

function scriptedModel(pointsPerRound: number, tasks: string[]) {
  return {
    async generate(task: string) {
      tasks.push(task);
      switch (task) {
        case 'pointPlan': {
          return Array.from({ length: pointsPerRound }, (_, index) => ({
            pointId: `point_${index + 1}_${tasks.length}`, kind: 'normal',
            timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } },
            actorIds: ['person_a', 'person_c'],
          }));
        }
        case 'action': return { kind: 'act', text: '我打开盒盖。' };
        case 'targets': return { targets: [] };
        case 'reaction': return '林川侧过身。';
        case 'results': return { person_c: '周宁掀开盒盖。' };
        case 'updates': return [{ stage: 'position', changes: {} }];
        case 'continuation': return { kind: 'handback', closedBy: 'model', cancelReason: null };
        case 'narration': return '门厅里安静。';
        default: throw new Error(`unexpected task ${task}`);
      }
    },
  };
}

async function run(pointsPerRound: number) {
  const store = createLocalProgressStore(new MemoryProgressBackend());
  const tasksBefore: string[] = [];
  const session = await LocalGameSession.create(template(), scriptedModel(pointsPerRound, tasksBefore), {
    storage: store, sessionId: 'repro_a', leaseHeartbeat: false,
  });
  await session.start();
  const first = await session.submit('我打开盒盖。');
  const worldId = session.worldId;
  await session.close();

  const tasksAfter: string[] = [];
  const reopened = await LocalGameSession.open(store, { worldId, initial: template() },
    scriptedModel(pointsPerRound, tasksAfter));
  const second = await reopened.session.submit('我踢了一下门框。');
  const third = await reopened.session.submit('我再等一会儿。');
  const advance = reopened.session.snapshot.transport.advance;
  return {
    pointsPerRound,
    firstTurn: first,
    commandsAfterReopen: reopened.session.commandsPlayed,
    secondTurn: second,
    thirdTurn: third,
    plannedAfterReopen: tasksAfter.includes('pointPlan'),
    advanceOpen: advance !== null,
    points: Object.keys(reopened.session.snapshot.transport.points).length,
  };
}

const one = await run(1);
const two = await run(2);
console.log(JSON.stringify({ onePointPlan: one, twoPointPlan: two }, null, 2));

const stalled = one.secondTurn.kind === 'await' && one.thirdTurn.reason === 'turn_in_progress';
console.log(stalled
  ? 'STALLED: after the refresh the new command is accepted but never planned; later submits are refused'
  : 'NO STALL: the command after the refresh completed');
if (two.secondTurn.kind === 'await' || two.thirdTurn.reason === 'turn_in_progress') {
  console.log('NOTE: the two-point plan also stalls; the finding is not specific to the plan size');
}
if (process.env.EXPECT_OK === '1' && stalled) {
  console.error('EXPECT_OK=1 and the stall is still present');
  process.exit(1);
}
