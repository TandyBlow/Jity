// Template identification probe (raw completion).
//
// The narration checkpoints were trained as raw continuations
// (`【状态】<json>\n【视角】…\n【叙事】`) or as ChatML instruct turns. The page
// adapter always goes through `createChatCompletion`, which wraps the prompt in
// the model's chat template; that is right for the instruct arm and wrong for
// the raw arm. This probe calls `createCompletion` directly so both shapes can
// be compared on the same facts, and records which one the weights actually
// continue.
//
//   node scripts/parallel-narration/probe-template.mjs \
//     --model /models/qwen25-1.5b-narr-Q4_K_M.gguf \
//     --out ../../../results/quality/template-probe.json
import { createHash } from 'node:crypto';
import { createReadStream, existsSync, mkdirSync, readFileSync, renameSync, statSync, writeFileSync } from 'node:fs';
import { cpus } from 'node:os';
import { basename, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { createServer } from 'vite';

const require = createRequire(resolve('package.json'));
const { chromium } = require('@playwright/test');
const frontend = fileURLToPath(new URL('../..', import.meta.url));
const option = (flag, fallback) => (process.argv.includes(flag) ? process.argv[process.argv.indexOf(flag) + 1] : fallback);
const config = {
  model: (() => {
    const value = option('--model', '/models/qwen25-1.5b-narr-Q4_K_M.gguf');
    return value.startsWith('/models/') ? value : `/models/${basename(value)}`;
  })(),
  out: resolve(frontend, option('--out', '../../../results/quality/template-probe.json')),
  modelDir: process.env.MODEL_DIR ?? 'D:/others/Jity/.local/world-narration-worktree/frontend/public/models',
  channel: option('--channel', 'msedge'),
  threads: Number(option('--threads', '4')),
  maxTokens: Number(option('--max-tokens', '220')),
};
const sha256 = (bytes) => createHash('sha256').update(bytes).digest('hex');
const modelFile = resolve(config.modelDir, basename(config.model));
const evidence = {
  status: 'IN_PROGRESS',
  recordedAt: new Date().toISOString(),
  config: {
    ...config,
    modelSha256: existsSync(modelFile) ? sha256(readFileSync(modelFile)) : null,
    modelBytes: existsSync(modelFile) ? statSync(modelFile).size : null,
  },
  device: { cpu: cpus()[0]?.model, logicalCpus: cpus().length, platform: process.platform },
  prompts: [],
};
const save = () => {
  mkdirSync(dirname(config.out), { recursive: true });
  const temp = `${config.out}.tmp`;
  writeFileSync(temp, `${JSON.stringify(evidence, null, 2)}\n`);
  renameSync(temp, config.out);
};

function assetMiddleware(vite) {
  const wllamaRoot = resolve(frontend, 'node_modules/@wllama/wllama/esm');
  const map = {
    '/wllama/index.min.js': { file: resolve(wllamaRoot, 'index.min.js'), type: 'application/javascript' },
    '/wasm/wllama.wasm': { file: resolve(wllamaRoot, 'wasm/wllama.wasm'), type: 'application/wasm' },
  };
  vite.middlewares.use((request, response, next) => {
    response.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
    response.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
    const url = (request.url ?? '').split('?')[0];
    if (url === '/__probe') {
      response.setHeader('Content-Type', 'text/html');
      response.end('<!doctype html><title>template probe</title>');
      return;
    }
    if (url.startsWith('/models/')) {
      const file = resolve(config.modelDir, basename(url));
      if (!existsSync(file)) { response.statusCode = 404; response.end('missing model'); return; }
      response.setHeader('Content-Type', 'application/octet-stream');
      response.setHeader('Content-Length', statSync(file).size);
      createReadStream(file).pipe(response);
      return;
    }
    const asset = map[url];
    if (asset) {
      if (!existsSync(asset.file)) { response.statusCode = 404; response.end('missing asset'); return; }
      response.setHeader('Content-Type', asset.type);
      createReadStream(asset.file).pipe(response);
      return;
    }
    next();
  });
}

const server = await createServer({
  root: frontend, configFile: false, logLevel: 'warn',
  server: { host: '127.0.0.1', port: 0, hmr: false },
  plugins: [{ name: 'template-probe-assets', configureServer: assetMiddleware }],
});
let browser;
try {
  await server.listen();
  const port = server.httpServer.address().port;
  browser = await chromium.launch({ headless: true, channel: config.channel });
  evidence.browser = browser.version();
  const page = await browser.newPage();
  page.on('pageerror', (error) => console.error('[pageerror]', error.message));
  await page.goto(`http://127.0.0.1:${port}/__probe`);
  const result = await page.evaluate(async (config) => {
    if (!crossOriginIsolated) throw new Error('template probe requires cross-origin isolation');
    const { createWllama } = await import('/src/lib/benchmark/wllama-loader.ts');
    const {
      renderTrainedInstructUser, renderTrainedRawPrompt, trainedSceneView, wrapChatml,
    } = await import('/src/lib/world-engine/local/narration-generation/trained-input.ts');
    const { legacyNarrationInput } = await import('/src/lib/world-engine/local/prompt.ts');
    const { SHORT_STATE } = await import('/src/lib/world-engine/runtime/b3-short-samples.ts');
    const clone = (value) => JSON.parse(JSON.stringify(value));
    const position = (containerId) => ({ containerId, slotId: null, relativeTo: null });

    const before = clone(SHORT_STATE);
    const after = clone(SHORT_STATE);
    after.characters.person_a.position = position('hall');
    const delta = { person_a: { entityId: 'person_a', positionSet: position('hall') } };
    const timeAdvance = { boundary: 'instant', duration: { amount: 0, unit: 'second' } };
    const view = trainedSceneView({ before, after, delta, timeAdvance });
    const legacy = legacyNarrationInput(before, { timeAdvance, entityDeltas: delta }, after, 'person_c');
    const system = '你是叙事引擎。根据给定的世界状态写出这一回合的小说正文。只写已结算的事实，不新增人物、物品、事件或往事；对话用「」；直接输出正文。';
    const prompts = [
      { id: 'trained-raw', kind: 'raw', text: renderTrainedRawPrompt(view) },
      { id: 'legacy-raw', kind: 'raw', text: legacy },
      { id: 'trained-instruct', kind: 'raw', text: wrapChatml(system, renderTrainedInstructUser(view)) },
      { id: 'trained-instruct-user', kind: 'raw', text: `${system}\n\n${renderTrainedInstructUser(view)}\n\n正文：` },
    ];

    const instance = await createWllama();
    const loadStarted = performance.now();
    const response = await fetch(config.model);
    if (!response.ok) throw new Error(`model fetch failed: ${response.status}`);
    const blob = await response.blob();
    await instance.loadModel([blob], { n_ctx: 4096, n_gpu_layers: 0, n_threads: config.threads });
    const loadMs = performance.now() - loadStarted;

    const results = [];
    for (const prompt of prompts) {
      const started = performance.now();
      let raw = '';
      let finishReason = null;
      await instance.createCompletion({
        prompt: prompt.text,
        max_tokens: config.maxTokens,
        temperature: 0.6,
        seed: 42,
        stream: true,
        onData: (chunk) => {
          const choice = chunk.choices?.[0];
          raw += choice?.delta?.content ?? '';
          if (choice?.finish_reason) finishReason = choice.finish_reason;
        },
        abortSignal: AbortSignal.timeout(180_000),
      });
      results.push({
        id: prompt.id, kind: prompt.kind, prompt: prompt.text, promptChars: prompt.text.length,
        raw, chars: [...raw].length, finishReason,
        durationMs: performance.now() - started,
      });
      console.log(`[probe] ${prompt.id}: chars=${[...raw].length} ms=${Math.round(performance.now() - started)}`);
    }
    await instance.exit();
    return { loadMs, results };
  }, config);
  evidence.status = 'DONE';
  evidence.loadMs = result.loadMs;
  evidence.prompts = result.results;
  save();
  console.log(JSON.stringify({ out: config.out, model: config.model, loadMs: Math.round(result.loadMs) }, null, 2));
} catch (error) {
  evidence.status = 'FAILED';
  evidence.error = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
  save();
  throw error;
} finally {
  await browser?.close();
  await server.close();
}
