/** T01 fixed-response controller acceptance: the real ControllerDriver runs
 * the declared corpus for both shared samples; inspect reads verify the
 * shared independent expectations; directed negatives prove the harness
 * rejects request/scope/model mismatches, undeclared previews and tampered
 * shared digests. */
import { describe, expect, test } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { assertSharedExpectation } from './harness';
import { buildT01Scenario, driveControllerSegment } from './t01.scenario';

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
      'create_world', 'narration_claim', 'narration_submit', 'allocate_ids', 'checkpoint_start_advance',
      'checkpoint_begin_point', 'preview_point', 'checkpoint_discover_group', 'checkpoint_extend_group',
      'checkpoint_close_group', 'checkpoint_stage_unit',
      ...Array.from({ length: 5 }, () => 'checkpoint_record_skip' as const),
      'preview_point', 'checkpoint_seal_point', 'commit_point', 'narration_claim', 'narration_submit',
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

test('DBG corpus s21 instantiation', () => {
  const scenario = buildT01Scenario('sample_1');
  const s21 = scenario.corpus.steps.find((s) => s.id === 's21')!;
  console.log('DBG s21 response:', JSON.stringify(s21.response).slice(0, 200));
  console.log('DBG s21 expectation:', JSON.stringify(s21.expectation)?.slice(0, 200));
  const s1 = scenario.corpus.steps.find((s) => s.id === 's1')!;
  console.log('DBG s1 response len:', JSON.stringify(s1.response).length);
  const s5 = scenario.corpus.steps.find((s) => s.id === 's5')!;
  console.log('DBG s5 response world.head:', JSON.stringify((s5.response as { world: { head: unknown } }).world.head).slice(0, 150));
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
    const { step, response } = await scenario.transport.runInspect('s21');
    expect(() => assertSharedExpectation(step, response)).toThrow(/shared digest mismatch/);
  });
});
