// Full H2 acceptance over the real HTTP transport and the REAL recovery
// controller (ControllerDriver.recover). The caller supplies an isolated A
// SQLite service (WORLD_SQLITE_PATH-backed persistent store). Phases are
// separate invocations so the orchestrator can restart the service or inject
// frozen-work damage between them; each phase writes its own report file.
//
//   main              worlds A+D: multi-source group rebuilt from the saved
//                     DFS checkpoint and driven through commit + narration +
//                     continuation; fencing (old claim submit/renew refused,
//                     new claim succeeds, stale-epoch late write refused);
//                     cross-epoch takeover recovery that commits a sealed
//                     uncommitted point left by the dead holder.
//   successor         world B: sealed current point + reserved successor with
//                     in-progress work; both baselines restored, then both
//                     points committed with no duplicate consumption.
//   build-frozen-case world C: mid-group state with a saved roll; writes the
//                     state file used by post-restart / expect-frozen.
//   post-restart      world C after a SERVICE RESTART: the persisted lease
//                     still refreshes and recovery reads the same facts.
//   expect-frozen     world C after the orchestrator damaged a row:
//                     recovery must STOP with frozen_work_corrupt/_missing.
//
// d20 note: the live rule rolls real dice, so branches (admitted or not,
// reuse or not) are decided by the server outcome. The script reads the
// realized group state, branches on it, and records the realized branch in
// the report; assertions are shaped by outcome, never by fixed values.
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { createServer } from 'vite';

const positional = process.argv.slice(2).filter((arg, index, all) => !arg.startsWith('--') && all[index - 1] !== '--state');
const [apiUrl, phase, reportPath, serverCheckout] = positional;
const argValue = (flag) => {
  const index = process.argv.indexOf(flag);
  return index >= 0 ? process.argv[index + 1] : undefined;
};
const statePath = argValue('--state');
const frozenKind = argValue('--kind');
if (!apiUrl || !phase || (phase === 'expect-frozen' && !frozenKind)) {
  throw new Error('Usage: node scripts/review-world-h2-full.mjs API_URL PHASE [REPORT_PATH] [A_CHECKOUT] [--state PATH] [--kind corrupt|missing]');
}
const root = fileURLToPath(new URL('../', import.meta.url));
const workspace = resolve(root, '..');

function sourceIdentity(checkout, files) {
  const git = (...args) => execFileSync('git', ['-c', `safe.directory=${workspace.replaceAll('\\', '/')}`, '-c', `safe.directory=${checkout.replaceAll('\\', '/')}`, '-C', checkout, ...args], { encoding: 'utf8' }).trim();
  return { head: git('rev-parse', 'HEAD'), status: git('status', '--short'), sourceSha256: Object.fromEntries(files.map((file) =>
    [file, createHash('sha256').update(readFileSync(resolve(checkout, file))).digest('hex')])) };
}
const browserIdentity = () => sourceIdentity(workspace, [
  'frontend/src/lib/world-engine/recovery.ts', 'frontend/src/lib/world-engine/controller.ts',
  'frontend/src/lib/world-engine/schedule.ts', 'frontend/scripts/review-world-h2-full.mjs']);
const serverIdentity = () => serverCheckout ? sourceIdentity(resolve(serverCheckout), [
  'backend/app/services/world/control.py', 'backend/app/services/world/authority.py', 'backend/app/database/world_frozen_repository.py']) : null;

const vite = await createServer({ root, configFile: false, server: { middlewareMode: true }, cacheDir: '../.local/h2-full-vite' });
try {
  const { HttpWorldTransport } = await vite.ssrLoadModule('/src/lib/world-engine/http-transport.ts');
  const { ControllerDriver, initialMemory } = await vite.ssrLoadModule('/src/lib/world-engine/controller.ts');
  // Capture the EXACT wire bytes of refused stage requests: the in-memory
  // request object can differ from the serialized body in no way, but the
  // capture removes all doubt when bisecting a server-side refusal.
  const wireCaptures = [];
  const capturingFetcher = async (input, init) => {
    const response = await fetch(input, init);
    if (response.status === 400 && String(init?.body ?? '').includes('"stage_unit"')) {
      wireCaptures.push({ url: String(input), body: String(init.body), status: response.status, response: await response.clone().text() });
    }
    return response;
  };
  const http = new HttpWorldTransport(apiUrl, capturingFetcher);
  const namespace = `h2full_${Date.now().toString(36)}`;
  let sequence = 0;
  const next = () => `${namespace}_${++sequence}`;

  // ---- scripted-API side: raw HTTP with explicit lease bindings ----
  let worldId = null;
  let lease = null;
  let head = null;
  let revision = null;
  const api = async (operation, payload) => {
    const result = await http.execute(operation, payload, worldId ? { worldId } : {});
    if (result.world) {
      worldId = result.world.worldId;
      head = result.world.head;
    }
    // The world view deliberately never echoes the lease token; grants ride
    // either data.lease (create_world) or FLAT data fields (lease_acquire).
    // Never overwrite the held credential with the tokenless world view.
    const flat = result.data?.leaseToken != null ? result.data : null;
    const granted = result.data?.lease ?? flat ?? result.world?.lease;
    if (granted?.leaseToken) lease = granted;
    if (result.control) revision = result.control.revision;
    return result;
  };
  const base = () => ({ protocolVersion: 2, requestId: next(), worldId, leaseToken: lease.leaseToken, fenceEpoch: lease.fenceEpoch });
  const ck = () => ({ ...base(), expectedPointId: head.pointId, expectedVersion: head.version, expectedCheckpointRevision: revision });
  const opLog = [];
  const diagnostics = { workShapes: [] };
  const call = async (operation, payload) => {
    opLog.push(operation);
    try {
      return await api(operation, payload);
    } catch (error) {
      if (error?.response) {
        opLog.push(`${operation}:REFUSED:${error.response.error.code}`);
        const refusal = new Error(`${operation} refused: ${error.response.error.code} ${JSON.stringify(error.response.error.details)}`);
        refusal.code = error.response.error.code;
        throw refusal;
      }
      throw error;
    }
  };
  const initial = JSON.parse(readFileSync(new URL('../../design/world-protocol/v1/fixtures/school.initial.json', import.meta.url), 'utf8'));
  delete initial.worldId;
  const roster = Object.keys(initial.characters).sort();
  const narrate = async () => {
    const pointId = head.pointId;
    const claim = (await call('narration_claim', { ...base(), mode: 'head', pointId })).data;
    await call('narration_submit', { ...base(), mode: 'head', pointId, claimToken: claim.claimToken, generation: claim.generation,
      issuedAtEpochMilli: claim.issuedAtEpochMilli, outcome: 'ready', text: `${namespace} 固定叙事。`, failureReason: null });
    return claim;
  };
  const allocate = async (slots) => {
    const allocation = await call('allocate_ids', { ...base(), allocationKey: `${namespace}_ids`, slots });
    return Object.fromEntries(allocation.data.allocations.map((a) => [a.slotKey, a.id]));
  };
  const createWorld = async () => {
    worldId = null; // a fresh world must not inherit the previous scope
    const created = await call('create_world', { protocolVersion: 2, requestId: next(), initial: structuredClone(initial) });
    await narrate();
    return created;
  };
  const beginPoint = (pointId, seconds) => call('checkpoint_begin_point', { ...ck(), operation: 'begin_point', pointId, kind: 'normal',
    timeAdvance: { boundary: 'elapsed', duration: { amount: seconds, unit: 'second' } } });
  const discover = (pointId, groupId, initiatorId, actionText) => call('checkpoint_discover_group', { ...ck(), operation: 'discover_group', pointId, groupId, initiatorId, actionText, targetIds: null });
  const extendTargets = (pointId, groupId, sourceId, targets) => call('checkpoint_extend_group', { ...ck(), operation: 'extend_group', pointId, groupId, sourceId, targets, admittedMember: null });
  const rollOne = (advanceId, roundId, groupId, sourceId, targetId, triggerKey) => call('create_rolls', { ...ck(),
    rolls: [{ advanceId, roundId, groupId, sourceId, targetId, triggerKey, ruleVersion: 'reaction-d20-v1', target: 11 }] });
  const acceptMember = (pointId, groupId, sourceId, memberId, actionText, roll) => call('checkpoint_extend_group', { ...ck(), operation: 'extend_group', pointId, groupId, sourceId,
    admittedMember: { memberId, actionText, rollRefs: [{ sourceId, targetId: memberId, triggerKey: roll.triggerKey, rollId: roll.rollId }] } });

  // ---- recovery-driver side: the REAL controller with a scripted model ----
  const modelLog = [];
  const scriptedModel = (answers) => ({
    async generate(task, key, input) {
      modelLog.push({ task, key, input: structuredClone(input) });
      const answer = answers[task] ?? (() => { throw new Error(`unexpected model task ${task} (${String(key)})`); })();
      return typeof answer === 'function' ? answer({ task, key, input }) : structuredClone(answer);
    },
  });
  const baseAnswers = () => ({
    continuation: { kind: 'handback', closedBy: 'model', cancelReason: null },
    narration: `${namespace} 恢复后叙事。`,
    time: { boundary: 'elapsed', duration: { amount: 2, unit: 'second' } },
    // #7 逐人判断：本轮点位未覆盖的槽位逐个判断，全部 skip。
    action: { kind: 'skip' },
  });
  const drive = async (driver, label, expectedStop) => {
    const status = await driver.run();
    if (expectedStop) assert.deepEqual(status, expectedStop, `[${label}] unexpected terminal status`);
    else assert.equal(status, undefined, `[${label}] driver did not complete: ${JSON.stringify(status)}`);
    return status;
  };
  const writeReport = (data) => {
    const report = { namespace, recordedAt: new Date().toISOString(), phase, browser: browserIdentity(), server: serverIdentity(),
      contractDigest: JSON.parse(readFileSync(new URL('../src/lib/world-engine/contract-digest.json', import.meta.url), 'utf8')), ...data };
    if (reportPath) writeFileSync(reportPath, JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify({ status: report.status, worldId: report.worldId, detail: report.detail ?? null }));
  };
  // Every phase runs inside this wrapper: a failed exploration still dumps
  // the op/model trail so the refusing request is identifiable.
  const runPhase = async (body) => {
    try {
      await body();
    } catch (error) {
      if (reportPath) writeFileSync(reportPath, JSON.stringify({ namespace, phase, status: 'FAILED', error: String(error),
        worldId, lastOps: opLog.slice(-25), modelCalls: modelLog.map((c) => ({ task: c.task, key: c.key })), diagnostics, wireCaptures }, null, 2) + '\n');
      throw error;
    }
  };

  // ================= main: multi-source recovery + fencing + takeover =================
  await runPhase(async () => {
  if (phase === 'main') {
    await createWorld();
    // d20 admission is random; the multi-source branch needs person_b
    // accepted pre-crash, so retry worlds until the first roll admits.
    const ids = {};
    let rollB = null;
    let bAccepted = false;
    let attempts = 0;
    for (attempts = 1; attempts <= 6 && !bAccepted; attempts++) {
      if (attempts > 1) await createWorld();
      const attemptIds = await allocate([
        { slotKey: 'advance', kind: 'advance' }, { slotKey: 'input', kind: 'input' }, { slotKey: 'round', kind: 'round' },
        { slotKey: 'point_1', kind: 'point' }, { slotKey: 'group_1', kind: 'group' },
        { slotKey: 'trigger:group_1:person_a:person_b', kind: 'trigger' }, { slotKey: 'trigger:group_1:person_a:person_c', kind: 'trigger' },
      ]);
      Object.assign(ids, attemptIds);
      await call('checkpoint_start_advance', { ...ck(), operation: 'start_advance', advanceId: ids.advance, inputId: ids.input,
        roundId: ids.round, inputText: '多源恢复验收输入。', order: roster });
      await beginPoint(ids.point_1, 1);
      await discover(ids.point_1, ids.group_1, 'person_a', 'person_a 推开重门，示意众人避开门边。');
      await extendTargets(ids.point_1, ids.group_1, 'person_a', [
        { targetId: 'person_b', triggerKey: ids['trigger:group_1:person_a:person_b'] },
        { targetId: 'person_c', triggerKey: ids['trigger:group_1:person_a:person_c'] }]);
      rollB = (await rollOne(ids.advance, ids.round, ids.group_1, 'person_a', 'person_b', ids['trigger:group_1:person_a:person_b'])).data.rolls[0];
      assert.equal(rollB.ruleVersion, 'reaction-d20-v1', 'new rolls must carry the live rule');
      if (rollB.admitted) {
        await acceptMember(ids.point_1, ids.group_1, 'person_a', 'person_b', 'person_b 稳住门轴。', { ...rollB, triggerKey: ids['trigger:group_1:person_a:person_b'] });
        bAccepted = true;
      }
    }
    assert.ok(bAccepted, 'no admitting roll in six attempts');
    const rollC = null; // a→c stays a saved pending_roll across recovery — its same-key re-roll is part of the walk.
    const pointId = ids.point_1;
    const groupId = ids.group_1;
    const preRecoveryOps = opLog.length;
    const answers = {
      ...baseAnswers(),
      targets: ({ input }) => (input.sourceId === 'person_b' ? { targets: [{ targetId: 'person_c' }] } : { targets: [] }),
      reaction: ({ input }) => `${input.memberId} 在门边的既定反应。`,
      // Results must cover exactly the settled members, which vary with the
      // d20 branches — derive them from the task input, never hardcode.
      results: ({ input }) => Object.fromEntries(input.members.map((m) => [m.memberId, `${m.memberId} 的既定结果。`])),
      updates: [{ stage: 'appearance', changes: { person_a: { appearanceChanges: [{ id: `${namespace}_change_1`, text: '重门被推开。', supersedes: [] }] } } }],
    };
    const driverRolls = [];
    const transport = { async execute(operation, request, scope) {
      opLog.push(operation);
      if (operation === 'create_rolls') driverRolls.push(structuredClone(request.rolls));
      if (operation === 'checkpoint_stage_unit') diagnostics.stageRequest = structuredClone(request);
      try {
        const response = await http.execute(operation, request, scope);
        if (response?.work) diagnostics.workShapes.push({ op: operation, keys: Object.keys(response.work),
          settledUnits: Array.isArray(response.work.settledUnits) ? response.work.settledUnits.length : typeof response.work.settledUnits,
          pendingGroup: response.work.pendingGroup === null ? 'null' : response.work.pendingGroup ? 'object' : 'absent' });
        return response;
      } catch (error) {
        if (error?.response) diagnostics.errors = [...(diagnostics.errors ?? []), { op: operation, error: error.response.error }];
        throw error;
      }
    } };
    const driver = new ControllerDriver({ transport, model: scriptedModel(answers) }, initialMemory(`${namespace}_fresh`, 'h2_recovery_a'));
    assert.equal(await driver.recover(worldId, { leaseToken: lease.leaseToken, fenceEpoch: lease.fenceEpoch }), undefined);
    const status = await driver.run();
    assert.ok(status === undefined || (status.kind === 'stop' && status.reason === 'world_complete'), `main walk did not complete: ${JSON.stringify(status)}`);
    const continuationCalls = modelLog.filter((c) => c.task === 'continuation');
    const resultsCalls = modelLog.filter((c) => c.task === 'results');
    const reactionCalls = modelLog.filter((c) => c.task === 'reaction');
    assert.equal(continuationCalls.length, 1, 'continuation must run exactly once');
    assert.equal(resultsCalls.length, 1, 'results must run exactly once for group_1');
    const resultsRolls = resultsCalls[0].input.members.flatMap((m) => m.rollRefs);
    const savedRollIds = [rollB].map((r) => r.rollId);
    for (const roll of [rollB]) {
      assert.ok(resultsRolls.some((r) => r.rollId === roll.rollId), `results input must carry saved roll ${roll.rollId}`);
    }
    const actionCalls = modelLog.filter((c) => c.task === 'action');
    // Recovered (accepted) members are never re-asked: person_a always (the
    // initiator), person_b whenever it was accepted pre-crash. Uncovered
    // slots — branch-dependent, person_c included whenever it never got
    // accepted — are still judged per person (#7), always as skips.
    const mustNeverBeAsked = ['person_a', ...(bAccepted ? ['person_b'] : [])];
    assert.ok(actionCalls.every((c) => !mustNeverBeAsked.includes(c.key)),
      `recovered members must never be re-asked for their action, got ${JSON.stringify(actionCalls.map((c) => c.key))}`);
    assert.ok(!modelLog.some((c) => c.task === 'pointPlan'), 'recovered round must not be re-planned');
    const allRollKeys = [[rollB].map((r) => [r.sourceId, r.targetId, r.triggerKey]), ...driverRolls.map((rolls) => rolls.map((r) => [r.sourceId, r.targetId, r.triggerKey]))].flat();
    assert.equal(new Set(allRollKeys.map((k) => k.join('|'))).size, allRollKeys.length, 'no threat key may ever be rolled twice');
    const reRolled = driverRolls.flat().find((r) => r.sourceId === 'person_a' && r.targetId === 'person_c');
    assert.ok(reRolled, 'the saved pending_roll threat (a→c) must be re-rolled after recovery');
    assert.equal(reRolled.triggerKey, ids['trigger:group_1:person_a:person_c'], 'the re-roll must reuse the SAVED trigger identity');
    assert.ok(driverRolls.flat().every((r) => r.ruleVersion === 'reaction-d20-v1'), 'post-recovery rolls must carry the live rule');
    assert.equal(opLog.filter((op) => op === 'commit_point').length, 1, 'exactly one commit (point_1)');
    const finalContext = await api('get_context', { includeRecovery: false, leaseToken: lease.leaseToken, fenceEpoch: lease.fenceEpoch });
    assert.equal(finalContext.world.head.narrationStatus, 'ready', 'head narration must be ready after the walk');

    // ---- fencing on a second world (sealed uncommitted point as the crash state) ----
    opLog.length = 0;
    await createWorld();
    const fenceIds = await allocate([
      { slotKey: 'advance', kind: 'advance' }, { slotKey: 'input', kind: 'input' }, { slotKey: 'round', kind: 'round' },
      { slotKey: 'point_1', kind: 'point' }, { slotKey: 'group_1', kind: 'group' },
    ]);
    await call('checkpoint_start_advance', { ...ck(), operation: 'start_advance', advanceId: fenceIds.advance, inputId: fenceIds.input,
      roundId: fenceIds.round, inputText: '围栏验收输入。', order: roster });
    await beginPoint(fenceIds.point_1, 3);
    await discover(fenceIds.point_1, fenceIds.group_1, 'person_a', 'person_a 独自检查大门。');
    await extendTargets(fenceIds.point_1, fenceIds.group_1, 'person_a', []);
    await call('checkpoint_close_group', { ...ck(), operation: 'close_group', pointId: fenceIds.point_1, groupId: fenceIds.group_1 });
    const candidates = { groupId: fenceIds.group_1, actorIds: ['person_a'], positions: {}, appearances: { person_a: [{ id: `${namespace}_fence_change`, text: '大门已检查。', supersedes: [] }] },
      tasksAchieved: {}, subtasksAdded: {}, personalities: {}, sanities: {}, taskCoverageIds: roster, personalityCoverageIds: [] };
    // Scripted API calls bypass the driver's identity funnel (§9.3): allocate
    // the candidate's change identity explicitly and rewrite before staging.
    const fenceChange = await allocate([{ slotKey: `change:${namespace}_fence`, kind: 'change' }]);
    candidates.appearances.person_a[0].id = fenceChange[`change:${namespace}_fence`];
    await call('checkpoint_stage_unit', { ...ck(), operation: 'stage_unit', pointId: fenceIds.point_1, groupId: fenceIds.group_1, candidates, results: { person_a: '大门结果。' } });
    // #7 逐人判断在封点前完成：未覆盖槽位逐个 record_skip（首次 skip 锁定
    // 时间），否则接管后的驱动要为未判断槽位规划新点。
    for (const actor of roster.filter((id) => id !== 'person_a')) {
      await call('checkpoint_record_skip', { ...ck(), operation: 'record_skip', pointId: fenceIds.point_1, slotActorId: actor });
    }
    await call('checkpoint_seal_point', { ...ck(), operation: 'seal_point', pointId: fenceIds.point_1 });
    const fenceWorld = worldId;
    const firstLease = { leaseToken: lease.leaseToken, fenceEpoch: lease.fenceEpoch };
    const oldClaim = (await call('narration_claim', { ...base(), mode: 'head', pointId: head.pointId })).data;
    const oldLease = { ...firstLease };
    const refused = async (operation, payload, code) => {
      opLog.push(operation);
      try {
        await api(operation, payload);
      } catch (error) {
        assert.equal(error?.response?.error?.code, code, `${operation} must refuse with ${code}`);
        opLog.push(`${operation}:REFUSED:${code}`);
        return error.response;
      }
      throw new Error(`${operation} should have been refused with ${code}`);
    };
    // Graceful handover: release, then the next holder takes a NEW epoch.
    // lease_release's body schema forbids worldId (path identity only).
    await call('lease_release', { protocolVersion: 2, requestId: next(), ...oldLease });
    const taken = (await call('lease_acquire', { protocolVersion: 2, requestId: next(), worldId, holderId: 'second' })).data;
    assert.equal(taken.fenceEpoch, oldLease.fenceEpoch + 1, 're-acquire must advance the epoch');
    // The stale claim is replayed under the NEW authority binding: the lease
    // level passes (the second holder's lease is live) so the refusal lands
    // at the claim level — the old claim's epoch no longer matches.
    await refused('narration_submit', { ...base(), mode: 'head', pointId: head.pointId,
      claimToken: oldClaim.claimToken, generation: oldClaim.generation, issuedAtEpochMilli: oldClaim.issuedAtEpochMilli,
      outcome: 'ready', text: '旧持有者的迟到叙事。', failureReason: null }, 'claim_fenced');
    await refused('narration_claim_renew', { ...base(), mode: 'head', pointId: head.pointId,
      claimToken: oldClaim.claimToken, generation: oldClaim.generation, issuedAtEpochMilli: oldClaim.issuedAtEpochMilli }, 'claim_fenced');
    // The dead holder's LATE WRITE uses its own old binding: refused at the
    // lease level with stale_epoch (the epoch has moved on).
    await refused('checkpoint_seal_point', { ...base(), leaseToken: oldLease.leaseToken, fenceEpoch: oldLease.fenceEpoch,
      expectedPointId: head.pointId, expectedVersion: head.version, expectedCheckpointRevision: revision,
      operation: 'seal_point', pointId: fenceIds.point_1 }, 'stale_epoch');
    const newClaim = (await call('narration_claim', { ...base(), mode: 'head', pointId: head.pointId })).data;
    assert.notEqual(newClaim.claimToken, oldClaim.claimToken, 'the new holder must receive a fresh claim');
    await call('narration_submit', { ...base(), mode: 'head', pointId: head.pointId, claimToken: newClaim.claimToken, generation: newClaim.generation,
      issuedAtEpochMilli: newClaim.issuedAtEpochMilli, outcome: 'ready', text: `${namespace} 新持有者叙事。`, failureReason: null });
    // Cross-epoch takeover recovery: a FRESH controller takes the abandoned
    // world and commits the sealed point the dead holder left. The second
    // holder releases first (a crash-expiry takeover would need the 120s
    // lease TTL); the release keeps the epoch retained, so the takeover's
    // acquire still advances it.
    await call('lease_release', { protocolVersion: 2, requestId: next(), leaseToken: lease.leaseToken, fenceEpoch: lease.fenceEpoch });
    const takeoverAnswers = { ...baseAnswers(),
      updates: [{ stage: 'appearance', changes: { person_a: { appearanceChanges: [{ id: `${namespace}_fence_change`, text: '大门已检查。', supersedes: [] }] } } }] };
    const takeoverOps = opLog.length;
    const takeoverDriver = new ControllerDriver({ transport: { async execute(operation, request, scope) { opLog.push(operation); return http.execute(operation, request, scope); } },
      model: scriptedModel(takeoverAnswers) }, initialMemory(`${namespace}_takeover`, 'h2_recovery_takeover'));
    assert.equal(await takeoverDriver.recover(fenceWorld), undefined);
    const takeoverStatus = await takeoverDriver.run();
    assert.ok(takeoverStatus === undefined || (takeoverStatus.kind === 'stop' && takeoverStatus.reason === 'world_complete'), `takeover walk failed: ${JSON.stringify(takeoverStatus)}`);
    const takeoverOpSlice = opLog.slice(takeoverOps);
    assert.equal(takeoverOpSlice.filter((op) => op === 'commit_point').length, 1, 'takeover must commit the sealed point exactly once');
    assert.ok(!takeoverOpSlice.includes('create_rolls'), 'takeover must not roll anything');
    writeReport({ status: 'PASS_MAIN', worldId, detail: { walkedWorld: worldId, fenceWorld, branch: { rollBadmitted: rollB.admitted, bAccepted, attempts },
      savedRollIds, modelTasks: modelLog.map((c) => c.task), fenceEpochs: { first: oldLease.fenceEpoch, second: taken.fenceEpoch },
      takeoverOps: takeoverOpSlice } });
  }

  // ================= successor: current + successor dual baseline =================
  if (phase === 'successor') {
    // Real reachable shape (A3 gate): a reserved successor cannot BEGIN
    // before its predecessor commits, so the crash state is a SEALED,
    // successor-reserving current point — and recovery must validate the
    // reservation, commit p1, then begin and drive p2 to completion.
    await createWorld();
    const ids = await allocate([
      { slotKey: 'advance', kind: 'advance' }, { slotKey: 'input', kind: 'input' }, { slotKey: 'round', kind: 'round' },
      { slotKey: 'point_1', kind: 'point' }, { slotKey: 'point_2', kind: 'point' },
      { slotKey: 'group_1', kind: 'group' }, { slotKey: 'trigger:group_1:person_a:person_b', kind: 'trigger' },
    ]);
    await call('checkpoint_start_advance', { ...ck(), operation: 'start_advance', advanceId: ids.advance, inputId: ids.input,
      roundId: ids.round, inputText: '后继点恢复验收输入。', order: roster });
    const p1Change = { id: `${namespace}_p1_change`, text: '第一点的既定变化。', supersedes: [] };
    await beginPoint(ids.point_1, 1);
    await discover(ids.point_1, ids.group_1, 'person_a', 'person_a 独自巡视门厅，示意 person_b 避开门边。');
    await extendTargets(ids.point_1, ids.group_1, 'person_a', [{ targetId: 'person_b', triggerKey: ids['trigger:group_1:person_a:person_b'] }]);
    const roll = (await rollOne(ids.advance, ids.round, ids.group_1, 'person_a', 'person_b', ids['trigger:group_1:person_a:person_b'])).data.rolls[0];
    assert.equal(roll.ruleVersion, 'reaction-d20-v1', 'successor rolls must carry the live rule');
    const accepted = new Set(['person_a']);
    if (roll.admitted) {
      await acceptMember(ids.point_1, ids.group_1, 'person_a', 'person_b', 'person_b 稳住门轴。', { ...roll, triggerKey: ids['trigger:group_1:person_a:person_b'] });
      accepted.add('person_b');
      // The stack moved to person_b: its frame must confirm empty targets
      // before the group can close.
      await extendTargets(ids.point_1, ids.group_1, 'person_b', []);
    }
    await call('checkpoint_close_group', { ...ck(), operation: 'close_group', pointId: ids.point_1, groupId: ids.group_1 });
    const p1Candidates = { groupId: ids.group_1, actorIds: [...accepted], positions: {}, appearances: { person_a: [p1Change] },
      tasksAchieved: {}, subtasksAdded: {}, personalities: {}, sanities: {}, taskCoverageIds: roster, personalityCoverageIds: [] };
    // Scripted API bypasses the driver's identity funnel: allocate explicitly.
    const p1ChangeIds = await allocate([{ slotKey: `change:${namespace}_p1`, kind: 'change' }]);
    p1Change.id = p1ChangeIds[`change:${namespace}_p1`];
    const results = Object.fromEntries([...accepted].map((m) => [m, `${m} 的第一点结果。`]));
    await call('checkpoint_stage_unit', { ...ck(), operation: 'stage_unit', pointId: ids.point_1, groupId: ids.group_1, candidates: p1Candidates, results });
    // #7：p1 未覆盖槽位在封点前逐个判断（接管/恢复后不得再补判）。
    for (const actor of roster.filter((id) => !accepted.has(id))) {
      await call('checkpoint_record_skip', { ...ck(), operation: 'record_skip', pointId: ids.point_1, slotActorId: actor });
    }
    await call('checkpoint_prepare_successor', { ...ck(), operation: 'prepare_successor', pointId: ids.point_1, successorPointId: ids.point_2,
      timeAdvance: { boundary: 'instant', duration: { amount: 0, unit: 'second' } } });
    const crashOps = opLog.length;
    const answers = {
      ...baseAnswers(),
      // The reserved p2 is an instant point with every slot judged: its scan
      // folds no changes at all.
      updates: [{ stage: 'appearance', changes: {} }],
    };
    const transport = { async execute(operation, request, scope) { opLog.push(operation); return http.execute(operation, request, scope); } };
    const driver = new ControllerDriver({ transport, model: scriptedModel(answers) }, initialMemory(`${namespace}_fresh`, 'h2_recovery_b'));
    assert.equal(await driver.recover(worldId, { leaseToken: lease.leaseToken, fenceEpoch: lease.fenceEpoch }), undefined);
    const status = await driver.run();
    assert.ok(status === undefined || (status.kind === 'stop' && status.reason === 'world_complete'), `successor walk failed: ${JSON.stringify(status)}`);
    const afterOps = opLog.slice(crashOps);
    assert.deepEqual(afterOps.filter((op) => op === 'commit_point').length, 2, 'both points must commit exactly once');
    assert.equal(afterOps.filter((op) => op === 'create_rolls').length, 0, 'the resolved roll must never be re-rolled');
    assert.equal(modelLog.filter((c) => c.task === 'results').length, 0, 'the staged unit must never be re-settled');
    assert.equal(modelLog.filter((c) => c.task === 'continuation').length, 1, 'continuation must run exactly once');
    const continuation = modelLog.find((c) => c.task === 'continuation');
    const expectedRoundChanges = [
      { pointId: ids.point_1, timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'second' } },
        entityDeltas: { person_a: { entityId: 'person_a', appearanceChanges: [p1Change] } } },
      { pointId: ids.point_2, timeAdvance: { boundary: 'instant', duration: { amount: 0, unit: 'second' } }, entityDeltas: {} },
    ];
    assert.deepEqual(continuation.input.roundChanges, expectedRoundChanges,
      'continuation must consume BOTH original raw deltas (p1 staged change + p2 empty), independently reconstructed');
    writeReport({ status: 'PASS_SUCCESSOR', worldId, detail: { branch: { rolladmitted: roll.admitted }, savedRollId: roll.rollId,
      commits: afterOps.filter((op) => op === 'commit_point').length, modelTasks: modelLog.map((c) => c.task) } });
  }

  // ================= frozen-case world: build / restart / damage =================
  if (phase === 'build-frozen-case') {
    // post-restart proves the SAVED DFS FRAME survives the restart, which only
    // exists while the accepted threat still owes work: an ADMITTED roll that
    // has not been extended pushes person_a back onto the sourceStack. A
    // rejected roll is handled immediately and leaves an empty stack, so this
    // fixture retries fresh worlds until one roll admits (max six, the same
    // bound as main) and records the realized branch. Without the retry the
    // post-restart assertion below failed on every rejected first roll
    // (2026-10-28, integration c4fbb97: "the saved DFS frame must survive the
    // restart").
    let ids = null;
    let roll = null;
    let attempts = 0;
    for (attempts = 1; attempts <= 6 && !roll?.admitted; attempts++) {
      if (attempts > 1) await createWorld();
      const attemptIds = await allocate([
        { slotKey: 'advance', kind: 'advance' }, { slotKey: 'input', kind: 'input' }, { slotKey: 'round', kind: 'round' },
        { slotKey: 'point_1', kind: 'point' }, { slotKey: 'group_1', kind: 'group' },
        { slotKey: 'trigger:group_1:person_a:person_b', kind: 'trigger' },
      ]);
      ids = attemptIds;
      await call('checkpoint_start_advance', { ...ck(), operation: 'start_advance', advanceId: ids.advance, inputId: ids.input,
        roundId: ids.round, inputText: '冻结事实验收输入。', order: roster });
      await beginPoint(ids.point_1, 2);
      await discover(ids.point_1, ids.group_1, 'person_a', 'person_a 推开重门，示意 person_b 避开门边。');
      await extendTargets(ids.point_1, ids.group_1, 'person_a', [{ targetId: 'person_b', triggerKey: ids['trigger:group_1:person_a:person_b'] }]);
      roll = (await rollOne(ids.advance, ids.round, ids.group_1, 'person_a', 'person_b', ids['trigger:group_1:person_a:person_b'])).data.rolls[0];
      assert.equal(roll.ruleVersion, 'reaction-d20-v1', 'frozen-case rolls must carry the live rule');
    }
    assert.ok(roll.admitted, 'no admitting roll in six frozen-case attempts');
    const state = { namespace, worldId, lease: { leaseToken: lease.leaseToken, fenceEpoch: lease.fenceEpoch },
      pointId: ids.point_1, groupId: ids.group_1, roundId: ids.round, rollId: roll.rollId,
      triggerKey: ids['trigger:group_1:person_a:person_b'], admitted: roll.admitted };
    if (!statePath) throw new Error('build-frozen-case requires --state PATH');
    writeFileSync(statePath, JSON.stringify(state, null, 2) + '\n');
    writeReport({ status: 'BUILT_FROZEN_CASE', worldId, detail: { ...state, attempts } });
  }
  if (phase === 'post-restart') {
    assert.ok(statePath, 'post-restart requires --state PATH');
    const state = JSON.parse(readFileSync(statePath, 'utf8'));
    worldId = state.worldId;
    lease = state.lease;
    const answers = { ...baseAnswers() };
    const driver = new ControllerDriver({ transport: { async execute(operation, request, scope) { opLog.push(operation); return http.execute(operation, request, scope); } },
      model: scriptedModel(answers) }, initialMemory(`${namespace}_restart`, 'h2_recovery_restart'));
    assert.equal(await driver.recover(worldId, { leaseToken: lease.leaseToken, fenceEpoch: lease.fenceEpoch }), undefined);
    const memory = driver.getMemory();
    const source = memory.sources[0];
    assert.ok(source, 'the saved DFS frame must survive the restart');
    assert.equal(source.sourceId, 'person_a', 'stack head must be the initiator');
    const saved = source.rolled.find((r) => r.rollId === state.rollId);
    assert.ok(saved, 'the saved roll identity must survive the restart');
    assert.equal(saved.admitted, state.admitted, 'saved admission must survive the restart');
    const groupAction = memory.groupActions[0];
    assert.ok(groupAction.rolls.some((r) => r.rollId === state.rollId), 'results dice facts must survive the restart');
    writeReport({ status: 'PASS_POST_RESTART', worldId, detail: { rollId: state.rollId, admitted: state.admitted, stack: ['person_a'] } });
  }
  if (phase === 'expect-frozen') {
    assert.ok(statePath && frozenKind, 'expect-frozen requires --state PATH and --kind corrupt|missing');
    const state = JSON.parse(readFileSync(statePath, 'utf8'));
    worldId = state.worldId;
    lease = state.lease;
    const answers = { ...baseAnswers() };
    const driver = new ControllerDriver({ transport: { async execute(operation, request, scope) { opLog.push(operation); return http.execute(operation, request, scope); } },
      model: scriptedModel(answers) }, initialMemory(`${namespace}_frozen`, 'h2_recovery_frozen'));
    const status = await driver.recover(worldId, { leaseToken: lease.leaseToken, fenceEpoch: lease.fenceEpoch });
    assert.deepEqual(status, { kind: 'stop', reason: `recovery_refused:get_context:frozen_work_${frozenKind}` },
      `damaged ${frozenKind} must stop recovery with the declared code`);
    writeReport({ status: `PASS_FROZEN_${frozenKind.toUpperCase()}`, worldId, detail: { stop: status } });
  }
  });
} finally {
  await vite.close();
}
