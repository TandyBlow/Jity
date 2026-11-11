#!/usr/bin/env node
/**
 * Static server for the action-classifier probe.
 *
 *   node scripts/action-classifier/serve.mjs --root <exportDir> --port 3261
 *
 * Serves:
 *   /                page.html next to this script
 *   /ort/*           onnxruntime-web dist files from node_modules
 *   /model/*         the export directory (model.onnx, vocab.txt, export.json)
 *
 * COOP/COEP are sent on every response so the multithreaded wasm backend stays
 * usable; the page prefers WebGPU when the adapter exists.
 */
import { createServer } from 'node:http';
import { createReadStream, existsSync, statSync } from 'node:fs';
import { extname, join, normalize, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = resolve(fileURLToPath(import.meta.url), '..');
const args = process.argv.slice(2);
const flag = (name, fallback = null) => {
  const index = args.indexOf(`--${name}`);
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback;
};
const root = resolve(flag('root', ''));
const port = Number(flag('port', '3261'));
const ortDir = resolve(here, '../../node_modules/onnxruntime-web/dist');

if (!root || !existsSync(root)) {
  console.error('usage: serve.mjs --root <exportDir> [--port 3261]');
  process.exit(2);
}
if (!existsSync(ortDir)) {
  console.error(`onnxruntime-web dist not found at ${ortDir}`);
  process.exit(2);
}

const types = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8', '.json': 'application/json; charset=utf-8',
  '.onnx': 'application/octet-stream', '.wasm': 'application/wasm',
  '.txt': 'text/plain; charset=utf-8', '.jsonl': 'application/jsonl; charset=utf-8',
};

const server = createServer((request, response) => {
  const url = new URL(request.url, 'http://127.0.0.1');
  const pathname = decodeURIComponent(url.pathname);
  const headers = {
    'cross-origin-opener-policy': 'same-origin',
    'cross-origin-embedder-policy': 'require-corp',
    'cross-origin-resource-policy': 'same-origin',
    'cache-control': 'no-store',
  };
  let file = null;
  if (pathname === '/' || pathname === '/page.html') file = join(here, 'page.html');
  else if (pathname.startsWith('/ort/')) file = join(ortDir, normalize(pathname.slice('/ort/'.length)));
  else if (pathname.startsWith('/model/')) file = join(root, normalize(pathname.slice('/model/'.length)));
  if (!file || !file.startsWith(root) && !file.startsWith(ortDir) && !file.startsWith(here)) {
    response.writeHead(404, headers); response.end('not found'); return;
  }
  if (!existsSync(file) || !statSync(file).isFile()) {
    response.writeHead(404, headers); response.end('not found'); return;
  }
  const stat = statSync(file);
  const type = types[extname(file).toLowerCase()] ?? 'application/octet-stream';
  const range = request.headers.range;
  if (range && /bytes=\d*-\d*/u.test(range)) {
    const [startText, endText] = range.replace(/bytes=/u, '').split('-');
    const start = startText ? Number(startText) : 0;
    const end = endText ? Math.min(Number(endText), stat.size - 1) : stat.size - 1;
    response.writeHead(206, {
      ...headers, 'content-type': type, 'accept-ranges': 'bytes',
      'content-range': `bytes ${start}-${end}/${stat.size}`, 'content-length': end - start + 1,
    });
    createReadStream(file, { start, end }).pipe(response);
    return;
  }
  response.writeHead(200, { ...headers, 'content-type': type, 'content-length': stat.size, 'accept-ranges': 'bytes' });
  createReadStream(file).pipe(response);
});

server.listen(port, '127.0.0.1', () => {
  console.log(`classifier probe on http://127.0.0.1:${port}  root=${root}`);
});
