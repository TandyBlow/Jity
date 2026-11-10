// Wiring check for the narration candidate patch.
//
// Loads the PATCHED `game-model.ts` from a target tree (the scratch worktree
// that has the live integration files + this patch) and drives its real
// `generate('narration', ...)` path with a controlled candidate. Three runs:
//
//   1. candidate accepts   → its prose is returned, progress is forwarded,
//                            the in-model single-shot call is NOT made;
//   2. candidate rejects   → the existing in-model writer runs (one call) and
//                            the result is marked as fallback;
//   3. `auto` selection    → no product-default candidate, so the in-model
//                            writer runs and no candidate code is touched;
//   4. second accepted run → receives the first accepted text as `priorText`
//                            (continuation reuses the accepted narration).
//
// The script never edits world state and never writes the product tree. It is
// evidence that the patch is wired, not a quality run.
//
//   node scripts/candidate-shipping/run-wiring-check.mjs --tree <patched tree> [--out file]
import { existsSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';

const here = dirname(fileURLToPath(import.meta.url));
const flag = (name, fallback) => {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
};
const tree = resolve(flag('--tree', 'D:/others/Jity/.local/parallel-local-game/scratch/shipping-06'));
const out = flag('--out', null);
if (!existsSync(resolve(tree, 'frontend/src/lib/world-engine/local/game-model.ts'))) {
  throw new Error(`patched tree not found: ${tree}`);
}

const engineCalls = [];
const fakeEngine = {
  info: { backend: 'wiring-check', modelId: 'fake-engine' },
  load: async () => undefined,
  complete: async (prompt, options) => {
    engineCalls.push({ promptChars: prompt.length, maxTokens: options?.maxTokens ?? null });
    let streamed = '';
    for (const fragment of ['风从走廊尽头吹过来，', '灯影在墙上晃了一下。']) {
      streamed += fragment;
      options?.onProgress?.({ raw: streamed, elapsedMs: 1 });
    }
    return '风从走廊尽头吹过来，灯影在墙上晃了一下。';
  },
  dispose: async () => undefined,
};

const results = { tree, status: 'IN_PROGRESS', checks: [], engineCalls: [] };
const check = (name, ok, detail) => {
  results.checks.push({ name, ok, detail });
  if (!ok) results.status = 'FAILED';
};

const server = await createServer({
  root: resolve(tree, 'frontend'), configFile: false, logLevel: 'error',
  server: { host: '127.0.0.1', port: 0, hmr: false },
});
try {
  const selection = await server.ssrLoadModule('/src/lib/world-engine/local/narration-candidates/selection/index.ts');
  const { LocalGameModel } = await server.ssrLoadModule('/src/lib/world-engine/local/game-model.ts');
  const { SHORT_STATE } = await server.ssrLoadModule('/src/lib/world-engine/runtime/b3-short-samples.ts');

  const clone = (value) => JSON.parse(JSON.stringify(value));
  const before = clone(SHORT_STATE);
  const after = clone(SHORT_STATE);
  after.characters.person_a.position = { containerId: 'hall', slotId: null, relativeTo: null };
  const point = {
    pointId: 'point_wiring',
    before,
    delta: {
      timeAdvance: { boundary: 'elapsed', duration: { amount: 2, unit: 'minute' } },
      entityDeltas: { person_a: { entityId: 'person_a', positionSet: { containerId: 'hall', slotId: null, relativeTo: null } } },
    },
    after,
  };

  const makeModel = (candidate) => {
    const events = { progress: [], complete: [], tasks: [] };
    const model = new LocalGameModel(fakeEngine, {
      narrationEngine: fakeEngine,
      narrationCandidate: candidate,
      onNarrationProgress: (progress) => events.progress.push(progress),
      onNarrationComplete: (progress) => events.complete.push(progress),
      onTask: (task, key, detail) => events.tasks.push({ task, key, ...detail }),
    });
    return {
      events,
      run: async (input = point) => {
        const value = await model.generate('narration', input.pointId, input);
        return { value, events };
      },
    };
  };

  const candidateCalls = [];
  const installCandidate = (result) => {
    selection.SHIPPED_CANDIDATES[0] = {
      id: 'trained',
      route: 'trained',
      version: 'wiring-check-candidate',
      label: 'wiring check',
      requires: { modules: [], template: 'none' },
      productDefault: true,
      availability: () => ({ available: true, reason: null }),
      run: async ({ point: input, onProgress }) => {
        candidateCalls.push({ pointId: input.pointId, priorText: input.priorText ?? null, playerInput: input.playerInput ?? null });
        onProgress?.({ text: '走廊里', elapsedMs: 5, verified: false, attempt: 0 });
        onProgress?.({ text: '走廊里的灯影晃了一下。', elapsedMs: 9, verified: false, attempt: 0 });
        return {
          candidateId: 'trained', route: 'trained', text: result.text, accepted: result.accepted,
          grade: result.accepted ? 'candidate' : 'candidate_unverified',
          status: result.accepted ? 'accepted' : 'rejected',
          reason: result.accepted ? null : 'rejected:wiring-fixture',
          issues: result.accepted ? [] : [{ kind: 'wiring_fixture', severity: 'hard' }],
          attempts: 1, promptChars: 80,
          timings: { totalMs: 12, attemptMs: [12], firstTokenMs: 5 },
          strategyVersion: 'wiring-check-candidate', allFellBack: false,
        };
      },
    };
  };

  const original = selection.SHIPPED_CANDIDATES[0];
  // 1. accepted candidate is submitted, streaming forwarded, in-model call skipped.
  installCandidate({ accepted: true, text: '走廊里的灯影晃了一下，他把手按在门框上。' });
  engineCalls.length = 0;
  const session = makeModel('trained');
  const accepted = await session.run();
  check('accepted: candidate text is the submitted narration',
    accepted.value === '走廊里的灯影晃了一下，他把手按在门框上。', accepted.value);
  check('accepted: real progress increments reach the page',
    accepted.events.progress.length === 2 && accepted.events.progress[1].raw === '走廊里的灯影晃了一下。',
    accepted.events.progress.map((event) => event.raw));
  check('accepted: onTask reports no fallback',
    accepted.events.tasks.some((task) => task.task === 'narration' && task.fallback === false), accepted.events.tasks);
  check('accepted: in-model single-shot call is not made', engineCalls.length === 0, engineCalls.length);
  check('accepted: completion evidence is forwarded',
    accepted.events.complete.length === 1 && accepted.events.complete[0].completion.finishReason === 'stop', accepted.events.complete.length);
  check('accepted: candidate receives the player input and the projection',
    candidateCalls.at(-1)?.pointId === 'point_wiring' && candidateCalls.at(-1)?.priorText === null, candidateCalls.at(-1));

  // 2. second accepted run reuses the accepted text as prior text.
  await session.run();
  check('continuation: previous accepted text is passed as priorText',
    candidateCalls.at(-1)?.priorText === '走廊里的灯影晃了一下，他把手按在门框上。', candidateCalls.at(-1));

  // 3. rejected candidate falls back to the existing writer.
  installCandidate({ accepted: false, text: '他推门走进了不存在的房间。' });
  engineCalls.length = 0;
  const rejected = await session.run();
  check('rejected: the submitted text is not the rejected draft', rejected.value !== '他推门走进了不存在的房间。', rejected.value);
  check('rejected: the in-model writer ran', engineCalls.length === 1, engineCalls.length);
  check('rejected: the point is marked as fallback',
    rejected.events.tasks.some((task) => task.task === 'narration' && task.fallback === true), rejected.events.tasks);

  // 4. `auto` never runs a candidate without product evidence: the existing
  //    in-model writer produces the text.
  selection.SHIPPED_CANDIDATES[0] = original;
  candidateCalls.length = 0;
  engineCalls.length = 0;
  const auto = await makeModel('auto').run();
  check('auto: no product-default candidate -> no candidate call', candidateCalls.length === 0, candidateCalls.length);
  check('auto: in-model writer produces the text', engineCalls.length === 1, engineCalls.length);

  // 5. a rejected/cancelled candidate must not poison the next accepted
  //    continuation's priorText.
  installCandidate({ accepted: false, text: '半句被取消的草稿' });
  const cancelled = await session.run();
  check('cancelled: rejected/cancelled draft is not submitted', cancelled.value !== '半句被取消的草稿', cancelled.value);
  installCandidate({ accepted: true, text: '取消之后重新写出的正文。' });
  await session.run();
  check('cancelled: a cancelled draft never becomes the next priorText',
    candidateCalls.at(-1)?.priorText === '走廊里的灯影晃了一下，他把手按在门框上。', candidateCalls.at(-1));

  // 6. `builtin` disables the runner entirely.
  engineCalls.length = 0;
  candidateCalls.length = 0;
  await makeModel('builtin').run();
  check('builtin: no candidate call and one in-model call', candidateCalls.length === 0 && engineCalls.length === 1,
    { candidateCalls: candidateCalls.length, engineCalls: engineCalls.length });

  results.status = results.checks.every((entry) => entry.ok) ? 'PASS' : 'FAILED';
  results.engineCalls = engineCalls;
} catch (error) {
  results.status = 'FAILED';
  results.error = error instanceof Error ? `${error.name}: ${error.message}\n${error.stack ?? ''}` : String(error);
} finally {
  await server.close();
}

const text = `${JSON.stringify(results, null, 2)}\n`;
if (out) writeFileSync(resolve(out), text);
console.log(text);
process.exitCode = results.status === 'PASS' ? 0 : 1;
