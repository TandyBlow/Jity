/** Driver-loop tests over scripted transport/model stubs. Response bodies are
 * minimal server envelopes (the contract layer validates shapes elsewhere);
 * the scenarios follow the shared-trace flow for entry (T01 s1–s5), one group
 * cycle (T02-el shape) and seal/commit/narration. */
import { describe, expect, test } from 'vitest';
import { ControllerDriver, initialMemory, type WorldModelPort } from './controller';
import { errorCatalog, triggerAllocationKey, triggerSlotKey, workingStateKey } from './schedule';
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
    // get_state 读取回包：world/control 沿用闭包当前值；data 携带该点自身记录（根点 null/null/{}）。
    const stateOk = (pointId: Id, previousPointId: Id | null, timeAdvance: TimeAdvance | null, entityDeltas: Record<string, unknown>) => ({
      protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1,
      world, control,
      data: { pointId, version: pointId === 'root' ? 0 : 1, state: workingState(), stateDigest: pointId === 'root' ? 'd0' : 'd1', previousPointId, timeAdvance, entityDeltas },
    });
    const transport = new ScriptedTransport([
      { op: 'create_world', respond: (r) => { world = { ...world, lease: { fenceEpoch: 1, expiresAtEpochMilli: 999999 } }; return writeOk('create_world', (r as { requestId: Id }).requestId, { worldId: 'w1', rootPointId: 'root', lease: { leaseToken: 'lease1', fenceEpoch: 1, expiresAtEpochMilli: 999999 } }); } },
      { op: 'narration_claim', respond: (r) => writeOk('narration_claim', (r as { requestId: Id }).requestId, { pointId: 'root', mode: 'head', generation: 1, fenceEpoch: 1, issuedAtEpochMilli: 5, expiresAtEpochMilli: 6, claimToken: 'ct_root' }) },
      { op: 'get_state', respond: () => stateOk('root', null, null, {}) },
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
      { op: 'get_state', respond: () => stateOk('p1', 'root', ta(2), { person_a: { entityId: 'person_a', positionSet: position } } as never) },
      { op: 'get_state', respond: () => stateOk('root', null, null, {}) },
      { op: 'narration_submit', respond: (r) => { world = { ...world, head: { pointId: 'p1', version: 1, stateDigest: 'd1', narrationStatus: 'ready' } }; return writeOk('narration_submit', (r as { requestId: Id }).requestId, { pointId: 'p1', narrationStatus: 'ready', generation: 1 }); } },
    ]);
    const model = new ScriptedModel([
      { task: 'initial', output: initialTemplate() as unknown as Json },
      { task: 'narration', output: '根叙事已就绪。' },
      { task: 'pointPlan', output: [{ pointId: 'p1', kind: 'normal', timeAdvance: ta(2), actorIds: ['person_a'] }] as unknown as Json },
      { task: 'action', output: { kind: 'act', text: 'person_a采取冻结行动。' } as unknown as Json },
      { task: 'targets', output: { targets: [{ targetId: 'person_d' }, { targetId: 'person_a' }] } },
      { task: 'reaction', output: 'person_d被迫反应。' },
      { task: 'targets', output: { targets: [] } },
      { task: 'results', output: { person_a: '结果a。', person_d: '结果d。' } },
      { task: 'updates', output: [{ stage: 'appearance', changes: { person_a: { appearanceChanges: [{ id: 'ch1', text: '指尖结霜。', supersedes: [] }] } } }] as unknown as Json },
      { task: 'narration', output: 'p1叙事完成。' },
    ]);
    const memory = initialMemory('req', 'browser');
    memory.playerInput = { text: '探索走廊', order: ORDER };
    memory.allocPlan = { allocationKey: 'chain_slots', slots: [{ slotKey: 'advance', kind: 'advance', scope: null }, { slotKey: 'input', kind: 'input', scope: null }, { slotKey: 'round', kind: 'round', scope: null }] };
    // 触发键是程序身份（#8）：夹具按调度器槽位键（含来源）预置，模型输出只声明目标。
    memory.ids = { 'group:person_a': 'g1', [triggerSlotKey('g1', 'person_a', 'person_d')]: 'tk_d', [triggerSlotKey('g1', 'person_a', 'person_a')]: 'tk_a' };
    const driver = new ControllerDriver({ transport, model }, memory);

    const status = await driver.run();
    expect(status).toEqual({ kind: 'await', reason: 'round_points_exhausted' });

    expect(transport.ops).toEqual([
      'create_world', 'narration_claim', 'get_state', 'narration_submit', 'allocate_ids', 'checkpoint_start_advance',
      'checkpoint_begin_point', 'preview_point', 'checkpoint_discover_group',
      'checkpoint_extend_group', 'create_rolls', 'create_rolls', 'checkpoint_extend_group', 'checkpoint_extend_group',
      'checkpoint_close_group', 'checkpoint_stage_unit',
      ...ORDER.slice(1).map(() => 'checkpoint_record_skip' as WorldOperation),
      'preview_point', 'checkpoint_seal_point', 'commit_point', 'narration_claim', 'get_state', 'get_state', 'narration_submit',
    ]);
    expect(model.calls.map((c) => `${c.task}:${c.key}`)).toEqual([
      'initial:initial', 'narration:root', 'pointPlan:r1', 'action:person_a', 'targets:person_a',
      'reaction:person_a', 'targets:person_d', 'results:g1', 'updates:g1', 'narration:p1',
    ]);
    const requestIds = (transport.requests as { requestId?: Id }[]).map((r) => r.requestId).filter((id): id is Id => id != null);
    expect(new Set(requestIds).size).toBe(requestIds.length);
    const extendTargets = transport.requests[9] as { targets: { targetId: string }[]; admittedMember: unknown };
    expect((transport.requests[8] as { groupId: Id }).groupId).toBe('g1');
    expect(extendTargets.targets.map((t) => t.targetId)).toEqual(['person_d', 'person_a']);
    const rolls = (transport.requests[10] as { rolls: { targetId: string }[] }).rolls;
    expect(rolls[0].targetId).toBe('person_a');
    expect((transport.requests[11] as { rolls: { targetId: string }[] }).rolls[0].targetId).toBe('person_d');
    // 叙事模型输入 = 独立手写字面量（不经 assembleNarrationInput）：固定输出验证。
    const nsState = workingState() as unknown as Json;
    const perspective = '主角视角（person_a「甲」）；只表达已结算的世界事实';
    expect(model.calls[1].input).toEqual({ pointId: 'root', before: null, delta: { timeAdvance: null, entityDeltas: {} }, after: nsState, perspective });
    expect(model.calls[9].input).toEqual({ pointId: 'p1', before: nsState, delta: { timeAdvance: ta(2), entityDeltas: { person_a: { entityId: 'person_a', positionSet: position } } }, after: nsState, perspective });
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

  test('#5 P1 regression: a refused position preview means ZERO appearance model calls', async () => {
    // 位置阶段引用不存在的容器 → preview 被 A 拒绝（ID_UNRESOLVED →
    // version_mismatch）→ 原有终态处理；外貌模型零调用、无跳过计数。
    const world = mkWorld({ head: { pointId: 'root', version: 0, stateDigest: 'd0', narrationStatus: 'ready' }, lease: { fenceEpoch: 1, expiresAtEpochMilli: 999999 }, activePointId: 'p1', activeRoundId: 'r1', advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: false } });
    let control = mkControl({ revision: 2 });
    let work = mkWork({ timeLocked: true, phase: 'settle_group', pendingGroup: { groupId: 'g1', sourceId: 'person_a', memberIds: ['person_a'], targetIds: [], frontierIds: [], closed: true } });
    const memory = initialMemory('req', 'browser');
    memory.leaseToken = 'lease1';
    memory.workingState = { key: workingStateKey(work), state: workingState() };
    memory.lastResults = { person_a: '结果。' };
    memory.updatesStages = ['position', 'appearance'];
    const previewRefused = () => { throw new WorldApiError(({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation: null, requestId: 'req', worldId: 'w1', error: { code: 'version_mismatch', httpStatus: 409, retryable: false, clientAction: 'refresh_context' as const, details: {} } }) as never); };
    const transport = new ScriptedTransport([
      { op: 'preview_point', respond: previewRefused },
      { op: 'get_context', respond: () => ({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, world, control, work, activeInput: null, recovery: null }) },
      { op: 'preview_point', respond: previewRefused },
      { op: 'get_context', respond: () => ({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, world, control, work, activeInput: null, recovery: null }) },
      { op: 'preview_point', respond: previewRefused },
      { op: 'get_context', respond: () => ({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, world, control, work, activeInput: null, recovery: null }) },
      { op: 'preview_point', respond: previewRefused },
      { op: 'get_context', respond: () => ({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, world, control, work, activeInput: null, recovery: null }) },
      { op: 'preview_point', respond: previewRefused },
      { op: 'get_context', respond: () => ({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, world, control, work, activeInput: null, recovery: null }) },
      { op: 'preview_point', respond: previewRefused },
    ]);
    const model = new ScriptedModel([
      { task: 'updates', output: { stage: 'position', changes: { person_a: { positionSet: { containerId: 'nonexistent_room', slotId: null, relativeTo: null } } } } as unknown as Json },
      { task: 'updates', output: { stage: 'appearance', changes: {} } as unknown as Json },
    ]);
    const driver = new ControllerDriver({ transport, model }, memory, { world, control, work });
    const status = await driver.run();
    // 非法候选按原有终态处理（重试预算耗尽 → error），绝不降级继续；
    // 外貌模型零调用、零跳过计数、零未决记录。
    // 有界重算（1 次刷新+1 次重试）后明确停止；外貌模型零调用。
    expect(status).toEqual({ kind: 'stop', reason: 'updates_preview_refused:version_mismatch' });
    expect(transport.ops.filter((op) => op === 'preview_point')).toHaveLength(2);
    expect(transport.ops.filter((op) => op === 'get_context')).toHaveLength(1);
    expect(model.calls.map((c) => c.key)).toEqual(['g1#position']);
    expect(memory.updatesPreviewSkipped).toBe(0);
    expect(memory.updatesApplied).toBe(0);
    expect(memory.updatesPendingRefs).toEqual([]);
  });
  test('#5 bounded stop: a forward reference with no later subtasks producer stops', async () => {
    const world = mkWorld({ head: { pointId: 'root', version: 0, stateDigest: 'd0', narrationStatus: 'ready' }, lease: { fenceEpoch: 1, expiresAtEpochMilli: 999999 }, activePointId: 'p1', activeRoundId: 'r1', advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: false } });
    const control = mkControl({ revision: 2 });
    const work = mkWork({ working: { cursor: 1, actedIds: ['person_a'], visitedIds: ['person_a'], settledUnitIds: [], intentStatus: 'consumed' } });
    const memory = initialMemory('req', 'browser');
    memory.leaseToken = 'lease1';
    memory.plan = [{ pointId: 'p1', kind: 'normal' as const, timeAdvance: ta(2), actorIds: ['person_a'] }];
    memory.groupActors = ['person_a'];
    memory.updatesStages = ['tasks', 'sanity']; // 无 subtasks 生产者
    memory.workingState = { key: workingStateKey(work), state: workingState() };
    const transport = new ScriptedTransport([]);
    const model = new ScriptedModel([
      { task: 'updates', output: { stage: 'tasks', changes: { person_a: { tasksAchieved: ['v13'] } } } as unknown as Json },
    ]);
    const driver = new ControllerDriver({ transport, model }, memory, { world, control, work });
    await driver.step(); // tasks 模型调用
    const status = await driver.step(); // 预检：悬挂引用无生产者 → 明确停止
    expect(status).toEqual({ kind: 'stop', reason: 'dangling_updates_refs:["person_a:v13"]' });
    expect(transport.ops).toEqual([]);
    expect(memory.updatesPreviewSkipped).toBe(0); // 未决延后不发生——直接停止
  });

  test('#5 time-scan split: the in-progress group rides the groupId-less candidates shape', async () => {
    // 时间扫描 tasks→subtasks：合成组必须走 groupId=null/actorIds=[] 的
    // 候选形状（wire 条件校验拒绝具名空组），且携带 tasksAchieved。
    const world = mkWorld({ head: { pointId: 'root', version: 0, stateDigest: 'd0', narrationStatus: 'ready' }, lease: { fenceEpoch: 1, expiresAtEpochMilli: 999999 }, activePointId: 'p1', activeRoundId: 'r1', advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: false } });
    const control = mkControl({ revision: 2 });
    const work = mkWork({ working: { cursor: 1, actedIds: ['person_a'], visitedIds: ['person_a'], settledUnitIds: [], intentStatus: 'consumed' } });
    const memory = initialMemory('req', 'browser');
    memory.leaseToken = 'lease1';
    memory.plan = [{ pointId: 'p1', kind: 'normal' as const, timeAdvance: ta(2), actorIds: ['person_a'] }];
    memory.groupActors = ['person_a'];
    memory.updatesStages = ['tasks', 'subtasks'];
    // t1 登记在状态任务表中——引用存活，preview 应携带在途组。
    memory.workingState = { key: workingStateKey(work), state: { ...workingState(), characters: { ...workingState().characters, person_a: { ...workingState().characters.person_a, tasks: { t1: { id: 't1', ownerId: 'person_a', parentTaskId: null, goal: '存活的任务', status: 'pending' } } } } } as never };
    const previewEnvelope = (state: unknown) => ({
      protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1,
      operation: 'preview_point', world, control, work,
      data: { pointId: 'p1', pointProjection: { worldId: 'w1', id: 'p1', sequence: 1, kind: 'normal', previousPointId: 'root', roundId: 'r1', advanceId: 'adv1', trigger: 'player', linkedFromPointId: null, timeAdvance: ta(2), entityDeltas: {} }, mergedEntityDeltas: {}, workingStateDigest: 'wsd', pointProjectionDigest: 'ppd', workingState: state },
    });
    const transport = new ScriptedTransport([
      { op: 'preview_point', respond: (r) => {
        const groups = (r as { settlementGroups: { groupId: string | null; actorIds: string[]; tasksAchieved: Record<string, string[]> }[] }).settlementGroups;
        const group = groups[0];
        if (group.groupId !== null || group.actorIds.length !== 0) throw new Error('time-scan in-progress group must be groupId-less with no actors');
        if (!group.tasksAchieved.person_a?.includes('t1')) throw new Error('time-scan in-progress group lost the tasks candidate');
        return previewEnvelope(workingState());
      } },
    ]);
    const model = new ScriptedModel([
      { task: 'updates', output: { stage: 'tasks', changes: { person_a: { tasksAchieved: ['t1'] } } } as unknown as Json },
      { task: 'updates', output: { stage: 'subtasks', changes: {} } as unknown as Json },
    ]);
    const driver = new ControllerDriver({ transport, model }, memory, { world, control, work });
    // 空点时间扫描路径：无计划 actor → 时间扫描分支。
    await driver.step(); // updates#tasks（时间扫描键；workingState 已种子化，无需前置 preview）
    await driver.step(); // read_working_state → 在途 preview
    await driver.step(); // updates#subtasks
    expect(transport.ops).toEqual(['preview_point']);
    expect(model.calls.map((c) => c.key)).toEqual(['time_scan:p1#tasks', 'time_scan:p1#subtasks']);
    expect(memory.updatesPreviewSkipped).toBe(0);
  });

  test('#5 forward task reference: a refused preview skips the boundary without retrying', async () => {
    // T03-collapse 语义：tasks 阶段的 v13 尚非状态事实——A 拒绝应用；
    // 阶梯跳过该边界（计数、不刷新重试），subtasks 读最后良好状态。
    const world = mkWorld({ head: { pointId: 'root', version: 0, stateDigest: 'd0', narrationStatus: 'ready' }, lease: { fenceEpoch: 1, expiresAtEpochMilli: 999999 }, activePointId: 'p1', activeRoundId: 'r1', advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: false } });
    const control = mkControl({ revision: 2 });
    const work = mkWork({ working: { cursor: 1, actedIds: ['person_a'], visitedIds: ['person_a'], settledUnitIds: [], intentStatus: 'consumed' } });
    const transport = new ScriptedTransport([
      // 预检在发送前延后：本边界零网络调用（apiResponse 留作反证——若到达即失败）。
    ]);
    const model = new ScriptedModel([
      { task: 'updates', output: { stage: 'tasks', changes: { person_a: { tasksAchieved: ['v13'] } } } as unknown as Json },
      { task: 'updates', output: { stage: 'subtasks', changes: {} } as unknown as Json },
    ]);
    const memory = initialMemory('req', 'browser');
    memory.leaseToken = 'lease1';
    memory.workingState = { key: workingStateKey(work), state: workingState() };
    memory.plan = [{ pointId: 'p1', kind: 'normal' as const, timeAdvance: ta(2), actorIds: ['person_a'] }];
    memory.groupActors = ['person_a'];
    memory.updatesStages = ['tasks', 'subtasks'];
    const driver = new ControllerDriver({ transport, model }, memory, { world, control, work });
    await driver.step(); // updates#tasks
    await driver.step(); // 预检发现前向引用 → 发送前延后（零网络调用）
    await driver.step(); // subtasks 照常发模型（读最后良好状态）
    expect(transport.ops).toEqual([]);
    expect(model.calls.map((c) => c.key)).toEqual(['time_scan:p1#tasks', 'time_scan:p1#subtasks']);
    expect(memory.updatesPreviewSkipped).toBe(1);
    expect(memory.updatesApplied).toBe(1);
    expect(memory.updatesPendingRefs).toEqual(['person_a:v13']);
    expect((model.calls[1].input as { workingState: { characters: Record<string, { tasks: Record<string, unknown> }> } }).workingState.characters.person_a.tasks).toEqual({}); // v13 不在状态中——未决，非已应用
  });

  test('#5 复审修正：未决引用只延后自身——同批有效变化照常应用（§6.3）', async () => {
    // tasks 阶段同批声明「已有任务 t1 达成＋未知任务 v13 引用」：t1 照常折入
    // 本边界 preview 应用，subtasks 阶段必须读到 t1=achieved；边界 preview
    // 绝不携带 v13（A 拒绝状态外引用）。v13 随最终结算批次出线（生产者声明
    // 已在 calls 里，checkUpdatesStages 的 produced 集合放行）。
    const world = mkWorld({ head: { pointId: 'root', version: 0, stateDigest: 'd0', narrationStatus: 'ready' }, lease: { fenceEpoch: 1, expiresAtEpochMilli: 999999 }, activePointId: 'p1', activeRoundId: 'r1', advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: false } });
    const control = mkControl({ revision: 2 });
    const work = mkWork({ working: { cursor: 1, actedIds: ['person_a'], visitedIds: ['person_a'], settledUnitIds: [], intentStatus: 'consumed' } });
    const taskOf = (id: string, status: 'pending' | 'achieved', parentTaskId: string | null) => ({ id, ownerId: 'person_a', parentTaskId, goal: `任务${id}`, status });
    const stateWithTasks = (tasks: Record<string, ReturnType<typeof taskOf>>) => ({ ...workingState(), characters: { ...workingState().characters, person_a: { ...workingState().characters.person_a, tasks } } });
    const previewEnvelope = (state: unknown) => ({
      protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1,
      operation: 'preview_point', world, control, work,
      data: { pointId: 'p1', pointProjection: { worldId: 'w1', id: 'p1', sequence: 1, kind: 'normal', previousPointId: 'root', roundId: 'r1', advanceId: 'adv1', trigger: 'player', linkedFromPointId: null, timeAdvance: ta(2), entityDeltas: {} }, mergedEntityDeltas: {}, workingStateDigest: 'wsd', pointProjectionDigest: 'ppd', workingState: state },
    });
    const transport = new ScriptedTransport([
      { op: 'preview_point', respond: (r) => {
        const achieved = (r as { settlementGroups: { tasksAchieved: Record<string, string[]> }[] }).settlementGroups[0].tasksAchieved.person_a ?? [];
        if (JSON.stringify(achieved) !== JSON.stringify(['t1'])) throw new Error(`boundary preview must carry only the valid part, got ${JSON.stringify(achieved)}`);
        return previewEnvelope(stateWithTasks({ t1: taskOf('t1', 'achieved', null) }));
      } },
      { op: 'checkpoint_stage_time_scan', respond: (r) => ({
        protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1,
        replayed: false, operation: 'checkpoint_stage_time_scan', requestId: (r as { requestId: Id }).requestId, requestHash: 'hash', world, control, work, data: {},
      }) },
    ]);
    const model = new ScriptedModel([
      { task: 'updates', output: { stage: 'tasks', changes: { person_a: { tasksAchieved: ['t1', 'v13'] } } } as unknown as Json },
      { task: 'updates', output: { stage: 'subtasks', changes: { person_a: { subtasksAdded: [{ id: 'v13', ownerId: 'person_a', parentTaskId: 't1', goal: '任务v13', status: 'pending' }] } } } as unknown as Json },
    ]);
    const memory = initialMemory('req', 'browser');
    memory.leaseToken = 'lease1';
    memory.workingState = { key: workingStateKey(work), state: stateWithTasks({ t1: taskOf('t1', 'pending', null) }) as never };
    memory.plan = [{ pointId: 'p1', kind: 'normal' as const, timeAdvance: ta(2), actorIds: ['person_a'] }];
    memory.groupActors = ['person_a'];
    memory.updatesStages = ['tasks', 'subtasks'];
    const driver = new ControllerDriver({ transport, model }, memory, { world, control, work });
    await driver.step(); // updates#tasks
    expect(memory.updatesPendingRefs).toEqual([]);
    await driver.step(); // 边界 1：拆分——只应用 t1，v13 记为未决（零额外候选）
    expect(memory.updatesPendingRefs).toEqual(['person_a:v13']);
    expect(memory.updatesPreviewSkipped).toBe(0); // 应用了有效部分——不是跳过
    expect(memory.updatesApplied).toBe(1);
    await driver.step(); // subtasks 模型（读 t1=achieved 的状态——§6.3）
    await driver.step(); // 最终批次：v13 达成＋生产同批出线
    expect(transport.ops).toEqual(['preview_point', 'checkpoint_stage_time_scan']);
    const subtasksInput = model.calls[1].input as { workingState: { characters: Record<string, { tasks: Record<string, { status: string }> }> } };
    expect(subtasksInput.workingState.characters.person_a.tasks.t1.status).toBe('achieved');
    const stageReq = transport.requests[1] as { candidates: { tasksAchieved: Record<string, string[]>; subtasksAdded: Record<string, { id: string }[]> } };
    expect(stageReq.candidates.tasksAchieved.person_a).toEqual(['t1', 'v13']);
    expect(stageReq.candidates.subtasksAdded.person_a.map((t) => t.id)).toEqual(['v13']);
    expect(memory.updatesPendingRefs).toEqual([]); // 随结算批次落定——未决清零
    expect(memory.updatesApplied).toBe(0); // 阶梯已被 stage_time_scan 消费
  });

  test('#5 复审修正：无生产者的悬挂引用即使同批有可达变化也立即停止', async () => {
    // updatesStages=['tasks','sanity']：v13 既无剩余生产者、也已生产集中无主，
    // 明确停止（模型契约违约，快速失败、零网络调用）；停止原因携带引用。
    const world = mkWorld({ head: { pointId: 'root', version: 0, stateDigest: 'd0', narrationStatus: 'ready' }, lease: { fenceEpoch: 1, expiresAtEpochMilli: 999999 }, activePointId: 'p1', activeRoundId: 'r1', advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: false } });
    const control = mkControl({ revision: 2 });
    const work = mkWork({ working: { cursor: 1, actedIds: ['person_a'], visitedIds: ['person_a'], settledUnitIds: [], intentStatus: 'consumed' } });
    const seeded = () => ({ ...workingState(), characters: { ...workingState().characters, person_a: { ...workingState().characters.person_a, tasks: { t1: { id: 't1', ownerId: 'person_a', parentTaskId: null, goal: '已有任务', status: 'pending' as const } } } } });
    const transport = new ScriptedTransport([]);
    const model = new ScriptedModel([
      { task: 'updates', output: { stage: 'tasks', changes: { person_a: { tasksAchieved: ['t1', 'v13'] } } } as unknown as Json },
    ]);
    const memory = initialMemory('req', 'browser');
    memory.leaseToken = 'lease1';
    memory.workingState = { key: workingStateKey(work), state: seeded() as never };
    memory.plan = [{ pointId: 'p1', kind: 'normal' as const, timeAdvance: ta(2), actorIds: ['person_a'] }];
    memory.groupActors = ['person_a'];
    memory.updatesStages = ['tasks', 'sanity'];
    const driver = new ControllerDriver({ transport, model }, memory, { world, control, work });
    await driver.step(); // updates#tasks
    const status = await driver.step(); // 预检：悬挂引用无生产者 → 明确停止
    expect(status).toEqual({ kind: 'stop', reason: 'dangling_updates_refs:["person_a:v13"]' });
    expect(transport.ops).toEqual([]);
    expect(memory.updatesPreviewSkipped).toBe(0);
    expect(memory.updatesPendingRefs).toEqual(['person_a:v13']);
  });

  test('#5 复审修正：preview 刷新后采纳新上下文再重试（绑定新 revision）', async () => {
    // 首次 preview 遭 version_mismatch(refresh_context)：get_context 回包
    // （revision 7）必须写回控制器状态，重试绑定 expectedCheckpointRevision=7
    // ——而不是拿旧 revision 5 原样重发、再吃一次拒绝（v3 复测 stale_revision）。
    const world = mkWorld({ head: { pointId: 'root', version: 0, stateDigest: 'd0', narrationStatus: 'ready' }, lease: { fenceEpoch: 1, expiresAtEpochMilli: 999999 }, activePointId: 'p1', activeRoundId: 'r1', advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: false } });
    const control = mkControl({ revision: 5 });
    const refreshedControl = mkControl({ revision: 7 });
    const work = mkWork({ timeLocked: true, phase: 'settle_group', pendingGroup: { groupId: 'g1', sourceId: 'person_a', memberIds: ['person_a'], targetIds: [], frontierIds: [], closed: true } });
    const memory = initialMemory('req', 'browser');
    memory.leaseToken = 'lease1';
    memory.workingState = { key: workingStateKey(work), state: workingState() };
    memory.lastResults = { person_a: '结果。' };
    memory.updatesStages = ['position', 'appearance'];
    const previewEnvelope = () => ({
      protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1,
      operation: 'preview_point', world, control: refreshedControl, work,
      data: { pointId: 'p1', pointProjection: { worldId: 'w1', id: 'p1', sequence: 1, kind: 'normal', previousPointId: 'root', roundId: 'r1', advanceId: 'adv1', trigger: 'player', linkedFromPointId: null, timeAdvance: ta(2), entityDeltas: {} }, mergedEntityDeltas: {}, workingStateDigest: 'wsd', pointProjectionDigest: 'ppd', workingState: workingState() },
    });
    const transport = new ScriptedTransport([
      { op: 'preview_point', respond: () => { throw apiError('version_mismatch', 'req'); } },
      { op: 'get_context', respond: () => ({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, world, control: refreshedControl, work, activeInput: null, recovery: null }) },
      { op: 'preview_point', respond: (r) => {
        if ((r as { expectedCheckpointRevision: number }).expectedCheckpointRevision !== 7) throw new Error('retry must bind the refreshed checkpoint revision');
        return previewEnvelope();
      } },
    ]);
    const model = new ScriptedModel([
      { task: 'updates', output: { stage: 'position', changes: { person_a: { positionSet: { containerId: 'hall', slotId: null, relativeTo: null } } } } as unknown as Json },
    ]);
    const driver = new ControllerDriver({ transport, model }, memory, { world, control, work });
    await driver.step(); // updates#position
    await driver.step(); // 拒绝 → 刷新（采纳 revision 7）→ 重试成功
    expect(transport.ops).toEqual(['preview_point', 'get_context', 'preview_point']);
    expect(memory.updatesApplied).toBe(1);
    expect(memory.updatesPendingRefs).toEqual([]);
  });

  test('#5 复审修正：刷新后工作基线迁移则明确停止，不重试', async () => {
    // get_context 回包指向另一个 head 点：旧点位的在途候选绝不发往新点位，
    // 以 updates_preview_baseline_moved 停止（第二次 preview 不发生）。
    const world = mkWorld({ head: { pointId: 'root', version: 0, stateDigest: 'd0', narrationStatus: 'ready' }, lease: { fenceEpoch: 1, expiresAtEpochMilli: 999999 }, activePointId: 'p1', activeRoundId: 'r1', advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: false } });
    const control = mkControl({ revision: 5 });
    const movedWorld = mkWorld({ head: { pointId: 'p2', version: 9, stateDigest: 'd9', narrationStatus: 'ready' }, lease: { fenceEpoch: 2, expiresAtEpochMilli: 999999 }, activePointId: 'p2', activeRoundId: 'r1', advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: false } });
    const movedWork = mkWork({ pointId: 'p2' });
    const work = mkWork({ timeLocked: true, phase: 'settle_group', pendingGroup: { groupId: 'g1', sourceId: 'person_a', memberIds: ['person_a'], targetIds: [], frontierIds: [], closed: true } });
    const memory = initialMemory('req', 'browser');
    memory.leaseToken = 'lease1';
    memory.workingState = { key: workingStateKey(work), state: workingState() };
    memory.lastResults = { person_a: '结果。' };
    memory.updatesStages = ['position', 'appearance'];
    const transport = new ScriptedTransport([
      { op: 'preview_point', respond: () => { throw apiError('version_mismatch', 'req'); } },
      { op: 'get_context', respond: () => ({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, world: movedWorld, control: mkControl({ revision: 8 }), work: movedWork, activeInput: null, recovery: null }) },
    ]);
    const model = new ScriptedModel([
      { task: 'updates', output: { stage: 'position', changes: { person_a: { positionSet: { containerId: 'hall', slotId: null, relativeTo: null } } } } as unknown as Json },
    ]);
    const driver = new ControllerDriver({ transport, model }, memory, { world, control, work });
    await driver.step(); // updates#position
    const status = await driver.step(); // 刷新后基线已迁移 → 明确停止
    expect(status).toEqual({ kind: 'stop', reason: 'updates_preview_baseline_moved:root->p2' });
    expect(transport.ops).toEqual(['preview_point', 'get_context']);
    expect(memory.updatesApplied).toBe(0);
  });

  test('#5 forced split: appearance reads the preview state with the new position applied', async () => {
    // 位置影响外貌（§11.2 强制拆分反例）：阶段 1 移动 person_a，阶段 2 的
    // 外貌判断必须读取 Python preview 应用新位置后的状态——输入里没有
    // priorStages/appliedDelta 让模型自己心算。
    const world = mkWorld({ head: { pointId: 'root', version: 0, stateDigest: 'd0', narrationStatus: 'ready' }, lease: { fenceEpoch: 1, expiresAtEpochMilli: 999999 }, activePointId: 'p1', activeRoundId: 'r1', advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: false } });
    const control = mkControl({ revision: 2 });
    const work = mkWork({ timeLocked: true, phase: 'settle_group', pendingGroup: { groupId: 'g1', sourceId: 'person_a', memberIds: ['person_a'], targetIds: [], frontierIds: [], closed: true } });
    const memory = initialMemory('req', 'browser');
    memory.leaseToken = 'lease1';
    memory.workingState = { key: workingStateKey(work), state: workingState() };
    memory.lastResults = { person_a: '结果。' };
    memory.updatesStages = ['position', 'appearance'];
    const movedState = () => ({ ...workingState(), characters: { ...workingState().characters, person_a: { ...workingState().characters.person_a, position: { containerId: 'hall', slotId: null, relativeTo: null } } } });
    const previewEnvelope = (state: unknown) => ({
      protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1,
      operation: 'preview_point', world, control, work,
      data: { pointId: 'p1', pointProjection: { worldId: 'w1', id: 'p1', sequence: 1, kind: 'normal', previousPointId: 'root', roundId: 'r1', advanceId: 'adv1', trigger: 'player', linkedFromPointId: null, timeAdvance: ta(2), entityDeltas: {} }, mergedEntityDeltas: {}, workingStateDigest: 'wsd', pointProjectionDigest: 'ppd', workingState: state },
    });
    const transport = new ScriptedTransport([
      { op: 'preview_point', respond: (r) => {
        // 合成在途组必须携带阶段 1 的位置候选。
        const groups = (r as { settlementGroups: { actorIds: string[]; positions: Record<string, { containerId: string }> }[] }).settlementGroups;
        if (!groups.some((g) => g.positions?.person_a?.containerId === 'hall')) throw new Error('preview request lacks the in-progress position candidate');
        return previewEnvelope(movedState());
      } },
      { op: 'checkpoint_stage_unit', respond: (r) => writeOkLocal2('checkpoint_stage_unit', r, { groupId: 'g1', unitId: 'u1', working: work.working }) },
    ]);
    const model = new ScriptedModel([
      { task: 'updates', output: { stage: 'position', changes: { person_a: { positionSet: { containerId: 'hall', slotId: null, relativeTo: null } } } } as unknown as Json },
      { task: 'updates', output: { stage: 'appearance', changes: {} } as unknown as Json },
    ]);
    const writeOkLocal2 = (operation: WorldOperation, request: unknown, data: unknown) => ({
      protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1,
      replayed: false, operation, requestId: (request as { requestId?: Id }).requestId ?? 'req', requestHash: 'hash', world, control, work, data,
    });
    const driver = new ControllerDriver({ transport, model }, memory, { world, control, work });
    // 只驱动到阶段 2 读取完成（阶段1模型 → preview → 阶段2模型）；
    // stage_unit 之后的收尾级联不属于本用例。
    await driver.step();
    await driver.step();
    await driver.step();
    expect(transport.ops).toEqual(['preview_point']);
    // 阶段 2 的输入=应用新位置后的状态；无 priorStages/appliedDelta。
    const appearanceCall = model.calls[1];
    expect(appearanceCall.key).toBe('g1#appearance');
    expect((appearanceCall.input as { workingState: { characters: Record<string, { position: { containerId: string } }> } }).workingState.characters.person_a.position.containerId).toBe('hall');
    expect(appearanceCall.input).not.toHaveProperty('priorStages');
    expect(appearanceCall.input).not.toHaveProperty('appliedDelta');
  });

  test('#6 cold start: a fresh controller assembles narration purely from server reads', async () => {
    // 全新控制器：memory.narration 为空；claim 后阶梯自行读取目标点（含
    // 原始 Δ）与前驱状态；模型输入与独立手写字面量一致。
    let world = mkWorld({ head: { pointId: 'p1', version: 1, stateDigest: 'd1', narrationStatus: 'pending' }, lease: { fenceEpoch: 3, expiresAtEpochMilli: 999999 }, activePointId: 'p1', activeRoundId: 'r1', advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: false } });
    const control = mkControl({ revision: 5, phase: 'complete' });
    const beforeState = { ...workingState(), time: { calendar: 'gregorian' as const, dateTime: '2026-01-01T11:59:00', instantOrdinal: 0 } };
    const afterState = { ...workingState(), time: { calendar: 'gregorian' as const, dateTime: '2026-01-01T12:01:00', instantOrdinal: 0 }, characters: { ...workingState().characters, person_a: { ...workingState().characters.person_a, position: { containerId: 'hall', slotId: null, relativeTo: null } } } };
    const delta = { timeAdvance: ta(2), entityDeltas: { person_a: { entityId: 'person_a', positionSet: { containerId: 'hall', slotId: null, relativeTo: null } } } };
    const stateOk = (pointId: Id, previousPointId: Id | null, timeAdvance: TimeAdvance | null, entityDeltas: Record<string, unknown>, state: unknown) => ({
      protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1,
      world, control,
      data: { pointId, version: pointId === 'root' ? 0 : 1, state, stateDigest: pointId === 'root' ? 'd0' : 'd1', previousPointId, timeAdvance, entityDeltas },
    });
    const writeOkLocal = (operation: WorldOperation, request: unknown, data: unknown) => ({
      protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1,
      replayed: false, operation, requestId: (request as { requestId?: Id }).requestId ?? 'req', requestHash: 'hash', world, control, work: null, data,
    });
    const transport = new ScriptedTransport([
      { op: 'narration_claim', respond: (r) => writeOkLocal('narration_claim', r, { pointId: 'p1', mode: 'head', generation: 1, fenceEpoch: 3, issuedAtEpochMilli: 3, expiresAtEpochMilli: 4, claimToken: 'ct_cold' }) },
      { op: 'get_state', respond: () => stateOk('p1', 'root', ta(2), delta.entityDeltas, afterState) },
      { op: 'get_state', respond: () => stateOk('root', null, null, {}, beforeState) },
      { op: 'narration_submit', respond: (r) => { world = { ...world, head: { ...world.head, narrationStatus: 'ready' as const } }; return writeOkLocal('narration_submit', r, { pointId: 'p1', narrationStatus: 'ready', generation: 1 }); } },
    ]);
    const model = new ScriptedModel([{ task: 'narration', output: '冷启动叙事。' }]);
    const driver = new ControllerDriver({ transport, model }, memoryWithAdvanceStart({ leaseToken: 'lease1' }), { world, control });
    const status = await driver.run();
    expect(status).toEqual({ kind: 'stop', reason: 'world_complete' });
    expect(transport.ops).toEqual(['narration_claim', 'get_state', 'get_state', 'narration_submit']);
    expect((transport.requests[1] as { point: string }).point).toBe('p1');
    expect((transport.requests[2] as { point: string }).point).toBe('root');
    // 独立字面量（不经 assembleNarrationInput）：before/after 确实不同。
    expect(model.calls[0].input).toEqual({
      pointId: 'p1', before: beforeState, delta, after: afterState,
      perspective: '主角视角（person_a「甲」）；只表达已结算的世界事实',
    });
    expect(driver.getMemory().narration).toBeNull();
  });

  test('#8 regression: per-source trigger keys through real allocate→extend (overlap, timeout retry, no clobber)', async () => {
    // 真实控制器走 allocate_ids → extend_group：来源 person_c 声明目标
    // [person_d, person_e]；person_d 的键已由另一来源 person_a 持有
    // （历史证据种子）——不同来源同一目标各占各槽，互不复用不覆盖。
    const world = mkWorld({ head: { pointId: 'root', version: 0, stateDigest: 'd0', narrationStatus: 'ready' }, lease: { fenceEpoch: 2, expiresAtEpochMilli: 999999 }, activePointId: 'p1', activeRoundId: 'r1', advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: false } });
    const control = mkControl({ revision: 3 });
    const work = mkWork({ phase: 'build_group', timeLocked: true, pendingGroup: { groupId: 'g1', sourceId: 'person_c', memberIds: ['person_c'], targetIds: [], frontierIds: [], closed: false } });
    const memory = initialMemory('req', 'browser');
    memory.leaseToken = 'lease1';
    memory.workingState = { key: workingStateKey(work), state: workingState() };
    memory.sources = [{ sourceId: 'person_c', actionText: '行动。', targetsExtended: false, pendingTargets: [], rolled: [] }];
    memory.ids = { [triggerSlotKey('g1', 'person_a', 'person_d')]: 'tk_a_d' };
    memory.lastTargets = { sourceId: 'person_c', targets: ['person_d', 'person_e'] };
    const writeOk = (operation: WorldOperation, request: unknown, data: unknown) => ({
      protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1,
      replayed: false, operation, requestId: (request as { requestId: Id }).requestId, requestHash: 'hash', world, control, work, data,
    });
    let timeouts = 0;
    const transport = new ScriptedTransport([
      // 首次分配响应丢失（超时）→ 同请求重试 → 服务端按 allocationKey 幂等
      // 返回同键；只请求本来源缺失的槽位，他人的 person_a→person_d 键不进请求。
      { op: 'allocate_ids', respond: () => { timeouts += 1; throw new WorldTimeoutError('response lost'); } },
      { op: 'allocate_ids', respond: (r) => writeOk('allocate_ids', r, { allocations: [{ slotKey: triggerSlotKey('g1', 'person_c', 'person_d'), id: 'tk_c_d' }, { slotKey: triggerSlotKey('g1', 'person_c', 'person_e'), id: 'tk_c_e' }] }) },
      { op: 'checkpoint_extend_group', respond: (r) => writeOk('checkpoint_extend_group', r, { groupId: 'g1', memberIds: ['person_c'], frontierIds: [] }) },
    ]);
    const driver = new ControllerDriver({ transport, model: new ScriptedModel([]) }, memory, { world, control, work });
    await driver.step(); // allocate_ids：超时 + 同请求重试成功，同一步内完成
    await driver.step(); // extend_group
    expect(transport.ops).toEqual(['allocate_ids', 'allocate_ids', 'checkpoint_extend_group']);
    const first = transport.requests[0] as Record<string, unknown>;
    const retry = transport.requests[1] as Record<string, unknown>;
    expect(retry).toEqual(first); // 超时重试逐字节复用同一请求（同 requestId 同槽位）
    expect(first).toMatchObject({
      allocationKey: triggerAllocationKey('g1', 'person_c'),
      slots: [
        { slotKey: triggerSlotKey('g1', 'person_c', 'person_d'), kind: 'trigger' },
        { slotKey: triggerSlotKey('g1', 'person_c', 'person_e'), kind: 'trigger' },
      ],
    });
    const extend = transport.requests[2] as { groupId: Id; targets: { targetId: Id; triggerKey: Id }[] };
    expect(extend.groupId).toBe('g1');
    expect(extend.targets).toEqual([
      { targetId: 'person_d', triggerKey: 'tk_c_d' },
      { targetId: 'person_e', triggerKey: 'tk_c_e' },
    ]);
    const committed = driver.getMemory();
    // 无覆盖：他人来源（person_a→person_d）的历史键原样保留；本来源两个键
    // 落位；目标集已消费。
    expect(committed.ids).toMatchObject({
      [triggerSlotKey('g1', 'person_c', 'person_d')]: 'tk_c_d',
      [triggerSlotKey('g1', 'person_c', 'person_e')]: 'tk_c_e',
      [triggerSlotKey('g1', 'person_a', 'person_d')]: 'tk_a_d',
    });
    expect(committed.sources[0]).toMatchObject({ targetsExtended: true });
    expect(committed.lastTargets).toBeNull();
    expect(timeouts).toBe(1);
  });
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
    // 组装阶梯：claim 后的根点读取（叙事只述已提交事实；前驱 root 免读 before）。
    const readEntry = (pointId: Id, previousPointId: Id | null = 'root', timeAdvance: TimeAdvance | null = ta(60)) => ({
      op: 'get_state' as WorldOperation,
      respond: () => ({
      protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1,
      world, control,
      data: { pointId, version: 0, state: workingState(), stateDigest: 'd0', previousPointId, timeAdvance, entityDeltas: {} },
      }),
    });
    const transport = new ScriptedTransport([
      previewEntry(), scanEntry(), previewEntry(), sealEntry(), commitEntry('dp0'),
      claimEntry(), readEntry('p0'), readEntry('root', null, null), submitEntry(),
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
      claimEntry(), readEntry('p1'), readEntry('root', null, null), submitEntry(),
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
      { op: 'get_state', respond: () => ({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, world, control, data: { pointId: 'p1', version: 1, state: workingState(), stateDigest: 'd1', previousPointId: null, timeAdvance: null, entityDeltas: {} } }) },
      { op: 'narration_submit', respond: (r) => ({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation: 'narration_submit', requestId: (r as { requestId: Id }).requestId, requestHash: 'hash', world: { ...world, head: { ...world.head, narrationStatus: 'ready' } }, control, work: null, data: { pointId: 'p1', narrationStatus: 'ready', generation: 2 } }) },
    ]);
    const model = new ScriptedModel([{ task: 'narration', output: '重生成叙事。' }]);
    const memory = memoryWithAdvanceStart({
      narration: { pointId: 'p1', claim: { claimToken: 'ct_old', generation: 1, issuedAtEpochMilli: 1 }, input: { pointId: 'p1', after: null, delta: null, previousPointId: null, before: null } },
      lastModel: { task: 'narration', key: 'p1', output: '旧文本。' },
    });
    const driver = new ControllerDriver({ transport, model }, memory, { world, control });
    await driver.step();
    expect(driver.getMemory().narration).toMatchObject({ pointId: 'p1', claim: null });
    expect(driver.getMemory().lastModel).toBeNull();
    await driver.step();
    await driver.step();
    await driver.step();
    await driver.step(); // 组装读取
    expect(transport.ops).toEqual(['narration_submit', 'narration_claim', 'get_state', 'narration_submit']);
    expect((transport.requests[3] as { claimToken: Id }).claimToken).toBe('ct_new');
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
    const control = mkControl({ revision: 3 });
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

describe('review regressions round 2 (18714a3 findings)', () => {
  test('recovery chains share the retry budget; a held lease waits instead of looping', async () => {
    let staleCalls = 0;
    const staleTransport: WorldTransport = { async execute(operation, request) { staleCalls++; void operation; throw apiError('stale_epoch', (request as { requestId?: Id })?.requestId ?? 'req'); } };
    const driver1 = new ControllerDriver({ transport: staleTransport, model: new ScriptedModel([]) }, memoryWithAdvanceStart(), { world: mkWorld(), control: mkControl() }, { retryLimit: 1 });
    const status1 = await driver1.run(1);
    expect(staleCalls).toBe(2);
    expect(status1).toEqual({ kind: 'error', detail: expect.stringContaining('recovery limit') });

    let heldCalls = 0;
    const heldError = new WorldApiError({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation: null, requestId: 'req', worldId: 'w1', error: { code: 'lease_invalid', httpStatus: 409, retryable: false, clientAction: 'reacquire_lease', details: { reason: 'lease_held' } } });
    const heldTransport: WorldTransport = { async execute(operation, request) {
      heldCalls++;
      if (operation === 'lease_acquire') throw heldError;
      throw apiError('stale_epoch', (request as { requestId?: Id })?.requestId ?? 'req');
    } };
    const driver2 = new ControllerDriver({ transport: heldTransport, model: new ScriptedModel([]) }, memoryWithAdvanceStart(), { world: mkWorld(), control: mkControl() });
    const status2 = await driver2.run(1);
    expect(heldCalls).toBe(2);
    expect(status2).toEqual({ kind: 'await', reason: 'lease_held_by_other' });
  });

  test('a command delivered while a request is in flight is not lost', async () => {
    const ops: WorldOperation[] = [];
    let release: ((value: unknown) => void) | null = null;
    const world = mkWorld();
    const control = mkControl();
    const transport: WorldTransport = { async execute(operation) {
      ops.push(operation);
      if (operation === 'checkpoint_start_advance') return new Promise((resolve) => { release = resolve as (value: unknown) => void; });
      return { protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation, requestId: 'x', requestHash: 'hash', world: mkWorld({ advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: false }, activeRoundId: 'r1', round: { roundId: 'r1', trigger: 'player', order: ORDER, cursor: 0, actedIds: [], visitedIds: [], conclusion: null } }), control: mkControl({ paused: true, revision: 2 }), work: null, data: { paused: true } } as never;
    } };
    const driver = new ControllerDriver({ transport, model: new ScriptedModel([]) }, memoryWithAdvanceStart(), { world, control });
    const inFlight = driver.step();
    driver.deliver({ kind: 'pause' });
    release!({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation: 'checkpoint_start_advance', requestId: 'x', requestHash: 'hash', world: mkWorld({ advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: false }, activeRoundId: 'r1', round: { roundId: 'r1', trigger: 'player', order: ORDER, cursor: 0, actedIds: [], visitedIds: [], conclusion: null } }), control: mkControl({ revision: 1 }), work: null, data: { advanceId: 'adv1', inputId: 'in1', roundId: 'r1' } });
    await inFlight;
    await driver.step();
    expect(ops).toEqual(['checkpoint_start_advance', 'checkpoint_pause']);
    expect(await driver.step()).toEqual({ kind: 'await', reason: 'paused_externally' });
  });

  test('claim_fenced refreshes context, drops the stale claim, and re-claims', async () => {
    const world = mkWorld({ head: { pointId: 'p1', version: 1, stateDigest: 'd1', narrationStatus: 'pending' } });
    const control = mkControl({ revision: 13 });
    const transport = new ScriptedTransport([
      { op: 'narration_submit', respond: (r) => apiError('claim_fenced', (r as { requestId?: Id })?.requestId ?? 'req') },
      { op: 'get_context', respond: () => ({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, world, control: mkControl({ revision: 14 }), work: null, activeInput: null, recovery: null }) },
      { op: 'narration_claim', respond: (r) => ({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation: 'narration_claim', requestId: (r as { requestId: Id }).requestId, requestHash: 'hash', world, control, work: null, data: { pointId: 'p1', mode: 'head', generation: 2, fenceEpoch: 1, issuedAtEpochMilli: 9, expiresAtEpochMilli: 10, claimToken: 'ct_new' } }) },
      { op: 'get_state', respond: () => ({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, world, control, data: { pointId: 'p1', version: 1, state: workingState(), stateDigest: 'd1', previousPointId: null, timeAdvance: null, entityDeltas: {} } }) },
      { op: 'narration_submit', respond: (r) => ({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation: 'narration_submit', requestId: (r as { requestId: Id }).requestId, requestHash: 'hash', world: { ...world, head: { ...world.head, narrationStatus: 'ready' } }, control, work: null, data: { pointId: 'p1', narrationStatus: 'ready', generation: 2 } }) },
    ]);
    const model = new ScriptedModel([{ task: 'narration', output: '新叙事。' }]);
    const memory = memoryWithAdvanceStart({
      narration: { pointId: 'p1', claim: { claimToken: 'ct_old', generation: 1, issuedAtEpochMilli: 1 }, input: { pointId: 'p1', after: null, delta: null, previousPointId: null, before: null } },
      lastModel: { task: 'narration', key: 'p1', output: '旧文本。' },
    });
    const driver = new ControllerDriver({ transport, model }, memory, { world, control });
    await driver.step(); // submit fenced → refresh_context drops the stale claim
    expect(driver.getMemory().narration).toMatchObject({ pointId: 'p1', claim: null });
    await driver.step(); // claim ct_new
    await driver.step(); // 组装读取（§7.1 阶梯）
    await driver.step(); // model narration
    await driver.step(); // submit with ct_new
    expect(transport.ops).toEqual(['narration_submit', 'get_context', 'narration_claim', 'get_state', 'narration_submit']);
    expect((transport.requests[4] as { claimToken: Id }).claimToken).toBe('ct_new');
    expect(model.calls.length).toBe(1);
    expect(driver.getMemory().narration).toBeNull();
  });

  test('a lease epoch change invalidates a held narration claim', async () => {
    const world = mkWorld({ head: { pointId: 'p1', version: 1, stateDigest: 'd1', narrationStatus: 'pending' }, advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: false }, activeRoundId: 'r1', activePointId: 'p1', round: { roundId: 'r1', trigger: 'player', order: ORDER, cursor: 0, actedIds: [], visitedIds: [], conclusion: null } });
    const control = mkControl({ revision: 4 });
    const work = mkWork();
    const transport = new ScriptedTransport([
      { op: 'checkpoint_pause', respond: (r) => ({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation: 'checkpoint_pause', requestId: (r as { requestId: Id }).requestId, requestHash: 'hash', world: { ...world, lease: { fenceEpoch: 2, expiresAtEpochMilli: 9 } }, control: mkControl({ paused: true, revision: 5 }), work, data: { paused: true } }) },
      { op: 'narration_claim', respond: (r) => ({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation: 'narration_claim', requestId: (r as { requestId: Id }).requestId, requestHash: 'hash', world, control: mkControl({ paused: true, revision: 6 }), work, data: { pointId: 'p1', mode: 'head', generation: 2, fenceEpoch: 2, issuedAtEpochMilli: 20, expiresAtEpochMilli: 30, claimToken: 'ct_fresh' } }) },
    ]);
    const memory = memoryWithAdvanceStart({
      narration: { pointId: 'p1', claim: { claimToken: 'ct_old', generation: 1, issuedAtEpochMilli: 1 }, input: { pointId: 'p1', after: null, delta: null, previousPointId: null, before: null } },
    });
    const driver = new ControllerDriver({ transport, model: new ScriptedModel([]) }, memory, { world, control, work });
    driver.deliver({ kind: 'pause' });
    await driver.step(); // pause response carries a new lease generation
    expect(driver.getMemory().narration).toMatchObject({ pointId: 'p1', claim: null });
    await driver.step(); // pending narration re-claims even while paused
    expect(transport.ops).toEqual(['checkpoint_pause', 'narration_claim']);
  });
});

describe('automatic round entry', () => {
  test('continue retires the old plan and allocates the new round slots before pointPlan', async () => {
    const player = mkWorld({ advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: true }, activeRoundId: 'r1', round: { roundId: 'r1', trigger: 'player', order: ORDER, cursor: 6, actedIds: ['person_a'], visitedIds: ORDER, conclusion: null } });
    const automatic = { ...player, activeRoundId: 'r2', round: { roundId: 'r2', trigger: 'automatic' as const, order: ['person_c'], cursor: 0, actedIds: [], visitedIds: [], conclusion: null } };
    const transport = new ScriptedTransport([
      { op: 'round_conclusion_conclude', respond: () => ({ world: automatic, control: mkControl({ revision: 1 }), work: null, data: { kind: 'continue', roundId: 'r1', nextRoundId: 'r2' } }) },
      { op: 'allocate_ids', respond: () => ({ world: automatic, control: mkControl({ revision: 1 }), work: null, data: { allocations: [{ slotKey: 'point', id: 'p2' }, { slotKey: 'group', id: 'g2' }] } }) },
    ]);
    const model = new ScriptedModel([{ task: 'pointPlan', output: [{ pointId: 'p2', kind: 'normal', timeAdvance: ta(2), actorIds: ['person_c'] }] as unknown as Json }]);
    const memory = memoryWithAdvanceStart({
      playerInput: null, ids: { point: 'old_point', 'group:person_c': 'old_group' },
      plan: [{ pointId: 'old_point', kind: 'normal', timeAdvance: ta(1), actorIds: ['person_a'] }], planIndex: 1,
      continuation: { kind: 'continue', closedBy: 'model', cancelReason: null, candidateCharacterIds: ['person_c'], nextRoundId: 'r2' },
      roundAllocations: { r2: { allocationKey: 'r2_slots', slots: [{ slotKey: 'point', kind: 'point', scope: 'r2' }, { slotKey: 'group', kind: 'group', scope: 'r2' }] } },
    });
    const driver = new ControllerDriver({ transport, model }, memory, { world: player, control: mkControl({ phase: 'assess_continuation' }) }, { identityAliases: { 'group:person_c': 'group' } });
    await driver.step();
    expect(driver.getMemory()).toMatchObject({ plan: null, planIndex: 0, continuation: null });
    await driver.step();
    expect(transport.ops).toEqual(['round_conclusion_conclude', 'allocate_ids']);
    expect(model.calls).toEqual([]);
    expect(driver.getMemory()).toMatchObject({ ids: { point: 'p2', 'group:person_c': 'g2' }, allocatedKeys: ['r2_slots'] });
    await driver.step();
    expect(model.calls).toMatchObject([{ task: 'pointPlan', key: 'r2' }]);
    expect(driver.pendingDecision()).toMatchObject({ kind: 'transport', operation: 'checkpoint_begin_point', request: { pointId: 'p2' } });
  });
});

describe('review regressions round 3 (bb5abd3 findings)', () => {
  test('a command delivered during a request survives a resolve_gate followup', async () => {
    const ops: WorldOperation[] = [];
    let rejectStart: ((error: unknown) => void) | null = null;
    const world = mkWorld();
    const control = mkControl();
    const pausedError = new WorldApiError({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation: null, requestId: 'req', worldId: 'w1', control: mkControl({ paused: true, revision: 1 }), error: { code: 'paused', httpStatus: 409, retryable: false, clientAction: 'resolve_gate', details: {} } });
    const transport: WorldTransport = { async execute(operation) {
      ops.push(operation);
      if (operation === 'checkpoint_start_advance') return new Promise((_, reject) => { rejectStart = reject; });
      return { protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation, requestId: 'x', requestHash: 'hash', world, control: mkControl({ paused: false, revision: 2 }), work: null, data: { paused: false } } as never;
    } };
    const driver = new ControllerDriver({ transport, model: new ScriptedModel([]) }, memoryWithAdvanceStart(), { world, control });
    const inFlight = driver.step();
    driver.deliver({ kind: 'resume' });
    rejectStart!(pausedError);
    await inFlight;
    expect(await driver.step()).toBeUndefined(); // checkpoint_resume fires — the command survived the gate followup
    expect(ops).toEqual(['checkpoint_start_advance', 'checkpoint_resume']);
  });

  test('losing the lease invalidates a held narration claim', async () => {
    const world = mkWorld({ head: { pointId: 'p1', version: 1, stateDigest: 'd1', narrationStatus: 'pending' }, lease: { fenceEpoch: 1, expiresAtEpochMilli: 9 }, advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: false }, activeRoundId: 'r1', activePointId: 'p1', round: { roundId: 'r1', trigger: 'player', order: ORDER, cursor: 0, actedIds: [], visitedIds: [], conclusion: null } });
    const control = mkControl({ revision: 4 });
    const work = mkWork();
    const leaseLost = new WorldApiError({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation: null, requestId: 'req', worldId: 'w1', world: { ...world, lease: null }, error: { code: 'lease_invalid', httpStatus: 409, retryable: false, clientAction: 'reacquire_lease', details: {} } });
    const heldError = new WorldApiError({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation: null, requestId: 'req', worldId: 'w1', error: { code: 'lease_invalid', httpStatus: 409, retryable: false, clientAction: 'reacquire_lease', details: { reason: 'lease_held' } } });
    const transport = new ScriptedTransport([
      { op: 'narration_submit', respond: () => { throw leaseLost; } },
      { op: 'lease_acquire', respond: () => { throw heldError; } },
    ]);
    const memory = memoryWithAdvanceStart({
      narration: { pointId: 'p1', claim: { claimToken: 'ct_old', generation: 1, issuedAtEpochMilli: 1 }, input: { pointId: 'p1', after: null, delta: null, previousPointId: null, before: null } },
      lastModel: { task: 'narration', key: 'p1', output: '旧文本。' },
    });
    const driver = new ControllerDriver({ transport, model: new ScriptedModel([]) }, memory, { world, control, work });
    const status = await driver.step();
    expect(status).toEqual({ kind: 'await', reason: 'lease_held_by_other' });
    expect(driver.getMemory().narration).toMatchObject({ pointId: 'p1', claim: null });
  });
});
