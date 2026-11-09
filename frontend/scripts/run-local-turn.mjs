/* Real-browser single-turn probe for the local (no-HTTP) game loop.
 * Usage: node scripts/run-local-turn.mjs --model /models/Qwen3-0.6B-Q4_K_M.gguf
 * It starts Vite, opens headless Edge, loads the static Dragon Raja world,
 * settles one player action entirely in the page, and writes a JSON report.
 * No backend, no remote model, no visible browser window. */
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { writeFileSync, mkdirSync } from 'node:fs';

const require = createRequire(resolve('package.json'));
const { createServer } = await import(pathToFileURL(require.resolve('vite')).href);
const { chromium } = require('@playwright/test');

const args = process.argv.slice(2);
const arg = (name, fallback) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : fallback; };
const model = arg('--model', '/models/Qwen3-0.6B-Q4_K_M.gguf');
const narrationModel = arg('--narration-model', '/models/qwen25-0.5b-narration-Q4_K_M.gguf');
const input = arg('--input', '我握紧护目镜，沿着车道向西回廊快走，尽量贴墙，注意听枪声。');
const out = arg('--out', '../artifacts/local-game/local-turn.json');
const timeoutMs = Number(arg('--timeout', '420000'));

const server = await createServer({
  root: process.cwd(), configFile: false, logLevel: 'warn',
  server: { host: '127.0.0.1', port: 0 },
  plugins: [{ name: 'local-probe', configureServer(v) {
    v.middlewares.use((req, res, next) => {
      if (req.url !== '/__local_turn') return next();
      res.setHeader('Content-Type', 'text/html');
      res.end('<!doctype html><meta charset="utf-8"><title>local turn</title>');
    });
  } }],
});
await server.listen();
const origin = `http://127.0.0.1:${server.config.server.port}`;
const browser = await chromium.launch({ headless: true, channel: 'msedge', args: ['--enable-unsafe-webgpu'] });
const page = await browser.newPage();
page.on('console', (m) => console.log(`[page:${m.type()}] ${m.text().slice(0, 800)}`));
page.on('pageerror', (e) => console.log(`[pageerror] ${e.message}`));
await page.goto(`${origin}/__local_turn`);

const result = await page.evaluate(async ({ model, narrationModel, input, timeoutMs }) => {
  const t0 = performance.now();
  let quota = null;
  try { quota = await navigator.storage?.estimate?.(); } catch {}
  const world = await (await fetch('/worlds/dragon-raja-free-day.world.json')).json();
  const { WllamaInferenceEngine } = await import('/src/lib/world-engine/runtime/wllama-engine.ts');
  const { LocalGameModel } = await import('/src/lib/world-engine/local/game-model.ts');
  const { LocalGameSession } = await import('/src/lib/world-engine/local/session.ts');
  const tasks = [];
  const narration = { firstAt: null, chunks: 0, text: '' };
  let engine;
  let narrationEngine;
  let session;
  try {
    const engineStarted = performance.now();
    engine = new WllamaInferenceEngine({ modelUrl: model, contextSize: 6144, nGpuLayers: 99999 });
    await engine.load();
    const loadMs = performance.now() - engineStarted;
    narrationEngine = new WllamaInferenceEngine({ modelUrl: narrationModel, contextSize: 4096, nGpuLayers: 99999 });
    await narrationEngine.load();
    const modelPort = new LocalGameModel(engine, {
      narrationEngine,
      onTask: (task, key, detail) => { tasks.push({ task, key, ...detail, raw: detail.raw?.slice(0, 600) }); console.log(`[task] ${task} ${key} ${Math.round(detail.ms)}ms fallback=${detail.fallback} ${detail.error ?? ''}`); },
      onNarrationProgress: (p) => { if (narration.firstAt === null) narration.firstAt = performance.now() - t0; narration.chunks += 1; narration.text = p.raw; },
      onNarrationComplete: (p) => console.log(`[narration] ${p.raw.length} chars`),
    });
    const port = { generate: async (task, key, input) => task === 'continuation' ? { kind: 'handback', closedBy: 'model', cancelReason: null } : modelPort.generate(task, key, input) };
    session = await LocalGameSession.create(world.initial, port, { worldId: world.worldId });
    await session.start();
    const turnStart = performance.now();
    const status = await Promise.race([
      session.submit(input),
      new Promise((_, reject) => setTimeout(() => reject(new Error('turn_timeout')), timeoutMs)),
    ]);
    const turnMs = performance.now() - turnStart;
    const state = await session.state();
    const context = await session.transport.execute('get_context', {}, { worldId: session.worldId });
    return { ok: true, loadMs, turnMs, status, tasks, narration, state, context, quota, snapshot: session.snapshot };
  } catch (error) {
    let state = null; let context = null;
    try { state = await session?.state(); } catch {}
    try { context = await session?.transport.execute('get_context', {}, { worldId: session.worldId }); } catch {}
    return { ok: false, error: error instanceof Error ? `${error.name}: ${error.message}` : String(error), stack: error instanceof Error ? error.stack : undefined, quota, tasks, narration, state, context };
  } finally {
    try { await engine?.dispose(); } catch {}
    try { await narrationEngine?.dispose(); } catch {}
  }
}, { model, narrationModel, input, timeoutMs });

mkdirSync(resolve(out, '..'), { recursive: true });
writeFileSync(resolve(out), JSON.stringify(result, null, 2), 'utf8');
console.log(JSON.stringify({ ok: result.ok, error: result.error, loadMs: result.loadMs, turnMs: result.turnMs, tasks: result.tasks?.length, narrationChars: result.narration?.text?.length, finalTime: result.state?.time, model }, null, 2));
await browser.close();
await server.close();
