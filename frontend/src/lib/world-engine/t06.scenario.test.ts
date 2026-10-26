import { describe, expect, test } from 'vitest';
import { driveControllerSlice } from './harness';
import { buildT06Scenario } from './t06.scenario';
import { WorldTimeoutError } from './transport';
import type { FaultAction, FaultAttempt } from './fault-transport';
import type { ErrorCode, Json, Scope } from './types';

type Scenario = ReturnType<typeof buildT06Scenario>;

async function beforeStep(scenario: Scenario, stepId: string) {
  for (let i = 0; i < 500; i++) {
    // #7：控制器段在录制预览 s16（已改为 harness 校验位）处分成两段。
    if (scenario.transport.nextStepId === 's16' && scenario.driver.pendingDecision().kind === 'transport') {
      await scenario.transport.runInspect('s16');
      continue;
    }
    if (scenario.transport.nextStepId === stepId && scenario.driver.pendingDecision().kind === 'transport') return;
    const terminal = await scenario.driver.step();
    if (terminal) throw new Error(`Ended before ${stepId}: ${JSON.stringify(terminal)}`);
  }
  throw new Error(`Never reached ${stepId}`);
}

async function runToTerminal(scenario: Scenario): Promise<{ kind: string; reason?: string; detail?: string }> {
  for (let i = 0; i < 50; i++) {
    const terminal = await scenario.driver.step();
    if (terminal) return terminal;
  }
  throw new Error('T06 probe never reached a terminal status');
}

/** The recorded exchange of a step, re-identified for a direct transport
 * probe: recorded requestId stays stripped, the probe mints its own. */
function recordedScope(scenario: Scenario, stepId: string): Scope {
  const step = scenario.corpus.steps.find((candidate) => candidate.id === stepId);
  if (!step) throw new Error(`T06 corpus has no step ${stepId}`);
  return structuredClone(step.scope);
}
function probeRequest(scenario: Scenario, stepId: string, requestId: string): Json {
  return { ...(scenario.corpus.requests[stepId] as Record<string, Json>), requestId };
}

async function finish(scenario: Scenario) {
  await driveControllerSlice(scenario, 'T06 fault session');
  if (scenario.transport.nextStepId === 's16') await scenario.transport.runInspect('s16');
  await driveControllerSlice(scenario, 'T06 fault session');
  for (const stepId of ['s21', 's22', 's23']) await scenario.transport.runInspect(stepId);
  scenario.transport.assertConsumed();
  scenario.model.assertConsumed();
  scenario.fault.assertFaultsConsumed();
  expect(scenario.driver.pendingDecision()).toMatchObject({ kind: 'model', task: 'continuation' });
  // #7 后 T01 多 5 次逐人判断（b–f 全 skip）。
  expect(scenario.driver.getMemory()).toMatchObject({ planIndex: 1, staged: [], stagedTimeScan: null, groupActors: [], narration: null, budget: { used: 13 } });
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
    // #7 后 leftover 逐人判断也存在；被复用的 confirmed work 仍是 a 的行动、
    // 结算与更新，没有被重新采样。
    expect(scenario.model.calls.filter((call) => call.task === 'results' || call.task === 'updates' || (call.task === 'action' && call.key === 'person_a')).map((call) => call.task)).toEqual(['action', 'results', 'updates']);
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

  test('only the bridge refresh moves the retried commit binding forward', async () => {
    const probe = buildT06Scenario(sampleId, []);
    const recorded = (probe.corpus.requests.s18 as Record<string, Json>).expectedCheckpointRevision as number;
    const sealed = structuredClone(probe.corpus.servedAfter.s17);
    const bridgeOnly = { ...sealed, control: { ...sealed.control!, revision: recorded + 1 } };
    // The error envelope stays at the recorded revision; ONLY the bridge
    // carries the bump — a driver that skips or ignores the refresh hop
    // binds the envelope's revision and fails this assertion.
    const scenario = buildT06Scenario(sampleId, [{ stepId: 's18', operation: 'commit_point', actions: [
      { kind: 'error', code: 'version_mismatch', bridge: bridgeOnly },
      { kind: 'timeout_before_send' }, { kind: 'timeout_before_send' }, { kind: 'timeout_before_send' }, { kind: 'timeout_before_send' },
    ] }]);
    await beforeStep(scenario, 's18');
    expect(await runToTerminal(scenario)).toMatchObject({ kind: 'error', detail: expect.stringContaining('retry limit exceeded on commit_point') });
    const attempts = scenario.fault.attempts.filter((attempt) => attempt.stepId === 's18');
    expect(attempts.map((attempt) => attempt.operation)).toEqual(['commit_point', 'get_context', 'commit_point', 'commit_point', 'commit_point', 'commit_point']);
    expect(attempts.map((attempt) => attempt.outcome)).toEqual(['error', 'context_bridge', 'timeout_before_send', 'timeout_before_send', 'timeout_before_send', 'timeout_before_send']);
    const revisions = attempts.filter((attempt) => attempt.operation === 'commit_point').map((attempt) => (attempt.request as Record<string, Json>).expectedCheckpointRevision);
    expect(revisions[0]).toBe(recorded);
    for (const revision of revisions.slice(1)) expect(revision).toBe(recorded + 1);
    scenario.fault.assertFaultsConsumed();
  });

  test('a requestId reused for a different operation gets the server-shaped request_id_reused', async () => {
    const scenario = buildT06Scenario(sampleId, []);
    await beforeStep(scenario, 's2');
    const scope = recordedScope(scenario, 's2');
    await scenario.fault.execute('narration_claim', probeRequest(scenario, 's2', 't06_probe_reused') as never, scope as never);
    await expect(scenario.fault.execute('narration_submit', probeRequest(scenario, 's20', 't06_probe_reused') as never, scope as never))
      .rejects.toMatchObject({ response: { error: { code: 'request_id_reused' } } });
    const attempt = scenario.fault.attempts.filter((candidate) => candidate.operation === 'narration_submit').at(-1);
    expect(attempt).toMatchObject({ outcome: 'error', code: 'request_id_reused' });
  });

  test('a definitively retired requestId refuses same-payload reuse with a ProtocolError', async () => {
    const scenario = buildT06Scenario(sampleId, [{ stepId: 's2', actions: [{ kind: 'error', code: 'claim_fenced' }] }]);
    await beforeStep(scenario, 's2');
    const request = probeRequest(scenario, 's2', 't06_probe_retired') as never;
    const scope = recordedScope(scenario, 's2') as never;
    await expect(scenario.fault.execute('narration_claim', request, scope)).rejects.toMatchObject({ response: { error: { code: 'claim_fenced' } } });
    await expect(scenario.fault.execute('narration_claim', request, scope)).rejects.toThrow(/\[fault\] retired requestId/);
  });

  test('a replayed narration claim is a summary without the claim token', async () => {
    const scenario = buildT06Scenario(sampleId, [{ stepId: 's2', actions: [{ kind: 'lose_response' }] }]);
    await beforeStep(scenario, 's2');
    const request = probeRequest(scenario, 's2', 't06_probe_claim') as never;
    const scope = recordedScope(scenario, 's2') as never;
    await expect(scenario.fault.execute('narration_claim', request, scope)).rejects.toBeInstanceOf(WorldTimeoutError);
    const replay = await scenario.fault.execute('narration_claim', request, scope) as unknown as { replayed: boolean; data: Record<string, Json> };
    expect(replay.replayed).toBe(true);
    expect(replay.data.claimToken).toBeUndefined();
    const acceptance = scenario.fault.acceptances.find((candidate) => candidate.operation === 'narration_claim');
    expect((acceptance?.response as { data: { claimToken?: string } }).data.claimToken).toEqual(expect.any(String));
  });

  test('the context bridge refuses a mismatched refresh scope', async () => {
    const scenario = buildT06Scenario(sampleId, [{ stepId: 's18', operation: 'commit_point', actions: [{ kind: 'error', code: 'version_mismatch' }] }]);
    await beforeStep(scenario, 's18');
    await expect(scenario.fault.execute('commit_point', probeRequest(scenario, 's18', 't06_probe_bridge') as never, recordedScope(scenario, 's18') as never))
      .rejects.toMatchObject({ response: { error: { code: 'version_mismatch' } } });
    await expect(scenario.fault.execute('get_context', {}, { worldId: 't06-other-world' } as never)).rejects.toThrow(/\[fault\] refresh context request\/scope mismatch/);
  });
});

test('T06 fault transport rejects unconsumed scripts', () => {
  const scenario = buildT06Scenario('sample_1', [{ stepId: 's3', actions: [{ kind: 'lose_response' }] }]);
  expect(() => scenario.fault.assertFaultsConsumed()).toThrow(/s3/);
});
