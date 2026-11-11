/** Frozen task-goal classification preflight (user §12.1, NON-NARRATIVE-
 * PREFLIGHT-20261111.md).
 *
 * Measures one thing: with the same Qwen3-0.6B the product uses, how often does
 * a single-label answer over the frozen 115-predicate enum land inside lane
 * 01's frozen acceptable set for each of the 73 task goals?
 *
 * This script is an experiment only. It does not import or change any product
 * settlement, action, target or results code, and it never writes lane 01's
 * gold file.
 *
 *   node scripts/semantic-preflight/run-preflight.mjs --contract
 *   node scripts/semantic-preflight/run-preflight.mjs --run --base http://127.0.0.1:3241
 *   node scripts/semantic-preflight/run-preflight.mjs --score runs/<runId>.jsonl
 *
 * --contract freezes and prints the prompt/schema and verifies the frozen
 * input hashes without touching a model. --run needs the local inference lease
 * and loads the model exactly once, then runs:
 *   phase 1  enum-enforcement probe (the same prompt with and without the
 *            json_schema constraint, demanding a label outside the enum)
 *   phase 2  73 goals, arm "cold" (cache_prompt:false, each item pays prefill)
 *   phase 3  the same 73 goals, arm "warm" (cache_prompt:true, product parity)
 * Every call's prompt, raw answer, token counts and wall time are appended to
 * a JSONL file as it happens, so an aborted run still leaves raw evidence.
 */
import { createHash } from 'node:crypto';
import { appendFile, mkdir, readFile, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { chromium } from '@playwright/test';

const here = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.dirname(path.dirname(here));
const repoRoot = path.dirname(frontendRoot);
/** The frozen inputs and shared evidence live in the main clone, not in a
 * per-lane worktree: worktrees/<lane> -> ../.. is the parallel-local-game root. */
const sharedRoot = process.env.PREFLIGHT_ROOT
  ?? path.resolve(repoRoot, '..', '..');
const preflightDir = path.join(sharedRoot, 'results', 'semantic-action-preflight-20261111');
const runsDir = path.join(preflightDir, 'runs');

const TASKS = path.join(preflightDir, 'tasks-73-inputs.json');
const LABELS = path.join(preflightDir, 'labels-v1.json');
const GOLD = path.join(preflightDir, 'gold-01.json');
const GOLD_HASH = path.join(preflightDir, 'gold-01.sha256');
const MANIFEST = path.join(preflightDir, 'manifest-04.json');

/** Frozen experiment configuration. Changing any value here invalidates the
 * manifest hash and therefore every score computed against it. */
const CONFIG = {
  modelFile: 'Qwen3-0.6B-Q4_K_M.gguf',
  modelUrl: '/models/Qwen3-0.6B-Q4_K_M.gguf',
  modelSha256: 'ac2d97712095a558e31573f62f466a3f9d93990898b0ec79d7c974c1780d524a',
  seed: 20261111,
  temperature: 0,
  maxTokens: 24,
  nCtx: 4096,
  nBatch: 512,
  nUbatch: 128,
  nGpuLayers: 99999,
  threads: 4,
  cachePrompt: { cold: false, warm: true },
  perItemTimeoutMs: 90_000,
  maxConsecutiveErrors: 5,
  totalBudgetMs: 45 * 60_000,
  schemaName: 'predicate_label',
};

function sha256(buffer) {
  return createHash('sha256').update(buffer).digest('hex');
}

async function readJson(file) {
  return JSON.parse(await readFile(file, 'utf8'));
}

function labelTable(labels) {
  // Only the 115 predicate words, in frozen file order. No group names, no
  // definitions (the user's "gloss must not enter the prompt") and no example
  // action sentences.
  return labels.groups.flatMap((group) => group.predicates);
}

function buildPrompt(goal, predicates) {
  return [
    '你是中文跑团游戏的任务分类器。只输出 JSON，不要解释。',
    '给出下面这条任务目标的主要动作标签，恰好一个。',
    '标签只能从下表里逐字选一个：',
    ...predicates,
    `任务目标：${goal}`,
    '输出 {"label":"<从上表逐字复制的标签>"}。',
  ].join('\n');
}

function buildSchema(predicates) {
  return {
    type: 'object',
    additionalProperties: false,
    required: ['label'],
    properties: { label: { type: 'string', enum: predicates } },
  };
}

async function contract() {
  const tasksRaw = await readFile(TASKS);
  const labelsRaw = await readFile(LABELS);
  const tasks = JSON.parse(tasksRaw);
  const labels = JSON.parse(labelsRaw);
  const predicates = labelTable(labels);
  const schema = buildSchema(predicates);
  const prompt = buildPrompt(tasks.tasks[0].goal, predicates);
  const problems = [];
  if (predicates.length !== 115) problems.push(`expected 115 predicates, found ${predicates.length}`);
  if (new Set(predicates).size !== predicates.length) problems.push('duplicate predicate in the enum');
  // The label block must be exactly the 115 frozen predicates in frozen order:
  // an extra line would be a group heading or a gloss, a missing one a dropped
  // label. (Two predicates happen to be spelled like their group name — 移动 and
  // 请求 — so comparing whole lines is the only honest check.)
  const lines = prompt.split('\n');
  const blockStart = lines.findIndex((line) => line === '标签只能从下表里逐字选一个：');
  const blockEnd = lines.findIndex((line) => line.startsWith('任务目标：'));
  const block = blockStart >= 0 && blockEnd > blockStart ? lines.slice(blockStart + 1, blockEnd) : null;
  if (!block) problems.push('label block not found in the prompt');
  else if (block.length !== predicates.length || block.some((line, index) => line !== predicates[index])) {
    problems.push(`label block is not the frozen 115 predicates in order (${block.length} lines)`);
  }
  if (block?.some((line) => /[:：]/u.test(line))) problems.push('a label line carries a definition (label: gloss)');
  if (/例[:：]/u.test(prompt)) problems.push('an example line leaked into the prompt');
  if (prompt.includes('做了什么') || prompt.includes('做了什么/看到什么')) problems.push('an action example leaked into the prompt');
  if (tasks.tasks.length !== 73) problems.push(`expected 73 task goals, found ${tasks.tasks.length}`);
  const goals = new Set(tasks.tasks.map((task) => task.goal));
  if (goals.size !== tasks.tasks.length) problems.push('duplicate goal in the frozen inputs');

  const perItemPromptChars = tasks.tasks.map((task) => buildPrompt(task.goal, predicates).length);
  const manifest = {
    version: 'preflight-04-v1',
    createdAt: new Date().toISOString(),
    purpose: 'Frozen prompt/schema/config for the 73-goal 115-label classification preflight (user §12.1). Experiment only; no product protocol is changed.',
    inputs: {
      tasks: { file: 'tasks-73-inputs.json', sha256: sha256(tasksRaw) },
      labels: { file: 'labels-v1.json', sha256: sha256(labelsRaw) },
      gold: {
        file: 'gold-01.json',
        sha256: sha256(await readFile(GOLD)),
        recordedSha256: (await readFile(GOLD_HASH, 'utf8')).trim().split(/\s+/u)[0],
        readOnlyForScoring: true,
      },
    },
    model: {
      file: CONFIG.modelFile,
      sha256: CONFIG.modelSha256,
      nCtx: CONFIG.nCtx,
      nBatch: CONFIG.nBatch,
      nUbatch: CONFIG.nUbatch,
      nGpuLayers: CONFIG.nGpuLayers,
      threads: CONFIG.threads,
    },
    decoding: {
      seed: CONFIG.seed,
      temperature: CONFIG.temperature,
      maxTokens: CONFIG.maxTokens,
      enableThinking: false,
      responseFormat: { type: 'json_schema', json_schema: { name: CONFIG.schemaName, strict: true } },
      cachePrompt: CONFIG.cachePrompt,
    },
    prompt: {
      template: '你是中文跑团游戏的任务分类器。只输出 JSON，不要解释。\n给出下面这条任务目标的主要动作标签，恰好一个。\n标签只能从下表里逐字选一个：\n<115 predicates, one per line, frozen order>\n任务目标：<goal>\n输出 {"label":"<从上表逐字复制的标签>"}。',
      charsMin: Math.min(...perItemPromptChars),
      charsMax: Math.max(...perItemPromptChars),
      sha256OfFirst: sha256(Buffer.from(prompt, 'utf8')),
      noGroupNames: true,
      noGloss: true,
      noActionExamples: true,
    },
    schema: { sha256: sha256(Buffer.from(JSON.stringify(schema), 'utf8')), enumSize: predicates.length },
    stopConditions: {
      perItemTimeoutMs: CONFIG.perItemTimeoutMs,
      maxConsecutiveErrors: CONFIG.maxConsecutiveErrors,
      totalBudgetMs: CONFIG.totalBudgetMs,
      onTimeout: 'record the item as timeout and continue',
      onBudget: 'stop after the current item and keep the JSONL raw evidence',
    },
    script: { file: 'frontend/scripts/semantic-preflight/run-preflight.mjs', sha256: sha256(await readFile(fileURLToPath(import.meta.url))) },
    phases: {
      probe: 'enum enforcement: the same prompt with and without the json_schema constraint, demanding a label outside the enum',
      cold: '73 goals, cache_prompt:false (each item pays its own prefill)',
      warm: '73 goals, cache_prompt:true (product parity for the shared label table)',
    },
    contract: { problems, ok: problems.length === 0 },
  };
  await writeFile(MANIFEST, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
  console.log(JSON.stringify({
    ok: problems.length === 0,
    problems,
    promptChars: [manifest.prompt.charsMin, manifest.prompt.charsMax],
    enumSize: predicates.length,
    manifest: path.relative(sharedRoot, MANIFEST),
    firstPrompt: prompt,
  }, null, 2));
  if (problems.length) process.exitCode = 1;
}

function arg(name, fallback = null) {
  const index = process.argv.indexOf(`--${name}`);
  return index > 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

function has(name) {
  return process.argv.includes(`--${name}`);
}

const PROBE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['label'],
  properties: { label: { type: 'string', enum: ['甲', '乙'] } },
};
const PROBE_PROMPT = '只输出 JSON，不要解释。请判断下面这句话的情感：我一点也不高兴。\n输出 {"label":"丙"}。';

async function run() {
  const base = arg('base', 'http://127.0.0.1:3241');
  const runId = arg('run-id', new Date().toISOString().replace(/[-:]/gu, '').replace(/\..+$/u, 'Z'));
  const manifest = await readJson(MANIFEST);
  const tasksRaw = await readFile(TASKS);
  const labelsRaw = await readFile(LABELS);
  if (sha256(tasksRaw) !== manifest.inputs.tasks.sha256) throw new Error('tasks file changed since the manifest was frozen');
  if (sha256(labelsRaw) !== manifest.inputs.labels.sha256) throw new Error('labels file changed since the manifest was frozen');
  const tasks = JSON.parse(tasksRaw);
  const predicates = labelTable(JSON.parse(labelsRaw));
  const schema = buildSchema(predicates);

  await mkdir(runsDir, { recursive: true });
  const jsonl = path.join(runsDir, `${runId}.jsonl`);
  const summaryPath = path.join(runsDir, `${runId}-summary.json`);
  const startedAt = new Date().toISOString();
  const budgetStart = Date.now();
  const write = async (record) => {
    await appendFile(jsonl, `${JSON.stringify(record)}\n`, 'utf8');
  };
  await write({
    kind: 'run-start', runId, startedAt, base, smoke: has('smoke'),
    manifestSha256: sha256(await readFile(MANIFEST)),
    tasksSha256: manifest.inputs.tasks.sha256, labelsSha256: manifest.inputs.labels.sha256,
    goldSha256: manifest.inputs.gold.sha256, modelSha256: manifest.model.sha256,
    config: manifest.decoding, phases: manifest.phases,
  });

  const browser = await chromium.launch({
    channel: 'msedge',
    headless: true,
    args: ['--enable-unsafe-webgpu', '--force_high_performance_gpu', '--ignore-gpu-blocklist'],
  }).catch(() => chromium.launch({ headless: true, args: ['--enable-unsafe-webgpu', '--force_high_performance_gpu', '--ignore-gpu-blocklist'] }));
  const page = await browser.newPage();
  const consoleLines = [];
  page.on('console', (message) => consoleLines.push(`[${message.type()}] ${message.text()}`.slice(0, 400)));
  page.on('pageerror', (error) => consoleLines.push(`[pageerror] ${String(error).slice(0, 400)}`));
  let consecutiveErrors = 0;
  let budgetHit = false;
  let model = null;
  try {
    await page.goto(`${base}/benchmark`, { waitUntil: 'domcontentloaded' });
    const isolated = await page.evaluate(() => window.crossOriginIsolated === true);
    if (!isolated) throw new Error('not cross-origin isolated; wllama multithread unavailable at this origin');
    model = await page.evaluate(async (config) => {
      const { Wllama } = await import('/wllama/index.min.js');
      const started = performance.now();
      const instance = new Wllama(
        { default: '/wasm/wllama.wasm' },
        { logger: { ...console, debug: () => undefined } },
      );
      await instance.loadModelFromUrl(config.modelUrl, {
        useCache: true,
        n_ctx: config.nCtx,
        n_batch: config.nBatch,
        n_ubatch: config.nUbatch,
        n_gpu_layers: config.nGpuLayers,
        warmup: false,
        n_threads: config.threads,
      });
      const w = window;
      w.__preflight = instance;
      return {
        libllama: Wllama.getLibllamaVersion?.() ?? null,
        multithread: instance.isMultithread(),
        numThreads: instance.getNumThreads(),
        loadMs: Math.round(performance.now() - started),
      };
    }, { modelUrl: `${base}${CONFIG.modelUrl}`, nCtx: CONFIG.nCtx, nBatch: CONFIG.nBatch, nUbatch: CONFIG.nUbatch, nGpuLayers: CONFIG.nGpuLayers, threads: CONFIG.threads });
    await write({ kind: 'model-loaded', model, at: new Date().toISOString() });

    const call = async (request) => {
      const result = await page.evaluate(async (input) => {
        const instance = window.__preflight;
        const started = performance.now();
        try {
          const response = await instance.createChatCompletion({
            messages: [{ role: 'user', content: input.prompt }],
            max_tokens: input.maxTokens,
            temperature: input.temperature,
            seed: input.seed,
            cache_prompt: input.cachePrompt,
            chat_template_kwargs: { enable_thinking: false },
            ...(input.schema ? { response_format: { type: 'json_schema', json_schema: { name: input.schemaName, schema: input.schema, strict: true } } } : {}),
          });
          return {
            ok: true,
            wallMs: Math.round(performance.now() - started),
            content: response?.choices?.[0]?.message?.content ?? null,
            finishReason: response?.choices?.[0]?.finish_reason ?? null,
            usage: response?.usage ?? null,
          };
        } catch (error) {
          return { ok: false, wallMs: Math.round(performance.now() - started), error: String(error?.message ?? error).slice(0, 400) };
        }
      }, request);
      return result;
    };

    // ── phase 1: is the enum actually enforced by the decoder? ─────────────
    for (const withSchema of [true, false]) {
      for (let trial = 1; trial <= 2; trial += 1) {
        const result = await call({
          prompt: PROBE_PROMPT, maxTokens: 16, temperature: CONFIG.temperature, seed: CONFIG.seed,
          cachePrompt: false, schema: withSchema ? PROBE_SCHEMA : null, schemaName: 'probe',
        });
        await write({ kind: 'probe', withSchema, trial, prompt: PROBE_PROMPT, schema: withSchema ? PROBE_SCHEMA : null, ...result });
        if (!result.ok) consecutiveErrors += 1;
      }
    }

    // ── phases 2 and 3: the 73 goals, cold then warm ──────────────────────
    const smoke = has('smoke');
    const itemLimit = smoke ? 3 : tasks.tasks.length;
    const arms = smoke ? ['cold'] : ['cold', 'warm'];
    for (const arm of arms) {
      for (let index = 0; index < itemLimit; index += 1) {
        if (Date.now() - budgetStart > CONFIG.totalBudgetMs) { budgetHit = true; break; }
        if (consecutiveErrors >= CONFIG.maxConsecutiveErrors) { budgetHit = true; break; }
        const task = tasks.tasks[index];
        const prompt = buildPrompt(task.goal, predicates);
        const started = Date.now();
        const result = await call({
          prompt, maxTokens: CONFIG.maxTokens, temperature: CONFIG.temperature, seed: CONFIG.seed,
          cachePrompt: CONFIG.cachePrompt[arm], schema, schemaName: CONFIG.schemaName,
        });
        const wall = Date.now() - started;
        const record = {
          kind: 'item', arm, index, taskId: task.taskId, ownerId: task.ownerId, goal: task.goal,
          prompt, promptChars: prompt.length, schemaSha256: manifest.schema.sha256,
          ...result, wallTotalMs: wall, at: new Date().toISOString(),
        };
        if (result.ok) {
          consecutiveErrors = 0;
          let parsed = null;
          try { parsed = JSON.parse(result.content); } catch { parsed = null; }
          record.parsedLabel = parsed?.label ?? null;
          record.inEnum = predicates.includes(record.parsedLabel);
        } else {
          consecutiveErrors += 1;
        }
        await write(record);
        process.stdout.write(`\r${arm} ${index + 1}/${tasks.tasks.length} ${record.wallTotalMs}ms ${record.parsedLabel ?? record.error ?? ''}`.padEnd(80));
      }
      process.stdout.write('\n');
      if (budgetHit) break;
    }
  } finally {
    await write({
      kind: 'run-end', runId, at: new Date().toISOString(), budgetHit,
      console: consoleLines.slice(-80),
    });
    await browser.close();
    const summary = {
      kind: 'preflight-summary', runId, startedAt, finishedAt: new Date().toISOString(),
      jsonl: path.relative(sharedRoot, jsonl), model, budgetHit,
      manifest: path.relative(sharedRoot, MANIFEST), manifestSha256: sha256(await readFile(MANIFEST)),
    };
    await writeFile(summaryPath, `${JSON.stringify(summary, null, 2)}\n`, 'utf8');
    console.log(`\nraw: ${path.relative(sharedRoot, jsonl)}\nsummary: ${path.relative(sharedRoot, summaryPath)}`);
  }
}

async function score(file) {
  const target = path.resolve(sharedRoot, file);
  const lines = (await readFile(target, 'utf8')).split('\n').filter(Boolean).map((line) => JSON.parse(line));
  const start = lines.find((row) => row.kind === 'run-start');
  if (!start) throw new Error('run file has no run-start record');
  const manifest = await readJson(MANIFEST);
  if (start.tasksSha256 !== manifest.inputs.tasks.sha256) throw new Error('run was produced against different task inputs');
  const goldRaw = await readFile(GOLD);
  const goldSha = sha256(goldRaw);
  const recorded = (await readFile(GOLD_HASH, 'utf8')).trim().split(/\s+/u)[0];
  if (goldSha !== recorded) throw new Error(`gold hash ${goldSha} does not match the frozen ${recorded}`);
  const gold = JSON.parse(goldRaw);
  const byId = new Map(gold.tasks.map((row) => [row.taskId, row]));
  const arms = {};
  for (const arm of ['cold', 'warm']) {
    const items = lines.filter((row) => row.kind === 'item' && row.arm === arm);
    const rows = items.map((item) => {
      const goldRow = byId.get(item.taskId);
      const acceptable = goldRow?.acceptableLabels ?? [];
      return {
        taskId: item.taskId, kind: goldRow?.kind ?? null, goal: item.goal,
        predicted: item.parsedLabel ?? null, acceptable, primary: goldRow?.primaryLabel ?? null,
        correct: Boolean(item.parsedLabel) && acceptable.includes(item.parsedLabel),
        inEnum: item.inEnum === true, wallMs: item.wallTotalMs, wallModelMs: item.wallMs,
        promptTokens: item.usage?.prompt_tokens ?? null, completionTokens: item.usage?.completion_tokens ?? null,
        finishReason: item.finishReason ?? null,
      };
    });
    const evaluated = rows.filter((row) => row.correct || row.predicted);
    const correct = rows.filter((row) => row.correct).length;
    const kindCounts = {};
    for (const kind of ['single', 'compound', 'ambiguous']) {
      const subset = rows.filter((row) => row.kind === kind);
      kindCounts[kind] = { total: subset.length, correct: subset.filter((row) => row.correct).length };
    }
    const times = rows.map((row) => row.wallMs).sort((a, b) => a - b);
    arms[arm] = {
      calls: rows.length, evaluated: evaluated.length, correct,
      accuracy: rows.length ? Number((correct / rows.length).toFixed(4)) : null,
      outOfEnum: rows.filter((row) => !row.inEnum).length,
      byKind: kindCounts,
      latency: times.length ? {
        mean: Math.round(times.reduce((sum, value) => sum + value, 0) / times.length),
        p50: times[Math.floor(times.length / 2)], max: times[times.length - 1],
      } : null,
    };
  }
  const probes = lines.filter((row) => row.kind === 'probe').map((row) => ({
    withSchema: row.withSchema, trial: row.trial, content: row.content, error: row.error ?? null,
    emittedOutsideEnum: Boolean(row.content) && !/甲|乙/u.test(row.content),
  }));
  const result = {
    kind: 'preflight-score', runId: start.runId, scoredAt: new Date().toISOString(),
    runJsonl: path.relative(sharedRoot, target), runJsonlSha256: sha256(await readFile(target)),
    goldSha256: goldSha, goldRecordedSha256: recorded,
    manifestSha256: sha256(await readFile(MANIFEST)),
    scoringRule: gold.scoring,
    enumEnforcement: {
      probes,
      withSchemaHonouredEnum: probes.filter((row) => row.withSchema).every((row) => !row.emittedOutsideEnum),
      withoutSchemaEscapedEnum: probes.filter((row) => !row.withSchema).some((row) => row.emittedOutsideEnum),
    },
    arms,
    misses: Object.fromEntries(['cold', 'warm'].map((arm) => [arm, lines
      .filter((row) => row.kind === 'item' && row.arm === arm)
      .map((item) => {
        const goldRow = byId.get(item.taskId);
        const acceptable = goldRow?.acceptableLabels ?? [];
        return { taskId: item.taskId, kind: goldRow?.kind ?? null, predicted: item.parsedLabel ?? null, acceptable };
      })
      .filter((row) => !row.predicted || !row.acceptable.includes(row.predicted))])),
    thresholds: {
      userRule: '>=59/73 (80%) proceed; 37-58/73 discuss merging per the user synonym groups; <=36/73 report to the user',
      cold: arms.cold.correct >= 59 ? 'proceed' : arms.cold.correct >= 37 ? 'discuss-merge' : 'report-to-user',
      warm: arms.warm.correct >= 59 ? 'proceed' : arms.warm.correct >= 37 ? 'discuss-merge' : 'report-to-user',
    },
  };
  const out = path.join(runsDir, `${start.runId}-score.json`);
  await writeFile(out, `${JSON.stringify(result, null, 2)}\n`, 'utf8');
  console.log(JSON.stringify({
    runId: result.runId, gold: goldSha.slice(0, 12), jsonl: result.runJsonlSha256.slice(0, 12),
    enumEnforcement: result.enumEnforcement.withSchemaHonouredEnum && result.enumEnforcement.withoutSchemaEscapedEnum,
    cold: arms.cold, warm: arms.warm, thresholds: result.thresholds, score: path.relative(sharedRoot, out),
  }, null, 2));
}

if (!existsSync(MANIFEST) && !has('contract')) {
  console.error('no frozen manifest: run --contract first');
  process.exit(2);
}

if (has('contract')) await contract();
else if (has('score')) await score(arg('score'));
else await run();
