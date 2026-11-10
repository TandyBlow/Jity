// Real-model probe for the action / targets / reaction handlers.
//
// The same on-device stack as the narration and rule-facts batches: headless
// Edge, wllama with a frozen GGUF asset, COOP/COEP, temperature 0, fixed seed.
// Each case prints the exact prompt the handler built, the raw completion,
// the decoded value, the guard issues (including rejected repair attempts)
// and the wall time. Nothing here is asserted to be "semantically correct":
// the archive is evidence for a human review of autonomous action, naming,
// target resolution, container/absence handling and reaction attribution.
//
// Structural invariants that ARE asserted:
//   - every returned value passes the controller's task codec;
//   - an off-screen actor and the player's character as reaction member make
//     zero model calls (scope/floor rules, not model answers);
//   - a case that fails twice is reported as fallback, never as model output.
//
//   node scripts/parallel-actions/run-action-eval.mjs --assets <public-dir> \
//        --out ../artifacts/action-eval/run.json
//   node scripts/parallel-actions/run-action-eval.mjs --dry        # no model
//
// --assets points at a public directory that holds models/, wllama/ and wasm/
// (this worktree may share the integrator's read-only assets). Without it the
// local frontend/public is used.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { cpus } from 'node:os';
import { createReadStream, existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import { chromium } from '@playwright/test';

const frontend = fileURLToPath(new URL('../../', import.meta.url));
const root = resolve(frontend, '..');
const option = (flag, fallback) => process.argv.includes(flag) ? process.argv[process.argv.indexOf(flag) + 1] : fallback;
const hasFlag = (flag) => process.argv.includes(flag);
const config = {
  model: option('--model', '/models/Qwen3-0.6B-Q4_K_M.gguf'),
  assets: resolve(option('--assets', resolve(frontend, 'public'))),
  contextSize: Number(option('--context', '4096')),
  numThreads: Number(option('--threads', '4')),
  channel: option('--channel', 'msedge'),
  seed: Number(option('--seed', '42')),
  temperature: Number(option('--temperature', '0')),
  timeoutMs: Number(option('--timeout', '120000')),
  maxTokens: Number(option('--max-tokens', '160')),
  dry: hasFlag('--dry'),
  only: option('--cases', '') ? option('--cases', '').split(',') : null,
};
const output = resolve(frontend, option('--out', '../.local/action-eval.json'));
const sha = (bytes) => createHash('sha256').update(bytes).digest('hex');
const fileSha = (path) => sha(readFileSync(path));
const git = (...args) => execFileSync('git', ['-c', `safe.directory=${root.replaceAll('\\', '/')}`, '-C', root, ...args], { encoding: 'utf8' }).trim();

// ── Cases ──────────────────────────────────────────────────────────────────
// Built on the shipped free-day world. `patch` moves entities before the call
// so absence/container/pronoun situations are real state, not prompt text.

const CASES = [
  {
    id: 'A1-autonomous-unnamed', task: 'action', actor: 'nono',
    playerInput: '我靠在巷口墙边，先确认护目镜有没有起雾。',
    events: ['巷口的红方无线电响了一声，报出西回廊有人接近。'],
    note: 'Named? no. Should still be judged from her own tasks and the radio event.',
  },
  {
    id: 'A2-named-request', task: 'action', actor: 'nono',
    playerInput: '诺诺，你帮我看一下西回廊那边有没有人。',
    note: 'Named and asked to do something.',
  },
  {
    id: 'A3-named-idle', task: 'action', actor: 'nono',
    playerInput: '诺诺，你叫什么名字？',
    note: 'Named but only small talk; a short reply or inaction are both legal.',
  },
  {
    id: 'A4a-offscreen-skip', task: 'action', actor: 'fingel',
    playerInput: '我靠在巷口墙边喘口气。',
    note: 'Fingel is in the shed; the default skip policy makes this a zero-call scope decision.',
  },
  {
    id: 'A4b-offscreen-judge', task: 'action', actor: 'fingel', offscreenPolicy: 'judge',
    playerInput: '我靠在巷口墙边喘口气。',
    events: ['器材棚门口传来脚步，停了一下又走远了。'],
    note: 'Explicit judge policy: judge Fingel from the shed only; the protagonist move must be hidden from him.',
  },
  {
    id: 'A5-protagonist-pending', task: 'action', actor: 'lu',
    playerInput: '我把护目镜推上去，先看巷口的动静。',
    note: 'Player pending command is the frozen action.',
  },
  {
    id: 'A6-protagonist-consumed', task: 'action', actor: 'lu', intentStatus: 'consumed',
    playerInput: '我把护目镜推上去，先看巷口的动静。',
    note: 'Command already executed: continuation only, no verbatim repeat.',
  },
  {
    id: 'A7-absent-npc-named', task: 'action', actor: 'nono',
    playerInput: '楚子航在钟楼吗？',
    note: 'Player names someone in another room; Nono may answer about him without acting as him.',
  },
  {
    id: 'T1-pronoun-single', task: 'targets', source: 'lu',
    actionText: '我把手里的地图递给她。',
    note: 'Pronoun with one present candidate.',
  },
  {
    id: 'T2-pronoun-ambiguous', task: 'targets', source: 'lu',
    patch: [{ entityId: 'fingel', containerId: 'lane', slotId: null }],
    actionText: '我把地图递给他。',
    note: 'Pronoun with two present candidates; the choice must be argued from the scene.',
  },
  {
    id: 'T3-absent-name', task: 'targets', source: 'lu',
    actionText: '我去钟楼找楚子航。',
    note: 'Names a registered character in another room: no target, absence recorded.',
  },
  {
    id: 'T4-container', task: 'targets', source: 'lu',
    patch: [
      { entityId: 'lu', containerId: 'shed', slotId: null },
      { entityId: 'nono', containerId: 'shed', slotId: null },
      { entityId: 'qin', containerId: 'cage', slotId: null },
    ],
    actionText: '我把货架上的备用护目镜拿下来，递给诺诺。',
    note: 'Shed scene: Qin is inside the cage (child location) and must not be selectable.',
  },
  {
    id: 'T5-empty-move', task: 'targets', source: 'lu',
    actionText: '我走向巷子尽头的检修口。',
    note: 'Movement only: a legal empty target set.',
  },
  {
    id: 'T6-two-present', task: 'targets', source: 'lu',
    patch: [{ entityId: 'fingel', containerId: 'lane', slotId: null }],
    actionText: '我把地图摊在地上，问诺诺和芬格尔谁认得这条路。',
    note: 'Two named present characters; both may be touched.',
  },
  {
    id: 'R1-member-reaction', task: 'reaction', source: 'lu', member: 'nono',
    actionText: '我把地图塞到她手里，让她先看路线。',
    note: 'Reaction of the admitted member to a specific threat.',
  },
  {
    id: 'R2-protagonist-member', task: 'reaction', source: 'nono', member: 'lu',
    actionText: '诺诺一把拽住路明非的袖子，把他往墙边带。',
    note: 'The player character is the member: zero-call program floor.',
  },
  {
    id: 'R3-echo-risk', task: 'reaction', source: 'lu', member: 'nono',
    actionText: '我把地图铺在地上，用指尖点着西回廊和检修口两条路线。',
    note: 'Long source action that invites verbatim repetition.',
  },
];

const selected = config.only ? CASES.filter((entry) => config.only.includes(entry.id)) : CASES;
assert.ok(selected.length > 0, 'no cases selected');

const sourceFiles = [
  'frontend/scripts/parallel-actions/run-action-eval.mjs',
  ...['local/semantics/actions/index', 'local/semantics/actions/checks', 'local/semantics/actions/scene',
    'local/semantics/actions/prompts', 'local/semantics/actions/text', 'local/semantics/actions/inputs',
    'local/semantics/actions/types', 'local/semantics/actions/fixtures', 'local/state', 'local/prompt',
    'runtime/structured-output', 'runtime/output-schema', 'runtime/wllama-engine', 'runtime/engine']
    .map((name) => `frontend/src/lib/world-engine/${name}.ts`),
];
const assetPath = config.model.startsWith('/') ? resolve(config.assets, config.model.slice(1)) : resolve(config.model);
const report = {
  status: 'IN_PROGRESS', recordedAt: new Date().toISOString(), config: { ...config, assetPath },
  source: {
    head: git('rev-parse', 'HEAD'), status: git('status', '--short', '--untracked-files=no'),
    sha256: Object.fromEntries(sourceFiles.map((file) => [file, fileSha(resolve(root, file))])),
    contractDigest: JSON.parse(readFileSync(resolve(root, 'frontend/src/lib/world-engine/contract-digest.json'), 'utf8')),
  },
  assets: {
    model: config.model, modelSha256: existsSync(assetPath) ? fileSha(assetPath) : null,
    modelBytes: existsSync(assetPath) ? statSync(assetPath).size : null,
    wllamaSha256: existsSync(resolve(config.assets, 'wllama/index.min.js')) ? fileSha(resolve(config.assets, 'wllama/index.min.js')) : null,
    wasmSha256: existsSync(resolve(config.assets, 'wasm/wllama.wasm')) ? fileSha(resolve(config.assets, 'wasm/wllama.wasm')) : null,
  },
  device: { cpu: cpus()[0]?.model, logicalCpus: cpus().length },
  cases: selected.map(({ id, task, note }) => ({ id, task, note })),
  runs: [],
};
const save = () => { mkdirSync(dirname(output), { recursive: true }); writeFileSync(output, JSON.stringify(report, null, 2) + '\n'); };
save();

function assetMiddleware(vite) {
  vite.middlewares.use((req, res, next) => {
    res.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
    res.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
    const url = (req.url ?? '').split('?')[0];
    if (url === '/__actions') {
      res.setHeader('Content-Type', 'text/html');
      res.end('<!doctype html><meta charset="utf-8"><title>Action evaluation</title><body></body>');
      return;
    }
    const asset = /^\/(models|wllama|wasm)\//.exec(url);
    if (!asset) { next(); return; }
    const file = resolve(config.assets, url.slice(1));
    if (!existsSync(file)) { next(); return; }
    res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript'
      : file.endsWith('.wasm') ? 'application/wasm' : 'application/octet-stream');
    res.setHeader('Content-Length', statSync(file).size);
    createReadStream(file).pipe(res);
  });
}

if (config.dry) {
  // No model: build the scenes and prompts for every case and archive them.
  // This proves the runnable interface and the prompt inputs without
  // pretending to be semantic evidence.
  const server = await createServer({ root: frontend, configFile: false, logLevel: 'warn',
    cacheDir: '../.local/action-eval-vite', server: { host: '127.0.0.1', port: 0, hmr: false },
    plugins: [{ name: 'action-dry', configureServer: assetMiddleware }] });
  let dryBrowser;
  try {
    await server.listen();
    dryBrowser = await chromium.launch({ headless: true, channel: config.channel });
    const page = await dryBrowser.newPage();
    await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__actions`);
    const rows = await page.evaluate(async (entries) => {
      const actions = await import('/src/lib/world-engine/local/semantics/actions/index.ts');
      const { buildInitialState } = await import('/src/lib/world-engine/local/state.ts');
      const { roomOf } = await import('/src/lib/world-engine/local/prompt.ts');
      const world = await (await fetch('/worlds/dragon-raja-free-day.world.json')).json();
      const apply = (state, patch = []) => {
        for (const move of patch) {
          const entity = state.characters[move.entityId] ?? state.items[move.entityId];
          entity.position = { containerId: move.containerId, slotId: move.slotId ?? null, relativeTo: null };
        }
        return state;
      };
      return entries.map((entry) => {
        const state = apply(structuredClone(buildInitialState({ ...world.initial, worldId: world.worldId })), entry.patch);
        const focus = entry.task === 'action' ? entry.actor : entry.task === 'targets' ? entry.source : entry.member;
        const offscreen = focus !== state.protagonistId && roomOf(state, focus) !== roomOf(state, state.protagonistId);
        const scopedSkip = offscreen && entry.offscreenPolicy === 'skip';
        const scene = actions.buildScene(state, focus, {
          playerInput: scopedSkip ? null : entry.playerInput ?? entry.actionText ?? null,
          aliases: {}, events: scopedSkip ? [] : entry.events ?? [] });
        const prompt = entry.task === 'action' ? actions.actionPrompt(scene)
          : entry.task === 'targets' ? actions.targetsPrompt(scene, entry.actionText, 2)
          : actions.reactionPrompt(scene, actions.buildScene(state, entry.source).actor, entry.actionText);
        return { id: entry.id, task: entry.task, offscreen, scopedSkip, promptChars: prompt.length, prompt,
          scene: { room: scene.roomName, visible: scene.visible.map((c) => c.name), absent: scene.absent.map((c) => `${c.name}@${c.roomName}`),
            items: scene.items.map((item) => `${item.name}@${item.position}`) } };
      });
    }, selected);
    report.dryRuns = rows;
    report.status = 'DRY';
    save();
    console.log(`[action-eval] dry: ${rows.length} prompts dumped to ${output}`);
  } finally {
    if (dryBrowser) await dryBrowser.close();
    await server.close();
  }
  process.exit(0);
}

let browser;
let server;
try {
  server = await createServer({ root: frontend, configFile: false, logLevel: 'warn',
    cacheDir: '../.local/action-eval-vite', server: { host: '127.0.0.1', port: 0, hmr: false },
    plugins: [{ name: 'action-eval', configureServer: assetMiddleware }] });
  await server.listen();
  const port = server.httpServer.address().port;
  browser = await chromium.launch({ headless: true, channel: config.channel });
  report.browser = browser.version();
  const page = await browser.newPage();
  page.on('pageerror', (error) => console.error('[pageerror]', error.message));
  await page.goto(`http://127.0.0.1:${port}/__actions`);
  const loaded = await page.evaluate(async (config) => {
    if (!crossOriginIsolated) throw new Error('action eval requires cross-origin isolation');
    const { WllamaInferenceEngine } = await import('/src/lib/world-engine/runtime/wllama-engine.ts');
    const { buildInitialState } = await import('/src/lib/world-engine/local/state.ts');
    const engine = new WllamaInferenceEngine({ modelUrl: config.model, contextSize: config.contextSize, numThreads: config.numThreads });
    const started = performance.now();
    await engine.load();
    const world = await (await fetch('/worlds/dragon-raja-free-day.world.json')).json();
    window.__actions = { engine, worldState: buildInitialState({ ...world.initial, worldId: world.worldId }), events: [] };
    return { loadMs: performance.now() - started, topology: engine.diagnostics };
  }, config);
  report.loadMs = loaded.loadMs;
  report.topology = loaded.topology;
  save();

  for (const entry of selected) {
    console.log(`[action-eval] ${entry.id}`);
    const row = await page.evaluate(async ({ entry, config }) => {
      const actions = await import('/src/lib/world-engine/local/semantics/actions/index.ts');
      const state = structuredClone(window.__actions.worldState);
      for (const move of entry.patch ?? []) {
        const entity = state.characters[move.entityId] ?? state.items[move.entityId];
        entity.position = { containerId: move.containerId, slotId: move.slotId ?? null, relativeTo: null };
      }
      const handlers = actions.createActionHandlers({ engine: window.__actions.engine, options: {
        capturePrompts: true, temperature: config.temperature, seed: config.seed,
        timeoutMs: config.timeoutMs, maxTokens: { action: config.maxTokens, targets: config.maxTokens, reaction: config.maxTokens },
        offscreenPolicy: entry.offscreenPolicy ?? 'skip',
        recentEvents: () => entry.events ?? [],
      } });
      const input = entry.task === 'action'
        ? { actor: entry.actor, advance: { inputText: entry.playerInput, intentStatus: entry.intentStatus ?? 'pending' }, workingState: state }
        : entry.task === 'targets'
          ? { sourceId: entry.source, actionText: entry.actionText, workingState: state }
          : { sourceId: entry.source, memberId: entry.member, sourceActionText: entry.actionText, rollId: 'roll_eval', workingState: state };
      const focus = entry.task === 'action' ? entry.actor : entry.task === 'targets' ? entry.source : entry.member;
      const scene = actions.buildScene(state, focus, { playerInput: entry.playerInput ?? null, aliases: {}, events: entry.events ?? [] });
      const started = performance.now();
      const result = entry.task === 'action' ? await handlers.action(entry.actor, input)
        : entry.task === 'targets' ? await handlers.targets(entry.source, input)
          : await handlers.reaction(entry.member, input);
      return { ...result, wallMs: Math.round(performance.now() - started), sourceType: result.source,
        scene: { room: scene.roomName,
          visible: scene.visible.map((character) => ({ id: character.id, name: character.name, position: character.position })),
          absent: scene.absent.map((character) => ({ id: character.id, name: character.name, room: character.roomName })),
          items: scene.items.map((item) => ({ id: item.id, name: item.name, position: item.position })) } };
    }, { entry, config });
    report.runs.push({ ...row, caseId: entry.id, note: entry.note, input: entry });
    save();
    const verdict = row.fallback ? 'FALLBACK' : row.source;
    console.log(`[action-eval] ${entry.id}: ${verdict} attempts=${row.attempts} ${row.elapsedMs}ms issues=${row.issues.map((item) => item.code).join(',') || '-'}`);
  }

  // Structural invariants only. Semantic quality is for review, not asserted.
  for (const run of report.runs) {
    const raw = typeof run.value === 'string' ? run.value : JSON.stringify(run.value);
    assert.ok(raw && raw.length > 0, `${run.caseId}: empty value`);
    if (run.caseId === 'A4a-offscreen-skip') {
      assert.equal(run.source, 'program', 'skip policy must not be model-decided');
      assert.equal(run.attempts, 0, 'skip policy must not spend a call');
    }
    if (run.caseId === 'A4b-offscreen-judge') {
      assert.ok(run.attempts >= 1, 'judge policy must actually ask the model');
      assert.ok(run.calls[0].prompt.includes('主角不在这里'), 'judged off-screen actor must not see the protagonist move');
      assert.ok(!run.calls[0].prompt.includes('我靠在巷口墙边喘口气。'), 'judged off-screen actor must not receive the player line');
    }
    if (run.caseId === 'A5-protagonist-pending') {
      assert.equal(run.source, 'program', 'pending player command is program-owned');
      assert.equal(run.attempts, 0, 'pending player command must not spend a call');
    }
    if (run.caseId === 'R2-protagonist-member') {
      assert.equal(run.source, 'program', 'the player character is never model-written');
      assert.equal(run.attempts, 0, 'protagonist reaction must not spend a call');
      assert.equal(run.value, '路明非没有作出反应。');
    }
  }

  const all = report.runs.flatMap((run) => run.calls.map((call) => call.elapsedMs)).sort((a, b) => a - b);
  const byTask = (task) => report.runs.filter((run) => run.task === task);
  report.summary = {
    cases: report.runs.length,
    calls: all.length,
    meanCallMs: all.length ? Math.round(all.reduce((sum, ms) => sum + ms, 0) / all.length) : null,
    p50CallMs: all.length ? all[Math.floor(all.length / 2)] : null,
    maxCallMs: all.length ? all[all.length - 1] : null,
    perTask: Object.fromEntries(['action', 'targets', 'reaction'].map((task) => {
      const runs = byTask(task);
      return [task, {
        cases: runs.length,
        model: runs.filter((run) => run.source === 'model').length,
        program: runs.filter((run) => run.source === 'program').length,
        fallback: runs.filter((run) => run.source === 'fallback').length,
        withIssues: runs.filter((run) => run.issues.some((item) => item.severity !== 'info')).length,
        repairs: runs.filter((run) => run.attempts > 1).length,
      }];
    })),
    issueCounts: report.runs.flatMap((run) => run.issues).reduce((counts, item) => {
      counts[item.code] = (counts[item.code] ?? 0) + 1; return counts;
    }, {}),
  };
  report.status = 'COMPLETED';
  report.completedAt = new Date().toISOString();
  save();
  console.log(`[action-eval] done: ${report.summary.cases} cases, ${report.summary.calls} calls, archive ${output}`);
} catch (error) {
  report.status = 'INTERRUPTED';
  report.error = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
  save();
  throw error;
} finally {
  if (browser) await browser.close();
  if (server) await server.close();
  report.cleanup = { browserClosed: Boolean(browser), serverClosed: Boolean(server) };
  save();
}
