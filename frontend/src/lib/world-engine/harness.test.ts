/** T01 fixed-response controller acceptance: the real ControllerDriver runs
 * the declared corpus for both shared samples; serve-time identity (runtime
 * digest chain, independent digest pins, preview↔expectation alignment,
 * shared independent expectations) and harness-issued inspect reads are
 * verified; directed negatives prove the harness rejects
 * request/scope/model mismatches, undeclared previews, request-id reuse,
 * recorded echo corruption and tampered shared digests or preview bodies. */
import { describe, expect, test } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { assertSharedExpectation, buildCorpus, ScenarioTransport } from './harness';
import { buildT01Scenario, driveControllerSegment } from './t01.scenario';
import type { Id, Json } from './types';

const rawT01 = () => JSON.parse(readFileSync(resolve(process.cwd(), '../design/world-protocol/v2/traces/T01.json'), 'utf8'));

async function runT01Acceptance(sampleId: string) {
  const scenario = buildT01Scenario(sampleId);
  await driveControllerSegment(scenario);

  // Inspect segment: harness-issued reads verified against the shared corpus.
  for (const id of ['s21', 's22', 's23']) {
    const { step, response } = await scenario.transport.runInspect(id);
    assertSharedExpectation(step, response);
  }

  // Declared stop boundary: the driver wants the continuation model call and
  // the harness ends the scenario without executing it.
  expect(scenario.driver.pendingDecision()).toMatchObject({ kind: 'model', task: 'continuation', key: scenario.roundId });

  scenario.transport.assertConsumed();
  scenario.model.assertConsumed();
  return scenario;
}

describe('T01 fixed-response controller acceptance', () => {
  test.each(['sample_1', 'sample_2'])('%s: controller segment, previews, inspect, stop boundary', async (sampleId) => {
    const scenario = await runT01Acceptance(sampleId);

    // Controller segment order: shared steps s1–s20 with one declared B
    // preview after begin; no command/probe claims for T01.
    expect(scenario.transport.ops).toEqual([
      'create_world', 'narration_claim', 'get_state', 'narration_submit', 'allocate_ids', 'checkpoint_start_advance',
      'checkpoint_begin_point', 'preview_point', 'checkpoint_discover_group', 'checkpoint_extend_group',
      'checkpoint_close_group', 'checkpoint_stage_unit',
      ...Array.from({ length: 5 }, () => 'checkpoint_record_skip' as const),
      'preview_point', 'checkpoint_seal_point', 'commit_point', 'narration_claim', 'get_state', 'get_state', 'narration_submit',
      'get_state', 'list_points', 'narration_get',
    ]);

    // Preview declarations: exactly one B specimen (after begin, placeholder
    // digests); the final preview is the shared s16 with real sample digests.
    const previews = scenario.corpus.steps.filter((s) => s.segment === 'preview');
    expect(previews.map((s) => s.id)).toEqual(['b-preview-after-begin-s6']);
    expect(previews.every((s) => s.placeholderDigests === true)).toBe(true);
    const s16 = scenario.corpus.steps.find((s) => s.sharedStepId === 's16')!;
    expect(s16.placeholderDigests).toBeUndefined();
    expect(String((s16.response as { data: { workingStateDigest: string } }).data.workingStateDigest)).not.toBe('0'.repeat(64));

    // The specimen stays inside T01's actual world: real protagonist, time,
    // roster, items and tasks — only the digests are placeholders. It is the
    // recorded s16 working state of the SAME point with the point's staged
    // entity deltas reverted to the recorded initial positions, and its
    // projection carries the recorded round (not the root point id).
    const specimen = scenario.corpus.steps.find((s) => s.id === 'b-preview-after-begin-s6')!;
    const specimenData = (specimen.response as { data: { workingState: Json; pointProjection: Json } }).data;
    const working = specimenData.workingState as { characters: Record<string, { position: Json; tasks: Record<string, unknown> }>; items: Record<string, unknown> };
    expect(specimenData.workingState).toMatchObject({ protagonistId: 'person_c', time: { calendar: 'gregorian', dateTime: '2026-01-01T11:59:02' } });
    expect(working.characters.person_a.position).toEqual({ containerId: 'lobby', slotId: null, relativeTo: null });
    expect(Object.keys(working.items).length).toBeGreaterThan(0);
    expect(Object.keys(working.characters.person_a.tasks)).toContain('task_a_root');
    const recorded16 = (s16.response as { data: { workingState: Json; pointProjection: Json } }).data;
    const reverted = structuredClone(recorded16.workingState);
    ((reverted as { characters: Record<string, { position: Json }> }).characters).person_a.position = { containerId: 'lobby', slotId: null, relativeTo: null };
    expect(specimenData.workingState).toEqual(reverted);
    expect(specimenData.pointProjection).toEqual({ ...(structuredClone(recorded16.pointProjection) as Record<string, unknown>), entityDeltas: {} });
    expect((specimenData.pointProjection as { roundId: Id }).roundId).toBe(scenario.roundId);

    // Model call order: task/key sequence, inputs already strictly verified.
    const rootId = scenario.corpus.servedAfter.s1.world!.head.pointId;
    const pointId = (scenario.corpus.requests.s6 as { pointId: string }).pointId;
    const groupId = (scenario.corpus.requests.s10 as { candidates: { groupId: string } }).candidates.groupId;
    expect(scenario.model.calls.map((c) => `${c.task}:${c.key}`)).toEqual([
      'initial:initial', `narration:${rootId}`, `pointPlan:${scenario.roundId}`, 'action:person_a',
      'targets:person_a', `results:${groupId}`, `updates:${groupId}`, `narration:${pointId}`,
    ]);

    // The inspect reads belong to the harness, not the driver.
    expect(scenario.transport.ops.slice(-3)).toEqual(['get_state', 'list_points', 'narration_get']);
  });
});

describe('T01 harness directed negatives', () => {
  test('rejects a driver request that breaks the identity binding', async () => {
    const scenario = buildT01Scenario('sample_1', undefined, { identityAliases: { 'group:person_a': 'no_such_slot' } });
    await expect(driveControllerSegment(scenario)).rejects.toThrow(/step s7 request mismatch/);
  });

  test('rejects a tampered declared request', async () => {
    const scenario = buildT01Scenario('sample_1');
    (scenario.corpus.steps.find((s) => s.sharedStepId === 's4')!.request as { allocationKey: string }).allocationKey = 'wrong_slots';
    await expect(driveControllerSegment(scenario)).rejects.toThrow(/step s4 request mismatch/);
  });

  test('rejects a tampered declared scope', async () => {
    const scenario = buildT01Scenario('sample_1');
    (scenario.corpus.steps.find((s) => s.sharedStepId === 's7')!.scope as { worldId: string }).worldId = 'other_world';
    await expect(driveControllerSegment(scenario)).rejects.toThrow(/step s7 scope mismatch/);
  });

  test('rejects a model call whose input does not match the declaration', async () => {
    const scenario = buildT01Scenario('sample_1');
    const action = scenario.model.declared.find((c) => c.task === 'action')!;
    (action.input as { actor: string }).actor = 'person_b';
    await expect(driveControllerSegment(scenario)).rejects.toThrow(/model call action\/person_a input mismatch/);
  });

  test('rejects an undeclared preview', async () => {
    const scenario = buildT01Scenario('sample_1');
    const previewIndex = scenario.corpus.steps.findIndex((s) => s.segment === 'preview');
    scenario.corpus.steps.splice(previewIndex, 1); // in place: the transport already holds this array
    await expect(driveControllerSegment(scenario)).rejects.toThrow(/declared checkpoint_discover_group, controller sent preview_point/);
  });

  test('rejects a tampered shared digest on the final expectation', async () => {
    const raw = rawT01();
    const sample = (raw.samples as { id: string; expectedDigests: Record<string, string> }[]).find((s) => s.id === 'sample_1')!;
    sample.expectedDigests.s21 = 'f'.repeat(64);
    const scenario = buildT01Scenario('sample_1', raw);
    await driveControllerSegment(scenario);
    // The independent expectation is enforced at serve time — the inspect
    // read itself refuses the tampered pin.
    await expect(scenario.transport.runInspect('s21')).rejects.toThrow(/shared digest mismatch/);
  });

  test('rejects a tampered final preview digest via the runtime digest chain', async () => {
    const scenario = buildT01Scenario('sample_1');
    (scenario.corpus.steps.find((s) => s.sharedStepId === 's16')!.response as { data: { workingStateDigest: string } }).data.workingStateDigest = 'f'.repeat(64);
    await expect(driveControllerSegment(scenario)).rejects.toThrow(/digest chain broken/);
  });

  test('rejects a tampered commit state digest via the runtime digest chain', async () => {
    const scenario = buildT01Scenario('sample_1');
    (scenario.corpus.steps.find((s) => s.sharedStepId === 's18')!.response as { data: { stateDigest: string } }).data.stateDigest = 'f'.repeat(64);
    await expect(driveControllerSegment(scenario)).rejects.toThrow(/digest chain broken/);
  });

  test('rejects a tampered point projection digest via the independent pin', async () => {
    const scenario = buildT01Scenario('sample_1');
    (scenario.corpus.steps.find((s) => s.sharedStepId === 's16')!.response as { data: { pointProjectionDigest: string } }).data.pointProjectionDigest = 'f'.repeat(64);
    await expect(driveControllerSegment(scenario)).rejects.toThrow(/independent digest pin broken/);
  });

  test('rejects a tampered final preview working state via the s21 alignment', async () => {
    const scenario = buildT01Scenario('sample_1');
    const working = (scenario.corpus.steps.find((s) => s.sharedStepId === 's16')!.response as { data: { workingState: { characters: Record<string, { sanity: number }> } } }).data.workingState;
    working.characters.person_a.sanity = 11; // the s21 independent expectation pins 10
    await driveControllerSegment(scenario);
    // The alignment binds s16's served body to s21's independent projection,
    // so the divergence surfaces when s21 is served.
    await expect(scenario.transport.runInspect('s21')).rejects.toThrow(/preview alignment broken/);
  });

  test('rejects a driver that reuses one requestId across operations', async () => {
    const scenario = buildT01Scenario('sample_1');
    (scenario.driver as unknown as { nextRequestId(): void }).nextRequestId = () => undefined;
    await expect(driveControllerSegment(scenario)).rejects.toThrow(/requestId req_T01_0 already used/);
  });

  test('rejects a corpus whose recorded response does not echo the request id', () => {
    const raw = rawT01();
    (raw.steps as { id: string; response: { requestId?: string } }[]).find((s) => s.id === 's1')!.response.requestId = 'req_other';
    expect(() => buildT01Scenario('sample_1', raw)).toThrow(/does not echo the request/);
  });

  test('builds corpora for traces with input-origin variables (T02)', () => {
    const raw = JSON.parse(readFileSync(resolve(process.cwd(), '../design/world-protocol/v2/traces/T02.json'), 'utf8'));
    expect(() => buildCorpus(raw, 'sample_1', [], [])).not.toThrow();
  });
});

describe('T06 retry/probe declarations and error-step consumption', () => {
  const rawT06 = () => JSON.parse(readFileSync(resolve(process.cwd(), '../design/world-protocol/v2/traces/T06.json'), 'utf8'));

  test('refuses to infer a recorded requestId reuse at build time', () => {
    // T06 s5 deliberately replays s4's id with a different payload — that
    // reuse is a declaration, never an inference.
    expect(() => buildCorpus(rawT06(), 'sample_1', [], [])).toThrow(/must be declared explicitly/);
  });

  test('accepts a declared probe and rejects declaring it a retry', () => {
    expect(() => buildCorpus(rawT06(), 'sample_1', [], [], [], [], [{ stepId: 's5', kind: 'probe' }])).not.toThrow();
    expect(() => buildCorpus(rawT06(), 'sample_1', [], [], [], [], [{ stepId: 's5', kind: 'continue' }])).toThrow(/declared retry diverges/);
  });

  test('a declared retry must repeat the original operation, scope and body', async () => {
    const corpus = buildCorpus(rawT06(), 'sample_1', [], [], [], [], [{ stepId: 's5', kind: 'probe' }]);
    const s4 = corpus.steps.find((s) => s.sharedStepId === 's4')!;
    const s5 = corpus.steps.find((s) => s.sharedStepId === 's5')!;
    const recordedId = (rawT06().steps as { id: string; request: { requestId: string } }[]).find((s) => s.id === 's4')!.request.requestId;
    // Reshape s5 into what a true retry looks like: the predecessor's body.
    s5.requestIdExpectation = 'continue';
    s5.request = structuredClone(s4.request);
    const tail = corpus.steps.findIndex((s) => s.sharedStepId === 's4');
    const tailSteps = corpus.steps.slice(tail);
    for (const step of tailSteps) step.digestChain = []; // chain integrity needs the unserved prefix; covered corpus-level
    const transport = new ScenarioTransport(tailSteps, 'T06');
    const serve = (step: typeof s4) => transport.execute(step.operation, { ...(step.request as Record<string, unknown>), requestId: recordedId } as never, step.scope as never);
    await serve(s4); // original call under a fresh id
    (s5.request as Record<string, unknown>).expectedCheckpointRevision = 99; // drifted resend
    await expect(serve(s5)).rejects.toThrow(/retry payload drift/);
    (s5.request as Record<string, unknown>).expectedCheckpointRevision = (s4.request as Record<string, unknown>).expectedCheckpointRevision;
    await expect(serve(s5)).rejects.toThrow(); // identity accepted: the recorded error is served
    expect(transport.consumed).toBe(2); // the error step was consumed linearly
    expect(transport.ops).toEqual(['checkpoint_pause', 'checkpoint_pause']);
  });
});
