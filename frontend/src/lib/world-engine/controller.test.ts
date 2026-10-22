/** Driver-loop tests over scripted transport/model stubs. Response bodies are
 * minimal server envelopes (the contract layer validates shapes elsewhere);
 * the scenarios follow the shared-trace flow for entry (T01 s1–s5), one group
 * cycle (T02-el shape) and seal/commit/narration. */
import { describe, expect, test } from 'vitest';
import { ControllerDriver, initialMemory, type WorldModelPort } from './controller';
import { errorCatalog, workingStateKey } from './schedule';
import type { ControllerMemory, ModelTask, PlannedPoint } from './schedule';
import { WorldApiError, WorldTimeoutError, type WorldTransport } from './transport';
import type { ClientAction, ControlState, ErrorCode, ErrorResponse, Id, Json, PointWork, TimeAdvance, WorldContext, WorldOperation } from './types';

const ORDER = ['person_a', 'person_b', 'person_c', 'person_d', 'person_e', 'person_f'];
const ta = (amount: number, boundary: 'elapsed' | 'instant' = 'elapsed'): TimeAdvance => ({ boundary, duration: { amount, unit: 'second' } });
const wt = { calendar: 'gregorian' as const, dateTime: '2026-01-01T00:00:00', instantOrdinal: 0 };
const position = { containerId: 'corridor', slotId: null, relativeTo: null };

const initialTemplate = () => ({
  engineVersion: 'world-engine-v1' as const, schemaVersion: 1 as const, protagonistId: 'person_a', initialTime: wt,
  locations: { corridor: { id: 'corridor', name: '走廊', parentLocationId: null, initialAppearance: '空旷' } },
  items: {},
  characters: { person_a: { id: 'person_a', name: '甲', initialPosition: position, initialAppearance: '正常', initialPersonality: '冷静', initialSanity: 50, tasks: {} } },
});
const workingState = () => ({
  engineVersion: 'world-engine-v1' as const, schemaVersion: 1 as const, worldId: 'w1', protagonistId: 'person_a', time: wt,
  initial: { ...initialTemplate(), worldId: 'w1' },
  locations: { corridor: { id: 'corridor', appearanceChanges: [] } }, items: {},
  characters: { person_a: { id: 'person_a', appearanceChanges: [], position, personalityChanges: [], sanity: 50, tasks: {} } },
});
const mkWorld = (over: Partial<WorldContext> = {}): WorldContext => ({
  worldId: 'w1', time: wt,
  head: { pointId: 'root', version: 0, stateDigest: 'd0', narrationStatus: 'ready' },
  advance: { advanceId: null, inputId: null, intentStatus: 'pending', inputAvailable: true },
  round: null, lease: { fenceEpoch: 1, expiresAtEpochMilli: 999999 },
  successor: null, activePointId: null, activeRoundId: null, ...over,
});
const mkControl = (over: Partial<ControlState> = {}): ControlState => ({
  phase: 'select_actor', paused: false, revision: 0,
  gate: { status: 'none', generation: null, issuedAtEpochMilli: null, expiresAtEpochMilli: null },
  blockedReasons: [], canCompute: true, ...over,
});
const mkWork = (over: Partial<PointWork> = {}): PointWork => ({
  pointId: 'p1', kind: 'normal', timeAdvance: ta(2), timeLocked: false, sealed: false, prefixDigest: null, predecessorWorkDigest: null,
  timeScanComplete: false, baseline: { headPointId: 'root', version: 0, stateDigest: 'd0' }, phase: 'select_actor',
  working: { cursor: 0, actedIds: [], visitedIds: [], settledUnitIds: [], intentStatus: 'pending' },
  settledUnits: [], pendingGroup: null, successor: null, ...over,
});

class ScriptedTransport implements WorldTransport {
  readonly ops: WorldOperation[] = [];
  readonly requests: unknown[] = [];
  private index = 0;
  constructor(public script: { op: WorldOperation; respond: (request: unknown) => unknown }[]) {}
  async execute(operation: WorldOperation, request: never, scope: never): Promise<never> {
    this.ops.push(operation);
    this.requests.push(structuredClone(request));
    const entry = this.script[this.index++];
    if (!entry || entry.op !== operation) throw new Error(`Unexpected transport call #${this.index}: ${operation}`);
    const response = entry.respond(request);
    if (response instanceof WorldApiError) throw response;
    return response as never;
  }
}

class ScriptedModel implements WorldModelPort {
  readonly calls: { task: ModelTask; key: string; input: Json }[] = [];
  private index = 0;
  constructor(public script: { task: ModelTask; output: Json }[]) {}
  async generate(task: ModelTask, key: string, input: Json): Promise<Json> {
    this.calls.push({ task, key, input: structuredClone(input) });
    const entry = this.script[this.index++];
    if (!entry || entry.task !== task) throw new Error(`Unexpected model call #${this.index}: ${task}/${key}`);
    return entry.output;
  }
}

const apiError = (code: ErrorCode, requestId: Id): WorldApiError => {
  const entry = errorCatalog[code];
  const response: ErrorResponse = {
    protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1,
    replayed: false, operation: null, requestId, worldId: 'w1',
    error: { code, httpStatus: entry.httpStatus, retryable: entry.retryable, clientAction: entry.clientAction, details: {} },
  };
  return new WorldApiError(response);
};

const memoryWithAdvanceStart = (over: Partial<ControllerMemory> = {}): ControllerMemory => ({
  ...initialMemory('req', 'browser'),
  leaseToken: 'lease1',
  playerInput: { text: '探索走廊', order: ORDER },
  allocPlan: { allocationKey: 'chain_slots', slots: [{ slotKey: 'advance', kind: 'advance', scope: null }, { slotKey: 'input', kind: 'input', scope: null }, { slotKey: 'round', kind: 'round', scope: null }] },
  ids: { advance: 'adv1', input: 'in1', round: 'r1' },
  ...over,
});

describe('driver end-to-end: entry, group cycle, seal/commit, narration', () => {
  test('drives the scripted scenario to the round boundary', async () => {
    let world = mkWorld({ head: { pointId: 'root', version: 0, stateDigest: 'd0', narrationStatus: 'pending' } });
    let control = mkControl({
      phase: 'complete',
      gate: { status: 'pending', generation: 1, issuedAtEpochMilli: 1, expiresAtEpochMilli: 2 },
      blockedReasons: ['narration_pending', 'phase_not_computable'], canCompute: false,
    });
    let work: PointWork | null = null;
    const writeOk = (operation: WorldOperation, requestId: Id, data: unknown) =>
      ({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation, requestId, requestHash: 'hash', world, control, work, data });
    const previewOk = (requestId: Id) => ({
      protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1,
      operation: 'preview_point', world, control, work,
      data: { pointId: 'p1', pointProjection: { worldId: 'w1', id: 'p1', sequence: 1, kind: 'normal', previousPointId: 'root', roundId: 'r1', advanceId: 'adv1', trigger: 'player', linkedFromPointId: null, timeAdvance: ta(2), entityDeltas: {} }, mergedEntityDeltas: {}, workingStateDigest: 'wsd1', pointProjectionDigest: 'ppd1', workingState: workingState() },
      requestId,
    });
    const transport = new ScriptedTransport([
      { op: 'create_world', respond: (r) => { world = { ...world, lease: { fenceEpoch: 1, expiresAtEpochMilli: 999999 } }; return writeOk('create_world', (r as { requestId: Id }).requestId, { worldId: 'w1', rootPointId: 'root', lease: { leaseToken: 'lease1', fenceEpoch: 1, expiresAtEpochMilli: 999999 } }); } },
      { op: 'narration_claim', respond: (r) => writeOk('narration_claim', (r as { requestId: Id }).requestId, { pointId: 'root', mode: 'head', generation: 1, fenceEpoch: 1, issuedAtEpochMilli: 5, expiresAtEpochMilli: 6, claimToken: 'ct_root' }) },
      { op: 'narration_submit', respond: (r) => { world = { ...world, head: { pointId: 'root', version: 0, stateDigest: 'd0', narrationStatus: 'ready' } }; control = mkControl({ phase: 'complete', revision: 1 }); return writeOk('narration_submit', (r as { requestId: Id }).requestId, { pointId: 'root', narrationStatus: 'ready', generation: 2 }); } },
      { op: 'allocate_ids', respond: (r) => { control = mkControl({ phase: 'complete', revision: 2 }); return writeOk('allocate_ids', (r as { requestId: Id }).requestId, { allocations: [{ slotKey: 'advance', id: 'adv1' }, { slotKey: 'input', id: 'in1' }, { slotKey: 'round', id: 'r1' }] }); } },
      { op: 'checkpoint_start_advance', respond: (r) => { world = { ...world, advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: false }, activeRoundId: 'r1', round: { roundId: 'r1', trigger: 'player', order: ORDER, cursor: 0, actedIds: [], visitedIds: [], conclusion: null } }; control = mkControl({ revision: 3 }); return writeOk('checkpoint_start_advance', (r as { requestId: Id }).requestId, { advanceId: 'adv1', inputId: 'in1', roundId: 'r1' }); } },
      { op: 'checkpoint_begin_point', respond: (r) => { work = mkWork(); control = mkControl({ revision: 4 }); return writeOk('checkpoint_begin_point', (r as { requestId: Id }).requestId, { pointId: 'p1' }); } },
      { op: 'preview_point', respond: (r) => previewOk((r as { requestId?: Id }).requestId ?? 'req') },
      { op: 'checkpoint_discover_group', respond: (r) => { work = mkWork({ phase: 'build_group', pendingGroup: { groupId: 'g1', sourceId: 'person_a', memberIds: ['person_a'], targetIds: [], frontierIds: [], closed: false } }); control = mkControl({ revision: 5 }); return writeOk('checkpoint_discover_group', (r as { requestId: Id }).requestId, { groupId: 'g1', targetIds: null }); } },
      { op: 'checkpoint_extend_group', respond: (r) => { control = mkControl({ revision: 6 }); return writeOk('checkpoint_extend_group', (r as { requestId: Id }).requestId, { groupId: 'g1', memberIds: ['person_a'], frontierIds: ['person_a'] }); } },
      { op: 'create_rolls', respond: (r) => writeOk('create_rolls', (r as { requestId: Id }).requestId, { rolls: [{ sourceId: 'person_a', targetId: (r as { rolls: [{ targetId: string }] }).rolls[0].targetId, triggerKey: (r as { rolls: [{ triggerKey: string }] }).rolls[0].triggerKey, rollId: 'roll_a', result: 3, eligibilityBaselineDigest: 'ebd', eligible: false, admitted: false }] }) },
      { op: 'create_rolls', respond: (r) => writeOk('create_rolls', (r as { requestId: Id }).requestId, { rolls: [{ sourceId: 'person_a', targetId: (r as { rolls: [{ targetId: string }] }).rolls[0].targetId, triggerKey: (r as { rolls: [{ triggerKey: string }] }).rolls[0].triggerKey, rollId: 'roll_d', result: 12, eligibilityBaselineDigest: 'ebd', eligible: true, admitted: true }] }) },
      { op: 'checkpoint_extend_group', respond: (r) => { work = mkWork({ phase: 'build_group', pendingGroup: { groupId: 'g1', sourceId: 'person_a', memberIds: ['person_a', 'person_d'], targetIds: [], frontierIds: [], closed: false } }); control = mkControl({ revision: 7 }); return writeOk('checkpoint_extend_group', (r as { requestId: Id }).requestId, { groupId: 'g1', memberIds: ['person_a', 'person_d'], frontierIds: [] }); } },
      { op: 'checkpoint_extend_group', respond: (r) => { control = mkControl({ revision: 8 }); return writeOk('checkpoint_extend_group', (r as { requestId: Id }).requestId, { groupId: 'g1', memberIds: ['person_a', 'person_d'], frontierIds: [] }); } },
      { op: 'checkpoint_close_group', respond: (r) => { work = mkWork({ phase: 'settle_group', pendingGroup: { groupId: 'g1', sourceId: 'person_a', memberIds: ['person_a', 'person_d'], targetIds: [], frontierIds: [], closed: true } }); control = mkControl({ revision: 9 }); return writeOk('checkpoint_close_group', (r as { requestId: Id }).requestId, { groupId: 'g1', closed: true }); } },
      { op: 'checkpoint_stage_unit', respond: (r) => { work = mkWork({ working: { cursor: 1, actedIds: ['person_a'], visitedIds: [], settledUnitIds: ['u1'], intentStatus: 'pending' } }); control = mkControl({ revision: 10 }); return writeOk('checkpoint_stage_unit', (r as { requestId: Id }).requestId, { groupId: 'g1', unitId: 'u1', working: work.working }); } },
      ...ORDER.slice(1).map((slotActorId, i) => ({
        op: 'checkpoint_record_skip' as WorldOperation,
        respond: (r: unknown) => {
          work = mkWork({ working: { cursor: i + 2, actedIds: ['person_a'], visitedIds: [], settledUnitIds: ['u1'], intentStatus: 'pending' } });
          control = mkControl({ revision: 11 + i });
          return writeOk('checkpoint_record_skip', (r as { requestId: Id }).requestId, { pointId: 'p1', working: work.working });
        },
      })),
      { op: 'preview_point', respond: (r) => previewOk((r as { requestId?: Id }).requestId ?? 'req') },
      { op: 'checkpoint_seal_point', respond: (r) => { work = mkWork({ sealed: true, prefixDigest: 'pd1', working: { cursor: 6, actedIds: ORDER, visitedIds: ORDER, settledUnitIds: ['u1'], intentStatus: 'pending' } }); control = mkControl({ revision: 16 }); return writeOk('checkpoint_seal_point', (r as { requestId: Id }).requestId, { pointId: 'p1', prefixDigest: 'pd1' }); } },
      { op: 'commit_point', respond: (r) => { world = { ...world, head: { pointId: 'p1', version: 1, stateDigest: 'd1', narrationStatus: 'pending' } }; work = null; control = mkControl({ revision: 17 }); return writeOk('commit_point', (r as { requestId: Id }).requestId, { pointId: 'p1', version: 1, stateDigest: 'd1' }); } },
      { op: 'narration_claim', respond: (r) => writeOk('narration_claim', (r as { requestId: Id }).requestId, { pointId: 'p1', mode: 'head', generation: 1, fenceEpoch: 1, issuedAtEpochMilli: 7, expiresAtEpochMilli: 8, claimToken: 'ct_p1' }) },
      { op: 'narration_submit', respond: (r) => { world = { ...world, head: { pointId: 'p1', version: 1, stateDigest: 'd1', narrationStatus: 'ready' } }; return writeOk('narration_submit', (r as { requestId: Id }).requestId, { pointId: 'p1', narrationStatus: 'ready', generation: 1 }); } },
    ]);
    const model = new ScriptedModel([
      { task: 'initial', output: initialTemplate() as unknown as Json },
      { task: 'narration', output: '根叙事已就绪。' },
      { task: 'pointPlan', output: [{ pointId: 'p1', kind: 'normal', timeAdvance: ta(2), actorIds: ['person_a'] }] as unknown as Json },
      { task: 'action', output: { kind: 'act', text: 'person_a采取冻结行动。' } as unknown as Json },
      { task: 'targets', output: { targets: [{ targetId: 'person_d', triggerKey: 'tk_d', ruleVersion: 'reaction-fixture-v1', target: 11 }, { targetId: 'person_a', triggerKey: 'tk_a', ruleVersion: 'reaction-fixture-v1', target: 11 }] } },
      { task: 'reaction', output: 'person_d被迫反应。' },
      { task: 'targets', output: { targets: [] } },
      { task: 'results', output: { person_a: '结果a。', person_d: '结果d。' } },
      { task: 'updates', output: [{ stage: 'appearance', changes: { person_a: { appearanceChanges: [{ id: 'ch1', text: '指尖结霜。', supersedes: [] }] } } }] as unknown as Json },
      { task: 'narration', output: 'p1叙事完成。' },
    ]);
    const memory = initialMemory('req', 'browser');
    memory.playerInput = { text: '探索走廊', order: ORDER };
    memory.allocPlan = { allocationKey: 'chain_slots', slots: [{ slotKey: 'advance', kind: 'advance', scope: null }, { slotKey: 'input', kind: 'input', scope: null }, { slotKey: 'round', kind: 'round', scope: null }] };
    memory.ids = { 'group:person_a': 'g1' };
    const driver = new ControllerDriver({ transport, model }, memory);

    const status = await driver.run();
    expect(status).toEqual({ kind: 'await', reason: 'round_points_exhausted' });

    expect(transport.ops).toEqual([
      'create_world', 'narration_claim', 'narration_submit', 'allocate_ids', 'checkpoint_start_advance',
      'checkpoint_begin_point', 'preview_point', 'checkpoint_discover_group',
      'checkpoint_extend_group', 'create_rolls', 'create_rolls', 'checkpoint_extend_group', 'checkpoint_extend_group',
      'checkpoint_close_group', 'checkpoint_stage_unit',
      ...ORDER.slice(1).map(() => 'checkpoint_record_skip' as WorldOperation),
      'preview_point', 'checkpoint_seal_point', 'commit_point', 'narration_claim', 'narration_submit',
    ]);
    expect(model.calls.map((c) => `${c.task}:${c.key}`)).toEqual([
      'initial:initial', 'narration:root', 'pointPlan:r1', 'action:person_a', 'targets:person_a',
      'reaction:person_a', 'targets:person_d', 'results:g1', 'updates:g1', 'narration:p1',
    ]);
    const requestIds = (transport.requests as { requestId?: Id }[]).map((r) => r.requestId).filter((id): id is Id => id != null);
    expect(new Set(requestIds).size).toBe(requestIds.length);
    const extendTargets = transport.requests[8] as { targets: { targetId: string }[]; admittedMember: unknown };
    expect((transport.requests[7] as { groupId: Id }).groupId).toBe('g1');
    expect(extendTargets.targets.map((t) => t.targetId)).toEqual(['person_d', 'person_a']);
    const rolls = (transport.requests[9] as { rolls: { targetId: string }[] }).rolls;
    expect(rolls[0].targetId).toBe('person_a');
    expect((transport.requests[10] as { rolls: { targetId: string }[] }).rolls[0].targetId).toBe('person_d');
    const committed = driver.getMemory();
    expect(committed).toMatchObject({ leaseToken: 'lease1', planIndex: 1, staged: [], groupActors: [], narration: null, budget: { used: 10 } });
    expect(committed.ids).toMatchObject({ advance: 'adv1', input: 'in1', round: 'r1' });
    const plan = committed.plan as PlannedPoint[];
    expect(plan[0]).toMatchObject({ pointId: 'p1', actorIds: ['person_a'] });
  });
});

describe('driver error routing and controls', () => {
  const advancing = (over: Partial<ControllerMemory> = {}) => {
    const world = mkWorld({ advance: { advanceId: null, inputId: null, intentStatus: 'pending', inputAvailable: true } });
    const control = mkControl();
    const transport = new ScriptedTransport([]);
    const model = new ScriptedModel([]);
    const driver = new ControllerDriver({ transport, model }, memoryWithAdvanceStart(over), { world, control });
    return { world, control, transport, model, driver };
  };
  test('request_in_progress retries the same payload and requestId', async () => {
    const { transport, driver } = advancing();
    transport.script = [
      { op: 'checkpoint_start_advance', respond: () => apiError('request_in_progress', 'retry') },
      { op: 'checkpoint_start_advance', respond: (r) => ({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation: 'checkpoint_start_advance', requestId: (r as { requestId: Id }).requestId, requestHash: 'h', world: mkWorld(), control: mkControl({ revision: 1 }), work: null, data: { advanceId: 'adv1', inputId: 'in1', roundId: 'r1' } }) },
    ];
    await driver.step();
    await driver.step();
    expect(transport.ops).toEqual(['checkpoint_start_advance', 'checkpoint_start_advance']);
    const ids = (transport.requests as { requestId: Id }[]).map((r) => r.requestId);
    expect(ids[0]).toBe(ids[1]);
  });
  test('definitive rejection refreshes context and mints a new requestId', async () => {
    const { transport, driver } = advancing();
    transport.script = [
      { op: 'checkpoint_start_advance', respond: (r) => apiError('revision_mismatch', (r as { requestId: Id }).requestId) },
      { op: 'get_context', respond: () => ({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, world: mkWorld(), control: mkControl({ revision: 7 }), work: null, activeInput: null, recovery: null }) },
      { op: 'checkpoint_start_advance', respond: (r) => ({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation: 'checkpoint_start_advance', requestId: (r as { requestId: Id }).requestId, requestHash: 'h', world: mkWorld(), control: mkControl({ revision: 8 }), work: null, data: { advanceId: 'adv1', inputId: 'in1', roundId: 'r1' } }) },
    ];
    await driver.step();
    await driver.step();
    await driver.step();
    expect(transport.ops).toEqual(['checkpoint_start_advance', 'get_context', 'checkpoint_start_advance']);
    const ids = (transport.requests as { requestId: Id }[]).map((r) => r.requestId);
    expect(ids[2]).not.toBe(ids[0]);
  });
  test('stale_epoch acquires a lease and the retry carries the new token', async () => {
    const { transport, driver } = advancing();
    transport.script = [
      { op: 'checkpoint_start_advance', respond: (r) => apiError('stale_epoch', (r as { requestId: Id }).requestId) },
      { op: 'lease_acquire', respond: () => ({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation: 'lease_acquire', requestId: 'x', requestHash: 'h', world: mkWorld({ lease: { fenceEpoch: 2, expiresAtEpochMilli: 999999 } }), control: mkControl(), work: null, data: { leaseToken: 'lease2', fenceEpoch: 2, expiresAtEpochMilli: 999999, holderId: 'browser' } }) },
      { op: 'checkpoint_start_advance', respond: (r) => ({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation: 'checkpoint_start_advance', requestId: (r as { requestId: Id }).requestId, requestHash: 'h', world: mkWorld({ lease: { fenceEpoch: 2, expiresAtEpochMilli: 999999 } }), control: mkControl({ revision: 1 }), work: null, data: { advanceId: 'adv1', inputId: 'in1', roundId: 'r1' } }) },
    ];
    await driver.step();
    await driver.step();
    await driver.step();
    expect(transport.ops).toEqual(['checkpoint_start_advance', 'lease_acquire', 'checkpoint_start_advance']);
    expect(driver.getMemory().leaseToken).toBe('lease2');
    expect((transport.requests[2] as { leaseToken: Id }).leaseToken).toBe('lease2');
  });
  test('exhausted budget pauses and reports the local pause', async () => {
    const world = mkWorld({ advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: false }, activeRoundId: 'r1', activePointId: 'p1', round: { roundId: 'r1', trigger: 'player', order: ORDER, cursor: 0, actedIds: [], visitedIds: [], conclusion: null } });
    const control = mkControl({ revision: 4 });
    const work = mkWork();
    const transport = new ScriptedTransport([
      { op: 'checkpoint_pause', respond: () => ({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation: 'checkpoint_pause', requestId: 'x', requestHash: 'h', world, control: mkControl({ revision: 5, paused: true }), work, data: { paused: true } }) },
    ]);
    const driver = new ControllerDriver(
      { transport, model: new ScriptedModel([]) },
      memoryWithAdvanceStart({
        plan: [{ pointId: 'p1', kind: 'normal', timeAdvance: ta(2), actorIds: ['person_a'] }],
        workingState: { key: JSON.stringify([work.pointId, work.baseline.version, work.timeAdvance, work.working.settledUnitIds, work.timeScanComplete]), state: workingState() as never },
        budget: { used: 4, max: 4 },
      }),
      { world, control, work },
    );
    expect(await driver.step()).toBeUndefined();
    expect(await driver.step()).toEqual({ kind: 'await', reason: 'local_budget_pause' });
    expect(driver.getMemory().localPause).toBe(true);
  });
  test('a pause command awaits the user, not the scheduler', async () => {
    const world = mkWorld({ advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: false }, activeRoundId: 'r1', activePointId: 'p1', round: { roundId: 'r1', trigger: 'player', order: ORDER, cursor: 0, actedIds: [], visitedIds: [], conclusion: null } });
    const control = mkControl({ revision: 4 });
    const work = mkWork();
    const transport = new ScriptedTransport([
      { op: 'checkpoint_pause', respond: () => ({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation: 'checkpoint_pause', requestId: 'x', requestHash: 'h', world, control: mkControl({ revision: 5, paused: true }), work, data: { paused: true } }) },
    ]);
    const driver = new ControllerDriver(
      { transport, model: new ScriptedModel([]) },
      memoryWithAdvanceStart({ plan: [{ pointId: 'p1', kind: 'normal', timeAdvance: ta(2), actorIds: ['person_a'] }] }),
      { world, control, work },
    );
    driver.deliver({ kind: 'pause' });
    expect(await driver.step()).toBeUndefined();
    expect(await driver.step()).toEqual({ kind: 'await', reason: 'paused_externally' });
    expect(driver.getMemory().localPause).toBe(false);
  });
});

describe('review regressions (553e341 findings)', () => {
  const midPoint = (workOver: Partial<PointWork>, memoryOver: Partial<ControllerMemory> = {}) => {
    const world = mkWorld({
      advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: false },
      activeRoundId: 'r1', activePointId: 'p1',
      round: { roundId: 'r1', trigger: 'player', order: ORDER, cursor: 0, actedIds: [], visitedIds: [], conclusion: null },
    });
    const control = mkControl({ revision: 6 });
    const work = mkWork(workOver);
    const transport = new ScriptedTransport([]);
    const model = new ScriptedModel([]);
    const memory = memoryWithAdvanceStart({
      plan: [{ pointId: 'p1', kind: 'normal', timeAdvance: ta(2), actorIds: ['person_a'] }],
      ids: { 'group:person_a': 'g1' },
      workingState: { key: workingStateKey(work), state: workingState() as never },
      ...memoryOver,
    });
    const driver = new ControllerDriver({ transport, model }, memory, { world, control, work });
    const writeOk = (operation: WorldOperation, request: unknown, data: unknown) => ({
      protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1,
      replayed: false, operation, requestId: (request as { requestId?: Id })?.requestId ?? 'req', requestHash: 'hash', world, control, work, data,
    });
    return { world, control, work, transport, model, driver, writeOk };
  };

  test('a final not-admitted roll retires the source and closes the group', async () => {
    const { transport, driver, writeOk } = midPoint(
      { phase: 'build_group', pendingGroup: { groupId: 'g1', sourceId: 'person_a', memberIds: ['person_a'], targetIds: [], frontierIds: [], closed: false } },
      { sources: [{ sourceId: 'person_a', actionText: '行动。', targetsExtended: true, pendingTargets: [{ targetId: 'person_d', triggerKey: 'tk_d', rule: { ruleVersion: 'reaction-fixture-v1', target: 11 } }], rolled: [] }] },
    );
    transport.script = [
      { op: 'create_rolls', respond: (r) => writeOk('create_rolls', r, { rolls: [{ sourceId: 'person_a', targetId: 'person_d', triggerKey: 'tk_d', rollId: 'roll_d', result: 3, eligibilityBaselineDigest: 'ebd', eligible: false, admitted: false }] }) },
      { op: 'checkpoint_close_group', respond: (r) => writeOk('checkpoint_close_group', r, { groupId: 'g1', closed: true }) },
    ];
    await driver.step();
    expect(driver.getMemory().sources).toEqual([]);
    await driver.step();
    expect(transport.ops).toEqual(['create_rolls', 'checkpoint_close_group']);
  });

  test('an admitted member counts as acted and never gets a second action call', async () => {
    const { transport, model, driver, work, writeOk } = midPoint(
      { phase: 'build_group', pendingGroup: { groupId: 'g1', sourceId: 'person_a', memberIds: ['person_a', 'person_d'], targetIds: [], frontierIds: [], closed: false } },
      {
        groupActors: ['person_a'],
        lastModel: { task: 'reaction', key: 'person_a', output: 'person_d被迫反应。' },
        sources: [{ sourceId: 'person_a', actionText: '行动。', targetsExtended: true, pendingTargets: [], rolled: [{ targetId: 'person_d', triggerKey: 'tk_d', rule: { ruleVersion: 'reaction-fixture-v1', target: 11 }, rollId: 'roll_d', admitted: true, reacted: false }] }],
      },
    );
    transport.script = [
      { op: 'checkpoint_extend_group', respond: (r) => writeOk('checkpoint_extend_group', r, { groupId: 'g1', memberIds: ['person_a', 'person_d'], frontierIds: [] }) },
      { op: 'checkpoint_extend_group', respond: (r) => writeOk('checkpoint_extend_group', r, { groupId: 'g1', memberIds: ['person_a', 'person_d'], frontierIds: [] }) },
      { op: 'checkpoint_close_group', respond: (r) => { Object.assign(work!, { phase: 'settle_group', pendingGroup: { groupId: 'g1', sourceId: 'person_a', memberIds: ['person_a', 'person_d'], targetIds: [], frontierIds: [], closed: true } }); return writeOk('checkpoint_close_group', r, { groupId: 'g1', closed: true }); } },
      { op: 'checkpoint_stage_unit', respond: (r) => { Object.assign(work!, { phase: 'select_actor', pendingGroup: null, working: { cursor: 2, actedIds: ['person_a', 'person_d'], visitedIds: [], settledUnitIds: ['u1'], intentStatus: 'pending' } }); return writeOk('checkpoint_stage_unit', r, { groupId: 'g1', unitId: 'u1', working: work.working }); } },
      { op: 'checkpoint_record_skip', respond: (r) => writeOk('checkpoint_record_skip', r, { pointId: 'p1', working: work.working }) },
    ];
    model.script = [
      { task: 'targets', output: { targets: [] } },
      { task: 'results', output: { person_a: 'a。', person_d: 'd。' } },
      { task: 'updates', output: [] as unknown as Json },
    ];
    await driver.step(); // extend admittedMember (consumes the reaction output)
    await driver.step(); // model targets for person_d (DFS)
    await driver.step(); // extend person_d targets
    await driver.step(); // close (both sources retired)
    await driver.step(); // model results
    await driver.step(); // model updates
    await driver.step(); // stage
    await driver.step(); // leave-behind skip
    expect(model.calls.map((c) => `${c.task}:${c.key}`)).toEqual(['targets:person_d', 'results:g1', 'updates:g1']);
    expect(transport.ops).toEqual(['checkpoint_extend_group', 'checkpoint_extend_group', 'checkpoint_close_group', 'checkpoint_stage_unit', 'checkpoint_record_skip']);
    expect((transport.requests[4] as { slotActorId: string }).slotActorId).toBe('person_c');
    expect(driver.getMemory().groupActors).toEqual(['person_a', 'person_d']);
  });

  test('split updates restart per point (no candidate leakage through commit)', async () => {
    let world = mkWorld({ advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: false }, activeRoundId: 'r1', activePointId: 'p0', round: { roundId: 'r1', trigger: 'player', order: ORDER, cursor: 0, actedIds: [], visitedIds: [], conclusion: null } });
    let control = mkControl({ revision: 2 });
    let work: PointWork | null = mkWork({ pointId: 'p0', timeAdvance: ta(60) });
    const writeOk = (operation: WorldOperation, request: unknown, data: unknown) => ({
      protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1,
      replayed: false, operation, requestId: (request as { requestId?: Id })?.requestId ?? 'req', requestHash: 'hash', world, control, work, data,
    });
    const previewOk = (r: unknown) => ({
      protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1,
      operation: 'preview_point', world, control, work, requestId: (r as { requestId?: Id })?.requestId,
      data: { pointId: work!.pointId, pointProjection: { worldId: 'w1', id: work!.pointId, sequence: 1, kind: 'normal', previousPointId: 'root', roundId: 'r1', advanceId: 'adv1', trigger: 'automatic', linkedFromPointId: null, timeAdvance: work!.timeAdvance, entityDeltas: {} }, mergedEntityDeltas: {}, workingStateDigest: 'wsd', pointProjectionDigest: 'ppd', workingState: workingState() },
    });
    const scanCalls: number[] = [];
    const scanEntry = (): { op: WorldOperation; respond: (r: unknown) => unknown } => ({
      op: 'checkpoint_stage_time_scan',
      respond: (r) => {
        scanCalls.push(((JSON.parse(JSON.stringify(r)) as { candidates: { sanities: Record<string, number> } }).candidates.sanities.person_a));
        Object.assign(work!, { timeScanComplete: true });
        control = mkControl({ revision: control.revision + 1 });
        return writeOk('checkpoint_stage_time_scan', r, { pointId: work!.pointId, working: work!.working });
      },
    });
    const previewEntry = () => ({ op: 'preview_point' as WorldOperation, respond: (r: unknown) => previewOk(r) });
    const sealEntry = () => ({
      op: 'checkpoint_seal_point' as WorldOperation,
      respond: (r: unknown) => {
        Object.assign(work!, { sealed: true, prefixDigest: 'pd' });
        control = mkControl({ revision: control.revision + 1 });
        return writeOk('checkpoint_seal_point', r, { pointId: work!.pointId, prefixDigest: 'pd' });
      },
    });
    const commitEntry = (digest: string) => ({
      op: 'commit_point' as WorldOperation,
      respond: (r: unknown) => {
        const finished = work;
        world = { ...world, head: { pointId: finished!.pointId, version: 1, stateDigest: digest, narrationStatus: 'pending' } };
        work = null;
        control = mkControl({ revision: control.revision + 1 });
        return writeOk('commit_point', r, { pointId: finished!.pointId, version: 1, stateDigest: digest });
      },
    });
    const claimEntry = () => ({
      op: 'narration_claim' as WorldOperation,
      respond: (r: unknown) => writeOk('narration_claim', r, { pointId: world.head.pointId, mode: 'head', generation: 1, fenceEpoch: 1, issuedAtEpochMilli: 1, expiresAtEpochMilli: 2, claimToken: `ct_${world.head.pointId}` }),
    });
    const submitEntry = () => ({
      op: 'narration_submit' as WorldOperation,
      respond: (r: unknown) => {
        world = { ...world, head: { ...world.head, narrationStatus: 'ready' } };
        return writeOk('narration_submit', r, { pointId: world.head.pointId, narrationStatus: 'ready', generation: 1 });
      },
    });
    const transport = new ScriptedTransport([
      previewEntry(), scanEntry(), previewEntry(), sealEntry(), commitEntry('dp0'),
      claimEntry(), submitEntry(),
      {
        op: 'checkpoint_begin_point',
        respond: (r) => {
          work = mkWork({ pointId: 'p1', timeAdvance: ta(60) });
          world = { ...world, activePointId: 'p1' };
          control = mkControl({ revision: control.revision + 1 });
          return writeOk('checkpoint_begin_point', r, { pointId: 'p1' });
        },
      },
      previewEntry(), scanEntry(), previewEntry(), sealEntry(), commitEntry('dp1'),
      claimEntry(), submitEntry(),
    ]);
    const model = new ScriptedModel([
      { task: 'updates', output: { stage: 'sanity', changes: { person_a: { sanitySet: 40 } } } as unknown as Json },
      { task: 'narration', output: 'p0叙事。' },
      { task: 'updates', output: { stage: 'sanity', changes: { person_a: { sanitySet: 41 } } } as unknown as Json },
      { task: 'narration', output: 'p1叙事。' },
    ]);
    const memory = memoryWithAdvanceStart({
      plan: [
        { pointId: 'p0', kind: 'normal', timeAdvance: ta(60), actorIds: [] },
        { pointId: 'p1', kind: 'normal', timeAdvance: ta(60), actorIds: [] },
      ],
      updatesStages: ['sanity'],
    });
    const driver = new ControllerDriver({ transport, model }, memory, { world, control, work });
    const status = await driver.run();
    expect(status).toEqual({ kind: 'await', reason: 'round_points_exhausted' });
    expect(scanCalls).toEqual([40, 41]);
    expect(model.calls.map((c) => c.key)).toEqual(['time_scan:p0#sanity', 'p0', 'time_scan:p1#sanity', 'p1']);
    expect(driver.getMemory().updatesCalls).toEqual([]);
  });

  test('claim_expired drops the claim and regenerates with a fresh token', async () => {
    const world = mkWorld({ head: { pointId: 'p1', version: 1, stateDigest: 'd1', narrationStatus: 'pending' } });
    const control = mkControl({ revision: 13 });
    const transport = new ScriptedTransport([
      { op: 'narration_submit', respond: (r) => apiError('claim_expired', (r as { requestId?: Id })?.requestId ?? 'req') },
      { op: 'narration_claim', respond: (r) => ({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation: 'narration_claim', requestId: (r as { requestId: Id }).requestId, requestHash: 'hash', world, control, work: null, data: { pointId: 'p1', mode: 'head', generation: 2, fenceEpoch: 1, issuedAtEpochMilli: 9, expiresAtEpochMilli: 10, claimToken: 'ct_new' } }) },
      { op: 'narration_submit', respond: (r) => ({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation: 'narration_submit', requestId: (r as { requestId: Id }).requestId, requestHash: 'hash', world: { ...world, head: { ...world.head, narrationStatus: 'ready' } }, control, work: null, data: { pointId: 'p1', narrationStatus: 'ready', generation: 2 } }) },
    ]);
    const model = new ScriptedModel([{ task: 'narration', output: '重生成叙事。' }]);
    const memory = memoryWithAdvanceStart({
      narration: { pointId: 'p1', claim: { claimToken: 'ct_old', generation: 1, issuedAtEpochMilli: 1 }, input: { pointId: 'p1' } },
      lastModel: { task: 'narration', key: 'p1', output: '旧文本。' },
    });
    const driver = new ControllerDriver({ transport, model }, memory, { world, control });
    await driver.step();
    expect(driver.getMemory().narration).toMatchObject({ pointId: 'p1', claim: null });
    expect(driver.getMemory().lastModel).toBeNull();
    await driver.step();
    await driver.step();
    await driver.step();
    expect(transport.ops).toEqual(['narration_submit', 'narration_claim', 'narration_submit']);
    expect((transport.requests[2] as { claimToken: Id }).claimToken).toBe('ct_new');
    expect(model.calls.length).toBe(1);
    expect(driver.getMemory().narration).toBeNull();
  });

  test('an external pause survives a lease detour', async () => {
    const world = mkWorld({ lease: null });
    const control = mkControl();
    const transport = new ScriptedTransport([
      { op: 'lease_acquire', respond: (r) => ({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation: 'lease_acquire', requestId: (r as { requestId: Id }).requestId, requestHash: 'hash', world: { ...world, lease: { fenceEpoch: 2, expiresAtEpochMilli: 9 } }, control, work: null, data: { leaseToken: 'lease2', fenceEpoch: 2, expiresAtEpochMilli: 9, holderId: 'browser' } }) },
      { op: 'checkpoint_pause', respond: (r) => ({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation: 'checkpoint_pause', requestId: (r as { requestId: Id }).requestId, requestHash: 'hash', world: { ...world, lease: { fenceEpoch: 2, expiresAtEpochMilli: 9 } }, control: mkControl({ paused: true, revision: 1 }), work: null, data: { paused: true } }) },
    ]);
    const driver = new ControllerDriver({ transport, model: new ScriptedModel([]) }, memoryWithAdvanceStart({ leaseToken: null }), { world, control });
    driver.deliver({ kind: 'pause' });
    await driver.step();
    expect(transport.ops).toEqual(['lease_acquire']);
    expect(driver.getMemory().leaseToken).toBe('lease2');
    await driver.step();
    expect(transport.ops).toEqual(['lease_acquire', 'checkpoint_pause']);
    expect(await driver.step()).toEqual({ kind: 'await', reason: 'paused_externally' });
  });

  test('preview errors route through refresh_context and re-preview', async () => {
    const world = mkWorld({ advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: false }, activeRoundId: 'r1', activePointId: 'p1', round: { roundId: 'r1', trigger: 'player', order: ORDER, cursor: 0, actedIds: [], visitedIds: [], conclusion: null } });
    let control = mkControl({ revision: 3 });
    const work = mkWork();
    const previewOk = (r: unknown) => ({
      protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1,
      operation: 'preview_point', world, control, work, requestId: (r as { requestId?: Id })?.requestId,
      data: { pointId: 'p1', pointProjection: { worldId: 'w1', id: 'p1', sequence: 1, kind: 'normal', previousPointId: 'root', roundId: 'r1', advanceId: 'adv1', trigger: 'player', linkedFromPointId: null, timeAdvance: ta(2), entityDeltas: {} }, mergedEntityDeltas: {}, workingStateDigest: 'wsd', pointProjectionDigest: 'ppd', workingState: workingState() },
    });
    const transport = new ScriptedTransport([
      { op: 'preview_point', respond: (r) => apiError('revision_mismatch', (r as { requestId?: Id })?.requestId ?? 'req') },
      { op: 'get_context', respond: () => ({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, world, control: mkControl({ revision: 9 }), work, activeInput: null, recovery: null }) },
      { op: 'preview_point', respond: (r) => previewOk(r) },
    ]);
    const driver = new ControllerDriver({ transport, model: new ScriptedModel([]) }, memoryWithAdvanceStart({ plan: [{ pointId: 'p1', kind: 'normal', timeAdvance: ta(2), actorIds: ['person_a'] }] }), { world, control, work });
    await driver.step();
    await driver.step();
    expect(transport.ops).toEqual(['preview_point', 'get_context', 'preview_point']);
    expect((transport.requests[2] as { expectedCheckpointRevision: number }).expectedCheckpointRevision).toBe(9);
    expect(driver.getMemory().workingState).not.toBeNull();
  });

  test('retry limit bounds timeout and request_in_progress loops', async () => {
    let timeoutCalls = 0;
    const timeoutTransport: WorldTransport = { async execute() { timeoutCalls++; throw new WorldTimeoutError(); } };
    const driver1 = new ControllerDriver({ transport: timeoutTransport, model: new ScriptedModel([]) }, memoryWithAdvanceStart(), { world: mkWorld(), control: mkControl() }, { retryLimit: 2 });
    const status = await driver1.run(1);
    expect(timeoutCalls).toBe(3);
    expect(status).toEqual({ kind: 'error', detail: expect.stringContaining('retry limit') });

    let busyCalls = 0;
    const busyTransport: WorldTransport = { async execute(operation, request) { busyCalls++; throw apiError('request_in_progress', (request as { requestId?: Id })?.requestId ?? 'req'); } };
    const driver2 = new ControllerDriver({ transport: busyTransport, model: new ScriptedModel([]) }, memoryWithAdvanceStart(), { world: mkWorld(), control: mkControl() }, { retryLimit: 2 });
    const status2 = await driver2.run(1);
    expect(busyCalls).toBe(3);
    expect(status2.kind).toBe('error');
  });
});
