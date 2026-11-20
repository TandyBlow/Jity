import { describe, expect, test } from 'vitest';
import { driveControllerSlice } from './harness';
import { buildT08Scenario, type T08Mode } from './t08.scenario';
import type { Json } from './types';

async function driveT08(sampleId: string, mode: T08Mode) {
  const scenario = buildT08Scenario(sampleId, mode);
  await scenario.transport.runInspect('s1');
  await driveControllerSlice(scenario, 'T08 prepare successor');
  expect(scenario.transport.nextStepId).toBe('s8');
  const beforeProbe = scenario.driver.getMemory();
  await expect(scenario.transport.runProbe('s8')).rejects.toMatchObject({ response: { error: { code: 'point_time_locked', clientAction: 'fix_request' } } });
  expect(scenario.driver.getMemory()).toEqual(beforeProbe);
  await driveControllerSlice(scenario, 'T08 commit and narration');
  expect(scenario.transport.nextStepId).toBe('s13');
  expect(scenario.driver.pendingDecision()).toMatchObject({ kind: 'read_working_state' });
  scenario.driver.deliver({ kind: 'cancel', reason: scenario.cancelReason });
  expect(await scenario.driver.step()).toBeUndefined();
  expect(await scenario.driver.step()).toEqual({ kind: 'stop', reason: 'world_complete' });
  return scenario;
}

describe.each([
  ['sample_1', 'normal'], ['sample_2', 'normal'],
  ['sample_1', 'commit_conflict'], ['sample_2', 'commit_conflict'],
] as [string, T08Mode][])('T08 %s %s', (sampleId, mode) => {
  test('reserves the successor, preserves locked time and cancels before successor computation', async () => {
    const scenario = await driveT08(sampleId, mode);
    const context = await scenario.transport.runInspect('s14');
    expect(context.response).toMatchObject({ activeInput: null, work: null, world: { activeRoundId: null, advance: { inputAvailable: false, intentStatus: 'expired' }, time: { dateTime: '2026-01-01T11:59:02', instantOrdinal: 0 } } });
    await scenario.transport.runInspect('s15');
    scenario.transport.assertConsumed();
    scenario.model.assertConsumed();
    expect(scenario.transport.ops).not.toContain('checkpoint_seal_point'); // prepare_successor sealed the predecessor
    expect(scenario.transport.ops).not.toContain('checkpoint_record_skip');
    expect(scenario.model.calls.map((call) => call.task)).toEqual(['pointPlan', 'action', 'targets', 'results', 'updates', 'time', 'narration']);
    const commits = scenario.transport.requests.filter((request) => (request as { point?: unknown }).point && (request as { settlementGroups?: unknown }).settlementGroups) as { requestId: string; point: { timeAdvance: Json } }[];
    expect(commits).toHaveLength(mode === 'normal' ? 1 : 2);
    for (const commit of commits) expect(commit.point.timeAdvance).toEqual({ boundary: 'elapsed', duration: { amount: 2, unit: 'second' } });
    if (mode === 'commit_conflict') {
      const { requestId: firstId, ...firstBody } = commits[0];
      const { requestId: secondId, ...secondBody } = commits[1];
      expect(firstId).not.toBe(secondId);
      expect(firstBody).toEqual(secondBody);
      const faultIndex = scenario.transport.ops.indexOf('commit_point');
      expect(scenario.transport.ops.slice(faultIndex, faultIndex + 3)).toEqual(['commit_point', 'get_context', 'commit_point']);
    }
    const timeCall = scenario.model.calls.find((call) => call.task === 'time')!;
    const stagePreview = scenario.corpus.steps.find((step) => step.id === 'b-t08-after-stage')!;
    expect((timeCall.input as { workingState: Json }).workingState).toEqual((stagePreview.response as { data: { workingState: Json } }).data.workingState);
    expect((stagePreview.request as { settlementGroups: unknown[] }).settlementGroups).toHaveLength(1);
    expect(scenario.driver.getMemory()).toMatchObject({ prepareSuccessor: false, successorTime: null, workingState: null, plan: null, sources: [], staged: [], commitPayload: null });
  });

  test('rejects tampering with the successful commit digest', async () => {
    const scenario = buildT08Scenario(sampleId, mode);
    (scenario.corpus.steps.find((step) => step.id === 's10')!.response as { data: { stateDigest: string } }).data.stateDigest = 'f'.repeat(64);
    await scenario.transport.runInspect('s1');
    await driveControllerSlice(scenario);
    await expect(scenario.transport.runProbe('s8')).rejects.toMatchObject({ response: { error: { code: 'point_time_locked' } } });
    await expect(driveControllerSlice(scenario)).rejects.toThrow(/digest chain broken/);
  });

  test('rejects tampering with the independent final state', async () => {
    const scenario = await driveT08(sampleId, mode);
    const final = scenario.corpus.steps.find((step) => step.id === 's15')!;
    (final.response as { data: { state: { characters: Record<string, { sanity: number }> } } }).data.state.characters.person_a.sanity++;
    await scenario.transport.runInspect('s14');
    await expect(scenario.transport.runInspect('s15')).rejects.toThrow(/shared projection mismatch/);
  });
});
