import { describe, expect, test } from 'vitest';
import { driveControllerSlice } from './harness';
import { buildT05Scenario, type T05PauseOrigin } from './t05.scenario';
import type { ControlState } from './types';

type T05Scenario = ReturnType<typeof buildT05Scenario>;

async function openAndPause(scenario: T05Scenario) {
  await scenario.transport.runInspect('s1');
  scenario.driver.deliver(scenario.pauseCommand);
  expect(await scenario.driver.step()).toBeUndefined();
  expect(scenario.driver.getMemory().localPause).toBe(scenario.pauseOrigin === 'budget');
}

async function renewAndResume(scenario: T05Scenario) {
  const beforeHeartbeat = scenario.driver.getMemory();
  const lease = await scenario.transport.runHeartbeat('s3');
  const claim = await scenario.transport.runHeartbeat('s4');
  expect(lease.response).toMatchObject({ control: { paused: true, canCompute: false } });
  expect(claim.response).toMatchObject({ control: { paused: true, canCompute: false }, data: { generation: 1 } });
  // These exchanges are harness-owned, with no driver request or model call.
  expect(scenario.driver.getMemory()).toEqual(beforeHeartbeat);
  expect(scenario.model.calls).toEqual([]);
  scenario.driver.deliver({ kind: 'resume' });
  expect(await scenario.driver.step()).toBeUndefined();
  expect(scenario.driver.getMemory().localPause).toBe(false);
  expect(scenario.driver.getMemory().narration?.claim).toBeNull();
  expect(scenario.driver.pendingDecision()).toMatchObject({ kind: 'transport', operation: 'narration_claim' });
}

async function pauseAndNarrate(scenario: T05Scenario) {
  scenario.driver.deliver(scenario.pauseCommand);
  expect(await scenario.driver.step()).toBeUndefined();
  await driveControllerSlice(scenario, 'T05 narration while paused');
  expect(scenario.transport.nextStepId).toBe('s9');
  expect(scenario.driver.getMemory().narration).toBeNull();
}

describe.each([
  ['sample_1', 'external'], ['sample_2', 'external'],
  ['sample_1', 'budget'], ['sample_2', 'budget'],
] as [string, T05PauseOrigin][])('T05 %s %s pause', (sampleId, pauseOrigin) => {
  test('resumes into a blocked claim, completes narration while paused and stays paused at ready', async () => {
    const scenario = buildT05Scenario(sampleId, pauseOrigin);
    await openAndPause(scenario);
    await renewAndResume(scenario);
    await pauseAndNarrate(scenario);
    const reason = pauseOrigin === 'budget' ? 'local_budget_pause' : 'paused_externally';
    const callsAtReady = [...scenario.transport.ops];
    expect(await scenario.driver.step()).toEqual({ kind: 'await', reason });
    expect(await scenario.driver.step()).toEqual({ kind: 'await', reason });
    expect(scenario.transport.ops).toEqual(callsAtReady);
    expect(scenario.driver.getMemory()).toMatchObject({ localPause: pauseOrigin === 'budget', budget: { used: 1, max: 0 } });
    const final = await scenario.transport.runInspect('s9');
    expect(final.response).toMatchObject({ world: { head: { narrationStatus: 'ready', version: 0 }, advance: { intentStatus: 'pending', inputAvailable: true } } });
    scenario.transport.assertConsumed();
    scenario.model.assertConsumed();
    expect(scenario.transport.ops).toEqual(['get_context', 'checkpoint_pause', 'lease_renew', 'narration_claim_renew', 'checkpoint_resume', 'checkpoint_pause', 'narration_claim', 'narration_submit', 'get_state']);
    expect(scenario.model.calls.map((call) => call.task)).toEqual(['narration']);
    const submit = scenario.transport.requests[7] as { pointId: string; generation: number; issuedAtEpochMilli: number };
    const renewed = scenario.transport.requests[3] as { issuedAtEpochMilli: number };
    expect(submit.generation).toBe(2);
    expect(submit.issuedAtEpochMilli).toBeGreaterThan(renewed.issuedAtEpochMilli);
  });
});

describe.each(['sample_1', 'sample_2'])('T05 %s directed negatives', (sampleId) => {
  test.each([
    ['s2', 'paused', false],
    ['s5', 'canCompute', true],
    ['s8', 'paused', false],
    ['s8', 'canCompute', true],
  ] as const)('rejects %s control.%s drift at the response being consumed', async (stepId, field, incorrectValue) => {
    const scenario = buildT05Scenario(sampleId);
    const step = scenario.corpus.steps.find((entry) => entry.id === stepId)!;
    const control = (step.response as unknown as { control: ControlState }).control;
    control[field] = incorrectValue;
    // A coherent resume mutation must pass the shared schema so the
    // independent business rule, rather than a structural rule, rejects it.
    if (stepId === 's5') control.blockedReasons = [];
    const advance = async () => {
      await openAndPause(scenario);
      await renewAndResume(scenario);
      await pauseAndNarrate(scenario);
    };
    if (stepId === 's8' && field === 'canCompute') {
      // Paused + compute-enabled is already forbidden by the shared schema.
      await expect(advance()).rejects.toThrow(/NarrationSubmitSuccess:.*control/);
    } else {
      await expect(advance()).rejects.toThrow(`[T05] step ${stepId}: business assertion failed at /control/${field}`);
    }
    expect(scenario.transport.nextStepId).toBe(stepId);
    expect(scenario.transport.ops).not.toContain('get_state');
  });

  test('rejects a heartbeat response with a different fence', async () => {
    const scenario = buildT05Scenario(sampleId);
    (scenario.corpus.steps.find((step) => step.id === 's3')!.response as { data: { fenceEpoch: number } }).data.fenceEpoch++;
    await openAndPause(scenario);
    await expect(scenario.transport.runHeartbeat('s3')).rejects.toThrow(/digest chain broken/);
    expect(scenario.transport.nextStepId).toBe('s3');
  });

  test('rejects an old generation on the new narration claim', async () => {
    const scenario = buildT05Scenario(sampleId);
    (scenario.corpus.steps.find((step) => step.id === 's7')!.response as { data: { generation: number } }).data.generation = 1;
    await openAndPause(scenario);
    await renewAndResume(scenario);
    await expect(pauseAndNarrate(scenario)).rejects.toThrow(/business assertion failed at \/data\/generation/);
    expect(scenario.model.calls).toEqual([]);
  });

  test('rejects a tampered final state digest', async () => {
    const scenario = buildT05Scenario(sampleId);
    const final = scenario.corpus.steps.find((step) => step.id === 's9')!;
    (final.response as { data: { stateDigest: string } }).data.stateDigest = 'f'.repeat(64);
    await openAndPause(scenario);
    await renewAndResume(scenario);
    await pauseAndNarrate(scenario);
    await expect(scenario.transport.runInspect('s9')).rejects.toThrow(/shared digest mismatch/);
  });

  test('rejects a tampered final state body', async () => {
    const scenario = buildT05Scenario(sampleId);
    const final = scenario.corpus.steps.find((step) => step.id === 's9')!;
    (final.response as { data: { state: { characters: Record<string, { sanity: number }> } } }).data.state.characters.person_a.sanity++;
    await openAndPause(scenario);
    await renewAndResume(scenario);
    await pauseAndNarrate(scenario);
    await expect(scenario.transport.runInspect('s9')).rejects.toThrow(/shared projection mismatch/);
  });

  test('the budget event identifies a local pause even without a numeric cap', async () => {
    const scenario = buildT05Scenario(sampleId, 'budget', null);
    await openAndPause(scenario);
    await renewAndResume(scenario);
    await pauseAndNarrate(scenario);
    expect(await scenario.driver.step()).toEqual({ kind: 'await', reason: 'local_budget_pause' });
  });
});
