// B-side A4 connection check. Runs B's unchanged HTTP transport/controller
// against A's documented persistent factory, with an isolated SQLite file.
// Fixed model outputs are transport fixtures, not real-model acceptance.
import assert from 'node:assert/strict';
import { createHash, randomUUID } from 'node:crypto';
import { execFileSync, spawn } from 'node:child_process';
import { closeSync, mkdirSync, openSync, readFileSync, writeFileSync } from 'node:fs';
import { createServer as createNetServer } from 'node:net';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import { chromium } from '@playwright/test';

const frontend = fileURLToPath(new URL('../', import.meta.url));
const root = resolve(frontend, '..');
const [aPath = resolve(root, '.local/world-server-worktree'), outputPath = resolve(root, 'artifacts/a4-browser-transport.json')] = process.argv.slice(2);
const serverRoot = resolve(aPath);
const output = resolve(outputPath);
const runtime = resolve(root, '.local/a4-browser-transport', randomUUID());
mkdirSync(runtime, { recursive: true });
mkdirSync(dirname(output), { recursive: true });
const sha = (path) => createHash('sha256').update(readFileSync(path)).digest('hex');
const identity = (checkout, files) => {
  const git = (...args) => execFileSync('git', ['-c', `safe.directory=${checkout.replaceAll('\\', '/')}`, '-C', checkout, ...args], { encoding: 'utf8' }).trim();
  return { head: git('rev-parse', 'HEAD'), status: git('status', '--short'),
    sha256: Object.fromEntries(files.map((file) => [file, sha(resolve(checkout, file))])) };
};
const aFiles = ['backend/app/world_app.py', 'backend/app/routers/worlds.py', 'backend/app/services/world/authority.py', 'backend/app/services/world/control.py', 'backend/app/database/world_store.py'];
const bFiles = ['frontend/scripts/review-world-a4-transport.mjs', 'frontend/scripts/review-world-h2-history.mjs',
  ...['controller', 'schedule', 'http-transport', 'protocol', 'recovery'].map((name) => `frontend/src/lib/world-engine/${name}.ts`)];
const before = { A: identity(serverRoot, aFiles), B: identity(root, bFiles) };
const report = { status: 'IN_PROGRESS', recordedAt: new Date().toISOString(), ...before,
  scope: 'A4 B transport connection; fixed outputs; excludes TTL expiry, full H2 and real-model acceptance',
  factory: 'app.world_app:create_persistent_world_app',
  contractDigest: JSON.parse(readFileSync(resolve(frontend, 'src/lib/world-engine/contract-digest.json'), 'utf8')) };
const save = () => writeFileSync(output, JSON.stringify(report, null, 2) + '\n');
save();
const freePort = () => new Promise((accept, reject) => {
  const socket = createNetServer(); socket.on('error', reject);
  socket.listen(0, '127.0.0.1', () => { const port = socket.address().port; socket.close(() => accept(port)); });
});
const apiPort = await freePort();
const browserPort = await freePort();
const apiUrl = `http://127.0.0.1:${apiPort}`;
const origin = `http://127.0.0.1:${browserPort}`;
const logFd = openSync(resolve(runtime, 'server.log'), 'w');
let service, browser, vite;
async function stop(child) {
  if (!child || child.exitCode !== null) return;
  await new Promise((done) => { child.once('exit', done); child.kill(); });
}
try {
  service = spawn(process.env.WORLD_PYTHON ?? 'python', ['-X', 'utf8', '-m', 'uvicorn', report.factory,
    '--factory', '--host', '127.0.0.1', '--port', String(apiPort), '--log-level', 'warning'], {
    cwd: resolve(serverRoot, 'backend'), windowsHide: true, stdio: ['ignore', logFd, logFd],
    env: { ...process.env, WORLD_SQLITE_PATH: resolve(runtime, 'world.sqlite'), WORLD_ALLOWED_ORIGINS: origin },
  });
  let spawnError;
  service.on('error', (error) => { spawnError = error; });
  const deadline = Date.now() + 30_000;
  for (;;) {
    if (spawnError) throw spawnError;
    if (service.exitCode !== null) throw new Error(`A service exited; see ${runtime}/server.log`);
    try { if ((await fetch(`${apiUrl}/openapi.json`)).ok) break; } catch { /* startup */ }
    if (Date.now() >= deadline) throw new Error('A service startup timeout');
    await new Promise((done) => setTimeout(done, 100));
  }
  const allowed = await fetch(`${apiUrl}/worlds`, { method: 'OPTIONS', headers: {
    Origin: origin, 'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'content-type,x-world-protocol-version',
  } });
  assert.equal(allowed.status, 200);
  assert.equal(allowed.headers.get('access-control-allow-origin'), origin);
  const denied = await fetch(`${apiUrl}/worlds`, { method: 'OPTIONS', headers: {
    Origin: 'http://127.0.0.1:1', 'Access-Control-Request-Method': 'POST',
  } });
  assert.equal(denied.status, 400);
  assert.equal(denied.headers.get('access-control-allow-origin'), null);
  report.cors = { allowedStatus: allowed.status, deniedStatus: denied.status, exactOrigin: true };
  vite = await createServer({ root: frontend, configFile: false, cacheDir: resolve(runtime, 'vite'),
    server: { host: '127.0.0.1', port: browserPort, strictPort: true, hmr: false },
    plugins: [{ name: 'a4-probe', configureServer(server) { server.middlewares.use((req, res, next) => {
      if (req.url !== '/__a4') return next();
      res.setHeader('Content-Type', 'text/html'); res.end('<!doctype html><title>A4 transport connection</title>');
    }); } }] });
  await vite.listen();
  browser = await chromium.launch({ channel: 'msedge', headless: true });
  report.browser = browser.version();
  const page = await browser.newPage();
  await page.goto(`${origin}/__a4`);
  const trace = JSON.parse(readFileSync(resolve(root, 'design/world-protocol/v2/traces/T01.json'), 'utf8'));
  report.rootFlows = await page.evaluate(async ({ apiUrl, trace }) => {
    const { HttpWorldTransport } = await import('/src/lib/world-engine/http-transport.ts');
    const { ControllerDriver, initialMemory } = await import('/src/lib/world-engine/controller.ts');
    const { instantiate } = await import('/src/lib/world-engine/trace-runner.ts');
    const check = (condition, message) => { if (!condition) throw new Error(message); };
    const results = [];
    for (const sample of trace.samples) {
      const req = Object.fromEntries(trace.steps.map((step) => [step.id, instantiate(step.request, sample.values)]));
      const http = new HttpWorldTransport(apiUrl); // browser default fetch, no injection
      const calls = [], tasks = [];
      const transport = { async execute(operation, request, scope) {
        const response = await http.execute(operation, request, scope);
        check(response.schemaVersion === 2, 'wrong envelope version');
        calls.push({ operation, request, response }); return response;
      } };
      const model = { async generate(task) {
        tasks.push(task);
        if (task === 'initial') return req.s1.initial;
        if (task === 'narration') return req.s3.text;
        throw new Error(`unexpected model task ${task}`);
      } };
      const driver = new ControllerDriver({ transport, model }, initialMemory(`a4_${sample.id}`, 'a4_browser'));
      let terminal;
      for (let index = 0; index < 20 && !terminal; index++) terminal = await driver.step();
      check(terminal?.kind === 'await', 'root flow did not await player input');
      check(JSON.stringify(tasks) === JSON.stringify(['initial', 'narration']), 'wrong task sequence');
      const claim = calls.find((call) => call.operation === 'narration_claim');
      const submit = calls.find((call) => call.operation === 'narration_submit');
      for (const key of ['claimToken', 'generation', 'issuedAtEpochMilli']) {
        check(submit.request[key] === claim.response.data[key], `claim receipt mismatch: ${key}`);
      }
      const created = calls.find((call) => call.operation === 'create_world').response;
      check(created.control.gate.status !== 'none' && !created.control.canCompute, 'creation gate missing');
      const scope = { worldId: created.data.worldId };
      const context = await http.execute('get_context', {}, scope);
      check(context.control.gate.status === 'none' && context.world.head.narrationStatus === 'ready', 'root gate not resolved');
      const first = await http.execute('get_state', {}, scope);
      const repeated = await http.execute('get_state', {}, scope);
      check(JSON.stringify(first.data) === JSON.stringify(repeated.data), 'read changed');
      check(first.data.stateDigest === created.world.head.stateDigest, 'root digest changed');
      const ids = calls.map((call) => call.request.requestId).filter(Boolean);
      check(new Set(ids).size === ids.length, 'duplicate request id');
      results.push({ sampleId: sample.id, worldId: scope.worldId, stateDigest: first.data.stateDigest,
        operations: calls.map((call) => call.operation), tasks, claimTriplePreserved: true,
        freshRequestIds: true, rootGateResolved: true, readStable: true });
    }
    return results;
  }, { apiUrl, trace });
  const historyPath = resolve(runtime, 'history.json');
  await new Promise((done, reject) => {
    const child = spawn(process.execPath, [resolve(frontend, 'scripts/review-world-h2-history.mjs'), apiUrl, historyPath, serverRoot],
      { cwd: frontend, windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] });
    let stderr = ''; child.stderr.on('data', (data) => { stderr += data; });
    child.once('error', reject);
    child.once('exit', (code) => code === 0 ? done() : reject(new Error(`B history harness failed (${code}): ${stderr}`)));
  });
  report.history = JSON.parse(readFileSync(historyPath, 'utf8'));
  assert.equal(report.history.status, 'PASS_HISTORY_SUBCHECK');
  assert.deepEqual(identity(serverRoot, aFiles).sha256, before.A.sha256);
  assert.deepEqual(identity(root, bFiles).sha256, before.B.sha256);
  report.sourceUnchangedDuringRun = true;
  report.status = 'PASS';
} catch (error) {
  report.status = 'FAIL'; report.error = String(error); throw error;
} finally {
  if (browser) await browser.close();
  if (vite) await vite.close();
  await stop(service); closeSync(logFd);
  report.cleanup = { browserClosed: true, viteClosed: true, serviceStopped: true };
  report.completedAt = new Date().toISOString(); save();
}
console.log(`PASS A4 B transport: ${report.rootFlows.length} browser root flows + existing full-roster history harness; ${output}`);
