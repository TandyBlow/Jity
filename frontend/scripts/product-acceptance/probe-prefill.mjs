// Prefill probe: one long Chinese prompt, several wllama batch configs.
// Measures first-token latency (prefill) and decode on the delivery 0.6B.
// Usage: node scripts/product-acceptance/probe-prefill.mjs

import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
import { acquireLease } from './lease.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const base = 'http://127.0.0.1:3177';
const out = resolve(root, 'artifacts/goal/narration/prefill-probe.json');

const paragraph = '路明非站在西侧服务巷的墙边，黄黑绳已经放下，右墙贴着赛区路线图，器材棚门敞开着。'
  + '他低头检查护目镜，镜片没有裂纹，镜带松着挂在胸前；演习背心前襟完好，没有演习弹痕，胸袋能放一只弹匣。'
  + '巷子尽头的低墙挡住庭院视线，墙角留着新鲜的演习弹红痕。诺诺在巷口，红发用发圈束在脑后，红色识别带缠在左臂。'
  + '远处钟楼的铜钟敲了两下，声音在楼宇之间散开。赛区图上画出庭院、东西回廊、跨溪小桥、钟楼与白线撤离路。';
const longText = Array.from({ length: 30 }, () => paragraph).join('');
const system = '你是中文小说续写助手。严格遵守给定前缀的事实、人物与文风，直接续写正文，不要标题、解释或总结。';
const configs = [
  { n_batch: 512, n_ubatch: 128 },
  { n_batch: 1024, n_ubatch: 256 },
  { n_batch: 2048, n_ubatch: 512 },
  { n_batch: 512, n_ubatch: 512 },
];

const lease = acquireLease({ purpose: 'G6 prefill probe' });
const browser = await chromium.launch({
  headless: true,
  channel: 'msedge',
  args: ['--enable-unsafe-webgpu', '--force_high_performance_gpu', '--ignore-gpu-blocklist'],
});
const evidence = { kind: 'jity-prefill-probe', at: new Date().toISOString(), chars: longText.length, configs: [] };
try {
  const page = await browser.newPage();
  await page.goto(`${base}/benchmark`, { waitUntil: 'domcontentloaded', timeout: 120000 });
  for (const config of configs) {
    const result = await page.evaluate(async ({ systemText, userText, nBatch, nUbatch }) => {
      const { Wllama } = await import('/wllama/index.min.js');
      const instance = new Wllama({ default: '/wasm/wllama.wasm' }, { logger: { ...console, debug: () => undefined } });
      const response = await fetch('/models/Qwen3-0.6B-Q4_K_M.gguf');
      const blob = await response.blob();
      const loadStarted = performance.now();
      await instance.loadModel([blob], {
        n_ctx: 12288, n_batch: nBatch, n_ubatch: nUbatch,
        n_gpu_layers: 99, warmup: false, n_threads: 4,
      });
      const loadMs = Math.round(performance.now() - loadStarted);
      const started = performance.now();
      const completion = await instance.createChatCompletion({
        messages: [
          { role: 'system', content: systemText },
          { role: 'user', content: userText },
        ],
        max_tokens: 48,
        temperature: 0.7,
        top_p: 0.9,
        seed: 20261122,
        cache_prompt: false,
        chat_template_kwargs: { enable_thinking: false },
      });
      const wallMs = Math.round(performance.now() - started);
      const usage = completion.usage ?? {};
      await instance.exit();
      return {
        loadMs, wallMs,
        promptTokens: usage.prompt_tokens ?? null,
        completionTokens: usage.completion_tokens ?? null,
      };
    }, { systemText: system, userText: longText, nBatch: config.n_batch, nUbatch: config.n_ubatch });
    evidence.configs.push({ ...config, ...result });
    console.log(`[${config.n_batch}/${config.n_ubatch}] load=${result.loadMs}ms promptTok=${result.promptTokens} wall=${result.wallMs}ms`);
  }
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
