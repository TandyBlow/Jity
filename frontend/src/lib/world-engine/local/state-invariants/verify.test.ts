/** Counterexamples for the record invariants. The raw transport restore path
 * trusts its input; this suite proves the gap with a valid then corrupted
 * record, and proves the read-only verifier rejects each corruption. */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import type { EntityDelta, InitialState, TimelinePoint, WorldState } from '../../types';
import { applyPoint, buildInitialState, stateDigest } from '../state';
import { LocalWorldTransport } from '../transport';
import {
  pointContinuityIssues, RecordInvariantError, verifyDisplayHistory, verifyDisplayedCommit, verifyTaskCoverage, verifyTaskDecisionEvidence,
  verifyVisibleAcceptance,
  verifySnapshotSequence, verifyWorldRecord, type WorldRecordLike,
} from './index';
import { restoreVerified, verifyBeforeRestore } from './guarded-restore';

const fixture = JSON.parse(readFileSync(
  resolve('scripts/parallel-kernel/fixtures/kernel-differential.json'), 'utf8'));

function point(state: WorldState, sequence: number, deltas: Record<string, EntityDelta>, previous?: string): TimelinePoint {
  return {
    worldId: state.worldId,
    id: `p${sequence}`,
    sequence,
    kind: 'normal',
    previousPointId: previous ?? (sequence === 1 ? 'root_0' : `p${sequence - 1}`),
    roundId: 'round_f',
    advanceId: 'advance_f',
    trigger: 'player',
    linkedFromPointId: null,
    timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } },
    entityDeltas: deltas,
  };
}

async function recordOf(initial: InitialState, points: TimelinePoint[]): Promise<WorldRecordLike & Record<string, unknown>> {
  const s0 = buildInitialState(structuredClone(initial));
  const rootId = points[0]?.previousPointId ?? 'root_0';
  const pointStates: Record<string, { version: number; state: WorldState; stateDigest: string }> = {
    [rootId]: { version: 0, state: s0, stateDigest: await stateDigest(s0) },
  };
  let current = s0;
  for (const entry of points) {
    current = applyPoint(current, entry);
    pointStates[entry.id] = { version: entry.sequence, state: current, stateDigest: await stateDigest(current) };
  }
  return {
    worldId: s0.worldId,
    initial: structuredClone(initial),
    state: current,
    version: points.length,
    rootPointId: rootId,
    headPointId: points.length ? points[points.length - 1].id : rootId,
    points: Object.fromEntries(points.map((entry) => [entry.id, entry])),
    pointStates,
    advance: null,
    round: null,
    work: null,
    control: { phase: 'complete', paused: false, revision: points.length },
  };
}

describe('record replay and restore gate', () => {
  it('accepts the root record of the real 14-character world', async () => {
    const world = JSON.parse(readFileSync(resolve('public/worlds/dragon-raja-free-day.world.json'), 'utf8'));
    const transport = await LocalWorldTransport.create(world.initial as InitialState, { worldId: world.initial.worldId, roll: () => 13 });
    const report = await verifyWorldRecord(transport.snapshot());
    expect(report.errors, JSON.stringify(report.errors)).toEqual([]);
    expect(report.ok).toBe(true);
  });

  it('accepts a record whose stored state, point projections and digest all replay exactly', async () => {
    const s0 = buildInitialState(structuredClone(fixture.normal.initial) as InitialState);
    const p1 = fixture.normal.point as TimelinePoint;
    const record = await recordOf(fixture.normal.initial as InitialState, [p1]);
    const report = await verifyWorldRecord(record);
    expect(report.errors).toEqual([]);
    expect(report.ok).toBe(true);
    expect(report.replayDigest).toBe(fixture.normal.stateDigestAfter);
    expect(await stateDigest(s0)).toBe(fixture.normal.stateDigestBefore);
    await expect(restoreVerified(record)).resolves.toBeInstanceOf(LocalWorldTransport);
  });

  it('rejects a tampered cached state while raw restore still accepts it', async () => {
    const record = await recordOf(fixture.normal.initial as InitialState, [fixture.normal.point as TimelinePoint]);
    const tampered = structuredClone(record) as WorldRecordLike & Record<string, unknown>;
    const state = tampered.state as WorldState;
    state.characters.person_a.position = { containerId: 'not_a_location', slotId: null, relativeTo: null };

    const report = await verifyWorldRecord(tampered);
    expect(report.ok).toBe(false);
    expect(report.errors.map((item) => item.code)).toContain('state_mismatch');
    await expect(verifyBeforeRestore(tampered)).rejects.toBeInstanceOf(RecordInvariantError);
    // The old entry point is the gap this gate exists for.
    await expect(LocalWorldTransport.restore(tampered as never)).resolves.toBeInstanceOf(LocalWorldTransport);
  });

  it('rejects a rewritten point digest even when the visible state looks valid', async () => {
    const record = await recordOf(fixture.normal.initial as InitialState, [fixture.normal.point as TimelinePoint]);
    const tampered = structuredClone(record) as WorldRecordLike & Record<string, unknown>;
    const states = tampered.pointStates as Record<string, { stateDigest: string }>;
    states.p1.stateDigest = '0'.repeat(64);
    const report = await verifyWorldRecord(tampered);
    expect(report.errors.map((item) => item.code)).toContain('point_digest_mismatch');
  });

  it('rejects a deleted point or a broken chain before it can become a new branch', async () => {
    const p1 = point(buildInitialState(structuredClone(fixture.worlds.fixture) as InitialState), 1, {});
    const s1 = applyPoint(buildInitialState(structuredClone(fixture.worlds.fixture) as InitialState), p1);
    const p2 = point(s1, 2, {}, 'p1');
    const record = await recordOf(fixture.worlds.fixture as InitialState, [p1, p2]);
    const missing = structuredClone(record) as WorldRecordLike & Record<string, unknown>;
    delete (missing.points as Record<string, unknown>).p1;
    const missingReport = await verifyWorldRecord(missing);
    expect(missingReport.errors.map((item) => item.code)).toContain('point_chain_broken');
    expect(missingReport.errors.map((item) => item.code)).toContain('version_mismatch');

    const broken = structuredClone(record) as WorldRecordLike & Record<string, unknown>;
    (broken.points as Record<string, TimelinePoint>).p2.previousPointId = 'p0';
    const brokenReport = await verifyWorldRecord(broken);
    expect(brokenReport.errors.map((item) => item.code)).toContain('point_chain_broken');
  });
});

describe('completion and discovery monotonicity', () => {
  function fixtureState(): WorldState {
    return buildInitialState(structuredClone(fixture.worlds.fixture) as InitialState);
  }

  it('detects a re-added completed task even though the reference kernel currently overwrites it', () => {
    const s0 = fixtureState();
    const p1 = point(s0, 1, {
      person_a: {
        entityId: 'person_a',
        subtasksAdded: [{ id: 'task_child', ownerId: 'person_a', parentTaskId: 'task_a', goal: '打开箱子', status: 'pending' }],
      },
    });
    const s1 = applyPoint(s0, p1);
    const p2 = point(s1, 2, { person_a: { entityId: 'person_a', tasksAchieved: ['task_child'] } });
    const s2 = applyPoint(s1, p2);
    expect(s2.characters.person_a.tasks.task_child.status).toBe('achieved');

    const p3 = point(s2, 3, {
      person_a: {
        entityId: 'person_a',
        subtasksAdded: [{ id: 'task_child', ownerId: 'person_a', parentTaskId: 'task_a', goal: '打开箱子', status: 'pending' }],
      },
    });
    const issues = pointContinuityIssues(s2, p3);
    expect(issues.map((item) => item.code)).toContain('task_duplicate_add');
    // The guard is intentionally before apply; the unguarded kernel still
    // replaces the achieved task, which is exactly why commit must call it.
    expect(applyPoint(s2, p3).characters.person_a.tasks.task_child.status).toBe('pending');
  });

  it('reports the regression when an already-written record contains it', async () => {
    const s0 = fixtureState();
    const p1 = point(s0, 1, {
      person_a: {
        entityId: 'person_a',
        subtasksAdded: [{ id: 'task_child', ownerId: 'person_a', parentTaskId: 'task_a', goal: '打开箱子', status: 'pending' }],
      },
    });
    const s1 = applyPoint(s0, p1);
    const p2 = point(s1, 2, { person_a: { entityId: 'person_a', tasksAchieved: ['task_child'] } });
    const s2 = applyPoint(s1, p2);
    const p3 = point(s2, 3, {
      person_a: {
        entityId: 'person_a',
        subtasksAdded: [{ id: 'task_child', ownerId: 'person_a', parentTaskId: 'task_a', goal: '打开箱子', status: 'pending' }],
      },
    });
    const record = await recordOf(fixture.worlds.fixture as InitialState, [p1, p2, p3]);
    const report = await verifyWorldRecord(record);
    expect(report.errors.map((item) => item.code)).toEqual(expect.arrayContaining(['task_duplicate_add', 'task_regressed']));
  });

  it('detects a cross-character task id and a wrong task owner before apply', () => {
    const s0 = buildInitialState(structuredClone(fixture.normal.initial) as InitialState);
    const pointWithBadTask = point(s0, 1, {
      person_b: { entityId: 'person_b', subtasksAdded: [{ id: 'task_a_root', ownerId: 'person_a', parentTaskId: null, goal: '错误任务', status: 'pending' }] },
    });
    const codes = pointContinuityIssues(s0, pointWithBadTask).map((item) => item.code);
    expect(codes).toEqual(expect.arrayContaining(['task_duplicate_add', 'task_hierarchy']));
  });

  it('detects a repeated location appearance id before it can duplicate a room discovery', () => {
    const s0 = fixtureState();
    const p1 = point(s0, 1, {
      room_a: { entityId: 'room_a', appearanceChanges: [{ id: 'ch_room', text: '墙上多了一道新划痕。', supersedes: [] }] },
    });
    const s1 = applyPoint(s0, p1);
    const p2 = point(s1, 2, {
      room_a: { entityId: 'room_a', appearanceChanges: [{ id: 'ch_room', text: '墙上多了一道新划痕。', supersedes: [] }] },
    });
    expect(pointContinuityIssues(s1, p2).map((item) => item.code)).toContain('change_duplicate');
  });

  it('detects a repeated description-change id that would duplicate a discovery', () => {
    const s0 = fixtureState();
    const p1 = point(s0, 1, {
      item_a: { entityId: 'item_a', appearanceChanges: [{ id: 'ch_found', text: '箱盖上有新的划痕。', supersedes: [] }] },
    });
    const s1 = applyPoint(s0, p1);
    const p2 = point(s1, 2, {
      item_a: { entityId: 'item_a', appearanceChanges: [{ id: 'ch_found', text: '箱盖上有新的划痕。', supersedes: [] }] },
    });
    const issues = pointContinuityIssues(s1, p2);
    expect(issues.map((item) => item.code)).toContain('change_duplicate');
  });
});

describe('visible acceptance summary', () => {
  it('accepts monotonic visible history and tasks', () => {
    const result = verifyVisibleAcceptance([
      { before: { historyCount: '3', tasks: [{ goal: '开门', done: false }] }, after: { historyCount: '4', tasks: [{ goal: '开门', done: true }] }, text: '门开了。', historyDelta: 1 },
    ]);
    expect(result.errors).toEqual([]);
    expect(result.warnings.map((item) => item.code)).toContain('evidence_shape');
  });

  it('rejects a roll ledger with a repeated roll id', async () => {
    const record = await recordOf(fixture.normal.initial as InitialState, []);
    const withRolls = record as WorldRecordLike & { rolls?: unknown; rollSeq?: number };
    withRolls.rolls = {
      a: { key: 'a', rollId: 'roll_same', result: 7, eligible: true, admitted: true },
      b: { key: 'b', rollId: 'roll_same', result: 8, eligible: true, admitted: true },
    };
    withRolls.rollSeq = 2;
    const report = await verifyWorldRecord(record);
    expect(report.errors.map((item) => item.code)).toContain('roll_invalid');
  });

  it('rejects a task id that appears under two characters', async () => {
    const record = await recordOf(fixture.normal.initial as InitialState, []);
    const state = record.state as WorldState;
    state.characters.person_b.tasks.task_a_root = {
      id: 'task_a_root', ownerId: 'person_b', parentTaskId: null, goal: '重复 id', status: 'pending',
    };
    const report = await verifyWorldRecord(record);
    expect(report.errors.map((item) => item.code)).toContain('task_hierarchy');
  });

  it('rejects a stored task whose parent does not exist in the same character', async () => {
    const record = await recordOf(fixture.normal.initial as InitialState, []);
    const state = record.state as WorldState;
    state.characters.person_a.tasks.task_orphan = {
      id: 'task_orphan', ownerId: 'person_a', parentTaskId: 'task_missing', goal: '找不到父任务', status: 'pending',
    };
    const report = await verifyWorldRecord(record);
    expect(report.errors.map((item) => item.code)).toContain('task_hierarchy');
  });

  it('rejects a visible task that returns to not-done', () => {
    const result = verifyVisibleAcceptance([
      { before: { historyCount: 1, tasks: [{ goal: '开门', done: false }] }, after: { historyCount: 2, tasks: [{ goal: '开门', done: true }] }, text: '门开了。', historyDelta: 1 },
      { before: { historyCount: 2, tasks: [{ goal: '开门', done: true }] }, after: { historyCount: 3, tasks: [{ goal: '开门', done: false }] }, text: '门又关上了。', historyDelta: 1 },
    ]);
    expect(result.errors.map((item) => item.code)).toContain('task_regressed');
  });

  it('rejects a history regression and a refresh that did not restore', () => {
    const result = verifyVisibleAcceptance([
      { before: { historyCount: 4 }, after: { historyCount: 3 }, text: '正文', historyDelta: -1, refreshMidSettle: { restored: false } },
    ]);
    expect(result.errors.map((item) => item.code)).toEqual(expect.arrayContaining(['history_regressed', 'refresh_not_restored']));
  });

  it('requires a snapshot series to keep the previous head and never move backwards', async () => {
    const initial = fixture.normal.initial as InitialState;
    const s0 = buildInitialState(structuredClone(initial));
    const first = await recordOf(initial, [point(s0, 1, {})]);
    const second = await recordOf(initial, [point(s0, 1, {}), point(s0, 2, {})]);
    const forward = await verifySnapshotSequence([{ transport: first }, { transport: second }]);
    expect(forward.errors).toEqual([]);
    const backward = await verifySnapshotSequence([{ transport: second }, { transport: first }]);
    expect(backward.errors.map((item) => item.code)).toEqual(expect.arrayContaining(['version_regressed', 'points_regressed']));
  });

  it('keeps every initial task and character and rejects a removed task row', async () => {
    const world = JSON.parse(readFileSync(resolve('public/worlds/dragon-raja-free-day.world.json'), 'utf8'));
    const transport = await LocalWorldTransport.create(world.initial as InitialState, { worldId: world.initial.worldId, roll: () => 13 });
    const record = transport.snapshot() as unknown as WorldRecordLike & Record<string, unknown>;
    const coverage = verifyTaskCoverage(record);
    expect(coverage.ok, JSON.stringify(coverage.errors)).toBe(true);
    expect(coverage.initialCharacters).toBe(14);
    expect(coverage.initialTasks).toBe(73);
    expect(coverage.achieved).toBeLessThanOrEqual(coverage.tasks);

    const tampered = structuredClone(record) as WorldRecordLike & Record<string, unknown>;
    const state = tampered.state as WorldState;
    const tasks = Object.keys(state.characters.lu.tasks);
    expect(tasks.length).toBeGreaterThan(0);
    delete state.characters.lu.tasks[tasks[0]];
    const bad = verifyTaskCoverage(tampered);
    expect(bad.ok).toBe(false);
    expect(bad.errors.map((item) => item.code)).toContain('task_regressed');
  });

  it('checks the real full-world task decision ledger shape', () => {
    const full = {
      tasks: 14, taskRows: 73, mode: 'per_character_decision',
      achievedByCharacter: [], assertedUnchanged: 73,
    };
    expect(verifyTaskDecisionEvidence(full).ok).toBe(true);
    expect(verifyTaskDecisionEvidence({ ...full, tasks: 1 }).errors.map((item) => item.code)).toContain('task_coverage');
    expect(verifyTaskDecisionEvidence({ ...full, taskRows: 12 }).errors.map((item) => item.code)).toContain('task_coverage');
    expect(verifyTaskDecisionEvidence({ ...full, excluded: ['onstage_only'] }).errors.map((item) => item.code)).toContain('task_coverage');
    const rejected = verifyTaskDecisionEvidence({ ...full, rejectedTaskIds: [{ characterId: 'doctor', taskId: 'task_doctor_flag' }] });
    expect(rejected.errors.map((item) => item.code)).toContain('task_coverage');
  });

  it('does not call a retained failed input a committed history', async () => {
    const initial = fixture.normal.initial as InitialState;
    const record = await recordOf(initial, []);
    const report = verifyDisplayHistory({ transport: record, commands: ['failed input kept for resume'] });
    expect(report.total).toBe(0);
    expect(report.errors).toEqual([]);
    expect(report.warnings.map((item) => item.code)).toContain('history_missing_command');
  });

  it('reports a command list shorter than the committed player history', async () => {
    const initial = fixture.normal.initial as InitialState;
    const s0 = buildInitialState(structuredClone(initial));
    const record = await recordOf(initial, [point(s0, 1, {})]);
    const report = verifyDisplayHistory({ transport: record, commands: [] });
    expect(report.total).toBe(1);
    expect(report.errors.map((item) => item.code)).toContain('history_missing_command');
    expect(report.warnings.map((item) => item.code)).toContain('history_text_missing');
  });

  it('warns, rather than failing, when the visible history delta is unusual', () => {
    const result = verifyVisibleAcceptance([
      { before: { historyCount: 4 }, after: { historyCount: 4 }, text: '正文', historyDelta: 0 },
    ]);
    expect(result.errors).toEqual([]);
    expect(result.warnings.map((item) => item.code)).toContain('history_delta');
  });

  it('rejects a displayed draft with no committed point or accepted text', () => {
    const report = verifyDisplayedCommit([{
      turn: 1,
      text: '一段草稿正文。',
      textSource: 'draft',
      historyDelta: 0,
      product: { source: 'draft', acceptedMs: null, draftMs: 176_322 },
      timings: { doneMs: 330_053, firstReadableMs: 176_487 },
      problems: ['draft_only_not_accepted', 'over_300s'],
      submission: null,
    }]);
    expect(report.ok).toBe(false);
    const codes = report.errors.map((item) => item.code);
    expect(codes).toContain('history_text_missing');
    expect(codes).toContain('evidence_shape');
    expect(report.warnings.map((item) => item.code)).toContain('history_delta');
    expect(report.errors.some((item) => item.detail.includes('draft'))).toBe(true);
  });

  it('accepts a committed turn with accepted text and a history delta', () => {
    const report = verifyDisplayedCommit([{
      turn: 1,
      text: '已采纳的正文。',
      textSource: 'accepted',
      historyDelta: 1,
      product: { source: 'accepted', acceptedMs: 42_000 },
      timings: { doneMs: 42_000, firstReadableMs: 8_000 },
      submission: { inputText: '我走过去。' },
    }]);
    expect(report.errors).toEqual([]);
    expect(report.ok).toBe(true);
  });
});
