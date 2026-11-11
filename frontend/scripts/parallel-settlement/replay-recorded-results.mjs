#!/usr/bin/env node
/**
 * Replay every recorded `results` answer from real /world-local runs through the
 * current settlement parser. Offline, no model.
 *
 *   node scripts/parallel-settlement/replay-recorded-results.mjs ../../../results/product/evidence
 *
 * Why: each 09 run stores the model's raw results answer. A turn dies when the
 * current parser rejects it. This sweep shows which recorded answers still fail,
 * with the rejection reason, so a fix targets a real input instead of a guess.
 *
 * Limits: the run's live state is not stored, so the parser reads the initial
 * world state. Ownership/position normalisations can therefore differ from the
 * run; the report marks each row and never claims product quality.
 */
import { createServer } from 'vite';
import { readFile, readdir } from 'node:fs/promises';
import { join } from 'node:path';

const root = process.cwd();
const dir = process.argv[2] ?? join(root, '../../../results/product/evidence');

const vite = await createServer({
  root, configFile: false, logLevel: 'warn',
  cacheDir: '../.local/vite-replay', server: { middlewareMode: true, hmr: false }, appType: 'custom',
});

function parseGroupId(groupId) {
  return String(groupId ?? '');
}

try {
  const { buildInitialState } = await vite.ssrLoadModule('/src/lib/world-engine/local/state.ts');
  const { createSettlementHandlers } = await vite.ssrLoadModule('/src/lib/world-engine/local/semantics/settlement/index.ts');
  const world = JSON.parse(await readFile(join(root, 'public/worlds/dragon-raja-free-day.world.json'), 'utf8'));
  const state = buildInitialState(world.initial);
  const names = new Map(Object.entries(state.initial.characters).map(([id, row]) => [row.name, id]));
  const resolve = (value) => (typeof value === 'string' ? (names.get(value) ?? value) : value);

  const files = (await readdir(dir)).filter((name) => /^09-.*\.json$/.test(name));
  const rows = [];
  for (const file of files) {
    let run;
    try { run = JSON.parse(await readFile(join(dir, file), 'utf8')); } catch { continue; }
    if (!run || typeof run !== 'object' || !Array.isArray(run.turns)) continue;
    for (const turn of run.turns) {
      for (const call of turn?.submission?.calls ?? []) {
        if (call?.task !== 'results' || typeof call.raw !== 'string' || !call.raw.trim().startsWith('{')) continue;
        // The raw is the last attempt; earlier attempts were rejected by the
        // parser at the time, and only the last one settles the point.
        let answer;
        try { answer = JSON.parse(call.raw.split('\n---\n').pop()); } catch { continue; }
        const judgments = Array.isArray(answer.judgments) ? answer.judgments : [];
        // Membership comes from the facts, not the judgement rows: the model
        // writes an extra row for a bystander and the real caller's group is the
        // frozen one (facts can only name members).
        const memberIds = [];
        for (const fact of Array.isArray(answer.facts) ? answer.facts : []) {
          for (const raw of Array.isArray(fact?.memberIds) ? fact.memberIds : []) {
            const id = resolve(raw);
            if (id && state.initial.characters[id] && !memberIds.includes(id)) memberIds.push(id);
          }
        }
        // A reaction group's reactor row can be the only row with an effect and
        // no fact of its own in the last raw; if its effect targets a member it
        // was in the freeze.
        for (const row of judgments) {
          const id = resolve(row?.memberId);
          if (!id || !state.initial.characters[id] || memberIds.includes(id)) continue;
          const effects = Array.isArray(row?.effects) ? row.effects : [];
          if (effects.some((effect) => memberIds.includes(resolve(effect?.targetId)))) memberIds.push(id);
        }
        if (!memberIds.length) continue;
        // Reconstruct the frozen roll table from the answer itself: the effects
        // row carries the admission the run froze.
        const members = memberIds.map((memberId) => {
          const row = judgments.find((item) => resolve(item?.memberId) === memberId);
          const effects = Array.isArray(row?.effects) ? row.effects : [];
          const rolls = effects
            .map((effect) => resolve(effect?.targetId))
            .filter((targetId) => state.initial.characters[targetId] && targetId !== memberId)
            .map((targetId, index) => ({
              targetId, rollId: `${memberId}_${index}`, result: 10, eligible: true,
              // The recorded effects row is the frozen admission the run used.
              admitted: effects.find((effect) => resolve(effect?.targetId) === targetId)?.reacted === true,
            }));
          return { memberId, actionText: '（回放：运行记录未保存冻结行动文本）', rollRefs: rolls };
        });
        let attempt = 0;
        const engine = {
          info: { backend: 'replay', modelId: 'recorded' },
          async load() {}, async dispose() {},
          async complete() {
            attempt += 1;
            // Return the recorded answer once; a repair call gets the same text
            // so a rejection is visible instead of looping.
            return call.raw.split('\n---\n').pop();
          },
        };
        const handlers = createSettlementHandlers({ engine });
        let outcome;
        try {
          outcome = await handlers.results(parseGroupId(call.key) || 'replay', { groupId: call.key, members, workingState: state });
        } catch (error) {
          rows.push({ file, turn: turn.turn, key: call.key, settled: false, error: String(error?.message ?? error).slice(0, 220), runError: call.error ?? null, runSettled: !call.error });
          continue;
        }
        const detail = outcome.evidence.detail ?? {};
        rows.push({
          file, turn: turn.turn, key: call.key, settled: outcome.value != null,
          error: outcome.error ?? null, runError: call.error ?? null, runSettled: !call.error,
          facts: Array.isArray(detail.facts) ? detail.facts.length : 0,
          dropped: Array.isArray(detail.droppedFacts) ? detail.droppedFacts.map((row) => row.reason) : [],
          adjusted: {
            outcome: Array.isArray(detail.outcomeAdjusted) ? detail.outcomeAdjusted.length : 0,
            effects: Array.isArray(detail.effectsAdjusted) ? detail.effectsAdjusted.length : 0,
            owner: Array.isArray(detail.ownershipAdjusted) ? detail.ownershipAdjusted.length : 0,
            firstPerson: Array.isArray(detail.firstPersonAdjusted) ? detail.firstPersonAdjusted.length : 0,
          },
        });
      }
    }
  }
  const stillFailing = rows.filter((row) => !row.settled);
  console.log(JSON.stringify({
    kind: 'recorded-results-replay',
    at: new Date().toISOString(),
    answers: rows.length,
    settled: rows.length - stillFailing.length,
    stillFailing: stillFailing.length,
    failures: stillFailing,
    rows,
  }, null, 1));
} finally {
  await vite.close();
}
