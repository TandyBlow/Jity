/** Measures the real settlement prompts against the real world file without a
 * model: an engine that records the prompt and then fails makes every stage
 * report its exact prompt text and length. This is a size/coverage probe, not
 * a model run and not quality evidence.
 *
 *   node scripts/parallel-settlement/prompt-size.mjs
 */
import { createServer } from 'vite';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';

const root = process.cwd();
const vite = await createServer({
  root, configFile: false, logLevel: 'warn',
  cacheDir: '../.local/vite-prompt-size',
  server: { middlewareMode: true, hmr: false }, appType: 'custom',
});

try {
  const { buildInitialState } = await vite.ssrLoadModule('/src/lib/world-engine/local/state.ts');
  const { createSettlementHandlers } = await vite.ssrLoadModule('/src/lib/world-engine/local/semantics/settlement/index.ts');
  const world = JSON.parse(await readFile(join(root, 'public/worlds/dragon-raja-free-day.world.json'), 'utf8'));
  const state = buildInitialState(world.initial);
  const protagonist = state.protagonistId;
  const order = Object.keys(state.initial.characters).sort().slice(0, 3);

  const prompts = [];
  const engine = {
    info: { backend: 'probe', modelId: 'none' },
    async load() {},
    async dispose() {},
    async complete(prompt) {
      prompts.push(prompt);
      throw new Error('probe: no model installed');
    },
  };

  const continuationInput = {
    round: { roundId: 'round_probe', trigger: 'player', conclusion: null },
    head: { pointId: 'point_probe' },
    workingState: state,
    roundChanges: [{ pointId: 'point_probe', timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } }, entityDeltas: {} }],
  };

  const handlers = createSettlementHandlers({ engine, options: { maxPromptChars: 1_000_000 } });
  const updates = await handlers.updates('group_probe', {
    groupId: 'group_probe',
    mode: 'group',
    results: Object.fromEntries(order.map((id) => [id, '甲把盒子推到桌边。乙接住盒子。'])),
    workingState: state,
  });
  const results = await handlers.results('group_probe', {
    groupId: 'group_probe',
    members: order.map((id) => ({
      memberId: id,
      actionText: '把盒子推到桌边',
      rollRefs: [],
    })),
    workingState: state,
  });
  const continuation = await handlers.continuation('round_probe', continuationInput);

  const rows = [];
  const collect = (task, outcome) => {
    for (const call of outcome.evidence.calls) {
      const header = call.prompt.split(String.fromCharCode(10))[0].slice(0, 24);
      rows.push({ task, header, chars: call.prompt.length, error: call.error ?? null });
    }
  };
  collect('results', results);
  collect('updates', updates);
  collect('continuation', continuation);
  const byLength = [...rows].sort((a, b) => b.chars - a.chars);
  const headers = [...new Set(rows.map((row) => row.header))];
  console.error(JSON.stringify({
    world: world.worldId,
    characters: Object.keys(state.initial.characters).length,
    items: Object.keys(state.initial.items).length,
    locations: Object.keys(state.initial.locations).length,
    tasks: Object.values(state.initial.characters).reduce((sum, c) => sum + Object.keys(c.tasks ?? {}).length, 0),
    protagonist,
    resultsError: results.error ?? null,
    updatesError: updates.error ?? null,
    continuationError: continuation.error ?? null,
    promptChars: byLength,
    maxPromptChars: byLength[0]?.chars ?? 0,
    over8000: byLength.filter((row) => row.chars > 8000).length,
    headers,
    largest: byLength.slice(0, 4).map((row) => ({ task: row.task, header: row.header, chars: row.chars })),
  }, null, 2));
} finally {
  await vite.close();
}
