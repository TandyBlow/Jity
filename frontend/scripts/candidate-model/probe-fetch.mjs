// Can the browser actually read a multi-GB GGUF from the model host?
//
// Loads no model and runs no inference. It answers the question the Qwen3-4B
// load raised: does the URL support HEAD, byte ranges and a streaming body,
// and what exactly fails when wllama's reader asks for the file?
import { createServer } from 'node:http';
import { existsSync } from 'node:fs';
import { basename, resolve } from 'node:path';
import { chromium } from '@playwright/test';
import { sendGguf } from './gguf-server.mjs';

const option = (flag, fallback) => (process.argv.includes(flag) ? process.argv[process.argv.indexOf(flag) + 1] : fallback);
const name = option('--file', 'Qwen3-4B-Instruct-2507-Q4_K_M.gguf');
const dirs = process.argv.includes('--models-dir')
  ? [option('--models-dir', '')]
  : [
    'D:/others/Jity/.local/models',
    'D:/others/Jity/.local/world-narration-worktree/frontend/public/models',
    'D:/others/Jity/frontend/public/models',
  ];
const file = dirs.map((dir) => resolve(dir, name)).find((candidate) => existsSync(candidate));
if (!file) throw new Error(`missing ${name} in ${dirs.join(', ')}`);

const server = createServer((request, response) => {
  response.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
  response.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
  const url = (request.url ?? '').split('?')[0];
  if (url.startsWith('/models/')) {
    const wanted = basename(decodeURIComponent(url));
    if (wanted !== basename(file)) { response.statusCode = 404; response.end('wrong file'); return; }
    sendGguf(request, response, file);
    return;
  }
  response.setHeader('Content-Type', 'text/html; charset=utf-8');
  response.end('<!doctype html><meta charset="utf-8"><title>fetch probe</title>');
});
await new Promise((done) => server.listen(0, '127.0.0.1', done));
const origin = `http://127.0.0.1:${server.address().port}`;
const url = `${origin}/models/${encodeURIComponent(basename(file))}`;

const browser = await chromium.launch({ headless: true, channel: option('--channel', 'msedge'), args: ['--force_high_performance_gpu', '--enable-unsafe-webgpu'] });
try {
  const page = await browser.newPage();
  page.on('requestfailed', (request) => console.log(`[requestfailed] ${request.method()} ${request.url()} ${request.failure()?.errorText}`));
  page.on('console', (message) => { if (message.type() === 'error') console.log('[console.error]', message.text().slice(0, 200)); });
  await page.goto(origin);
  const result = await page.evaluate(async (modelUrl) => {
    const out = {};
    const head = await fetch(modelUrl, { method: 'HEAD' });
    out.head = { status: head.status, length: Number(head.headers.get('content-length')), ranges: head.headers.get('accept-ranges'), type: head.headers.get('content-type') };
    const ranged = await fetch(modelUrl, { headers: { Range: 'bytes=0-1023' } });
    const rangedBytes = await ranged.arrayBuffer();
    out.range = { status: ranged.status, bytes: rangedBytes.byteLength, contentRange: ranged.headers.get('content-range') };
    try {
      const full = await fetch(modelUrl);
      out.get = { status: full.status, length: Number(full.headers.get('content-length')) };
      const reader = full.body.getReader();
      let read = 0;
      while (read < 1024 * 1024) {
        const { done, value } = await reader.read();
        if (done) break;
        read += value.byteLength;
      }
      await reader.cancel();
      out.stream = { read };
    } catch (error) {
      out.stream = { error: String(error?.message ?? error) };
    }
    try {
      const full = await fetch(modelUrl);
      const buffer = await full.arrayBuffer();
      out.arrayBuffer = { bytes: buffer.byteLength };
    } catch (error) {
      out.arrayBuffer = { error: String(error?.message ?? error) };
    }
    return out;
  }, url);
  console.log(JSON.stringify(result, null, 2));
} finally {
  await browser.close();
  await new Promise((done) => server.close(done));
}
