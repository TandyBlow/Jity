/** Whole-scene entry from a committed fact packet plus the settled state read.
 *
 * Lane 04 projects the facts; this script then calls THIS composer's
 * `generateCandidate` (not 04's beat writer) with `committed`, `state`,
 * `beforeState` and `delta`. The composer fills scene material from the state
 * and writes the whole turn at once. This is the path a page can use without
 * injecting the per-beat composer.
 *
 *   LANE04_ROOT=../04-settlement ./node_modules/.bin/jiti \
 *     ./scripts/candidate-prose/sample-committed-state.ts
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

import { generateCandidate } from '../../src/lib/world-engine/local/narration-candidates/prose-composer/index';

const lane04 = process.env.LANE04_ROOT ?? join(process.cwd(), '..', '..', '04-settlement');
const load = async (modulePath: string) => import(pathToFileURL(join(lane04, modulePath)).href) as Promise<Record<string, unknown>>;

const stateModule = await load('frontend/src/lib/world-engine/local/state.ts');
const constrained = await load('frontend/src/lib/world-engine/local/narration-candidates/constrained/index.ts');
const buildInitialState = stateModule.buildInitialState as (initial: unknown) => unknown;
const applyPoint = stateModule.applyPoint as (state: unknown, point: unknown) => unknown;
const projectConstrainedScene = constrained.projectConstrainedScene as (after: unknown, before: unknown) => { base: unknown };

const world = JSON.parse(readFileSync(
  join(process.cwd(), '..', 'data', 'worlds', 'dragon-raja-free-day.world.json'),
  'utf8',
)) as { worldId: string; initial: unknown };

const base = buildInitialState(world.initial);
const point = {
  worldId: world.worldId,
  id: 'whole_1',
  sequence: 1,
  kind: 'normal',
  previousPointId: 'root',
  roundId: 'whole_r1',
  advanceId: 'whole_a1',
  trigger: 'player',
  linkedFromPointId: null,
  timeAdvance: { boundary: 'elapsed', duration: { amount: 5, unit: 'minute' } },
  entityDeltas: {
    lu: {
      entityId: 'lu',
      positionSet: { containerId: 'shed', slotId: 'slot_counter', relativeTo: null },
      tasksAchieved: ['task_lu_goggles'],
      appearanceChanges: [{ id: 'whole_a1', text: '护目镜的带子在手腕上绕了一圈。', supersedes: [] }],
      personalityChanges: [{ id: 'whole_p1', text: '不再把选择推给别人。', supersedes: [] }],
      sanitySet: 40,
    },
  },
};
const after = applyPoint(base, point);
const beforeRead = {
  pointId: 'root', version: 0, state: base, stateDigest: 'root',
  previousPointId: null, timeAdvance: null, entityDeltas: {},
};
const afterRead = {
  pointId: point.id, version: 1, state: after, stateDigest: 'whole-digest',
  previousPointId: 'root', timeAdvance: point.timeAdvance, entityDeltas: point.entityDeltas,
};
const { base: committed } = projectConstrainedScene(afterRead, beforeRead);

const progress: string[] = [];
const started = performance.now();
const result = generateCandidate({
  engine: null,
  committed,
  state: after,
  beforeState: base,
  delta: { timeAdvance: point.timeAdvance },
  priorText: null,
  signal: new AbortController().signal,
  onProgress: (event) => progress.push(event.status),
  policy: { minChars: 60 },
} as never);
const elapsed = performance.now() - started;

console.log(`accepted=${result.accepted} sparse=${result.sparse} chars=${[...result.text].length} ${elapsed.toFixed(1)}ms`);
console.log(result.text);
console.log('issues', JSON.stringify(result.issues));
console.log('progress', progress.join(','));
