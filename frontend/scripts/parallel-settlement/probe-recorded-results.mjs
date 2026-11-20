import { createServer } from 'vite';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
const root = process.cwd();
const file = process.argv[2];
const turn = Number(process.argv[3]);
const key = process.argv[4];
const vite = await createServer({ root, configFile: false, logLevel: 'warn', cacheDir: '../.local/vite-replay-probe', server: { middlewareMode: true, hmr: false }, appType: 'custom' });
try {
  const { buildInitialState } = await vite.ssrLoadModule('/src/lib/world-engine/local/state.ts');
  const { createSettlementHandlers } = await vite.ssrLoadModule('/src/lib/world-engine/local/semantics/settlement/index.ts');
  const world = JSON.parse(await readFile(join(root, 'public/worlds/dragon-raja-free-day.world.json'), 'utf8'));
  const state = buildInitialState(world.initial);
  const run = JSON.parse(await readFile(file, 'utf8'));
  const t = run.turns.find((row) => row.turn === turn);
  const call = t.submission.calls.find((row) => row.task === 'results' && row.key === key);
  const answer = JSON.parse(call.raw.split('\n---\n').pop());
  const names = new Map(Object.entries(state.initial.characters).map(([id, row]) => [row.name, id]));
  const resolve = (v) => (typeof v === 'string' ? (names.get(v) ?? v) : v);
  const memberIds = [];
  for (const fact of answer.facts ?? []) for (const raw of fact.memberIds ?? []) { const id = resolve(raw); if (id && state.initial.characters[id] && !memberIds.includes(id)) memberIds.push(id); }
  const members = memberIds.map((memberId) => {
    const row = (answer.judgments ?? []).find((item) => resolve(item?.memberId) === memberId);
    const effects = Array.isArray(row?.effects) ? row.effects : [];
    const rolls = effects
      .map((effect) => resolve(effect?.targetId))
      .filter((targetId) => state.initial.characters[targetId] && targetId !== memberId)
      .map((targetId, index) => ({
        targetId, rollId: `${memberId}_${index}`, result: 10, eligible: true,
        admitted: effects.find((effect) => resolve(effect?.targetId) === targetId)?.reacted === true,
      }));
    return { memberId, actionText: '(probe)', rollRefs: rolls };
  });
  const engine = { info: { backend: 'probe', modelId: 'x' }, async load() {}, async dispose() {}, async complete() { return call.raw.split('\n---\n').pop(); } };
  const outcome = await createSettlementHandlers({ engine }).results(key, { groupId: key, members, workingState: state });
  const detail = outcome.evidence.detail ?? {};
  console.log(JSON.stringify({ members, facts: detail.facts, dropped: detail.droppedFacts, adjusted: { firstPerson: detail.firstPersonAdjusted, outcome: detail.outcomeAdjusted }, implicit: detail.implicitJudgments, value: outcome.value, error: outcome.error, detailKeys: Object.keys(detail) }, null, 1));
} finally { await vite.close(); }
