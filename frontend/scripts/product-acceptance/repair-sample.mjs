// D-022 self-repair prototype: take a failing narration draft plus its own
// prompt, ask the same model once to fix only the fact contradictions.
// Usage: node scripts/product-acceptance/repair-sample.mjs --cases run40-legal-rate-e.json:s06,run37-handback-arm.json:s06 --samples 3 --out artifacts/goal/narration/repair-sample-20261122.json
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
const out = resolve(root, arg('--out', 'artifacts/goal/narration/repair-sample-20261122.json'));
const caseArgs = (arg('--cases', 'run40-legal-rate-e.json:s06,run37-handback-arm.json:s06') || '').split(',').filter(Boolean);

const REPAIR = [
  '上一稿：',
  '@DRAFT@',
  '修订要求：只改与下面事实矛盾的地方：事实里没有发生的动作、被阻止的动作、未登记的人物或物品，不得写成已发生；不要新增事实里没有的人物、对白、物品或动作；其余句子尽量保持，长度可以微调。',
  '',
  '正文：',
].join('\n');

function withDraft(prompt, draft) {
  const marker = '正文：';
  const index = prompt.lastIndexOf(marker);
  const block = REPAIR.replace('@DRAFT@', draft.trim());
  if (index < 0) return `${prompt}\n${block}`;
  return `${prompt.slice(0, index)}${block}`;
}

const lease = acquireLease({ purpose: `D-022 repair sample ${base}` });
const browser = await chromium.launch({
  headless: true,
  channel: 'msedge',
  args: ['--enable-unsafe-webgpu', '--force_high_performance_gpu', '--ignore-gpu-blocklist'],
});
const evidence = { kind: 'jity-d022-repair-sample', at: new Date().toISOString(), base, model: modelUrl, samples, cases: [], lease: lease.record };

try {
  const page = await browser.newPage();
  await page.goto(`${base}/benchmark`, { waitUntil: 'domcontentloaded', timeout: 120000 });
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

  for (const spec of caseArgs) {
    const [file, turnId] = spec.split(':');
    const run = JSON.parse(readFileSync(resolve(root, 'artifacts/goal/semantics', file), 'utf8'));
    const turn = (run.turns ?? []).find((item) => String(item.id).startsWith(turnId));
    if (!turn) throw new Error(`turn ${turnId} not found in ${file}`);
    const prompt = turn.product?.narration?.prompt ?? '';
    const draft = turn.text ?? '';
    if (!prompt.trim() || !draft.trim()) throw new Error(`missing prompt or draft for ${spec}`);
    const repairPrompt = withDraft(prompt, draft);
    const entry = { case: spec, original: draft, repairPromptChars: repairPrompt.length, outputs: [] };
    for (let index = 0; index < samples; index += 1) {
      const started = Date.now();
      const text = await page.evaluate(async ({ promptText }) => {
        const response = await window.__evalWllama.createChatCompletion({
          messages: [{ role: 'user', content: promptText }],
          max_tokens: 320,
          temperature: 0.45,
          top_p: 0.95,
          cache_prompt: false,
          chat_template_kwargs: { enable_thinking: false },
        });
        return response.choices?.[0]?.message?.content ?? '';
      }, { promptText: repairPrompt });
      entry.outputs.push({ wallMs: Date.now() - started, text: String(text).trim() });
      console.log(`[${spec}] sample ${index + 1}: ${String(text).trim().length} chars`);
    }
    evidence.cases.push(entry);
  }
  mkdirSync(dirname(out), { recursive: true });
  writeFileSync(out, JSON.stringify(evidence, null, 1));
  console.log(`DONE -> ${out}`);
} finally {
  await browser.close();
}
