/** Handwritten state/memory snapshots for the B1 pure scheduler; responses
 * and trace-corpus shapes follow the shared contract specimens (T01–T09). */
import { describe, expect, test } from 'vitest';
import { assembleNarrationInput, checkUpdatesStages, errorCatalog, errorReaction, foldIdentity, initialNarrationAssembly, scheduleNext, sha256Hex, triggerAllocationKey, triggerSlotKey, workingStateKey } from './schedule';
import type { ControllerMemory, Decision, PlannedPoint, ScheduleView, SourceAnalysis, StagedUnit, UpdatesCall, UpdatesStage } from './schedule';
import { validateRequest } from './protocol';
import type { ClientAction, ControlState, ErrorCode, ErrorResponse, Json, PointWork, TimeAdvance, WorldContext, WorldState } from './types';

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

const workingState = (): WorldState => ({
  engineVersion: 'world-engine-v1' as const, schemaVersion: 1 as const, worldId: 'w1', protagonistId: 'person_a', time: wt,
  initial: { ...initialTemplate(), worldId: 'w1' },
  locations: { corridor: { id: 'corridor', appearanceChanges: [] } },
  items: {},
  characters: { person_a: { id: 'person_a', appearanceChanges: [], position, personalityChanges: [], sanity: 50, tasks: { t1: { id: 't1', ownerId: 'person_a', parentTaskId: null, goal: '检查走廊', status: 'pending' } } } },
});

const world = (over: Partial<WorldContext> = {}): WorldContext => ({
  worldId: 'w1', time: wt,
  head: { pointId: 'root', version: 0, stateDigest: 'd0', narrationStatus: 'ready' },
  advance: { advanceId: null, inputId: null, intentStatus: 'pending', inputAvailable: true },
  round: null, lease: { fenceEpoch: 1, expiresAtEpochMilli: 999999 },
  successor: null, activePointId: null, activeRoundId: null, ...over,
});

const control = (over: Partial<ControlState> = {}): ControlState => ({
  phase: 'select_actor', paused: false, revision: 0,
  gate: { status: 'none', generation: null, issuedAtEpochMilli: null, expiresAtEpochMilli: null },
  blockedReasons: [], canCompute: true, ...over,
});

const pointWork = (over: Partial<PointWork> = {}): PointWork => ({
  pointId: 'p1', kind: 'normal', timeAdvance: ta(2), timeLocked: false, sealed: false, prefixDigest: null, predecessorWorkDigest: null,
  timeScanComplete: false, baseline: { headPointId: 'root', version: 0, stateDigest: 'd0' }, phase: 'select_actor',
  working: { cursor: 0, actedIds: [], visitedIds: [], settledUnitIds: [], intentStatus: 'pending' },
  settledUnits: [], pendingGroup: null, successor: null, ...over,
});

const memory = (over: Partial<ControllerMemory> = {}): ControllerMemory => ({
  requestId: 'rq1', leaseToken: 'lease1', holderId: 'browser', ids: {}, allocPlan: null, roundAllocations: {}, allocatedKeys: [], playerInput: null, playerAdvance: null,
  plan: null, planIndex: 0, prepareSuccessor: false, localPause: false, budget: { used: 0, max: null },
  narration: null, workingState: null, sources: [], staged: [], stagedTimeScan: null, groupActors: [], groupActions: [], lastModel: null, lastTargets: null, lastResults: null,
  updatesStages: [], updatesCalls: [], updatesApplied: 0, updatesPreviewSkipped: 0, updatesPendingRefs: [],
  lastRoundIdentityError: null, roundIdentityBlocked: null,
  continuation: null, roundChanges: null, successorTime: null, commitPayload: null, initialTemplate: null, ...over,
});

const view = (world_: WorldContext | null, control_: ControlState, work_: PointWork | null, memory_: ControllerMemory, command?: ScheduleView['command'], activeInput: ScheduleView['activeInput'] = null): ScheduleView =>
  ({ world: world_, control: control_, work: work_, memory: memory_, command, activeInput });

const next = (w: WorldContext | null, c: ControlState, wk: PointWork | null, m: ControllerMemory, command?: ScheduleView['command']): Decision =>
  scheduleNext(view(w, c, wk, m, command));

const expectTransport = (decision: Decision, operation: string, narrationPointId?: string) => {
  expect(decision.kind).toBe('transport');
  if (decision.kind !== 'transport') return decision;
  expect(decision.operation).toBe(operation);
  const expectedScope: { worldId: string; pointId?: string } = { worldId: 'w1' };
  if (operation === 'narration_claim' || operation === 'narration_submit') expectedScope.pointId = narrationPointId!;
  expect(decision.scope).toEqual(expectedScope);
  validateRequest(decision.operation, decision.request);
  return decision;
};

const groupOf = (sourceId: string, actionText = '行动。'): SourceAnalysis =>
  ({ sourceId, actionText, targetsExtended: false, pendingTargets: [], rolled: [] });

const stagedUnit = (groupId = 'g1', actorId = 'person_a'): StagedUnit => ({
  groupId, actorIds: [actorId], results: {},
  candidates: { groupId, actorIds: [actorId], positions: {}, appearances: {}, tasksAchieved: {}, subtasksAdded: {}, personalities: {}, sanities: {}, taskCoverageIds: [], personalityCoverageIds: [] },
});

describe('advance pipeline (T01 spine)', () => {
  test('awaits player input', () => {
    const decision = next(world(), control(), null, memory({ allocPlan: { allocationKey: 'chain_slots', slots: [] } }));
    expect(decision).toEqual({ kind: 'await_command', reason: 'player_input' });
  });
  test('creates the world from the initial template with an empty scope', () => {
    const m = memory({ initialTemplate: initialTemplate() });
    const decision = next(null, control(), null, m) as Extract<Decision, { kind: 'transport' }>;
    expect(decision.kind).toBe('transport');
    expect(decision.operation).toBe('create_world');
    expect(decision.scope).toEqual({});
    validateRequest(decision.operation, decision.request);
  });
  test('allocates ids before start_advance', () => {
    const m = memory({ playerInput: { text: '探索走廊', order: ORDER }, allocPlan: { allocationKey: 'chain_slots', slots: [{ slotKey: 'advance', kind: 'advance', scope: null }] } });
    const decision = expectTransport(next(world(), control(), null, m), 'allocate_ids') as Extract<Decision, { kind: 'transport' }>;
    const request = decision.request as unknown as { allocationKey: string; slots: unknown[] };
    expect(request.allocationKey).toBe('chain_slots');
    expect(request.slots.length).toBe(1);
  });
  test('starts the advance with allocated ids and player order', () => {
    const m = memory({ playerInput: { text: '探索走廊', order: ORDER }, ids: { advance: 'adv1', input: 'in1', round: 'r1' }, allocPlan: { allocationKey: 'chain_slots', slots: [] } });
    const decision = expectTransport(next(world(), control(), null, m), 'checkpoint_start_advance') as Extract<Decision, { kind: 'transport' }>;
    const request = decision.request as unknown as Record<string, unknown>;
    expect(request.operation).toBe('start_advance');
    expect(request).toMatchObject({ advanceId: 'adv1', inputId: 'in1', roundId: 'r1', inputText: '探索走廊', order: ORDER, expectedCheckpointRevision: 0 });
  });
  test('begins the planned point', () => {
    const w = world({ advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: false }, activeRoundId: 'r1', round: { roundId: 'r1', trigger: 'player', order: ORDER, cursor: 0, actedIds: [], visitedIds: [], conclusion: null } });
    const plan: PlannedPoint[] = [{ pointId: 'p1', kind: 'normal', timeAdvance: ta(2), actorIds: ['person_a'] }];
    const decision = expectTransport(next(w, control({ revision: 1 }), null, memory({ plan, planIndex: 0 })), 'checkpoint_begin_point') as Extract<Decision, { kind: 'transport' }>;
    expect(decision.request as unknown as Record<string, unknown>).toMatchObject({ operation: 'begin_point', pointId: 'p1', kind: 'normal', timeAdvance: ta(2), expectedCheckpointRevision: 1 });
  });
  test('resolves the plan through the model port first', () => {
    const w = world({ advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: false }, activeRoundId: 'r1', round: { roundId: 'r1', trigger: 'player', order: ORDER, cursor: 0, actedIds: [], visitedIds: [], conclusion: null } });
    const decision = next(w, control(), null, memory());
    expect(decision).toMatchObject({ kind: 'model', task: 'pointPlan', key: 'r1' });
  });
  test('T01 s1–s5: root narration, allocate and start all run under phase=complete', () => {
    const c0 = control({
      phase: 'complete', revision: 0,
      gate: { status: 'pending', generation: 1, issuedAtEpochMilli: 1, expiresAtEpochMilli: 2 },
      blockedReasons: ['narration_pending', 'phase_not_computable'], canCompute: false,
    });
    const w0 = world({ head: { pointId: 'root', version: 0, stateDigest: 'd0', narrationStatus: 'pending' } });
    const m = memory({ playerInput: { text: '探索走廊', order: ORDER }, allocPlan: { allocationKey: 'chain_slots', slots: [{ slotKey: 'advance', kind: 'advance', scope: null }, { slotKey: 'input', kind: 'input', scope: null }, { slotKey: 'round', kind: 'round', scope: null }] } });
    expectTransport(next(w0, c0, null, m), 'narration_claim', 'root');
    m.narration = { pointId: 'root', claim: { claimToken: 'ct0', generation: 1, issuedAtEpochMilli: 5 }, input: initialNarrationAssembly('root') };
    // 组装阶梯：目标读（root 即目标，previousPointId=null 免 before 读）
    expectTransport(next(w0, c0, null, m), 'get_state', 'root');
    m.narration!.input.after = workingState() as never;
    m.narration!.input.delta = { timeAdvance: null, entityDeltas: {} };
    expect(next(w0, c0, null, m)).toMatchObject({ kind: 'model', task: 'narration', key: 'root' });
    m.lastModel = { task: 'narration', key: 'root', output: '走廊的霜气未散。' };
    expectTransport(next(w0, c0, null, m), 'narration_submit', 'root');
    // Driver applies s3: narration ready, gate cleared. s4: allocate under complete.
    const w1 = world({ head: { pointId: 'root', version: 0, stateDigest: 'd0', narrationStatus: 'ready' } });
    const c1 = control({ phase: 'complete', revision: 1 });
    expectTransport(next(w1, c1, null, m), 'allocate_ids');
    m.ids = { advance: 'adv1', input: 'in1', round: 'r1' };
    expectTransport(next(w1, c1, null, m), 'checkpoint_start_advance');
    // Without pending player input the controller stops.
    m.playerInput = null;
    m.ids = {};
    expect(next(w1, c1, null, m)).toEqual({ kind: 'stop', reason: 'world_complete' });
  });
});

describe('normal point: group cycle (T01/T02 shapes)', () => {
  const activeWorld = () => world({
    head: { pointId: 'root', version: 0, stateDigest: 'd0', narrationStatus: 'ready' },
    advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: false },
    activeRoundId: 'r1', activePointId: 'p1',
    round: { roundId: 'r1', trigger: 'player', order: ORDER, cursor: 0, actedIds: [], visitedIds: [], conclusion: null },
  });
  const spine = (over: { work?: Partial<PointWork>; memory?: Partial<ControllerMemory>; revision?: number } = {}) => ({
    w: activeWorld(), c: control({ revision: over.revision ?? 2 }),
    wk: pointWork(over.work), m: memory({ plan: [{ pointId: 'p1', kind: 'normal' as const, timeAdvance: ta(2), actorIds: ['person_a'] }], ids: { 'group:person_a': 'g1' }, ...over.memory }),
  });

  test('previews before the first action, then asks the action model', () => {
    const { w, c, wk, m } = spine();
    expect(next(w, c, wk, m)).toEqual({ kind: 'read_working_state' });
    m.workingState = { key: workingStateKey(wk), state: workingState() };
    expect(next(w, c, wk, m)).toMatchObject({ kind: 'model', task: 'action', key: 'person_a' });
  });
  test('discovers the group from an act output with null targets', () => {
    const { w, c, wk, m } = spine({ memory: { workingState: { key: workingStateKey(pointWork()), state: workingState() }, lastModel: { task: 'action', key: 'person_a', output: { kind: 'act', text: 'person_a采取冻结行动。' } as unknown as Json } } });
    const decision = expectTransport(next(w, c, wk, m), 'checkpoint_discover_group') as Extract<Decision, { kind: 'transport' }>;
    expect(decision.request as unknown as Record<string, unknown>).toMatchObject({ operation: 'discover_group', pointId: 'p1', groupId: 'g1', initiatorId: 'person_a', actionText: 'person_a采取冻结行动。', targetIds: null });
  });
  test('a planned actor returning skip records the skip instead of discovering', () => {
    const { w, c, wk, m } = spine({ memory: { workingState: { key: workingStateKey(pointWork()), state: workingState() }, lastModel: { task: 'action', key: 'person_a', output: { kind: 'skip' } as unknown as Json } } });
    const decision = expectTransport(next(w, c, wk, m), 'checkpoint_record_skip') as Extract<Decision, { kind: 'transport' }>;
    expect((decision.request as unknown as { slotActorId: string }).slotActorId).toBe('person_a');
  });
  test('missing trigger keys allocate at runtime before extending (program-owned keys)', () => {
    const pending: SourceAnalysis = { sourceId: 'person_a', actionText: '行动。', targetsExtended: false, pendingTargets: [], rolled: [] };
    const { w, c, wk, m } = spine({
      work: { phase: 'build_group', pendingGroup: { groupId: 'g1', sourceId: 'person_a', memberIds: ['person_a'], targetIds: [], frontierIds: [], closed: false } },
      memory: { workingState: { key: workingStateKey(pointWork()), state: workingState() }, sources: [pending], lastTargets: { sourceId: 'person_a', targets: ['person_d', 'person_a', 'person_d'] } },
    });
    // 键未分配：先走运行时 allocate_ids（模型输出不携带键，目标集不重采样；
    // allocationKey 稳定 → 重试幂等；重复目标去重）。
    const allocate = expectTransport(next(w, c, wk, m), 'allocate_ids') as Extract<Decision, { kind: 'transport' }>;
    expect(allocate.request as unknown as Record<string, unknown>).toMatchObject({
      allocationKey: triggerAllocationKey('g1', 'person_a'),
      slots: [
        { slotKey: triggerSlotKey('g1', 'person_a', 'person_d'), kind: 'trigger' },
        { slotKey: triggerSlotKey('g1', 'person_a', 'person_a'), kind: 'trigger' },
      ],
    });
    m.ids[triggerSlotKey('g1', 'person_a', 'person_d')] = 'tk_d';
    m.ids[triggerSlotKey('g1', 'person_a', 'person_a')] = 'tk_a';
    // 键齐：extend_group 用程序解析的键；create_rolls 带程序锁定规则。
    const extend = expectTransport(next(w, c, wk, m), 'checkpoint_extend_group') as Extract<Decision, { kind: 'transport' }>;
    expect((extend.request as unknown as { targets: unknown[] }).targets).toEqual([{ targetId: 'person_d', triggerKey: 'tk_d' }, { targetId: 'person_a', triggerKey: 'tk_a' }]);
    pending.targetsExtended = true;
    pending.pendingTargets = [{ targetId: 'person_d', triggerKey: 'tk_d' }, { targetId: 'person_a', triggerKey: 'tk_a' }]
      .sort((a, b) => (a.targetId < b.targetId ? -1 : 1))
      .map((t) => ({ targetId: t.targetId, triggerKey: t.triggerKey, rule: { ruleVersion: 'reaction-d20-v1' as const, target: 11 } }));
    const roll = expectTransport(next(w, c, wk, m), 'create_rolls') as Extract<Decision, { kind: 'transport' }>;
    expect((roll.request as unknown as { rolls: { targetId: string; ruleVersion: string; target: number }[] }).rolls).toEqual([{ advanceId: 'adv1', roundId: 'r1', groupId: 'g1', sourceId: 'person_a', targetId: 'person_a', triggerKey: 'tk_a', ruleVersion: 'reaction-d20-v1', target: 11 }]);
  });
  test('a mixed key set requests only this source\u2019s missing slots (no reuse, no clobber)', () => {
    const pending: SourceAnalysis = { sourceId: 'person_c', actionText: '行动。', targetsExtended: false, pendingTargets: [], rolled: [] };
    const { w, c, wk, m } = spine({
      work: { phase: 'build_group', pendingGroup: { groupId: 'g1', sourceId: 'person_c', memberIds: ['person_c'], targetIds: [], frontierIds: [], closed: false } },
      // 他人来源 person_a 早已为 person_d 分配过键（方向：person_a→person_d）：
      // 不得复用、不得覆盖、不得随本次请求重发——只缺本来源自己的 person_e 槽位。
      memory: {
        workingState: { key: workingStateKey(pointWork()), state: workingState() }, sources: [pending],
        lastTargets: { sourceId: 'person_c', targets: ['person_d', 'person_e'] },
        ids: { [triggerSlotKey('g1', 'person_c', 'person_d')]: 'tk_c_d', [triggerSlotKey('g1', 'person_a', 'person_d')]: 'tk_a_d' },
      },
    });
    const allocate = expectTransport(next(w, c, wk, m), 'allocate_ids') as Extract<Decision, { kind: 'transport' }>;
    expect(allocate.request as unknown as Record<string, unknown>).toMatchObject({
      allocationKey: triggerAllocationKey('g1', 'person_c'),
      slots: [{ slotKey: triggerSlotKey('g1', 'person_c', 'person_e'), kind: 'trigger' }],
    });
    expect(m.ids[triggerSlotKey('g1', 'person_a', 'person_d')]).toBe('tk_a_d');
  });
  test('an empty target set extends without allocating', () => {
    const pending: SourceAnalysis = { sourceId: 'person_a', actionText: '行动。', targetsExtended: false, pendingTargets: [], rolled: [] };
    const { w, c, wk, m } = spine({
      work: { phase: 'build_group', pendingGroup: { groupId: 'g1', sourceId: 'person_a', memberIds: ['person_a'], targetIds: [], frontierIds: [], closed: false } },
      memory: { workingState: { key: workingStateKey(pointWork()), state: workingState() }, sources: [pending], lastTargets: { sourceId: 'person_a', targets: [] } },
    });
    const extend = expectTransport(next(w, c, wk, m), 'checkpoint_extend_group') as Extract<Decision, { kind: 'transport' }>;
    expect((extend.request as unknown as { targets: unknown[] }).targets).toEqual([]);
  });
  test('reaction runs before the admitted extend and carries roll refs (T02-el s5–s6)', () => {
    const pending: SourceAnalysis = {
      sourceId: 'person_c', actionText: '行动。', targetsExtended: true,
      pendingTargets: [{ targetId: 'person_d', triggerKey: 'tk_d', rule: { ruleVersion: 'reaction-d20-v1', target: 11 } }],
      rolled: [],
    };
    const { w, c, wk, m } = spine({
      work: { phase: 'build_group', pendingGroup: { groupId: 'g9', sourceId: 'person_c', memberIds: ['person_c'], targetIds: [], frontierIds: [], closed: false } },
      memory: { workingState: { key: workingStateKey(pointWork()), state: workingState() }, sources: [pending] },
    });
    expect(expectTransport(next(w, c, wk, m), 'create_rolls')).toBeTruthy();
    pending.rolled.push({ targetId: 'person_d', triggerKey: 'tk_d', rule: { ruleVersion: 'reaction-d20-v1', target: 11 }, rollId: 'roll_d', admitted: true, reacted: false });
    pending.pendingTargets = [];
    // 反应读发起者的冻结威胁文本（§6.2 步骤 4）——与 targets 同源。
    expect(next(w, c, wk, m)).toMatchObject({ kind: 'model', task: 'reaction', key: 'person_c', input: { sourceActionText: '行动。', memberId: 'person_d', rollId: 'roll_d' } });
    m.lastModel = { task: 'reaction', key: 'person_c', output: 'person_d被迫反应。' };
    const extend = expectTransport(next(w, c, wk, m), 'checkpoint_extend_group') as Extract<Decision, { kind: 'transport' }>;
    expect((extend.request as unknown as { admittedMember: unknown }).admittedMember).toEqual({
      memberId: 'person_d', actionText: 'person_d被迫反应。',
      rollRefs: [{ sourceId: 'person_c', targetId: 'person_d', triggerKey: 'tk_d', rollId: 'roll_d' }],
    });
  });
  test('action input carries the chain-level advance: player text plus the served intent status (#1, §6.1)', () => {
    const { w, c, wk, m } = spine();
    m.workingState = { key: workingStateKey(wk), state: workingState() };
    expect(scheduleNext(view(w, c, wk, m, undefined, { advanceId: 'adv1', inputId: 'in1', text: '我推开重门。' }))).toMatchObject({
      kind: 'model', task: 'action', key: 'person_a',
      input: { actor: 'person_a', advance: { inputText: '我推开重门。', intentStatus: 'consumed' } },
    });
    // 正常输入路径：没有 context 回读时，驱动器自己 start_advance 的原文仍可用，
    // 且只在 advance 身份一致时生效。
    const retained: ControllerMemory = { ...m, playerAdvance: { advanceId: 'adv1', inputId: 'in1', text: '我推开重门。' } };
    expect(next(w, c, wk, retained)).toMatchObject({ kind: 'model', task: 'action', input: { advance: { inputText: '我推开重门。' } } });
    const stale: ControllerMemory = { ...m, playerAdvance: { advanceId: 'adv0', inputId: 'in0', text: '上一轮的输入' } };
    expect(next(w, c, wk, stale)).toMatchObject({ kind: 'model', task: 'action', input: { advance: { inputText: null } } });
    // 旧 advance 的 context 快照同样不得泄漏；同一 advance 的 context 是权威来源。
    expect(scheduleNext(view(w, c, wk, m, undefined, { advanceId: 'adv0', inputId: 'in0', text: '上一轮的输入' }))).toMatchObject({ kind: 'model', task: 'action', input: { advance: { inputText: null } } });
    expect(scheduleNext(view(w, c, wk, retained, undefined, { advanceId: 'adv1', inputId: 'in1', text: '服务端原文' }))).toMatchObject({ kind: 'model', task: 'action', input: { advance: { inputText: '服务端原文' } } });
    // 消费状态取自服务态，不是文本的有无：未消费的 advance 仍是 pending。
    const pendingWorld = { ...w, advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'pending' as const, inputAvailable: true } };
    expect(next(pendingWorld, c, wk, m)).toMatchObject({ kind: 'model', task: 'action', input: { advance: { inputText: null, intentStatus: 'pending' } } });
  });
  test('results input carries the whole frozen group and every roll outcome, inadmissible included (#4, §7.1)', () => {
    const { w, c, wk, m } = spine({
      work: { phase: 'settle_group', pendingGroup: { groupId: 'g1', sourceId: 'person_a', memberIds: ['person_a', 'person_b'], targetIds: [], frontierIds: [], closed: true } },
      memory: {
        workingState: { key: workingStateKey(pointWork()), state: workingState() },
        groupActions: [
          { memberId: 'person_b', actionText: '从储物柜里取出钥匙', rolls: [] },
          { memberId: 'person_a', actionText: '用力推开走廊尽头的门', rolls: [
            { targetId: 'person_b', rollId: 'roll_1', result: 12, eligible: true, admitted: true },
            { targetId: 'person_c', rollId: 'roll_2', result: 3, eligible: false, admitted: false },
          ] },
        ],
      },
    });
    expect(next(w, c, wk, m)).toMatchObject({
      kind: 'model', task: 'results', key: 'g1',
      input: {
        groupId: 'g1',
        members: [
          { memberId: 'person_b', actionText: '从储物柜里取出钥匙', rollRefs: [] },
          { memberId: 'person_a', actionText: '用力推开走廊尽头的门', rollRefs: [
            { targetId: 'person_b', rollId: 'roll_1', result: 12, eligible: true, admitted: true },
            { targetId: 'person_c', rollId: 'roll_2', result: 3, eligible: false, admitted: false },
          ] },
        ],
      },
    });
  });
  test('missing frozen group actions stop before results instead of an empty member list (#4)', () => {
    const { w, c, wk, m } = spine({
      work: { phase: 'settle_group', pendingGroup: { groupId: 'g1', sourceId: 'person_a', memberIds: ['person_a', 'person_b'], targetIds: [], frontierIds: [], closed: true } },
      memory: {
        workingState: { key: workingStateKey(pointWork()), state: workingState() },
        groupActions: [{ memberId: 'person_a', actionText: '行动。', rolls: [] }],
      },
    });
    expect(next(w, c, wk, m)).toEqual({ kind: 'stop', reason: 'frozen_actions_missing:person_b' });
  });
  test('DFS: the reaction of an admitted sibling precedes rolling the next one (T02-el s5–s8)', () => {
    const pending: SourceAnalysis = {
      sourceId: 'person_c', actionText: '行动。', targetsExtended: true,
      pendingTargets: [{ targetId: 'person_e', triggerKey: 'tk_e', rule: { ruleVersion: 'reaction-d20-v1', target: 11 } }],
      rolled: [{ targetId: 'person_d', triggerKey: 'tk_d', rule: { ruleVersion: 'reaction-d20-v1', target: 11 }, rollId: 'roll_d', admitted: true, reacted: false }],
    };
    const { w, c, wk, m } = spine({
      work: { phase: 'build_group', pendingGroup: { groupId: 'g9', sourceId: 'person_c', memberIds: ['person_c'], targetIds: [], frontierIds: [], closed: false } },
      memory: { workingState: { key: workingStateKey(pointWork()), state: workingState() }, sources: [pending] },
    });
    expect(next(w, c, wk, m)).toMatchObject({ kind: 'model', task: 'reaction', key: 'person_c', input: { memberId: 'person_d' } });
    pending.rolled[0].reacted = true;
    const roll = expectTransport(next(w, c, wk, m), 'create_rolls') as Extract<Decision, { kind: 'transport' }>;
    expect((roll.request as unknown as { rolls: { targetId: string }[] }).rolls[0].targetId).toBe('person_e');
  });
  test('analyses an admitted member immediately (DFS), closes when the frontier empties', () => {
    const pending: SourceAnalysis = { sourceId: 'person_c', actionText: '行动。', targetsExtended: true, pendingTargets: [], rolled: [] };
    const member: SourceAnalysis = { sourceId: 'person_d', actionText: 'person_d被迫反应。', targetsExtended: false, pendingTargets: [], rolled: [] };
    const { w, c, wk, m } = spine({
      work: { phase: 'build_group', pendingGroup: { groupId: 'g9', sourceId: 'person_c', memberIds: ['person_c', 'person_d'], targetIds: [], frontierIds: [], closed: false } },
      memory: { workingState: { key: workingStateKey(pointWork()), state: workingState() }, sources: [member, pending] },
    });
    expect(next(w, c, wk, m)).toMatchObject({ kind: 'model', task: 'targets', key: 'person_d' });
    m.sources = [];
    expectTransport(next(w, c, wk, m), 'checkpoint_close_group');
  });
  test('results then updates then stage; positions only from positionSet deltas (T02 s6)', () => {
    const { w, c, wk, m } = spine({
      work: { phase: 'settle_group', pendingGroup: { groupId: 'g1', sourceId: 'person_a', memberIds: ['person_a'], targetIds: [], frontierIds: [], closed: true } },
      memory: {
        workingState: { key: workingStateKey(pointWork()), state: workingState() },
        groupActions: [{ memberId: 'person_a', actionText: '行动。', rolls: [] }],
      },
    });
    expect(next(w, c, wk, m)).toMatchObject({ kind: 'model', task: 'results', key: 'g1' });
    m.lastResults = { person_a: 'person_a的行动结果已确认。' };
    // §7.1：更新读已确认结果——不是在提示词里提一下，而是输入真的带上。
    expect(next(w, c, wk, m)).toMatchObject({ kind: 'model', task: 'updates', key: 'g1', input: { groupId: 'g1', mode: 'group', results: { person_a: 'person_a的行动结果已确认。' } } });
    m.lastModel = {
      task: 'updates', key: 'g1', output: [{
        stage: 'appearance',
        changes: { person_a: { positionSet: position, appearanceChanges: [{ id: 'ch1', text: '指尖结霜。', supersedes: [] }] } },
      }] as unknown as Json,
    };
    const stage = expectTransport(next(w, c, wk, m), 'checkpoint_stage_unit') as Extract<Decision, { kind: 'transport' }>;
    const request = stage.request as unknown as { candidates: Record<string, unknown>; results: Record<string, string> };
    expect(request.candidates).toMatchObject({
      groupId: 'g1', actorIds: ['person_a'], positions: { person_a: position },
      appearances: { person_a: [{ id: 'ch1', text: '指尖结霜。', supersedes: [] }] },
      taskCoverageIds: ['person_a'], personalityCoverageIds: [],
    });
    expect(request.results).toEqual({ person_a: 'person_a的行动结果已确认。' });
  });
  test('T03-collapse shape: tasks achieved declare world-roster coverage (2026-10-22 ruling)', () => {
    const { w, c, wk, m } = spine({
      work: { phase: 'settle_group', pendingGroup: { groupId: 'g1', sourceId: 'person_a', memberIds: ['person_a'], targetIds: [], frontierIds: [], closed: true } },
      memory: { workingState: { key: workingStateKey(pointWork()), state: workingState() }, lastResults: { person_a: 'x' } },
    });
    m.lastModel = {
      task: 'updates', key: 'g1', output: [
        { stage: 'tasks', changes: { person_a: { tasksAchieved: ['t1'] } } },
        { stage: 'subtasks', changes: { person_a: { subtasksAdded: [{ id: 'v12', ownerId: 'person_a', parentTaskId: null, goal: '检查安全', status: 'pending' }] } } },
      ] as unknown as Json,
    };
    const stage = expectTransport(next(w, c, wk, m), 'checkpoint_stage_unit') as Extract<Decision, { kind: 'transport' }>;
    const candidates = (stage.request as unknown as { candidates: Record<string, unknown> }).candidates;
    expect(candidates).toMatchObject({ actorIds: ['person_a'], tasksAchieved: { person_a: ['t1'] }, positions: {}, taskCoverageIds: ['person_a'], personalityCoverageIds: ['person_a'] });
  });
  test('uncovered slots are judged in frozen order; later-covered slots are deferred (T01/T02 P1)', () => {
    // T01：计划只覆盖 person_a——a 的组 stage 后，b 必须被询问，不能由程序补记跳过。
    const { w, c, wk, m } = spine({ work: { working: { cursor: 1, actedIds: ['person_a'], visitedIds: ['person_a'], settledUnitIds: ['u1'], intentStatus: 'consumed' } }, memory: { groupActors: ['person_a'], staged: [stagedUnit()] } });
    m.workingState = { key: workingStateKey(wk), state: workingState() };
    expect(next(w, c, wk, m)).toMatchObject({ kind: 'model', task: 'action', key: 'person_b' });
    m.lastModel = { task: 'action', key: 'person_b', output: { kind: 'skip' } as unknown as Json };
    const skip = expectTransport(next(w, c, wk, m), 'checkpoint_record_skip') as Extract<Decision, { kind: 'transport' }>;
    expect((skip.request as unknown as { slotActorId: string }).slotActorId).toBe('person_b');
    // T02 P1：a、b 都已暂存、游标到 2，c 属 P2 → 本点不跳也不问。
    const plan2: PlannedPoint[] = [
      { pointId: 'p1', kind: 'normal', timeAdvance: ta(2), actorIds: ['person_a', 'person_b'] },
      { pointId: 'p2', kind: 'instant', timeAdvance: ta(0, 'instant'), actorIds: ['person_c', 'person_d'] },
      { pointId: 'p3', kind: 'linked', timeAdvance: ta(3, 'instant'), actorIds: ['person_e', 'person_f'] },
    ];
    const m2 = memory({ plan: plan2, planIndex: 0, groupActors: ['person_a', 'person_b'], staged: [stagedUnit('g1', 'person_a'), stagedUnit('g2', 'person_b')] });
    const wk2 = pointWork({ working: { cursor: 2, actedIds: ['person_a', 'person_b'], visitedIds: [], settledUnitIds: ['u1', 'u2'], intentStatus: 'consumed' } });
    expect(next(w, c, wk2, m2)).toEqual({ kind: 'read_working_state' });
    m2.workingState = { key: workingStateKey(wk2), state: workingState() };
    expectTransport(next(w, c, wk2, m2), 'checkpoint_seal_point');
  });
  test('a point whose every judged actor skipped still owes its time scan', () => {
    const { w, c, wk, m } = spine({ work: { working: { cursor: 1, actedIds: ['person_a'], visitedIds: ['person_a'], settledUnitIds: [], intentStatus: 'consumed' } }, memory: { groupActors: ['person_a'] } });
    m.workingState = { key: workingStateKey(wk), state: workingState() };
    // 未被计划覆盖的 b 仍要逐人判断（省略不是跳过）。
    expect(next(w, c, wk, m)).toMatchObject({ kind: 'model', task: 'action', key: 'person_b' });
    m.lastModel = { task: 'action', key: 'person_b', output: { kind: 'skip' } as unknown as Json };
    const skip = expectTransport(next(w, c, wk, m), 'checkpoint_record_skip') as Extract<Decision, { kind: 'transport' }>;
    expect((skip.request as unknown as { slotActorId: string }).slotActorId).toBe('person_b');
    // 其余槽位均已处理且无结算单位 → 本点仍须时间扫描（时间不会因无人行动而丢弃）。
    wk.working = { ...wk.working, cursor: 6, visitedIds: ORDER, actedIds: ['person_a'] };
    m.lastModel = null;
    m.groupActors = [...ORDER];
    m.workingState = { key: workingStateKey(wk), state: workingState() };
    expect(next(w, c, wk, m)).toMatchObject({ kind: 'model', task: 'updates', key: 'time_scan:p1', input: { mode: 'time_scan' } });
    m.lastModel = { task: 'updates', key: 'time_scan:p1', output: [{ stage: 'sanity', changes: { person_a: { sanitySet: 40 } } }] as unknown as Json };
    expectTransport(next(w, c, wk, m), 'checkpoint_stage_time_scan');
  });
  test('previews before sealing, then seals', () => {
    const { w, c, wk, m } = spine({ work: { working: { cursor: 6, actedIds: ORDER, visitedIds: ORDER, settledUnitIds: ['u1'], intentStatus: 'consumed' } }, memory: { groupActors: ['person_a'], staged: [stagedUnit()] } });
    expect(next(w, c, wk, m)).toEqual({ kind: 'read_working_state' });
    m.workingState = { key: workingStateKey(wk), state: workingState() };
    expectTransport(next(w, c, wk, m), 'checkpoint_seal_point');
  });
  test('commits the staged payload once sealed', () => {
    const { w, c, wk, m } = spine({
      work: { sealed: true, prefixDigest: 'pd1' },
      memory: { commitPayload: { point: { worldId: 'w1', id: 'p1', sequence: 1, kind: 'normal', previousPointId: 'root', roundId: 'r1', advanceId: 'adv1', trigger: 'player', linkedFromPointId: null, timeAdvance: ta(2), entityDeltas: {} }, settlementGroups: [] } },
    });
    const decision = expectTransport(next(w, c, wk, m), 'commit_point') as Extract<Decision, { kind: 'transport' }>;
    expect(decision.request as unknown as Record<string, unknown>).toMatchObject({ advanceId: 'adv1', roundId: 'r1', pointId: 'p1' });
  });
});

describe('composite trigger identity keys (#8: unambiguous + wire-bounded)', () => {
  test('sha256Hex matches the standard vectors', () => {
    expect(sha256Hex('')).toBe('e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855');
    expect(sha256Hex('abc')).toBe('ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
  });
  test('folding is injective across segment boundaries (a:b|c vs a|b:c)', () => {
    expect(triggerSlotKey('g', 'a:b', 'c')).not.toBe(triggerSlotKey('g', 'a', 'b:c'));
    expect(triggerAllocationKey('g', 'a:b')).not.toBe(triggerAllocationKey('g', 'a'));
    expect(foldIdentity('a:b', 'c')).not.toBe(foldIdentity('a', 'b:c'));
  });
  test('keys stay within the 128-char wire bound for 50-char legal IDs', () => {
    const long = 'k'.repeat(50);
    const slotKey = triggerSlotKey(long, long, long);
    const allocationKey = triggerAllocationKey(long, long);
    expect(slotKey.length).toBeLessThanOrEqual(128);
    expect(allocationKey.length).toBeLessThanOrEqual(128);
    expect(slotKey).toMatch(/^trigger:[0-9a-f]{32}$/);
  });
  test('folding is stable across calls (idempotent retries bind to the same key)', () => {
    expect(triggerSlotKey('g1', 'person_c', 'person_d')).toBe(triggerSlotKey('g1', 'person_c', 'person_d'));
    expect(triggerAllocationKey('g1', 'person_c')).toBe(triggerAllocationKey('g1', 'person_c'));
  });
});

describe('updates split (1–6 per-stage calls)', () => {
  const settling = (stages: UpdatesStage[] = ['tasks', 'sanity']) => ({
    w: world({
      advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: false },
      activeRoundId: 'r1', activePointId: 'p1',
      round: { roundId: 'r1', trigger: 'player', order: ORDER, cursor: 0, actedIds: [], visitedIds: [], conclusion: null },
    }),
    c: control({ revision: 5 }),
    wk: pointWork({ phase: 'settle_group', pendingGroup: { groupId: 'g1', sourceId: 'person_a', memberIds: ['person_a'], targetIds: [], frontierIds: [], closed: true } }),
    m: memory({
      plan: [{ pointId: 'p1', kind: 'normal', timeAdvance: ta(2), actorIds: ['person_a'] }],
      workingState: { key: workingStateKey(pointWork()), state: workingState() },
      lastResults: { person_a: '结果。' },
      updatesStages: stages,
    }),
  });
  test('emits keyed per-stage calls; later stages read only after the between-stage preview', () => {
    const { w, c, wk, m } = settling();
    expect(next(w, c, wk, m)).toMatchObject({
      kind: 'model', task: 'updates', key: 'g1#tasks',
      input: { stage: 'tasks' },
    });
    const tasksCall: UpdatesCall = { stage: 'tasks', changes: { person_a: { tasksAchieved: ['t1'] } } };
    m.updatesCalls.push(tasksCall);
    // §6.3 阶梯：前序候选未应用 → 先经 preview 应用，再发后序阶段调用；
    // 输入不再携带 priorStages/appliedDelta。
    expect(next(w, c, wk, m)).toEqual({ kind: 'read_working_state' });
    m.updatesApplied = 1;
    m.workingState = { key: workingStateKey(wk), state: workingState() };
    expect(next(w, c, wk, m)).toMatchObject({
      kind: 'model', task: 'updates', key: 'g1#sanity',
      input: { stage: 'sanity' },
    });
    m.updatesCalls.push({ stage: 'sanity', changes: { person_a: { sanitySet: 42 } } });
    const stage = expectTransport(next(w, c, wk, m), 'checkpoint_stage_unit') as Extract<Decision, { kind: 'transport' }>;
    const candidates = (stage.request as unknown as { candidates: Record<string, unknown> }).candidates;
    expect(candidates).toMatchObject({ tasksAchieved: { person_a: ['t1'] }, sanities: { person_a: 42 }, personalityCoverageIds: ['person_a'] });
  });
  test('T03-collapse split: a mid-sequence reference may await later production', () => {
    const { w, c, wk, m } = settling(['tasks', 'subtasks']);
    expect(next(w, c, wk, m)).toMatchObject({ kind: 'model', task: 'updates', key: 'g1#tasks', input: { stage: 'tasks' } });
    m.updatesCalls.push({ stage: 'tasks', changes: { person_a: { tasksAchieved: ['v13'] } } });
    // v13 is produced only by the later subtasks stage — no early dangling stop.
    expect(next(w, c, wk, m)).toEqual({ kind: 'read_working_state' });
    m.updatesApplied = 1;
    m.workingState = { key: workingStateKey(wk), state: workingState() };
    expect(next(w, c, wk, m)).toMatchObject({
      kind: 'model', task: 'updates', key: 'g1#subtasks',
      input: { stage: 'subtasks' },
    });
    m.updatesCalls.push({ stage: 'subtasks', changes: { person_a: { subtasksAdded: [{ id: 'v13', ownerId: 'person_a', parentTaskId: null, goal: '确认门边', status: 'pending' }] } } });
    const stage = expectTransport(next(w, c, wk, m), 'checkpoint_stage_unit') as Extract<Decision, { kind: 'transport' }>;
    const candidates = (stage.request as unknown as { candidates: Record<string, unknown> }).candidates;
    // The delta entity is roster-consistent; coverage follows the world roster.
    expect(candidates).toMatchObject({ tasksAchieved: { person_a: ['v13'] }, subtasksAdded: { person_a: [{ id: 'v13', ownerId: 'person_a', parentTaskId: null, goal: '确认门边', status: 'pending' }] }, personalityCoverageIds: ['person_a'] });
  });
  test('rejects out-of-order stage sequences', () => {
    const input = { taskIds: new Set<string>(), changeIds: new Set<string>() };
    expect(() => checkUpdatesStages(input, [
      { stage: 'sanity', changes: {} },
      { stage: 'tasks', changes: {} },
    ])).toThrow('Out-of-order/duplicate updates stage');
    expect(() => checkUpdatesStages(input, [
      { stage: 'tasks', changes: {} },
      { stage: 'tasks', changes: {} },
    ])).toThrow('Out-of-order/duplicate updates stage');
  });
});

describe('narration pipeline', () => {
  const narrating = (over: { paused?: boolean; status?: 'pending' | 'missing' | 'failed' } = {}) => ({
    w: world({ head: { pointId: 'p1', version: 1, stateDigest: 'd1', narrationStatus: over.status ?? 'pending' } }),
    c: control({ revision: 13, paused: over.paused ?? false }),
  });
  test('claims head narration, generates, then submits ready', () => {
    const { w, c } = narrating();
    const m = memory({ narration: { pointId: 'p1', claim: null, input: initialNarrationAssembly('p1') } });
    expectTransport(next(w, c, null, m), 'narration_claim', 'p1');
    m.narration!.claim = { claimToken: 'ct1', generation: 1, issuedAtEpochMilli: 123 };
    // 阶梯：目标读 → previousPointId 非空 → 前驱读 → 模型
    expectTransport(next(w, c, null, m), 'get_state', 'p1');
    m.narration!.input.after = workingState() as never;
    m.narration!.input.delta = { timeAdvance: ta(2), entityDeltas: {} };
    m.narration!.input.previousPointId = 'root';
    expectTransport(next(w, c, null, m), 'get_state', 'root');
    m.narration!.input.before = workingState() as never;
    expect(next(w, c, null, m)).toMatchObject({ kind: 'model', task: 'narration', key: 'p1' });
    m.lastModel = { task: 'narration', key: 'p1', output: '走廊的霜气未散。' };
    const submit = expectTransport(next(w, c, null, m), 'narration_submit', 'p1') as Extract<Decision, { kind: 'transport' }>;
    expect(submit.request as unknown as Record<string, unknown>).toMatchObject({ outcome: 'ready', text: '走廊的霜气未散。', claimToken: 'ct1', generation: 1, mode: 'head' });
  });
  test('narration runs through an external pause (T05 s7/s8)', () => {
    const { w, c } = narrating({ paused: true });
    const m = memory({ narration: { pointId: 'p1', claim: { claimToken: 'ct1', generation: 1, issuedAtEpochMilli: 123 }, input: { pointId: 'p1', after: workingState() as never, delta: { timeAdvance: null, entityDeltas: {} }, previousPointId: null, before: null } } });
    expect(next(w, c, null, m)).toMatchObject({ kind: 'model', task: 'narration', key: 'p1' });
    m.lastModel = { task: 'narration', key: 'p1', output: '暂停中的叙事照常提交。' };
    const submit = expectTransport(next(w, c, null, m), 'narration_submit', 'p1') as Extract<Decision, { kind: 'transport' }>;
    expect((submit.request as unknown as { outcome: string }).outcome).toBe('ready');
  });
  test('exhausted budget does not deadlock narration', () => {
    const { w, c } = narrating();
    const m = memory({ narration: { pointId: 'p1', claim: { claimToken: 'ct1', generation: 1, issuedAtEpochMilli: 123 }, input: { pointId: 'p1', after: workingState() as never, delta: { timeAdvance: null, entityDeltas: {} }, previousPointId: null, before: null } }, budget: { used: 9, max: 9 } });
    expect(next(w, c, null, m)).toMatchObject({ kind: 'model', task: 'narration' });
  });
  test('narration assembly ladder: incomplete flag and point mismatch both stop', () => {
    const w = world({ head: { pointId: 'p1', version: 1, stateDigest: 'd1', narrationStatus: 'pending' } });
    const c = control({ revision: 13 });
    // readIncomplete：缺字段/点不匹配 → 停止，不默认空增量、不反复读取。
    const m = memory({ narration: { pointId: 'p1', claim: { claimToken: 'ct1', generation: 1, issuedAtEpochMilli: 1 }, input: { pointId: 'p1', after: null, delta: null, previousPointId: null, before: null, readIncomplete: true } } });
    expect(next(w, c, null, m)).toEqual({ kind: 'stop', reason: 'narration_read_incomplete' });
    // 组装完整 + previousPointId=null（root 前驱）→ 直接发模型。
    m.narration!.input = { pointId: 'p1', after: workingState() as never, delta: { timeAdvance: ta(2), entityDeltas: {} }, previousPointId: null, before: null };
    const decision = next(w, c, null, m);
    expect(decision).toMatchObject({ kind: 'model', task: 'narration', key: 'p1' });
    // 组装函数输出形状（独立于场景字面量的实现侧自检）。
    expect(assembleNarrationInput(m.narration!.input)).toMatchObject({ pointId: 'p1', before: null });
  });
  test('pending narration without a lease acquires the lease instead of throwing', () => {
    const w = world({ head: { pointId: 'p1', version: 1, stateDigest: 'd1', narrationStatus: 'pending' }, lease: null });
    const c = control({ revision: 13 });
    const decision = expectTransport(next(w, c, null, memory({ leaseToken: null })), 'lease_acquire') as Extract<Decision, { kind: 'transport' }>;
    expect((decision.request as unknown as { holderId: string }).holderId).toBe('browser');
  });
  test('paused without narration awaits a command', () => {
    const w = world({ head: { pointId: 'p1', version: 1, stateDigest: 'd1', narrationStatus: 'ready' } });
    const c = control({ paused: true });
    expect(next(w, c, null, memory())).toEqual({ kind: 'await_command', reason: 'paused_externally' });
    expect(next(w, c, null, memory({ localPause: true }))).toEqual({ kind: 'await_command', reason: 'local_budget_pause' });
  });
});

describe('empty point time scan (T03)', () => {
  // 合法空点：人物机会都已处理（visited 前缀=全序），时间扫描承包槽位。
  const emptyPoint = (over: Partial<PointWork> = {}) => pointWork({ pointId: 'p0', timeScanComplete: false, ...over });
  const setup = (over: Partial<ControllerMemory> = {}) => ({
    w: world({ advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed' as const, inputAvailable: false }, activeRoundId: 'r1', activePointId: 'p0', round: { roundId: 'r1', trigger: 'automatic' as const, order: ORDER, cursor: 6, actedIds: [], visitedIds: ORDER, conclusion: null } }),
    c: control({ revision: 2 }),
    wk: emptyPoint({ working: { cursor: 6, actedIds: [], visitedIds: ORDER, settledUnitIds: [], intentStatus: 'consumed' } }),
    m: memory({ plan: [{ pointId: 'p0', kind: 'normal' as const, timeAdvance: ta(60), actorIds: [] }], ...over }),
  });
  test('an empty plan with unvisited slots still asks each actor (review guard)', () => {
    // actorIds: [] 且游标 0、六人未处理——不得直接进时间扫描。
    const w = world({ advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed' as const, inputAvailable: false }, activeRoundId: 'r1', activePointId: 'p0', round: { roundId: 'r1', trigger: 'automatic' as const, order: ORDER, cursor: 0, actedIds: [], visitedIds: [], conclusion: null } });
    const wk = pointWork({ pointId: 'p0', timeScanComplete: false });
    const m = memory({ plan: [{ pointId: 'p0', kind: 'normal' as const, timeAdvance: ta(60), actorIds: [] }], workingState: { key: workingStateKey(wk), state: workingState() } });
    expect(next(w, control(), wk, m)).toMatchObject({ kind: 'model', task: 'action', key: 'person_a' });
  });
  test('previews, then asks the updates model for the scan', () => {
    const { w, c, wk, m } = setup();
    expect(next(w, c, wk, m)).toEqual({ kind: 'read_working_state' });
    m.workingState = { key: workingStateKey(wk), state: workingState() };
    expect(next(w, c, wk, m)).toMatchObject({ kind: 'model', task: 'updates', key: 'time_scan:p0' });
  });
  test('stages scan candidates with a null group and world-roster coverage', () => {
    const { w, c, wk, m } = setup({ workingState: { key: workingStateKey(emptyPoint()), state: workingState() } });
    m.lastModel = {
      task: 'updates', key: 'time_scan:p0', output: [
        { stage: 'tasks', changes: { person_a: { tasksAchieved: ['t1'] } } },
        { stage: 'personality', changes: { person_a: { personalityChanges: [{ id: 'pc1', text: '放松警惕。', supersedes: [] }] } } },
        { stage: 'sanity', changes: { person_a: { sanitySet: 45 } } },
      ] as unknown as Json,
    };
    const scan = expectTransport(next(w, c, wk, m), 'checkpoint_stage_time_scan') as Extract<Decision, { kind: 'transport' }>;
    const candidates = (scan.request as unknown as { candidates: Record<string, unknown> }).candidates;
    expect(candidates).toMatchObject({ groupId: null, actorIds: [], tasksAchieved: { person_a: ['t1'] }, sanities: { person_a: 45 }, taskCoverageIds: ['person_a'], personalityCoverageIds: ['person_a'] });
  });
  test('requires a fresh preview after the scan: timeScanComplete is part of the state key', () => {
    const { w, c, wk, m } = setup({ workingState: { key: workingStateKey(emptyPoint()), state: workingState() } });
    wk.timeScanComplete = true;
    m.lastModel = null;
    expect(next(w, c, wk, m)).toEqual({ kind: 'read_working_state' });
    m.workingState = { key: workingStateKey(wk), state: workingState() };
    expectTransport(next(w, c, wk, m), 'checkpoint_seal_point');
  });
});

describe('successor time reads staged work', () => {
  test('refreshes the preview before generating time after a staged unit', () => {
    const w = world({ advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: true }, activeRoundId: 'r1', round: { roundId: 'r1', trigger: 'player', order: ['person_a'], cursor: 0, actedIds: [], visitedIds: [], conclusion: null } });
    const wk = pointWork({ timeLocked: true, working: { cursor: 1, actedIds: ['person_a'], visitedIds: ['person_a'], settledUnitIds: ['unit1'], intentStatus: 'consumed' } });
    const m = memory({
      plan: [{ pointId: 'p1', kind: 'normal', timeAdvance: ta(2), actorIds: ['person_a'] }],
      groupActors: ['person_a'], staged: [stagedUnit()], prepareSuccessor: true,
      ids: { successor: 'p2' }, workingState: { key: workingStateKey(pointWork()), state: workingState() },
    });
    expect(next(w, control(), wk, m)).toEqual({ kind: 'read_working_state' });
    const stagedState = workingState();
    stagedState.characters.person_a.sanity = 35;
    m.workingState = { key: workingStateKey(wk), state: stagedState };
    expect(next(w, control(), wk, m)).toMatchObject({ kind: 'model', task: 'time', key: 'successor:p1', input: { workingState: { characters: { person_a: { sanity: 35 } } } } });
  });
});

describe('round conclusion', () => {
  const assessing = () => ({
    w: world({ advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed' as const, inputAvailable: false }, activeRoundId: 'r1', round: { roundId: 'r1', trigger: 'automatic' as const, order: ORDER, cursor: 6, actedIds: ORDER, visitedIds: ORDER, conclusion: null } }),
    c: control({ phase: 'assess_continuation' as const, revision: 9 }),
  });
  test('asks the continuation model with the current world and this round’s changes', () => {
    const { w, c } = assessing();
    const state = workingState();
    const changes = [{ pointId: 'p1', timeAdvance: ta(2), entityDeltas: { person_a: { entityId: 'person_a', positionSet: position } } }];
    const m = memory({ workingState: { key: workingStateKey(pointWork()), state }, roundChanges: { roundId: 'r1', points: changes } });
    expect(next(w, c, null, m)).toMatchObject({
      kind: 'model', task: 'continuation', key: 'r1',
      input: { workingState: { protagonistId: 'person_a' }, roundChanges: changes },
    });
    // 缺数据时零模型调用：世界与变化都不能为空（H2 补读另做）。
    expect(next(w, c, null, memory())).toEqual({ kind: 'stop', reason: 'continuation_context_missing:workingState,roundChanges' });
    expect(next(w, c, null, memory({ workingState: { key: 'k', state } }))).toEqual({ kind: 'stop', reason: 'continuation_context_missing:roundChanges' });
    // 上一轮遗留的变化不串到本轮——roundId 不符同样算缺。
    expect(next(w, c, null, memory({ workingState: { key: 'k', state }, roundChanges: { roundId: 'r0', points: changes } }))).toEqual({ kind: 'stop', reason: 'continuation_context_missing:roundChanges' });
    expect(next(w, c, null, memory({ roundChanges: { roundId: 'r1', points: changes } }))).toEqual({ kind: 'stop', reason: 'continuation_context_missing:workingState' });
    const concluding = memory({ continuation: { kind: 'handback', closedBy: 'model', cancelReason: null } });
    const conclude = expectTransport(next(w, c, null, concluding), 'round_conclusion_conclude') as Extract<Decision, { kind: 'transport' }>;
    expect((conclude.request as unknown as { conclusion: unknown }).conclusion).toEqual({ kind: 'handback', closedBy: 'model', cancelReason: null });
  });
  test('concludes continue with a seeded next round id', () => {
    const { w, c } = assessing();
    const m = memory({ continuation: { kind: 'continue', closedBy: 'model', cancelReason: null, candidateCharacterIds: ['person_c'], nextRoundId: 'r2' } });
    expectTransport(next(w, c, null, m), 'round_conclusion_conclude');
  });
});

describe('commands, budget, gate and lease', () => {
  const active = () => ({
    w: world({ advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed' as const, inputAvailable: false }, activeRoundId: 'r1', round: { roundId: 'r1', trigger: 'player' as const, order: ORDER, cursor: 0, actedIds: [], visitedIds: [], conclusion: null } }),
    c: control({ revision: 3 }),
  });
  test('pause/resume/cancel commands emit the matching control operations', () => {
    const { w, c } = active();
    const m = memory();
    expectTransport(next(w, c, null, m, { kind: 'pause' }), 'checkpoint_pause');
    expectTransport(next(w, c, null, m, { kind: 'budget_exhausted' }), 'checkpoint_pause');
    expectTransport(next(w, c, null, m, { kind: 'resume' }), 'checkpoint_resume');
    const cancel = expectTransport(next(w, c, null, m, { kind: 'cancel', reason: '玩家放弃' }), 'round_conclusion_cancel') as Extract<Decision, { kind: 'transport' }>;
    expect((cancel.request as unknown as { cancelReason: string }).cancelReason).toBe('玩家放弃');
  });
  test('commands without a lease acquire one first', () => {
    const c = control({ revision: 3 });
    const w = world({ lease: null });
    const decision = expectTransport(next(w, c, null, memory({ leaseToken: null }), { kind: 'pause' }), 'lease_acquire') as Extract<Decision, { kind: 'transport' }>;
    expect((decision.request as unknown as { holderId: string }).holderId).toBe('browser');
  });
  test('budget exhaustion turns the next due state-computation call into a pause', () => {
    const { w, c } = active();
    const wk = pointWork();
    const m = memory({ plan: [{ pointId: 'p1', kind: 'normal', timeAdvance: ta(2), actorIds: ['person_a'] }], workingState: { key: workingStateKey(wk), state: workingState() }, budget: { used: 4, max: 4 } });
    expectTransport(next(w, c, wk, m), 'checkpoint_pause');
  });
  test('pending gate awaits a command', () => {
    const { w, c } = active();
    c.gate = { status: 'pending', generation: 1, issuedAtEpochMilli: 1, expiresAtEpochMilli: 2 };
    expect(next(w, c, null, memory())).toEqual({ kind: 'await_command', reason: 'gate_pending' });
  });
  test('missing lease acquires one before anything else', () => {
    const { c } = active();
    const w = world({ lease: null });
    const decision = expectTransport(next(w, c, null, memory({ leaseToken: null })), 'lease_acquire') as Extract<Decision, { kind: 'transport' }>;
    expect((decision.request as unknown as { holderId: string }).holderId).toBe('browser');
  });
  test('canCompute=false blocks state computation but not the control plane', () => {
    const c = control({ revision: 0, canCompute: false, blockedReasons: ['phase_not_computable'] });
    const m = memory({ playerInput: { text: 'x', order: ORDER }, ids: { advance: 'adv1', input: 'in1', round: 'r1' }, allocPlan: { allocationKey: 'chain_slots', slots: [] } });
    expectTransport(next(world(), c, null, m), 'checkpoint_start_advance');
  });
});

describe('error routing pins the frozen 18-code catalog', () => {
  const expected: Record<ErrorCode, [number, boolean, ClientAction]> = {
    narration_blocked: [409, true, 'wait_narration'],
    cache_missing: [409, false, 'regenerate_narration'],
    claim_expired: [409, false, 'regenerate_narration'],
    claim_fenced: [409, false, 'refresh_context'],
    paused: [409, false, 'resolve_gate'],
    stale_epoch: [409, false, 'reacquire_lease'],
    lease_invalid: [409, false, 'reacquire_lease'],
    revision_mismatch: [409, false, 'refresh_context'],
    phase_invalid: [409, false, 'refresh_context'],
    version_mismatch: [409, false, 'refresh_context'],
    protocol_version_unsupported: [400, false, 'none'],
    request_id_reused: [409, false, 'fix_request'],
    request_in_progress: [409, true, 'retry_same_request'],
    point_time_locked: [409, false, 'fix_request'],
    frozen_work_missing: [409, false, 'pause'],
    frozen_work_corrupt: [409, false, 'pause'],
    preview_budget_exceeded: [413, false, 'fix_request'],
    request_malformed: [400, false, 'fix_request'],
  };
  const followup: Partial<Record<ErrorCode, string>> = {
    request_in_progress: 'retry_same_request',
    stale_epoch: 'lease_acquire', lease_invalid: 'lease_acquire',
    revision_mismatch: 'refresh_context', phase_invalid: 'refresh_context', version_mismatch: 'refresh_context', claim_fenced: 'refresh_context',
    narration_blocked: 'finish_own_narration', cache_missing: 'finish_own_narration', claim_expired: 'finish_own_narration',
    paused: 'await_control',
    frozen_work_missing: 'pause_and_stop', frozen_work_corrupt: 'pause_and_stop',
    request_id_reused: 'stop', point_time_locked: 'stop', request_malformed: 'stop', preview_budget_exceeded: 'stop', protocol_version_unsupported: 'stop',
  };
  const mkError = (code: ErrorCode): ErrorResponse => ({
    protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 2, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1,
    replayed: false, operation: null, requestId: null, worldId: null,
    error: { code, httpStatus: expected[code][0], retryable: expected[code][1], clientAction: expected[code][2], details: {} },
  });
  test.each(Object.entries(expected) as [ErrorCode, [number, boolean, ClientAction]][])('%s', (code, [httpStatus, retryable, clientAction]) => {
    expect(Object.keys(errorCatalog).sort()).toEqual(Object.keys(expected).sort());
    expect(errorCatalog[code]).toMatchObject({ httpStatus, retryable, clientAction });
    const reaction = errorReaction(mkError(code));
    expect(reaction.clientAction).toBe(clientAction);
    expect(reaction.reuseRequestId).toBe(code === 'request_in_progress');
    expect(reaction.followup).toBe(followup[code]);
  });
});

describe('updates guard: dangling references only', () => {
  const input = { taskIds: new Set(['t_root']), changeIds: new Set(['ch_old']) };
  test('rejects a task reference produced nowhere', () => {
    const result = checkUpdatesStages(input, [{ stage: 'tasks', changes: { person_a: { tasksAchieved: ['t_ghost'] } } }]);
    expect(result).toMatchObject({ ok: false, dangling: [{ kind: 'task', id: 't_ghost' }] });
  });
  test('rejects a supersedes reference produced nowhere', () => {
    const result = checkUpdatesStages(input, [{ stage: 'appearance', changes: { person_a: { appearanceChanges: [{ id: 'ch1', text: 'x', supersedes: ['ch_ghost'] }] } } }]);
    expect(result).toMatchObject({ ok: false, dangling: [{ kind: 'change', id: 'ch_ghost' }] });
  });
  test('accepts the T03-collapse overlap: v13 achieved in one stage, added as pending in a later one', () => {
    const result = checkUpdatesStages({ taskIds: new Set(), changeIds: new Set() }, [
      { stage: 'tasks', changes: { person_c: { tasksAchieved: ['v13'] } } },
      { stage: 'subtasks', changes: { person_c: { subtasksAdded: [
        { id: 'v12', ownerId: 'person_c', parentTaskId: null, goal: '检查安全', status: 'pending' },
        { id: 'v13', ownerId: 'person_c', parentTaskId: 'v12', goal: '确认门边', status: 'pending' },
      ] } } },
    ]);
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.merged.person_c).toMatchObject({ entityId: 'person_c', tasksAchieved: ['v13'] });
      expect(result.merged.person_c.subtasksAdded?.map((t) => t.id)).toEqual(['v12', 'v13']);
    }
  });
  test('merges split per-stage calls in order (updates granularity 1–6 calls)', () => {
    const result = checkUpdatesStages(input, [
      { stage: 'position', changes: { person_a: { positionSet: { containerId: 'room', slotId: null, relativeTo: null } } } },
      { stage: 'appearance', changes: { person_a: { appearanceChanges: [{ id: 'ch2', text: 'y', supersedes: ['ch_old'] }] } } },
    ]);
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.merged.person_a.positionSet).toEqual({ containerId: 'room', slotId: null, relativeTo: null });
      expect(result.merged.person_a.appearanceChanges?.length).toBe(1);
    }
  });
});
