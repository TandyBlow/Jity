// Does the browser itself hold two GGUF shards (2.5 GB total) at once?
//
// Loads no model and runs no inference. This isolates the split-4B failure:
// wllama's loader fetches each shard into a Blob and keeps all of them until
// loadModel() finishes, so if the browser's Blob store cannot hold the
// aggregate, no amount of splitting at the wllama layer helps.
import { createServer } from 'node:http';
import { existsSync, writeFileSync } from 'node:fs';
import { basename, resolve } from 'node:path';
import { chromium } from '@playwright/test';
import { sendGguf } from './gguf-server.mjs';

const option = (flag, fallback) => (process.argv.includes(flag) ? process.argv[process.argv.indexOf(flag) + 1] : fallback);
const dir = resolve(option('--dir', '.local/models/qwen3-4b-split'));
const mode = option('--mode', 'blob');
const channel = option('--channel', 'msedge');
const outPath = option('--out', null);
const files = process.argv.includes('--file')
  ? process.argv.slice(process.argv.indexOf('--file') + 1).filter((value) => !value.startsWith('--'))
  : [
    'Qwen3-4B-Instruct-2507-Q4_K_M.gguf-00001-of-00002.gguf',
    'Qwen3-4B-Instruct-2507-Q4_K_M.gguf-00002-of-00002.gguf',
  ];
const paths = files.map((name) => resolve(dir, name));
for (const path of paths) if (!existsSync(path)) throw new Error(`missing ${path}`);

const server = createServer((request, response) => {
  response.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
  response.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
  const path = (request.url ?? '').split('?')[0];
  if (path.startsWith('/models/')) {
    const wanted = basename(decodeURIComponent(path));
    const file = paths.find((candidate) => basename(candidate) === wanted);
    if (!file) { response.statusCode = 404; response.end('wrong file'); return; }
    sendGguf(request, response, file);
    return;
  }
  response.setHeader('Content-Type', 'text/html; charset=utf-8');
  response.end('<!doctype html><meta charset="utf-8"><title>two-shard probe</title>');
});
await new Promise((done) => server.listen(0, '127.0.0.1', done));
const origin = `http://127.0.0.1:${server.address().port}`;
const urls = paths.map((path) => `${origin}/models/${encodeURIComponent(basename(path))}`);

const browser = await chromium.launch({ headless: true, channel, args: ['--force_high_performance_gpu', '--enable-unsafe-webgpu'] });
try {
  const page = await browser.newPage();
  page.on('requestfailed', (request) => {
    if (/\/models\//.test(request.url())) console.log(`[requestfailed] ${request.url()} ${request.failure()?.errorText}`);
  });
  await page.goto(origin);
  const result = await page.evaluate(async ({ urls, mode }) => {
    const heap = () => (performance.memory ? {
      usedMB: Math.round(performance.memory.usedJSHeapSize / 1048576),
      totalMB: Math.round(performance.memory.totalJSHeapSize / 1048576),
      limitMB: Math.round(performance.memory.jsHeapSizeLimit / 1048576),
    } : null);
    const kept = [];
    const steps = [];
    const estimate = navigator.storage?.estimate ? await navigator.storage.estimate() : null;
    for (const url of urls) {
      const step = { url, mode, ok: false, bytes: null, elapsedMs: null, error: null, heapBefore: heap() };
      const started = performance.now();
      try {
        const response = await fetch(url);
        step.status = response.status;
        step.contentLength = Number(response.headers.get('content-length'));
        const body = mode === 'arraybuffer' ? await response.arrayBuffer() : await response.blob();
        kept.push(body);
        step.bytes = body.size ?? body.byteLength;
        step.ok = true;
      } catch (error) {
        step.error = `${error?.name ?? 'Error'}: ${error?.message ?? error}`;
      }
      step.elapsedMs = Math.round(performance.now() - started);
      step.heapAfter = heap();
      steps.push(step);
    }
    return { steps, kept: kept.length, estimate };
  }, { urls, mode });
  const payload = { checkedAt: new Date().toISOString(), browser: await browser.version(), mode, dir, files, result };
  const text = JSON.stringify(payload, null, 2);
  if (outPath) writeFileSync(resolve(outPath), `${text}
`);
  console.log(text);
} finally {
  await browser.close();
  await new Promise((done) => server.close(done));
}
