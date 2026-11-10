#!/usr/bin/env node
/**
 * Shared real-browser entry for narration candidates.
 *
 * One queue, one browser, one engine per model. Candidates are the teams'
 * already-written modules; this script does not implement narration, does not
 * invent prompts and does not turn machine checks into quality claims.
 *
 *   node scripts/quality-candidates/run-browser-candidates.mjs \
 *     --candidate 02-narration=/abs/path/to/narration-generation/index.ts \
 *     --set free-day \
 *     --out ../../../results/quality/browser-09.json
 *
 * Local inference is exclusive: the script acquires the shared lease right
 * before loading a model and releases it in `finally`. A run that did not load
 * a model (dry listing) needs no lease.
 *
 * Evidence: every run records the exact input text, identity (world/point/
 * version/digest), prompt and raw attempts from the candidate, the readable
 * paragraphs, wall time, first-token time and every error. Results are merged
 * atomically into the shared file after each scenario, so a crash loses at most
 * one run.
 */
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { closeSync, createReadStream, existsSync, mkdirSync, openSync, readFileSync, renameSync, statSync, unlinkSync, writeFileSync } from 'node:fs';
import { cpus } from 'node:os';
import { basename, dirname, isAbsolute, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { createServer } from 'vite';

const require = createRequire(resolve('package.json'));
const { chromium } = require('@playwright/test');

const frontend = fileURLToPath(new URL('../..', import.meta.url));
const leaseScript = 'D:/others/Jity/.local/parallel-local-game/resource_lease.py';

const argv = process.argv.slice(2);
const value = (flag, fallback = null) => {
  const index = argv.indexOf(flag);
  return index >= 0 && index + 1 < argv.length ? argv[index + 1] : fallback;
};
const values = (flag) => {
  const out = [];
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === flag && index + 1 < argv.length) out.push(argv[index + 1]);
  }
  return out;
};
const flag = (name) => argv.includes(name);
const pairs = (list) => Object.fromEntries(list.map((entry) => {
  const at = entry.indexOf('=');
  return at > 0 ? [entry.slice(0, at), entry.slice(at + 1)] : [entry, ''];
}));

const config = {
  lane: value('--lane', '09-ui'),
  purpose: value('--purpose', 'shared browser candidate queue'),
  model: value('--model', '/models/qwen25-0.5b-narration-Q4_K_M.gguf'),
  modelDir: value('--model-dir', process.env.MODEL_DIR ?? 'D:/others/Jity/.local/world-narration-worktree/frontend/public/models'),
  world: value('--world', resolve(frontend, 'public/worlds/dragon-raja-free-day.world.json')),
  out: resolve(frontend, value('--out', '../../../results/quality/browser-09.json')),
  set: value('--set', 'free-day'),
  only: value('--only', '') ? value('--only').split(',').map((id) => id.trim()).filter(Boolean) : null,
  exclude: value('--exclude', '') ? value('--exclude').split(',').map((id) => id.trim()).filter(Boolean) : null,
  threads: Number(value('--threads', '4')),
  contextSize: Number(value('--context-size', '4096')),
  gpu: flag('--gpu'),
  channel: value('--channel', 'msedge'),
  maxTokens: value('--max-tokens') ? Number(value('--max-tokens')) : undefined,
  temperature: value('--temperature') ? Number(value('--temperature')) : undefined,
  hardTimeoutMs: Number(value('--hard-timeout-ms', '240000')),
  maxRuns: value('--max-runs') ? Number(value('--max-runs')) : null,
  repeat: Math.max(1, Number(value('--repeat', '1'))),
  noLease: flag('--no-lease'),
  leaseWaitSeconds: Number(value('--lease-wait-seconds', '0')),
  dry: flag('--dry'),
  inspect: flag('--inspect'),
  probe: flag('--probe'),
  status: flag('--status'),
  noEngine: flag('--no-engine'),
  quiet: flag('--quiet'),
  aliasSrc: resolve(value('--alias-src', resolve(frontend, 'src'))),
  allowDirs: values('--allow-dir'),
  candidateSpecs: pairs(values('--candidate')),
  owners: pairs(values('--owner')),
  models: pairs(values('--candidate-model')),
  exports: pairs(values('--candidate-export')),
  notes: pairs(values('--candidate-note')),
  policies: pairs(values('--candidate-policy')),
  loaders: pairs(values('--candidate-loader')),
  loaderModelIds: pairs(values('--candidate-model-id')),
  engineLoader: value('--engine-loader'),
  engineModelId: value('--engine-model-id'),
};

/** `<path>::<export>` or `<path>` (default export name loadCandidateModel). */
function parseLoader(spec) {
  if (!spec) return null;
  const at = spec.lastIndexOf('::');
  const file = isAbsolute(spec.slice(0, at > 0 ? at : spec.length))
    ? spec.slice(0, at > 0 ? at : spec.length)
    : resolve(frontend, spec.slice(0, at > 0 ? at : spec.length));
  if (!existsSync(file)) fail(`engine loader module missing: ${file}`);
  return { file, moduleUrl: moduleUrlFor(file), exportName: at > 0 ? spec.slice(at + 2) : 'loadCandidateModel' };
}

// Candidate-specific policy overrides (e.g. 02's mode=beats). Parsed once so a
// typo fails before any model is loaded.
const candidatePolicies = Object.fromEntries(Object.entries(config.policies).map(([id, json]) => {
  try {
    return [id, JSON.parse(json)];
  } catch (error) {
    fail(`--candidate-policy ${id} is not JSON: ${error.message}`);
  }
}));

const sha256File = (file) => createHash('sha256').update(readFileSync(file)).digest('hex');

/** The model that actually loads is the one served from `--model-dir`; a
 * `--model` path with the same basename is only a request. Hash the served
 * bytes once and keep both identities so evidence cannot silently name a
 * different file than the one the browser loaded. */
const modelHashCache = new Map();
function servedModelIdentity(url) {
  const servedPath = resolve(config.modelDir, basename(url));
  if (!existsSync(servedPath)) return { url, servedPath, exists: false };
  const stat = statSync(servedPath);
  const key = `${servedPath}:${stat.size}:${stat.mtimeMs}`;
  let sha256 = modelHashCache.get(key);
  if (!sha256) {
    sha256 = sha256File(servedPath);
    modelHashCache.set(key, sha256);
  }
  return { url, servedPath, exists: true, bytes: stat.size, sha256, mtime: new Date(stat.mtimeMs).toISOString() };
}

function requestedModelIdentity(requested) {
  const requestedPath = requested.startsWith('/models/')
    ? resolve(config.modelDir, basename(requested))
    : resolve(requested);
  if (!existsSync(requestedPath)) return { path: requestedPath, exists: false };
  const stat = statSync(requestedPath);
  return { path: requestedPath, exists: true, bytes: stat.size };
}

function fail(message) {
  console.error(`error: ${message}`);
  process.exit(1);
}

function printStatus() {
  const current = readEvidence();
  console.log(JSON.stringify({
    lane: current.lane ?? config.lane,
    updatedAt: current.updatedAt ?? null,
    candidates: Object.fromEntries(Object.entries(current.candidates ?? {}).map(([id, candidate]) => [id, {
      owner: candidate.owner,
      source: candidate.source,
      latest: candidate.latest ?? {},
      modelUrl: candidate.modelUrl,
    }])),
    runs: (current.runs ?? []).map((run) => ({
      runId: run.runId, candidateId: run.candidateId, scenarioId: run.scenarioId,
      at: run.startedAt, accepted: run.result?.accepted, chars: run.result?.chars,
      wallMs: Math.round(run.wallMs ?? 0), error: run.error ?? null,
      firstReadableAtMs: run.progress?.firstReadableAtMs ?? null,
      engineAlive: run.engineAfter?.alive ?? null,
    })),
    failures: current.failures ?? [],
    notices: (current.notices ?? []).map((notice) => ({ at: notice.at, to: notice.to, runId: notice.runId, summary: notice.summary })),
    probes: current.probes ?? [],
  }, null, 2));
}

if (config.status) {
  printStatus();
  process.exit(0);
}

if ((!config.candidateSpecs || Object.keys(config.candidateSpecs).length === 0) && !config.probe && !config.status) {
  fail('at least one --candidate <id>=<module path> is required (or use --probe/--status)');
}
if (!['short', 'free-day', 'all'].includes(config.set)) fail(`--set must be short|free-day|all, got ${config.set}`);
if (!existsSync(config.world)) fail(`world asset missing: ${config.world}`);

const candidates = Object.entries(config.candidateSpecs).map(([id, modulePath]) => {
  const file = isAbsolute(modulePath) ? modulePath : resolve(frontend, modulePath);
  if (!existsSync(file)) fail(`candidate module missing for ${id}: ${file}`);
  const model = config.models[id] ?? config.model;
  const loader = parseLoader(config.loaders[id] ?? config.engineLoader);
  return {
    id,
    owner: config.owners[id] ?? id,
    file,
    moduleUrl: moduleUrlFor(file),
    modelUrl: model.startsWith('/models/') ? model : `/models/${basename(model)}`,
    exportName: config.exports[id] ?? 'generateCandidate',
    notes: config.notes[id] ?? null,
    loader: loader ? {
      moduleUrl: loader.moduleUrl,
      exportName: loader.exportName,
      modelId: config.loaderModelIds[id] ?? config.engineModelId ?? undefined,
      modelRoot: '/models',
      file: loader.file,
    } : null,
  };
});

/** Vite URL for a module file inside or outside the frontend root. */
function moduleUrlFor(file) {
  const normalized = resolve(file).replace(/\\/g, '/');
  const rel = relative(frontend, normalized).replace(/\\/g, '/');
  return rel.startsWith('..') ? encodeURI(`/@fs/${normalized}`) : encodeURI(`/${rel}`);
}

/** Every candidate module's directory (and its frontend root, when it has one)
 * must be readable by the dev server; nothing is copied. */
function allowedDirectories(candidateList) {
  const dirs = new Set([frontend, config.modelDir, config.aliasSrc, ...config.allowDirs.map((dir) => resolve(dir))]);
  const files = [...candidateList.map((candidate) => candidate.file), ...candidateList.map((candidate) => candidate.loader?.file).filter(Boolean)];
  for (const file of files) {
    let dir = dirname(file);
    dirs.add(dir);
    for (let depth = 0; depth < 6 && dir !== dirname(dir); depth += 1) {
      const parent = dirname(dir);
      if (existsSync(resolve(parent, 'node_modules')) || existsSync(resolve(parent, 'package.json'))) dirs.add(parent);
      dir = parent;
    }
  }
  return [...dirs];
}

function assetMiddleware() {
  const wllamaRoot = resolve(frontend, 'node_modules/@wllama/wllama/esm');
  const map = {
    '/wllama/index.min.js': { file: resolve(wllamaRoot, 'index.min.js'), type: 'application/javascript' },
    '/wasm/wllama.wasm': { file: resolve(wllamaRoot, 'wasm/wllama.wasm'), type: 'application/wasm' },
  };
  return (request, response, next) => {
    response.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
    response.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
    const url = (request.url ?? '').split('?')[0];
    if (url === '/favicon.ico') { response.statusCode = 204; response.end(); return; }
    if (url === '/__candidates') {
      response.setHeader('Content-Type', 'text/html');
      response.end('<!doctype html><meta charset="utf-8"><title>candidate driver</title>');
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
  };
}

/* ---------------- evidence file ---------------- */

function emptyEvidence() {
  return {
    lane: config.lane,
    kind: 'browser-candidate-runs',
    updatedAt: null,
    purpose: 'Real browser output for narration candidates. Text and prompts are evidence for the owning team; no machine score is a quality verdict.',
    runner: {
      script: 'frontend/scripts/quality-candidates/run-browser-candidates.mjs',
      driver: 'frontend/src/lib/world-engine/local/narration-candidates/browser-driver/index.ts',
      command: null,
      lane: config.lane,
    },
    device: { cpu: cpus()[0]?.model, logicalCpus: cpus().length, platform: process.platform },
    models: {},
    candidates: {},
    runs: [],
    failures: [],
    notices: [],
    probes: [],
  };
}

function readEvidence() {
  if (!existsSync(config.out)) return emptyEvidence();
  // Another lane may write the shared file with an older copy of this script
  // that does not take the lock or write via rename. Retry a partial read
  // instead of moving the file away; the old rename-on-error path could
  // delete a healthy snapshot written a millisecond later.
  for (let attempt = 0; attempt < 8; attempt += 1) {
    try {
      const parsed = JSON.parse(readFileSync(config.out, 'utf8'));
      if (parsed?.kind !== 'browser-candidate-runs') return emptyEvidence();
      return { ...emptyEvidence(), ...parsed, candidates: parsed.candidates ?? {}, runs: parsed.runs ?? [], failures: parsed.failures ?? [] };
    } catch {
      if (attempt === 7) {
        console.warn(`[queue] ${config.out} stayed unreadable after retries; using an empty snapshot`);
        return emptyEvidence();
      }
      sleepSync(100);
    }
  }
  return emptyEvidence();
}

let evidence = readEvidence();

function mergeEvidence(base, incoming) {
  const merged = { ...base, ...incoming };
  const runs = new Map();
  for (const run of [...(base.runs ?? []), ...(incoming.runs ?? [])]) {
    if (run?.runId) runs.set(run.runId, run);
  }
  merged.runs = [...runs.values()].sort((a, b) => String(a.startedAt).localeCompare(String(b.startedAt)));
  const failures = new Map();
  for (const failure of [...(base.failures ?? []), ...(incoming.failures ?? [])]) {
    failures.set(`${failure.at}|${failure.candidateId}|${failure.scenarioId}|${failure.error}`, failure);
  }
  merged.failures = [...failures.values()];
  const candidates = { ...(base.candidates ?? {}) };
  for (const [id, candidate] of Object.entries(incoming.candidates ?? {})) {
    const previous = candidates[id] ?? {};
    const latest = { ...(previous.latest ?? {}) };
    for (const [scenarioId, entry] of Object.entries(candidate.latest ?? {})) {
      const old = latest[scenarioId];
      if (!old || String(entry.at) >= String(old.at)) latest[scenarioId] = entry;
    }
    candidates[id] = { ...previous, ...candidate, latest };
  }
  merged.candidates = candidates;
  merged.models = { ...(base.models ?? {}), ...(incoming.models ?? {}) };
  const notices = new Map();
  for (const notice of [...(base.notices ?? []), ...(incoming.notices ?? [])]) {
    notices.set(`${notice.at}|${notice.to}|${notice.summary}`, notice);
  }
  merged.notices = [...notices.values()];
  const probes = new Map();
  for (const probe of [...(base.probes ?? []), ...(incoming.probes ?? [])]) {
    probes.set(`${probe.at}|${probe.model}`, probe);
  }
  merged.probes = [...probes.values()];
  merged.summary = rebuildSummary(merged);
  return merged;
}

/** Latest run per candidate+scenario in one flat table. Owners read this to
 * find their own text without walking `runs[]`; it is a pointer, never a
 * quality verdict. */
function rebuildSummary(snapshot) {
  const latest = new Map();
  for (const run of snapshot.runs ?? []) {
    const key = `${run.candidateId}::${run.scenarioId}`;
    const old = latest.get(key);
    if (!old || String(run.startedAt) >= String(old.startedAt)) latest.set(key, run);
  }
  return [...latest.values()].map((run) => ({
    candidateId: run.candidateId,
    scenarioId: run.scenarioId,
    runId: run.runId,
    startedAt: run.startedAt,
    accepted: run.result?.accepted ?? null,
    chars: run.result?.chars ?? null,
    wallMs: Math.round(run.wallMs ?? 0),
    firstReadableAtMs: run.progress?.firstReadableAtMs ?? null,
    backend: run.engine?.loader?.backend ?? null,
    gpuRequested: run.engine?.gpuRequested ?? null,
    issues: (run.result?.issues ?? []).slice(0, 6).map((issue) => `${issue.severity ?? ''}:${issue.kind ?? issue}`),
    textPreview: (run.result?.text ?? '').slice(0, 80),
    textLocation: `${config.out}#runs[${run.runId}]`,
  })).sort((a, b) => `${a.candidateId}${a.scenarioId}`.localeCompare(`${b.candidateId}${b.scenarioId}`));
}

function sleepSync(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function saveEvidence() {
  mkdirSync(dirname(config.out), { recursive: true });
  const lock = `${config.out}.lock`;
  const deadline = Date.now() + 30_000;
  let locked = false;
  while (Date.now() < deadline) {
    try {
      const fd = openSync(lock, 'wx');
      closeSync(fd);
      locked = true;
      break;
    } catch {
      sleepSync(100);
    }
  }
  try {
    const current = readEvidence();
    evidence = mergeEvidence(current, evidence);
    evidence.updatedAt = new Date().toISOString();
    evidence.runner.command = [process.execPath, ...process.argv.slice(1)].join(' ');
    const temp = `${config.out}.tmp-${process.pid}`;
    writeFileSync(temp, `${JSON.stringify(evidence, null, 2)}\n`);
    renameSync(temp, config.out);
  } finally {
    if (locked) {
      try { unlinkSync(lock); } catch { /* advisory lock; a lost unlink only delays the next writer */ }
    }
  }
}

/** Provenance for an imported module: which commit it came from and whether
 * the file (or its directory) has uncommitted changes. Running an in-progress
 * working copy is allowed, but the evidence must say so. */
function sourceInfo(file) {
  const dir = dirname(file);
  const git = (args, cwd = dir) => {
    const result = spawnSync('git', ['-C', cwd, ...args], { encoding: 'utf8' });
    return result.status === 0 ? result.stdout.trim() : null;
  };
  const toplevel = git(['rev-parse', '--show-toplevel']);
  return {
    commit: git(['rev-parse', 'HEAD']),
    toplevel,
    // The whole package directory counts: a dirty sibling module changes the
    // imported behaviour even when this entry file is committed.
    dirty: toplevel ? Boolean(git(['status', '--porcelain', '--', relative(toplevel, dir).split(sep).join('/')], toplevel)) : null,
  };
}

function registerCandidate(candidate, extra = {}) {
  const existing = evidence.candidates[candidate.id] ?? {};
  evidence.candidates[candidate.id] = {
    ...existing,
    id: candidate.id,
    owner: candidate.owner,
    module: candidate.file,
    moduleUrl: candidate.moduleUrl,
    moduleSha256: sha256File(candidate.file),
    source: sourceInfo(candidate.file),
    exportName: extra.exportName ?? candidate.exportName,
    modelUrl: candidate.modelUrl,
    loader: candidate.loader ?? null,
    notes: candidate.notes,
    firstSeenAt: existing.firstSeenAt ?? new Date().toISOString(),
    ...extra,
  };
}

function summarize(candidateId, scenarioId, run) {
  const entry = evidence.candidates[candidateId] ?? {};
  const latest = { ...(entry.latest ?? {}) };
  latest[scenarioId] = {
    runId: run.runId,
    at: run.startedAt,
    accepted: run.result.accepted,
    chars: run.result.chars,
    wallMs: Math.round(run.wallMs),
    firstParagraph: run.result.firstParagraph,
    textLocation: `${config.out}#runs[${run.runId}]`,
    contractOk: run.contract.ok,
    error: run.error,
  };
  evidence.candidates[candidateId] = { ...entry, latest };
}

function recordFailure(candidateId, scenarioId, error, extra = {}) {
  evidence.failures.push({ at: new Date().toISOString(), candidateId, scenarioId, error, ...extra });
  console.error(`[queue] FAIL ${candidateId} ${scenarioId}: ${error}`);
}

/* ---------------- lease ---------------- */

let leaseHeld = false;

async function acquireLease() {
  const deadline = Date.now() + Math.max(0, config.leaseWaitSeconds) * 1000;
  for (;;) {
    const result = spawnSync('python', [leaseScript, 'acquire', '--lane', config.lane, '--purpose', config.purpose], { encoding: 'utf8' });
    if (result.status === 0) {
      leaseHeld = true;
      console.log(`[lease] acquired for ${config.lane}: ${config.purpose}`);
      return true;
    }
    const holder = (result.stdout || result.stderr || '').trim();
    if (Date.now() >= deadline) {
      console.log(`[lease] busy: ${holder || `exit ${result.status}`}`);
      return false;
    }
    console.log(`[lease] busy, waiting: ${holder}`);
    await new Promise((resolve) => setTimeout(resolve, 2_000));
  }
}

function releaseLease() {
  if (!leaseHeld) return;
  leaseHeld = false;
  const result = spawnSync('python', [leaseScript, 'release', '--lane', config.lane], { encoding: 'utf8' });
  console.log(`[lease] release: ${(result.stdout || result.stderr || '').trim()}`);
}

/* ---------------- server + browser ---------------- */

// Acquire before starting Vite/Chromium: waiting queues must not each hold a
// browser while another lane owns the inference resource.
if (!config.dry && !config.inspect && !config.noEngine && !config.noLease && !leaseHeld) {
  if (!(await acquireLease())) {
    recordFailure('*', '*', 'lease_busy');
    saveEvidence();
    process.exit(2);
  }
}

const server = await createServer({
  root: frontend,
  configFile: false,
  logLevel: 'warn',
  resolve: { alias: { '@': config.aliasSrc } },
  optimizeDeps: { noDiscovery: true, include: [] },
  server: { host: '127.0.0.1', port: 0, hmr: false, fs: { strict: true, allow: allowedDirectories(candidates) } },
  plugins: [{ name: 'candidate-assets', configureServer: (vite) => { vite.middlewares.use(assetMiddleware()); } }],
});

let browser = null;
let exitCode = 0;
try {
  await server.listen();
  const port = server.httpServer.address().port;
  browser = await chromium.launch({
    headless: true,
    channel: config.channel,
    ...(config.gpu ? { args: ['--enable-unsafe-webgpu'] } : {}),
  });
  const page = await browser.newPage();
  page.on('pageerror', (error) => console.error('[pageerror]', error.message));
  page.on('console', (message) => { if (message.type() === 'error') console.error('[console]', message.text()); });
  await page.goto(`http://127.0.0.1:${port}/__candidates`);

  const buffer = await page.evaluate(() => ({ isolated: crossOriginIsolated, gpu: typeof navigator !== 'undefined' && 'gpu' in navigator }));
  if (!buffer.isolated) fail('cross-origin isolation is required for wllama');

  evidence.device.browser = await browser.version();
  evidence.device.crossOriginIsolated = buffer.isolated;
  evidence.device.webgpuAvailable = buffer.gpu;
  evidence.runner.aliasSrc = config.aliasSrc;

  const driverUrl = '/src/lib/world-engine/local/narration-candidates/browser-driver/index.ts';
  const call = (operation, payload) => page.evaluate(async ({ driverUrl, operation, payload }) => {
    const driver = await import(driverUrl);
    if (operation === 'prepare') return { ok: true, value: await driver.prepare(payload) };
    if (operation === 'inspect') return { ok: true, value: await driver.inspectCandidate(payload) };
    if (operation === 'loadEngine') return { ok: true, value: await driver.loadEngine(payload) };
    if (operation === 'runOne') return { ok: true, value: await driver.runOne(payload) };
    if (operation === 'probeEngine') return { ok: true, value: await driver.probeEngine(payload) };
    if (operation === 'dispose') return { ok: true, value: await driver.disposeEngines() };
    throw new Error(`unknown operation ${operation}`);
  }, { driverUrl, operation, payload });

  const world = JSON.parse(readFileSync(config.world, 'utf8'));

  const prepared = await call('prepare', {
    set: config.set,
    freeDay: world,
    include: config.only,
    exclude: config.exclude,
    candidates: candidates.map((candidate) => ({
      id: candidate.id,
      owner: candidate.owner,
      moduleUrl: candidate.moduleUrl,
      exportName: candidate.exportName,
      modelUrl: candidate.modelUrl,
      notes: candidate.notes,
      loader: candidate.loader,
    })),
  });
  if (!prepared.ok) fail(prepared.error ?? 'prepare failed');
  const scenarios = prepared.value;
  const scenarioIds = scenarios.map((scenario) => scenario.id);
  if (config.probe) {
    {
      const loaded = await call('loadEngine', {
        modelUrl: config.model, contextSize: config.contextSize, threads: config.threads, gpu: config.gpu, reuse: false,
      });
      if (!loaded.ok) { recordFailure('probe', '*', `engine_load_failed:${loaded.error}`); process.exitCode = 1; }
      else {
        loaded.value.modelFile = servedModelIdentity(config.model);
        console.log(`[probe] engine loaded in ${Math.round(loaded.value.loadMs)}ms backend=${loaded.value.info.backend} model=${loaded.value.info.modelId}`);
        const probe = await call('probeEngine', {
          modelUrl: config.model,
          prompt: value('--prompt', '用一句中文描写走廊里的脚步声。'),
          maxTokens: Number(value('--probe-max-tokens', '32')),
          timeoutMs: Number(value('--probe-timeout-ms', '30000')),
          temperature: 0.7,
        });
        if (!probe.ok) { recordFailure('probe', '*', `probe_failed:${probe.error}`); process.exitCode = 1; }
        else {
          console.log(`[probe] ${probe.value.chars} chars in ${Math.round(probe.value.wallMs)}ms progress=${probe.value.progressEvents}`);
          console.log(`[probe-text] ${String(probe.value.text).slice(0, 200)}`);
          evidence.probes = [...(evidence.probes ?? []), { at: new Date().toISOString(), model: config.model, modelFile: servedModelIdentity(config.model), ...probe.value, engine: loaded.value }];
        }
      }
      await call('dispose', {});
    }
  } else if (config.inspect) {
    for (const candidate of candidates) {
      const inspected = await call('inspect', {
        id: candidate.id, owner: candidate.owner, moduleUrl: candidate.moduleUrl,
        exportName: candidate.exportName, modelUrl: candidate.modelUrl, notes: candidate.notes, loader: candidate.loader,
      });
      if (!inspected.ok) {
        recordFailure(candidate.id, '*', `import_failed: ${inspected.error}`);
        continue;
      }
      registerCandidate(candidate, { inspect: inspected.value, inspectedAt: new Date().toISOString(), exportName: inspected.value.usedExport });
      console.log(`[inspect] ${candidate.id}: export=${inspected.value.usedExport} exports=${inspected.value.moduleExports.join(',')} documented=${inspected.value.hasDocumentedExport}`);
    }
  } else if (config.dry) {
    console.log(JSON.stringify({ scenarios, candidates: candidates.map(({ id, owner, moduleUrl, modelUrl, exportName }) => ({ id, owner, moduleUrl, modelUrl, exportName })) }, null, 2));
    process.exitCode = 0;
  } else {
    console.log(`[queue] ${candidates.length} candidate(s) x ${scenarios.length} scenario(s): ${scenarioIds.join(', ')}`);
    for (const scenario of scenarios) {
      console.log(`[input] ${scenario.id}: ${scenario.inputChars} chars, viewpoint ${scenario.identity.viewpointName}, change=${scenario.identity.changeKinds.join(',') || 'none'}, present=${scenario.scenePresent}`);
    }

    const keyOf = (candidate) => `${candidate.modelUrl}::${candidate.loader?.moduleUrl ?? ''}::${candidate.loader?.modelId ?? ''}`;
    const modelOrder = [...new Set(candidates.map(keyOf))];
    let totalRuns = 0;
    for (const engineKey of modelOrder) {
      const group = candidates.filter((candidate) => keyOf(candidate) === engineKey);
      const modelUrl = group[0].modelUrl;
      const loader = group[0].loader;
      const loaded = config.noEngine
        ? { ok: true, value: {
          modelUrl: '', loadMs: 0, info: { backend: 'stub', modelId: null }, diagnostics: null,
          webgpuAvailable: false, gpuRequested: false,
          backendNote: 'no engine loaded (--no-engine); program-only candidate path',
        } }
        : await call('loadEngine', {
          modelUrl,
          contextSize: config.contextSize,
          threads: config.threads,
          gpu: config.gpu,
          reuse: true,
          loader: loader ? { moduleUrl: loader.moduleUrl, exportName: loader.exportName, modelId: loader.modelId, modelRoot: loader.modelRoot } : null,
        });
      if (!loaded.ok) {
        recordFailure(group[0].id, '*', `engine_load_failed: ${loaded.error}`);
        continue;
      }
      if (!config.noEngine) {
        const served = servedModelIdentity(modelUrl);
        const requested = requestedModelIdentity(config.models[group[0].id] ?? config.model);
        evidence.models = { ...(evidence.models ?? {}), [modelUrl]: { served, requested, requestedUrl: config.models[group[0].id] ?? config.model } };
        loaded.value.modelFile = served;
        if (served.exists && requested.exists && served.bytes !== requested.bytes) {
          recordFailure(group[0].id, '*', `model_file_mismatch: served=${served.bytes}B requested=${requested.bytes}B`, { afterRun: true });
        }
      }
      const reloadNote = loaded.value.reloadReason ? ` reload=${loaded.value.reloadReason}` : '';
      if (config.noEngine) console.log('[engine] skipped (--no-engine)');
      else console.log(`[engine] ${modelUrl} ${loaded.value.coldStart ? `loaded in ${Math.round(loaded.value.loadMs)}ms` : 'reused'} backend=${loaded.value.info.backend} threads=${loaded.value.diagnostics?.numThreads ?? '?'} gpuRequested=${loaded.value.gpuRequested} webgpuAvailable=${loaded.value.webgpuAvailable}${reloadNote}`);
      if (loaded.value.reloadReason) recordFailure(group[0].id, '*', `engine_reload:${loaded.value.reloadReason}`, { afterRun: true });
      for (const candidate of group) {
        registerCandidate(candidate, { engine: loaded.value, queuedAt: new Date().toISOString() });
        for (let repeat = 0; repeat < config.repeat; repeat += 1) {
          for (const scenario of scenarios) {
            if (config.maxRuns !== null && totalRuns >= config.maxRuns) break;
            totalRuns += 1;
            const result = await call('runOne', {
              candidateId: candidate.id,
              scenarioId: scenario.id,
              hardTimeoutMs: config.hardTimeoutMs,
              stubEngine: config.noEngine,
              maxTokens: config.maxTokens,
              temperature: config.temperature,
              policyOverride: candidatePolicies[candidate.id] ?? null,
            });
            if (!result.ok) {
              recordFailure(candidate.id, scenario.id, result.error ?? 'run failed');
              saveEvidence();
              continue;
            }
            const run = result.value;
            run.repeat = repeat + 1;
            // Hash at dispatch time, not only at registration: teams edit
            // their candidate between scenarios, and a long queue must not
            // attribute later bytes to an earlier run.
            run.moduleSha256 = sha256File(candidate.file);
            run.engine = loaded.value;
            run.evidenceFile = config.out;
            evidence.runs.push(run);
            summarize(candidate.id, scenario.id, run);
            if (!run.contract.ok) {
              recordFailure(candidate.id, scenario.id, `contract: ${run.contract.missing.join(',')}`, { runId: run.runId });
            }
            saveEvidence();
            const status = run.result.accepted ? 'accepted' : 'rejected';
            console.log(`[run] ${candidate.id} ${scenario.id} repeat=${repeat + 1} ${status} chars=${run.result.chars} wall=${Math.round(run.wallMs)}ms attempts=${run.result.attempts.length} firstReadable=${run.progress.firstReadableAtMs == null ? 'none' : `${Math.round(run.progress.firstReadableAtMs)}ms`} engineAlive=${run.engineAfter.alive}`);
            if (!run.engineAfter.alive) {
              recordFailure(candidate.id, scenario.id, 'engine_dead_after_run', { runId: run.runId });
            }
            if (!config.quiet) {
              const preview = run.result.paragraphs[0] ?? '(no text)';
              console.log(`[text] ${preview.slice(0, 160)}${preview.length > 160 ? '…' : ''}`);
            }
          }
        }
      }
    }
    await call('dispose', {});
  }
} catch (error) {
  console.error(error);
  recordFailure('*', '*', error instanceof Error ? `${error.name}: ${error.message}` : String(error));
  saveEvidence();
  exitCode = 1;
} finally {
  try { if (browser) await browser.close(); } catch (error) { console.error('[browser close]', error.message); }
  try { await server.close(); } catch (error) { console.error('[server close]', error.message); }
  releaseLease();
  if (!config.dry) saveEvidence();
}

// Vite/Playwright can keep a handle alive after a successful dry/inspect run;
// the evidence and lease are already flushed, so exit explicitly.
process.exit(exitCode);
