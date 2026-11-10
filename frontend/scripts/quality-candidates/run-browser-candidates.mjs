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
import { createReadStream, existsSync, mkdirSync, readFileSync, renameSync, statSync, writeFileSync } from 'node:fs';
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

function fail(message) {
  console.error(`error: ${message}`);
  process.exit(1);
}

if (!config.candidateSpecs || Object.keys(config.candidateSpecs).length === 0) {
  fail('at least one --candidate <id>=<module path> is required');
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
    candidates: {},
    runs: [],
    failures: [],
  };
}

function readEvidence() {
  if (!existsSync(config.out)) return emptyEvidence();
  try {
    const parsed = JSON.parse(readFileSync(config.out, 'utf8'));
    if (parsed?.kind !== 'browser-candidate-runs') return emptyEvidence();
    return { ...emptyEvidence(), ...parsed, candidates: parsed.candidates ?? {}, runs: parsed.runs ?? [], failures: parsed.failures ?? [] };
  } catch (error) {
    const backup = `${config.out}.corrupt-${Date.now()}`;
    renameSync(config.out, backup);
    console.warn(`[queue] unreadable evidence moved to ${backup}: ${error.message}`);
    return emptyEvidence();
  }
}

let evidence = readEvidence();

function saveEvidence() {
  evidence.updatedAt = new Date().toISOString();
  evidence.runner.command = [process.execPath, ...process.argv.slice(1)].join(' ');
  mkdirSync(dirname(config.out), { recursive: true });
  const temp = `${config.out}.tmp`;
  writeFileSync(temp, `${JSON.stringify(evidence, null, 2)}\n`);
  renameSync(temp, config.out);
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
    await new Promise((resolve) => setTimeout(resolve, 20_000));
  }
}

function releaseLease() {
  if (!leaseHeld) return;
  leaseHeld = false;
  const result = spawnSync('python', [leaseScript, 'release', '--lane', config.lane], { encoding: 'utf8' });
  console.log(`[lease] release: ${(result.stdout || result.stderr || '').trim()}`);
}

/* ---------------- server + browser ---------------- */

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
  if (config.inspect) {
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
    let skippedForLease = false;
    for (const engineKey of modelOrder) {
      const group = candidates.filter((candidate) => keyOf(candidate) === engineKey);
      const modelUrl = group[0].modelUrl;
      const loader = group[0].loader;
      if (!config.noLease && !leaseHeld && !(await acquireLease())) { skippedForLease = true; break; }
      const loaded = await call('loadEngine', {
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
      const reloadNote = loaded.value.reloadReason ? ` reload=${loaded.value.reloadReason}` : '';
      console.log(`[engine] ${modelUrl} ${loaded.value.coldStart ? `loaded in ${Math.round(loaded.value.loadMs)}ms` : 'reused'} backend=${loaded.value.info.backend} threads=${loaded.value.diagnostics?.numThreads ?? '?'} gpuRequested=${loaded.value.gpuRequested} webgpuAvailable=${loaded.value.webgpuAvailable}${reloadNote}`);
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
    if (skippedForLease) {
      recordFailure('*', '*', 'lease_busy'); process.exitCode = 2;
    }
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

if (exitCode !== 0) process.exitCode = exitCode;
