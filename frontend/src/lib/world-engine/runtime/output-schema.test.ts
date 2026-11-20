import Ajv from 'ajv';
import { describe, expect, test } from 'vitest';
import { taskOutputSchema } from './output-schema';
import { decodeTaskOutput } from './structured-output';
import { B3_SHORT_SAMPLES, SHORT_STATE, judgeShortSample } from './b3-short-samples';
import { buildTaskPrompt } from './prompts';

const ajv = new Ajv({ strict: false, allowUnionTypes: true });

describe('B3 constrained generation and independent fact probes', () => {
  test('action grammar keeps skip and act disjoint; rejects a drifting field', () => {
    const valid = ajv.compile(taskOutputSchema('action', {}) as object);
    expect(valid({ kind: 'skip' })).toBe(true);
    expect(valid({ kind: 'skip', text: '开盒' })).toBe(false);
    expect(valid({ kind: 'act', text: '周宁试着打开盒盖。' })).toBe(true);
    expect(valid({ kind: 'act', text: '' })).toBe(false);
    expect(valid({ kind: 'act', actorId: 'person_c' })).toBe(false);
  });

  test('split updates bind stage, entity roster and delta fields; accepted example reaches codec', () => {
    const sample = B3_SHORT_SAMPLES.find((sample) => sample.id === 'updates-position')!;
    const valid = ajv.compile(taskOutputSchema('updates', sample.input) as object);
    const good = { stage: 'position', changes: { person_a: { positionSet: { containerId: 'hall', slotId: null, relativeTo: null } } } };
    expect(valid(good)).toBe(true);
    expect(decodeTaskOutput('updates', JSON.stringify(good), { updatesSplitMode: true, updatesStage: 'position' })).toEqual(good);
    expect(valid({ stage: 'sanity', changes: {} })).toBe(false);
    expect(valid({ stage: 'position', changes: { invented_actor: good.changes.person_a } })).toBe(false);
    expect(valid({ stage: 'position', changes: { person_a: { sanitySet: 8 } } })).toBe(false);
    expect(valid([good])).toBe(false);
    expect(() => decodeTaskOutput('updates', '{"stage":"sanity","changes":{}}', { updatesSplitMode: true, updatesStage: 'position' })).toThrow(/stage differs/);
  });

  test('batch stays an array and prose receives no grammar', () => {
    const valid = ajv.compile(taskOutputSchema('updates', { workingState: {} }) as object);
    expect(valid([{ stage: 'sanity', changes: { person_a: { sanitySet: 8 } } }])).toBe(true);
    expect(valid({ stage: 'sanity', changes: {} })).toBe(false);
    expect(taskOutputSchema('narration', {})).toBeUndefined();
    expect(taskOutputSchema('reaction', {})).toBeUndefined();
  });

  test('fact checks reject actor substitution, wrong numeric updates and unsupported narration', () => {
    expect(judgeShortSample('action-npc', { kind: 'act', text: '周宁打开盒盖。' })).toMatch(/归属/);
    expect(judgeShortSample('action-npc', { kind: 'skip' })).toBeNull();
    expect(judgeShortSample('action-player', { kind: 'act', text: '周宁试着打开盒盖。' })).toBeNull();
    expect(judgeShortSample('updates-sanity', { stage: 'sanity', changes: { person_a: { sanitySet: 2 } } })).toMatch(/应设为8/);
    expect(judgeShortSample('narration-root', '周宁从盒子中拿出了钥匙。')).toMatch(/未提交/);
    // The sample input is a Json fixture; read the moved entity's position
    // through the fixture's own type so the probe stays refactor-checked.
    type SampleState = typeof SHORT_STATE;
    const moved = B3_SHORT_SAMPLES.find((sample) => sample.id === 'narration-move')!.input as unknown as {
      before: SampleState; after: SampleState;
      delta: { entityDeltas: { person_a: { positionSet: SampleState['characters']['person_a']['position'] } } };
    };
    expect(moved.before.characters.person_a.position.containerId).toBe('corridor');
    expect(moved.after.characters.person_a.position.containerId).toBe('hall');
    expect(moved.delta.entityDeltas.person_a.positionSet).toEqual(moved.after.characters.person_a.position);
  });

  test('prose reasoning leaks and prose-wrapped JSON refuse; no silent stripping of a paid answer', () => {
    expect(() => decodeTaskOutput('narration', '<think>猜测</think>走廊很安静。')).toThrow(/markup/);
    expect(() => decodeTaskOutput('action', '```json\n{"kind":"skip"}\n```\n再说两句')).toThrow(/valid JSON/);
    expect(decodeTaskOutput('action', '```json\n{"kind":"skip"}\n```')).toEqual({ kind: 'skip' });
    const npc = B3_SHORT_SAMPLES[0];
    const player = B3_SHORT_SAMPLES[1];
    expect(buildTaskPrompt(npc.task, npc.key, npc.input)).toContain('本角色不是主角');
    expect(buildTaskPrompt(player.task, player.key, player.input)).toContain('本角色就是主角');
  });
});
