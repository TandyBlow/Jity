// Program-mode run for the C route (facts -> beats -> prose -> verification).
//
//   node scripts/candidate-constrained/run-program.mjs [--out <file>] [--mode program|model]
//
// Builds genuine settled points with the SAME browser kernel the product page
// uses (initial state -> applyPoint -> digests), then runs `generateCandidate`
// over the saved state pair. No hand-written packet, no fake state.
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';

const frontend = fileURLToPath(new URL('../../', import.meta.url));
const option = (flag, fallback) => process.argv.includes(flag) ? process.argv[process.argv.indexOf(flag) + 1] : fallback;
const outPath = option('--out', resolve(frontend, '../.local/candidate-constrained/run.json'));
const mode = option('--mode', 'program');

const worldFile = resolve(frontend, 'public/worlds/dragon-raja-free-day.world.json');
const world = JSON.parse(readFileSync(worldFile, 'utf8'));

const vite = await createServer({
  root: frontend,
  configFile: false,
  logLevel: 'warn',
  cacheDir: '../.local/candidate-constrained-vite',
  server: { middlewareMode: true, hmr: false },
  appType: 'custom',
});
let exitCode = 0;
try {
  const stateModule = await vite.ssrLoadModule('/src/lib/world-engine/local/state.ts');
  const candidateModule = await vite.ssrLoadModule('/src/lib/world-engine/local/narration-candidates/constrained/index.ts');
  const { buildInitialState, applyPoint, stateDigest } = stateModule;
  const { generateCandidate } = candidateModule;

  const initial = buildInitialState(world.initial);
  const rootDigest = await stateDigest(initial);
  const point0 = {
    worldId: world.worldId,
    id: 'point_root',
    sequence: 0,
    kind: 'normal',
    previousPointId: null,
    roundId: 'round_root',
    advanceId: 'advance_root',
    trigger: 'player',
    linkedFromPointId: null,
    timeAdvance: { duration: { amount: 0, unit: 'minute' } },
    entityDeltas: {},
  };

  const minute = (amount) => ({ duration: { amount, unit: 'minute' } });
  const at = (containerId, slotId = null) => ({ containerId, slotId, relativeTo: null });

  // Point 1: public/simple scene. The viewpoint walks from the service lane
  // into the equipment shed; nothing else changes.
  const point1 = {
    worldId: world.worldId,
    id: 'point_shed_1',
    sequence: 1,
    kind: 'normal',
    previousPointId: point0.id,
    roundId: 'round_1',
    advanceId: 'advance_1',
    trigger: 'player',
    linkedFromPointId: null,
    timeAdvance: minute(1),
    entityDeltas: {
      lu: { entityId: 'lu', positionSet: at('shed', 'slot_counter') },
    },
  };
  const state1 = applyPoint(initial, point1);
  const digest1 = await stateDigest(state1);

  // Point 2: free-day complex scene. Moves in/out of view, a task achieved, a
  // new subtask, a visible appearance change on the character and on the room,
  // a personality change, a sanity drop — plus hidden changes outside the room
  // that must NOT be narrated.
  const point2 = {
    worldId: world.worldId,
    id: 'point_shed_2',
    sequence: 2,
    kind: 'normal',
    previousPointId: point1.id,
    roundId: 'round_1',
    advanceId: 'advance_2',
    trigger: 'player',
    linkedFromPointId: null,
    timeAdvance: minute(2),
    entityDeltas: {
      lu: {
        entityId: 'lu',
        positionSet: at('shed', 'slot_counter'),
        appearanceChanges: [{
          id: 'change_lu_goggles_up',
          text: '护目镜已经推到额头上，镜带压住一撮头发，右手还搭在颈后的镜带上。',
          supersedes: [],
        }],
        personalityChanges: [{
          id: 'change_lu_use_gear',
          text: '开口还是先绕一句玩笑，但已经把护目镜当成要用的东西，不再只是挂在胸前给别人看。',
          supersedes: [],
        }],
        sanitySet: 40,
        tasksAchieved: ['task_lu_goggles'],
        subtasksAdded: [{
          id: 'task_lu_counter',
          ownerId: 'lu',
          parentTaskId: 'task_lu_kit',
          goal: '向秦越报明护目镜已经领到手，再问清担架放在哪一侧',
          status: 'pending',
        }],
      },
      goggles_lu: { entityId: 'goggles_lu', positionSet: at('lu', 'slot_right_hand') },
      nono: {
        entityId: 'nono',
        positionSet: at('shed', 'slot_cage'),
        tasksAchieved: ['task_nono_lu'],
      },
      fingel: { entityId: 'fingel', positionSet: at('yard', 'slot_south_cover') },
      shed: {
        entityId: 'shed',
        appearanceChanges: [{
          id: 'change_shed_lock_open',
          text: '器材笼的挂锁已经打开，锁舌挂在笼门上，笼里那副折叠担架被拖到了门口。',
          supersedes: [],
        }],
      },
      // Hidden: outside the shed, must stay in evidence and out of the prose.
      caesar: { entityId: 'caesar', positionSet: at('yard', null) },
      tang: { entityId: 'tang', sanitySet: 34 },
    },
  };
  const state2 = applyPoint(state1, point2);
  const digest2 = await stateDigest(state2);

  const committed = (anchor, state, beforeState, point) => ({
    anchor,
    state,
    beforeState,
    timeAdvance: point.timeAdvance,
    entityDeltas: point.entityDeltas,
    facts: [],
  });

  const simplePacket = committed({
    worldId: world.worldId, pointId: point1.id, version: 1, stateDigest: digest1, previousPointId: point0.id,
  }, state1, initial, point1);
  const complexPacket = committed({
    worldId: world.worldId, pointId: point2.id, version: 2, stateDigest: digest2, previousPointId: point1.id,
  }, state2, state1, point2);

  const noopEngine = {
    name: 'none',
    async complete() { throw new Error('program mode: no model engine'); },
    async *stream() { throw new Error('program mode: no model engine'); },
  };

  const runs = [];
  const simple = await generateCandidate({
    engine: noopEngine,
    committed: simplePacket,
    inputText: '我走进器材棚，先看看领用台上有什么。',
    priorText: null,
    policy: { mode: 'program', knowledge: { discoveredItemIds: ['map', 'rules'] } },
  });
  runs.push({ id: 'simple', input: '我走进器材棚，先看看领用台上有什么。', result: simple });
  if (!simple.accepted) exitCode = 1;

  const complex = await generateCandidate({
    engine: noopEngine,
    committed: complexPacket,
    inputText: '我把护目镜推到额头上，问秦越担架在哪一侧。',
    priorText: simple.text,
    policy: {
      mode: 'program',
      knowledge: { discoveredItemIds: ['map', 'rules'], visitedLocationIds: ['lane', 'shed'], metCharacterIds: ['nono', 'fingel'] },
      resultsText: '路明非把护目镜推到额头上，问秦越担架放在哪一侧；秦越说担架已经在器材笼门口，先报用途再登记。',
    },
  });
  runs.push({ id: 'complex', input: '我把护目镜推到额头上，问秦越担架在哪一侧。', result: complex });
  if (!complex.accepted) exitCode = 1;

  // Same point without full state: legacy CommittedNarration packet only.
  const factsOnlyBase = complex.basePacket ?? { anchor: complexPacket.anchor, facts: [] };
  const factsOnly = await generateCandidate({
    engine: noopEngine,
    committed: { ...factsOnlyBase, inputText: '我把护目镜推到额头上，问秦越担架在哪一侧。', priorText: simple.text },
    policy: { mode: 'program' },
  });
  runs.push({ id: 'facts-only', input: '我把护目镜推到额头上，问秦越担架在哪一侧。', result: factsOnly });
  if (!factsOnly.accepted) exitCode = 1;

  const report = {
    generatedAt: new Date().toISOString(),
    mode,
    worldFile,
    points: {
      root: { pointId: point0.id, version: 0, stateDigest: rootDigest },
      simple: { pointId: point1.id, version: 1, stateDigest: digest1 },
      complex: { pointId: point2.id, version: 2, stateDigest: digest2 },
    },
    runs: runs.map(({ id, input, result }) => ({
      id,
      input,
      text: result.text,
      accepted: result.accepted,
      status: result.status,
      issues: result.issues,
      unverifiedSentences: result.verification.unverifiedSentences,
      hiddenFactIds: result.verification.hiddenFactIds,
      coverage: result.verification.coverage,
      chars: result.verification.chars,
      composers: result.composers,
      beats: result.rawAttempts.map((beat) => ({ beatId: beat.beatId, kind: beat.kind, source: beat.source, text: beat.text, ms: beat.ms, issues: beat.issues })),
      plan: result.plan ? result.plan.beats.map((beat) => ({ id: beat.id, kind: beat.kind, factIds: beat.factIds, mustMention: beat.mustMention })) : null,
      timings: result.timings,
      strategyVersion: result.strategyVersion,
    })),
  };
  mkdirSync(dirname(outPath), { recursive: true });
  writeFileSync(outPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  console.log(`wrote ${outPath}`);
  for (const run of report.runs) {
    console.log(`\n===== ${run.id} accepted=${run.accepted} chars=${run.chars} hidden=${run.hiddenFactIds.length} =====`);
    console.log(run.text);
    const hard = run.issues.filter((issue) => issue.severity === 'hard');
    if (hard.length) console.log('HARD ISSUES', JSON.stringify(hard, null, 2));
  }
} catch (error) {
  exitCode = 1;
  console.error(error);
} finally {
  await vite.close();
}
process.exit(exitCode);
