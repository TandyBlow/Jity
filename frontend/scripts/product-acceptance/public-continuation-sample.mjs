// G6 4.3 baseline: run the five public Chinese continuations through the
// delivery narration GGUF in the product's own wllama runtime.
// Usage: node scripts/product-acceptance/public-continuation-sample.mjs [--base URL] [--model URL] [--samples 3]

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
import { acquireLease } from './lease.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const arg = (name, fallback) => {
  const index = process.argv.indexOf(name);
  return index > 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
};
const base = arg('--base', 'http://127.0.0.1:3177').replace(/\/$/, '');
const modelUrl = arg('--model', '/models/Qwen3-1.7B-Q4_K_M.gguf');
const samples = Number(arg('--samples', '3'));
const mode = arg('--mode', 'single'); // single | draft-polish
const out = resolve(root, arg('--out', 'artifacts/goal/narration/public-continuations-baseline-20261122.json'));
const prompts = JSON.parse(readFileSync(resolve(here, 'narration-prompts-public.json'), 'utf8'));

const SYSTEM = '你是中文小说续写助手。严格遵守给定前缀的事实、人物与文风，直接续写正文，不要标题、解释、总结或任何说明。';

const lease = acquireLease({ purpose: `G6 public continuation baseline ${base}` });
const browser = await chromium.launch({
  headless: true,
  channel: 'msedge',
  args: ['--enable-unsafe-webgpu', '--force_high_performance_gpu', '--ignore-gpu-blocklist'],
});
const evidence = { kind: 'jity-g6-public-continuations', at: new Date().toISOString(), base, model: modelUrl, samples, prompts: [], lease: lease.record };

try {
  const page = await browser.newPage();
  await page.goto(`${base}/benchmark`, { waitUntil: 'domcontentloaded', timeout: 120000 });
  // Blob load: loadModelFromUrl hits the browser OPFS quota on this box.
  await page.evaluate(async ({ url }) => {
    const { Wllama } = await import('/wllama/index.min.js');
    const instance = new Wllama(
      { default: '/wasm/wllama.wasm' },
      { logger: { ...console, debug: () => undefined } },
    );
    const response = await fetch(url);
    if (!response.ok) throw new Error(`model fetch ${response.status}`);
    const blob = await response.blob();
    const started = performance.now();
    await instance.loadModel([blob], {
      n_ctx: 4096, n_batch: 512, n_ubatch: 128,
      n_gpu_layers: 99, warmup: false, n_threads: 4,
    });
    window.__evalWllama = instance;
    window.__evalLoadMs = Math.round(performance.now() - started);
  }, { url: modelUrl.startsWith('http') ? modelUrl : `${base}${modelUrl}` });
  evidence.loadMs = await page.evaluate(() => window.__evalLoadMs);
  console.log(`[load] ${evidence.loadMs}ms`);

  for (const prompt of prompts) {
    const entry = { id: prompt.id, source: prompt.source, outputs: [] };
    for (let index = 0; index < samples; index += 1) {
      const result = await page.evaluate(async ({ system, user, seed, mode }) => {
        const call = async (systemText, userText, maxTokens) => {
          const started = performance.now();
          const response = await window.__evalWllama.createChatCompletion({
            messages: [
              { role: 'system', content: systemText },
              { role: 'user', content: userText },
            ],
            max_tokens: maxTokens,
            temperature: 0.7,
            top_p: 0.9,
            seed,
            cache_prompt: false,
            chat_template_kwargs: { enable_thinking: false },
          });
          return {
            wallMs: Math.round(performance.now() - started),
            text: response.choices?.[0]?.message?.content ?? '',
            finishReason: response.choices?.[0]?.finish_reason ?? null,
            completionTokens: response.usage?.completion_tokens ?? null,
          };
        };
        const totalStarted = performance.now();
        if (mode !== 'draft-polish') {
          const single = await call(system, user, 320);
          return { ...single, wallMs: Math.round(performance.now() - totalStarted) };
        }
        // Two-stage composition on the same weights: draft, then polish against
        // the prefix. Cheapest faithful test of the many-small-passes hypothesis.
        const draft = await call(system, user, 320);
        const polish = await call(
          '你是中文小说编辑。只修正错别字、重复和与给定前缀事实矛盾的地方，保持情节、人称与长度；不要添加新情节，不要写说明。输出润色后的全文。',
          `${user}

【草稿】
${draft.text}`,
          320,
        );
        return {
          wallMs: Math.round(performance.now() - totalStarted),
          text: polish.text,
          finishReason: polish.finishReason,
          completionTokens: (draft.completionTokens ?? 0) + (polish.completionTokens ?? 0),
          draft,
          polish,
        };
      }, { system: SYSTEM, user: `${prompt.prefix}

${prompt.instruction}`, seed: 20261122 + index, mode });
      entry.outputs.push(result);
      console.log(`[${prompt.id}] sample ${index + 1}: ${result.completionTokens} tok in ${(result.wallMs / 1000).toFixed(1)}s finish=${result.finishReason}`);
    }
    evidence.prompts.push(entry);
  }
  await page.evaluate(async () => { await window.__evalWllama?.exit(); });
} catch (error) {
  evidence.error = error instanceof Error ? error.message : String(error);
} finally {
  await browser.close().catch(() => undefined);
  lease.release();
}

mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, JSON.stringify(evidence, null, 2) + '\n');
console.log(`${evidence.error ? 'FAILED' : 'DONE'} -> ${out}`);
process.exitCode = evidence.error ? 1 : 0;
