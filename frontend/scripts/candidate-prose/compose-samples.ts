/** Real prose from the public free-day world, through both call shapes.
 *
 *  - `generateCandidate({policy:{scene}})` — lane 02's entry shape.
 *  - `composeConstrainedBeat({beat, scene})` — lane 04's per-beat composer.
 *
 * Run from `frontend/`:
 *   ./node_modules/.bin/jiti ./scripts/candidate-prose/compose-samples.ts
 *
 * Every name, place, item and detail below is read from
 * `data/worlds/dragon-raja-free-day.world.json`; the script adds no material.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import {
  composeConstrainedBeat, generateCandidate,
  type BeatFactLike, type ComposeBeatRequestLike, type ProseScene,
} from '../../src/lib/world-engine/local/narration-candidates/prose-composer/index';

interface WorldFile {
  worldId: string;
  protagonistId: string;
  initial: {
    locations: Record<string, { id: string; name: string; parentLocationId: string | null; initialAppearance: string }>;
    characters: Record<string, { id: string; name: string; initialPosition: { containerId: string }; initialAppearance: string }>;
    items: Record<string, { id: string; name: string; initialPosition: { containerId: string }; initialAppearance: string }>;
  };
}

const worldPath = join(process.cwd(), '..', 'data', 'worlds', 'dragon-raja-free-day.world.json');
const world = JSON.parse(readFileSync(worldPath, 'utf8')) as WorldFile;
const location = (id: string) => world.initial.locations[id];
const character = (id: string) => world.initial.characters[id];
const item = (id: string) => world.initial.items[id];

function actor(id: string, extra: { gender?: 'male' | 'female' | 'unknown'; references?: string[] } = {}) {
  const source = character(id);
  return {
    id,
    name: source.name,
    gender: extra.gender ?? 'unknown' as const,
    references: extra.references,
    appearance: [source.initialAppearance],
    isProtagonist: id === world.protagonistId,
  };
}

const LANE = location('lane');
const SHED = location('shed');

/** 1. Standing in the service lane while Nono gives the briefing. */
const briefing: ProseScene = {
  worldId: world.worldId,
  pointId: 'sample_lane_briefing',
  protagonistId: 'lu',
  location: { id: LANE.id, name: LANE.name, parentName: location(LANE.parentLocationId!)?.name, details: [LANE.initialAppearance] },
  cast: [actor('lu', { gender: 'male' }), actor('nono', { gender: 'female', references: ['她'] })],
  items: [],
  beats: [
    { kind: 'action', actorId: 'nono', text: '诺诺把短枪换到左手，右手指向巷子尽头。' },
    { kind: 'line', speakerId: 'nono', text: '红方在集结点，蓝方守着钟楼。你要过去，别走正中。' },
    { kind: 'line', speakerId: 'lu', text: '走哪边？' },
    { kind: 'line', speakerId: 'nono', text: '西回廊有柱子，地下通道要过检修口。两条都比正路慢。' },
    { kind: 'task', actorId: 'lu', label: '向诺诺问清当前红蓝两方局势', scope: 'sub' },
    { kind: 'leave', actorId: 'nono', to: '红方集结点' },
  ],
  policy: { minChars: 90, seed: 17 },
};

/** 2. The protagonist walks to the equipment shed and finds Fingel. */
const shed: ProseScene = {
  worldId: world.worldId,
  pointId: 'sample_shed_battery',
  protagonistId: 'lu',
  location: { id: SHED.id, name: SHED.name, parentName: location(SHED.parentLocationId!)?.name, details: [SHED.initialAppearance] },
  parentLocation: { name: location(SHED.parentLocationId!)?.name ?? '西侧器材区' },
  cast: [actor('lu', { gender: 'male' }), actor('fingel', { gender: 'male' })],
  items: [
    {
      id: 'camera_battery', name: item('camera_battery').name,
      details: [item('camera_battery').initialAppearance], positionName: SHED.name,
    },
  ],
  beats: [
    { kind: 'move', actorId: 'lu', from: LANE.name, to: SHED.name },
    { kind: 'item', itemId: 'camera_battery', change: 'modified', detail: '芬格尔把相机备用电池从口袋里拿出来，放在领用台上。' },
    { kind: 'line', speakerId: 'fingel', text: '别看，机型不一样，插不进去。' },
    { kind: 'line', speakerId: 'lu', text: '能用就行。' },
    { kind: 'task', actorId: 'fingel', label: '确认短讯机电池与相机电池型号不同', scope: 'sub' },
    { kind: 'personality', actorId: 'fingel', text: '不再把每一件小事都算成一笔交易。' },
  ],
  policy: { minChars: 90, seed: 23 },
};

/** 3. A quiet minute: nobody moves, nothing changes. */
const quiet: ProseScene = {
  worldId: world.worldId,
  pointId: 'sample_quiet',
  protagonistId: 'lu',
  location: { id: LANE.id, name: LANE.name, details: [LANE.initialAppearance] },
  cast: [actor('lu', { gender: 'male' })],
  items: [],
  beats: [
    { kind: 'noChange' },
    { kind: 'time', amount: 1, unit: 'minute' },
  ],
  policy: { minChars: 16, seed: 5 },
};

/** 4. Continuation: the previous turn is quoted back, so it must not repeat. */
const continuation: ProseScene = {
  ...shed,
  pointId: 'sample_shed_after',
  items: [],
  beats: [
    { kind: 'stay', actorId: 'lu' },
    { kind: 'line', speakerId: 'lu', text: '这节电池能撑多久？' },
    { kind: 'line', speakerId: 'fingel', text: '够你把话说完。' },
    { kind: 'leave', actorId: 'fingel', to: LANE.name },
  ],
  priorText: '电池盒的盖子已经打开，槽里换上了一节新电池。\n\n「别看，机型不一样，插不进去。」芬格尔开口。\n\n器材棚里只剩路明非一个人。',
  policy: { minChars: 60, seed: 29 },
};

function run(name: string, scene: ProseScene): void {
  const started = performance.now();
  const first = generateCandidate({ policy: { scene } });
  const elapsed = performance.now() - started;
  console.log(`\n===== ${name}  accepted=${first.accepted}  chars=${[...first.text].length}  ${elapsed.toFixed(1)}ms`);
  console.log(first.text);
  if (!first.accepted) console.log('ISSUES', JSON.stringify(first.issues));
  if (first.sparse) console.log('SPARSE skeleton');
}

run('1 lane briefing', briefing);
run('2 shed battery', shed);
run('3 quiet minute', quiet);
run('4 continuation', continuation);

/** 5. The same material through lane 04's per-beat entry. */
const beatFacts: BeatFactLike[] = [
  { id: 'b_time', kind: 'time', mandatory: true, visibility: 'scene', advance: { duration: { amount: 4, unit: 'minute' } } },
  {
    id: 'b_move', kind: 'move', mandatory: true, visibility: 'scene', entityId: 'lu', name: character('lu').name,
    entityKind: 'character', from: LANE.name, to: SHED.name, viewpoint: true,
  },
  {
    id: 'b_task', kind: 'task_achieved', mandatory: true, visibility: 'scene', ownerId: 'lu', name: character('lu').name,
    goal: '在进入交火区前拿到可用的护目镜并检查镜片',
  },
  {
    id: 'b_sanity', kind: 'sanity_changed', mandatory: true, visibility: 'scene', ownerId: 'lu',
    name: character('lu').name, from: 43, to: 40,
  },
  {
    id: 'b_item', kind: 'item_present', mandatory: false, visibility: 'scene', itemId: 'supply_counter',
    name: '器材领用台', container: SHED.name, note: '台上夹着领用簿，笔尖尚湿。',
  },
];

const beatScene = {
  viewpoint: { id: 'lu', name: character('lu').name, location: LANE.name, note: character('lu').initialAppearance },
  place: { id: SHED.id, name: SHED.name, parentName: location(SHED.parentLocationId!)?.name ?? null, note: SHED.initialAppearance },
  present: [
    { id: 'lu', name: character('lu').name, note: character('lu').initialAppearance, viewpoint: true },
    { id: 'fingel', name: character('fingel').name, note: character('fingel').initialAppearance },
  ],
  objects: [{ id: 'supply_counter', name: '器材领用台', note: '台上夹着领用簿，笔尖尚湿。' }],
  facts: beatFacts,
  priorText: null,
};

const beatRequests: Array<[string, string[]]> = [
  ['open', ['b_time']],
  ['move', ['b_move']],
  ['event', ['b_task', 'b_sanity']],
  ['scene', ['b_item']],
  ['close', []],
];

console.log('\n===== 5 lane 04 per-beat entry');
for (const [kind, factIds] of beatRequests) {
  const request: ComposeBeatRequestLike = {
    beat: { id: kind, kind, factIds, details: [SHED.initialAppearance], mustMention: [], seed: 41 },
    scene: beatScene,
    prior: null,
  };
  const started = performance.now();
  const result = composeConstrainedBeat(request);
  console.log(`--- ${kind} (${(performance.now() - started).toFixed(2)}ms)`);
  console.log(result.text);
}
