// Three matched full/focused pairs, sourced from the real rule HTTP run.
// Same model, threads, seed, budgets and per-task output requirements.
// cache_prompt=false in every arm; actual cache_n is checked, not assumed.
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { chromium } from '@playwright/test';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { cpus } from 'node:os';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const frontend = fileURLToPath(new URL('../', import.meta.url));
const root = resolve(frontend, '..');
const option = (flag, fallback) => process.argv.includes(flag) ? process.argv[process.argv.indexOf(flag) + 1] : fallback;
const httpReportPath = resolve(root, option('--http-report', '.local/rule-facts-http.json'));
const httpBytes = readFileSync(httpReportPath);
const evidence = JSON.parse(httpBytes);
assert.equal(evidence.status, 'PASS_RULE_FACTS_HTTP');
const moved = evidence.rows.find((row) => row.id === 'move');
const numeric = evidence.rows.find((row) => row.id === 'numeric');
const cases = [
  { task: 'action', key: 'person_c', input: { actor: 'person_c', advance: { inputText: '走到门厅', intentStatus: 'pending' }, workingState: moved.predecessor.state } },
  { task: 'updates', key: 'numeric_comparison#sanity', input: { groupId: 'numeric_comparison', mode: 'group', stage: 'sanity',
    results: { person_c: '周宁完成任务「完成压力试验」，经历压力试验后更谨慎；精神值从10变为8。' },
    ruleAssessment: numeric.decision, workingState: numeric.predecessor.state } },
  { task: 'narration', key: moved.saved.pointId, input: { pointId: moved.saved.pointId, before: moved.predecessor.state,
    delta: { timeAdvance: moved.saved.timeAdvance, entityDeltas: moved.saved.entityDeltas }, after: moved.saved.state, perspective: '周宁视角，仅表达保存事实' },
    committedReads: { before: moved.predecessor, after: moved.saved } },
];
const config = { model: '/models/Qwen3-0.6B-Q4_K_M.gguf', contextSize: 4096, numThreads: 4,
  channel: 'msedge', seed: 42, temperature: 0, cachePrompt: false, timeoutMs: 120_000,
  taskMaxTokens: { action: 80, updates: 192, narration: 128 } };
const output = resolve(root, option('--out', '.local/b3-focused.json'));
const files = ['frontend/scripts/run-b3-focused.mjs', ...['engine', 'wllama-engine', 'model-port', 'prompts', 'focused-input',
  'committed-narration', 'rule-facts', 'output-schema', 'structured-output'].map((name) => `frontend/src/lib/world-engine/runtime/${name}.ts`)];
const sha = (bytes) => createHash('sha256').update(bytes).digest('hex');
const git = (...args) => execFileSync('git', ['-c', `safe.directory=${root.replaceAll('\\', '/')}`, '-C', root, ...args], { encoding: 'utf8' }).trim();
const report = { status: 'IN_PROGRESS', recordedAt: new Date().toISOString(), config,
  source: { head: git('rev-parse', 'HEAD'), status: git('status', '--short'),
    sha256: Object.fromEntries(files.map((file) => [file, sha(readFileSync(resolve(root, file)))])) },
  factSource: { reportSha256: sha(httpBytes), serverCommit: evidence.serverSource.head,
    movementAnchor: moved.narration.packet.anchor, numericAnchor: numeric.narration.packet.anchor },
  assets: { modelSha256: sha(readFileSync(resolve(frontend, 'public/models/Qwen3-0.6B-Q4_K_M.gguf'))),
    bundleSha256: sha(readFileSync(resolve(frontend, 'public/wllama/index.min.js'))),
    wasmSha256: sha(readFileSync(resolve(frontend, 'public/wasm/wllama.wasm'))),
    packageVersion: JSON.parse(readFileSync(resolve(frontend, 'node_modules/@wllama/wllama/package.json'))).version },
  device: { cpu: cpus()[0]?.model, logicalCpus: cpus().length }, rows: [] };
const resume = option('--resume', null);
report.rowProvenance = {};
if (resume) {
  const previousBytes = readFileSync(resolve(root, resume));
  const previous = JSON.parse(previousBytes);
  assert.deepEqual(previous.config, config, 'resume must retain all inference parameters');
  assert.deepEqual(previous.factSource, report.factSource, 'resume must use the same committed facts');
  assert.deepEqual(previous.assets, report.assets, 'resume must use identical model/runtime assets');
  for (const file of files.filter((file) => file !== 'frontend/scripts/run-b3-focused.mjs')) {
    assert.equal(previous.source.sha256[file], report.source.sha256[file], `runtime changed: ${file}`);
  }
  report.rows = previous.rows;
  report.resume = { previousReportSha256: sha(previousBytes), previousSource: previous.source,
    previousStatus: previous.status, previousError: previous.error,
    previousBrowser: previous.browser, previousDevice: previous.device, previousTopology: previous.topology,
    previousLoadMs: previous.loadMs, previousCleanup: previous.cleanup };
  for (const row of previous.rows) report.rowProvenance[row.id] = report.resume.previousReportSha256;
}
const save = () => { mkdirSync(dirname(output), { recursive: true }); writeFileSync(output, JSON.stringify(report, null, 2) + '\n'); };
save();
const server = await createServer({ root: frontend, configFile: false, logLevel: 'warn', cacheDir: '../.local/b3-focused-vite',
  server: { host: '127.0.0.1', port: 0, hmr: false },
  plugins: [{ name: 'b3-focused', configureServer(vite) { vite.middlewares.use((req, res, next) => {
    res.setHeader('Cross-Origin-Opener-Policy', 'same-origin'); res.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
    if (req.url !== '/__focused') return next();
    res.setHeader('Content-Type', 'text/html'); res.end('<!doctype html><title>B3 focused input comparison</title>');
  }); } }],
});
let browser;
let activeId;
let lastSave = 0;
try {
  await server.listen();
  report.serverPort = server.httpServer.address().port;
  browser = await chromium.launch({ headless: true, channel: config.channel });
  report.browser = browser.version();
  const page = await browser.newPage();
  page.on('pageerror', (error) => console.error('[pageerror]', error.message));
  await page.exposeFunction('checkpointFocused', (progress) => {
    if (activeId !== progress.id || Date.now() - lastSave < 1500) return;
    lastSave = Date.now(); report.inFlight = progress; save();
  });
  const setup = await page.goto(`http://127.0.0.1:${report.serverPort}/__focused`).then(() => page.evaluate(async ({ config, cases }) => {
    if (!crossOriginIsolated) throw new Error('Focused page requires cross-origin isolation');
    const { WllamaInferenceEngine } = await import('/src/lib/world-engine/runtime/wllama-engine.ts');
    const { RuntimeWorldModelPort } = await import('/src/lib/world-engine/runtime/model-port.ts');
    const { buildTaskPrompt } = await import('/src/lib/world-engine/runtime/prompts.ts');
    const { projectCommittedNarration, checkFactNarration } = await import('/src/lib/world-engine/runtime/committed-narration.ts');
    const engine = new WllamaInferenceEngine({ modelUrl: config.model, contextSize: config.contextSize, numThreads: config.numThreads });
    const started = performance.now(); await engine.load();
    window.__focused = { engine, RuntimeWorldModelPort, buildTaskPrompt, projectCommittedNarration, checkFactNarration, cases };
    return { loadMs: performance.now() - started, topology: engine.diagnostics, crossOriginIsolated };
  }, { config, cases }));
  Object.assign(report, setup);
  assert.deepEqual(setup.topology, { multithread: true, numThreads: 4 });
  save();
  for (const [index, sample] of cases.entries()) {
    const modes = index === 1 ? ['focused', 'full'] : ['full', 'focused'];
    for (const mode of modes) {
      const id = `${sample.task}-${mode}`;
      if (report.rows.some((row) => row.id === id)) continue; // failed attempts also retain their paid evidence
      activeId = id; lastSave = 0; report.inFlight = { id, raw: '' }; save();
      console.log(`[focused] start ${id}`);
      let watchdog;
      const row = await Promise.race([page.evaluate(async ({ index, mode, config, id }) => {
        const runtime = window.__focused;
        const sample = runtime.cases[index];
        let completion;
        const port = new runtime.RuntimeWorldModelPort(runtime.engine, undefined, { ...config, inputMode: mode, committedReads: sample.committedReads,
          onCompletion: (_task, _key, evidence) => { completion = evidence; },
          onProgress: (_task, _key, progress) => { window.checkpointFocused({ id, ...progress }); },
        });
        const prompt = runtime.buildTaskPrompt(sample.task, sample.key, sample.input, { inputMode: mode, committedReads: sample.committedReads });
        const started = performance.now();
        try {
          const generation = await port.generateDetailed(sample.task, sample.key, sample.input);
          let contentReason = null;
          if (sample.task === 'action') {
            const value = generation.value;
            if (value.kind !== 'act' || !/周宁|person_c|主角/.test(value.text) || !/门厅/.test(value.text) || /林川|钥匙|开盒/.test(value.text)) contentReason = 'action_actor_or_destination_mismatch';
          } else if (sample.task === 'updates') {
            const value = generation.value;
            if (value.stage !== 'sanity' || Object.keys(value.changes).join() !== 'person_c'
              || JSON.stringify(value.changes.person_c) !== '{"sanitySet":8}') contentReason = 'numeric_candidate_mismatch';
          } else {
            const packet = runtime.projectCommittedNarration(sample.committedReads.after, sample.committedReads.before);
            const checked = runtime.checkFactNarration(packet, generation.value);
            if (!checked.ok) contentReason = checked.reason;
          }
          return { id, task: sample.task, mode, input: sample.input, prompt, promptCharacters: prompt.length,
            value: generation.value, completion, timing: generation.timing, wallMs: performance.now() - started,
            failure: contentReason ? 'content' : null, contentReason };
        } catch (error) {
          return { id, task: sample.task, mode, input: sample.input, prompt, promptCharacters: prompt.length, completion,
            failure: error.name === 'StructuredOutputError' ? 'structure' : 'engine', error: `${error.name}: ${error.message}`, wallMs: performance.now() - started };
        }
      }, { index, mode, config, id }), new Promise((_resolve, reject) => { watchdog = setTimeout(() => reject(new Error(`watchdog exceeded: ${id}`)), config.timeoutMs + 20_000); })]).finally(() => clearTimeout(watchdog));
      activeId = null; delete report.inFlight;
      report.rows.push(row); report.rowProvenance[id] = 'current_run'; save();
      console.log(`[focused] ${id}: ${row.failure ?? 'ok'}, ${Math.round(row.wallMs)}ms, prefill=${row.completion?.timings?.prompt_ms}, cache=${row.completion?.timings?.cache_n}`);
      if (row.completion?.timings) assert.equal(row.completion.timings.cache_n, 0, 'comparison must not attribute cache reuse to input cropping');
      else assert.equal(row.failure, 'engine', 'a completed generation must report its prompt/cache metrics');
    }
  }
  report.status = 'COMPLETED'; report.completedAt = new Date().toISOString(); save();
} catch (error) {
  report.status = 'INTERRUPTED'; report.error = String(error); save(); throw error;
} finally {
  if (browser) await browser.close();
  await server.close(); report.cleanup = { browserClosed: true, serverClosed: true }; save();
}
