/** Sweep several settled points of the public free-day world through the
 * composer inside lane 04's constrained candidate.
 *
 * Each scenario is a real state pair produced by the browser kernel; the
 * printed text is what a player would read. The last line of every block says
 * whether every beat came from this composer (`program:prose-composer`) or
 * whether 04 had to fall back to its own realizer.
 *
 *   LANE04_ROOT=../04-settlement ./node_modules/.bin/jiti \
 *     ./scripts/candidate-prose/sweep-free-day.ts
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

import { createBeatComposer } from '../../src/lib/world-engine/local/narration-candidates/prose-composer/index';

const lane04 = process.env.LANE04_ROOT ?? join(process.cwd(), '..', '..', '04-settlement');
const load = async (modulePath: string) => import(pathToFileURL(join(lane04, modulePath)).href) as Promise<Record<string, unknown>>;

const stateModule = await load('frontend/src/lib/world-engine/local/state.ts');
const candidateModule = await load('frontend/src/lib/world-engine/local/narration-candidates/constrained/index.ts');
const buildInitialState = stateModule.buildInitialState as (initial: unknown) => unknown;
const applyPoint = stateModule.applyPoint as (state: unknown, point: unknown) => unknown;
const stateDigest = stateModule.stateDigest as (state: unknown) => Promise<string>;
const generateCandidate = candidateModule.generateCandidate as (input: unknown) => Promise<Record<string, unknown>>;

const world = JSON.parse(readFileSync(
  join(process.cwd(), '..', 'data', 'worlds', 'dragon-raja-free-day.world.json'),
  'utf8',
)) as { worldId: string; initial: unknown };

type Point = {
  name: string;
  time: { amount: number; unit: string } | null;
  deltas: Record<string, Record<string, unknown>>;
  priorText?: string;
  requireTime?: boolean;
};

const points: Point[] = [
  {
    name: 'walk to the shed',
    time: { amount: 3, unit: 'minute' },
    deltas: { lu: { entityId: 'lu', positionSet: { containerId: 'shed', slotId: 'slot_counter', relativeTo: null } } },
  },
  {
    name: 'two people move, one stays',
    time: { amount: 1, unit: 'minute' },
    deltas: {
      nono: { entityId: 'nono', positionSet: { containerId: 'red_rally', slotId: null, relativeTo: null } },
      fingel: { entityId: 'fingel', positionSet: { containerId: 'lane', slotId: 'slot_entry', relativeTo: null } },
    },
  },
  {
    name: 'task achieved and sanity drops',
    time: { amount: 2, unit: 'minute' },
    deltas: {
      lu: { entityId: 'lu', sanitySet: 40, tasksAchieved: ['task_lu_goggles'] },
    },
  },
  {
    name: 'appearance and personality change',
    time: { amount: 5, unit: 'minute' },
    deltas: {
      lu: {
        entityId: 'lu',
        appearanceChanges: [{ id: 'sweep_a1', text: '护目镜的带子在手腕上绕了一圈。', supersedes: [] }],
        personalityChanges: [{ id: 'sweep_p1', text: '说话前先看一眼对方的鞋，再决定要不要开玩笑。', supersedes: [] }],
      },
    },
  },
  {
    name: 'battery moves out of a pocket',
    time: { amount: 1, unit: 'minute' },
    deltas: {
      camera_battery: { entityId: 'camera_battery', positionSet: { containerId: 'supply_counter', slotId: 'slot_top', relativeTo: null } },
    },
  },
  {
    name: 'subtask added',
    time: { amount: 1, unit: 'minute' },
    deltas: {
      lu: {
        entityId: 'lu',
        subtasksAdded: [{
          id: 'sweep_t1', ownerId: 'lu', parentTaskId: 'task_lu_match',
          goal: '把护目镜的镜片对着光再检查一遍', status: 'pending',
        }],
      },
    },
  },
  {
    name: 'time only, nobody moves',
    time: { amount: 2, unit: 'minute' },
    deltas: {},
  },
  {
    name: 'campus move with two witnesses',
    time: { amount: 4, unit: 'minute' },
    deltas: {
      lu: { entityId: 'lu', positionSet: { containerId: 'yard', slotId: null, relativeTo: null } },
      tang: { entityId: 'tang', positionSet: { containerId: 'east_arcade', slotId: null, relativeTo: null } },
    },
  },
  {
    name: 'two moves in opposite directions',
    time: { amount: 2, unit: 'minute' },
    deltas: {
      lu: { entityId: 'lu', positionSet: { containerId: 'shed', slotId: 'slot_counter', relativeTo: null } },
      fingel: { entityId: 'fingel', positionSet: { containerId: 'lane', slotId: 'slot_entry', relativeTo: null } },
    },
  },
  {
    name: 'sanity recovers',
    time: { amount: 3, unit: 'minute' },
    deltas: { lu: { entityId: 'lu', sanitySet: 47 } },
  },
  {
    name: 'item appearance changes in view',
    time: { amount: 2, unit: 'minute' },
    deltas: {
      camera_battery: {
        entityId: 'camera_battery',
        appearanceChanges: [{ id: 'sweep_item_a1', text: '包装被拆开了，外壳上留着一道指甲划痕。', supersedes: [] }],
      },
    },
  },
  {
    name: 'complex point: task, subtask, personality, sanity',
    time: { amount: 6, unit: 'minute' },
    deltas: {
      lu: {
        entityId: 'lu',
        sanitySet: 38,
        tasksAchieved: ['task_lu_goggles'],
        subtasksAdded: [{
          id: 'sweep_t2', ownerId: 'lu', parentTaskId: 'task_lu_match',
          goal: '把护目镜的镜片对着光再检查一遍', status: 'pending',
        }],
        personalityChanges: [{ id: 'sweep_p2', text: '不再把选择推给别人。', supersedes: [] }],
      },
    },
  },
  {
    name: 'one second passes',
    time: { amount: 1, unit: 'second' },
    deltas: {},
  },
  {
    name: 'continuation after a briefing',
    time: { amount: 1, unit: 'minute' },
    deltas: { nono: { entityId: 'nono', positionSet: { containerId: 'red_rally', slotId: null, relativeTo: null } } },
    priorText: '「红方在集结点，蓝方守着钟楼。」诺诺开口，「你要过去，别走正中。」\n\n「走哪边？」路明非问。',
  },
];

const baseState = buildInitialState(world.initial);
const composer = createBeatComposer();
const loggingComposer = (async (request: Parameters<typeof composer>[0], options: Parameters<typeof composer>[1]) => {
  const result = await composer(request, options);
  console.log(`  [composer] ${request.beat.id} seed=${String(request.beat.seed)} ${JSON.stringify(result.text)}`);
  return result;
}) as typeof composer;

for (const [index, point] of points.entries()) {
  const pointRecord = {
    worldId: world.worldId,
    id: `sweep_${index + 1}`,
    sequence: index + 1,
    kind: 'normal',
    previousPointId: index === 0 ? 'root' : `sweep_${index}`,
    roundId: `sweep_r${index + 1}`,
    advanceId: `sweep_a${index + 1}`,
    trigger: 'player',
    linkedFromPointId: null,
    timeAdvance: point.time ? { boundary: 'elapsed', duration: point.time } : null,
    entityDeltas: point.deltas,
  };
  const after = applyPoint(baseState, pointRecord);
  const digest = await stateDigest(after);
  const result = await generateCandidate({
    engine: undefined,
    committed: {
      anchor: { worldId: world.worldId, pointId: pointRecord.id, version: 1, stateDigest: digest, previousPointId: 'root' },
      state: after,
      beforeState: baseState,
      timeAdvance: pointRecord.timeAdvance,
      entityDeltas: pointRecord.entityDeltas,
      facts: [],
    },
    priorText: point.priorText ?? null,
    onProgress: () => {},
    policy: {
      mode: 'program',
      composer: loggingComposer,
      minChars: point.time ? 40 : 16,
      maxChars: 800,
      requireTime: point.requireTime ?? Boolean(point.time),
      sanityStyle: 'direction',
    },
  });
  const composers = (result.composers as string[]) ?? [];
  // 'program' is lane 04's own realizer; our composer reports 'program:<name>'.
  const fallbacks = composers.filter((name) => name === 'program');
  const issues = (result.issues as unknown[]) ?? [];
  console.log(`\n===== ${index + 1}. ${point.name}`);
  console.log(`accepted=${String(result.accepted)} status=${String(result.status)} chars=${[...String(result.text)].length}`);
  console.log(String(result.text));
  if (issues.length) console.log('ISSUES', JSON.stringify(issues));
  for (const attempt of (result.rawAttempts as Array<Record<string, unknown>>) ?? []) {
    console.log(`  - ${String(attempt.beatId)} [${String(attempt.source)}] ${JSON.stringify(attempt.text)}`);
  }
  console.log(fallbacks.length
    ? `!! ${fallbacks.length} beat(s) fell back to lane 04's realizer`
    : 'all beats from prose-composer');
}
