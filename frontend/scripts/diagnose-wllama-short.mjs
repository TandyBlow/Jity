// SHORT wllama diagnostic for the B3 baseline failures — a handful of SMALL
// requests, NOT a re-run. Attribution targets:
//  (a) where the time goes: first-token latency (prefill) vs decode rate,
//      with real token counts and finish reasons captured via onNewToken;
//  (b) why structure decodes rejected: compare the RAW completion path (the
//      current B3 adapter behavior: no chat template, thinking NOT disabled,
//      no constrained decode) against the CHAT path (chat template +
//      enable_thinking:false) with and without a json_schema constraint;
//  (c) thread topology actually observed in this page.
// Single-thread defaults matching the B3 runner page (no COOP/COEP).
// Report lands in artifacts/wllama-diagnostic.json. Child server closed in
// finally. Nothing here draws model-capability conclusions — it only
// localizes the failure mode of THIS configuration.
//
// Run: node scripts/diagnose-wllama-short.mjs [--channel msedge] [--model /models/Qwen3-0.6B-Q4_K_M.gguf]
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { writeFileSync, mkdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = resolve(frontendRoot, '..');

const args = process.argv.slice(2);
const argValue = (name, fallback) => {
  const index = args.indexOf(name);
  return index !== -1 && args[index + 1] !== undefined ? args[index + 1] : fallback;
};
const CONFIG = {
  channel: argValue('--channel', 'msedge'),
  model: argValue('--model', '/models/Qwen3-0.6B-Q4_K_M.gguf'),
  maxTokens: 48,
  seed: 42,
};
const OUTPUT = resolve(repoRoot, argValue('--out', 'artifacts/wllama-diagnostic.json'));

const require = createRequire(resolve(frontendRoot, 'package.json'));
const { createServer } = await import(pathToFileURL(require.resolve('vite')).href);
const { chromium } = require('@playwright/test');

const server = await createServer({
  root: frontendRoot,
  configFile: false,
  logLevel: 'warn',
  server: { host: '127.0.0.1', port: 0, strictPort: false, hmr: false },
  plugins: [{
    name: 'wllama-diagnostic-page',
    configureServer(vite) {
      vite.middlewares.use((req, res, next) => {
        if (req.url !== '/__diag') return next();
        res.setHeader('Content-Type', 'text/html');
        res.end('<!doctype html><title>Jity wllama diagnostic</title>');
      });
    },
  }],
});
await server.listen();
const port = server.config.server.port ?? server.config.server.inferredPort;
const origin = `http://127.0.0.1:${port}`;
console.log(`[diag] vite at ${origin}; model ${CONFIG.model}`);

let browser;
try {
  browser = await chromium.launch({ headless: true, channel: CONFIG.channel });
  const page = await browser.newPage();
  page.on('pageerror', (error) => console.error('[pageerror]', error.message));
  page.on('console', (message) => {
    const text = message.text();
    if (message.type() === 'error') console.error('[console.error]', text);
    else console.log(`[page:${message.type()}]`, text);
  });
  await page.goto(`${origin}/__diag`);

  const outcome = await page.evaluate(async (config) => {
    const { createWllama } = await import('/src/lib/benchmark/wllama-loader.ts');
    const { buildTaskPrompt } = await import('/src/lib/world-engine/runtime/prompts.ts');
    const { B3_SAMPLES } = await import('/src/lib/world-engine/runtime/b3-samples.ts');

    const instance = await createWllama();
    await instance.loadModelFromUrl(config.model, { n_ctx: 4096, n_gpu_layers: 0 });
    const topology = { multithread: instance.isMultithread(), numThreads: instance.getNumThreads() };
    console.log(`[diag] loaded: multithread=${topology.multithread} threads=${topology.numThreads}`);

    // A real frozen B3 task prompt (action task, longest realistic shape).
    const actionSample = B3_SAMPLES.find((s) => s.id === 'action-1');
    const prompt = buildTaskPrompt('action', actionSample.key, actionSample.input);
    const schema = {
      type: 'object',
      properties: { kind: { type: 'string', enum: ['act', 'skip'] }, text: { type: 'string' } },
      required: ['kind'],
    };

    /** Streams a raw completion (stream:true + onData — the NON-stream path
     * never fires a token callback, which is why the first probe attempt saw
     * zero tokens), counting chunks and capturing first-token latency plus
     * whatever usage/finish metadata wllama attaches to the final chunk. */
    async function rawProbe(name, promptText, maxTokens, cachePrompt) {
      const started = performance.now();
      let firstTokenMs = null;
      let tokens = 0;
      let text = '';
      let lastChunk = null;
      await instance.createCompletion({
        prompt: promptText,
        max_tokens: maxTokens,
        temperature: 0,
        seed: config.seed,
        cache_prompt: cachePrompt,
        stream: true,
        onData: (chunk) => {
          tokens += 1;
          if (firstTokenMs == null) firstTokenMs = performance.now() - started;
          const piece = typeof chunk === 'string' ? chunk : chunk?.choices?.[0]?.text ?? '';
          text += piece;
          try { lastChunk = JSON.parse(JSON.stringify(chunk)); } catch { lastChunk = { unserializable: true }; }
        },
      });
      return {
        name, path: 'raw', maxTokens, wallMs: performance.now() - started,
        firstTokenMs, tokens, lastChunkMeta: lastChunk,
        textHead: text.slice(0, 300),
        hasThinkOpen: text.includes('<think>'),
      };
    }

    async function chatProbe(name, promptText, maxTokens, withSchema, cachePrompt) {
      const started = performance.now();
      const request = {
        messages: [{ role: 'user', content: promptText }],
        max_tokens: maxTokens,
        temperature: 0,
        seed: config.seed,
        cache_prompt: cachePrompt,
        chat_template_kwargs: { enable_thinking: false },
        ...(withSchema ? { response_format: { type: 'json_schema', json_schema: { name: 'probe', schema, strict: true } } } : {}),
      };
      const response = await instance.createChatCompletion(request);
      const text = (response.choices?.[0]?.message?.content ?? '').replace(/<think>[\s\S]*?<\/think>/g, '').trim();
      let meta = null;
      try { meta = JSON.parse(JSON.stringify(response.usage ?? response.timings ?? null)); } catch { meta = { unserializable: true }; }
      let parsed = null;
      if (withSchema) {
        try { parsed = JSON.parse(text); } catch { parsed = null; }
      }
      return {
        name, path: withSchema ? 'chat+json_schema' : 'chat', maxTokens, wallMs: performance.now() - started,
        usageOrTimings: meta, textHead: text.slice(0, 300),
        jsonParseOk: withSchema ? parsed != null : null,
      };
    }

    const probes = [];
    console.log('[diag] P0 tiny raw (decode-rate probe, 16 tokens)');
    probes.push(await rawProbe('P0-tiny-raw', '数到三。', 16, false));
    console.log(`[diag] P0 done: ${Math.round(probes[0].wallMs)}ms, firstToken ${Math.round(probes[0].firstTokenMs ?? -1)}ms, tokens ${probes[0].tokens}`);
    console.log('[diag] P1 real B3 action prompt, RAW path (B3 adapter equivalent), 48 tokens');
    probes.push(await rawProbe('P1-action-raw', prompt, config.maxTokens, false));
    console.log(`[diag] P1 done: ${Math.round(probes[1].wallMs)}ms, firstToken ${Math.round(probes[1].firstTokenMs ?? -1)}ms, tokens ${probes[1].tokens}, think=${probes[1].hasThinkOpen}`);
    console.log('[diag] P2 same prompt, CHAT path + thinking off, 48 tokens');
    probes.push(await chatProbe('P2-action-chat', prompt, config.maxTokens, false, false));
    console.log(`[diag] P2 done: ${Math.round(probes[2].wallMs)}ms`);
    console.log('[diag] P3 CHAT + json_schema constraint, 48 tokens (prefix cached from P2)');
    probes.push(await chatProbe('P3-action-chat-schema', prompt, config.maxTokens, true, true));
    console.log(`[diag] P3 done: ${Math.round(probes[3].wallMs)}ms, jsonParseOk=${probes[3].jsonParseOk}`);

    return { topology, promptLengthChars: prompt.length, probes };
  }, CONFIG);

  const payload = {
    status: 'COMPLETED',
    layer: 'short wllama diagnostic; localizes time and structure failures of THIS configuration, no capability conclusions',
    recordedAt: new Date().toISOString(),
    config: CONFIG,
    browser: browser.version(),
    origin,
    ...outcome,
  };
  mkdirSync(dirname(OUTPUT), { recursive: true });
  writeFileSync(OUTPUT, JSON.stringify(payload, null, 2) + '\n');
  console.log(`[diag] done → ${OUTPUT}`);
} finally {
  if (browser) await browser.close();
  await server.close();
}
