import { describe, expect, test } from 'vitest';
import { driveControllerSegment } from './harness';
import { buildT06Scenario } from './t06.scenario';
import type { FaultAction, FaultAttempt } from './fault-transport';
import type { ErrorCode, Json } from './types';

type Scenario = ReturnType<typeof buildT06Scenario>;

async function beforeStep(scenario: Scenario, stepId: string) {
  for (let i = 0; i < 500; i++) {
    if (scenario.transport.nextStepId === stepId && scenario.driver.pendingDecision().kind === 'transport') return;
    const terminal = await scenario.driver.step();
    if (terminal) throw new Error(`Ended before ${stepId}: ${JSON.stringify(terminal)}`);
  }
  throw new Error(`Never reached ${stepId}`);
}

async function finish(scenario: Scenario) {
  await driveControllerSegment(scenario, 'T06 fault session');
  for (const stepId of ['s21', 's22', 's23']) await scenario.transport.runInspect(stepId);
  scenario.transport.assertConsumed();
  scenario.model.assertConsumed();
  scenario.fault.assertFaultsConsumed();
  expect(scenario.driver.pendingDecision()).toMatchObject({ kind: 'model', task: 'continuation' });
  expect(scenario.driver.getMemory()).toMatchObject({ planIndex: 1, staged: [], stagedTimeScan: null, groupActors: [], narration: null, budget: { used: 8 } });
}

function sameAttempt(attempts: FaultAttempt[]) {
  expect(attempts.length).toBeGreaterThan(1);
  for (const attempt of attempts.slice(1)) {
    expect(attempt.operation).toBe(attempts[0].operation);
    expect(attempt.request).toEqual(attempts[0].request);
    expect(attempt.scope).toEqual(attempts[0].scope);
  }
}

describe.each(['sample_1', 'sample_2'])('T06 %s loss and idempotency', (sampleId) => {
  test.each(['s4', 's5', 's10', 's18', 's20'])('loses the accepted %s response, replays the same write and advances once', async (stepId) => {
    const scenario = buildT06Scenario(sampleId, [{ stepId, actions: [{ kind: 'lose_response' }] }]);
    await finish(scenario);
    const attempts = scenario.fault.attempts.filter((attempt) => attempt.stepId === stepId);
    sameAttempt(attempts);
    expect(attempts.map((attempt) => attempt.outcome)).toEqual(['lost_response', 'replayed']);
    expect(scenario.fault.acceptances.filter((acceptance) => acceptance.stepId === stepId)).toHaveLength(1);
    expect(scenario.transport.ops.filter((operation) => operation === attempts[0].operation)).toHaveLength(stepId === 's20' ? 2 : 1);
  });

  test('retries a before-acceptance timeout and an in-progress rejection with the same complete payload', async () => {
    const scenario = buildT06Scenario(sampleId, [{ stepId: 's10', actions: [{ kind: 'timeout_before_send' }, { kind: 'error', code: 'request_in_progress' }] }]);
    await finish(scenario);
    const attempts = scenario.fault.attempts.filter((attempt) => attempt.stepId === 's10');
    sameAttempt(attempts);
    expect(attempts.map((attempt) => attempt.outcome)).toEqual(['timeout_before_send', 'error', 'accepted']);
    expect(scenario.fault.acceptances.filter((acceptance) => acceptance.stepId === 's10')).toHaveLength(1);
  });

  test.each(['revision_mismatch', 'version_mismatch', 'phase_invalid'] as ErrorCode[])('%s refreshes context, retires the rejected id and preserves confirmed model work', async (code) => {
    const scenario = buildT06Scenario(sampleId, [{ stepId: 's18', operation: 'commit_point', actions: [{ kind: 'error', code }] }]);
    await finish(scenario);
    const attempts = scenario.fault.attempts.filter((attempt) => attempt.stepId === 's18');
    expect(attempts.map((attempt) => attempt.operation)).toEqual(['commit_point', 'get_context', 'commit_point']);
    const first = attempts[0].request as Record<string, Json>;
    const last = attempts[2].request as Record<string, Json>;
    expect(last.requestId).not.toBe(first.requestId);
    expect({ ...last, requestId: null }).toEqual({ ...first, requestId: null });
    expect(attempts[1].outcome).toBe('context_bridge');
    expect(scenario.model.calls.filter((call) => ['action', 'results', 'updates'].includes(call.task)).map((call) => call.task)).toEqual(['action', 'results', 'updates']);
  });

  test.each(['timeout_before_send', 'request_in_progress', 'lose_response'])('%s hits the retry bound and can resume the still-pending write without resampling', async (kind) => {
    const action: FaultAction = kind === 'request_in_progress' ? { kind: 'error', code: 'request_in_progress' } : { kind: kind as 'timeout_before_send' | 'lose_response' };
    const scenario = buildT06Scenario(sampleId, [{ stepId: 's18', actions: [action, action, action] }], 2);
    await beforeStep(scenario, 's18');
    const before = scenario.driver.getMemory();
    const calls = structuredClone(scenario.model.calls);
    expect(await scenario.driver.step()).toMatchObject({ kind: 'error', detail: expect.stringContaining('retry limit exceeded') });
    const attempts = scenario.fault.attempts.filter((attempt) => attempt.stepId === 's18');
    expect(attempts).toHaveLength(3);
    sameAttempt(attempts);
    expect(scenario.driver.getMemory()).toEqual(before);
    expect(scenario.model.calls).toEqual(calls);
    expect(scenario.fault.acceptances.filter((acceptance) => acceptance.stepId === 's18')).toHaveLength(kind === 'lose_response' ? 1 : 0);
    expect(await scenario.driver.step()).toBeUndefined();
    expect(scenario.driver.getMemory()).toMatchObject({ planIndex: 1, staged: [], commitPayload: null });
    await finish(scenario);
    expect(scenario.fault.acceptances.filter((acceptance) => acceptance.stepId === 's18')).toHaveLength(1);
  });

  test('a recovery-hop timeout uses the original operation retry budget', async () => {
    const scenario = buildT06Scenario(sampleId, [
      { stepId: 's18', operation: 'commit_point', actions: [{ kind: 'error', code: 'version_mismatch' }] },
      { stepId: 's18', operation: 'get_context', actions: [{ kind: 'timeout_before_send' }, { kind: 'timeout_before_send' }] },
    ], 2);
    await beforeStep(scenario, 's18');
    expect(await scenario.driver.step()).toMatchObject({ kind: 'error', detail: expect.stringContaining('retry limit exceeded on get_context') });
    const attempts = scenario.fault.attempts.filter((attempt) => attempt.stepId === 's18');
    expect(attempts.map((attempt) => attempt.operation)).toEqual(['commit_point', 'get_context', 'get_context']);
    expect(scenario.driver.getMemory().planIndex).toBe(0);
    expect(scenario.transport.nextStepId).toBe('s18');
    scenario.fault.assertFaultsConsumed();
  });
});
