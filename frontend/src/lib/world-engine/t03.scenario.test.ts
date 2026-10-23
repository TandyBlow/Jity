/** T03 time-scan and collapse acceptance: non-empty scan deltas reach the
 * later previews through the same settlement list (A §7), the seal preview
 * aligns with the final independent expectation, and the collapse group's
 * candidates carry the ruled world-roster coverage. */
import { describe, expect, test } from 'vitest';
import { assertSharedExpectation, driveControllerSegment } from './harness';
import { buildT03Scenario, openT03Session, type T03TraceName } from './t03.scenario';
import type { Json, SettlementGroup } from './types';

const ROSTER = ['person_a', 'person_b', 'person_c', 'person_d', 'person_e', 'person_f'];

interface PreviewData {
  workingState: {
    time: Json;
    characters: Record<string, {
      sanity: number;
      tasks: Record<string, { status: string; parentTaskId: string | null }>;
      appearanceChanges: { id: string; sourcePointId: string; active: boolean }[];
      personalityChanges: { id: string; sourcePointId: string; active: boolean }[];
    }>;
  };
  pointProjection: { entityDeltas: Record<string, Json> };
  mergedEntityDeltas: Record<string, Json>;
}

const EXPECTED_TIMES: Record<T03TraceName, { dateTime: string; instantOrdinal: number }> = {
  'T03': { dateTime: '2026-01-01T12:00:00', instantOrdinal: 0 },
  'T03-collapse': { dateTime: '2026-01-01T11:59:07', instantOrdinal: 0 },
};

async function runT03Acceptance(traceName: T03TraceName, sampleId: string) {
  const scenario = buildT03Scenario(traceName, sampleId);
  await openT03Session(scenario);
  await driveControllerSegment(scenario, traceName);
  const { step, response } = await scenario.transport.runInspect(scenario.finalStepId);
  assertSharedExpectation(step, response);
  expect(scenario.driver.pendingDecision()).toMatchObject({ kind: 'model', task: 'continuation', key: scenario.roundId });
  scenario.transport.assertConsumed();
  scenario.model.assertConsumed();
  return scenario;
}

describe.each([
  ['T03', 'sample_1'],
  ['T03', 'sample_2'],
  ['T03-collapse', 'sample_1'],
  ['T03-collapse', 'sample_2'],
] as [T03TraceName, string][])('%s %s: scan/collapse segment, previews, inspect, stop boundary', (traceName, sampleId) => {
  test('opens the session, drives the scan point, ends at the continuation boundary', async () => {
    const scenario = await runT03Acceptance(traceName, sampleId);

    // Context bootstrap, then controller-issued allocation for collapse.
    expect(scenario.transport.ops[0]).toBe('get_context');
    expect(scenario.transport.ops).not.toContain('create_world');
    expect(scenario.transport.ops).toContain(traceName === 'T03' ? 'checkpoint_stage_time_scan' : 'checkpoint_stage_unit');

    // Preview specimens: begin + the stage anchor, placeholder digests.
    const previews = scenario.corpus.steps.filter((s) => s.segment === 'preview');
    expect(previews).toHaveLength(2);
    expect(previews.every((s) => s.placeholderDigests === true)).toBe(true);
    const [beginPreview, sealPreview] = previews;

    // THE A §7 point: the stage anchor's preview carries the staged unit in
    // its settlement list — T03's scan candidate (groupId null, non-empty
    // sections), T03-collapse's group candidates under the ruled coverage.
    const suffix = sampleId === 'sample_2' ? '_sampleB' : '';
    const pointId = `${traceName === 'T03' ? 'time_only' : 'p4'}${suffix}`;
    const groupId = `group_task${suffix}`;
    const sealGroups = (sealPreview.request as unknown as { settlementGroups: SettlementGroup[] }).settlementGroups;
    expect(sealGroups).toHaveLength(1);
    if (traceName === 'T03') {
      expect(sealGroups[0]).toMatchObject({ groupId: null, sanities: { person_c: 35 } });
    } else {
      expect(sealGroups[0]).toMatchObject({ groupId });
    }
    expect(sealGroups[0].taskCoverageIds).toEqual(ROSTER);
    expect(sealGroups[0].personalityCoverageIds).toEqual(ROSTER);

    // Bodies: the begin preview is the inherited base state under the staged
    // time; the seal preview is the committed final state (serve-time
    // alignment binds it to the independent expectation).
    const begin = (beginPreview.response as unknown as { data: PreviewData }).data;
    const seal = (sealPreview.response as unknown as { data: PreviewData }).data;
    expect(begin.workingState.time).toMatchObject(EXPECTED_TIMES[traceName]);
    expect(seal.workingState.time).toEqual(begin.workingState.time);
    expect(begin.pointProjection.entityDeltas).toEqual({});
    expect(begin.mergedEntityDeltas).toEqual({});
    expect((beginPreview.request as { settlementGroups: unknown[] }).settlementGroups).toEqual([]);
    expect(seal.mergedEntityDeltas).toEqual(seal.pointProjection.entityDeltas);
    expect(Object.keys(seal.mergedEntityDeltas)).toEqual(['person_c']);
    const before = begin.workingState.characters.person_c;
    const after = seal.workingState.characters.person_c;
    expect(before.sanity).toBe(30);
    expect(before.tasks.task_wait_noon.status).toBe('pending');
    expect(before.appearanceChanges).toEqual([]);
    expect(before.personalityChanges).toEqual([]);
    if (traceName === 'T03') {
      expect(after.sanity).toBe(35);
      expect(after.tasks.task_wait_noon.status).toBe('achieved');
      expect(after.personalityChanges).toEqual([expect.objectContaining({ sourcePointId: pointId, active: true })]);
    } else {
      const parent = `task_new_parent${suffix}`;
      const child = `task_new_child${suffix}`;
      expect(before.tasks[parent]).toBeUndefined();
      expect(before.tasks[child]).toBeUndefined();
      expect(after.tasks[parent]).toMatchObject({ status: 'pending', parentTaskId: 'task_c_root' });
      expect(after.tasks[child]).toMatchObject({ status: 'achieved', parentTaskId: parent });
      expect(after.appearanceChanges).toEqual([expect.objectContaining({ id: `change_final${suffix}`, sourcePointId: pointId, active: true })]);
      // The candidate adds a pending child and achieves it in the same unit;
      // the server projection collapses that into one achieved addition.
      expect(sealGroups[0].tasksAchieved.person_c).toEqual([child]);
      expect(sealGroups[0].subtasksAdded.person_c.find((task) => task.id === child)?.status).toBe('pending');
      expect(seal.pointProjection.entityDeltas.person_c).toMatchObject({
        subtasksAdded: [expect.objectContaining({ id: parent, status: 'pending' }), expect.objectContaining({ id: child, status: 'achieved' })],
      });
      expect(seal.pointProjection.entityDeltas.person_c).not.toHaveProperty('tasksAchieved');
    }

    // Roster legality of the collapse group: what the DRIVER sent.
    const sentStage = scenario.transport.requests.map((r) => r as { candidates?: SettlementGroup }).find((r) => r.candidates?.groupId === groupId);
    if (traceName === 'T03-collapse') {
      expect(sentStage).toBeDefined();
      expect(sentStage!.candidates!.taskCoverageIds).toEqual(ROSTER);
      expect(sentStage!.candidates!.personalityCoverageIds).toEqual(ROSTER);
    }

    // Model calls: generated from the recording.
    const calls = scenario.model.calls.map((c) => `${c.task}:${c.key}`);
    expect(calls[0]).toBe(`pointPlan:${scenario.roundId}`);
    if (traceName === 'T03') {
      expect(calls).toEqual([`pointPlan:${scenario.roundId}`, `updates:time_scan:${pointId}`, `narration:${pointId}`]);
    } else {
      expect(calls).toEqual([`pointPlan:${scenario.roundId}`, 'action:person_c', 'targets:person_c', `results:${groupId}`, `updates:${groupId}`, `narration:${pointId}`]);
    }
    // Model generation at the stage boundary reads the previously served
    // begin preview, never the yet-unserved post-stage state.
    const updates = scenario.model.calls.find((call) => call.task === 'updates')!;
    expect((updates.input as { workingState: Json }).workingState).toEqual(begin.workingState);
    expect(scenario.driver.getMemory().stagedTimeScan).toBeNull();
    expect(scenario.driver.getMemory().staged).toEqual([]);
    expect(scenario.transport.ops).toHaveLength(traceName === 'T03' ? 10 : 14);
    if (traceName === 'T03-collapse') {
      expect(scenario.transport.ops[1]).toBe('allocate_ids');
      expect((scenario.transport.requests[1] as { requestId: string }).requestId).toMatch(/^req_T03-collapse_\d+$/);
      expect(scenario.driver.getMemory().ids['group:person_c']).toBe(groupId);
      expect(scenario.driver.getMemory().ids.point).toBe(pointId);
    }
  });

  test('rejects a preview that drops the staged scan/group candidate', async () => {
    const scenario = buildT03Scenario(traceName, sampleId);
    const sealPreview = scenario.corpus.steps.filter((s) => s.segment === 'preview').at(-1)!;
    (sealPreview.request as { settlementGroups: unknown[] }).settlementGroups = []; // the pre-fix driver bug
    await openT03Session(scenario);
    await expect(driveControllerSegment(scenario, traceName)).rejects.toThrow(/request mismatch/);
  });

  test('rejects a begin preview that leaks the later staged state into model input', async () => {
    const scenario = buildT03Scenario(traceName, sampleId);
    const [beginPreview, sealPreview] = scenario.corpus.steps.filter((s) => s.segment === 'preview');
    (beginPreview.response as { data: { workingState: Json } }).data.workingState = structuredClone((sealPreview.response as { data: { workingState: Json } }).data.workingState);
    await openT03Session(scenario);
    await expect(driveControllerSegment(scenario, traceName)).rejects.toThrow(/input mismatch/);
  });
});

describe('T03 harness directed negatives', () => {
  test('round entry allocates even when old slot values remain in memory', async () => {
    const scenario = buildT03Scenario('T03-collapse', 'sample_1');
    scenario.memory.ids['group:person_c'] = 'old_round_group';
    scenario.memory.ids.point = 'old_round_point';
    await openT03Session(scenario);
    await driveControllerSegment(scenario);
    expect(scenario.transport.ops.filter((operation) => operation === 'allocate_ids')).toHaveLength(1);
    expect(scenario.driver.getMemory().ids['group:person_c']).toBe('group_task');
    expect(scenario.driver.getMemory().ids.point).toBe('p4');
  });

  test('a mismatched round allocation stops before pointPlan or action generation', async () => {
    const scenario = buildT03Scenario('T03-collapse', 'sample_1');
    const allocate = scenario.corpus.steps.find((step) => step.operation === 'allocate_ids')!;
    (allocate.response as { data: { allocations: { slotKey: string }[] } }).data.allocations.at(-1)!.slotKey = 'unexpected_slot';
    await openT03Session(scenario);
    await expect(driveControllerSegment(scenario)).rejects.toThrow(/Allocation response does not match requested slots/);
    expect(scenario.model.calls).toEqual([]);
  });

  test('rejects a tampered final digest at the inspect read', async () => {
    const scenario = buildT03Scenario('T03', 'sample_1');
    const finalStep = scenario.corpus.steps.find((s) => s.sharedStepId === scenario.finalStepId)!;
    finalStep.expectation!.expectedDigest = 'f'.repeat(64);
    await openT03Session(scenario);
    await driveControllerSegment(scenario, 'T03');
    await expect(scenario.transport.runInspect(scenario.finalStepId)).rejects.toThrow(/shared digest mismatch/);
  });

  test('rejects a tampered seal preview body via the final alignment', async () => {
    const scenario = buildT03Scenario('T03-collapse', 'sample_1');
    const sealPreview = scenario.corpus.steps.filter((s) => s.segment === 'preview').at(-1)!;
    (((sealPreview.response as { data: { workingState: { characters: Record<string, { sanity: number }> } } }).data.workingState).characters).person_c.sanity = 99;
    await openT03Session(scenario);
    await driveControllerSegment(scenario, 'T03-collapse');
    await expect(scenario.transport.runInspect(scenario.finalStepId)).rejects.toThrow(/preview alignment broken/);
  });
});
