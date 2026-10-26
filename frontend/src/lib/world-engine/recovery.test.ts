import { describe, expect, test } from 'vitest';
import availableFixture from '../../../../design/world-protocol/v2/fixtures/branches/recovery.success.json';
import openFixture from '../../../../design/world-protocol/v2/fixtures/branches/recovery-unconfirmed.success.json';
import successorFixture from '../../../../design/world-protocol/v2/fixtures/branches/recovery-successor.success.json';
import stateFixture from '../../../../design/world-protocol/v2/fixtures/api/get_state/success.json';
import { ControllerDriver, initialMemory, type WorldModelPort } from './controller';
import { readControllerRecovery, recoverPoint } from './recovery';
import { WorldApiError, WorldTimeoutError, type WorldTransport } from './transport';
import { validateSuccess } from './protocol';
import type { ContextResponse, DataMap, Json, PointRecovery, RequestMap, Success, WorldContext, WorldOperation } from './types';
import type { ModelTask } from './schedule';
import { RuntimeWorldModelPort } from './runtime/model-port';
import { WorldSession } from './runtime/session';

type Summary = DataMap['list_points']['points'][number];
const copy = <T>(value: T): T => structuredClone(value);
const context = () => copy(availableFixture) as ContextResponse;
const openContext = () => copy(openFixture) as ContextResponse;
const timeAdvance = { boundary: 'elapsed' as const, duration: { amount: 2, unit: 'second' as const } };

/** Independent read records, with distinguishable raw deltas. No controller
 * assembler, state kernel or recovered memory is used to make expectations. */
function history(count = 3, startRound = 1) {
  const summaries: Summary[] = Array.from({ length: count + 1 }, (_, sequence) => ({ pointId: sequence ? `p${sequence}` : 'root_0', sequence,
    kind: sequence ? 'normal' : 'root', roundId: sequence >= startRound && sequence > 0 ? 'round_1' : sequence ? 'older_round' : null,
    advanceId: sequence ? sequence >= startRound ? 'advance_1' : 'older_advance' : null, stateDigest: `digest_${sequence}` }));
  const records = summaries.map((p) => ({ pointId: p.pointId, version: p.sequence, stateDigest: p.stateDigest,
    state: copy(stateFixture.data.state), previousPointId: p.sequence ? summaries[p.sequence - 1].pointId : null,
    timeAdvance: p.sequence ? copy(timeAdvance) : null,
    entityDeltas: p.sequence ? { person_c: { entityId: 'person_c', appearanceChanges: [{ id: `change_${p.sequence}`, text: `原始变化 ${p.sequence}`, supersedes: [] }] } } : {},
  })) as DataMap['get_state'][];
  return { summaries, records };
}

function continuationContext(h: ReturnType<typeof history>): ContextResponse {
  const c = context();
  const head = h.summaries.at(-1)!;
  c.world.head = { pointId: head.pointId, version: head.sequence, stateDigest: head.stateDigest, narrationStatus: 'ready' };
  c.world.advance.intentStatus = 'consumed';
  c.world.activePointId = null;
  c.world.activeRoundId = 'round_1';
  c.control.phase = 'assess_continuation';
  c.work = null;
  c.recovery = { fenceEpoch: 7, current: null, successor: null };
  return c;
}

class RecoveryTransport implements WorldTransport {
  readonly calls: { operation: WorldOperation; request: unknown }[] = [];
  reads = 0;
  restored = false;
  pageSize = 100;
  hidden: ContextResponse | null = null;
  mutate?: (operation: WorldOperation, response: unknown, request: unknown) => unknown;
  extra?: (operation: WorldOperation, request: unknown) => unknown;
  constructor(public c: ContextResponse, public h = history(0)) {
    if (c.world.head.version === 0) this.h.summaries[0].stateDigest = c.world.head.stateDigest;
    if (c.world.head.version === 0) this.h.records[0].stateDigest = c.world.head.stateDigest;
  }
  async execute<K extends WorldOperation>(operation: K, request: RequestMap[K]): Promise<Success<K>> {
    this.calls.push({ operation, request: copy(request) });
    const base = { protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1,
      canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, world: copy(this.c.world) };
    let response: unknown;
    switch (operation) {
      case 'lease_acquire': response = { ...base, control: copy(this.c.control), work: copy(this.c.work), data: { leaseToken: 'fresh_lease', fenceEpoch: 7, expiresAtEpochMilli: 999999999, holderId: 'new_holder' } }; break;
      case 'lease_renew': response = { ...base, data: { leaseToken: (request as RequestMap['lease_renew']).leaseToken, fenceEpoch: 7, expiresAtEpochMilli: 999999999 } }; break;
      case 'get_context': this.reads++; response = copy(this.restored || !this.hidden ? this.c : this.hidden); break;
      case 'list_points': {
        const after = (request as RequestMap['list_points']).after ?? -1;
        response = { ...base, data: { points: copy(this.h.summaries.filter((p) => p.sequence > after).slice(0, this.pageSize)) } };
        break;
      }
      case 'get_state': response = { ...base, data: copy(this.h.records.find((r) => r.pointId === (request as RequestMap['get_state']).point)) }; break;
      case 'checkpoint_restore_group_work': {
        this.restored = true;
        const r = request as RequestMap['checkpoint_restore_group_work'];
        response = { ...base, control: copy(this.c.control), work: copy(this.c.work), data: { pointId: r.pointId, groupId: r.groupId,
          fenceEpoch: 7, attempt: 2, sourceEpoch: r.sourceEpoch, sourceAttempt: r.sourceAttempt, restoredMemberIds: r.manifest.map((m) => m.memberId) } };
        break;
      }
      case 'allocate_ids': response = { ...base, control: copy(this.c.control), work: copy(this.c.work), data: { allocations: (request as RequestMap['allocate_ids']).slots.map((s, i) => ({ slotKey: s.slotKey, id: `new_group_${i}` })) } }; break;
      default:
        if (!this.extra) throw new Error(`Unexpected call ${operation}`);
        response = this.extra(operation, request);
    }
    return (this.mutate ? this.mutate(operation, response, request) : response) as Success<K>;
  }
}

function nextId() { let n = 0; return () => `bootstrap_${++n}`; }
const model = () => {
  const calls: { task: ModelTask; key: string; input: Json }[] = [];
  const port: WorldModelPort = { async generate(task, key, input): Promise<Json> {
    calls.push({ task, key, input: copy(input) });
    if (task === 'continuation') return { kind: 'handback', closedBy: 'model', cancelReason: null };
    if (task === 'targets') return { targets: [] };
    return {};
  } };
  return { calls, port };
};

describe('H2 round history reads', () => {
  test('continuation reads ALL committed points, including commits made before this new driver existed', async () => {
    const h = history(3);
    const transport = new RecoveryTransport(continuationContext(h), h);
    transport.pageSize = 2; // a short page must not be treated as EOF
    const m = model();
    const driver = new ControllerDriver({ transport, model: m.port }, initialMemory('new_session', 'new_holder'));
    expect(await driver.recover('world_school')).toBeUndefined();
    await driver.step();
    expect(m.calls).toHaveLength(1);
    expect(m.calls[0].task).toBe('continuation');
    expect(m.calls[0].input).toMatchObject({ roundChanges: [
      { pointId: 'p1', timeAdvance, entityDeltas: { person_c: { entityId: 'person_c', appearanceChanges: [{ id: 'change_1', text: '原始变化 1', supersedes: [] }] } } },
      { pointId: 'p2', timeAdvance, entityDeltas: { person_c: { entityId: 'person_c', appearanceChanges: [{ id: 'change_2', text: '原始变化 2', supersedes: [] }] } } },
      { pointId: 'p3', timeAdvance, entityDeltas: { person_c: { entityId: 'person_c', appearanceChanges: [{ id: 'change_3', text: '原始变化 3', supersedes: [] }] } } },
    ], workingState: stateFixture.data.state });
    expect(transport.calls.filter((c) => c.operation === 'list_points').map((c) => c.request)).toEqual([{ after: null, limit: 100 }, { after: 1, limit: 100 }]);
    expect(transport.calls.filter((c) => c.operation === 'get_state').map((c) => c.request)).toEqual([{ point: 'p1' }, { point: 'p2' }, { point: 'p3' }]);
    expect(transport.calls.some((c) => c.operation === 'round_conclusion_conclude')).toBe(false);
  });

  test('pages across 100 points, excludes earlier rounds, and preserves raw supersedes', async () => {
    const h = history(103, 98);
    h.records[102].entityDeltas.person_c.appearanceChanges![0].supersedes = ['change_98', 'change_100'];
    const transport = new RecoveryTransport(continuationContext(h), h);
    const recovered = await readControllerRecovery(transport, 'world_school', 'new_holder', nextId());
    expect(recovered.roundChanges?.points.map((p) => p.pointId)).toEqual(['p98', 'p99', 'p100', 'p101', 'p102', 'p103']);
    expect(recovered.roundChanges?.points[4].entityDeltas.person_c.appearanceChanges![0].supersedes).toEqual(['change_98', 'change_100']);
    expect(transport.calls.filter((c) => c.operation === 'list_points').map((c) => c.request)).toEqual([{ after: null, limit: 100 }, { after: 99, limit: 100 }]);
  });

  test('a verified round with no commits is an explicit empty list', async () => {
    const h = history(0);
    const recovered = await readControllerRecovery(new RecoveryTransport(continuationContext(h), h), 'world_school', 'new_holder', nextId());
    expect(recovered.roundChanges).toEqual({ roundId: 'round_1', points: [] });
  });

  test.each([
    ['missing page', (t: RecoveryTransport) => { t.h.summaries.splice(2); }, 'recovery_history_incomplete'],
    ['gap', (t: RecoveryTransport) => { t.h.summaries.splice(1, 1); }, 'recovery_history_gap'],
    ['duplicate', (t: RecoveryTransport) => { t.h.summaries[2].pointId = 'p1'; }, 'recovery_history_gap'],
    ['head digest', (t: RecoveryTransport) => { t.h.summaries[3].stateDigest = 'wrong'; }, 'recovery_history_head_mismatch'],
    ['missing delta', (t: RecoveryTransport) => { delete (t.h.records[1] as Partial<DataMap['get_state']>).entityDeltas; }, 'recovery_point_read_incomplete:p1'],
    ['wrong predecessor', (t: RecoveryTransport) => { t.h.records[2].previousPointId = 'root_0'; }, 'recovery_point_read_incomplete:p2'],
    ['wrong target point', (t: RecoveryTransport) => { t.h.records[1].pointId = 'other'; }, 'recovery_point_read_incomplete:p1'],
    ['wrong point digest', (t: RecoveryTransport) => { t.h.records[1].stateDigest = 'wrong'; }, 'recovery_point_read_incomplete:p1'],
    ['wrong advance', (t: RecoveryTransport) => { t.h.summaries[1].advanceId = 'old'; }, 'recovery_history_advance_mismatch'],
    ['missing round point', (t: RecoveryTransport) => { t.h.summaries[2].roundId = 'old'; }, 'recovery_history_round_mismatch'],
    ['context changed at final read', (t: RecoveryTransport) => { t.mutate = (op, response) => { if (op === 'get_context' && t.reads === 2) (response as ContextResponse).control.revision++; return response; }; }, 'recovery_snapshot_changed'],
    ['head moves during reads', (t: RecoveryTransport) => { t.mutate = (op, response) => { if (op === 'get_state') (response as { world: WorldContext }).world.head.pointId = 'future'; return response; }; }, 'recovery_snapshot_changed'],
  ] as const)('%s stops before any model or conclusion, including repeated runs', async (_name, mutate, reason) => {
    const h = history(3);
    const t = new RecoveryTransport(continuationContext(h), h);
    mutate(t);
    const m = model();
    const driver = new ControllerDriver({ transport: t, model: m.port }, initialMemory('fresh', 'new_holder'));
    const result = await driver.recover('world_school');
    expect(result?.kind).toBe('stop');
    expect(result && 'reason' in result ? result.reason : '').toContain(reason);
    const count = t.calls.length;
    expect(await driver.run()).toEqual(result);
    expect(await driver.run()).toEqual(result);
    expect(t.calls).toHaveLength(count);
    expect(m.calls).toEqual([]);
    expect(t.calls.some((c) => c.operation === 'round_conclusion_conclude')).toBe(false);
  });
});

describe('H2 frozen work', () => {
  test('a reserved successor binds its FUTURE baseline, retains its instant time, and allocates remaining identities', async () => {
    const c = copy(successorFixture) as ContextResponse;
    validateSuccess('get_context', c);
    const t = new RecoveryTransport(c);
    const recovered = await readControllerRecovery(t, 'world_school', 'new_holder', nextId());
    expect(recovered.plan?.map((p) => [p.pointId, p.kind, p.timeAdvance])).toEqual([
      ['p1', 'normal', { boundary: 'elapsed', duration: { amount: 2, unit: 'second' } }],
      ['p2', 'instant', { boundary: 'instant', duration: { amount: 0, unit: 'second' } }],
    ]);
    expect(recovered.successor?.work.baseline.headPointId).toBe('p1');
    expect(recovered.ids).toEqual({ 'group:person_e': 'new_group_0', 'group:person_f': 'new_group_1' });
    expect(t.calls.some((c) => c.operation === 'checkpoint_begin_point')).toBe(false);
  });

  test('a successor cannot borrow the current head as its baseline', async () => {
    const c = copy(successorFixture) as ContextResponse;
    c.recovery!.successor!.work.baseline = copy(c.recovery!.current!.work.baseline);
    await expect(readControllerRecovery(new RecoveryTransport(c), 'world_school', 'new_holder', nextId())).rejects.toThrow('recovery_baseline_mismatch');
  });

  test('refresh validates retained authority with renew; never acquires over a live lease', async () => {
    const t = new RecoveryTransport(context());
    const result = await readControllerRecovery(t, 'world_school', 'new_holder', nextId(), 3, { leaseToken: 'retained_lease', fenceEpoch: 7 });
    expect(t.calls[0]).toEqual({ operation: 'lease_renew', request: { protocolVersion: 2, requestId: 'bootstrap_1', worldId: 'world_school', leaseToken: 'retained_lease', fenceEpoch: 7 } });
    expect(result.leaseToken).toBe('retained_lease');
    expect(t.calls.some((c) => c.operation === 'lease_acquire')).toBe(false);
  });

  test('available settled work copies original actions, results and candidates; visited members cannot be judged again', async () => {
    const c = context();
    validateSuccess('get_context', c);
    const t = new RecoveryTransport(c);
    const recovered = await readControllerRecovery(t, 'world_school', 'new_holder', nextId());
    expect(recovered.point?.staged[0]).toEqual({ groupId: 'group_cd', actorIds: ['person_c', 'person_d'], candidates: availableFixture.recovery.current.groups[0].candidates,
      results: { person_c: '重门打开。', person_d: 'D 退到一旁。' } });
    expect(recovered.point?.groupActors).toEqual(['person_c', 'person_d']);
    expect(t.calls.some((call) => call.operation === 'checkpoint_restore_group_work')).toBe(false);
  });

  test('takeover copies ONLY the manifest and then re-reads originals; never uploads replacement text', async () => {
    const c = context();
    const t = new RecoveryTransport(c);
    t.hidden = copy(c);
    t.hidden.recovery!.current!.payloadStatus = 'restore_required';
    t.hidden.recovery!.current!.groups = [];
    const recovered = await readControllerRecovery(t, 'world_school', 'new_holder', nextId());
    const restore = t.calls.find((c) => c.operation === 'checkpoint_restore_group_work')!;
    expect(restore.request).toEqual({ protocolVersion: 2, requestId: 'bootstrap_2', worldId: 'world_school', leaseToken: 'fresh_lease', fenceEpoch: 7,
      expectedPointId: 'root_0', expectedVersion: 0, expectedCheckpointRevision: 2, operation: 'restore_group_work', ...c.recovery!.current!.restoreSources[0] });
    expect(t.calls.slice(0, 4).map((c) => c.operation)).toEqual(['lease_acquire', 'get_context', 'checkpoint_restore_group_work', 'get_context']);
    expect(recovered.point?.staged[0].candidates).toEqual(c.recovery!.current!.groups[0].candidates);
  });

  test('an open saved action goes to target analysis with EXACT original text, never action generation', async () => {
    const c = openContext();
    validateSuccess('get_context', c);
    const t = new RecoveryTransport(c);
    t.extra = (op) => {
      expect(op).toBe('preview_point');
      return { world: c.world, control: c.control, work: c.work, data: { workingState: stateFixture.data.state, pointProjection: {} } };
    };
    const m = model();
    const driver = new ControllerDriver({ transport: t, model: m.port }, initialMemory('fresh', 'new_holder'));
    expect(await driver.recover('world_school')).toBeUndefined();
    expect(driver.getMemory().groupActions).toEqual([{ memberId: 'person_c', actionText: 'C 推开重门，示意 D 避开门边。', rolls: [] }]);
    await driver.step(); // preview
    await driver.step(); // targets
    expect(m.calls).toHaveLength(1);
    expect(m.calls[0]).toMatchObject({ task: 'targets', key: 'person_c', input: { actionText: 'C 推开重门，示意 D 避开门边。' } });
  });

  test('closed group with saved candidates stages exact originals with zero model calls', async () => {
    const c = context();
    const point = c.recovery!.current!;
    const unit = point.work.settledUnits[0];
    point.work.pendingGroup = { groupId: 'group_cd', sourceId: 'person_c', memberIds: ['person_c', 'person_d'], targetIds: ['person_d'], frontierIds: [], closed: true };
    point.work.settledUnits = [];
    point.work.working.settledUnitIds = [];
    point.work.phase = 'settle_group';
    c.work = copy(point.work);
    c.control.phase = 'settle_group';
    const t = new RecoveryTransport(c);
    t.extra = (op) => {
      expect(op).toBe('checkpoint_stage_unit');
      return { world: c.world, control: c.control, work: c.work, data: { unitId: unit.unitId } };
    };
    const m = model();
    const driver = new ControllerDriver({ transport: t, model: m.port }, initialMemory('fresh', 'new_holder'));
    expect(await driver.recover('world_school')).toBeUndefined();
    await driver.step();
    const request = t.calls.at(-1)!.request as RequestMap['checkpoint_stage_unit'];
    expect(request.candidates).toEqual(availableFixture.recovery.current.groups[0].candidates);
    expect(request.results).toEqual({ person_c: '重门打开。', person_d: 'D 退到一旁。' });
    expect(driver.getMemory().restoredUnit).toBeNull();
    expect(m.calls).toEqual([]);
  });

  test('a recovered sealed point previews the original candidates and commits once without regenerating anything', async () => {
    const c = context();
    c.recovery!.current!.work.sealed = true;
    c.recovery!.current!.work.prefixDigest = 'sealed_prefix';
    c.work = copy(c.recovery!.current!.work);
    const point = { worldId: 'world_school', id: 'p1', sequence: 1, kind: 'normal', previousPointId: 'root_0', roundId: 'round_1', advanceId: 'advance_1',
      trigger: 'player', linkedFromPointId: null, timeAdvance, entityDeltas: { person_d: { entityId: 'person_d', positionSet: { containerId: 'corridor', slotId: null, relativeTo: null } } } };
    const t = new RecoveryTransport(c);
    t.extra = (op, request) => {
      if (op === 'preview_point') {
        expect((request as RequestMap['preview_point']).settlementGroups).toEqual([availableFixture.recovery.current.groups[0].candidates]);
        return { world: c.world, control: c.control, work: c.work, data: { workingState: stateFixture.data.state, pointProjection: point } };
      }
      expect(op).toBe('commit_point');
      expect((request as RequestMap['commit_point']).point).toEqual(point);
      const world = copy(c.world);
      world.head = { pointId: 'p1', version: 1, stateDigest: 'committed', narrationStatus: 'ready' };
      world.activePointId = null;
      return { world, control: { ...c.control, paused: true, canCompute: false, blockedReasons: ['paused'] }, work: null, data: { pointId: 'p1', version: 1, stateDigest: 'committed' } };
    };
    const m = model();
    const driver = new ControllerDriver({ transport: t, model: m.port }, initialMemory('fresh', 'new_holder'));
    expect(await driver.recover('world_school')).toBeUndefined();
    await driver.step();
    await driver.step();
    expect(await driver.run()).toEqual({ kind: 'await', reason: 'paused_externally' });
    expect(t.calls.filter((c) => c.operation === 'commit_point')).toHaveLength(1);
    expect(driver.getMemory().roundChanges).toEqual({ roundId: 'round_1', points: [{ pointId: 'p1', timeAdvance, entityDeltas: point.entityDeltas }] });
    expect(driver.getMemory().groupActions).toEqual([]);
    expect(m.calls).toEqual([]);
  });

  test('sealed work without its saved candidate bytes stops instead of previewing an empty projection', async () => {
    const c = context();
    c.work!.sealed = true;
    const t = new RecoveryTransport(c);
    const m = model();
    const memory = initialMemory('fresh', 'new_holder');
    memory.leaseToken = 'held_lease';
    const driver = new ControllerDriver({ transport: t, model: m.port }, memory, { world: c.world, control: c.control, work: c.work });
    expect(await driver.run()).toEqual({ kind: 'stop', reason: 'sealed_work_missing' });
    expect(await driver.run()).toEqual({ kind: 'stop', reason: 'sealed_work_missing' });
    expect(t.calls).toEqual([]);
    expect(m.calls).toEqual([]);
  });

  test.each([
    ['missing action', (p: PointRecovery) => { p.groups[0].members[0].actionText = null; }, 'frozen_actions_missing:person_c'],
    ['missing candidates', (p: PointRecovery) => { p.groups[0].candidates = null; }, 'recovery_candidates_missing:group_cd'],
    ['missing group', (p: PointRecovery) => { p.groups = []; }, 'recovery_groups_incomplete'],
    ['missing result', (p: PointRecovery) => { p.groups[0].members[0].resultText = null; }, 'recovery_results_missing:person_c'],
    ['scan marker without bytes', (p: PointRecovery) => { p.work.timeScanComplete = true; }, 'recovery_time_scan_missing'],
  ] as const)('%s fails before any regenerated work', (_name, mutate, reason) => {
    const c = context();
    mutate(c.recovery!.current!);
    expect(() => recoverPoint(c.recovery!.current!, c.world)).toThrow(reason);
  });

  test('closed unsettled group without roll outcomes explicitly stops; never re-rolls to recover missing facts', async () => {
    const c = openContext();
    const p = c.recovery!.current!;
    p.work.pendingGroup!.closed = true;
    p.work.pendingGroup!.frontierIds = [];
    p.work.phase = 'settle_group';
    p.groups[0].members[0].targets = [{ targetId: 'person_d', triggerKey: 'trigger_cd' }];
    p.groups[0].members[0].rollRefs = [{ sourceId: 'person_c', targetId: 'person_d', triggerKey: 'trigger_cd', rollId: 'roll_cd' }];
    c.work = copy(p.work);
    const t = new RecoveryTransport(c);
    const m = model();
    const driver = new ControllerDriver({ transport: t, model: m.port }, initialMemory('fresh', 'new_holder'));
    expect(await driver.recover('world_school')).toEqual({ kind: 'stop', reason: 'recovery_roll_outcomes_missing' });
    expect(await driver.run()).toEqual({ kind: 'stop', reason: 'recovery_roll_outcomes_missing' });
    expect(m.calls).toEqual([]);
    expect(t.calls.map((c) => c.operation)).toEqual(['lease_acquire', 'get_context']);
  });

  test('restore timeout retries identical request and manifest, then reads original text', async () => {
    const c = context();
    const t = new RecoveryTransport(c);
    t.hidden = copy(c);
    t.hidden.recovery!.current!.payloadStatus = 'restore_required';
    t.hidden.recovery!.current!.groups = [];
    let timeout = true;
    t.mutate = (op, response) => { if (op === 'checkpoint_restore_group_work' && timeout) { timeout = false; throw new WorldTimeoutError(); } return response; };
    await readControllerRecovery(t, 'world_school', 'new_holder', nextId());
    const copies = t.calls.filter((c) => c.operation === 'checkpoint_restore_group_work');
    expect(copies).toHaveLength(2);
    expect(copies[0].request).toEqual(copies[1].request);
  });

  test('A refuses restore: hold a persistent stop, no models and no silent new lease', async () => {
    const c = context();
    const t = new RecoveryTransport(c);
    t.hidden = copy(c);
    t.hidden.recovery!.current!.payloadStatus = 'restore_required';
    t.hidden.recovery!.current!.groups = [];
    t.mutate = (op, response) => { if (op === 'checkpoint_restore_group_work') throw new WorldApiError({ error: { code: 'frozen_work_missing' } } as never); return response; };
    const m = model();
    const driver = new ControllerDriver({ transport: t, model: m.port }, initialMemory('fresh', 'new_holder'));
    const stopped = { kind: 'stop', reason: 'recovery_refused:checkpoint_restore_group_work:frozen_work_missing' };
    expect(await driver.recover('world_school')).toEqual(stopped);
    expect(await driver.run()).toEqual(stopped);
    expect(m.calls).toEqual([]);
    expect(t.calls.filter((c) => c.operation === 'lease_acquire')).toHaveLength(1);
  });
});

describe('H2 session bootstrap', () => {
  test.each([false, true])('new session bootstraps once and starts its lease heartbeat (refresh=%s)', async (refresh) => {
    const c = context();
    c.control.paused = true;
    c.control.canCompute = false;
    c.control.blockedReasons = ['paused'];
    const t = new RecoveryTransport(c);
    const scheduled: { cancelled: boolean; fire: () => void }[] = [];
    const clock = { now: () => 1, set: (_delay: number, fire: () => void) => {
      const timer = { cancelled: false, fire };
      scheduled.push(timer);
      return () => { timer.cancelled = true; };
    } };
    let modelCalls = 0;
    const port = new RuntimeWorldModelPort({ info: { backend: 'fake', modelId: null }, load: async () => {}, dispose: async () => {},
      complete: async () => { modelCalls++; throw new Error('no inference during bootstrap'); } });
    const session = new WorldSession(t, port, { clock, recoverWorldId: 'world_school',
      recoveryLease: refresh ? { leaseToken: 'held_lease', fenceEpoch: 7 } : undefined });
    try {
      expect(await session.run()).toEqual({ kind: 'await', reason: 'paused_externally' });
      const count = t.calls.length;
      expect(await session.run()).toEqual({ kind: 'await', reason: 'paused_externally' });
      expect(t.calls).toHaveLength(count);
      const timer = [...scheduled].reverse().find((timer) => !timer.cancelled)!;
      expect(timer).toBeDefined();
      const renews = t.calls.filter((c) => c.operation === 'lease_renew').length;
      timer.fire();
      for (let i = 0; i < 8; i++) await Promise.resolve();
      expect(t.calls.filter((c) => c.operation === 'lease_renew')).toHaveLength(renews + 1);
      expect(modelCalls).toBe(0);
    } finally { await session.dispose(); }
  });

  test('failed bootstrap stays stopped across run calls and cannot fall into initial generation', async () => {
    const t = new RecoveryTransport(context());
    t.c.recovery = null; // active work without its originals
    let generated = false;
    const port = new RuntimeWorldModelPort({ info: { backend: 'fake', modelId: null }, load: async () => {}, dispose: async () => {},
      complete: async () => { generated = true; throw new Error('unexpected inference'); } });
    const session = new WorldSession(t, port, { recoverWorldId: 'world_school', clock: { now: () => 1, set: () => () => {} } });
    try {
      expect(await session.run()).toEqual({ kind: 'stop', reason: 'recovery_context_missing' });
      const count = t.calls.length;
      expect(await session.run()).toEqual({ kind: 'stop', reason: 'recovery_context_missing' });
      expect(t.calls).toHaveLength(count);
      expect(generated).toBe(false);
    } finally { await session.dispose(); }
  });
});
