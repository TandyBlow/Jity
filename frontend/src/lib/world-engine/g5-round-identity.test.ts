// G5 产品 continue 身份链的最小验收（预审 2026-10-29，确定性桩，不含模型
// continuation 开放）。八条用例对应预审 README「最小验收用例」1–8：
// 无 sink/无预置的阻断、正常连续续轮、预置完整性、conclude 重试/拒绝/耗尽、
// 分配失败屏障、补丁契约收窄、恢复入口（会话级见
// runtime/rule-session-continue.test.ts）、handback 零分配。
import { describe, expect, test } from 'vitest';
import { ControllerDriver, initialMemory, type WorldModelPort } from './controller';
import type { ControllerMemory } from './schedule';
import { WorldApiError, WorldTimeoutError } from './transport';
import type { ControlState, Id, Json, WorldContext, WorldOperation } from './types';

const copy = <T>(value: T): T => structuredClone(value);
const ta = (amount: number) => ({ boundary: 'elapsed' as const, duration: { amount, unit: 'second' as const } });
const ORDER = ['person_a', 'person_b', 'person_c'];

const mkControl = (over: Partial<ControlState> = {}): ControlState => ({
  phase: 'select_actor', paused: false, revision: 1,
  gate: { status: 'none', generation: null, issuedAtEpochMilli: null, expiresAtEpochMilli: null },
  blockedReasons: [], canCompute: true, ...over,
});
const playerWorld = (): WorldContext => ({
  worldId: 'w1',
  head: { pointId: 'p1', version: 1, stateDigest: 'd1', narrationStatus: 'ready' },
  advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: true },
  activeRoundId: 'r1',
  round: { roundId: 'r1', trigger: 'player', order: ORDER, cursor: 3, actedIds: [], visitedIds: ORDER, conclusion: null },
  lease: { fenceEpoch: 1 }, successor: null, activePointId: 'p1', time: { calendar: 'gregorian', dateTime: 'day 1 08:00', instantOrdinal: 1 },
} as unknown as WorldContext);
const automaticWorld = (nextRoundId: Id, order: Id[]): WorldContext => ({
  ...playerWorld(), activeRoundId: nextRoundId,
  round: { roundId: nextRoundId, trigger: 'automatic', order, cursor: 0, actedIds: [], visitedIds: [], conclusion: null },
});
const memoryPending = (over: Partial<ControllerMemory> = {}): ControllerMemory => ({
  ...initialMemory('req', 'browser'),
  leaseToken: 'lease1',
  ids: { point: 'old_point', 'group:person_c': 'old_group' },
  ...over,
});

interface ServerRound { key: string; ids: Record<Id, Id> }
/** 幂等桩服务端：同 allocationKey 永远重放同一批 id；新 key 才消费新 id。 */
const idempotentSink = (allocated: Map<Id, ServerRound>, calls: { key: Id; slots: { slotKey: Id; kind: string }[] }[]) =>
  async (roundId: Id, order: Id[]) => {
    const key = `product_round_${roundId}`;
    const slots = [{ slotKey: 'point', kind: 'point' as const }, ...order.map((actor) => ({ slotKey: `group:${actor}`, kind: 'group' as const }))];
    calls.push({ key, slots });
    let round = allocated.get(key);
    if (!round) {
      round = { key, ids: Object.fromEntries(slots.map((slot, index) => [slot.slotKey, `${slot.slotKey}_fresh_${allocated.size + 1}_${index}`])) };
      allocated.set(key, round);
    }
    return { ids: round.ids, roundAllocations: { [roundId]: { allocationKey: key, slots } }, allocatedKeys: [key] };
  };

const continueTo = (nextRoundId: Id) => ({ kind: 'continue' as const, closedBy: 'model' as const, cancelReason: null, candidateCharacterIds: ['person_c'], nextRoundId });
const handbackConclusion = { kind: 'handback' as const, closedBy: 'model' as const, cancelReason: null };
describe('G5 product round-identity chain (pre-audit 2026-10-29, identityGate drivers)', () => {
  const gateDriver = (transport: { execute: (op: WorldOperation, request: never, scope: never) => Promise<never> }, model: WorldModelPort, memory: ControllerMemory, player: WorldContext) =>
    new ControllerDriver({ transport: transport as never, model }, memory, { world: player, control: mkControl({ phase: 'assess_continuation' }) }, { identityGate: true });
  /** pointPlan 从活内存取 point——证明产品链读的是 sink 分配后的新身份。 */
  const livePointPlanModel = (driver: ControllerDriver): WorldModelPort => ({
    generate: async (task) => {
      if (task !== 'pointPlan') throw new Error(`unexpected model task ${task}`);
      return [{ pointId: driver.getMemory().ids.point, kind: 'normal', timeAdvance: ta(1), actorIds: ORDER }];
    },
  });
  const swapModel = (driver: ControllerDriver, model: WorldModelPort): void => {
    (driver as unknown as { io: { model: WorldModelPort } }).io.model = model;
  };
  test('case 1: no sink and no pre-seed blocks the round entry with a recognizable stop, never reusing the old point', async () => {
    const player = playerWorld();
    const transport = { execute: async (op: WorldOperation) => {
      if (op === 'round_conclusion_conclude') return { world: automaticWorld('r2', ['person_c']), control: mkControl({ revision: 2 }), work: null,
        data: { kind: 'continue', roundId: 'r1', nextRoundId: 'r2' } } as never;
      throw new Error(`unexpected ${op}`);
    } };
    const model = { generate: async () => { throw new Error('pointPlan must not run'); } };
    const driver = gateDriver(transport, model, memoryPending({ continuation: continueTo('r2') }), player);
    await driver.step(); // conclude 采纳 + missing-sink 通知
    expect(driver.getMemory().roundIdentityBlocked).toBe('sink_missing:r2');
    expect(await driver.step()).toEqual({ kind: 'stop', reason: 'round_identity_blocked:sink_missing:r2' });
    expect(driver.pendingDecision()).toEqual({ kind: 'stop', reason: 'round_identity_blocked:sink_missing:r2' });
  });

  test('case 1b: an empty sink patch (no roundAllocations entry) is a blocking failure, not silence', async () => {
    const player = playerWorld();
    const transport = { execute: async (op: WorldOperation) => (op === 'round_conclusion_conclude'
      ? { world: automaticWorld('r2', ['person_c']), control: mkControl({ revision: 2 }), work: null,
          data: { kind: 'continue', roundId: 'r1', nextRoundId: 'r2' } } as never
      : Promise.reject(new Error(`unexpected ${op}`))) };
    const driver = gateDriver(transport, { generate: async () => { throw new Error('pointPlan must not run'); } },
      memoryPending({ continuation: continueTo('r2') }), player);
    let sinkCalls = 0;
    driver.setRoundIdentitySink(() => { sinkCalls += 1; return undefined; });
    await driver.step();
    expect(sinkCalls).toBe(1);
    expect(driver.getMemory().roundIdentityBlocked).toBe('empty_patch:r2');
    expect(driver.getMemory().lastRoundIdentityError).toBe('round_identity_empty_patch:r2');
    expect(await driver.step()).toEqual({ kind: 'stop', reason: 'round_identity_blocked:empty_patch:r2' });
  });

  test('case 2: two consecutive continues rotate round/point/group through the stable per-round keys', async () => {
    const player = playerWorld();
    const allocated = new Map<Id, ServerRound>();
    const calls: { key: Id; slots: { slotKey: Id; kind: string }[] }[] = [];
    const ops: WorldOperation[] = [];
    const transport = { execute: async (op: WorldOperation) => {
      ops.push(op);
      if (op === 'round_conclusion_conclude') {
        const pending = ops.filter((entry) => entry === 'round_conclusion_conclude').length;
        const next = pending === 1 ? 'r2' : 'r3';
        return { world: automaticWorld(next, ['person_c']), control: mkControl({ revision: 2 }), work: null,
          data: { kind: 'continue', roundId: pending === 1 ? 'r1' : 'r2', nextRoundId: next } } as never;
      }
      throw new Error(`unexpected ${op}`);
    } };
    const memory = memoryPending({ continuation: continueTo('r2') });
    const driver = new ControllerDriver({ transport: transport as never, model: { generate: async () => { throw new Error('swap me'); } } },
      memory, { world: player, control: mkControl({ phase: 'assess_continuation' }) }, { identityGate: true });
    swapModel(driver, livePointPlanModel(driver));
    driver.setRoundIdentitySink(idempotentSink(allocated, calls));
    await driver.step(); // conclude r1 → r2，sink 分配 product_round_r2
    expect(driver.getMemory().roundIdentityBlocked).toBeNull();
    const round2Point = driver.getMemory().ids.point;
    expect(round2Point).not.toBe('old_point');
    expect(driver.getMemory().ids['group:person_c']).not.toBe('old_group');
    // 下一个决策是 pointPlan（不再有 allocate 步——sink 已折入 allocatedKeys）。
    expect(driver.pendingDecision()).toEqual({ kind: 'model', task: 'pointPlan', key: 'r2', input: expect.anything() });
    await driver.step(); // pointPlan 消费活内存的新 point
    expect(memory.plan![0].pointId).toBe(round2Point);
    // 第二次 continue（白盒装配：r2 是正在收尾的 automatic 轮——服务端处于
    // assess_continuation；conclude 之后服务端才切到 r3）。
    (driver as unknown as { memory: ControllerMemory }).memory.continuation = continueTo('r3');
    const concludingState = driver as unknown as { state: { world: WorldContext; control: ControlState } };
    concludingState.state.world = automaticWorld('r2', ['person_c']);
    concludingState.state.control = mkControl({ phase: 'assess_continuation', revision: 3 });
    await driver.step(); // conclude r2 → r3，sink 分配 product_round_r3
    const round3Point = driver.getMemory().ids.point;
    expect(round3Point).not.toBe(round2Point);
    expect(driver.getMemory().ids['group:person_c']).not.toBe('old_group');
    expect(allocated.get('product_round_r2')!.ids.point).not.toBe(allocated.get('product_round_r3')!.ids.point);
    expect(calls.map((entry) => entry.key)).toEqual(['product_round_r2', 'product_round_r3']);
    expect(driver.pendingDecision()).toEqual({ kind: 'model', task: 'pointPlan', key: 'r3', input: expect.anything() });
  });

  test('case 3: a complete pre-seed allocates before pointPlan; empty slots or a missing actor slot stop as incomplete', async () => {
    const player = playerWorld();
    const conclude = (world: WorldContext) => async (op: WorldOperation) => {
      if (op === 'round_conclusion_conclude') return { world, control: mkControl({ revision: 2 }), work: null,
        data: { kind: 'continue', roundId: 'r1', nextRoundId: 'r2' } } as never;
      if (op === 'allocate_ids') return { world, control: mkControl({ revision: 3 }), work: null,
        data: { allocations: [{ slotKey: 'point', id: 'pre_point' }, { slotKey: 'group:person_c', id: 'pre_group' }] } } as never;
      throw new Error(`unexpected ${op}`);
    };
    const complete = gateDriver({ execute: conclude(automaticWorld('r2', ['person_c'])) as never }, { generate: async () => { throw new Error('swap me'); } },
      memoryPending({ playerInput: null, continuation: continueTo('r2'),
        roundAllocations: { r2: { allocationKey: 'r2_slots', slots: [{ slotKey: 'point', kind: 'point' }, { slotKey: 'group:person_c', kind: 'group' }] } } }), player);
    swapModel(complete, livePointPlanModel(complete));
    await complete.step(); // conclude
    await complete.step(); // 预置入口的 allocate_ids（先于 pointPlan）
    expect(complete.getMemory().ids.point).toBe('pre_point');
    expect(complete.pendingDecision()).toEqual({ kind: 'model', task: 'pointPlan', key: 'r2', input: expect.anything() });
    await complete.step(); // pointPlan 用预置分配的新 point
    expect(complete.getMemory().plan![0].pointId).toBe('pre_point');

    const emptySlots = gateDriver({ execute: conclude(automaticWorld('r2', ['person_c'])) as never }, { generate: async () => { throw new Error('must not run'); } },
      memoryPending({ playerInput: null, continuation: continueTo('r2'),
        roundAllocations: { r2: { allocationKey: 'empty', slots: [] } }, allocatedKeys: ['empty'] }), player);
    await emptySlots.step();
    expect(await emptySlots.step()).toEqual({ kind: 'stop', reason: 'round_identity_incomplete:r2:point,group:person_c' });

    const missingActor = gateDriver({ execute: conclude(automaticWorld('r2', ['person_c'])) as never }, { generate: async () => { throw new Error('must not run'); } },
      memoryPending({ playerInput: null, continuation: continueTo('r2'),
        roundAllocations: { r2: { allocationKey: 'r2_slots', slots: [{ slotKey: 'point', kind: 'point' }] } }, allocatedKeys: ['r2_slots'],
        ids: { point: 'pre_point' } }), player);
    await missingActor.step();
    expect(await missingActor.step()).toEqual({ kind: 'stop', reason: 'round_identity_incomplete:r2:group:person_c' });
  });

  test('case 4: conclude timeout + in_progress + replay reuse identical requests and notify once; definitive rejection and exhaustion never do', async () => {
    const player = playerWorld();
    const requests: unknown[] = [];
    let mode = 0; // 0 timeout, 1 in_progress, 2 replay success
    const transport = { execute: async (op: WorldOperation, request: never) => {
      if (op !== 'round_conclusion_conclude') throw new Error(`unexpected ${op}`);
      requests.push(copy(request));
      if (mode === 0) { mode = 1; throw new WorldTimeoutError('lost receipt'); }
      if (mode === 1) { mode = 2; throw new WorldApiError({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 2, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation: null, requestId: (request as { requestId: Id }).requestId, worldId: 'w1', error: { code: 'request_in_progress', httpStatus: 409, retryable: true, clientAction: 'retry_same_request', details: {} } }); }
      return { world: automaticWorld('r2', ['person_c']), control: mkControl({ revision: 2 }), work: null, replayed: true,
        data: { kind: 'continue', roundId: 'r1', nextRoundId: 'r2' } } as never;
    } };
    const sinkCalls: Id[] = [];
    const driver = gateDriver(transport, { generate: async () => { throw new Error('must not run'); } },
      memoryPending({ continuation: continueTo('r2') }), player);
    driver.setRoundIdentitySink(async (roundId) => {
      sinkCalls.push(roundId);
      const slots = [{ slotKey: 'point', kind: 'point' as const }, { slotKey: 'group:person_c', kind: 'group' as const }];
      return { ids: { point: `point_${roundId}`, 'group:person_c': `group_${roundId}` },
        roundAllocations: { [roundId]: { allocationKey: `product_round_${roundId}`, slots } },
        allocatedKeys: [`product_round_${roundId}`] };
    });
    await driver.step();
    expect(requests).toHaveLength(3);
    expect(requests[0]).toEqual(requests[1]);
    expect(requests[1]).toEqual(requests[2]);
    expect(sinkCalls).toEqual(['r2']);
    expect(driver.getMemory().roundIdentityBlocked).toBeNull();

    const rejected = gateDriver({ execute: async (op: WorldOperation) => {
      if (op !== 'round_conclusion_conclude') throw new Error(`unexpected ${op}`);
      throw new WorldApiError({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 2, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation: null, requestId: 'req_1', worldId: 'w1', error: { code: 'request_id_reused', httpStatus: 409, retryable: false, clientAction: 'fix_request', details: {} } });
    } }, { generate: async () => { throw new Error('must not run'); } },
      memoryPending({ continuation: continueTo('r2') }), player);
    let rejectedSinks = 0;
    rejected.setRoundIdentitySink(async () => { rejectedSinks += 1; return undefined; });
    expect((await rejected.step())?.kind).toBe('stop');
    expect(rejectedSinks).toBe(0);
    expect(rejected.getMemory().continuation ?? null).not.toBeNull();

    const exhausted = gateDriver({ execute: async (op: WorldOperation) => {
      if (op !== 'round_conclusion_conclude') throw new Error(`unexpected ${op}`);
      throw new WorldTimeoutError('unknown fate');
    } }, { generate: async () => { throw new Error('must not run'); } },
      memoryPending({ continuation: continueTo('r2') }), player);
    let exhaustedSinks = 0;
    exhausted.setRoundIdentitySink(async () => { exhaustedSinks += 1; return undefined; });
    expect((await exhausted.step())?.kind).toBe('error');
    expect(exhaustedSinks).toBe(0);
  });

  test('case 5: a failing allocation blocks the entry before pointPlan and never silently advances', async () => {
    const player = playerWorld();
    const transport = { execute: async (op: WorldOperation) => (op === 'round_conclusion_conclude'
      ? { world: automaticWorld('r2', ['person_c']), control: mkControl({ revision: 2 }), work: null,
          data: { kind: 'continue', roundId: 'r1', nextRoundId: 'r2' } } as never
      : Promise.reject(new Error(`unexpected ${op}`))) };
    const driver = gateDriver(transport, { generate: async () => { throw new Error('pointPlan must not run'); } },
      memoryPending({ continuation: continueTo('r2') }), player);
    driver.setRoundIdentitySink(async () => { throw new WorldTimeoutError('allocation receipt lost'); });
    await driver.step();
    expect(driver.getMemory().roundIdentityBlocked).toBe('sink_failed:r2:allocation receipt lost');
    expect(await driver.step()).toEqual({ kind: 'stop', reason: 'round_identity_blocked:sink_failed:r2:allocation receipt lost' });
    expect(driver.getMemory().ids.point).toBe('old_point');
  });

  test('case 6: the patch contract is three identity fields — extra memory fields are refused, real deltas preserve recovered identities', async () => {
    const player = playerWorld();
    const transport = { execute: async (op: WorldOperation) => (op === 'round_conclusion_conclude'
      ? { world: automaticWorld('r2', ['person_c']), control: mkControl({ revision: 2 }), work: null,
          data: { kind: 'continue', roundId: 'r1', nextRoundId: 'r2' } } as never
      : Promise.reject(new Error(`unexpected ${op}`))) };
    const memory = memoryPending({ continuation: continueTo('r2') });
    memory.ids = { point: 'recovered_point', 'group:person_c': 'recovered_group' };
    memory.allocatedKeys = ['existing_key'];
    memory.budget.used = 7;
    const driver = gateDriver(transport, { generate: async () => { throw new Error('must not run'); } }, memory, player);
    // 夹带 budget 的整包式补丁：预算不得被覆盖，extra 记诊断；身份三字段照常折入。
    driver.setRoundIdentitySink(async (roundId) => ({ ids: { point: 'fresh_point', 'group:person_c': 'fresh_group' },
      roundAllocations: { [roundId]: { allocationKey: `product_round_${roundId}`, slots: [] } }, allocatedKeys: [`product_round_${roundId}`],
      budget: { used: 0, max: null } } as never));
    await driver.step();
    expect(driver.getMemory()).toMatchObject({ ids: { point: 'fresh_point', 'group:person_c': 'fresh_group' }, budget: { used: 7 } });
    expect(driver.getMemory().lastRoundIdentityError).toBe('round_identity_patch_extra_fields:budget');
    // 真实增量：只声明新键时，既有身份与 keys 原样保留。
    const delta = gateDriver(transport, { generate: async () => { throw new Error('must not run'); } },
      memoryPending({ continuation: continueTo('r2') }), player);
    (delta as unknown as { memory: ControllerMemory }).memory.ids = { point: 'recovered_point', 'group:person_c': 'recovered_group' };
    (delta as unknown as { memory: ControllerMemory }).memory.allocatedKeys = ['existing_key'];
    delta.setRoundIdentitySink(async (roundId) => ({ ids: { 'group:person_c': 'fresh_group' },
      roundAllocations: { [roundId]: { allocationKey: `product_round_${roundId}`, slots: [] } }, allocatedKeys: [`product_round_${roundId}`] }));
    await delta.step();
    expect(delta.getMemory()).toMatchObject({ ids: { point: 'recovered_point', 'group:person_c': 'fresh_group' }, allocatedKeys: ['existing_key', 'product_round_r2'] });
  });

  test('case 6b (review P2): declared-complete slots and keys cannot borrow stale ids — the patch must carry them', async () => {
    const player = playerWorld();
    const transport = { execute: async (op: WorldOperation) => (op === 'round_conclusion_conclude'
      ? { world: automaticWorld('r2', ['person_c']), control: mkControl({ revision: 2 }), work: null,
          data: { kind: 'continue', roundId: 'r1', nextRoundId: 'r2' } } as never
      : Promise.reject(new Error(`unexpected ${op}`))) };
    const build = (ids: Record<Id, Id> | undefined) => {
      const driver = gateDriver(transport, { generate: async () => { throw new Error('pointPlan must not run'); } },
        memoryPending({ continuation: continueTo('r2') }), player);
      driver.setRoundIdentitySink(async (roundId) => ({
        ...(ids ? { ids } : {}),
        roundAllocations: { [roundId]: { allocationKey: `product_round_${roundId}`,
          slots: [{ slotKey: 'point', kind: 'point' }, { slotKey: 'group:person_c', kind: 'group' }] } },
        allocatedKeys: [`product_round_${roundId}`],
      }));
      return driver;
    };
    // 反例一：声明完整 + key 已折入，但补丁完全不带 ids——旧 point/group 不得冒充本轮结果。
    const noIds = build(undefined);
    await noIds.step();
    expect(noIds.getMemory().roundIdentityBlocked).toBe('incomplete:r2:point,group:person_c');
    expect(noIds.getMemory().ids).toMatchObject({ point: 'old_point', 'group:person_c': 'old_group' });
    expect(await noIds.step()).toEqual({ kind: 'stop', reason: 'round_identity_blocked:incomplete:r2:point,group:person_c' });

    // 反例二：patch.ids 缺一名 actor——只缺的槽位进入阻断明细。
    const missingActor = build({ point: 'fresh_point' });
    await missingActor.step();
    expect(missingActor.getMemory().roundIdentityBlocked).toBe('incomplete:r2:group:person_c');
    expect(await missingActor.step()).toEqual({ kind: 'stop', reason: 'round_identity_blocked:incomplete:r2:group:person_c' });
  });

  test('case 8: an automatic handback allocates nothing and leaves no blocked state', async () => {
    const player = playerWorld();
    const handbackWorld: WorldContext = { ...automaticWorld('r2', ['person_c']),
      round: { roundId: 'r2', trigger: 'automatic', order: ['person_c'], cursor: 0, actedIds: [], visitedIds: [], conclusion: { kind: 'handback', closedBy: 'model', cancelReason: null } } };
    const transport = { execute: async (op: WorldOperation) => (op === 'round_conclusion_conclude'
      ? { world: handbackWorld, control: mkControl({ phase: 'complete', revision: 2 }), work: null,
          data: { kind: 'handback', roundId: 'r1', nextRoundId: null } } as never
      : Promise.reject(new Error(`unexpected ${op}`))) };
    let sinkCalls = 0;
    const driver = gateDriver(transport, { generate: async () => { throw new Error('must not run'); } },
      memoryPending({ continuation: handbackConclusion }), player);
    driver.setRoundIdentitySink(async () => { sinkCalls += 1; return undefined; });
    await driver.step();
    expect(sinkCalls).toBe(0);
    expect(driver.getMemory().roundIdentityBlocked).toBeNull();
    expect(driver.getMemory().continuation).toBeNull();
  });
});
