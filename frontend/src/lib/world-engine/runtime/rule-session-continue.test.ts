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

/** automatic 轮刚开启、尚未建点的恢复快照（真实 readControllerRecovery 可读）。 */
const entryContext = () => {
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
  c.recovery = { fenceEpoch: 7, current: null, successor: null };
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
