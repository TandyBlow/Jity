import { describe, expect, test } from 'vitest';
import { buildTaskPrompt } from './prompts';
import { B3_SAMPLES, T01_WORKING_STATE } from './b3-samples';
import { runB3Evaluation, formatB3Summary, type B3Judge } from './b3-eval';
import type { InferenceEngine } from './engine';
import type { ModelTask } from '../schedule';
import type { Json } from '../types';

describe('buildTaskPrompt', () => {
  test('JSON tasks teach the exact output contract and carry the serialized input', () => {
    const prompt = buildTaskPrompt('action', 'person_a', { actor: 'person_a', workingState: T01_WORKING_STATE });
    expect(prompt).toContain('[任务: action]');
    expect(prompt).toContain('"kind":"act"');
    expect(prompt).toContain('person_a');
    expect(prompt).toContain('输出:');
    expect(prompt).toContain('在场角色: person_a, person_b, person_c');
  });

  test('text tasks forbid JSON and never show a schema', () => {
    const narration = buildTaskPrompt('narration', 'root_0', { pointId: 'root_0', stateDigest: 'd' });
    expect(narration).toContain('不要 JSON');
    expect(narration).not.toContain('"kind"');
    expect(narration).toContain('正文:');
    const reaction = buildTaskPrompt('reaction', 'person_b', { sourceId: 'person_a', memberId: 'person_b', rollId: 'r', workingState: T01_WORKING_STATE });
    expect(reaction).toContain('不要 JSON');
  });

  test('updates prompts distinguish batch and split modes', () => {
    const batch = buildTaskPrompt('updates', 'group_a', { groupId: 'group_a', mode: 'group', workingState: T01_WORKING_STATE });
    const split = buildTaskPrompt('updates', 'group_a#sanity', { groupId: 'group_a', mode: 'group', workingState: T01_WORKING_STATE, stage: 'sanity' });
    expect(batch).toContain('只输出 JSON 数组');
    expect(batch).not.toContain('单阶段模式');
    expect(split).toContain('单阶段模式');
    expect(split).toContain('本调用阶段: sanity');
  });

  test('deterministic in the declared call', () => {
    expect(buildTaskPrompt('time', 'p1', { point: {} })).toBe(buildTaskPrompt('time', 'p1', { point: {} }));
    expect(buildTaskPrompt('narration', 'a', { pointId: 'a' })).not.toBe(buildTaskPrompt('narration', 'b', { pointId: 'b' }));
  });
});

describe('B3 frozen samples', () => {
  test('ids are unique and every task has at least two samples', () => {
    const ids = B3_SAMPLES.map((sample) => sample.id);
    expect(new Set(ids).size).toBe(ids.length);
    const tasks = new Set(B3_SAMPLES.map((sample) => sample.task));
    const allTasks: ModelTask[] = ['action', 'targets', 'reaction', 'results', 'updates', 'continuation', 'narration', 'initial', 'time', 'pointPlan'];
    for (const task of allTasks) {
      expect(tasks.has(task)).toBe(true);
      expect(B3_SAMPLES.filter((sample) => sample.task === task).length).toBeGreaterThanOrEqual(2);
    }
  });

  test('every sample records provenance and working-state samples carry the frozen T01 world', () => {
    for (const sample of B3_SAMPLES) {
      expect(sample.note).toMatch(/冻结/);
    }
    const action = B3_SAMPLES.find((sample) => sample.id === 'action-1')!;
    expect((action.input as { workingState: { worldId: string } }).workingState.worldId).toBe('world_school');
  });
});

/** Scripted engine keyed by sample order: outputs.pop() per completion. */
function scriptedEngine(outputs: string[]): InferenceEngine {
  return {
    info: { backend: 'fake', modelId: 'fake.gguf' },
    load: async () => {},
    complete: async () => outputs.shift() ?? '',
    dispose: async () => {},
  };
}

/** Valid outputs aligned with B3_SAMPLES order (see the corpus for ids). */
function validOutputsFor(samples: typeof B3_SAMPLES): string[] {
  return samples.map((sample) => {
    switch (sample.task) {
      case 'action': return '{"kind":"act","text":"用力推门"}';
      case 'targets': return '{"targets":[{"targetId":"person_b","triggerKey":"group:person_b","ruleVersion":"reaction-d20-v1","target":11}]}';
      case 'results': return '{"person_a":"门开了"}';
      case 'updates': return (sample.input as { stage?: unknown }).stage !== undefined
        ? '{"stage":"sanity","changes":{"person_a":{"sanitySet":8}}}'
        : '[{"stage":"position","changes":{"person_a":{"positionSet":{"containerId":"corridor","slotId":null,"relativeTo":null}}}}]';
      case 'continuation': return '{"kind":"handback","closedBy":"model","cancelReason":null}';
      case 'initial': return JSON.stringify({ engineVersion: 'world-engine-v1', schemaVersion: 1, protagonistId: 'person_c', initialTime: { calendar: 'gregorian', dateTime: '2026-09-01T08:00:00', instantOrdinal: 0 }, locations: {}, items: {}, characters: {} });
      case 'time': return '{"boundary":"elapsed","duration":{"amount":2,"unit":"second"}}';
      case 'pointPlan': {
        const actor = ((sample.input as { round?: { order?: string[] } }).round?.order ?? ['person_a'])[0];
        return `[{"pointId":"p1","kind":"normal","timeAdvance":{"boundary":"elapsed","duration":{"amount":2,"unit":"second"}},"actorIds":["${actor}"]}]`;
      }
      case 'narration': return '走廊尽头的门吱呀一声开了，灰尘在光柱里浮动。';
      case 'reaction': return 'person_b 被门声惊得回过头。';
      default: throw new Error(`unhandled ${sample.task}`);
    }
  });
}

describe('runB3Evaluation', () => {
  test('all-valid outputs: full structure and semantic-floor rates, timings and calls recorded', async () => {
    const report = await runB3Evaluation(scriptedEngine(validOutputsFor(B3_SAMPLES)), B3_SAMPLES);
    expect(report.totals).toMatchObject({ samples: B3_SAMPLES.length, structureOk: B3_SAMPLES.length, semanticFloorOk: B3_SAMPLES.length, calls: B3_SAMPLES.length });
    for (const row of report.perTask) {
      expect(row.structureRate).toBe(1);
      expect(row.semanticFloorRate).toBe(1);
      expect(row.calls).toBeGreaterThanOrEqual(2);
      expect(row.avgRunMs).toBeGreaterThanOrEqual(0);
    }
    expect(report.results.every((row) => row.timing !== null)).toBe(true);
    expect(formatB3Summary(report)).toContain('结构 20/20');
  });

  test('structure failures are recorded per sample, never thrown; per-task rates reflect them', async () => {
    const outputs = validOutputsFor(B3_SAMPLES);
    outputs[0] = 'not json at all'; // action-1
    outputs[17] = '   '; // narration-2: empty after trim → structure failure
    outputs[4] = '{"person_a":42}'; // results-1: wrong value type
    const report = await runB3Evaluation(scriptedEngine(outputs), B3_SAMPLES);
    const failed = report.results.filter((row) => !row.structured);
    expect(failed.map((row) => row.id).sort()).toEqual(['action-1', 'narration-2', 'results-1']);
    for (const row of failed) {
      expect(row.structureError).toBeTruthy();
      expect(row.timing).toBeNull();
      expect(row.semanticFloor).toBe(false);
    }
    const actionRow = report.perTask.find((row) => row.task === 'action')!;
    expect(actionRow.structureOk).toBe(1);
    expect(actionRow.samples).toBe(2);
    expect(report.totals.structureOk).toBe(B3_SAMPLES.length - 3);
  });

  test('a structural pass can still fail the semantic floor; judges are pluggable', async () => {
    const outputs = validOutputsFor(B3_SAMPLES);
    outputs[2] = '{"targets":[{"targetId":"person_z","triggerKey":"group:person_z","ruleVersion":"reaction-d20-v1","target":11}]}'; // targets-1: unknown target id
    const report = await runB3Evaluation(scriptedEngine(outputs), B3_SAMPLES);
    const row = report.results.find((result) => result.id === 'targets-1')!;
    expect(row.structured).toBe(true); // the codec accepts the shape
    expect(row.semanticFloor).toBe(false);
    expect(row.semanticNote).toMatch(/不在场: person_z/);

    const custom: Record<string, B3Judge> = { action: () => 'custom judge says no' };
    const outputs2 = validOutputsFor(B3_SAMPLES);
    const overridden = await runB3Evaluation(scriptedEngine(outputs2), B3_SAMPLES, { judges: custom });
    expect(overridden.results.filter((result) => result.task === 'action').every((result) => result.semanticFloor === false)).toBe(true);
  });

  test('fenced JSON from the engine passes through the real decode path', async () => {
    const outputs = validOutputsFor(B3_SAMPLES);
    outputs[0] = '```json\n{"kind":"skip"}\n```'; // action-1 fenced
    const report = await runB3Evaluation(scriptedEngine(outputs), B3_SAMPLES);
    expect(report.results.find((result) => result.id === 'action-1')!.structured).toBe(true);
  });
});
