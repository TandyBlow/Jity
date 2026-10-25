import { describe, expect, test } from 'vitest';
import { driveControllerSlice } from './harness';
import { buildT04Scenario } from './t04.scenario';
import type { Json } from './types';

async function driveT04(sampleId: string) {
  const scenario = buildT04Scenario(sampleId);
  const initial = await scenario.transport.runInspect('s1');
  await driveControllerSlice(scenario, 'T04 continue');
  expect(scenario.transport.nextStepId).toBe('s3');
  const automatic = await scenario.transport.runInspect('s3');
  expect((automatic.response as { activeInput: Json }).activeInput).toEqual((initial.response as { activeInput: Json }).activeInput);
  expect(scenario.driver.getMemory().plan).toBeNull();
  expect(scenario.driver.getMemory().planIndex).toBe(0);
  await driveControllerSlice(scenario, 'T04 automatic and handback');
  return scenario;
}

describe.each(['sample_1', 'sample_2'])('T04 %s', (sampleId) => {
  test('continues the input chain into an automatic round, hands back and replays without resurrecting input', async () => {
    const scenario = await driveT04(sampleId);
    expect(await scenario.driver.step()).toEqual({ kind: 'stop', reason: 'world_complete' });
    const cleared = await scenario.transport.runInspect('s14');
    expect((cleared.response as { activeInput: unknown }).activeInput).toBeNull();
    const replay = await scenario.transport.runInspect('s15');
    expect(replay.response).toMatchObject({ replayed: true, world: { advance: { inputAvailable: false } } });
    const first = scenario.corpus.steps.find((step) => step.id === 's13')!;
    expect((replay.response as { data: Json }).data).toEqual((first.response as { data: Json }).data);
    const concludeWrites = scenario.transport.requests.filter((request) => (request as { operation?: string }).operation === 'conclude');
    expect(concludeWrites).toHaveLength(3);
    expect(concludeWrites[2]).toEqual(concludeWrites[1]);
    const final = await scenario.transport.runInspect('s16');
    expect(final.response).toMatchObject({ world: { advance: { inputAvailable: false } } });
    await scenario.transport.runInspect('s17');
    scenario.model.assertConsumed();
    scenario.transport.assertConsumed();
    expect(scenario.model.calls.map((call) => call.task)).toEqual(['continuation', 'pointPlan', 'action', 'targets', 'results', 'updates', 'narration', 'continuation']);
    expect(scenario.driver.getMemory()).toMatchObject({ plan: null, planIndex: 0, workingState: null, staged: [], sources: [], commitPayload: null, continuation: null, narration: null });
    for (const step of scenario.corpus.steps.filter((step) => step.operation !== 'get_context')) {
      expect(step.response).not.toHaveProperty('activeInput');
      expect((step.response as { data: Json }).data).not.toHaveProperty('inputText');
    }
  });

  test('rejects payload drift in the harness idempotency replay', async () => {
    const scenario = await driveT04(sampleId);
    await scenario.transport.runInspect('s14');
    (scenario.corpus.steps.find((step) => step.id === 's15')!.request as { expectedCheckpointRevision: number }).expectedCheckpointRevision++;
    await expect(scenario.transport.runInspect('s15')).rejects.toThrow(/retry payload drift/);
  });

  test.each([
    ['s2', false],
    ['s13', true],
  ] as const)('rejects an incorrect inputAvailable on conclude %s before consuming it', async (stepId, incorrectValue) => {
    const scenario = buildT04Scenario(sampleId);
    const conclude = scenario.corpus.steps.find((step) => step.id === stepId)!;
    (conclude.response as { world: { advance: { inputAvailable: boolean } } }).world.advance.inputAvailable = incorrectValue;
    await scenario.transport.runInspect('s1');
    if (stepId === 's13') {
      await driveControllerSlice(scenario);
      await scenario.transport.runInspect('s3');
    }
    await expect(driveControllerSlice(scenario)).rejects.toThrow(`[T04] step ${stepId}: business assertion failed at /world/advance/inputAvailable`);
    expect(scenario.transport.nextStepId).toBe(stepId);
    // s13 前的组装阶梯恰好一次目标读＋一次前驱读；s2 之前无叙事读取。
    if (stepId === 's13') {
      expect(scenario.transport.ops.filter((op) => op === 'get_state')).toHaveLength(2);
    } else {
      expect(scenario.transport.ops).not.toContain('get_state');
    }
    // Only the preceding continue can have been consumed. Neither the
    // following context nor replay is issued to mask the bad response.
    expect(scenario.transport.ops.filter((operation) => operation === 'round_conclusion_conclude')).toHaveLength(stepId === 's2' ? 0 : 1);
  });

  test('rejects tampering with the automatic round commit digest', async () => {
    const scenario = buildT04Scenario(sampleId);
    (scenario.corpus.steps.find((step) => step.id === 's10')!.response as { data: { stateDigest: string } }).data.stateDigest = 'f'.repeat(64);
    await scenario.transport.runInspect('s1');
    await driveControllerSlice(scenario);
    await scenario.transport.runInspect('s3');
    await expect(driveControllerSlice(scenario)).rejects.toThrow(/digest chain broken/);
  });

  test('rejects tampering with the final state read', async () => {
    const scenario = await driveT04(sampleId);
    const final = scenario.corpus.steps.find((step) => step.id === 's16')!;
    (final.response as { data: { state: { characters: Record<string, { sanity: number }> } } }).data.state.characters.person_a.sanity++;
    await scenario.transport.runInspect('s14');
    await scenario.transport.runInspect('s15');
    await expect(scenario.transport.runInspect('s16')).rejects.toThrow(/shared projection mismatch/);
  });

  test('a preview mutation cannot rewrite the independently declared model input', async () => {
    const scenario = buildT04Scenario(sampleId);
    const preview = scenario.corpus.steps.find((step) => step.id === 'b-t04-after-begin')!;
    (preview.response as { data: { workingState: { characters: Record<string, { sanity: number }> } } }).data.workingState.characters.person_c.sanity++;
    await scenario.transport.runInspect('s1');
    await driveControllerSlice(scenario);
    await scenario.transport.runInspect('s3');
    await expect(driveControllerSlice(scenario)).rejects.toThrow(/input mismatch/);
  });
});
