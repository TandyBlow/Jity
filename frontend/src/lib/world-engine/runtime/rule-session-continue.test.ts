// G5 会话级验收（预审 2026-10-29 用例 7）：真实产品 sink + 真实
// readControllerRecovery，覆盖「continue 已提交但 point 未创建」与
// 「group 分配已提交但尚未折入本地」两个刷新/接管窗口。确定性桩，
// 不含真实 HTTP/SQLite 与模型 continuation（另行调度）。
import { describe, expect, test } from 'vitest';
import recoverySuccess from '../../../../../design/world-protocol/v2/fixtures/branches/recovery.success.json';
import stateSuccess from '../../../../../design/world-protocol/v2/fixtures/api/get_state/success.json';
import { RuleWorldSession } from './rule-session';
import type { CommittedRead } from './committed-narration';
import type { Id, InitialTemplate, Json, RequestMap, WorldOperation } from '../types';
import { WorldApiError } from '../transport';
import { errorCatalog } from '../schedule';

const copy = <T>(value: T): T => structuredClone(value);
const ORDER = ['person_c'];

const minimalPolicy = {
  routes: [], sanity: { minimum: 0, maximum: 10, effects: { strain: -2, recover: 1 }, milestones: {
    strain: { taskId: 't1', goal: 'g1', requiredLocationId: 'corridor', minimumElapsedSeconds: 1, personalityText: 'p1' },
    recover: { taskId: 't2', goal: 'g2', requiredLocationId: 'corridor', minimumElapsedSeconds: 1, personalityText: 'p2' },
  } },
} as unknown as Parameters<typeof RuleWorldSession.createNew>[0]['policy'];
const minimalInitial = {
  engineVersion: 'world-engine-v1', schemaVersion: 1, protagonistId: 'person_c', initialTime: { calendar: 'gregorian', dateTime: 'day 1 08:00', instantOrdinal: 1 },
  locations: {}, items: {}, characters: { person_c: { id: 'person_c', name: '丙', initialPosition: { containerId: 'hall' }, initialAppearance: '', initialPersonality: '', initialSanity: 10, tasks: {} } },
} as unknown as InitialTemplate;

/** automatic 轮刚开启、尚未建点的恢复快照（真实 readControllerRecovery 可读）；
 * fenceEpoch 参数化以模拟接管后的新租约代际。 */
const entryContext = (fenceEpoch = 7) => {
  const c = copy(recoverySuccess) as unknown as { world: Record<string, unknown>; control: { phase: string }; work: unknown; recovery: unknown; [key: string]: unknown };
  c.world.activePointId = null;
  c.world.successor = null;
  c.work = null;
  const round = c.world.round as { roundId: Id; trigger: string; order: Id[]; cursor: number; actedIds: Id[]; visitedIds: Id[]; conclusion: unknown };
  round.roundId = 'r2';
  round.trigger = 'automatic';
  round.order = [...ORDER];
  round.cursor = 0;
  round.actedIds = [];
  round.visitedIds = [];
  round.conclusion = null;
  (c.world.advance as { intentStatus: string }).intentStatus = 'consumed';
  c.world.activeRoundId = 'r2';
  c.world.lease = { fenceEpoch, expiresAtEpochMilli: 1 };
  c.recovery = { fenceEpoch, current: null, successor: null };
  c.control.phase = 'select_actor';
  return c;
};

interface Registry { ids: Record<Id, Record<Id, Id>>; calls: { key: Id; slots: { slotKey: Id; kind: string }[] }[]; freshKeys: Set<Id> }
/** 幂等分配注册表：同 key 重放同一批 id；只有新 key 消费新 id。 */
const registry = (preCommitted: Record<Id, Record<Id, Id>> = {}): Registry => {
  const ids: Record<Id, Record<Id, Id>> = copy(preCommitted);
  const calls: { key: Id; slots: { slotKey: Id; kind: string }[] }[] = [];
  const freshKeys = new Set<Id>();
  return { ids, calls, freshKeys };
};

const sessionTransport = (entry: () => ReturnType<typeof entryContext>, reg: Registry, requests: { op: WorldOperation; body: unknown }[]) => {
  const state = copy((stateSuccess as { data: { state: unknown } }).data.state);
  return {
    execute: async (op: WorldOperation, body: never): Promise<never> => {
      requests.push({ op, body: copy(body) });
      const base = () => ({ world: entry().world, control: entry().control, work: null });
      if (op === 'lease_acquire') return { ...base(), data: { leaseToken: 'fresh_lease', fenceEpoch: 7, expiresAtEpochMilli: 1, holderId: 'x' } } as never;
      if (op === 'get_context') return copy(entry()) as never;
      if (op === 'list_points') return { ...base(), data: { points: [{ pointId: (entry().world as { head: { pointId: Id } }).head.pointId, sequence: 0, stateDigest: (entry().world as { head: { stateDigest: string } }).head.stateDigest, kind: 'root', roundId: null, advanceId: null }] } } as never;
      if (op === 'get_state') return { ...base(), data: { pointId: (entry().world as { head: { pointId: Id } }).head.pointId, version: 0, stateDigest: (entry().world as { head: { stateDigest: string } }).head.stateDigest, state, previousPointId: null, timeAdvance: null, entityDeltas: {} } } as never;
      if (op === 'allocate_ids') {
        const request = body as unknown as RequestMap['allocate_ids'];
        const slotList = request.slots.map((slot) => ({ slotKey: slot.slotKey, kind: slot.kind as string }));
        reg.calls.push({ key: request.allocationKey, slots: slotList });
        let batch = reg.ids[request.allocationKey];
        if (!batch) {
          batch = Object.fromEntries(request.slots.map((slot, index) => [slot.slotKey, `srv_${request.allocationKey}_${index}`]));
          reg.ids[request.allocationKey] = batch;
          reg.freshKeys.add(request.allocationKey);
        }
        return { ...base(), data: { allocations: request.slots.map((slot) => ({ slotKey: slot.slotKey, id: batch![slot.slotKey] })) } } as never;
      }
      if (op === 'checkpoint_begin_point') {
        // 用冻结目录自身的值构造拒绝（控制器会核对信封与目录一致）。
        const entry = errorCatalog.request_malformed;
        throw new WorldApiError({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 2, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation: null, requestId: (body as { requestId: Id }).requestId, worldId: 'world_school', error: { code: 'request_malformed', httpStatus: entry.httpStatus, retryable: entry.retryable, clientAction: entry.clientAction, details: {} } });
      }
      throw new Error(`unexpected transport op ${op}`);
    },
  } as never;
};

describe('G5 refresh windows through the real product sink and real recovery (pre-audit case 7)', () => {
  test('case 7a: continue committed but point not created — a fresh session re-provisions the entry and plans the NEW point', async () => {
    const reg = registry();
    const requests: { op: WorldOperation; body: unknown }[] = [];
    const session = RuleWorldSession.createRecovered(
      { transport: sessionTransport(entryContext, reg, requests), initial: minimalInitial, policy: minimalPolicy }, 'world_school');
    const status = await session.attach();
    // 恢复入口恰好补调一次分配：key 按轮稳定、槽位覆盖 point + 冻结 order 逐人 group。
    expect(reg.calls).toHaveLength(1);
    expect(reg.calls[0].key).toBe('product_round_r2');
    expect(reg.calls[0].slots.map((slot) => slot.slotKey).sort()).toEqual(['group:person_c', 'point']);
    const memory = session.getMemory();
    const newPoint = reg.ids['product_round_r2'].point;
    expect(memory.ids.point).toBe(newPoint);
    expect(memory.roundIdentityBlocked).toBeNull();
    // 产品 pointPlan（规则权威端口）消费的是新 point，begin_point 请求携带同一 id。
    expect(memory.plan).not.toBeNull();
    expect(memory.plan![0].pointId).toBe(newPoint);
    const begin = requests.find((entry) => entry.op === 'checkpoint_begin_point');
    expect((begin?.body as { pointId: Id }).pointId).toBe(newPoint);
    expect((status as { kind: string }).kind).toBe('stop');
    session.dispose();
  });

  test('case 7b: a group allocation committed but never folded replays the SAME batch — no new consumption', async () => {
    const committed = { point: 'committed_point', 'group:person_c': 'committed_group' };
    const reg = registry({ product_round_r2: committed });
    const requests: { op: WorldOperation; body: unknown }[] = [];
    const session = RuleWorldSession.createRecovered(
      { transport: sessionTransport(entryContext, reg, requests), initial: minimalInitial, policy: minimalPolicy }, 'world_school');
    await session.attach();
    // 补调发生，但服务端按 key 幂等重放已提交批次——id 计数零新增。
    expect(reg.calls).toHaveLength(1);
    expect(reg.freshKeys.size).toBe(0);
    const memory = session.getMemory();
    expect(memory.ids.point).toBe('committed_point');
    expect(memory.ids['group:person_c']).toBe('committed_group');
    expect(memory.plan![0].pointId).toBe('committed_point');
    session.dispose();
  });
});

describe('G5 review fixes (669582d follow-up): request namespace, session isolation, patch-carried ids', () => {
  const state = copy((stateSuccess as { data: { state: unknown } }).data.state);
  const until = async (predicate: () => boolean): Promise<void> => {
    for (let i = 0; i < 200 && !predicate(); i += 1) await new Promise((done) => setTimeout(done, 5));
  };
  const reject = (requestId: Id, code: 'request_malformed' | 'request_id_reused' | 'lease_invalid'): never => {
    const entry = errorCatalog[code];
    throw new WorldApiError({ protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 2, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation: null, requestId, worldId: 'world_school', error: { code, httpStatus: entry.httpStatus, retryable: entry.retryable, clientAction: entry.clientAction, details: {} } });
  };
  /** 双层幂等桩服务端：先验请求幂等（同 requestId 不同正文 = request_id_reused），
   * 再做 allocationKey 业务重放（同 key 永远同一批 id，只有新 key 铸新 id）。 */
  const makeServer = () => {
    const requestBodies = new Map<Id, string>();
    const batches = new Map<Id, Record<Id, Id>>();
    let minted = 0;
    return {
      batches,
      mintedCount: () => minted,
      allocate: (body: { requestId: Id; leaseToken: Id; fenceEpoch: number; allocationKey: Id; slots: { slotKey: Id }[] }):
        { ok: true; data: { allocations: { slotKey: Id; id: Id }[] } } | { ok: false; error: 'request_id_reused' } => {
        const canonical = JSON.stringify([body.leaseToken, body.fenceEpoch, body.allocationKey, body.slots]);
        const seen = requestBodies.get(body.requestId);
        if (seen !== undefined) {
          if (seen !== canonical) return { ok: false, error: 'request_id_reused' };
        } else {
          requestBodies.set(body.requestId, canonical);
          let batch = batches.get(body.allocationKey);
          if (!batch) {
            minted += 1;
            batch = Object.fromEntries(body.slots.map((slot, index) => [slot.slotKey, `srv_${minted}_${index}`]));
            batches.set(body.allocationKey, batch);
          }
        }
        const batch = batches.get(body.allocationKey)!;
        return { ok: true, data: { allocations: body.slots.map((slot) => ({ slotKey: slot.slotKey, id: batch[slot.slotKey] })) } };
      },
    };
  };
  /** 每会话一个 transport：租约按 token/epoch 供给，allocate 走共享服务端。 */
  const takeoverTransport = (server: ReturnType<typeof makeServer>, token: Id, fenceEpoch: number, requests: { op: WorldOperation; body: unknown }[]) => ({
    execute: async (op: WorldOperation, body: never): Promise<never> => {
      requests.push({ op, body: copy(body) });
      const snapshot = entryContext(fenceEpoch);
      const head = (snapshot.world as { head: { pointId: Id; stateDigest: string } }).head;
      const base = () => ({ world: snapshot.world, control: snapshot.control, work: null });
      if (op === 'lease_acquire') return { ...base(), data: { leaseToken: token, fenceEpoch, expiresAtEpochMilli: 1, holderId: 'x' } } as never;
      if (op === 'get_context') return snapshot as never;
      if (op === 'list_points') return { ...base(), data: { points: [{ pointId: head.pointId, sequence: 0, stateDigest: head.stateDigest, kind: 'root', roundId: null, advanceId: null }] } } as never;
      if (op === 'get_state') return { ...base(), data: { pointId: head.pointId, version: 0, stateDigest: head.stateDigest, state, previousPointId: null, timeAdvance: null, entityDeltas: {} } } as never;
      if (op === 'allocate_ids') {
        const request = body as unknown as { requestId: Id; leaseToken: Id; fenceEpoch: number; allocationKey: Id; slots: { slotKey: Id }[] };
        const result = server.allocate(request);
        if (!result.ok) reject(request.requestId, result.error);
        return { ...base(), data: (result as { ok: true; data: { allocations: { slotKey: Id; id: Id }[] } }).data } as never;
      }
      if (op === 'checkpoint_begin_point') reject((body as { requestId: Id }).requestId, 'request_malformed');
      throw new Error(`unexpected transport op ${op}`);
    },
  } as never);
  const driverBlockedDetail = (session: RuleWorldSession): string | null => session.getMemory().roundIdentityBlocked;
  const recoverAndPlan = async (transport: never): Promise<RuleWorldSession> => {
    const session = RuleWorldSession.createRecovered(
      { transport, initial: minimalInitial, policy: minimalPolicy }, 'world_school');
    await session.attach();
    return session;
  };

  test('takeover: a new session re-provisions the same round under its own request namespace and replays the batch by allocation key', async () => {
    const server = makeServer();
    const requestsA: { op: WorldOperation; body: unknown }[] = [];
    const requestsB: { op: WorldOperation; body: unknown }[] = [];
    const sessionA = await recoverAndPlan(takeoverTransport(server, 'lease_old', 7, requestsA) as never);
    const sessionB = await recoverAndPlan(takeoverTransport(server, 'lease_new', 8, requestsB) as never);
    const allocA = requestsA.filter((entry) => entry.op === 'allocate_ids');
    const allocB = requestsB.filter((entry) => entry.op === 'allocate_ids');
    expect(allocA).toHaveLength(1);
    expect(allocB).toHaveLength(1);
    const bodyA = allocA[0].body as { requestId: Id; leaseToken: Id; fenceEpoch: number };
    const bodyB = allocB[0].body as { requestId: Id; leaseToken: Id; fenceEpoch: number };
    // 会话独立命名空间：同轮补调的 requestId 不碰撞（旧实现同为 *_r2_1，
    // 换租约正文即 request_id_reused，业务重放根本到不了）。
    expect(bodyA.requestId).not.toBe(bodyB.requestId);
    expect(bodyA.leaseToken).toBe('lease_old');
    expect(bodyB.leaseToken).toBe('lease_new');
    expect(bodyB.fenceEpoch).toBe(8);
    // 业务幂等：同一 allocationKey 只铸一批，两个会话拿到同一批 id。
    expect(server.mintedCount()).toBe(1);
    const batch = server.batches.get('product_round_r2')!;
    expect(sessionA.getMemory().ids.point).toBe(batch.point);
    expect(sessionB.getMemory().ids.point).toBe(batch.point);
    expect(sessionB.getMemory().roundIdentityBlocked).toBeNull();
    // B 的终点是身份链贯通后的 begin 截断，而不是身份阻断。
    sessionA.dispose();
    sessionB.dispose();
  });

  test('isolation: a hung allocation cannot hold attach hostage after stop, and a late success is never folded', async () => {
    let release: ((value: unknown) => void) | null = null;
    let allocateSeen = false;
    const hang = new Promise<never>((resolve) => { release = resolve as never; });
    const snapshot = entryContext(7);
    const transport = {
      execute: async (op: WorldOperation, body: never): Promise<never> => {
        const hangHead = (snapshot.world as { head: { pointId: Id; stateDigest: string } }).head;
        const base = () => ({ world: snapshot.world, control: snapshot.control, work: null });
        if (op === 'lease_acquire') return { ...base(), data: { leaseToken: 'lease_old', fenceEpoch: 7, expiresAtEpochMilli: 1, holderId: 'x' } } as never;
        if (op === 'get_context') return snapshot as never;
        if (op === 'list_points') return { ...base(), data: { points: [{ pointId: hangHead.pointId, sequence: 0, stateDigest: hangHead.stateDigest, kind: 'root', roundId: null, advanceId: null }] } } as never;
        if (op === 'get_state') return { ...base(), data: { pointId: hangHead.pointId, version: 0, stateDigest: hangHead.stateDigest, state, previousPointId: null, timeAdvance: null, entityDeltas: {} } } as never;
        if (op === 'allocate_ids') { allocateSeen = true; return hang as never; }
        throw new Error(`unexpected transport op ${op}`);
      },
    } as never;
    const session = RuleWorldSession.createRecovered(
      { transport, initial: minimalInitial, policy: minimalPolicy }, 'world_school');
    const attached = session.attach();
    await until(() => allocateSeen);
    session.stop();
    const outcome = await Promise.race([
      attached.then(() => 'settled', () => 'rejected'),
      new Promise<'hung'>((done) => setTimeout(() => done('hung'), 250)),
    ]);
    expect(outcome).toBe('settled');
    // 迟到成功放行：已停止会话的内存不得折入。
    release!({ data: { allocations: [{ slotKey: 'point', id: 'late_point' }, { slotKey: 'group:person_c', id: 'late_group' }] } });
    await new Promise((done) => setTimeout(done, 20));
    expect(session.getMemory().ids.point).toBeUndefined();
    expect(session.sessionStatus).toBe('stopped');
  });

  test('isolation: lease_invalid from the allocation is observed by the session lease layer (heartbeat stopped, round blocked)', async () => {
    // 观察层证据（复审 P1 修正要求）：分配错误信封必须进入会话租约观察层
    // ——observe 对 lease_invalid 停掉租约心跳。给授权一个短有效期：心跳若
    // 未被停，renew 会在观察后立即出现；修复后一次都不应出现。
    const snapshot = entryContext(7);
    const renewals: number[] = [];
    const transport = {
      execute: async (op: WorldOperation, body: never): Promise<never> => {
        const head = (snapshot.world as { head: { pointId: Id; stateDigest: string } }).head;
        const base = () => ({ world: snapshot.world, control: snapshot.control, work: null });
        if (op === 'lease_acquire') return { ...base(), data: { leaseToken: 'lease_old', fenceEpoch: 7, expiresAtEpochMilli: Date.now() + 40, holderId: 'x' } } as never;
        if (op === 'lease_renew') { renewals.push(Date.now()); return { ...base(), data: { leaseToken: 'lease_old', fenceEpoch: 7, expiresAtEpochMilli: Date.now() + 40 } } as never; }
        if (op === 'get_context') return snapshot as never;
        if (op === 'list_points') return { ...base(), data: { points: [{ pointId: head.pointId, sequence: 0, stateDigest: head.stateDigest, kind: 'root', roundId: null, advanceId: null }] } } as never;
        if (op === 'get_state') return { ...base(), data: { pointId: head.pointId, version: 0, stateDigest: head.stateDigest, state, previousPointId: null, timeAdvance: null, entityDeltas: {} } } as never;
        if (op === 'allocate_ids') reject((body as { requestId: Id }).requestId, 'lease_invalid');
        throw new Error(`unexpected transport op ${op}`);
      },
    } as never;
    const session = RuleWorldSession.createRecovered(
      // 租约 40ms 有效、lead 5s → 授权落定即调度一次 renew；lease_invalid 的
      // observe 会停掉租约心跳，该 renew 不应发生。
      { transport, initial: minimalInitial, policy: minimalPolicy, heartbeatLeadMs: 5_000 }, 'world_school');
    const status = await session.attach();
    // 分配失败进入身份屏障（错误正文原样穿透观察层——driver 路径的
    // lease_invalid 属可 reacquire 族，隔离错误只留给 stop/失租终态）。
    expect(driverBlockedDetail(session)).toBe('sink_failed:r2:lease_invalid');
    expect((status as { reason?: string }).reason).toBe('round_identity_blocked:sink_failed:r2:lease_invalid');
    await new Promise((done) => setTimeout(done, 200));
    expect(renewals).toEqual([]);
    expect(session.sessionStatus).toBe('idle');
  });
});
