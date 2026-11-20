#!/usr/bin/env node
/**
 * Run the MiniRBT-H256 action classifier in Edge, once-loaded and batched.
 *
 *   node scripts/action-classifier/run.mjs \
 *     --export ../../../results/action-dataset-20261111/export \
 *     --out ../../../results/action-dataset-20261111/runs/classifier-<id>.jsonl \
 *     [--batch 8] [--limit 0] [--port 3261]
 *
 * Preconditions, all checked before a model is loaded:
 *   - export.json exists with model/tokenizer/config/test hashes,
 *   - the hashes match the files on disk,
 *   - the test file hash matches the frozen value,
 *   - the lease is held (use scripts/product-acceptance/run-with-lease.mjs).
 */
import { createHash } from 'node:crypto';
import { createReadStream, existsSync, readFileSync, writeFileSync, mkdirSync, appendFileSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const here = resolve(fileURLToPath(import.meta.url), '..');
const args = process.argv.slice(2);
const flag = (name, fallback = null) => {
  const index = args.indexOf(`--${name}`);
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback;
};
const exportDir = resolve(flag('export', ''));
const outFile = resolve(flag('out', ''));
const batchSize = Number(flag('batch', '8'));
const limit = Number(flag('limit', '0'));
const port = Number(flag('port', '3261'));
const runId = flag('run-id', new Date().toISOString().replace(/[-:]/gu, '').replace(/\..+$/u, 'Z'));

const sha256File = (path) => new Promise((done, fail) => {
  const hash = createHash('sha256');
  createReadStream(path).on('data', (chunk) => hash.update(chunk)).on('end', () => done(hash.digest('hex'))).on('error', fail);
});
const sha256Text = (text) => createHash('sha256').update(text).digest('hex');
const fail = (message) => { console.error(`[abort] ${message}`); process.exit(2); };

if (!exportDir || !existsSync(exportDir)) fail('usage: run.mjs --export <dir> --out <file>');
const manifestPath = resolve(exportDir, 'export.json');
if (!existsSync(manifestPath)) fail(`no export.json in ${exportDir}; 04 has not published a validated export yet`);
const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
const manifestSha = sha256Text(readFileSync(manifestPath, 'utf8'));

for (const [key, spec] of Object.entries({ model: manifest.model, tokenizer: manifest.tokenizer, config: manifest.config, test: manifest.test })) {
  if (!spec?.file || !spec?.sha256) fail(`export.json is missing ${key}.file or ${key}.sha256`);
  const path = resolve(exportDir, spec.file);
  if (!existsSync(path)) fail(`${key} file missing: ${path}`);
  const actual = await sha256File(path);
  if (actual !== spec.sha256) fail(`${key} hash mismatch: ${actual} != ${spec.sha256}`);
}
if (!Array.isArray(manifest.heads) || manifest.heads.length === 0) fail('export.json has no heads');

const testPath = resolve(exportDir, manifest.test.file);
const rows = readFileSync(testPath, 'utf8').split('\n').filter(Boolean).map((line) => JSON.parse(line));
if (rows.length === 0) fail('the frozen test file is empty');
const items = limit > 0 ? rows.slice(0, limit) : rows;
const idField = manifest.input?.idField ?? 'rowId';
const textField = manifest.input?.field ?? 'x';
for (const row of items) {
  if (row[idField] == null) fail(`a test row has no ${idField}`);
  if (typeof row[textField] !== 'string' || row[textField].length === 0) fail(`a test row has no ${textField} text`);
}

mkdirSync(dirname(outFile), { recursive: true });
if (existsSync(outFile)) fail(`refusing to overwrite ${outFile}`);

const server = spawn(process.execPath, [resolve(here, 'serve.mjs'), '--root', exportDir, '--port', String(port)], { stdio: ['ignore', 'pipe', 'pipe'] });
const serverLog = [];
server.stdout.on('data', (chunk) => serverLog.push(String(chunk).trim()));
server.stderr.on('data', (chunk) => serverLog.push(String(chunk).trim()));
const waitForServer = async () => {
  for (let i = 0; i < 60; i += 1) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/page.html`, { signal: AbortSignal.timeout(800) });
      if (response.ok) return;
    } catch { /* not up yet */ }
    await new Promise((done) => setTimeout(done, 250));
  }
  throw new Error(`probe server did not start: ${serverLog.join(' | ')}`);
};

const argmax = (data, dims) => {
  const classes = dims[dims.length - 1];
  const rowsOut = data.length / classes;
  const picked = [];
  for (let i = 0; i < rowsOut; i += 1) {
    let best = 0;
    for (let c = 1; c < classes; c += 1) if (data[i * classes + c] > data[i * classes + best]) best = c;
    const row = data.slice(i * classes, (i + 1) * classes);
    const max = row[best];
    const sum = row.reduce((acc, value) => acc + Math.exp(value - max), 0);
    picked.push({ index: best, prob: 1 / sum, logit: row[best] });
  }
  return picked;
};
const decode = (tensors, headName) => {
  const head = manifest.heads.find((entry) => entry.name === headName);
  if (!head) return null;
  const tensor = tensors[head.output];
  if (!tensor) return { error: `output ${head.output} missing` };
  const picked = argmax(tensor.data, tensor.dims);
  return picked.map((row) => ({ ...row, label: head.labels?.[row.index] ?? null }));
};

const write = (record) => appendFileSync(outFile, `${JSON.stringify(record)}\n`, 'utf8');
write({
  kind: 'run-start', runId, startedAt: new Date().toISOString(),
  exportDir, manifestSha256: manifestSha, testSha256: manifest.test.sha256,
  modelSha256: manifest.model.sha256, tokenizerSha256: manifest.tokenizer.sha256, configSha256: manifest.config.sha256,
  heads: manifest.heads.map((head) => head.name), batchSize, items: items.length,
});

let browser = null;
try {
  await waitForServer();
  browser = await chromium.launch({
    channel: 'msedge', headless: true,
    args: ['--enable-unsafe-webgpu', '--force_high_performance_gpu', '--ignore-gpu-blocklist'],
  }).catch(() => chromium.launch({ headless: true, args: ['--enable-unsafe-webgpu', '--force_high_performance_gpu', '--ignore-gpu-blocklist'] }));
  const page = await browser.newPage();
  const consoleLines = [];
  page.on('console', (message) => consoleLines.push(`[${message.type()}] ${message.text()}`.slice(0, 300)));
  page.on('pageerror', (error) => consoleLines.push(`[pageerror] ${String(error).slice(0, 300)}`));
  await page.goto(`http://127.0.0.1:${port}/page.html`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => window.__ready === true, null, { timeout: 30000 });
  const setup = await page.evaluate(async (input) => window.__setup(input), {
    modelUrl: '/model/' + manifest.model.file,
    vocabUrl: '/model/' + manifest.tokenizer.file,
    lowercase: manifest.tokenizer.lowercase !== false,
    maxLen: Number(manifest.tokenizer.maxLen ?? 192),
    preferWebGpu: manifest.config.preferWebGpu !== false,
  });
  write({ kind: 'model-loaded', at: new Date().toISOString(), setup });

  // Tokenizer parity first: ids must match 04's Python BertTokenizer on the
  // cases shipped with the export. A mismatch aborts before any batch, because
  // every later number would describe a different input than the training one.
  const parity = manifest.tokenizer.parity;
  if (!Array.isArray(parity) || parity.length === 0) fail('export.json has no tokenizer.parity cases');
  const parityRows = [];
  for (const probe of parity) {
    const ids = await page.evaluate((text) => window.__tokenize(text), probe.text);
    const ok = JSON.stringify(ids) === JSON.stringify(probe.ids);
    parityRows.push({ text: probe.text, expected: probe.ids, actual: ids, ok });
    if (!ok) {
      write({ kind: 'tokenizer-parity', ok: false, rows: parityRows });
      fail(`tokenizer parity failed for ${JSON.stringify(probe.text).slice(0, 40)}: ${JSON.stringify(ids)} != ${JSON.stringify(probe.ids)}`);
    }
  }
  write({ kind: 'tokenizer-parity', ok: true, rows: parityRows });

  let done = 0;
  for (let start = 0; start < items.length; start += batchSize) {
    const batch = items.slice(start, start + batchSize).map((row) => ({ rowId: String(row[idField]), text: String(row[textField]) }));
    const result = await page.evaluate(async (input) => window.__classify(input.batch, { padTo: input.padTo }), { batch, padTo: manifest.tokenizer.padTo ?? null });
    batch.forEach((row, index) => {
      const single = {};
      for (const head of manifest.heads) {
        const tensor = result.tensors[head.output];
        if (!tensor) continue;
        const classes = tensor.dims[tensor.dims.length - 1];
        const slice = tensor.data.slice(index * classes, (index + 1) * classes);
        single[head.output] = { dims: tensor.dims, data: slice };
      }
      const y = {};
      for (const head of manifest.heads) {
        const picked = decode({ [head.output]: single[head.output] }, head.name)?.[0] ?? null;
        y[head.name] = picked;
      }
      write({
        kind: 'item', runId, index: start + index, rowId: row.rowId,
        inputChars: row.text.length, inputSha256: sha256Text(row.text),
        inputText: row.text, inputIds: result.inputIds[index],
        y, batchWallMs: result.wallMs, batchSize: result.batchSize, length: result.length,
        tensors: single,
      });
      done += 1;
    });
    console.log(`[batch ${start / batchSize + 1}] ${batch.length} items in ${result.wallMs} ms (${done}/${items.length})`);
  }
  write({ kind: 'run-end', at: new Date().toISOString(), runId, done, console: consoleLines.slice(-40) });
  console.log(`[done] ${done} items -> ${outFile}`);
} catch (error) {
  write({ kind: 'run-error', at: new Date().toISOString(), runId, error: String(error).slice(0, 500) });
  console.error(`[error] ${String(error).slice(0, 500)}`);
  process.exitCode = 1;
} finally {
  if (browser) await browser.close().catch(() => undefined);
  server.kill();
}
