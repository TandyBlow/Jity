/** Run this composer inside lane 04's constrained candidate.
 *
 * Lane 04 owns the fact projection, the beat plan and the per-beat gate. This
 * script builds one real point with the browser kernel, projects the scene,
 * injects `createBeatComposer()` through `policy.composer`, and prints:
 *   - the accepted text,
 *   - every beat's text and the gate's issues,
 *   - the progress events 04 emitted.
 *
 * Lane 04's branch is a separate worktree, so the import path is explicit:
 *   LANE04_ROOT=D:/.../worktrees/04-settlement ./node_modules/.bin/jiti \
 *     ./scripts/candidate-prose/run-04-beats.ts
 *
 * The default assumes the usual layout (`worktrees/04-settlement` next to
 * `worktrees/07-sync`). Nothing here is imported by the product build.
 */
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

import {
  createBeatComposer,
} from '../../src/lib/world-engine/local/narration-candidates/prose-composer/index';

const lane04 = process.env.LANE04_ROOT
  ?? join(process.cwd(), '..', '..', '04-settlement');

async function load(modulePath: string): Promise<Record<string, unknown>> {
  try {
    return await import(pathToFileURL(join(lane04, modulePath)).href) as Record<string, unknown>;
  } catch (error) {
    console.error(`Cannot import lane 04 from ${lane04}. Set LANE04_ROOT to its worktree.`);
    throw error;
  }
}

const stateModule = await load('frontend/src/lib/world-engine/local/state.ts');
const candidateModule = await load('frontend/src/lib/world-engine/local/narration-candidates/constrained/index.ts');
const buildInitialState = stateModule.buildInitialState as (initial: unknown) => unknown;
const applyPoint = stateModule.applyPoint as (state: unknown, point: unknown) => unknown;
const stateDigest = stateModule.stateDigest as (state: unknown) => Promise<string>;
const generateCandidate = candidateModule.generateCandidate as (input: unknown) => Promise<Record<string, unknown>>;

const initial = {
  engineVersion: 'world-engine-v1', schemaVersion: 1, worldId: 'world_demo', protagonistId: 'lu',
  initialTime: { calendar: 'gregorian', dateTime: '2026-03-01T10:00:00', instantOrdinal: 0 },
  locations: {
    lane: { id: 'lane', name: '西侧服务巷', parentLocationId: null, initialAppearance: '巷口的黄黑绳已放下，右墙贴着赛区图。', slots: [] },
    shed: { id: 'shed', name: '器材棚', parentLocationId: 'lane', initialAppearance: '推拉门可回服务巷，领用台在门内右侧。', slots: [{ id: 'slot_counter', label: '领用台前' }] },
  },
  items: {
    battery: { id: 'battery', name: '相机备用电池', initialPosition: { containerId: 'fingel', slotId: 'slot_pocket', relativeTo: null }, initialAppearance: '包装还没拆。', slots: [] },
  },
  characters: {
    lu: {
      id: 'lu', name: '路明非', initialPosition: { containerId: 'lane', slotId: null, relativeTo: null },
      initialAppearance: '校服领口松着，护目镜挂在胸前。', initialPersonality: '先把玩笑说完再办正事。', initialSanity: 43,
      tasks: { goggles: { id: 'goggles', ownerId: 'lu', parentTaskId: null, goal: '把护目镜戴好并确认镜片没有裂纹', status: 'pending' } },
      slots: [],
    },
    fingel: {
      id: 'fingel', name: '芬格尔', initialPosition: { containerId: 'shed', slotId: 'slot_counter', relativeTo: null },
      initialAppearance: '头发乱着，手指在机身上敲了两下。', initialPersonality: '把每一件小事都说成一笔交易。', initialSanity: 51,
      tasks: {}, slots: [],
    },
  },
};

const state0 = buildInitialState(initial);
const point = {
  worldId: 'world_demo', id: 'p1', sequence: 1, kind: 'normal', previousPointId: 'root',
  roundId: 'r1', advanceId: 'a1', trigger: 'player', linkedFromPointId: null,
  timeAdvance: { boundary: 'elapsed', duration: { amount: 4, unit: 'minute' } },
  entityDeltas: {
    lu: {
      entityId: 'lu',
      positionSet: { containerId: 'shed', slotId: 'slot_counter', relativeTo: null },
      appearanceChanges: [{ id: 'a1', text: '护目镜的带子在手腕上绕了一圈。', supersedes: [] }],
      sanitySet: 40,
      tasksAchieved: ['goggles'],
    },
    fingel: { entityId: 'fingel', sanitySet: 48 },
    battery: { entityId: 'battery', positionSet: { containerId: 'shed', slotId: 'slot_counter', relativeTo: null } },
  },
};
const state1 = applyPoint(state0, point);
const digest = await stateDigest(state1);

const progress: unknown[] = [];
const result = await generateCandidate({
  engine: undefined,
  committed: {
    anchor: { worldId: 'world_demo', pointId: 'p1', version: 1, stateDigest: digest, previousPointId: 'root' },
    state: state1,
    beforeState: state0,
    timeAdvance: point.timeAdvance,
    entityDeltas: point.entityDeltas,
    facts: [],
  },
  priorText: null,
  onProgress: (event: unknown) => progress.push(event),
  policy: {
    mode: 'program',
    composer: createBeatComposer(),
    minChars: 60,
    maxChars: 800,
    requireTime: true,
    sanityStyle: 'direction',
  },
});

console.log(`accepted=${String(result.accepted)} status=${String(result.status)} composers=${JSON.stringify(result.composers)}`);
console.log(String(result.text));
console.log('issues', JSON.stringify(result.issues));
const attempts = result.rawAttempts as Array<{ beatId: string; source: string; text: string; issues: unknown[] }>;
for (const attempt of attempts) {
  console.log(`- ${attempt.beatId} [${attempt.source}] ${JSON.stringify(attempt.text)}`);
  if (attempt.issues.length) console.log(`  issues ${JSON.stringify(attempt.issues)}`);
}
console.log(`progress events: ${progress.length}`);
