// H2 history subcheck over the real HTTP transport + controller. The caller
// supplies an isolated A service. This does NOT claim takeover/restore passed.
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { createServer } from 'vite';

const [apiUrl, reportPath, serverCheckout] = process.argv.slice(2);
if (!apiUrl) throw new Error('Usage: node scripts/review-world-h2-history.mjs API_URL [REPORT_PATH] [A_CHECKOUT]');
const root = fileURLToPath(new URL('../', import.meta.url));
const workspace = resolve(root, '..');
function sourceIdentity(checkout, files) {
  const git = (...args) => execFileSync('git', ['-c', `safe.directory=${workspace.replaceAll('\\', '/')}`, '-c', `safe.directory=${checkout.replaceAll('\\', '/')}`, '-C', checkout, ...args], { encoding: 'utf8' }).trim();
  return { head: git('rev-parse', 'HEAD'), status: git('status', '--short'), sourceSha256: Object.fromEntries(files.map((file) =>
    [file, createHash('sha256').update(readFileSync(resolve(checkout, file))).digest('hex')])) };
}
const vite = await createServer({ root, configFile: false, server: { middlewareMode: true }, cacheDir: '../.local/h2-history-vite' });
try {
  const { HttpWorldTransport } = await vite.ssrLoadModule('/src/lib/world-engine/http-transport.ts');
  const { ControllerDriver, initialMemory } = await vite.ssrLoadModule('/src/lib/world-engine/controller.ts');
  const initial = JSON.parse(readFileSync(new URL('../../design/world-protocol/v1/fixtures/school.initial.json', import.meta.url), 'utf8'));
  delete initial.worldId;
  const http = new HttpWorldTransport(apiUrl);
  const namespace = `h2_${Date.now().toString(36)}`;
  let sequence = 0;
  let served;
  let lease;
  const next = () => `${namespace}_${++sequence}`;
  const execute = async (op, payload) => {
    const result = await http.execute(op, payload, served ? { worldId: served.world.worldId } : {});
    served = { ...served, ...result };
    return result;
  };
  const created = await execute('create_world', { protocolVersion: 2, requestId: next(), initial });
  lease = created.data.lease;
  const base = () => ({ protocolVersion: 2, requestId: next(), worldId: served.world.worldId, leaseToken: lease.leaseToken, fenceEpoch: lease.fenceEpoch });
  const checkpoint = () => ({ ...base(), expectedPointId: served.world.head.pointId, expectedVersion: served.world.head.version, expectedCheckpointRevision: served.control.revision });
  const narrate = async () => {
    const pointId = served.world.head.pointId;
    const claim = await execute('narration_claim', { ...base(), mode: 'head', pointId });
    await execute('narration_submit', { ...base(), mode: 'head', pointId, claimToken: claim.data.claimToken, generation: claim.data.generation,
      issuedAtEpochMilli: claim.data.issuedAtEpochMilli, outcome: 'ready', text: '固定验收叙事。', failureReason: null });
  };
  await narrate();
  const roster = Object.keys(initial.characters).sort();
  const actors = roster;
  const slots = ['advance', 'input', 'round', ...actors.map((_, i) => `point_${i + 1}`),
    ...actors.map((_, i) => `group_${i + 1}`), ...actors.map((_, i) => `change_${i + 1}`)];
  const allocation = await execute('allocate_ids', { ...base(), allocationKey: `${namespace}_ids`, slots: slots.map((slotKey) => ({ slotKey, kind: slotKey.split('_')[0] })) });
  const ids = Object.fromEntries(allocation.data.allocations.map((a) => [a.slotKey, a.id]));
  // A player round freezes the complete roster (control.py refuses anything else).
  await execute('checkpoint_start_advance', { ...checkpoint(), operation: 'start_advance', advanceId: ids.advance, inputId: ids.input,
    roundId: ids.round, inputText: '进行六点固定验收。', order: actors });
  const expectedChanges = [];
  for (let index = 1; index <= actors.length; index++) {
    const actor = actors[index - 1];
    const pointId = ids[`point_${index}`];
    const groupId = ids[`group_${index}`];
    // A round's first point is normal/elapsed; later points in the same round are instant.
    const timeAdvance = index === 1
      ? { boundary: 'elapsed', duration: { amount: 1, unit: 'second' } }
      : { boundary: 'instant', duration: { amount: 0, unit: 'second' } };
    const change = { id: ids[`change_${index}`], text: `第 ${index} 点的原始变化。`, supersedes: [] };
    await execute('checkpoint_begin_point', { ...checkpoint(), operation: 'begin_point', pointId, kind: index === 1 ? 'normal' : 'instant', timeAdvance });
    await execute('checkpoint_discover_group', { ...checkpoint(), operation: 'discover_group', pointId, groupId, initiatorId: actor, actionText: `${actor} 的固定行动。`, targetIds: null });
    await execute('checkpoint_extend_group', { ...checkpoint(), operation: 'extend_group', pointId, groupId, sourceId: actor, targets: [], admittedMember: null });
    await execute('checkpoint_close_group', { ...checkpoint(), operation: 'close_group', pointId, groupId });
    const candidates = { groupId, actorIds: [actor], positions: {}, appearances: { [actor]: [change] }, tasksAchieved: {}, subtasksAdded: {}, personalities: {}, sanities: {}, taskCoverageIds: roster, personalityCoverageIds: [] };
    await execute('checkpoint_stage_unit', { ...checkpoint(), operation: 'stage_unit', pointId, groupId, candidates, results: { [actor]: '固定结果。' } });
    await execute('checkpoint_seal_point', { ...checkpoint(), operation: 'seal_point', pointId });
    const preview = await execute('preview_point', { protocolVersion: 2, worldId: served.world.worldId, advanceId: ids.advance, roundId: ids.round,
      pointId, expectedPointId: served.world.head.pointId, expectedVersion: served.world.head.version, expectedCheckpointRevision: served.control.revision,
      timeAdvance, settlementGroups: [candidates] });
    await execute('commit_point', { ...checkpoint(), advanceId: ids.advance, roundId: ids.round, pointId, point: preview.data.pointProjection, settlementGroups: [candidates] });
    await narrate();
    // Authored independently from preview, saved reads or recovery helpers.
    expectedChanges.push({ pointId, timeAdvance, entityDeltas: { [actor]: { entityId: actor, appearanceChanges: [change] } } });
  }
  assert.equal(served.control.phase, 'assess_continuation');
  const recoveryOps = [];
  const modelCalls = [];
  const transport = { async execute(operation, request, scope) {
    recoveryOps.push(operation);
    return http.execute(operation, request, scope);
  } };
  const model = { async generate(task, key, input) {
    modelCalls.push({ task, key, input: structuredClone(input) });
    assert.equal(task, 'continuation');
    assert.deepEqual(input.roundChanges, expectedChanges);
    return { kind: 'handback', closedBy: 'model', cancelReason: null };
  } };
  const driver = new ControllerDriver({ transport, model }, initialMemory(`${namespace}_fresh`, 'history_check'));
  assert.equal(await driver.recover(served.world.worldId, { leaseToken: lease.leaseToken, fenceEpoch: lease.fenceEpoch }), undefined);
  assert.equal(await driver.step(), undefined);
  assert.equal(modelCalls.length, 1);
  assert.equal(recoveryOps.filter((op) => op === 'get_state').length, actors.length);
  assert.equal(recoveryOps.includes('round_conclusion_conclude'), false);
  const report = { status: 'PASS_HISTORY_SUBCHECK', recordedAt: new Date().toISOString(), scope: 'real HTTP + A state service + fresh B controller; not full H2 takeover acceptance',
    command: 'node scripts/review-world-h2-history.mjs API_URL [REPORT_PATH] [A_CHECKOUT]',
    browser: sourceIdentity(workspace, ['frontend/src/lib/world-engine/recovery.ts', 'frontend/src/lib/world-engine/controller.ts',
      'frontend/src/lib/world-engine/schedule.ts', 'frontend/src/lib/world-engine/runtime/session.ts', 'frontend/scripts/review-world-h2-history.mjs']),
    server: serverCheckout ? sourceIdentity(resolve(serverCheckout), ['backend/app/services/world/control.py', 'backend/app/world_app.py']) : null,
    worldId: served.world.worldId, roundId: ids.round, committedPointIds: expectedChanges.map((p) => p.pointId),
    rawDeltasMatchIndependentExpectation: true, modelCalls: modelCalls.map((c) => c.task), recoveryOps,
    contractDigest: JSON.parse(readFileSync(new URL('../src/lib/world-engine/contract-digest.json', import.meta.url), 'utf8')) };
  if (reportPath) writeFileSync(reportPath, JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify(report, null, 2));
} finally {
  await vite.close();
}
