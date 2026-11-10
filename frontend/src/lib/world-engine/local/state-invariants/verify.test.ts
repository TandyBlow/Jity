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
  pointContinuityIssues, RecordInvariantError, verifyWorldRecord,
  type WorldRecordLike,
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
