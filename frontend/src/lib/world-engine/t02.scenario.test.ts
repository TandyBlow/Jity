/** T02 group-expansion and empty-linked-time-scan acceptance: the real
 * ControllerDriver runs both declared corpora for both samples; the
 * bootstrap get_context and the final get_state are harness-issued inspects
 * held to the shared independent expectations; directed negatives prove the
 * harness rejects tampered final digests and tampered preview specimen
 * bodies. */
import { describe, expect, test } from 'vitest';
import { assertSharedExpectation, driveControllerSegment } from './harness';
import { buildT02Scenario, type T02TraceName } from './t02.scenario';
import type { Json } from './types';

const EXPECTED_PREVIEW_TIMES: Record<T02TraceName, { dateTime: string; instantOrdinal: number }[]> = {
  'T02': [
    { dateTime: '2026-01-01T11:59:02', instantOrdinal: 0 },
    { dateTime: '2026-01-01T11:59:02', instantOrdinal: 1 },
    { dateTime: '2026-01-01T11:59:05', instantOrdinal: 0 },
  ],
  'T02-empty-linked': [
    { dateTime: '2026-01-01T11:59:02', instantOrdinal: 1 },
    { dateTime: '2026-01-01T11:59:02', instantOrdinal: 2 },
  ],
};

/** §6.1：行动输入的消费状态随调用时刻的最近服务态变化——T02 的点 1 两组在
 * commit 前（pending），commit 后的点 2/3 已消费；空链开在已消费之后。文本
 * 始终是最后一次 context 回包的玩家输入。 */
const EXPECTED_ACTION_ADVANCE: Record<T02TraceName, { intentStatus: string; inputText: string }[]> = {
  'T02': [
    { intentStatus: 'pending', inputText: '我推开重门。' },
    { intentStatus: 'pending', inputText: '我推开重门。' },
    { intentStatus: 'consumed', inputText: '我推开重门。' },
    { intentStatus: 'consumed', inputText: '我推开重门。' },
  ],
  'T02-empty-linked': [{ intentStatus: 'consumed', inputText: '我推开重门。' }],
};

/** §7.1：results 输入的全组冻结行动顺序——发起者先入，被准入者逐个前插。
 * results 调用按录制中的 stage_unit 顺序排列。 */
const EXPECTED_RESULT_MEMBERS: Record<T02TraceName, string[][]> = {
  'T02': [['person_a'], ['person_b'], ['person_d', 'person_c'], ['person_f', 'person_e']],
  'T02-empty-linked': [['person_f', 'person_e', 'person_d', 'person_c']],
};

async function runT02Acceptance(traceName: T02TraceName, sampleId: string) {
  const scenario = buildT02Scenario(traceName, sampleId);
  await scenario.transport.runInspect(scenario.bootstrapStepId); // session-open get_context
  await driveControllerSegment(scenario, traceName);
  const { step, response } = await scenario.transport.runInspect(scenario.finalStepId);
  assertSharedExpectation(step, response);
  // Declared stop boundary: the round's points are exhausted, the driver
  // wants the continuation model call and the harness ends without it.
  expect(scenario.driver.pendingDecision()).toMatchObject({ kind: 'model', task: 'continuation', key: scenario.roundId });
  scenario.transport.assertConsumed();
  scenario.model.assertConsumed();
  return scenario;
}

describe.each([
  ['T02', 'sample_1'],
  ['T02', 'sample_2'],
  ['T02-empty-linked', 'sample_1'],
  ['T02-empty-linked', 'sample_2'],
] as [T02TraceName, string][])('%s %s: controller segment, previews, inspect, stop boundary', (traceName, sampleId) => {
  test('opens on the recorded context, drives both points/rolls, ends at the continuation boundary', async () => {
    const scenario = await runT02Acceptance(traceName, sampleId);

    // No create_world/allocate/start_advance exists: the session opens with
    // the bootstrap get_context and its first controller op is a begin.
    expect(scenario.transport.ops).not.toContain('create_world');
    expect(scenario.transport.ops[0]).toBe('get_context');
    expect(scenario.transport.ops[1]).toBe('checkpoint_begin_point');
    expect(scenario.transport.ops.at(-1)).toBe('get_state');

    // Preview specimens: one after every begin/stage anchor, placeholder
    // digests, real bodies — the point's staged successor time over the
    // recorded final state, the recorded commit point as projection.
    const previews = scenario.corpus.steps.filter((s) => s.segment === 'preview');
    expect(previews).toHaveLength(traceName === 'T02' ? 7 : 4); // begins + stage anchors
    expect(previews.every((s) => s.placeholderDigests === true)).toBe(true);
    const times = EXPECTED_PREVIEW_TIMES[traceName];
    const finalState = (scenario.corpus.steps.find((s) => s.sharedStepId === scenario.finalStepId)!.response as { data: { state: Json } }).data.state;
    for (const preview of previews) {
      const working = (preview.response as { data: { workingState: { time: { dateTime: string; instantOrdinal: number } } } }).data.workingState;
      expect(times.some((t) => t.dateTime === working.time.dateTime && t.instantOrdinal === working.time.instantOrdinal)).toBe(true);
      const body = { ...(structuredClone(finalState) as Record<string, unknown>), time: working.time };
      expect(working).toEqual(body);
    }
    // The last preview is the one aligned to the final independent state.
    const lastPreview = previews.at(-1)!;
    expect(lastPreview.id).toBe(scenario.corpus.steps.find((s) => s.sharedStepId === scenario.finalStepId)!.expectation!.alignsWith!.previewStepId);

    // Model calls: generated from the recording, matched by the driver.
    const calls = scenario.model.calls.map((c) => `${c.task}:${c.key}`);
    expect(calls[0]).toBe(`pointPlan:${scenario.roundId}`);
    expect(calls.at(-1)).toMatch(/^narration:/);

    // §6.1：每次行动调用的 advance＝调用时刻的消费状态＋最后的 context 文本。
    const actions = scenario.model.calls.filter((c) => c.task === 'action').map((c) => (c.input as { advance: { intentStatus: string; inputText: string } }).advance);
    expect(actions).toEqual(EXPECTED_ACTION_ADVANCE[traceName]);

    // §7.1：results 携带本组冻结行动（跨组不混）与全部骰点判定（含未准入）。
    const results = scenario.model.calls.filter((c) => c.task === 'results').map((c) => c.input as { members: { memberId: string; actionText: string; rollRefs: { targetId: string; result: number; eligible: boolean; admitted: boolean }[] }[] });
    expect(results.map((call) => call.members.map((member) => member.memberId))).toEqual(EXPECTED_RESULT_MEMBERS[traceName]);
    expect(results.flatMap((call) => call.members).every((member) => member.actionText.length > 0)).toBe(true);
    const rollFacts = results.map((call) => call.members.map((member) => member.rollRefs.map(({ targetId, result, eligible, admitted }) => ({ targetId, result, eligible, admitted }))));
    if (traceName === 'T02') {
      // 发起者的两个判定：未准入且不合格 / 准入；被牵连者准入后的判定：
      // 合格但未准入（仍入列）。
      expect(rollFacts[2]).toEqual([
        [{ targetId: 'person_e', result: 5, eligible: true, admitted: false }],
        [
          { targetId: 'person_a', result: 17, eligible: false, admitted: false },
          { targetId: 'person_d', result: 15, eligible: true, admitted: true },
        ],
      ]);
      expect(rollFacts[3]).toEqual([
        [],
        [
          { targetId: 'person_c', result: 17, eligible: false, admitted: false },
          { targetId: 'person_f', result: 15, eligible: true, admitted: true },
        ],
      ]);
    } else {
      expect(rollFacts[0].at(-1)).toEqual([
        { targetId: 'person_d', result: 15, eligible: true, admitted: true },
        { targetId: 'person_e', result: 15, eligible: true, admitted: true },
        { targetId: 'person_f', result: 15, eligible: true, admitted: true },
      ]);
      expect(rollFacts[0].slice(0, -1).every((rolls) => rolls.length === 0)).toBe(true);
    }
    expect(calls.filter((c) => c.startsWith('action:')).length).toBeGreaterThan(0);
  });
});

describe('T02 harness directed negatives', () => {
  test('rejects a tampered final digest at the inspect read', async () => {
    const scenario = buildT02Scenario('T02', 'sample_1');
    const finalStep = scenario.corpus.steps.find((s) => s.sharedStepId === scenario.finalStepId)!;
    finalStep.expectation!.expectedDigest = 'f'.repeat(64);
    await scenario.transport.runInspect(scenario.bootstrapStepId);
    await driveControllerSegment(scenario, 'T02');
    await expect(scenario.transport.runInspect(scenario.finalStepId)).rejects.toThrow(/shared digest mismatch/);
  });

  test('rejects a tampered preview specimen body via the final alignment', async () => {
    const scenario = buildT02Scenario('T02-empty-linked', 'sample_1');
    const previews = scenario.corpus.steps.filter((s) => s.segment === 'preview');
    const lastPreview = previews.at(-1)!;
    (((lastPreview.response as { data: { workingState: { characters: Record<string, { sanity: number }> } } }).data.workingState).characters).person_c.sanity = 99;
    await scenario.transport.runInspect(scenario.bootstrapStepId);
    await driveControllerSegment(scenario, 'T02-empty-linked');
    await expect(scenario.transport.runInspect(scenario.finalStepId)).rejects.toThrow(/preview alignment broken/);
  });
});
