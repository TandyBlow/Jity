/** Ten consecutive turns on the same world, each with the previous turn as
 * `priorText`. A development check of cross-turn behaviour (repeated closers,
 * repeated paragraphs, characters shrinking to nothing) that three independent
 * samples cannot see. It is NOT product acceptance and it uses no model.
 *
 *   LANE04_ROOT=../04-settlement ./node_modules/.bin/jiti \
 *     ./scripts/candidate-prose/chain-10.ts
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

interface Turn {
  text: string;
  time: { amount: number; unit: 'second' | 'minute' };
  deltas: Record<string, Record<string, unknown>>;
}

const turns: Turn[] = [
  { text: '走到器材棚', time: { amount: 2, unit: 'minute' }, deltas: { lu: { entityId: 'lu', positionSet: { containerId: 'shed', slotId: 'slot_counter', relativeTo: null } } } },
  { text: '戴好护目镜（任务达成）', time: { amount: 3, unit: 'minute' }, deltas: { lu: { entityId: 'lu', tasksAchieved: ['task_lu_goggles'] } } },
  { text: '芬格尔跟进来', time: { amount: 1, unit: 'minute' }, deltas: { fingel: { entityId: 'fingel', positionSet: { containerId: 'shed', slotId: null, relativeTo: null } } } },
  { text: '个性与精神变化', time: { amount: 2, unit: 'minute' }, deltas: { lu: { entityId: 'lu', personalityChanges: [{ id: 'chain_p1', text: '不再把选择留给别人。', supersedes: [] }], sanitySet: 44 } } },
  { text: '只在原地过一分钟', time: { amount: 1, unit: 'minute' }, deltas: {} },
  { text: '走到中央庭院', time: { amount: 4, unit: 'minute' }, deltas: { lu: { entityId: 'lu', positionSet: { containerId: 'yard', slotId: null, relativeTo: null } } } },
  { text: '诺诺也在庭院', time: { amount: 1, unit: 'minute' }, deltas: { nono: { entityId: 'nono', positionSet: { containerId: 'yard', slotId: null, relativeTo: null } } } },
  { text: '外貌变化', time: { amount: 2, unit: 'minute' }, deltas: { lu: { entityId: 'lu', appearanceChanges: [{ id: 'chain_a1', text: '袖口沾了喷泉边的水。', supersedes: [] }] } } },
  { text: '精神回升', time: { amount: 2, unit: 'minute' }, deltas: { lu: { entityId: 'lu', personalityChanges: [{ id: 'chain_p2', text: '愿意先听完再回答。', supersedes: [] }], sanitySet: 58 } } },
  { text: '回到服务巷', time: { amount: 3, unit: 'minute' }, deltas: { lu: { entityId: 'lu', positionSet: { containerId: 'lane', slotId: null, relativeTo: null } } } },
  // 11-20: items, dialogue, two actors at once, task progress, sanity, no-change.
  { text: '在服务巷拿到地图', time: { amount: 2, unit: 'minute' }, deltas: { map: { entityId: 'map', positionSet: { containerId: 'lane', slotId: null, relativeTo: null } } } },
  { text: '两名同伴同时进巷', time: { amount: 2, unit: 'minute' }, deltas: { fingel: { entityId: 'fingel', positionSet: { containerId: 'lane', slotId: null, relativeTo: null } }, nono: { entityId: 'nono', positionSet: { containerId: 'lane', slotId: null, relativeTo: null } } } },
  { text: '与诺诺对话一句', time: { amount: 1, unit: 'minute' }, deltas: { nono: { entityId: 'nono', quotesAdded: [{ id: 'chain_q1', text: '你先说清楚自己要站在哪一边。' }] } } },
  { text: '推进子任务', time: { amount: 2, unit: 'minute' }, deltas: { lu: { entityId: 'lu', tasksAchieved: ['task_lu_choice'] } } },
  { text: '精神下降', time: { amount: 1, unit: 'minute' }, deltas: { lu: { entityId: 'lu', sanitySet: 38 } } },
  { text: '又一分钟没变化', time: { amount: 1, unit: 'minute' }, deltas: {} },
  { text: '地图被收走', time: { amount: 1, unit: 'minute' }, deltas: { map: { entityId: 'map', positionSet: { containerId: 'shed', slotId: null, relativeTo: null } } } },
  { text: '同伴离开', time: { amount: 2, unit: 'minute' }, deltas: { fingel: { entityId: 'fingel', positionSet: { containerId: 'yard', slotId: null, relativeTo: null } } } },
  { text: '诺诺后退半步', time: { amount: 1, unit: 'minute' }, deltas: { nono: { entityId: 'nono', positionChanges: [{ axis: 'y', delta: -0.5 }] } } },
  { text: '走到器材棚', time: { amount: 3, unit: 'minute' }, deltas: { lu: { entityId: 'lu', positionSet: { containerId: 'shed', slotId: null, relativeTo: null } } } },
];

let state = buildInitialState(world.initial);
let beforeRead = {
  pointId: 'root', version: 0, state, stateDigest: 'root',
  previousPointId: null, timeAdvance: null, entityDeltas: {},
} as Record<string, unknown>;
let priorText: string | null = null;
const transcript: string[] = [];
const accepted: string[] = [];
const sentences: string[] = [];
const closers: string[] = [];

for (const [index, turn] of turns.entries()) {
  const point = {
    worldId: world.worldId,
    id: `chain_${index + 1}`,
    sequence: index + 1,
    kind: 'normal',
    previousPointId: beforeRead.pointId,
    roundId: `chain_r${index + 1}`,
    advanceId: `chain_a${index + 1}`,
    trigger: 'player',
    linkedFromPointId: null,
    timeAdvance: { boundary: 'elapsed', duration: turn.time },
    entityDeltas: turn.deltas,
  } as Record<string, unknown>;
  const after = applyPoint(beforeRead.state, point);
  const afterRead = {
    pointId: point.id,
    version: index + 1,
    state: after,
    stateDigest: `chain-digest-${index + 1}`,
    previousPointId: beforeRead.pointId,
    timeAdvance: point.timeAdvance,
    entityDeltas: point.entityDeltas,
  };
  const { base: committed } = projectConstrainedScene(afterRead, beforeRead);
  if (process.env.DUMP_BEATS === String(index + 1)) {
    console.log('BEATS keys', Object.keys(committed as Record<string, unknown>));
    console.log('BEATS', JSON.stringify(committed, null, 1).slice(0, 4000));
  }
  const result = generateCandidate({
    committed: { ...(committed as Record<string, unknown>), state: after },
    state: after,
    beforeState: beforeRead.state,
    delta: { timeAdvance: point.timeAdvance },
    priorText,
    // 06 has the transcript; passing it stops static texture being stamped
    // again two or more turns later.
    policy: { minChars: 12, avoidText: transcript.join(String.fromCharCode(10)) || null },
  } as never);

  const paragraphs = result.text.split(/\n{2,}/).map((part) => part.trim()).filter(Boolean);
  const tail = paragraphs.at(-1) ?? '';
  for (const sentence of result.text.split(/(?<=[。！？」])/u).map((part) => part.trim()).filter(Boolean)) {
    sentences.push(sentence);
  }
  if (tail) closers.push(tail);
  accepted.push(result.accepted ? 'ok' : 'REJECTED');
  console.log(`\n===== turn ${index + 1}: ${turn.text}`);
  console.log(`accepted=${result.accepted} chars=${[...result.text].length} issues=${JSON.stringify(result.issues)}`);
  console.log(result.text);
  if (!result.accepted) console.log('paragraphs', JSON.stringify(result.composed.paragraphs));

  if (result.text) transcript.push(result.text);
  priorText = result.text || priorText;
  beforeRead = afterRead;
  state = after;
}

// Cross-turn repetition checks: verbatim sentences and identical closers.
const seen = new Map<string, number>();
for (const sentence of sentences) seen.set(sentence, (seen.get(sentence) ?? 0) + 1);
const repeatedSentences = [...seen.entries()].filter(([, count]) => count > 1);
const closerCounts = new Map<string, number>();
for (const closer of closers) closerCounts.set(closer, (closerCounts.get(closer) ?? 0) + 1);
const repeatedClosers = [...closerCounts.entries()].filter(([, count]) => count > 1);

console.log('\n===== summary');
console.log(`accepted ${accepted.filter((entry) => entry === 'ok').length}/${turns.length}`);
console.log(`sentences ${sentences.length}, repeated verbatim ${repeatedSentences.length}`);
for (const [sentence, count] of repeatedSentences) console.log(`  x${count} ${sentence}`);
console.log(`distinct closers ${closerCounts.size}/${closers.length}; repeated closers ${repeatedClosers.length}`);
for (const [closer, count] of repeatedClosers) console.log(`  x${count} ${closer}`);
console.log(`total chars ${closers.reduce((sum, closer) => sum + [...closer].length, 0)} (closers only)`);
