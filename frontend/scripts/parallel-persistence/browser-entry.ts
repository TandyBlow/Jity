/** Browser-side scenarios for the durable local session. Bundled by
 * scripts/parallel-persistence/run-indexeddb-check.mjs and driven from
 * Playwright; every step returns plain JSON so the runner can assert. */
import type { InitialTemplate, Json, WorldState } from '../../src/lib/world-engine/types';
import type { ModelTask } from '../../src/lib/world-engine/schedule';
import type { WorldModelPort } from '../../src/lib/world-engine/controller';
import {
  createLocalProgressStore, migrateLegacySnapshot, openLocalProgressStore,
  LEGACY_SNAPSHOT_KEY, MemoryProgressBackend,
  type LocalProgressStore, type ProgressMetadata,
} from '../../src/lib/world-engine/local/persistence';
import { LocalGameSession } from '../../src/lib/world-engine/local/session';

const WORLD_ID = 'world_browser_check';

interface Hooks {
  crashOn?: (task: ModelTask, key: string) => boolean;
  blockOn?: (task: ModelTask, key: string) => Promise<void> | null;
}

interface Step {
  name: string;
  ok: boolean;
  detail: Json;
}

/** A settled turn hands back as await (mid-round) or world_complete (handback). */
function turnSettled(status: { kind: string; reason?: string }): boolean {
  return status.kind === 'await' || (status.kind === 'stop' && status.reason === 'world_complete');
}

const steps: Step[] = [];
function record(name: string, ok: boolean, detail: unknown): void {
  steps.push({ name, ok, detail: detail as Json });
}

function position(containerId: string) {
  return { containerId, slotId: null, relativeTo: null };
}

function template(): InitialTemplate {
  const time = { calendar: 'gregorian' as const, dateTime: '2009-10-17T15:20:00', instantOrdinal: 0 };
  const task = { id: 'task_watch', ownerId: 'person_a', parentTaskId: null, goal: '留在走廊守门，不碰盒子', status: 'pending' as const };
  return {
    engineVersion: 'world-engine-v1', schemaVersion: 1, protagonistId: 'person_c', initialTime: time,
    locations: {
      corridor: { id: 'corridor', name: '走廊', parentLocationId: null, initialAppearance: '明亮的走廊，通往门厅。' },
      hall: { id: 'hall', name: '门厅', parentLocationId: null, initialAppearance: '安静的门厅。' },
    },
    items: { box: { id: 'box', name: '盒子', initialPosition: position('corridor'), initialAppearance: '盒盖关闭。' } },
    characters: {
      person_a: { id: 'person_a', name: '林川', initialPosition: position('corridor'), initialAppearance: '穿灰衣。', initialPersonality: '谨慎，恪守职责', initialSanity: 10, tasks: { task_watch: task } },
      person_c: { id: 'person_c', name: '周宁', initialPosition: position('corridor'), initialAppearance: '穿蓝衣。', initialPersonality: '好奇', initialSanity: 10, tasks: {} },
    },
  };
}

function scriptedModel(log: string[], hooks: Hooks = {}): WorldModelPort {
  return {
    async generate(task: ModelTask, key: string, input: Json): Promise<Json> {
      log.push(`${task}:${key}`);
      if (hooks.crashOn?.(task, key)) throw new Error('browser_simulated_refresh');
      const blocked = hooks.blockOn?.(task, key);
      if (blocked) await blocked;
      const data = input as { actor?: string; workingState?: { protagonistId: string }; advance?: { inputText: string | null } };
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

interface BrowserApi {
  reset(): Promise<void>;
  storeCheck(): Promise<Json>;
  createAndPlay(): Promise<Json>;
  midTurnSnapshot(): Promise<Json>;
  resumeAfterRefresh(): Promise<Json>;
  claimInSecondTab(): Promise<Json>;
  takeoverWorld(): Promise<Json>;
  staleWorldWriterFenced(): Promise<Json>;
  takeoverAfterExpiry(): Promise<Json>;
  staleTabSaveFenced(): Promise<Json>;
  legacyMigration(): Promise<Json>;
  cancelInFlight(): Promise<Json>;
  pauseAndResume(): Promise<Json>;
  resumeAtContinuation(): Promise<Json>;
  listAndDelete(): Promise<Json>;
  duplicateSubmit(): Promise<Json>;
  steps(): Json;
  worldState(): Promise<WorldState>;
}

let store: LocalProgressStore | null = null;
let session: LocalGameSession | null = null;
const log: string[] = [];

function metadataSummary(metadata: ProgressMetadata | null): Json {
  if (!metadata) return null;
  return {
    worldId: metadata.worldId, revision: metadata.revision, version: metadata.version,
    hasWork: metadata.hasWork, workPhase: metadata.workPhase, narrationStatus: metadata.narrationStatus,
    checkpointRevision: metadata.checkpointRevision, writerId: metadata.writerId, commands: metadata.commands,
    stateDigest: metadata.stateDigest, snapshotDigest: metadata.snapshotDigest,
  };
}

const api: BrowserApi = {
  async reset() {
    await new Promise<void>((resolve, reject) => {
      const request = indexedDB.deleteDatabase('jity-local-progress');
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
      request.onblocked = () => resolve();
    });
    await store?.close();
    store = null;
    session = null;
    log.length = 0;
    steps.length = 0;
    localStorage.clear();
  },

  async storeCheck() {
    store = await openLocalProgressStore();
    record('store.kind', store.kind === 'indexeddb', { kind: store.kind, durable: store.durable });
    return { kind: store.kind, durable: store.durable };
  },

  async createAndPlay() {
    if (!store) throw new Error('call storeCheck first');
    const created = await LocalGameSession.create(template(), scriptedModel(log), {
      worldId: WORLD_ID, storage: store, sessionId: 'tab_a', roll: () => 13,
    });
    session = created;
    const boot = await created.start();
    const status = await created.submit('我打开盒盖。');
    const saved = await store.load(WORLD_ID);
    const record2 = saved!.snapshot.transport;
    record('create.boot', boot.kind === 'await', boot);
    record('create.turn', turnSettled(status), status);
    record('create.saved', !!saved && record2.version === 1, { metadata: metadataSummary(saved?.metadata ?? null), version: record2.version });
    record('create.dice', Object.keys(record2.rolls).length === 1, Object.keys(record2.rolls));
    record('create.commands', JSON.stringify(saved?.snapshot.commands) === JSON.stringify(['我打开盒盖。']), saved?.snapshot.commands);
    return { metadata: metadataSummary(saved!.metadata), version: record2.version, rolls: Object.keys(record2.rolls) };
  },

  async midTurnSnapshot() {
    if (!store) throw new Error('call storeCheck first');
    const crashing = scriptedModel(log, { crashOn: (task) => task === 'reaction' });
    log.length = 0;
    const crashed = await LocalGameSession.create(template(), crashing, {
      worldId: `${WORLD_ID}_mid`, storage: store, sessionId: 'tab_a', leaseHeartbeat: false, leaseTtlMs: 1_500, roll: () => 13,
    });
    await crashed.start();
    let error = '';
    try { await crashed.submit('我打开盒盖。'); } catch (caught) { error = caught instanceof Error ? caught.message : String(caught); }
    const saved = await store.load(`${WORLD_ID}_mid`);
    const transport = saved?.snapshot.transport;
    record('mid.error', error === 'browser_simulated_refresh', { error });
    record('mid.hasWork', saved?.metadata.hasWork === true, metadataSummary(saved?.metadata ?? null));
    record('mid.frozenAction', transport?.work?.pendingGroup?.actionTexts.person_c === '我打开盒盖。', transport?.work?.pendingGroup?.actionTexts ?? null);
    record('mid.rollSaved', Object.keys(transport?.rolls ?? {}).length === 1, Object.keys(transport?.rolls ?? {}));
    // Intentionally not closed: a crashed tab stops renewing, so the record's
    // lease must expire before another tab may take over.
    return { metadata: metadataSummary(saved?.metadata ?? null), rolls: Object.keys(transport?.rolls ?? {}), error };
  },

  async resumeAfterRefresh() {
    if (!store) throw new Error('call storeCheck first');
    const resumeLog: string[] = [];
    await store.close();
    // New page context: re-open the store and restore from IndexedDB only.
    store = await openLocalProgressStore();
    const beforeSaved = await store.load(`${WORLD_ID}_mid`);
    if (!beforeSaved) throw new Error('no saved mid-turn record');
    const restored = await LocalGameSession.restoreFromStore(store, `${WORLD_ID}_mid`, scriptedModel(resumeLog), {
      sessionId: 'tab_b', roll: () => 13,
    });
    if (!restored) throw new Error('no saved record');
    const duplicate = await restored.submit('另一次行动');
    const status = await restored.start();
    const after = restored.snapshot.transport;
    const before = beforeSaved.snapshot.transport;
    const rollKeys = Object.keys(before.rolls);
    record('resume.duplicateRefused', duplicate.kind === 'stop' && duplicate.reason === 'turn_in_progress', duplicate);
    record('resume.status', turnSettled(status), status);
    record('resume.version', after.version === 1, { version: after.version });
    record('resume.diceReused', JSON.stringify(Object.keys(after.rolls)) === JSON.stringify(rollKeys)
      && after.rolls[rollKeys[0]]?.rollId === before.rolls[rollKeys[0]]?.rollId
      && after.rolls[rollKeys[0]]?.result === before.rolls[rollKeys[0]]?.result,
      { before: before.rolls[rollKeys[0]], after: after.rolls[rollKeys[0]] });
    record('resume.actionNotRepeated', !resumeLog.includes('action:person_c') && !resumeLog.includes('targets:person_c'),
      { calls: resumeLog });
    record('resume.committed', after.advance === null && after.work === null && after.narrations[after.headPointId]?.status === 'ready',
      { advance: after.advance, work: after.work, narration: after.narrations[after.headPointId]?.status });
    await restored.close();
    return { version: after.version, status, rolls: Object.keys(after.rolls), calls: resumeLog };
  },

  async claimInSecondTab() {
    if (!store) throw new Error('call storeCheck first');
    // A live lease from another page must block a takeover.
    const claim = await store.claimLease(WORLD_ID, 'tab_b', 30_000);
    const detail: Json = claim.acquired ? { acquired: true } : { acquired: false, holderId: claim.holderId };
    record('lease.blocked', claim.acquired === false, detail);
    return detail;
  },

  async takeoverWorld() {
    if (!store) throw new Error('call storeCheck first');
    const lease = await store.takeoverLease(WORLD_ID, 'tab_b', 30_000);
    record('lease.takeover', lease.holderId === 'tab_b' && lease.epoch >= 2, lease);
    return { epoch: lease.epoch, holderId: lease.holderId };
  },

  async staleWorldWriterFenced() {
    if (!store || !session) throw new Error('call createAndPlay first');
    const before = (await store.load(WORLD_ID))!.metadata.revision;
    const status = await session.submit('第二次行动');
    const after = (await store.load(WORLD_ID))!.metadata;
    const again = await session.submit('第三次行动');
    record('fence.worldWriterBlocked', session.persistence.blocked === 'lease_lost'
      && status.kind === 'stop' && status.reason === 'progress_lease_lost', { blocked: session.persistence.blocked, status });
    record('fence.worldRecordUnchanged', after.revision === before && after.writerId === 'tab_a',
      { before, after: after.revision, writerId: after.writerId });
    record('fence.worldRefusesNewTurn', again.kind === 'stop' && again.reason === 'progress_lease_lost', again);
    return { blocked: session.persistence.blocked, revision: after.revision };
  },

  async takeoverAfterExpiry() {
    if (!store) throw new Error('call storeCheck first');
    const clock = { value: Date.now() };
    const shortLived = createLocalProgressStore(new MemoryProgressBackend(), { now: () => clock.value });
    const first = await shortLived.claimLease(WORLD_ID, 'tab_a', 1_000);
    const during = await shortLived.claimLease(WORLD_ID, 'tab_b', 1_000);
    clock.value += 5_000;
    const after = await shortLived.claimLease(WORLD_ID, 'tab_b', 1_000);
    record('lease.expiry', first.acquired && during.acquired === false && after.acquired === true
      && (after as { recovered?: boolean }).recovered === true,
      { first: first.acquired, during: (during as { acquired: boolean }).acquired, after });
    const lease = await shortLived.readLease(WORLD_ID);
    record('lease.epochBumped', !!lease && lease.epoch >= 2 && lease.holderId === 'tab_b', lease);
    return { epoch: lease?.epoch ?? null, holder: lease?.holderId ?? null };
  },

  async staleTabSaveFenced() {
    if (!store) throw new Error('call storeCheck first');
    const clock = { value: Date.now() };
    const local = createLocalProgressStore(new MemoryProgressBackend(), { now: () => clock.value });
    const events: string[] = [];
    const stale = await LocalGameSession.create(template(), scriptedModel(log), {
      worldId: `${WORLD_ID}_fence`, storage: local, sessionId: 'tab_a', leaseHeartbeat: false, leaseTtlMs: 1_000, roll: () => 13,
      onEvent: (event) => events.push(event.type),
    });
    await stale.start();
    clock.value += 5_000;
    const takeover = await LocalGameSession.restoreFromStore(local, `${WORLD_ID}_fence`, scriptedModel(log), {
      sessionId: 'tab_b', leaseHeartbeat: false, leaseTtlMs: 1_000, roll: () => 13,
    });
    const revisionBefore = (await local.load(`${WORLD_ID}_fence`))!.metadata.revision;
    await stale.submit('我打开盒盖。');
    const afterStale = (await local.load(`${WORLD_ID}_fence`))!.metadata.revision;
    const refused = await stale.submit('再来一次。');
    record('fence.staleBlocked', stale.persistence.blocked === 'lease_lost' && events.includes('lease_lost'),
      { blocked: stale.persistence.blocked, events });
    record('fence.recordUnchanged', afterStale === revisionBefore, { revisionBefore, afterStale });
    record('fence.refusesNewTurn', refused.kind === 'stop' && refused.reason === 'progress_lease_lost', refused);
    const winner = await takeover!.submit('我退回走廊。');
    const afterWinner = (await local.load(`${WORLD_ID}_fence`))!.metadata;
    record('fence.takeoverWins', turnSettled(winner) && afterWinner.revision > revisionBefore && afterWinner.writerId === 'tab_b',
      { winner, revision: afterWinner.revision, writerId: afterWinner.writerId, version: afterWinner.version });
    await stale.close();
    await takeover!.close();
    return { blocked: stale.persistence.blocked, revision: afterWinner.revision, writerId: afterWinner.writerId };
  },

  async legacyMigration() {
    if (!store) throw new Error('call storeCheck first');
    const legacySession = await LocalGameSession.create(template(), scriptedModel(log), { worldId: `${WORLD_ID}_legacy`, roll: () => 13 });
    await legacySession.start();
    const raw = JSON.stringify(legacySession.snapshot);
    localStorage.setItem(LEGACY_SNAPSHOT_KEY, raw);
    const migrated = await migrateLegacySnapshot(store, { now: 1_700_000_000_000 });
    const backup = migrated.backupKey ? await store.loadLegacyBackup(migrated.backupKey) : null;
    const restored = await LocalGameSession.restoreFromStore(store, `${WORLD_ID}_legacy`, scriptedModel(log));
    record('legacy.migrated', migrated.status === 'migrated' && !!restored, { status: migrated.status, revision: migrated.revision });
    record('legacy.sourceKept', localStorage.getItem(LEGACY_SNAPSHOT_KEY) === raw, { kept: localStorage.getItem(LEGACY_SNAPSHOT_KEY) === raw });
    record('legacy.backup', backup?.raw === raw, { backupKey: migrated.backupKey, same: backup?.raw === raw });
    localStorage.setItem(LEGACY_SNAPSHOT_KEY, '{broken');
    const corrupt = await migrateLegacySnapshot(store, { now: 1_700_000_001_000 });
    const stillThere = localStorage.getItem(LEGACY_SNAPSHOT_KEY) === '{broken';
    record('legacy.corruptPreserved', corrupt.status === 'corrupt' && stillThere, { status: corrupt.status, stillThere });
    await restored?.close();
    return { status: migrated.status, corrupt: corrupt.status };
  },

  async duplicateSubmit() {
    const release = { fn: null as null | (() => void) };
    const blocked = new Promise<void>((resolve) => { release.fn = resolve; });
    const localLog: string[] = [];
    const model = scriptedModel(localLog, { blockOn: (task, key) => (task === 'action' && key === 'person_c' ? blocked : null) });
    const solo = await LocalGameSession.create(template(), model, { worldId: `${WORLD_ID}_dup`, roll: () => 13 });
    await solo.start();
    const first = solo.submit('我打开盒盖。');
    const started = Date.now();
    while (!localLog.includes('action:person_c') && Date.now() - started < 5_000) await new Promise((resolve) => setTimeout(resolve, 5));
    const duplicate = await solo.submit('我打开盒盖。');
    const commandsDuring = solo.commandsPlayed.length;
    release.fn?.();
    const status = await first;
    record('duplicate.refused', duplicate.kind === 'stop' && duplicate.reason === 'turn_in_progress', duplicate);
    record('duplicate.oneCommand', commandsDuring === 1, { commands: solo.commandsPlayed });
    record('duplicate.turnFinished', turnSettled(status) && solo.snapshot.transport.version === 1, { status, version: solo.snapshot.transport.version });
    await solo.close();
    return { duplicate, version: solo.snapshot.transport.version };
  },

  async cancelInFlight() {
    const release = { fn: null as null | (() => void) };
    const blocked = new Promise<void>((resolve) => { release.fn = resolve; });
    const localLog: string[] = [];
    const model = scriptedModel(localLog, { blockOn: (task, key) => (task === 'action' && key === 'person_c' ? blocked : null) });
    const solo = await LocalGameSession.create(template(), model, { worldId: `${WORLD_ID}_cancel`, roll: () => 13 });
    await solo.start();
    const turn = solo.submit('我打开盒盖。');
    const started = Date.now();
    while (!localLog.includes('action:person_c') && Date.now() - started < 5_000) await new Promise((resolve) => setTimeout(resolve, 5));
    const cancelled = solo.cancel('player_abort');
    release.fn?.();
    const status = await cancelled;
    await turn;
    const record2 = solo.snapshot.transport;
    record('cancel.status', turnSettled(status), status);
    record('cancel.roundAbandoned', record2.advance === null && record2.work === null && Object.keys(record2.points).length === 0
      && record2.round?.conclusion?.closedBy === 'cancel',
      { advance: record2.advance, work: record2.work, points: Object.keys(record2.points), conclusion: record2.round?.conclusion });
    const next = await solo.submit('我退回走廊。');
    record('cancel.nextTurnWorks', turnSettled(next) && solo.snapshot.transport.version === 1,
      { next, version: solo.snapshot.transport.version, commands: solo.commandsPlayed });
    await solo.close();
    return { status, version: solo.snapshot.transport.version };
  },

  async pauseAndResume() {
    if (!store) throw new Error('call storeCheck first');
    const localLog: string[] = [];
    let insideResults = false;
    let release!: () => void;
    const blocked = new Promise<void>((resolve) => { release = resolve; });
    const model = scriptedModel(localLog, {
      blockOn: (task) => {
        if (task !== 'results') return null;
        insideResults = true;
        return blocked;
      },
    });
    const solo = await LocalGameSession.create(template(), model, {
      worldId: `${WORLD_ID}_pause`, storage: store, sessionId: 'tab_a', leaseHeartbeat: false, roll: () => 13,
    });
    await solo.start();
    const turn = solo.submit('我打开盒盖。');
    const started = Date.now();
    while (!insideResults && Date.now() - started < 5_000) await new Promise((resolve) => setTimeout(resolve, 5));
    const pausedStatus = solo.pause();
    release();
    const paused = await pausedStatus;
    await turn;
    const saved = await store.load(`${WORLD_ID}_pause`);
    record('pause.paused', paused.kind === 'await' && paused.reason === 'paused_externally',
      { paused, recordPaused: saved?.metadata.paused, hasWork: saved?.metadata.hasWork });
    record('pause.saved', saved?.metadata.paused === true && saved?.metadata.hasWork === true,
      metadataSummary(saved?.metadata ?? null));
    const refused = await solo.submit('暂停时的命令');
    record('pause.refusesSubmit', refused.kind === 'stop' && refused.reason === 'paused', refused);
    await solo.close();

    // Reload: a new connection to the same IndexedDB, then resume the frozen work.
    await store.close();
    store = await openLocalProgressStore();
    const restored = await LocalGameSession.restoreFromStore(store, `${WORLD_ID}_pause`, scriptedModel(localLog), {
      sessionId: 'tab_b', leaseHeartbeat: false, roll: () => 13,
    });
    if (!restored) throw new Error('no paused record');
    const stillPaused = await restored.start();
    record('pause.restoredPaused', stillPaused.kind === 'await' && stillPaused.reason === 'paused_externally', stillPaused);
    const rollKeys = Object.keys(saved!.snapshot.transport.rolls);
    const resumed = await restored.resume();
    const after = restored.snapshot.transport;
    record('pause.resumed', turnSettled(resumed) && after.version === 1 && after.control.paused === false
      && JSON.stringify(Object.keys(after.rolls)) === JSON.stringify(rollKeys),
      { resumed, version: after.version, paused: after.control.paused, rolls: Object.keys(after.rolls) });
    await restored.close();
    return { paused: saved?.metadata.paused === true, version: after.version };
  },

  async resumeAtContinuation() {
    if (!store) throw new Error('call storeCheck first');
    const localLog: string[] = [];
    const crashing = scriptedModel(localLog, { crashOn: (task) => task === 'continuation' });
    const crashed = await LocalGameSession.create(template(), crashing, {
      worldId: `${WORLD_ID}_ctx`, storage: store, sessionId: 'tab_a', leaseHeartbeat: false, leaseTtlMs: 1_500, roll: () => 13,
    });
    await crashed.start();
    let error = '';
    try { await crashed.submit('我打开盒盖。'); } catch (caught) { error = caught instanceof Error ? caught.message : String(caught); }
    const saved = await store.load(`${WORLD_ID}_ctx`);
    record('ctx.pointCommitted', error === 'browser_simulated_refresh' && saved?.metadata.version === 1
      && saved?.metadata.hasWork === false && saved?.metadata.phase === 'assess_continuation',
      { error, metadata: metadataSummary(saved?.metadata ?? null) });
    // The dead tab's lease must lapse before the other tab may take over.
    await new Promise((resolve) => setTimeout(resolve, 1_800));
    await store.close();
    store = await openLocalProgressStore();
    const restored = await LocalGameSession.restoreFromStore(store, `${WORLD_ID}_ctx`, scriptedModel(localLog), {
      sessionId: 'tab_b', leaseHeartbeat: false, roll: () => 13,
    });
    if (!restored) throw new Error('no continuation record');
    const status = await restored.start();
    const after = restored.snapshot.transport;
    record('ctx.roundFinished', turnSettled(status) && after.version === 1 && after.control.phase === 'complete'
      && after.round?.conclusion?.kind === 'handback' && after.narrations[after.headPointId]?.status === 'ready',
      { status, version: after.version, phase: after.control.phase, conclusion: after.round?.conclusion, narration: after.narrations[after.headPointId]?.status });
    await restored.close();
    return { version: after.version, phase: after.control.phase };
  },

  async listAndDelete() {
    if (!store) throw new Error('call storeCheck first');
    const listed = await store.list();
    const worlds = listed.map((item) => item.worldId).sort();
    const expected = [`${WORLD_ID}_ctx`, `${WORLD_ID}_legacy`, `${WORLD_ID}_mid`, `${WORLD_ID}_pause`, WORLD_ID].sort();
    record('store.list', JSON.stringify(worlds) === JSON.stringify(expected),
      { worlds, revisions: listed.map((item) => item.revision) });
    await store.delete(`${WORLD_ID}_legacy`, { force: true });
    const gone = await store.load(`${WORLD_ID}_legacy`);
    const remaining = (await store.list()).length;
    record('store.delete', gone === null && remaining === listed.length - 1, { gone: gone === null, remaining, before: listed.length });
    return { worlds, remaining };
  },

  steps(): Json { return steps as unknown as Json; },

  async worldState() {
    if (!session) throw new Error('no session');
    return session.state();
  },
};

declare global {
  interface Window { PersistenceCheck: BrowserApi }
}
window.PersistenceCheck = api;
