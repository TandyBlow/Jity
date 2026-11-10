// Load 06's real TypeScript modules without writing into their worktree.
//
// Why: the beat prompts I train on must be the prompts the page actually
// builds. Re-typing the builder in Python drifts silently (it already happened
// once with the page draft prompt), so this asks vite to load their source and
// runs it in node. cacheDir points into my experiments directory, so nothing is
// written under the 06 worktree.
//
//   node harness/beats-prompts.mjs --in beats.jsonl --out prompts.jsonl
import { createRequire } from 'node:module';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';

const FRONTEND = 'D:/others/Jity/.local/parallel-local-game/worktrees/06-recovery/frontend';
const CACHE = path.resolve('experiments/narration-runtime-v2/.vite-cache');

export async function loadModules(root = FRONTEND) {
  const require = createRequire(path.join(root, 'package.json'));
  const vitePath = require.resolve('vite');
  const vite = await import('file://' + vitePath.replace(/\\/g, '/'));
  mkdirSync(CACHE, { recursive: true });
  const server = await vite.createServer({
    root, cacheDir: CACHE, configFile: false, logLevel: 'error',
    server: { middlewareMode: true, hmr: false }, appType: 'custom',
  });
  const load = (id) => server.ssrLoadModule(id);
  const mod = await load('/src/lib/world-engine/local/narration-candidates/trained-generation/beats.ts');
  const narration = await load('/src/lib/world-engine/runtime/committed-narration.ts');
  return { server, mod, narration, close: () => server.close() };
}

async function main() {
  const args = { in: '', out: '' };
  for (let i = 2; i < process.argv.length; i += 2) args[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
  const { mod, narration, close } = await loadModules();
  try {
    const rows = readFileSync(args.in, 'utf8').split('\n').filter((line) => line.trim()).map((line) => JSON.parse(line));
    let done = 0;
    const out = [];
    for (const row of rows) {
      let prompt;
      try {
        let beat = row.beat;
        if (row.usePlan) {
          const planned = mod.planBeats({
            committed: { facts: [row.fact] }, ledger: row.ledger, policy: row.policy ?? {}, scene: row.scene,
          });
          beat = planned.find((item) => item.kind === 'fact') ?? planned[planned.length - 1];
        }
        prompt = mod.buildBeatPrompt({
          beat, ledger: row.ledger, policy: row.policy ?? {}, scene: row.scene ?? null,
          written: row.written ?? [], priorTail: row.priorTail ?? null,
        });
      } catch (error) {
        prompt = { error: String(error) };
      }
      out.push({ id: row.id, prompt });
      done += 1;
    }
    if (args.out) writeFileSync(args.out, out.map((item) => JSON.stringify(item)).join('\n') + '\n');
    process.stdout.write(JSON.stringify({ rows: done, out: args.out, factPhrases: narration.factPhrases({ kind: 'moved', name: 'A', from: 'B', to: 'C' }) }) + '\n');
  } finally {
    await close();
  }
}

if (process.argv[1]?.endsWith('beats-prompts.mjs')) main().catch((error) => { console.error(error); process.exit(1); });
