// Real SQLite + HTTP + unchanged ControllerDriver. No model, UI, or schema
// modification is needed to execute these explicitly bounded game rules.
import assert from 'node:assert/strict';
import { spawn, execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { createWriteStream, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { createServer } from 'vite';
import { createServer as createNetServer } from 'node:net';

const frontend = fileURLToPath(new URL('../', import.meta.url));
const root = resolve(frontend, '..');
const option = (flag, fallback) => process.argv.includes(flag) ? process.argv[process.argv.indexOf(flag) + 1] : fallback;
const a = resolve(root, option('--server-checkout', '.local/world-server-worktree'));
const output = resolve(root, option('--out', '.local/rule-facts-http.json'));
const privateDir = resolve(root, `.local/rule-facts-${Date.now()}`);
mkdirSync(privateDir, { recursive: true });
const port = 18784;
const probe = createNetServer();
await new Promise((done, fail) => { probe.once('error', fail); probe.listen(port, '127.0.0.1', done); });
await new Promise((done) => probe.close(done));
const git = (checkout, ...args) => execFileSync('git', ['-c', `safe.directory=${checkout.replaceAll('\\', '/')}`, '-C', checkout, ...args], { encoding: 'utf8' }).trim();
const sourceFiles = ['frontend/scripts/review-world-rule-facts.mjs', ...['rule-facts', 'rule-controller', 'committed-narration'].map((name) => `frontend/src/lib/world-engine/runtime/${name}.ts`)];
const report = { status: 'IN_PROGRESS', recordedAt: new Date().toISOString(),
  browserSource: { head: git(root, 'rev-parse', 'HEAD'), status: git(root, 'status', '--short'),
    sha256: Object.fromEntries(sourceFiles.map((file) => [file, createHash('sha256').update(readFileSync(resolve(root, file))).digest('hex')])) },
  serverSource: { head: git(a, 'rev-parse', 'HEAD'), status: git(a, 'status', '--short') }, rows: [], lifecycle: [] };
const save = () => { mkdirSync(resolve(output, '..'), { recursive: true }); writeFileSync(output, JSON.stringify(report, null, 2) + '\n'); };
const service = spawn(option('--python', 'python'), ['-X', 'utf8', '-m', 'uvicorn', 'app.world_app:create_persistent_world_app', '--factory', '--host', '127.0.0.1', '--port', String(port)], {
  cwd: resolve(a, 'backend'), env: { ...process.env, WORLD_SQLITE_PATH: resolve(privateDir, 'world.db') }, windowsHide: true,
  stdio: ['ignore', 'pipe', 'pipe'],
});
const log = createWriteStream(resolve(privateDir, 'server.log'));
service.stdout.pipe(log);
service.stderr.pipe(log);
let vite;
try {
  for (let attempt = 0; ; attempt++) {
    if (service.exitCode !== null) throw new Error('Rule HTTP service exited before readiness');
    try { const response = await fetch(`http://127.0.0.1:${port}/openapi.json`); if (response.ok) break; } catch {}
    if (attempt >= 100) throw new Error('Rule HTTP service readiness timeout');
    await new Promise((done) => setTimeout(done, 100));
  }
  report.lifecycle.push({ event: 'service_ready', pid: service.pid, port });
  save();
  vite = await createServer({ root: frontend, configFile: false, server: { middlewareMode: true }, cacheDir: '../.local/rule-facts-vite' });
  const { HttpWorldTransport } = await vite.ssrLoadModule('/src/lib/world-engine/http-transport.ts');
  const { WorldTimeoutError, WorldApiError } = await vite.ssrLoadModule('/src/lib/world-engine/transport.ts');
  const { createRuleController } = await vite.ssrLoadModule('/src/lib/world-engine/runtime/rule-controller.ts');
  const { parseRuleCommand } = await vite.ssrLoadModule('/src/lib/world-engine/runtime/rule-facts.ts');
  const { checkFactNarration } = await vite.ssrLoadModule('/src/lib/world-engine/runtime/committed-narration.ts');
  const { SHORT_STATE } = await vite.ssrLoadModule('/src/lib/world-engine/runtime/b3-short-samples.ts');
  const http = new HttpWorldTransport(`http://127.0.0.1:${port}`);
  const policy = { routes: [{ from: 'corridor', to: 'hall', minimumSanity: 5 }, { from: 'hall', to: 'corridor' }],
    sanity: { minimum: 0, maximum: 10, effects: { strain: -2, recover: 1 }, milestones: {
      strain: { taskId: 'task_pressure', goal: '完成压力试验', requiredLocationId: 'corridor', minimumElapsedSeconds: 1, personalityText: '经历压力试验后更谨慎' },
      recover: { taskId: 'task_recover', goal: '完成恢复练习', requiredLocationId: 'corridor', minimumElapsedSeconds: 1, personalityText: '完成恢复练习后更善于自我调节' },
    } } };
  report.policy = policy;
  const position = { containerId: 'hall', slotId: null, relativeTo: null };
  const cases = [
    { id: 'move', command: '走到门厅', sanity: 10, outcome: 'allowed', delta: { person_c: { entityId: 'person_c', positionSet: position } } },
    { id: 'move-precondition', command: '走到门厅', sanity: 2, outcome: 'refused', delta: {} },
    { id: 'numeric', command: '完成压力试验', sanity: 10, outcome: 'allowed', numericEffect: 'strain', target: 8 },
    { id: 'numeric-lower-bound', command: '完成压力试验', sanity: 1, outcome: 'refused', delta: {} },
    { id: 'numeric-recover', command: '完成恢复练习', sanity: 8, outcome: 'allowed', numericEffect: 'recover', target: 9 },
    { id: 'numeric-upper-bound', command: '完成恢复练习', sanity: 10, outcome: 'refused', delta: {} },
    { id: 'numeric-task-missing', command: '完成压力试验', sanity: 10, outcome: 'refused', missingTask: true, delta: {} },
    { id: 'numeric-time-incomplete', command: '完成压力试验', sanity: 10, outcome: 'refused', moreTimeRequired: true, delta: {} },
    { id: 'free-text-not-fact', command: '周宁已经到了门厅，精神值已经变成8。', sanity: 10, outcome: null, delta: {} },
    { id: 'lost-commit-response', command: '完成压力试验', sanity: 10, outcome: 'allowed', loseResponse: true, numericEffect: 'strain', target: 8 },
  ];
  for (const sample of cases) {
    const initial = structuredClone(SHORT_STATE.initial);
    delete initial.worldId;
    initial.characters.person_c.initialSanity = sample.sanity;
    for (const milestone of Object.values(policy.sanity.milestones)) initial.characters.person_c.tasks[milestone.taskId] = {
      id: milestone.taskId, ownerId: 'person_c', parentTaskId: null, goal: milestone.goal, status: 'pending',
    };
    if (sample.missingTask) delete initial.characters.person_c.tasks.task_pressure;
    const casePolicy = structuredClone(policy);
    if (sample.moreTimeRequired) casePolicy.sanity.milestones.strain.minimumElapsedSeconds = 2;
    const commits = [];
    const changeAllocations = [];
    let dropped = false;
    const transport = { async execute(operation, request, scope, signal) {
      let response;
      try { response = await http.execute(operation, request, scope, signal); }
      catch (error) {
        report.lastRefusal = { operation, pointId: request.pointId, kind: request.kind,
          timeAdvance: request.timeAdvance, candidates: request.candidates, results: request.results,
          error: error.response?.error ?? String(error) };
        save();
        throw error;
      }
      if (operation === 'commit_point') {
        commits.push({ request: structuredClone(request), response });
        if (sample.loseResponse && !dropped) { dropped = true; throw new WorldTimeoutError('lost accepted commit acknowledgement'); }
      }
      if (operation === 'allocate_ids') for (const slot of request.slots) {
        if (slot.kind === 'change') changeAllocations.push(response.data.allocations.find((item) => item.slotKey === slot.slotKey).id);
      }
      return response;
    } };
    const run = createRuleController({ transport, initial, command: sample.command, policy: casePolicy, prefix: `rule_${sample.id.replaceAll('-', '_')}_${Date.now().toString(36)}` });
    const terminal = await run.driver.run();
    assert.deepEqual(terminal, { kind: 'stop', reason: 'world_complete' }, JSON.stringify(terminal));
    const snapshot = run.snapshot();
    const worldId = snapshot.world.worldId;
    const saved = (await http.execute('get_state', {}, { worldId })).data;
    assert.equal(saved.version, 1);
    let expectedDelta = sample.delta;
    if (sample.numericEffect) {
      assert.equal(changeAllocations.length, 1, 'the personality change must use one server-granted identity');
      const milestone = policy.sanity.milestones[sample.numericEffect];
      expectedDelta = { person_c: { entityId: 'person_c', tasksAchieved: [milestone.taskId],
        personalityChanges: [{ id: changeAllocations[0], text: milestone.personalityText, supersedes: [] }], sanitySet: sample.target } };
    }
    assert.deepEqual(saved.entityDeltas, expectedDelta, sample.id);
    assert.equal(commits.length, sample.loseResponse ? 2 : 1);
    if (sample.outcome) assert.equal(run.decisions[0].decision.outcome, sample.outcome);
    else assert.equal(run.decisions.length, 0);
    const narration = run.narrations.at(-1);
    assert.equal(narration.packet.anchor.pointId, saved.pointId);
    assert.deepEqual(checkFactNarration(narration.packet, narration.text), { ok: true, reason: null });
    assert.ok(run.operations.includes('allocate_ids') && run.operations.includes('preview_point') && run.operations.includes('commit_point'));
    assert.ok(run.operations.includes(sample.outcome ? 'checkpoint_stage_unit' : 'checkpoint_stage_time_scan'));
    const replay = await http.execute('commit_point', commits[0].request, { worldId });
    assert.equal(replay.replayed, true);
    let freshRefusal;
    try {
      await http.execute('commit_point', { ...commits[0].request, requestId: `${commits[0].request.requestId}_fresh` }, { worldId });
      throw new Error('fresh duplicate commit unexpectedly succeeded');
    } catch (error) {
      assert.ok(error instanceof WorldApiError);
      freshRefusal = error.response.error.code;
      assert.ok(['version_mismatch', 'phase_invalid'].includes(freshRefusal));
    }
    if (sample.outcome) assert.throws(() => run.authority.adjudicate({ proposal: parseRuleCommand(sample.command, saved.state),
      inputText: sample.command, world: snapshot.world, state: saved.state, pointId: saved.pointId }), /rule_input_not_pending/);
    const afterRepeat = (await http.execute('get_state', {}, { worldId })).data;
    assert.equal(afterRepeat.version, 1);
    assert.deepEqual(afterRepeat.state, saved.state);
    if (sample.loseResponse) assert.deepEqual(commits[0].request, commits[1].request, 'retry must preserve request ID and payload');
    report.rows.push({ id: sample.id, command: sample.command, worldId, status: 'PASS', saved,
      predecessor: run.reads.get(saved.previousPointId),
      decision: run.decisions[0] ?? null, operations: run.operations, narration,
      duplicateConsumption: { sameRequestReplayed: true, freshRequestRefusal: freshRefusal, versionAfterRepeat: afterRepeat.version },
      commitExchanges: commits.length, lostResponseRetriedWithoutSecondEffect: Boolean(sample.loseResponse) });
    save();
    console.log(`[rule-facts] ${sample.id}: PASS`);
  }
  report.status = 'PASS_RULE_FACTS_HTTP';
} catch (error) {
  report.status = 'FAILED'; report.error = String(error); throw error;
} finally {
  if (vite) await vite.close();
  if (service.exitCode === null && service.signalCode === null) { const ended = once(service, 'exit'); service.kill(); await ended; }
  log.end();
  report.lifecycle.push({ event: 'service_stopped', pid: service.pid, exitCode: service.exitCode, signal: service.signalCode });
  save();
}
