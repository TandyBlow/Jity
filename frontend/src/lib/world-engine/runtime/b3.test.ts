import { describe, expect, test } from 'vitest';
import { buildTaskPrompt } from './prompts';
import { B3_SAMPLES, T01_WORKING_STATE } from './b3-samples';
import { runB3Evaluation, formatB3Summary, type B3Judge } from './b3-eval';
import type { InferenceEngine } from './engine';
import { WllamaInferenceEngine } from './wllama-engine';
import type { Wllama } from '@wllama/wllama';
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

  test('§6.1/§6.2/§7.1 inputs reach the prompt verbatim, not only as contract wording', () => {
    const action = buildTaskPrompt('action', 'person_a', { actor: 'person_a', advance: { inputText: '去走廊尽头看看那扇门', intentStatus: 'pending' }, workingState: T01_WORKING_STATE });
    expect(action).toContain('"inputText":"去走廊尽头看看那扇门"');
    expect(action).toContain('"intentStatus":"pending"');
    // 行动是对「输入 actor 指定的人物」的判断，不是固定写主角；pending 输入需
    // 结合最新状态判断能否执行（可能已失效）。
    expect(action).toContain('输入 actor 指定的角色');
    expect(action).toContain('不一定是主角');
    expect(action).toContain('结合最新工作状态判断能否执行');
    const reaction = buildTaskPrompt('reaction', 'person_a', { sourceId: 'person_a', sourceActionText: '用力推开走廊尽头的门', memberId: 'person_b', rollId: 'roll_1', workingState: T01_WORKING_STATE });
    expect(reaction).toContain('"sourceActionText":"用力推开走廊尽头的门"');
    const results = buildTaskPrompt('results', 'group_a', {
      groupId: 'group_a', workingState: T01_WORKING_STATE,
      members: [{ memberId: 'person_a', actionText: '用力推开走廊尽头的门', rollRefs: [{ targetId: 'person_b', rollId: 'roll_1', result: 3, eligible: false, admitted: false }] }],
    });
    expect(results).toContain('"actionText":"用力推开走廊尽头的门"');
    expect(results).toContain('"eligible":false');
    // §7.1：更新读已确认结果——输入与契约都体现，时间扫描（无 results）不提。
    const updates = buildTaskPrompt('updates', 'group_a', { groupId: 'group_a', mode: 'group', results: { person_a: '结果已确认。' }, workingState: T01_WORKING_STATE });
    expect(updates).toContain('"results":{"person_a":"结果已确认。"}');
    expect(updates).toContain('results 是已确认的结算结果');
    const scan = buildTaskPrompt('updates', 'time_scan:p1', { mode: 'time_scan', workingState: T01_WORKING_STATE });
    expect(scan).not.toContain('results 是已确认的结算结果');
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
    const batch = buildTaskPrompt('updates', 'group_a', { groupId: 'group_a', mode: 'group', workingState: T01_WORKING_STATE, priorStages: [], appliedDelta: {} });
    const split = buildTaskPrompt('updates', 'group_a#sanity', { groupId: 'group_a', mode: 'group', workingState: T01_WORKING_STATE, priorStages: [], appliedDelta: {}, stage: 'sanity' });
    expect(batch).toContain('只输出 JSON 数组');
    expect(batch).not.toContain('不要数组'); // the batch contract never mentions the single-object shape
    expect(split).toContain('不要数组');
    expect(split).toContain('只输出一个 JSON 对象');
    expect(split).not.toContain('只输出 JSON 数组'); // mutually exclusive contracts
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

/** An engine whose load always fails: real device work = zero completions. */
function brokenLoadEngine(): InferenceEngine {
  return {
    info: { backend: 'fake', modelId: 'fake.gguf' },
    load: () => Promise.reject(new Error('model asset missing')),
    complete: async () => '',
    dispose: async () => {},
  };
}

/** A controllable engine so a test can slow individual completions. */
function timedEngine(outputs: string[], delays: number[]): InferenceEngine {
  let started = 0;
  return {
    info: { backend: 'fake', modelId: 'fake.gguf' },
    load: async () => {},
    complete: async () => {
      const index = started++;
      const delay = delays[index] ?? 0;
      if (delay > 0) await new Promise((resolve) => setTimeout(resolve, delay));
      return outputs.shift() ?? '';
    },
    dispose: async () => {},
  };
}

/** Valid outputs aligned with B3_SAMPLES order (see the corpus for ids). */
function validOutputsFor(samples: typeof B3_SAMPLES): string[] {
  return samples.map((sample) => {
    switch (sample.task) {
      case 'action': return '{"kind":"act","text":"用力推门"}';
      case 'targets': return '{"targets":[{"targetId":"person_b"}]}';
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
    expect(report.results.every((row) => row.failure === null && row.timing !== null)).toBe(true);
    expect(formatB3Summary(report)).toContain('结构 20/20');
  });

  test('failure stages are separated; structural rejections keep their generation cost in the timing average', async () => {
    const outputs = validOutputsFor(B3_SAMPLES);
    outputs[0] = 'not json at all'; // action-1 → structure failure (engine ran)
    outputs[17] = '   '; // narration-2: empty after trim → structure failure
    outputs[4] = '{"person_a":42}'; // results-1: wrong value type → structure failure
    const delays = B3_SAMPLES.map((_s, index) => (index === 0 ? 90 : 10)); // the malformed output is the EXPENSIVE one
    const report = await runB3Evaluation(timedEngine(outputs, delays), B3_SAMPLES);
    const structural = report.results.filter((row) => row.failure === 'structure');
    expect(structural.map((row) => row.id).sort()).toEqual(['action-1', 'narration-2', 'results-1']);
    for (const row of structural) {
      expect(row.structureError).toBeTruthy();
      expect(row.timing).not.toBeNull(); // the generation happened
    }
    const actionRow = report.perTask.find((row) => row.task === 'action')!;
    expect(actionRow.structureOk).toBe(1);
    expect(actionRow.samples).toBe(2);
    expect(actionRow.calls).toBe(2); // both completions actually ran
    // The 90ms structural rejection IS in the average: (90 + 10) / 2.
    expect(actionRow.avgRunMs).toBeGreaterThanOrEqual(45);
    expect(report.totals.structureOk).toBe(B3_SAMPLES.length - 3);
    expect(report.totals.calls).toBe(B3_SAMPLES.length); // every sample made its engine call
  });

  test('an engine whose load fails records the engine stage with zero calls', async () => {
    const report = await runB3Evaluation(brokenLoadEngine(), B3_SAMPLES.slice(0, 3));
    expect(report.results.map((row) => row.failure)).toEqual(['engine', 'engine', 'engine']);
    expect(report.totals.calls).toBe(0); // no completion was ever started
    expect(report.totals.structureOk).toBe(0);
    const row = report.perTask[0]!;
    expect(row.avgRunMs).toBe(0); // no generation cost to average
  });

  test('a structural pass can still fail the semantic floor; judges are pluggable', async () => {
    const outputs = validOutputsFor(B3_SAMPLES);
    outputs[2] = '{"targets":[{"targetId":"person_z"}]}'; // targets-1: unknown target id
    const report = await runB3Evaluation(scriptedEngine(outputs), B3_SAMPLES);
    const row = report.results.find((result) => result.id === 'targets-1')!;
    expect(row.failure).toBe('semantic'); // the codec accepts the shape
    expect(row.timing).not.toBeNull();
    expect(row.semanticNote).toMatch(/不在场: person_z/);

    const custom: Record<string, B3Judge> = { action: () => 'custom judge says no' };
    const outputs2 = validOutputsFor(B3_SAMPLES);
    const overridden = await runB3Evaluation(scriptedEngine(outputs2), B3_SAMPLES, { judges: custom });
    expect(overridden.results.filter((result) => result.task === 'action').every((result) => result.failure === 'semantic')).toBe(true);
  });

  test('a crashing judge is its own stage: structure and timing stand, only the verdict is missing', async () => {
    const outputs = validOutputsFor(B3_SAMPLES); // both target samples are structurally valid
    const custom: Record<string, B3Judge> = { targets: () => { throw new Error('judge bug'); } };
    const report = await runB3Evaluation(scriptedEngine(outputs), B3_SAMPLES, { judges: custom });
    const row = report.results.find((result) => result.id === 'targets-1')!;
    expect(row.failure).toBe('judge');
    expect(row.judgeError).toMatch(/judge bug/);
    expect(row.timing).not.toBeNull(); // the generation cost stands
    const targetsRow = report.perTask.find((entry) => entry.task === 'targets')!;
    expect(targetsRow.structureOk).toBe(2); // the codec verdict is NOT overturned
    expect(targetsRow.semanticFloorOk).toBe(0); // both verdicts are missing — judge crashed, not failed
  });

  test('targets are judged against the CHARACTER roster: a location target fails the floor', async () => {
    const outputs = validOutputsFor(B3_SAMPLES);
    outputs[2] = '{"targets":[{"targetId":"corridor"}]}'; // targets-1: a LOCATION
    const report = await runB3Evaluation(scriptedEngine(outputs), B3_SAMPLES);
    const row = report.results.find((result) => result.id === 'targets-1')!;
    expect(row.failure).toBe('semantic'); // the codec accepts the shape…
    expect(row.semanticNote).toMatch(/不在场: corridor/); // …but corridor is not a character
  });


  test('composition: the REAL wllama adapter works through the counting wrapper (fake wasm)', async () => {
    const createCalls: Array<Record<string, unknown>> = [];
    let exits = 0;
    let wasmCompletions = 0;
    const fakeWllama = {
      loadModelFromUrl: async () => {},
      createCompletion: async (options: Record<string, unknown>) => {
        wasmCompletions += 1;
        createCalls.push(options);
        // Sample order: answer each task with something structurally valid
        // enough to pass or fail the codec — the harness must count it.
        return { choices: [{ text: '走廊尽头的门吱呀一声开了。' }] };
      },
      exit: async () => {
        exits += 1;
      },
    } as unknown as Wllama;
    const engine = new WllamaInferenceEngine({ modelUrl: '/models/m.gguf' }, async () => fakeWllama);
    // Three text-task samples: prose decodes without any JSON contract.
    const samples = B3_SAMPLES.filter((sample) => sample.task === 'narration');
    const report = await runB3Evaluation(engine, samples);
    expect(wasmCompletions).toBe(samples.length); // the REAL adapter's completions happened
    expect(report.totals.calls).toBe(samples.length); // the wrapper counted them through prototype methods intact
    expect(report.results.every((row) => row.timing !== null)).toBe(true);
    expect(report.results.every((row) => row.failure === null)).toBe(true); // prose decodes cleanly
    expect(createCalls.every((call) => typeof call.prompt === 'string' && (call.prompt as string).includes('正文:'))).toBe(true);
    expect(exits).toBe(0); // the harness never disposes the engine
  });

  test('fenced JSON from the engine passes through the real decode path', async () => {
    const outputs = validOutputsFor(B3_SAMPLES);
    outputs[0] = '```json\n{"kind":"skip"}\n```'; // action-1 fenced
    const report = await runB3Evaluation(scriptedEngine(outputs), B3_SAMPLES);
    expect(report.results.find((result) => result.id === 'action-1')!.failure).toBeNull();
  });
});
