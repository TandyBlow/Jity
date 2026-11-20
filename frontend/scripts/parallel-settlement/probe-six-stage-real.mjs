#!/usr/bin/env node
/**
 * Real-model probe of the six-stage settlement, with the two task contracts.
 *
 * Why: across 171 recorded task-stage answers (532 updates answers, 44 evidence
 * files) the model never marked a single task achieved and never proposed a
 * subtask. So the personality, sanity and subtask stages have never run on real
 * model output, and the roster skeleton in the tasks prompt is the prime suspect
 * (it prints a complete answer that names every character as unchanged).
 *
 * This script runs the REAL handler code (createSettlementHandlers -> updates,
 * all six stages in order) against the REAL Qwen3-0.6B through wllama in Edge,
 * on the real world state, for:
 *   A. tasksContract 'roster'   (today's default)
 *   B. tasksContract 'achieved' (model asserts changes only)
 * and records every prompt, raw answer, timing and the per-stage detail.
 *
 * Assets are served read-only from another worktree's public/ directory because
 * this worktree has no model files; the script hashes what it served.
 *
 *   node scripts/parallel-settlement/probe-six-stage-real.mjs \
 *     --assets ../06-recovery/frontend/public --out ../../../results/quality/04-six-stage-real.json
 */
import { createHash } from 'node:crypto';
import { createReadStream, existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { dirname, extname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import { chromium } from '@playwright/test';

const frontend = fileURLToPath(new URL('../..', import.meta.url));
const option = (flag, fallback) => (process.argv.includes(flag) ? process.argv[process.argv.indexOf(flag) + 1] : fallback);
const assetsDir = resolve(process.cwd(), option('--assets', '../06-recovery/frontend/public'));
const output = resolve(process.cwd(), option('--out', '../../../results/quality/04-six-stage-real.json'));
const modelFile = 'Qwen3-0.6B-Q4_K_M.gguf';
const shas = (path) => createHash('sha256').update(readFileSync(path)).digest('hex');

const MIME = {
  '.js': 'text/javascript; charset=utf-8', '.wasm': 'application/wasm',
  '.gguf': 'application/octet-stream', '.json': 'application/json',
};

const server = await createServer({
  root: frontend, configFile: false, logLevel: 'warn',
  cacheDir: '../.local/vite-six-stage-probe',
  server: { host: '127.0.0.1', port: 0, hmr: false },
  plugins: [{
    name: 'six-stage-probe',
    configureServer(vite) {
      vite.middlewares.use((req, res, next) => {
        res.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
        res.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
        const url = String(req.url ?? '');
        if (url === '/__probe') {
          res.setHeader('Content-Type', 'text/html; charset=utf-8');
          res.end('<!doctype html><title>six-stage probe</title>');
          return undefined;
        }
        for (const prefix of ['/models/', '/wllama/', '/wasm/']) {
          if (!url.startsWith(prefix)) continue;
          const file = join(assetsDir, url);
          if (!existsSync(file) || !statSync(file).isFile()) {
            res.statusCode = 404; res.end('missing asset');
            return undefined;
          }
          res.setHeader('Content-Type', MIME[extname(file)] ?? 'application/octet-stream');
          res.setHeader('Content-Length', String(statSync(file).size));
          createReadStream(file).pipe(res);
          return undefined;
        }
        return next();
      });
    },
  }],
});

/** The point under test: the real world, one group whose fact satisfies
 * lu's goggles task ("把胸前护目镜戴好并确认镜片没有裂纹"), plus nono's own
 * result so the shared group still has two members. */
const CASE = {
  id: 'goggles-achieved',
  groupId: 'group_probe',
  results: {
    lu: '路明非把胸前的护目镜戴好，低头确认镜片没有裂纹，然后抬手示意诺诺可以走了。',
    nono: '诺诺点头，把红色识别带往左臂上又绕紧一圈。',
  },
};

/** A fact that both satisfies the goggles goal and is a plausible personality
 * trigger: the same character, after finishing his own task, gives his spare
 * lens away. If the model ever adds a personality record, sanity must follow. */
const CASE_PERSONALITY = {
  id: 'personality-change',
  groupId: 'group_probe3',
  results: {
    lu: '路明非把胸前的护目镜戴好，确认镜片没有裂纹，然后把自己的备用镜片塞给诺诺。',
    nono: '诺诺接过备用镜片，点头收进腰包。',
  },
};

const CASE_SUBTASK = {
  id: 'subtask-opportunity',
  groupId: 'group_probe2',
  results: {
    lu: '路明非发现诺诺的短讯机没电，得先找一枚满电的R型电池才能继续联络。',
    nono: '诺诺把故障的短讯机递过来，说电池盒在红方地图桌上。',
  },
};

const report = {
  kind: 'six-stage-real-probe',
  startedAt: new Date().toISOString(),
  status: 'IN_PROGRESS',
  sources: Object.fromEntries([
    'src/lib/world-engine/local/semantics/settlement/updates.ts',
    'src/lib/world-engine/local/semantics/settlement/results.ts',
    'src/lib/world-engine/local/semantics/settlement/task-verifier.ts',
    'src/lib/world-engine/local/semantics/settlement/projection.ts',
    'src/lib/world-engine/local/semantics/settlement/support.ts',
    'src/lib/world-engine/local/semantics/settlement/types.ts',
    'src/lib/world-engine/local/state.ts',
  ].map((file) => [`frontend/${file}`, shas(resolve(frontend, file))])),
  assets: {
    model: { file: modelFile, sha256: shas(join(assetsDir, 'models', modelFile)) },
    wllama: shas(join(assetsDir, 'wllama', 'index.min.js')),
    wasm: shas(join(assetsDir, 'wasm', 'wllama.wasm')),
    servedFrom: assetsDir,
  },
  world: 'public/worlds/dragon-raja-free-day.world.json',
  cases: [],
  runs: [],
};
const save = () => { mkdirSync(dirname(output), { recursive: true }); writeFileSync(output, `${JSON.stringify(report, null, 1)}\n`); };
save();

let browser;
try {
  await server.listen();
  const port = server.httpServer.address().port;
  report.serverPort = port;
  const base = `http://127.0.0.1:${port}`;
  browser = await chromium.launch({ channel: 'msedge', headless: true }).catch(() => chromium.launch({ headless: true }));
  report.browser = browser.version();
  const page = await browser.newPage();
  const pageLog = [];
  page.on('pageerror', (error) => pageLog.push(`[pageerror] ${String(error).slice(0, 300)}`));
  await page.goto(`${base}/__probe`, { waitUntil: 'domcontentloaded' });
  const loaded = await page.evaluate(async ({ modelUrl }) => {
    if (!crossOriginIsolated) throw new Error('probe requires cross-origin isolation');
    const { Wllama } = await import('/wllama/index.min.js');
    const started = performance.now();
    const instance = new Wllama({ default: '/wasm/wllama.wasm' }, { logger: { debug: () => undefined, log: () => undefined, warn: () => undefined, error: () => undefined } });
    await instance.loadModelFromUrl(modelUrl, { useCache: true, n_ctx: 4096, n_batch: 512, n_ubatch: 128, n_gpu_layers: 99999, warmup: false, n_threads: 4 });
    window.__probe = instance;
    return { loadMs: Math.round(performance.now() - started), multithread: instance.isMultithread(), threads: instance.getNumThreads() };
  }, { modelUrl: `/models/${modelFile}` });
  report.load = loaded;
  save();

  const { buildInitialState } = await server.ssrLoadModule('/src/lib/world-engine/local/state.ts');
  const { createSettlementHandlers } = await server.ssrLoadModule('/src/lib/world-engine/local/semantics/settlement/index.ts');
  const world = JSON.parse(readFileSync(join(frontend, 'public/worlds/dragon-raja-free-day.world.json'), 'utf8'));
  const baseState = buildInitialState(world.initial);

  const engine = {
    info: { backend: 'wllama', modelId: modelFile },
    async load() {},
    async dispose() {},
    async complete(prompt, opts = {}) {
      const result = await page.evaluate(async ({ prompt, opts }) => {
        const instance = window.__probe;
        const started = performance.now();
        try {
          const response = await instance.createChatCompletion({
            messages: [{ role: 'user', content: prompt }],
            chat_template_kwargs: { enable_thinking: false },
            cache_prompt: true,
            max_tokens: opts.maxTokens ?? 512,
            temperature: opts.temperature ?? 0,
            seed: 20261111,
            ...(opts.jsonSchema ? { response_format: { type: 'json_schema', json_schema: { name: 'task_output', schema: opts.jsonSchema, strict: true } } } : {}),
          });
          return {
            ok: true, wallMs: Math.round(performance.now() - started),
            content: response?.choices?.[0]?.message?.content ?? '',
            finishReason: response?.choices?.[0]?.finish_reason ?? null,
            usage: response?.usage ?? null,
          };
        } catch (error) {
          return { ok: false, wallMs: Math.round(performance.now() - started), error: String(error?.message ?? error).slice(0, 400) };
        }
      }, { prompt, opts });
      if (!result.ok) throw new Error(result.error);
      lastCompletion = result;
      return result.content;
    },
  };
  let lastCompletion = null;

  const only = option('--only', '');
  for (const [caseSpec, contract] of [[CASE, 'roster'], [CASE, 'achieved'], [CASE_SUBTASK, 'achieved'], [CASE_PERSONALITY, 'achieved']]) {
    const id = `${caseSpec.id}#${contract}`;
    if (only && !id.startsWith(only)) continue;
    report.cases.push({ id, contract, results: caseSpec.results });
    const started = Date.now();
    const onTask = (task, key, detail) => {
      report.runs.push({
        case: id, task, key, at: new Date().toISOString(),
        ms: Math.round(detail.ms ?? 0), fallback: Boolean(detail.fallback), error: detail.error ?? null,
        promptChars: detail.promptChars ?? null, stageMs: detail.stageMs ?? null, raw: detail.raw ?? null,
        completion: lastCompletion ? { finishReason: lastCompletion.finishReason, usage: lastCompletion.usage } : null,
      });
      lastCompletion = null;
      save();
    };
    const handlers = createSettlementHandlers({ engine, options: { requireTaskSupport: true, tasksContract: contract, onTask } });
    const outcome = await handlers.updates(caseSpec.groupId, {
      groupId: caseSpec.groupId, mode: 'group', workingState: baseState, results: caseSpec.results,
    });
    const detail = outcome.evidence.detail ?? {};
    const stages = (detail.stages ?? []).map((row) => ({
      stage: row.stage, ms: row.ms, fallback: row.fallback, error: row.error,
      skipped: row.skipped ?? null,
      newlyAchieved: row.newlyAchievedTaskIds ?? null,
      defaultedUnchanged: row.taskScope?.defaultedUnchanged ?? null,
      supports: row.taskScope?.supports ?? null,
      rejected: row.taskScope?.rejectedTaskIds ?? null,
      verifier: row.taskScope?.verifier ?? null,
      rejectedPersonality: row.rejectedPersonality ?? null,
      sanityValues: row.values ?? null,
      personalityChanged: row.changedCharacterIds ?? row.changes?.length ?? null,
      sanityOwners: row.owners ?? null,
      subtasksAdded: row.addedTaskIds ?? null,
      changes: row.changes ?? null,
    }));
    report.cases[report.cases.length - 1].finished = {
      at: new Date().toISOString(), wallMs: Date.now() - started,
      fallback: outcome.fallback, error: outcome.error ?? null,
      stageErrors: detail.stageErrors ?? null, stages,
    };
    save();
    const achievedCount = stages.reduce((sum, row) => sum + (row.newlyAchieved?.length ?? 0), 0);
    console.log(`[probe] ${id}: stages=${stages.map((row) => row.stage).join(',')} achieved=${achievedCount} ` +
      `wallMs=${Date.now() - started}${outcome.error ? ` error=${outcome.error}` : ''}`);
  }
  report.pageLog = pageLog;
  report.status = 'COMPLETED';
  report.completedAt = new Date().toISOString();
  save();
} catch (error) {
  report.status = 'FAILED';
  report.error = String(error?.stack ?? error).slice(0, 4000);
  save();
  throw error;
} finally {
  if (browser) await browser.close();
  await server.close();
}
