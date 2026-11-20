// Re-capture the page's narration prompts from 06's real prompt.ts.
//
// The golden files under golden/page-prompt/ exist so the Python port cannot
// drift from the page. When 06 changes prompt.ts (they changed the repair head
// to 160-240 in 6a157cb5), the golden must be re-captured from their source —
// never hand-edited. This loads their TypeScript through vite with a cache dir
// inside my experiments tree, so nothing is written under the 06 worktree.
//
//   node harness/page-prompts.mjs --outdir golden/page-prompt
import { createRequire } from 'node:module';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';

const FRONTEND = 'D:/others/Jity/.local/parallel-local-game/worktrees/06-recovery/frontend';
const CACHE = path.resolve('experiments/narration-runtime-v2/.vite-cache');
const WORLD = 'D:/others/Jity/.local/parallel-local-game/worktrees/06-recovery/frontend/public/worlds/dragon-raja-free-day.world.json';

async function main() {
  const args = { outdir: 'golden/page-prompt', draft: 'golden/page-prompt/draft.txt', view: '' };
  for (let i = 2; i < process.argv.length; i += 2) args[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
  mkdirSync(CACHE, { recursive: true });
  const require = createRequire(path.join(FRONTEND, 'package.json'));
  const vite = await import('file://' + require.resolve('vite').replace(/\\/g, '/'));
  const server = await vite.createServer({
    root: FRONTEND, cacheDir: CACHE, configFile: false, logLevel: 'error',
    server: { middlewareMode: true, hmr: false }, appType: 'custom',
  });
  try {
    const prompt = await server.ssrLoadModule('/src/lib/world-engine/local/prompt.ts');
    const loader = await server.ssrLoadModule('/src/lib/world-engine/local/world-loader.ts');
    const worldText = readFileSync(WORLD, 'utf8');
    const read = loader.readStaticWorldValue(JSON.parse(worldText));
    const state = read.state;
    let view = args.view || state.protagonistId;
    if (args['view-name']) {
      const hit = Object.entries(state.initial.characters).find(([, ch]) => ch.name === args['view-name']);
      if (!hit) throw new Error('viewpoint name not in world: ' + args['view-name']);
      view = hit[0];
    }
    const draft = readFileSync(path.resolve(args.draft), 'utf8').replace(/\r\n/g, '\n').trim();
    const out = {};
    for (const mode of ['scene', 'repair']) {
      const rendered = prompt.instructNarrationInput(null, {}, state, view, '', '', draft, mode);
      out[mode] = rendered.prompt;
      writeFileSync(path.join(args.outdir, `ts-${mode}.txt`), rendered.prompt + '\n', 'utf8');
    }
    writeFileSync(path.join(args.outdir, 'capture.json'), JSON.stringify({
      capturedFrom: 'worktrees/06-recovery/frontend/src/lib/world-engine/local/prompt.ts',
      world: 'public/worlds/dragon-raja-free-day.world.json',
      viewpointId: view,
      viewpointName: state.initial.characters[view]?.name,
      draftSha256Note: 'draft.txt unchanged; prompt heads come from the loaded source',
      prompts: { scene: out.scene.length, repair: out.repair.length },
    }, null, 1) + '\n', 'utf8');
    process.stdout.write(JSON.stringify({ view: state.initial.characters[view]?.name, scene: out.scene.length, repair: out.repair.length }) + '\n');
  } finally {
    await server.close();
  }
}

main().catch((error) => { console.error(error); process.exit(1); });
