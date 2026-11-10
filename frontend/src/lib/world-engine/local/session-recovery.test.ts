/** CPU-only verification of the durable local session: simulated storage,
 * refresh-style mid-settlement restore, duplicate submit, multi-tab fencing,
 * legacy migration and cancel. No GPU/model weights involved. */
import { describe, expect, it } from 'vitest';
import type { WorldModelPort } from '../controller';
import type { ModelTask } from '../schedule';
import type { InitialTemplate, Json } from '../types';
import { SHORT_STATE } from '../runtime/b3-short-samples';
import { LocalGameSession, type LocalSessionEvent } from './session';
import {
  createLocalProgressStore, LEGACY_SNAPSHOT_KEY, MemoryProgressBackend, migrateLegacySnapshot, ProgressConflictError,
  SessionLeaseHeldError, type LegacyStorageLike, type LocalProgressStore,
} from './persistence';

function template(): InitialTemplate {
  const initial = structuredClone(SHORT_STATE.initial) as InitialTemplate & { worldId?: string };
  delete initial.worldId;
  return initial;
}

interface ModelHooks {
  /** Throw after the transport write this task follows (simulated refresh). */
  crashOn?: (task: ModelTask, key: string) => Error | null;
  /** Await before answering, to hold a step in flight. */
  blockOn?: (task: ModelTask, key: string) => Promise<void> | null;
}

function scriptedModel(log: string[], hooks: ModelHooks = {}): WorldModelPort {
  return {
    async generate(task: ModelTask, key: string, input: Json): Promise<Json> {
      log.push(`${task}:${key}`);
      const crash = hooks.crashOn?.(task, key);
      if (crash) throw crash;
      const blocked = hooks.blockOn?.(task, key);
      if (blocked) await blocked;
      const data = input as {
        actor?: string; workingState?: { protagonistId: string };
        advance?: { inputText: string | null };
      };
      switch (task) {
        case 'pointPlan': {
          const round = (input as { round?: { roundId?: string } }).round;
          return [{ pointId: `point_${round?.roundId ?? 'round'}_1`, kind: 'normal',
            timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } }, actorIds: ['person_a', 'person_c'] }];
        }
        case 'action':
          return data.actor === data.workingState?.protagonistId
            ? { kind: 'act', text: data.advance?.inputText ?? '我走到门厅。' }
            : { kind: 'skip' };
        case 'targets':
          return key === 'person_c' ? { targets: [{ targetId: 'person_a' }] } : { targets: [] };
        case 'reaction':
          return '林川侧过身，让开半步。';
        case 'results':
          return { person_c: '周宁掀开盒盖。', person_a: '林川侧过身。' };
        case 'updates':
          return [{ stage: 'position', changes: {} }];
        case 'continuation':
          return { kind: 'handback', closedBy: 'model', cancelReason: null };
        case 'narration':
          return key === 'p1' ? '门厅里安静下来，盒盖开着。' : '走廊里很安静，盒子还盖着。';
        default:
          throw new Error(`unexpected task ${task}`);
      }
    },
  };
}

async function waitFor(predicate: () => boolean, timeoutMs = 3000): Promise<void> {
  const started = Date.now();
  while (!predicate()) {
    if (Date.now() - started > timeoutMs) throw new Error('wait_for_timeout');
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
}

class MemoryStorage implements LegacyStorageLike {
  private readonly values = new Map<string, string>();
  getItem(key: string): string | null { return this.values.get(key) ?? null; }
  setItem(key: string, value: string): void { this.values.set(key, value); }
  removeItem(key: string): void { this.values.delete(key); }
}

/** Delegating store whose next n saves fail like a quota error. */
function faultStore(inner: LocalProgressStore): { store: LocalProgressStore; failSaves: (count: number) => void } {
  let failures = 0;
  return {
    failSaves: (count) => { failures = count; },
    store: {
      kind: inner.kind, durable: inner.durable,
      save: async (worldId, snapshot, options) => {
        if (failures > 0) { failures -= 1; throw new Error('simulated_quota_exceeded'); }
        return inner.save(worldId, snapshot, options);
      },
      load: (worldId) => inner.load(worldId),
      list: () => inner.list(),
      delete: (worldId, options) => inner.delete(worldId, options),
      close: () => inner.close(),
      claimLease: (worldId, holderId, ttlMs) => inner.claimLease(worldId, holderId, ttlMs),
      renewLease: (worldId, holderId, ttlMs) => inner.renewLease(worldId, holderId, ttlMs),
      takeoverLease: (worldId, holderId, ttlMs) => inner.takeoverLease(worldId, holderId, ttlMs),
      releaseLease: (worldId, holderId) => inner.releaseLease(worldId, holderId),
      readLease: (worldId) => inner.readLease(worldId),
      backupLegacy: (backup) => inner.backupLegacy(backup),
      loadLegacyBackup: (key) => inner.loadLegacyBackup(key),
    },
  };
}

describe('local progress store', () => {
  it('derives immutable metadata, rejects stale revisions and deletes', async () => {
    const backend = new MemoryProgressBackend();
    const store = createLocalProgressStore(backend, { now: () => 1_000 });
    const session = await LocalGameSession.create(template(), scriptedModel([]), { roll: () => 13 });
    await session.start();
    const snapshot = session.snapshot;
    const worldId = snapshot.transport.worldId;

    const first = await store.save(worldId, snapshot, { expectedRevision: 0, writerId: 'tab_a', digest: true });
    expect(first.revision).toBe(1);
    expect(first.headPointId).toBe(snapshot.transport.headPointId);
    expect(first.version).toBe(snapshot.transport.version);
    expect(first.hasWork).toBe(false);
    expect(first.writerId).toBe('tab_a');
    expect(first.narrationStatus).toBe('ready');
    expect(first.snapshotDigest).toMatch(/^[0-9a-f]{64}$/);

    await expect(store.save(worldId, snapshot, { expectedRevision: 0 })).rejects.toBeInstanceOf(ProgressConflictError);
    const second = await store.save(worldId, snapshot, { expectedRevision: 1, now: 2_000 });
    expect(second.revision).toBe(2);
    expect(second.savedAtEpochMilli).toBe(2_000);

    const loaded = await store.load(worldId);
    expect(loaded?.metadata.revision).toBe(2);
    expect(loaded?.snapshot.transport.headPointId).toBe(snapshot.transport.headPointId);
    expect((await store.list()).map((item) => item.revision)).toEqual([2]);

    await store.delete(worldId, { force: true });
    expect(await store.load(worldId)).toBeNull();
    expect(await store.list()).toEqual([]);
  });

  it('refuses to save with another writer lease', async () => {
    const backend = new MemoryProgressBackend();
    const store = createLocalProgressStore(backend, { now: () => 1_000 });
    const session = await LocalGameSession.create(template(), scriptedModel([]), { roll: () => 13 });
    await session.start();
    const snapshot = session.snapshot;
    const worldId = snapshot.transport.worldId;
    const claim = await store.claimLease(worldId, 'tab_a', 30_000);
    expect(claim.acquired).toBe(true);
    await expect(store.save(worldId, snapshot, { expectedRevision: 0, sessionId: 'tab_b', requireLease: true }))
      .rejects.toMatchObject({ name: 'SessionLeaseLostError' });
    await store.save(worldId, snapshot, { expectedRevision: 0, sessionId: 'tab_a', requireLease: true });
    const fenced = await store.claimLease(worldId, 'tab_b', 30_000);
    expect(fenced.acquired).toBe(false);
  });

  it('rejects a corrupt snapshot instead of writing it', async () => {
    const backend = new MemoryProgressBackend();
    const store = createLocalProgressStore(backend);
    const broken = { transport: { worldId: 'w1' }, commands: [] } as never;
    await expect(store.save('w1', broken, { expectedRevision: 0 })).rejects.toThrow('local_progress_snapshot_invalid');
    expect(await store.load('w1')).toBeNull();
  });
});

describe('LocalGameSession durability', () => {
  it('keeps playing after a failed save and catches up on the next checkpoint', async () => {
    const backend = new MemoryProgressBackend();
    const store = createLocalProgressStore(backend);
    const fault = faultStore(store);
    fault.failSaves(1);
    const events: LocalSessionEvent[] = [];
    const session = await LocalGameSession.create(template(), scriptedModel([]), {
      roll: () => 13, storage: fault.store, leaseHeartbeat: false, onEvent: (event) => events.push(event),
    });
    expect(session.persistence.state).toBe('error');
    expect(events.some((event) => event.type === 'save_failed')).toBe(true);

    await session.start();
    expect(await store.load(session.worldId)).not.toBeNull();
    expect(session.persistence.state).toBe('saved');
    expect(session.persistence.revision).toBeGreaterThan(0);

    const status = await session.submit('我打开盒盖。');
    expect(status.kind).not.toBe('error');
    const saved = await store.load(session.worldId);
    expect(saved?.metadata.version).toBe(1);
    expect(saved?.snapshot.transport.version).toBe(1);
    expect(saved?.snapshot.commands).toEqual(['我打开盒盖。']);
  });

  it('restores a mid-settlement checkpoint without repeating frozen actions or dice', async () => {
    const backend = new MemoryProgressBackend();
    const clock = { value: 100_000 };
    const store = createLocalProgressStore(backend, { now: () => clock.value });
    const log: string[] = [];
    const crashing = scriptedModel(log, { crashOn: (task) => task === 'reaction' ? new Error('simulated_refresh') : null });
    const session = await LocalGameSession.create(template(), crashing, {
      storage: store, sessionId: 'tab_a', leaseHeartbeat: false, leaseTtlMs: 1_000, roll: () => 13,
    });
    await session.start();
    await expect(session.submit('我打开盒盖。')).rejects.toThrow('simulated_refresh');

    const saved = await store.load(session.worldId);
    expect(saved?.metadata.hasWork).toBe(true);
    expect(saved?.metadata.advanceId).not.toBeNull();
    const savedRecord = saved!.snapshot.transport;
    const rollKeys = Object.keys(savedRecord.rolls);
    expect(rollKeys).toHaveLength(1);
    const rollBefore = savedRecord.rolls[rollKeys[0]];
    expect(savedRecord.work?.pendingGroup?.actionTexts.person_c).toBe('我打开盒盖。');
    expect(saved?.snapshot.checkpoint).toBeDefined();

    // The dead tab never released its lease: after the TTL another tab takes
    // over instead of assuming a single process.
    clock.value += 5_000;
    const restored = await LocalGameSession.restoreFromStore(store, session.worldId, scriptedModel([]), {
      sessionId: 'tab_b', leaseHeartbeat: false, leaseTtlMs: 1_000,
    });
    expect(restored).not.toBeNull();
    expect(await restored!.submit('另一次行动')).toEqual({ kind: 'stop', reason: 'turn_in_progress' });
    expect(restored!.commandsPlayed).toEqual(['我打开盒盖。']);

    const status = await restored!.start();
    expect(status.kind).not.toBe('error');
    const record = restored!.snapshot.transport;
    expect(record.version).toBe(1);
    expect(Object.keys(record.rolls)).toEqual(rollKeys);
    expect(record.rolls[rollKeys[0]].rollId).toBe(rollBefore.rollId);
    expect(record.rolls[rollKeys[0]].result).toBe(rollBefore.result);
    expect(record.advance).toBeNull();
    expect(record.work).toBeNull();
    expect(record.narrations[record.headPointId].status).toBe('ready');

    // A raw snapshot without the scheduler hint is the legacy shape: the
    // open point is still rebuilt from the record and finishes identically.
    const legacy = { ...saved!.snapshot, checkpoint: undefined };
    const legacySession = await LocalGameSession.restore(legacy, scriptedModel([]), { leaseHeartbeat: false });
    const legacyStatus = await legacySession.start();
    expect(legacyStatus.kind).not.toBe('error');
    expect(Object.keys(legacySession.snapshot.transport.rolls)).toEqual(rollKeys);
    expect(legacySession.snapshot.transport.rolls[rollKeys[0]].rollId).toBe(rollBefore.rollId);
    expect(legacySession.snapshot.transport.version).toBe(1);
  });

  it('resumes a turn whose work was written but whose model input was lost', async () => {
    const backend = new MemoryProgressBackend();
    const clock = { value: 300_000 };
    const store = createLocalProgressStore(backend, { now: () => clock.value });
    const log: string[] = [];
    const crashing = scriptedModel(log, { crashOn: (task, key) => task === 'action' && key === 'person_c' ? new Error('simulated_refresh') : null });
    const session = await LocalGameSession.create(template(), crashing, {
      storage: store, sessionId: 'tab_a', leaseHeartbeat: false, leaseTtlMs: 1_000, roll: () => 13,
    });
    await session.start();
    // The point and person_a's skip were already checkpointed before the crash.
    await expect(session.submit('我打开盒盖。')).rejects.toThrow('simulated_refresh');
    expect(log).toContain('action:person_a');
    const saved = await store.load(session.worldId);
    expect(saved?.metadata.hasWork).toBe(true);
    expect(saved?.metadata.workPhase).toBe('select_actor');
    expect(saved!.snapshot.transport.work?.pendingGroup).toBeNull();
    expect(saved!.metadata.advanceId).toBe(saved!.snapshot.transport.advance?.advanceId);

    const revisionBefore = saved!.metadata.revision;

    clock.value += 5_000;
    const restored = await LocalGameSession.restoreFromStore(store, session.worldId, scriptedModel([]), {
      sessionId: 'tab_b', leaseHeartbeat: false, leaseTtlMs: 1_000, roll: () => 13,
    });
    expect(restored).not.toBeNull();
    // The resume's group allocation is itself checkpointed, on top of the
    // revision the record already had (never a conflict, never a rollback).
    expect(restored!.persistence.state).toBe('saved');
    expect(restored!.persistence.revision).toBe(revisionBefore + 1);
    const afterResume = await store.load(session.worldId);
    expect(afterResume!.metadata.revision).toBe(revisionBefore + 1);
    expect(afterResume!.metadata.version).toBe(0);
    // Only the resume bucket must be stable; later trigger allocations are new
    // facts of the turn that followed, not duplicate group identities.
    const resumeBuckets = (record: { allocations: Record<string, Record<string, string>> }) =>
      JSON.stringify(Object.entries(record.allocations).filter(([key]) => key.startsWith('resume_')).sort());
    const allocations = resumeBuckets(afterResume!.snapshot.transport);

    const status = await restored!.start();
    expect(status.kind).not.toBe('error');
    expect(restored!.snapshot.transport.version).toBe(1);
    expect(restored!.snapshot.transport.advance).toBeNull();
    expect(restored!.commandsPlayed).toEqual(['我打开盒盖。']);

    // A second refresh finds the checkpointed record with no conflict.
    clock.value += 5_000;
    const again = await LocalGameSession.restoreFromStore(store, session.worldId, scriptedModel([]), {
      sessionId: 'tab_c', leaseHeartbeat: false, leaseTtlMs: 1_000, roll: () => 13,
    });
    expect(again).not.toBeNull();
    expect(again!.persistence.blocked).toBeNull();
    expect(resumeBuckets(again!.snapshot.transport)).toBe(allocations);
  });

  it('finishes the round after a refresh at the continuation boundary', async () => {
    const backend = new MemoryProgressBackend();
    const clock = { value: 350_000 };
    const store = createLocalProgressStore(backend, { now: () => clock.value });
    const log: string[] = [];
    const crashing = scriptedModel(log, { crashOn: (task) => task === 'continuation' ? new Error('simulated_refresh') : null });
    const session = await LocalGameSession.create(template(), crashing, {
      storage: store, sessionId: 'tab_a', leaseHeartbeat: false, leaseTtlMs: 1_000, roll: () => 13,
    });
    await session.start();
    await expect(session.submit('我打开盒盖。')).rejects.toThrow('simulated_refresh');
    const saved = await store.load(session.worldId);
    // The point is committed, the round is not concluded yet.
    expect(saved?.metadata.version).toBe(1);
    expect(saved?.metadata.hasWork).toBe(false);
    expect(saved?.metadata.phase).toBe('assess_continuation');
    expect(saved?.metadata.roundId).toBe(saved!.snapshot.transport.round?.roundId);

    clock.value += 5_000;
    const restored = await LocalGameSession.restoreFromStore(store, session.worldId, scriptedModel([]), {
      sessionId: 'tab_b', leaseHeartbeat: false, leaseTtlMs: 1_000, roll: () => 13,
    });
    expect(restored).not.toBeNull();
    const status = await restored!.start();
    expect(status.kind).not.toBe('error');
    const record = restored!.snapshot.transport;
    expect(record.version).toBe(1);
    expect(record.control.phase).toBe('complete');
    expect(record.advance).toBeNull();
    expect(record.round?.conclusion).toEqual({ kind: 'handback', closedBy: 'model', cancelReason: null });
    expect(record.narrations[record.headPointId].status).toBe('ready');
  });

  it('refuses a duplicate submit while the same turn is in flight', async () => {
    const log: string[] = [];
    let release!: () => void;
    const blocked = new Promise<void>((resolve) => { release = resolve; });
    const model = scriptedModel(log, { blockOn: (task, key) => task === 'action' && key === 'person_c' ? blocked : null });
    const session = await LocalGameSession.create(template(), model, { roll: () => 13 });
    await session.start();
    const first = session.submit('我打开盒盖。');
    await waitFor(() => log.includes('action:person_c'));
    const duplicate = await session.submit('我打开盒盖。');
    expect(duplicate).toEqual({ kind: 'stop', reason: 'turn_in_progress' });
    expect(session.commandsPlayed).toEqual(['我打开盒盖。']);
    release();
    const status = await first;
    expect(status.kind).not.toBe('error');
    expect(session.snapshot.transport.version).toBe(1);
  });

  it('discards the in-flight model answer on cancel and lets a new turn start', async () => {
    const log: string[] = [];
    let release!: () => void;
    const blocked = new Promise<void>((resolve) => { release = resolve; });
    const model = scriptedModel(log, { blockOn: (task, key) => task === 'action' && key === 'person_c' ? blocked : null });
    const session = await LocalGameSession.create(template(), model, { roll: () => 13 });
    await session.start();
    const turn = session.submit('我打开盒盖。');
    await waitFor(() => log.includes('action:person_c'));

    const cancelled = session.cancel('player_abort');
    release();
    const status = await cancelled;
    await turn;
    expect(status.kind).not.toBe('error');

    const record = session.snapshot.transport;
    expect(record.advance).toBeNull();
    expect(record.work).toBeNull();
    expect(record.points).toEqual({});
    expect(record.rolls).toEqual({});
    expect(record.round?.conclusion).toEqual({ kind: 'handback', closedBy: 'cancel', cancelReason: 'player_abort' });
    expect(record.control.phase).toBe('complete');

    const next = await session.submit('我退回走廊。');
    expect(next.kind).not.toBe('error');
    expect(session.snapshot.transport.version).toBe(1);
    expect(session.snapshot.commands).toEqual(['我打开盒盖。', '我退回走廊。']);
  });

  it('pauses mid-turn, restores paused, then resumes the same frozen work', async () => {
    const backend = new MemoryProgressBackend();
    const clock = { value: 400_000 };
    const store = createLocalProgressStore(backend, { now: () => clock.value });
    const log: string[] = [];
    let release!: () => void;
    const blocked = new Promise<void>((resolve) => { release = resolve; });
    const model = scriptedModel(log, { blockOn: (task) => task === 'results' ? blocked : null });
    const session = await LocalGameSession.create(template(), model, {
      storage: store, sessionId: 'tab_a', leaseHeartbeat: false, leaseTtlMs: 1_000, roll: () => 13,
    });
    await session.start();
    const turn = session.submit('我打开盒盖。');
    await waitFor(() => log.some((entry) => entry.startsWith('results:')));
    const pausedStatus = session.pause();
    release();
    const paused = await pausedStatus;
    expect(paused).toEqual({ kind: 'await', reason: 'paused_externally' });
    await turn;
    const saved = await store.load(session.worldId);
    expect(saved?.metadata.paused).toBe(true);
    expect(saved?.metadata.hasWork).toBe(true);
    expect(saved!.snapshot.transport.work?.pendingGroup?.closed).toBe(true);
    expect(await session.submit('暂停时的新命令')).toEqual({ kind: 'stop', reason: 'paused' });

    clock.value += 5_000;
    const restored = await LocalGameSession.restoreFromStore(store, session.worldId, scriptedModel([]), {
      sessionId: 'tab_b', leaseHeartbeat: false, leaseTtlMs: 1_000, roll: () => 13,
    });
    expect(restored).not.toBeNull();
    const stillPaused = await restored!.start();
    expect(stillPaused).toEqual({ kind: 'await', reason: 'paused_externally' });
    expect(restored!.commandsPlayed).toEqual(['我打开盒盖。']);

    const resumed = await restored!.resume();
    expect(resumed.kind).not.toBe('error');
    const record = restored!.snapshot.transport;
    expect(record.version).toBe(1);
    expect(record.control.paused).toBe(false);
    expect(Object.keys(record.rolls)).toEqual(Object.keys(saved!.snapshot.transport.rolls));
    expect(record.advance).toBeNull();
  });

  it('fences a stale tab and lets the takeover writer win', async () => {
    const backend = new MemoryProgressBackend();
    const clock = { value: 200_000 };
    const store = createLocalProgressStore(backend, { now: () => clock.value });
    const events: LocalSessionEvent[] = [];
    const tabA = await LocalGameSession.create(template(), scriptedModel([]), {
      roll: () => 13, storage: store, sessionId: 'tab_a', leaseHeartbeat: false, leaseTtlMs: 1_000, onEvent: (event) => events.push(event),
    });
    await tabA.start();
    await expect(LocalGameSession.restoreFromStore(store, tabA.worldId, scriptedModel([]), {
      sessionId: 'tab_b', leaseHeartbeat: false, leaseTtlMs: 1_000,
    })).rejects.toBeInstanceOf(SessionLeaseHeldError);

    clock.value += 5_000;
    const tabB = await LocalGameSession.restoreFromStore(store, tabA.worldId, scriptedModel([]), {
      sessionId: 'tab_b', leaseHeartbeat: false, leaseTtlMs: 1_000,
    });
    expect(tabB).not.toBeNull();
    const before = await store.load(tabA.worldId);
    const revisionBefore = before!.metadata.revision;

    // tab A still thinks it is the writer; its save is fenced and the stored
    // record does not move.
    await tabA.submit('我打开盒盖。');
    expect(tabA.persistence.blocked).toBe('lease_lost');
    expect(events.some((event) => event.type === 'lease_lost')).toBe(true);
    expect((await store.load(tabA.worldId))!.metadata.revision).toBe(revisionBefore);
    expect(await tabA.submit('再来一次。')).toEqual({ kind: 'stop', reason: 'progress_lease_lost' });

    const status = await tabB!.submit('我退回走廊。');
    expect(status.kind).not.toBe('error');
    const after = await store.load(tabA.worldId);
    expect(after!.metadata.revision).toBeGreaterThan(revisionBefore);
    expect(after!.metadata.writerId).toBe('tab_b');
    expect(after!.snapshot.commands).toEqual(['我退回走廊。']);
    expect(after!.snapshot.transport.version).toBe(1);
  });

  it('supports an explicit takeover and fences the previous writer immediately', async () => {
    const backend = new MemoryProgressBackend();
    const clock = { value: 500_000 };
    const store = createLocalProgressStore(backend, { now: () => clock.value });
    const writer = await LocalGameSession.create(template(), scriptedModel([]), {
      storage: store, sessionId: 'tab_a', leaseHeartbeat: false, leaseTtlMs: 60_000, roll: () => 13,
    });
    await writer.start();
    const revisionBefore = (await store.load(writer.worldId))!.metadata.revision;

    // Live lease: a plain claim is refused, an explicit takeover is not.
    const refused = await store.claimLease(writer.worldId, 'tab_b', 60_000);
    expect(refused.acquired).toBe(false);
    const taken = await store.takeoverLease(writer.worldId, 'tab_b', 60_000);
    expect(taken.holderId).toBe('tab_b');
    expect(taken.epoch).toBeGreaterThanOrEqual(2);

    const fenced = await writer.submit('我打开盒盖。');
    expect(fenced).toEqual({ kind: 'stop', reason: 'progress_lease_lost' });
    expect(writer.persistence.blocked).toBe('lease_lost');
    expect((await store.load(writer.worldId))!.metadata.revision).toBe(revisionBefore);
    expect(await writer.submit('再来一次。')).toEqual({ kind: 'stop', reason: 'progress_lease_lost' });

    const winner = await LocalGameSession.restoreFromStore(store, writer.worldId, scriptedModel([]), {
      sessionId: 'tab_b', leaseHeartbeat: false, leaseTtlMs: 60_000, roll: () => 13,
    });
    const status = await winner!.submit('我退回走廊。');
    expect(status.kind).not.toBe('error');
    const saved = await store.load(writer.worldId);
    expect(saved!.metadata.writerId).toBe('tab_b');
    expect(saved!.metadata.revision).toBeGreaterThan(revisionBefore);
    expect(saved!.snapshot.transport.version).toBe(1);
  });

  it('stops when the planner keeps naming a committed point instead of spinning', async () => {
    const stuck: WorldModelPort = {
      async generate(task): Promise<Json> {
        if (task === 'pointPlan') {
          return [{ pointId: 'point_fixed', kind: 'normal',
            timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } }, actorIds: ['person_a', 'person_c'] }];
        }
        if (task === 'action') return { kind: 'skip' };
        if (task === 'targets') return { targets: [] };
        if (task === 'results') return {};
        if (task === 'updates') return [];
        if (task === 'continuation') return { kind: 'handback', closedBy: 'model', cancelReason: null };
        if (task === 'narration') return '安静。';
        throw new Error(`unexpected ${task}`);
      },
    };
    const session = await LocalGameSession.create(template(), stuck, { roll: () => 13 });
    await session.start();
    const first = await session.submit('我打开盒盖。');
    expect(first.kind).not.toBe('error');
    const second = await session.submit('我退回走廊。');
    expect(second).toEqual({ kind: 'stop', reason: 'stalled:checkpoint_begin_point' });
    // The refused point was never committed twice and no round was invented.
    expect(Object.keys(session.snapshot.transport.points)).toEqual(['point_fixed']);
    expect(session.commandsPlayed).toEqual(['我打开盒盖。', '我退回走廊。']);
  });

  it('migrates the legacy localStorage save with a backup and keeps corrupt originals', async () => {
    const storage = new MemoryStorage();
    const legacySession = await LocalGameSession.create(template(), scriptedModel([]), { roll: () => 13 });
    await legacySession.start();
    const raw = JSON.stringify(legacySession.snapshot);
    storage.setItem(LEGACY_SNAPSHOT_KEY, raw);

    const backend = new MemoryProgressBackend();
    const store = createLocalProgressStore(backend);
    const migrated = await migrateLegacySnapshot(store, { storage, now: 500 });
    expect(migrated.status).toBe('migrated');
    expect(migrated.worldId).toBe(legacySession.worldId);
    expect(storage.getItem(LEGACY_SNAPSHOT_KEY)).toBe(raw);
    const backup = await store.loadLegacyBackup(migrated.backupKey!);
    expect(backup?.raw).toBe(raw);

    const restored = await LocalGameSession.restoreFromStore(store, legacySession.worldId, scriptedModel([]));
    expect(restored).not.toBeNull();
    expect(restored!.snapshot.transport.version).toBe(legacySession.snapshot.transport.version);

    const again = await migrateLegacySnapshot(store, { storage, now: 600 });
    expect(again.status).toBe('already_saved');
    expect((await store.load(legacySession.worldId))!.metadata.revision).toBe(1);

    storage.setItem(LEGACY_SNAPSHOT_KEY, '{not json');
    const corrupt = await migrateLegacySnapshot(store, { storage, now: 700 });
    expect(corrupt.status).toBe('corrupt');
    expect(storage.getItem(LEGACY_SNAPSHOT_KEY)).toBe('{not json');
    expect((await store.loadLegacyBackup(corrupt.backupKey!))?.raw).toBe('{not json');
    expect((await store.load(legacySession.worldId))!.metadata.revision).toBe(1);
  });
});
