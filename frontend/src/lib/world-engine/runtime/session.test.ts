import { describe, expect, test, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { WorldSession, type DriverLike } from './session';
import type { ControllerIo, DriverStatus } from '../controller';
import { initialMemory } from '../controller';
import type { CompleteOptions, InferenceEngine } from './engine';
import { RuntimeWorldModelPort } from './model-port';
import { WorldApiError, WorldTimeoutError } from '../transport';
import type { HeartbeatClock } from './heartbeat';
import type { ModelTask } from '../schedule';
import type { Id, Json, Scope, WorldOperation } from '../types';

/** Deterministic clock (same semantics as the heartbeat tests). */
class ManualClock implements HeartbeatClock {
  private nowMs = 0;
  private seq = 0;
  private readonly timers: { at: number; fn: () => void; cancelled: boolean; seq: number }[] = [];
  now(): number { return this.nowMs; }
  set(delayMs: number, fn: () => void): () => void {
    const entry = { at: this.nowMs + Math.max(0, delayMs), fn, cancelled: false, seq: this.seq++ };
    this.timers.push(entry);
    return () => { entry.cancelled = true; };
  }
  advance(ms: number): void {
    const target = this.nowMs + ms;
    for (;;) {
      const due = this.timers.filter((t) => !t.cancelled && t.at <= target).sort((a, b) => a.at - b.at || a.seq - b.seq)[0];
      if (!due) break;
      this.nowMs = due.at;
      due.cancelled = true;
      due.fn();
    }
    this.nowMs = target;
  }
}

async function settle(): Promise<void> {
  for (let i = 0; i < 6; i++) await Promise.resolve();
}

/** Scripted engine: pops one raw output per completion; hold keeps every
 * completion pending until flush. */
function fakeEngine(outputs: string[]) {
  const calls: Array<{ prompt: string; options?: CompleteOptions }> = [];
  const pending: Array<() => void> = [];
  let loads = 0;
  let loadPromise: Promise<void> | null = null;
  let hold = false;
  const engine: InferenceEngine = {
    info: { backend: 'fake', modelId: 'fake.gguf' },
    load: () => {
      loadPromise ??= (async () => { loads += 1; })();
      return loadPromise;
    },
    complete: (prompt, options) => {
      calls.push({ prompt, options });
      const text = outputs.shift() ?? '';
      if (!hold) return Promise.resolve(text);
      return new Promise<string>((resolve) => pending.push(() => resolve(text)));
    },
    dispose: async () => {},
  };
  return {
    engine, calls,
    get loads() { return loads; },
    hold(value: boolean) { hold = value; },
    flush() { for (const release of pending.splice(0)) release(); },
    get pendingCount() { return pending.length; },
  };
}

type ScriptStep =
  | { kind: 'transport'; op: WorldOperation; request: Record<string, unknown>; scope: Scope; respond: () => unknown | Promise<unknown>; done?: boolean }
  | { kind: 'model'; task: ModelTask; key: string; input: Json }
  | { kind: 'terminal'; status: DriverStatus };

/** Scripted driver double: exercises the session's REAL observed transport
 * and signal-bound model port — the wiring under test. */
class ScriptedDriver implements DriverLike {
  private index = 0;
  readonly memory = initialMemory('req_session_test', 'test');
  constructor(private readonly script: ScriptStep[], private readonly io: ControllerIo) {}
  deliver(): void {}
  getMemory() { return this.memory; }
  async step(): Promise<DriverStatus | undefined> {
    const entry = this.script[this.index++];
    if (!entry) return { kind: 'await', reason: 'script exhausted' };
    if (entry.kind === 'terminal') return entry.status;
    if (entry.kind === 'model') {
      await this.io.model.generate(entry.task, entry.key, entry.input);
      return undefined;
    }
    await this.io.transport.execute(entry.op, entry.request as never, entry.scope as never);
    return undefined;
  }
}

function envelope(worldId: Id, lease: { fenceEpoch: number; expiresAtEpochMilli: number } | null) {
  return { world: { worldId, lease } };
}

function createWorldResponse(worldId: Id, expiresAtEpochMilli: number) {
  return {
    ...envelope(worldId, { fenceEpoch: 1, expiresAtEpochMilli }),
    data: { worldId, rootPointId: 'root_0', lease: { leaseToken: 'lease_1', fenceEpoch: 1, expiresAtEpochMilli } },
  };
}

function claimResponse(pointId: Id, generation: number, claimToken: Id, expiresAtEpochMilli: number, replayed = false) {
  return {
    replayed,
    data: { pointId, mode: 'head', generation, fenceEpoch: 1, issuedAtEpochMilli: 1_000, expiresAtEpochMilli, claimToken },
  };
}

function apiError(code: string): WorldApiError {
  return new WorldApiError({
    protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1',
    serverTimeEpochMilli: 1, replayed: false, operation: null, requestId: null, worldId: 'w1',
    world: null, control: null, work: null,
    error: { code, httpStatus: 409, retryable: false, clientAction: 'none', details: {} },
  } as never);
}

function harness(script: ScriptStep[], engineOutputs: string[], renew: { lease?: (request: unknown) => unknown | Promise<unknown>; claim?: (request: unknown) => unknown | Promise<unknown>; acquire?: (request: unknown) => unknown | Promise<unknown> } = {}) {
  const clock = new ManualClock();
  const engine = fakeEngine(engineOutputs);
  const port = new RuntimeWorldModelPort(engine.engine);
  const transportLog: Array<{ op: WorldOperation; request: Record<string, unknown>; scope: Scope }> = [];
  const leaseRenew = renew.lease ?? (() => ({ data: { leaseToken: 'lease_1', fenceEpoch: 1, expiresAtEpochMilli: 1_000_000 } }));
  const claimRenew = renew.claim ?? (() => ({ data: { pointId: 'root_0', mode: 'head', generation: 1, fenceEpoch: 1, issuedAtEpochMilli: 1_000, expiresAtEpochMilli: 1_000_000 } }));
  const raw = {
    async execute(op: WorldOperation, request: Record<string, unknown>, scope: Scope): Promise<unknown> {
      transportLog.push({ op, request, scope });
      if (op === 'lease_renew') return leaseRenew(request) as never;
      if (op === 'narration_claim_renew') return claimRenew(request) as never;
      if (op === 'get_state') {
        // 组装阶梯的读取：返回请求点自身记录（夹具世界=单根点，前驱恒 null）。
        const pointId = (request.point as string) ?? 'root_0';
        const state = { engineVersion: 'world-engine-v1', schemaVersion: 1, worldId: 'w1', protagonistId: 'person_c', time: { calendar: 'gregorian', dateTime: '2026-01-01T11:59:00', instantOrdinal: 0 }, initial: { worldId: 'w1', engineVersion: 'world-engine-v1', schemaVersion: 1, protagonistId: 'person_c', initialTime: { calendar: 'gregorian', dateTime: '2026-01-01T11:59:00', instantOrdinal: 0 }, locations: {}, items: {}, characters: { person_c: { id: 'person_c', name: 'C', initialPosition: { containerId: 'w1', slotId: null, relativeTo: null }, initialAppearance: '刚到', initialPersonality: '好奇', initialSanity: 10, tasks: {} } } }, locations: {}, items: {}, characters: {} };
        return { data: { pointId, version: 0, state, stateDigest: 'd0', previousPointId: null, timeAdvance: null, entityDeltas: {} } };
      }
      if (op === 'lease_acquire') {
        if (!renew.acquire) throw new Error(`unexpected transport call ${op}`);
        return renew.acquire(request) as never;
      }
      const entry = script.find((step) => step.kind === 'transport' && step.op === op && !step.done);
      if (!entry || entry.kind !== 'transport') throw new Error(`unexpected transport call ${op}`);
      entry.done = true;
      return entry.respond() as never;
    },
  };
  const hooks = { statuses: [] as DriverStatus[], leaseLost: [] as string[], claimLost: [] as unknown[] };
  const session = new WorldSession(raw as never, port, {
    clock,
    createDriver: (io) => new ScriptedDriver(script, io),
    hooks: {
      onStatus: (status) => hooks.statuses.push(status),
      onLeaseLost: (loss) => hooks.leaseLost.push(loss),
      onClaimLost: (loss) => hooks.claimLost.push(loss),
    },
  });
  return { clock, engine, port, transportLog, hooks, session, script };
}

const MODEL_NARRATION: ScriptStep[] = [];
void MODEL_NARRATION;

describe('WorldSession assembly', () => {
  test('envelopes alone start, update and stop both heartbeats', async () => {
    const h = harness([
      { kind: 'transport', op: 'create_world', request: {}, scope: {}, respond: () => createWorldResponse('w1', 120_000) },
      { kind: 'model', task: 'narration', key: 'root_0', input: { pointId: 'root_0', stateDigest: 'd' } },
      { kind: 'transport', op: 'narration_claim', request: { pointId: 'root_0' }, scope: { worldId: 'w1', pointId: 'root_0' }, respond: () => claimResponse('root_0', 1, 'claim_1', 60_000) },
      { kind: 'terminal', status: { kind: 'await', reason: 'awaiting player input' } },
    ], ['叙事正文']);
    expect(await h.session.run()).toEqual({ kind: 'await', reason: 'awaiting player input' });
    h.clock.advance(30_000); // claim expiry 60k − lead 30k
    await settle();
    const claimRenews = h.transportLog.filter((entry) => entry.op === 'narration_claim_renew');
    expect(claimRenews).toHaveLength(1);
    expect(claimRenews[0]!.request.claimToken).toBe('claim_1');
    h.clock.advance(60_000); // lease expiry 120k − 30k
    await settle();
    const leaseRenews = h.transportLog.filter((entry) => entry.op === 'lease_renew');
    expect(leaseRenews).toHaveLength(1);
    expect(leaseRenews[0]!.request.leaseToken).toBe('lease_1');
  });

  test('submitting the narration stops the claim heartbeat; the lease keeps beating', async () => {
    const h = harness([
      { kind: 'transport', op: 'create_world', request: {}, scope: {}, respond: () => createWorldResponse('w1', 120_000) },
      { kind: 'transport', op: 'narration_claim', request: { pointId: 'root_0' }, scope: { worldId: 'w1', pointId: 'root_0' }, respond: () => claimResponse('root_0', 1, 'claim_1', 60_000) },
      { kind: 'transport', op: 'narration_submit', request: { pointId: 'root_0' }, scope: { worldId: 'w1', pointId: 'root_0' }, respond: () => ({ data: { pointId: 'root_0', narrationStatus: 'ready', generation: 1 } }) },
      { kind: 'terminal', status: { kind: 'stop', reason: 'done' } },
    ], []);
    expect(await h.session.run()).toEqual({ kind: 'stop', reason: 'done' });
    h.clock.advance(150_000);
    await settle();
    expect(h.transportLog.filter((entry) => entry.op === 'narration_claim_renew')).toHaveLength(0); // claim consumed
    expect(h.transportLog.filter((entry) => entry.op === 'lease_renew').length).toBeGreaterThanOrEqual(1); // lease alive
  });

  test('a claim renewal update and a point switch restart the claim heartbeat correctly', async () => {
    const claimLog: Array<Record<string, unknown>> = [];
    const h = harness([
      { kind: 'transport', op: 'create_world', request: {}, scope: {}, respond: () => createWorldResponse('w1', 1_000_000) },
      { kind: 'transport', op: 'narration_claim', request: { pointId: 'root_0' }, scope: { worldId: 'w1', pointId: 'root_0' }, respond: () => claimResponse('root_0', 1, 'claim_gen1', 60_000) },
      { kind: 'transport', op: 'narration_claim', request: { pointId: 'root_0' }, scope: { worldId: 'w1', pointId: 'root_0' }, respond: () => claimResponse('root_0', 2, 'claim_gen2', 60_000) },
      { kind: 'terminal', status: { kind: 'await', reason: 'first boundary' } },
      { kind: 'transport', op: 'narration_claim', request: { pointId: 'point_1' }, scope: { worldId: 'w1', pointId: 'point_1' }, respond: () => claimResponse('point_1', 1, 'claim_p1', 90_000) },
      { kind: 'terminal', status: { kind: 'await', reason: 'second boundary' } },
    ], [], {
      claim: (request) => {
        claimLog.push(request as Record<string, unknown>);
        const pointId = (request as { pointId: Id }).pointId;
        return { data: { pointId, mode: 'head', generation: (request as { generation: number }).generation, fenceEpoch: 1, issuedAtEpochMilli: 1_000, expiresAtEpochMilli: 1_000_000 } };
      },
    });
    expect(await h.session.run()).toEqual({ kind: 'await', reason: 'first boundary' });
    h.clock.advance(30_000); // gen2 claim (fresh after update) renews first
    await settle();
    expect(claimLog).toHaveLength(1);
    expect(claimLog[0]!.claimToken).toBe('claim_gen2'); // the update replaced the state, not a restart from gen1
    expect(claimLog[0]!.pointId).toBe('root_0');
    expect(await h.session.run()).toEqual({ kind: 'await', reason: 'second boundary' }); // script continues: the point switch
    h.clock.advance(30_000); // point_1 claim (exp 90k) renews at 60k after the stop+start
    await settle();
    expect(claimLog).toHaveLength(2);
    expect(claimLog[1]!.claimToken).toBe('claim_p1');
    expect(claimLog[1]!.pointId).toBe('point_1');
  });

  test('repeat run() calls share one loop; stop settles everything and refuses late receipts', async () => {
    const h = harness([
      { kind: 'transport', op: 'create_world', request: {}, scope: {}, respond: () => createWorldResponse('w1', 120_000) },
      { kind: 'model', task: 'narration', key: 'root_0', input: { pointId: 'root_0', stateDigest: 'd' } },
      { kind: 'terminal', status: { kind: 'stop', reason: 'unreached' } },
    ], ['迟到的叙事']);
    h.engine.hold(true);
    const first = h.session.run();
    const second = h.session.run();
    expect(second).toBe(first); // single loop
    await settle();
    expect(h.session.sessionStatus).toBe('running');
    h.clock.advance(90_000); // renew fires while the generation is held
    await settle();
    h.session.stop();
    const status = await first;
    expect(status).toEqual({ kind: 'stop', reason: 'session_stopped' });
    h.engine.flush(); // late inference settle
    await settle();
    h.clock.advance(1_000_000); // nothing may schedule again
    await settle();
    expect(h.transportLog.filter((entry) => entry.op === 'lease_renew')).toHaveLength(1);
    await expect(h.session.run()).rejects.toThrow(/stopped/);
    expect(h.session.sessionStatus).toBe('stopped');
  });

  test('stop settles a held transport wait promptly; the late settle is refused, not adopted', async () => {
    let releaseResponse: ((value: unknown) => void) | null = null;
    const h = harness([
      { kind: 'transport', op: 'create_world', request: {}, scope: {}, respond: () => createWorldResponse('w1', 1_000_000) },
      {
        kind: 'transport', op: 'get_context', request: {}, scope: { worldId: 'w1' },
        respond: () => new Promise((resolve) => { releaseResponse = resolve; }),
      },
      { kind: 'terminal', status: { kind: 'stop', reason: 'unreached' } },
    ], []);
    const running = h.session.run();
    await settle(); // the held get_context is in flight
    h.session.stop();
    const status = await running; // settles via the call-signal race, WITHOUT the raw response
    expect(status).toEqual({ kind: 'stop', reason: 'session_stopped' });
    releaseResponse!(envelope('w1', null)); // the raw settle lands late and stays discarded
    await settle();
    expect(h.session.sessionStatus).toBe('stopped');
  });

  test('a late error envelope after stop cannot steer the driver: no followup writes', async () => {
    let rejectResponse: ((error: unknown) => void) | null = null;
    const h = harness([
      { kind: 'transport', op: 'create_world', request: {}, scope: {}, respond: () => createWorldResponse('w1', 1_000_000) },
      {
        kind: 'transport', op: 'narration_submit', request: { pointId: 'root_0' }, scope: { worldId: 'w1', pointId: 'root_0' },
        respond: () => new Promise((_resolve, reject) => { rejectResponse = reject; }),
      },
      { kind: 'terminal', status: { kind: 'stop', reason: 'unreached' } },
    ], []);
    const running = h.session.run();
    await settle(); // the submit is in flight
    h.session.stop();
    rejectResponse!(apiError('stale_epoch')); // must NOT reach the driver's errorReaction (no lease_acquire followup)
    const status = await running;
    expect(status).toEqual({ kind: 'stop', reason: 'session_stopped' });
    await settle();
    expect(h.transportLog.filter((entry) => entry.op === 'lease_acquire')).toHaveLength(0);
  });

  test('a heartbeat lease loss isolates the chain: both heartbeats stop, in-flight settles are replaced', async () => {
    const h = harness([
      { kind: 'transport', op: 'create_world', request: {}, scope: {}, respond: () => createWorldResponse('w1', 60_000) },
      { kind: 'model', task: 'action', key: 'person_a', input: { actor: 'person_a' } },
      { kind: 'terminal', status: { kind: 'stop', reason: 'unreached' } },
    ], ['{"kind":"act","text":"推门"}'], { lease: () => Promise.reject(apiError('stale_epoch')) });
    h.engine.hold(true);
    const running = h.session.run();
    await settle();
    h.clock.advance(30_000); // lease renew (60k lead 30k) is lost
    await settle();
    const status = await running;
    expect(status).toEqual({ kind: 'error', detail: 'lease lost: stale_epoch' });
    expect(h.hooks.leaseLost).toEqual(['stale_epoch']);
    h.engine.flush(); // late inference settle discarded
    await settle();
    h.clock.advance(500_000); // neither heartbeat may schedule again
    await settle();
    expect(h.transportLog.filter((entry) => entry.op === 'lease_renew')).toHaveLength(1);
    expect(h.transportLog.filter((entry) => entry.op === 'narration_claim_renew')).toHaveLength(0);
    expect(h.session.sessionStatus).toBe('lost_lease');
    await expect(h.session.run()).rejects.toThrow(/lost its lease/);
  });

  test('a foreign epoch in an envelope fences the held token instead of upgrading it', async () => {
    const h = harness([
      { kind: 'transport', op: 'create_world', request: {}, scope: {}, respond: () => createWorldResponse('w1', 120_000) },
      { kind: 'transport', op: 'get_context', request: {}, scope: { worldId: 'w1' },
        respond: () => envelope('w1', { fenceEpoch: 8, expiresAtEpochMilli: 240_000 }) },
      { kind: 'terminal', status: { kind: 'stop', reason: 'done' } },
    ], []);
    expect(await h.session.run()).toEqual({ kind: 'error', detail: 'lease lost: stale_epoch' }); // the loop is isolated, not resumed
    expect(h.hooks.leaseLost).toEqual(['stale_epoch']); // the epoch-7 token is dead, not re-bound at epoch 8
    expect(h.session.sessionStatus).toBe('lost_lease');
    await expect(h.session.run()).rejects.toThrow(/lost its lease/);
    h.clock.advance(500_000);
    await settle();
    expect(h.transportLog.filter((entry) => entry.op === 'lease_renew')).toHaveLength(0);
  });

  test('a lost lease is terminal: the session never attempts recovery itself', async () => {
    const h = harness([
      { kind: 'transport', op: 'create_world', request: {}, scope: {}, respond: () => createWorldResponse('w1', 60_000) },
      { kind: 'terminal', status: { kind: 'stop', reason: 'done' } },
    ], [], { lease: () => Promise.reject(apiError('stale_epoch')) });
    await h.session.run();
    h.clock.advance(30_000); // the lease renew is lost
    await settle();
    expect(h.session.sessionStatus).toBe('lost_lease');
    await expect(h.session.run()).rejects.toThrow(/lost its lease; recovery is a later batch/);
    h.clock.advance(500_000);
    await settle();
    expect(h.transportLog.filter((entry) => entry.op === 'lease_acquire')).toHaveLength(0); // no session-issued recovery
    expect(h.transportLog.filter((entry) => entry.op === 'lease_renew')).toHaveLength(1); // heartbeats dead
  });

  test('stop() and dispose() still close a lost-lease session cleanly', async () => {
    const h = harness([
      { kind: 'transport', op: 'create_world', request: {}, scope: {}, respond: () => createWorldResponse('w1', 60_000) },
      { kind: 'terminal', status: { kind: 'stop', reason: 'done' } },
    ], [], { lease: () => Promise.reject(apiError('stale_epoch')) });
    await h.session.run();
    h.clock.advance(30_000); // lost
    await settle();
    expect(h.session.sessionStatus).toBe('lost_lease');
    h.session.stop(); // still allowed, still terminal
    expect(h.session.sessionStatus).toBe('stopped');
    await expect(h.session.run()).rejects.toThrow(/stopped/);
    await h.session.dispose(); // idempotent cleanup path
  });


  test('default namespaces are session-unique: heartbeat ids never collide', async () => {
    const leaseOk = () => ({ data: { leaseToken: 'lease_1', fenceEpoch: 1, expiresAtEpochMilli: 1_000_000 } });
    const h1 = harness([
      { kind: 'transport', op: 'create_world', request: {}, scope: {}, respond: () => createWorldResponse('w1', 60_000) },
      { kind: 'terminal', status: { kind: 'stop', reason: 'done' } },
    ], [], { lease: leaseOk });
    const h2 = harness([
      { kind: 'transport', op: 'create_world', request: {}, scope: {}, respond: () => createWorldResponse('w2', 60_000) },
      { kind: 'terminal', status: { kind: 'stop', reason: 'done' } },
    ], [], { lease: leaseOk });
    await h1.session.run();
    await h2.session.run();
    h1.clock.advance(30_000);
    h2.clock.advance(30_000);
    await settle();
    const ids = [...h1.transportLog, ...h2.transportLog].filter((entry) => entry.op === 'lease_renew').map((entry) => entry.request.requestId);
    expect(ids).toHaveLength(2);
    expect(ids[0]).not.toBe(ids[1]);
  });
});
describe('WorldSession composition with the real ControllerDriver', () => {
  const load = (name: string): Record<string, unknown> =>
    JSON.parse(readFileSync(new URL(`../../../../../design/world-protocol/v2/fixtures/api/${name}.json`, import.meta.url), 'utf8'));

  function fixtureSession(submitRespond?: () => unknown | Promise<unknown>, inject: { renewLease?: () => unknown | Promise<unknown>; acquire?: () => unknown | Promise<unknown> } = {}, engineOutputs?: string[]) {
    const create = structuredClone(load('create_world/success')) as Record<string, never>;
    (create.world as never as { lease: { expiresAtEpochMilli: number } }).lease.expiresAtEpochMilli = 120_000;
    (create.data as never as { lease: { expiresAtEpochMilli: number } }).lease.expiresAtEpochMilli = 120_000;
    const claim = structuredClone(load('narration_claim/success')) as Record<string, never>;
    const submit = structuredClone(load('narration_submit/success')) as Record<string, never>;
    // Every served envelope carries the lease view; keep them all on the
    // test clock (a newer same-epoch expiry legitimately reschedules).
    for (const served of [claim, submit]) {
      (served.world as never as { lease: { expiresAtEpochMilli: number } }).lease.expiresAtEpochMilli = 120_000;
    }
    const initial = (load('create_world/request') as { initial: unknown }).initial;
    const clock = new ManualClock();
    const engine = fakeEngine(engineOutputs ?? [JSON.stringify(initial), '教室后门的锁咔哒一声弹开。']);
    const port = new RuntimeWorldModelPort(engine.engine);
    const transportLog: Array<{ op: WorldOperation; request: Record<string, unknown> }> = [];
    const raw = {
      async execute(op: WorldOperation, request: Record<string, unknown>): Promise<unknown> {
        transportLog.push({ op, request });
        if (op === 'create_world') return create as never;
        if (op === 'narration_claim') return claim as never;
        if (op === 'narration_submit') return submitRespond ? submitRespond() as never : submit as never;
        if (op === 'get_state') {
        // 组装阶梯读取：单根点夹具，前驱恒 null。
        const pointId = (request.point as string) ?? 'root_0';
        const st = { engineVersion: 'world-engine-v1', schemaVersion: 1, worldId: 'w1', protagonistId: 'person_c', time: { calendar: 'gregorian', dateTime: '2026-01-01T11:59:00', instantOrdinal: 0 }, initial: { worldId: 'w1', engineVersion: 'world-engine-v1', schemaVersion: 1, protagonistId: 'person_c', initialTime: { calendar: 'gregorian', dateTime: '2026-01-01T11:59:00', instantOrdinal: 0 }, locations: {}, items: {}, characters: { person_c: { id: 'person_c', name: 'C', initialPosition: { containerId: 'w1', slotId: null, relativeTo: null }, initialAppearance: '刚到', initialPersonality: '好奇', initialSanity: 10, tasks: {} } } }, locations: {}, items: {}, characters: {} };
        return { data: { pointId, version: 0, state: st, stateDigest: 'd0', previousPointId: null, timeAdvance: null, entityDeltas: {} } };
        }
        if (op === 'lease_renew') return (inject.renewLease ? inject.renewLease() : { data: { leaseToken: 'lease_a', fenceEpoch: 7, expiresAtEpochMilli: 1_000_000 } }) as never;
        if (op === 'lease_acquire') return (inject.acquire ? inject.acquire() : { data: { holderId: 'browser', leaseToken: 'lease_new', fenceEpoch: 8, expiresAtEpochMilli: 1_000_000 } }) as never;
        throw new Error(`unexpected transport call ${op}`);
      },
    };
    const hooks = { statuses: [] as DriverStatus[], leaseLost: [] as string[], claimLost: [] as unknown[] };
    const session = new WorldSession(raw as never, port, { clock, hooks: {
      onStatus: (status) => hooks.statuses.push(status),
      onLeaseLost: (code) => hooks.leaseLost.push(code),
      onClaimLost: (loss) => hooks.claimLost.push(loss),
    } }); // default factory: the REAL ControllerDriver
    return { session, clock, transportLog, engine, hooks };
  }

  test('the real driver reaches the await boundary and the lease heartbeat follows the fixtures', async () => {
    const h = fixtureSession();
    const status = await h.session.run();
    expect(status.kind).toBe('await'); // root narration ready, waiting for player input
    expect(h.transportLog.map((entry) => entry.op)).toEqual(['create_world', 'narration_claim', 'get_state', 'narration_submit']);
    h.clock.advance(90_000); // fixture lease (120k) minus the 30k lead
    await settle();
    const renews = h.transportLog.filter((entry) => entry.op === 'lease_renew');
    expect(renews).toHaveLength(1);
    expect(renews[0]!.request.leaseToken).toBe('lease_a');
    expect(renews[0]!.request.fenceEpoch).toBe(7);
  });



  test('composition: a lost lease is terminal — run() refuses, no recovery, memory untouched by late receipts', async () => {
    const h = fixtureSession(undefined, {
      renewLease: () => Promise.reject(apiError('stale_epoch')),
      acquire: () => { throw new Error('the session must not attempt recovery'); },
    });
    const first = await h.session.run();
    expect(first.kind).toBe('await');
    h.clock.advance(90_000); // the lease renew is lost
    await settle();
    const idsAfterTheLoss = h.transportLog.map((entry) => entry.request.requestId);
    expect(h.hooks.leaseLost).toEqual(['stale_epoch']);
    expect(h.session.sessionStatus).toBe('lost_lease');
    await expect(h.session.run()).rejects.toThrow(/lost its lease/); // explicitly refused, not resumed
    expect(h.session.getMemory().leaseToken).toBe('lease_a'); // the stale token stands; reconciliation is the recovery batch's job
    h.clock.advance(1_000_000);
    await settle();
    const idsNow = h.transportLog.map((entry) => entry.request.requestId);
    expect(idsNow).toEqual(idsAfterTheLoss); // no exchange of any kind after the loss
  });

  test('composition: a late stale_epoch after stop drives no reacquire followup', async () => {
    let rejectSubmit: ((error: unknown) => void) | null = null;
    const h = fixtureSession(() => new Promise((_resolve, reject) => { rejectSubmit = reject; }));
    const running = h.session.run();
    for (let i = 0; i < 200 && !h.transportLog.some((entry) => entry.op === 'narration_submit'); i++) await settle();
    expect(h.transportLog.some((entry) => entry.op === 'narration_submit')).toBe(true); // the submit is genuinely in flight
    h.session.stop();
    rejectSubmit!(apiError('stale_epoch')); // late error envelope lands after the epoch raised
    const status = await running;
    expect(status).toEqual({ kind: 'stop', reason: 'session_stopped' });
    await settle();
    // The real controller's errorReaction WOULD reacquire the lease here
    // (lease_acquire followup); the isolation must prevent that write.
    expect(h.transportLog.filter((entry) => entry.op === 'lease_acquire')).toHaveLength(0);
  });

  test('two default real-driver sessions mint distinct create requestIds', async () => {
    const first = fixtureSession();
    const second = fixtureSession();
    await first.session.run();
    await second.session.run();
    const ids = [first, second].map((h) => h.transportLog.find((entry) => entry.op === 'create_world')!.request.requestId);
    expect(ids[0]).not.toBe(ids[1]); // no idempotency collision on a shared server
  });
});

describe('WorldSession namespace uniqueness across module instances', () => {
  test('two fresh module copies in the same millisecond still mint distinct namespaces', async () => {
    const frozen = 1_234_567_890;
    const realNow = Date.now;
    Date.now = () => frozen; // the per-instance counter AND the clock collide
    const makeSession = (Session: typeof import('./session').WorldSession) => {
      const engine = fakeEngine([]);
      const port = new RuntimeWorldModelPort(engine.engine);
      const raw = { async execute(): Promise<unknown> { throw new Error('no exchanges needed'); } };
      return new Session(raw as never, port, { clock: new ManualClock() });
    };
    try {
      // Two FRESH module instances: each counter restarts at 1 under the
      // frozen clock, so without entropy both namespaces would be identical.
      vi.resetModules();
      const moduleA = await import('./session');
      const first = makeSession(moduleA.WorldSession);
      vi.resetModules();
      const moduleB = await import('./session');
      const second = makeSession(moduleB.WorldSession);
      expect(moduleB.WorldSession).not.toBe(moduleA.WorldSession); // genuinely separate instances
      expect(first.idNamespace.startsWith('s1_')).toBe(true); // counter restarted in both
      expect(second.idNamespace.startsWith('s1_')).toBe(true);
      // Entropy — not the counter, not the clock — keeps the namespaces apart.
      expect(first.idNamespace).not.toBe(second.idNamespace);
    } finally {
      Date.now = realNow;
    }
  });
});
