// G5 real HTTP/SQLite fault-recovery acceptance (commander task, 2026-10-30).
// Baselines: world-browser@26ba477 (product) + agent checkout (server).
// Real uvicorn service, real SQLite, independent port/output dir; NO model
// calls, frozen v5/v6 evidence untouched.
//
//   node scripts/review-g5-http-recovery.mjs --server-checkout <服务检出> `
//        [--expect-server-head <sha 前缀>] [--out artifacts/g5-http-recovery/g5-http-recovery.json]
//
// Scenarios (each on its own fresh world inside the one service/DB):
//   S1  committed-but-receipt-lost: the server really commits allocate_ids,
//       the client wrapper drops the success receipt AFTER the HTTP round trip
//       (injection point: after server commit, before client consumption; the
//       DB rows are read at the injection moment as commit proof). The product
//       session blocks/terminals; the EXACT captured request (same requestId +
//       same body) is then replayed over a raw transport and must return the
//       same identities with no new DB rows (request-level idempotency).
//   S2  takeover in the committed-but-unfolded window: the blocked session's
//       lease is released, a fresh session recovers with a NEW lease and NEW
//       request namespace; the stable allocationKey replays the SAME batch and
//       the automatic round then runs to completion on the real product stack.
//   S3  the two idempotency layers separately: same requestId + different
//       body → request_id_reused; NEW requestId + same allocationKey/slots →
//       business replay of the original batch.
//   S4  old-lease rejection: NEW requestId under an old lease → refused, no DB
//       change. Recorded separately: the SAME requestId exact replay under the
//       old lease SUCCEEDS (request-level replay precedes lease validation).
//   S5  post-fault state: blocked terminal, submit refusal, recovered
//       identities, DB consumption counts before/after (woven into S1/S2 and
//       summarized).
//
// Failures are deliverable evidence: an assertion failure fails the run and
// keeps every recorded wire/DB artifact.
import assert from 'node:assert/strict';
import { execFileSync, spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { createWriteStream, existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { createServer as createNetServer } from 'node:net';

const frontend = fileURLToPath(new URL('../', import.meta.url));
const root = resolve(frontend, '..');
const option = (flag, fallback) => process.argv.includes(flag) ? process.argv[process.argv.indexOf(flag) + 1] : fallback;
const output = resolve(root, option('--out', 'artifacts/g5-http-recovery/g5-http-recovery.json'));

// 服务检出必填：旧默认路径已退役（e8302bf 同款守卫）。
const checkoutArg = option('--server-checkout', null);
if (!checkoutArg) {
  console.error('[g5-http] FAILED: --server-checkout <服务检出> is required (the old default checkout is retired)');
  process.exit(1);
}
const serverCheckout = resolve(root, checkoutArg);
if (!existsSync(resolve(serverCheckout, 'backend', 'app', 'world_app.py'))) {
  console.error(`[g5-http] FAILED: --server-checkout ${checkoutArg} has no backend/app/world_app.py`);
  process.exit(1);
}
const serverHead = execFileSync('git', ['-c', `safe.directory=${serverCheckout.replaceAll('\\', '/')}`, '-C', serverCheckout, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
console.log(`[g5-http] server checkout HEAD ${serverHead}`);
const expectedHead = option('--expect-server-head', null);
if (expectedHead && !serverHead.startsWith(expectedHead)) {
  console.error(`[g5-http] FAILED: server HEAD ${serverHead} does not match --expect-server-head ${expectedHead}`);
  process.exit(1);
}

// ---- TS loading (same transpile pattern as the offline probes) ----
const require = createRequire(import.meta.url);
const ts = require('typescript');
require.extensions['.ts'] = (module, file) => module._compile(ts.transpileModule(readFileSync(file, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
}).outputText, file);
const load = (p) => require(resolve(frontend, 'src', p));
const { HttpWorldTransport } = load('lib/world-engine/http-transport.ts');
const { WorldTimeoutError, WorldApiError } = load('lib/world-engine/transport.ts');
const { ControllerDriver, initialMemory } = load('lib/world-engine/controller.ts');
const { RuleWorldSession } = load('lib/world-engine/runtime/rule-session.ts');
const { defaultInitialTemplate, WORLD_POLICY } = load('app/world/world-defaults.ts');

// ---- baselines & source pinning ----
const browserHead = execFileSync('git', ['-C', root, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
const browserStatus = execFileSync('git', ['-C', root, 'status', '--short'], { encoding: 'utf8' }).replace(/\n+$/, '');
const serverStatus = execFileSync('git', ['-C', serverCheckout, 'status', '--short', '--', 'backend/app'], { encoding: 'utf8' }).replace(/\n+$/, '');
if (browserStatus) { console.error(`[g5-http] FAILED: browser tree dirty:\n${browserStatus}`); process.exit(1); }
if (serverStatus) { console.error(`[g5-http] FAILED: server backend/app dirty:\n${serverStatus}`); process.exit(1); }
const pinnedFiles = [
  'frontend/scripts/review-g5-http-recovery.mjs',
  'frontend/src/lib/world-engine/controller.ts',
  'frontend/src/lib/world-engine/schedule.ts',
  'frontend/src/lib/world-engine/recovery.ts',
  'frontend/src/lib/world-engine/http-transport.ts',
  'frontend/src/lib/world-engine/transport.ts',
  'frontend/src/lib/world-engine/runtime/rule-session.ts',
  'frontend/src/lib/world-engine/runtime/session.ts',
  'frontend/src/app/world/world-defaults.ts',
];
const serverAppRoot = resolve(serverCheckout, 'backend', 'app').replaceAll('\\', '/');
const walkServerFiles = (dir) => readdirSync(dir, { withFileTypes: true }).flatMap((entry) => entry.isDirectory()
  ? (entry.name === '__pycache__' ? [] : walkServerFiles(resolve(dir, entry.name))) : [resolve(dir, entry.name)]);
const serverFiles = walkServerFiles(resolve(serverCheckout, 'backend', 'app'))
  .map((file) => ({ path: `backend/app/${file.replaceAll('\\', '/').slice(serverAppRoot.length + 1)}`, file }));
const sha = (file) => createHash('sha256').update(readFileSync(file)).digest('hex');

const report = {
  kind: 'g5-http-recovery', status: 'IN_PROGRESS', recordedAt: new Date().toISOString(),
  baselines: {
    browser: { head: browserHead, status: browserStatus },
    server: { checkout: 'agent', head: serverHead, status: serverStatus },
    browserSourceSha256: Object.fromEntries(pinnedFiles.map((file) => [file, sha(resolve(root, file))])),
    serverSourceSha256: Object.fromEntries(serverFiles.map(({ path, file }) => [path, sha(file)])),
  },
  service: null, scenarios: {}, summary: null,
};
const save = () => { mkdirSync(resolve(output, '..'), { recursive: true }); writeFileSync(output, JSON.stringify(report, null, 2) + '\n'); };
save();

// ---- service ----
async function freePort() {
  const probe = createNetServer();
  const port = await new Promise((done, fail) => { probe.once('error', fail); probe.listen(0, '127.0.0.1', () => done(probe.address().port)); });
  await new Promise((done) => probe.close(done));
  return port;
}
const apiPort = await freePort();
const apiOrigin = `http://127.0.0.1:${apiPort}`;
const privateDir = resolve(root, `.local/g5-http-${Date.now()}`);
mkdirSync(privateDir, { recursive: true });
const dbPath = resolve(privateDir, 'world.db');
report.service = { apiOrigin, port: apiPort, dbFile: 'world.db (in the run-private dir; a readable copy is archived with the report)' };
save();
const service = spawn(option('--python', 'python'), ['-X', 'utf8', '-m', 'uvicorn', 'app.world_app:create_persistent_world_app', '--factory',
  '--host', '127.0.0.1', '--port', String(apiPort)], { cwd: resolve(serverCheckout, 'backend'),
  env: { ...process.env, WORLD_SQLITE_PATH: dbPath, WORLD_ALLOWED_ORIGINS: 'http://127.0.0.1' },
  windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
const serviceLog = createWriteStream(resolve(privateDir, 'server.log'), { flags: 'a' });
service.stdout.pipe(serviceLog); service.stderr.pipe(serviceLog);
const cleanup = () => { try { service.kill(); } catch {} };
process.on('exit', cleanup);
const waitReady = async () => {
  for (let attempt = 0; ; attempt++) {
    if (service.exitCode !== null) throw new Error('World HTTP service exited before readiness');
    try { const r = await fetch(`${apiOrigin}/openapi.json`, { signal: AbortSignal.timeout(8000) }); if (r.ok) return; } catch { /* booting */ }
    if (attempt >= 60) throw new Error('World HTTP service readiness timeout');
    await new Promise((done) => setTimeout(done, 500));
  }
};
await waitReady();
console.log('[g5-http] service ready');

// ---- DB evidence (direct read of the real SQLite file) ----
const dbQuery = (sql, params = []) => JSON.parse(execFileSync(option('--python', 'python'),
  ['-X', 'utf8', '-c',
    `import sqlite3,json
con=sqlite3.connect(r'file:${dbPath.replaceAll('\\', '/')}?mode=ro',uri=True)
cur=con.execute(${JSON.stringify(sql)}, ${JSON.stringify(params)})
print(json.dumps([dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchall()]))`,
  ], { encoding: 'utf8' }));
const dbAllocations = (worldId) => dbQuery(
  'SELECT allocation_key, slot_key, allocated_id AS id, kind FROM world_id_allocations WHERE world_id=? ORDER BY allocation_key, slot_key', [worldId]);
const dbConsumedRounds = (worldId) => dbQuery('SELECT id, input_id FROM world_advances WHERE world_id=?', [worldId]);

// ---- wire recording ----
const trimResponse = (op, response) => {
  if (op === 'allocate_ids') return structuredClone(response);
  if (op === 'round_conclusion_conclude' || op.startsWith('lease_')) return structuredClone(response);
  if (op === 'get_state') return { pointId: response?.data?.pointId, version: response?.data?.version, stateDigest: response?.data?.stateDigest, previousPointId: response?.data?.previousPointId };
  if (op === 'get_context') return { phase: response?.control?.phase, revision: response?.control?.revision, activeRoundId: response?.world?.activeRoundId, activePointId: response?.world?.activePointId, advanceId: response?.world?.advance?.advanceId, roundTrigger: response?.world?.round?.trigger ?? null };
  if (op === 'list_points') return { points: (response?.data?.points ?? []).map((p) => ({ pointId: p.pointId, kind: p.kind, roundId: p.roundId })) };
  if (op === 'checkpoint_begin_point') return { pointId: response?.data?.pointId };
  return { dataKeys: Object.keys(response?.data ?? {}) };
};
const recorder = (inner, wire) => ({ async execute(op, body, scope, signal) {
  const entry = { op, request: structuredClone(body), at: Date.now() };
  try {
    const response = await inner.execute(op, body, scope, signal);
    entry.response = trimResponse(op, response);
    wire.push(entry);
    return response;
  } catch (error) {
    entry.error = error instanceof WorldApiError ? { code: error.response.error.code, clientAction: error.response.error.clientAction } : String(error?.message ?? error);
    wire.push(entry);
    throw error;
  }
} });
const raw = new HttpWorldTransport(apiOrigin);

// ---- world window: round 1 driven by a scripted-port controller over REAL HTTP,
// concluded as continue into a pre-allocated automatic round, stopped at the
// G5 window (round open, no point, no r2 identities) ----
class WindowReady extends Error {}
async function buildWindow(label, wire) {
  const transport = recorder(raw, wire);
  const created = await transport.execute('create_world', { protocolVersion: 2, requestId: `${label}_create`, initial: defaultInitialTemplate() }, {});
  const worldId = created.data.worldId;
  const lease = { leaseToken: created.data.lease.leaseToken, fenceEpoch: created.data.lease.fenceEpoch };
  const roster = Object.keys(defaultInitialTemplate().characters).sort();
  const protagonist = defaultInitialTemplate().protagonistId;
  // 程序预分配下一轮 round id（continue 结论需要；G4 接线前的合法预置路径）。
  const roundAlloc = await transport.execute('allocate_ids', { protocolVersion: 2, requestId: `${label}_round2`, worldId,
    leaseToken: lease.leaseToken, fenceEpoch: lease.fenceEpoch,
    allocationKey: `${label}_next_round`, slots: [{ slotKey: 'round_next', kind: 'round' }] }, { worldId });
  const nextRoundId = roundAlloc.data.allocations[0].id;
  const memory = initialMemory(`${label}_drv`, `${label}_holder`);
  memory.leaseToken = lease.leaseToken;
  // pointPlan 每轮规划一次：round 1 给真计划（pointId 读驱动活内存——
  // bootstrapRecovery 会整体替换 memory，闭包旧引用是陈旧值）；
  // continue 后的新轮规划即窗口哨兵。
  const live = { driver: null };
  const port = {
    generate: async (task, key) => {
      if (task === 'pointPlan' && key === nextRoundId) throw new WindowReady(label); // the window
      if (task === 'pointPlan') return [{ pointId: live.driver.getMemory().ids.point, kind: 'normal',
        timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'second' } }, actorIds: [...roster] }];
      if (task === 'action') return { kind: 'skip' };
      if (task === 'updates') return [];
      if (task === 'narration') return `（${label} 结算叙事）`;
      if (task === 'continuation') return { kind: 'continue', closedBy: 'model', cancelReason: null, candidateCharacterIds: [protagonist], nextRoundId };
      throw new Error(`unexpected model task ${task}/${key}`);
    },
  };
  const driver = new ControllerDriver({ transport, model: port }, memory);
  live.driver = driver;
  await driver.recover(worldId, lease);
  const slots = [{ slotKey: 'advance', kind: 'advance' }, { slotKey: 'input', kind: 'input' }, { slotKey: 'round', kind: 'round' },
    { slotKey: 'point', kind: 'point' }, ...roster.map((actor) => ({ slotKey: `group:${actor}`, kind: 'group' }))];
  driver.preparePlayerInput('走到走廊', roster, { allocationKey: `${label}_cmd1`, slots }, slots.map((slot) => slot.slotKey));
  try { await driver.run(300); } catch (error) { if (!(error instanceof WindowReady)) throw error; }
  const context = await transport.execute('get_context', { includeRecovery: false }, { worldId });
  assert.equal(context.world.round?.trigger, 'automatic', `${label}: automatic round open`);
  assert.equal(context.world.activePointId ?? null, null, `${label}: no point yet`);
  assert.equal(context.control.phase, 'select_actor', `${label}: round entry phase`);
  const allocationsBefore = dbAllocations(worldId);
  return { worldId, lease, roster, protagonist, nextRoundId, allocationsBefore, context: trimResponse('get_context', context) };
}

// ---- product session transport with the receipt-drop fault ----
function faultTransport(inner, wire, faultState) {
  return { async execute(op, body, scope, signal) {
    if (faultState.armed && op === 'allocate_ids' && String(body.allocationKey ?? '').startsWith('product_round_')) {
      faultState.armed = false;
      // REAL HTTP round trip: the server transaction commits here.
      const response = await inner.execute(op, body, scope, signal);
      const worldId = body.worldId;
      const dbRowsAtInjection = dbAllocations(worldId).filter((row) => row.allocation_key === body.allocationKey);
      // Injection point: AFTER the server commit (rows visible in SQLite),
      // BEFORE the client consumes the receipt — drop it as a timeout.
      faultState.captured = { request: structuredClone(body), responseIds: response.data.allocations.map((a) => ({ ...a })), dbRowsAtInjection };
      faultState.faulted = true;
      const entry = { op, request: structuredClone(body), at: Date.now(), fault: 'receipt_dropped_after_server_commit', dbRowsAtInjection };
      wire.push(entry);
      console.log(`[g5-http] fault injected: ${body.allocationKey} committed (${dbRowsAtInjection.length} DB rows), receipt dropped`);
      throw new WorldTimeoutError('g5: receipt dropped after server commit');
    }
    return recorder(inner, wire).execute(op, body, scope, signal);
  } };
}
const sessionOptions = (transport, holderId) => ({ transport, initial: defaultInitialTemplate(), policy: WORLD_POLICY, holderId });

// ---- scenario runner ----
const results = [];
const check = async (name, fn) => {
  const wire = [];
  const started = Date.now();
  try {
    const detail = await fn(wire);
    report.scenarios[name] = { ok: true, ms: Date.now() - started, detail: detail ?? null, wire };
    results.push(name);
    console.log(`[g5-http] PASS ${name}`);
  } catch (error) {
    report.scenarios[name] = { ok: false, ms: Date.now() - started, error: String(error?.stack ?? error), wire };
    save();
    console.error(`[g5-http] FAIL ${name}:`, error);
    throw error;
  }
  save();
};

try {
  // ---------------- S1: committed, receipt lost, same-requestId replay ----------------
  await check('S1_committed_receipt_lost', async (wire) => {
    const win = await buildWindow('s1', wire);
    const fault = { armed: true, captured: null, faulted: false };
    const session = RuleWorldSession.createRecovered(sessionOptions(faultTransport(raw, wire, fault), 'g5_s1'), win.worldId, win.lease);
    const status = await session.attach();
    assert.ok(fault.faulted, 'the receipt-drop fault must have fired');
    assert.equal(fault.captured.dbRowsAtInjection.length, fault.captured.responseIds.length, 'server rows exist at the injection moment');
    assert.equal(status.kind, 'stop');
    assert.match(status.reason, new RegExp(`^round_identity_blocked:sink_failed:${win.nextRoundId}:`), 'the round entry is blocked by the failed allocation');
    assert.equal(session.sessionStatus, 'stopped', 'the blocked entry is a session terminal');
    await assert.rejects(session.submit('走到走廊'), /rule_session_identity_blocked/, 'submit refuses before writing input');
    assert.equal(session.getMemory().playerInput, null, 'no input was written into the driver memory');
    const dbAfterBlock = dbAllocations(win.worldId);
    assert.equal(dbAfterBlock.length, win.allocationsBefore.length + fault.captured.responseIds.length, 'exactly the committed batch exists');
    // Request-level replay: the EXACT captured request (same requestId, same body).
    const replay = await raw.execute('allocate_ids', structuredClone(fault.captured.request), { worldId: win.worldId });
    const replayIds = Object.fromEntries(replay.data.allocations.map((a) => [a.slotKey, a.id]));
    const originalIds = Object.fromEntries(fault.captured.responseIds.map((a) => [a.slotKey, a.id]));
    assert.deepEqual(replayIds, originalIds, 'the replay returns the same identities');
    assert.equal(dbAllocations(win.worldId).length, dbAfterBlock.length, 'no new DB rows from the replay');
    session.dispose();
    return {
      worldId: win.worldId, fault: fault.captured, blockedStop: status,
      dbAfterBlock, replay: { request: fault.captured.request, responseIds: replayIds }, nextRoundId: win.nextRoundId,
    };
  });

  // ---------------- S2: takeover in the committed-but-unfolded window ----------------
  await check('S2_takeover_same_batch', async (wire) => {
    const win = await buildWindow('s2', wire);
    const fault = { armed: true, captured: null, faulted: false };
    const sessionB = RuleWorldSession.createRecovered(sessionOptions(faultTransport(raw, wire, fault), 'g5_s2a'), win.worldId, win.lease);
    const statusB = await sessionB.attach();
    assert.ok(fault.faulted && statusB.kind === 'stop', 'session B blocks on the dropped receipt');
    const batchIds = Object.fromEntries(fault.captured.responseIds.map((a) => [a.slotKey, a.id]));
    const beforeCount = dbAllocations(win.worldId).length;
    // Real takeover: release the blocked session's lease, then a fresh session
    // recovers with a NEW lease (no heldLease → lease_acquire) and a NEW
    // request namespace; the stable allocationKey replays the same batch.
    await raw.execute('lease_release', { protocolVersion: 2, requestId: 's2_release', leaseToken: win.lease.leaseToken, fenceEpoch: win.lease.fenceEpoch }, { worldId: win.worldId });
    const sessionC = RuleWorldSession.createRecovered(sessionOptions(recorder(raw, wire), 'g5_s2b'), win.worldId);
    const statusC = await sessionC.attach();
    assert.equal(statusC.kind, 'stop');
    assert.equal(statusC.reason, 'world_complete', `the automatic round completes on the recovered batch (got: ${statusC.reason})`);
    const memoryC = sessionC.getMemory();
    assert.equal(memoryC.roundIdentityBlocked, null, 'no blocked state after recovery');
    assert.equal(memoryC.ids.point, batchIds.point, 'the recovered session plans the SAME point');
    assert.equal(memoryC.ids[`group:${win.protagonist}`], batchIds[`group:${win.protagonist}`], 'and the SAME group identity');
    assert.equal(dbAllocations(win.worldId).length, beforeCount, 'no new identities were consumed by the takeover');
    const points = await raw.execute('list_points', { after: null, limit: 100 }, { worldId: win.worldId });
    assert.equal(points.data.points.filter((p) => p.kind !== 'root').length, 2, 'round 1 point + the recovered automatic-round point');
    sessionB.dispose(); sessionC.dispose();
    return {
      worldId: win.worldId, fault: fault.captured, blockedStopB: statusB, endStatusC: statusC,
      recoveredIds: { point: memoryC.ids.point, group: memoryC.ids[`group:${win.protagonist}`] },
      points: points.data.points.map((p) => ({ pointId: p.pointId, kind: p.kind, roundId: p.roundId })),
    };
  });

  // ---------------- S3: the two idempotency layers, separately ----------------
  await check('S3_two_idempotency_layers', async (wire) => {
    const transport = recorder(raw, wire);
    const created = await transport.execute('create_world', { protocolVersion: 2, requestId: 's3_create', initial: defaultInitialTemplate() }, {});
    const worldId = created.data.worldId;
    const lease = { leaseToken: created.data.lease.leaseToken, fenceEpoch: created.data.lease.fenceEpoch };
    const key = 's3_batch';
    const slots = [{ slotKey: 'point', kind: 'point' }, { slotKey: 'group:p', kind: 'group' }];
    const first = await transport.execute('allocate_ids', { protocolVersion: 2, requestId: 's3_req_1', worldId,
      leaseToken: lease.leaseToken, fenceEpoch: lease.fenceEpoch, allocationKey: key, slots }, { worldId });
    const before = dbAllocations(worldId).length;
    // (a) same requestId + different body → request-level rejection.
    await assert.rejects(
      transport.execute('allocate_ids', { protocolVersion: 2, requestId: 's3_req_1', worldId,
        leaseToken: lease.leaseToken, fenceEpoch: lease.fenceEpoch, allocationKey: 's3_other_key', slots }, { worldId }),
      (error) => error instanceof WorldApiError && error.response.error.code === 'request_id_reused',
      'same requestId with a different body is refused');
    // (b) NEW requestId + same allocationKey/slots → business replay.
    const replay = await transport.execute('allocate_ids', { protocolVersion: 2, requestId: 's3_req_2', worldId,
      leaseToken: lease.leaseToken, fenceEpoch: lease.fenceEpoch, allocationKey: key, slots }, { worldId });
    assert.deepEqual(replay.data.allocations, first.data.allocations, 'the business layer replays the original batch');
    assert.equal(dbAllocations(worldId).length, before, 'no new DB rows from either call');
    return { worldId, first: first.data.allocations, reuseRefused: 'request_id_reused', replay: replay.data.allocations };
  });

  // ---------------- S4: old-lease rejection vs request-level replay ----------------
  await check('S4_old_lease_rejection', async (wire) => {
    const transport = recorder(raw, wire);
    const created = await transport.execute('create_world', { protocolVersion: 2, requestId: 's4_create', initial: defaultInitialTemplate() }, {});
    const worldId = created.data.worldId;
    const oldLease = { leaseToken: created.data.lease.leaseToken, fenceEpoch: created.data.lease.fenceEpoch };
    const key = 's4_batch';
    const slots = [{ slotKey: 'point', kind: 'point' }, { slotKey: 'group:p', kind: 'group' }];
    const first = await transport.execute('allocate_ids', { protocolVersion: 2, requestId: 's4_req_1', worldId,
      leaseToken: oldLease.leaseToken, fenceEpoch: oldLease.fenceEpoch, allocationKey: key, slots }, { worldId });
    // Move the lease: release + acquire as another holder.
    await transport.execute('lease_release', { protocolVersion: 2, requestId: 's4_release', leaseToken: oldLease.leaseToken, fenceEpoch: oldLease.fenceEpoch }, { worldId });
    const fresh = await transport.execute('lease_acquire', { protocolVersion: 2, requestId: 's4_acquire', worldId, holderId: 'g5_s4_holder2' }, { worldId });
    const newLease = { leaseToken: fresh.data.leaseToken, fenceEpoch: fresh.data.fenceEpoch };
    assert.notEqual(newLease.leaseToken, oldLease.leaseToken, 'the new lease is a different grant');
    const before = dbAllocations(worldId).length;
    // (i) NEW requestId under the OLD lease → lease-level refusal, no DB change.
    await assert.rejects(
      transport.execute('allocate_ids', { protocolVersion: 2, requestId: 's4_req_old_lease', worldId,
        leaseToken: oldLease.leaseToken, fenceEpoch: oldLease.fenceEpoch, allocationKey: 's4_other', slots }, { worldId }),
      (error) => error instanceof WorldApiError && ['lease_invalid', 'stale_epoch'].includes(error.response.error.code),
      'a new request under an old lease is refused by the lease layer');
    assert.equal(dbAllocations(worldId).length, before, 'the refused request consumed nothing');
    // (ii) SAME requestId + same body under the OLD lease → request-level replay
    // succeeds (idempotency precedes lease validation) — recorded separately so
    // the two layers are never conflated.
    const replay = await transport.execute('allocate_ids', { protocolVersion: 2, requestId: 's4_req_1', worldId,
      leaseToken: oldLease.leaseToken, fenceEpoch: oldLease.fenceEpoch, allocationKey: key, slots }, { worldId });
    assert.deepEqual(replay.data.allocations, first.data.allocations, 'the exact replay returns the original batch');
    assert.equal(dbAllocations(worldId).length, before, 'the replay consumes nothing new');
    return { worldId, first: first.data.allocations, newLease: { fenceEpoch: newLease.fenceEpoch }, oldLeaseRefused: true, exactReplayUnderOldLease: 'replayed_before_lease_check', replay: replay.data.allocations };
  });

  // ---------------- S5: post-fault state summary (re-verified live) ----------------
  await check('S5_post_fault_state', async (wire) => {
    const win = await buildWindow('s5', wire);
    const fault = { armed: true, captured: null, faulted: false };
    const session = RuleWorldSession.createRecovered(sessionOptions(faultTransport(raw, wire, fault), 'g5_s5'), win.worldId, win.lease);
    const status = await session.attach();
    const dbAtFault = dbAllocations(win.worldId);
    const advancesAtFault = dbConsumedRounds(win.worldId);
    // The blocked session is terminal in every observable channel.
    assert.equal(session.sessionStatus, 'stopped');
    await assert.rejects(session.submit('走到走廊'), /rule_session_identity_blocked/);
    await assert.rejects(session.submit('再走一步'), /rule_session_identity_blocked/, 'repeated submits keep refusing');
    assert.equal(session.getMemory().playerInput, null);
    // The window identities: exactly the faulted batch exists for the round.
    const roundKey = Object.keys(Object.fromEntries(dbAtFault.map((r) => [r.allocation_key, true]))).find((k) => k.startsWith('product_round_'));
    const batchRows = dbAtFault.filter((r) => r.allocation_key === roundKey);
    assert.deepEqual(batchRows.map((r) => r.id).sort(), fault.captured.responseIds.map((a) => a.id).sort(), 'DB rows equal the committed batch');
    // A fresh session recovers the same batch and finishes the round.
    await raw.execute('lease_release', { protocolVersion: 2, requestId: 's5_release', leaseToken: win.lease.leaseToken, fenceEpoch: win.lease.fenceEpoch }, { worldId: win.worldId });
    const sessionC = RuleWorldSession.createRecovered(sessionOptions(recorder(raw, wire), 'g5_s5b'), win.worldId);
    const statusC = await sessionC.attach();
    assert.equal(statusC.reason, 'world_complete');
    assert.equal(sessionC.getMemory().ids.point, fault.captured.responseIds.find((a) => a.slotKey === 'point').id);
    assert.equal(dbAllocations(win.worldId).length, dbAtFault.length, 'recovery consumed nothing new');
    assert.deepEqual(dbConsumedRounds(win.worldId), advancesAtFault, 'no extra advance was consumed');
    session.dispose(); sessionC.dispose();
    return { worldId: win.worldId, roundKey, dbAtFault, endStatus: statusC, submitsRefused: 2 };
  });

  report.status = results.length === 5 ? 'PASS_G5_HTTP_RECOVERY' : 'COMPLETED_WITH_FAILURES';
  report.summary = {
    passed: results.length, scenarios: results,
    note: 'Real HTTP service + real SQLite; the receipt-drop injection happens after the server transaction commits (DB rows read at the injection moment) and before the client consumes the receipt. No model calls; frozen v5/v6 evidence untouched. Lease tokens and requestIds are ephemeral local identifiers, not credentials — nothing to redact.',
  };
  save();
  console.log(`[g5-http] ${report.status} → ${output}`);
} catch (error) {
  report.status = 'FAILED';
  report.error = String(error?.stack ?? error);
  save();
  console.error('[g5-http] FAILED:', error);
  process.exitCode = 1; // 自动化判据：失败必须以非零退出码呈现，不能只看报告
} finally {
  cleanup();
  await new Promise((done) => { if (service.exitCode !== null) return done(); const t = setTimeout(done, 5000); service.once('exit', () => { clearTimeout(t); done(); }); });
  try { service.kill('SIGKILL'); } catch {}
  // Archive a readable copy of the DB + server log next to the report.
  const archiveDir = resolve(output, '..');
  for (const suffix of ['', '-wal', '-shm']) {
    const source = resolve(privateDir, `world.db${suffix}`);
    if (existsSync(source)) { mkdirSync(archiveDir, { recursive: true }); const { copyFileSync } = await import('node:fs'); copyFileSync(source, resolve(archiveDir, `world.db${suffix}`)); }
  }
  if (existsSync(resolve(privateDir, 'server.log'))) copyFileSyncSafe(resolve(privateDir, 'server.log'), resolve(archiveDir, 'server.log'));
  console.log(`[g5-http] db+log archived in ${resolve(output, '..')}`);
}
function copyFileSyncSafe(from, to) { mkdirSync(resolve(to, '..'), { recursive: true }); require('node:fs').copyFileSync(from, to); }
