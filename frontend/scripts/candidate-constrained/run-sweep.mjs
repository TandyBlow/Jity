// Deterministic sweep over the real 龙族·自由一日 world.
//
//   node scripts/candidate-constrained/run-sweep.mjs [--out <file>] [--composer <path>]
//
// Builds each point with the page state kernel (initial state -> applyPoint),
// then runs `generateCandidate` in program mode and records acceptance, issues
// and the prose. This is coverage evidence for the C route, not a quality score.
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';

const frontend = fileURLToPath(new URL('../../', import.meta.url));
const option = (flag, fallback) => process.argv.includes(flag) ? process.argv[process.argv.indexOf(flag) + 1] : fallback;
const outPath = resolve(frontend, option('--out', '../.local/candidate-constrained/sweep.json'));
const composerPath = option('--composer', null);
const world = JSON.parse(readFileSync(resolve(frontend, 'public/worlds/dragon-raja-free-day.world.json'), 'utf8'));

const vite = await createServer({
  root: frontend, configFile: false, logLevel: 'warn', cacheDir: '../.local/candidate-constrained-vite',
  server: { middlewareMode: true, hmr: false }, appType: 'custom',
});
let exitCode = 0;
try {
  const { buildInitialState, applyPoint, stateDigest } = await vite.ssrLoadModule('/src/lib/world-engine/local/state.ts');
  const { generateCandidate } = await vite.ssrLoadModule('/src/lib/world-engine/local/narration-candidates/constrained/index.ts');
  let composer = null;
  if (composerPath) {
    const composerModule = await vite.ssrLoadModule(`/@fs/${composerPath.split(String.fromCharCode(92)).join('/')}`);
    const factory = composerModule.createBeatComposer ?? composerModule.default;
    if (typeof factory !== 'function') throw new Error(`--composer ${composerPath} exports no createBeatComposer()`);
    composer = factory();
  }

  const at = (containerId, slotId = null) => ({ containerId, slotId, relativeTo: null });
  const minute = (amount) => ({ boundary: 'elapsed', duration: { amount, unit: 'minute' } });

  const initial = buildInitialState(world.initial);

  const steps = [
    {
      id: 'move-lu', text: '我沿墙根走进院子。',
      point: {
        timeAdvance: minute(1),
        entityDeltas: { lu: { entityId: 'lu', positionSet: at('yard', 'slot_south_cover') } },
      },
    },
    {
      id: 'nono-task', text: '我问诺诺现在能不能过去。',
      point: {
        timeAdvance: minute(2),
        entityDeltas: {
          nono: {
            entityId: 'nono',
            tasksAchieved: ['task_nono_lu'],
          },
        },
      },
    },
    {
      id: 'fingel-appearance', text: '我看了看芬格尔的相机。',
      point: {
        timeAdvance: minute(1),
        entityDeltas: {
          fingel: {
            entityId: 'fingel',
            appearanceChanges: [{ id: 'sweep_fingel', text: '相机背带绕在手腕上，机身的漆磕掉了一角。', supersedes: [] }],
          },
        },
      },
    },
    {
      id: 'qin-subtask', text: '我问秦越担架要怎么登记。',
      point: {
        timeAdvance: minute(1),
        entityDeltas: {
          qin: {
            entityId: 'qin',
            subtasksAdded: [{
              id: 'task_qin_sweep', ownerId: 'qin', parentTaskId: 'task_qin_gear',
              goal: '让领用簿上写明担架由谁搬走', status: 'pending',
            }],
          },
        },
      },
    },
    {
      id: 'chu-sanity', text: '我听见钟楼那边有人喊话。',
      point: {
        timeAdvance: minute(1),
        entityDeltas: { chu: { entityId: 'chu', sanitySet: 66 } },
      },
    },
    {
      id: 'lin-personality', text: '我看了林亦舟一眼。',
      point: {
        timeAdvance: minute(1),
        entityDeltas: {
          lin: {
            entityId: 'lin',
            personalityChanges: [{
              id: 'sweep_lin', text: '开始肯把脚踝到底能不能受力说清楚，而不是只说位置。', supersedes: [],
            }],
          },
        },
      },
    },
    {
      id: 'zhou-move-task', text: '我抬头看旗台外廊。',
      point: {
        timeAdvance: minute(2),
        entityDeltas: {
          zhou: {
            entityId: 'zhou', positionSet: at('top', 'slot_balcony_door'),
            tasksAchieved: ['task_zhou_latch'],
          },
        },
      },
    },
    {
      id: 'item-move', text: '我把护目镜放到领用台上。',
      point: {
        timeAdvance: minute(1),
        entityDeltas: { goggles_lu: { entityId: 'goggles_lu', positionSet: at('shed', 'slot_counter') } },
      },
    },
    {
      id: 'place-appearance', text: '院子里的花槽被挪动过。',
      point: {
        timeAdvance: minute(1),
        entityDeltas: {
          yard: {
            entityId: 'yard',
            appearanceChanges: [{ id: 'sweep_yard', text: '南端石花槽被推到喷泉池边，露出底下的湿泥。', supersedes: [] }],
          },
        },
      },
    },
    {
      id: 'hidden-only', text: '我留在器材棚里等消息。',
      point: {
        timeAdvance: minute(1),
        entityDeltas: {
          caesar: { entityId: 'caesar', sanitySet: 70 },
          tang: { entityId: 'tang', positionSet: at('bridge', null) },
        },
      },
    },
    {
      id: 'elapsed-only', text: '我在原地待了一会儿。',
      point: { timeAdvance: minute(5), entityDeltas: {} },
    },
    {
      id: 'result-only', text: '我把话问完就停下。',
      resultsText: '路明非问清担架的去向；秦越说先报用途，再登记领用牌。',
      point: { timeAdvance: minute(1), entityDeltas: {} },
    },
  ];

  const runs = [];
  let previousPointId = 'sweep_root';
  let previousState = initial;
  let previousText = null;
  for (const [index, step] of steps.entries()) {
    const point = {
      worldId: world.worldId, id: `sweep_${index + 1}`, sequence: index + 1, kind: 'normal',
      previousPointId, roundId: 'round_sweep', advanceId: `advance_sweep_${index + 1}`,
      trigger: 'player', linkedFromPointId: null,
      timeAdvance: step.point.timeAdvance,
      entityDeltas: step.point.entityDeltas,
    };
    const after = applyPoint(previousState, point);
    const digest = await stateDigest(after);
    const result = await generateCandidate({
      engine: { info: { backend: 'none', modelId: null }, async load() {}, async dispose() {}, async complete() { throw new Error('program mode'); } },
      committed: {
        anchor: { worldId: world.worldId, pointId: point.id, version: index + 1, stateDigest: digest, previousPointId },
        state: after, beforeState: previousState, timeAdvance: point.timeAdvance, entityDeltas: point.entityDeltas, facts: [],
      },
      inputText: step.text,
      priorText: previousText,
      policy: { mode: 'program', resultsText: step.resultsText ?? null, composer },
    });
    const hard = result.issues.filter((issue) => issue.severity === 'hard');
    runs.push({
      id: step.id, pointId: point.id, accepted: result.accepted, status: result.status,
      chars: result.verification.chars, hardIssues: hard, text: result.text,
      composers: result.composers, hidden: result.verification.hiddenFactIds,
      coverage: result.verification.coverage,
    });
    if (!result.accepted) exitCode = 1;
    if (result.text) previousText = result.text;
    previousPointId = point.id;
    previousState = after;
  }

  const report = {
    generatedAt: new Date().toISOString(),
    world: 'dragon-raja-free-day.world.json',
    composer: composerPath,
    accepted: runs.filter((run) => run.accepted).length,
    total: runs.length,
    runs,
  };
  mkdirSync(dirname(outPath), { recursive: true });
  writeFileSync(outPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  for (const run of runs) {
    console.log(`${run.accepted ? 'ok  ' : 'FAIL'} ${run.id.padEnd(18)} ${String(run.chars).padStart(4)} chars  ${run.composers.join(',')}`);
    if (!run.accepted) console.log(JSON.stringify(run.hardIssues, null, 2));
  }
  console.log(`\n${report.accepted}/${report.total} accepted -> ${outPath}`);
} catch (error) {
  exitCode = 1;
  console.error(error);
} finally {
  await vite.close();
}
process.exit(exitCode);
