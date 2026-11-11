#!/usr/bin/env node
/**
 * Real-model CHAIN probe: five points in a row, each settled by the real
 * six-stage runner on the state the previous point produced.
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

/** The chain: the same five points a real turn would take, each one settled on
 * the state the previous point produced, so the second occurrence of a fact
 * meets an already-achieved task and the task prompt has to show it. */
const CHAIN = [
  { id: 'p1-goggles', results: CASE.results },
  { id: 'p2-goggles-again', results: CASE.results },
  { id: 'p3-battery', results: CASE_SUBTASK.results },
  { id: 'p4-personality', results: CASE_PERSONALITY.results },
  { id: 'p5-quiet', results: { lu: '路明非站在原地等诺诺回话。', nono: '诺诺没有动。' } },
  // An automatic round: no member action, only time passing. This is the other
  // half of a real turn's points and the only place `basis: "time"` applies.
  { id: 'p6-timescan', mode: 'time_scan', results: {} },
];

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
  calls: [],
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
      report.calls.push({
        at: new Date().toISOString(), wallMs: result.wallMs, promptChars: prompt.length,
        maxTokens: opts.maxTokens ?? null, finishReason: result.finishReason,
        usage: result.usage ?? null,
      });
      save();
      return result.content;
    },
  };
  let lastCompletion = null;

  const { mergeUpdatesStages } = await server.ssrLoadModule('/src/lib/world-engine/schedule.ts');
  const { applyPoint, pointEntityDeltas } = await server.ssrLoadModule('/src/lib/world-engine/local/state.ts');
  const only = option('--only', '');
  let state = baseState;
  for (const [index, spec] of CHAIN.entries()) {
    if (only && !spec.id.startsWith(only)) continue;
    const started = Date.now();
    const onTask = (task, key, detail) => {
      report.runs.push({
        case: spec.id, task, key, at: new Date().toISOString(),
        ms: Math.round(detail.ms ?? 0), fallback: Boolean(detail.fallback), error: detail.error ?? null,
        promptChars: detail.promptChars ?? null, stageMs: detail.stageMs ?? null, raw: detail.raw ?? null,
        completion: lastCompletion ? { finishReason: lastCompletion.finishReason, usage: lastCompletion.usage } : null,
      });
      lastCompletion = null;
      save();
    };
    const handlers = createSettlementHandlers({ engine, options: { requireTaskSupport: true, tasksContract: 'achieved', onTask } });
    const mode = spec.mode ?? 'group';
    const outcome = await handlers.updates(`chain_${index}`, {
      ...(mode === 'group' ? { groupId: `chain_${index}` } : {}), mode, workingState: state, results: spec.results,
    });
    const detail = outcome.evidence.detail ?? {};
    const stages = (detail.stages ?? []).map((row) => ({
      stage: row.stage, ms: row.ms, fallback: row.fallback, error: row.error,
      skipped: row.skipped ?? null,
      newlyAchieved: row.newlyAchievedTaskIds ?? null,
      defaultedUnchanged: row.taskScope?.defaultedUnchanged ?? null,
      rejected: row.taskScope?.rejectedTaskIds ?? null,
      rejectedPersonality: row.rejectedPersonality ?? null,
      rejectedSubtasks: row.rejectedSubtasks ?? null,
      sanityValues: row.values ?? null,
      personalityChanged: row.changedCharacterIds ?? null,
      subtasksAdded: row.addedTaskIds ?? null,
      detailKeys: Object.keys(row),
      detail: row,
    }));
    const row = { id: spec.id, results: spec.results, calls: outcome.value };
    report.cases.push(row);
    let commit = null;
    try {
      const merged = mergeUpdatesStages(outcome.value);
      const unit = {
        groupId: mode === 'group' ? `chain_${index}` : null, actorIds: Object.keys(spec.results),
        taskCoverageIds: Object.keys(spec.results), personalityCoverageIds: Object.keys(spec.results),
        positions: Object.fromEntries(Object.entries(merged).filter(([, d]) => d.positionSet !== undefined).map(([id, d]) => [id, d.positionSet])),
        appearances: Object.fromEntries(Object.entries(merged).filter(([, d]) => d.appearanceChanges !== undefined).map(([id, d]) => [id, d.appearanceChanges])),
        tasksAchieved: Object.fromEntries(Object.entries(merged).filter(([, d]) => d.tasksAchieved !== undefined).map(([id, d]) => [id, d.tasksAchieved])),
        subtasksAdded: Object.fromEntries(Object.entries(merged).filter(([, d]) => d.subtasksAdded !== undefined).map(([id, d]) => [id, d.subtasksAdded])),
        personalities: Object.fromEntries(Object.entries(merged).filter(([, d]) => d.personalityChanges !== undefined).map(([id, d]) => [id, d.personalityChanges])),
        sanities: Object.fromEntries(Object.entries(merged).filter(([, d]) => d.sanitySet !== undefined).map(([id, d]) => [id, d.sanitySet])),
      };
      const pointDeltas = pointEntityDeltas(mode === 'group' ? [unit] : [], mode === 'group' ? null : unit);
      const timeAdvance = { boundary: 'elapsed', duration: { amount: 3, unit: 'minute' } };
      state = applyPoint(state, {
        worldId: world.worldId, id: `chain_${index}`, sequence: index + 1, kind: 'normal',
        previousPointId: index === 0 ? 'start' : `chain_${index - 1}`,
        roundId: `round_${index}`, advanceId: `advance_${index}`, trigger: 'player',
        linkedFromPointId: null, timeAdvance, entityDeltas: pointDeltas,
      });
      commit = { ok: true, deltas: pointDeltas };
    } catch (error) {
      commit = { ok: false, error: String(error?.message ?? error) };
    }
    row.finished = {
      at: new Date().toISOString(), wallMs: Date.now() - started,
      fallback: outcome.fallback, error: outcome.error ?? null,
      stageErrors: detail.stageErrors ?? null, stages, commit,
      stateAfter: {
        tasks: Object.fromEntries(Object.entries(state.characters).flatMap(([id, c]) => Object.entries(c.tasks ?? {}).map(([taskId, task]) => [`${id}/${taskId}`, task.status]))),
        personalityCounts: Object.fromEntries(Object.entries(state.characters).map(([id, c]) => [id, (c.personalityChanges ?? []).length])),
        sanity: Object.fromEntries(Object.entries(state.characters).map(([id, c]) => [id, c.sanity])),
      },
    };
    save();
    const achievedCount = stages.reduce((sum, stageRow) => sum + (stageRow.newlyAchieved?.length ?? 0), 0);
    console.log(`[chain] ${spec.id}: achieved=${achievedCount} personality=${JSON.stringify(stages.find((r) => r.stage === 'personality')?.personalityChanged ?? null)} sanity=${JSON.stringify(stages.find((r) => r.stage === 'sanity')?.sanityValues ?? null)} commit=${commit.ok ? 'ok' : commit.error} wallMs=${Date.now() - started}`);
  }
  if (process.argv.includes('--cont')) {
    // The turn-ending stage: what the real model proposes as the automatic
    // round, and what the policy does with it. Two calls on the same state:
    // once with no committed change, once with the goggles achievement.
    const { createContinuationPolicy } = await server.ssrLoadModule('/src/lib/world-engine/local/semantics/settlement/index.ts');
    const contCases = [
      { id: 'cont-no-change', roundChanges: [] },
      {
        id: 'cont-goggles',
        roundChanges: [{
          pointId: 'cont_p1',
          timeAdvance: { boundary: 'elapsed', duration: { amount: 3, unit: 'minute' } },
          entityDeltas: { lu: { entityId: 'lu', tasksAchieved: ['task_lu_goggles'] } },
        }],
        head: 'cont_p1',
      },
    ];
    for (const spec of contCases) {
      const started = Date.now();
      const runner = createSettlementHandlers({
        engine,
        options: { onTask: (task, key, detail) => {
          report.runs.push({ case: spec.id, task, key, ms: Math.round(detail.ms ?? 0), raw: detail.raw ?? null, at: new Date().toISOString() });
          save();
        } },
      });
      const outcome = await runner.continuation(spec.id, {
        workingState: baseState,
        round: { roundId: 'round_cont', trigger: 'player' },
        roundChanges: spec.roundChanges,
        head: { pointId: spec.head ?? 'cont_p0' },
        roundProgress: { progress: spec.roundChanges.length > 0 },
      });
      const ev = outcome.evidence;
      report.cases.push({
        id: spec.id, continuation: true,
        finished: {
          wallMs: Date.now() - started, value: outcome.value, error: outcome.error ?? null,
          detail: ev.detail ?? null, fallback: outcome.fallback,
        },
      });
      save();
      console.log(`[cont] ${spec.id}: value=${JSON.stringify(outcome.value)} wallMs=${Date.now() - started} error=${outcome.error ?? '-'}`);
    }
    void createContinuationPolicy;
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
