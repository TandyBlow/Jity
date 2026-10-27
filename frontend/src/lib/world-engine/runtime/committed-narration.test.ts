import { describe, expect, test } from 'vitest';
import { SHORT_STATE } from './b3-short-samples';
import { checkFactNarration, projectCommittedNarration, renderCommittedNarration, selectFactNarration, type CommittedRead } from './committed-narration';
import type { WorldState } from '../types';
import { projectTaskInput } from './focused-input';
import { buildTaskPrompt } from './prompts';

function reads() {
  const before: CommittedRead = { pointId: 'root', previousPointId: null, version: 0, stateDigest: 'root_digest',
    state: structuredClone(SHORT_STATE) as unknown as WorldState, timeAdvance: null, entityDeltas: {} };
  const after = structuredClone(before);
  Object.assign(after, { pointId: 'point_1', previousPointId: 'root', version: 1, stateDigest: 'point_digest',
    timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'second' } },
    entityDeltas: { person_c: { entityId: 'person_c', positionSet: { containerId: 'hall', slotId: null, relativeTo: null } } } });
  after.state.characters.person_c.position.containerId = 'hall';
  after.state.time = { ...after.state.time, dateTime: '2026-10-27T09:00:01' };
  return { before, after };
}

describe('saved facts, template baseline and bounded polish', () => {
  test('templates attribute movement, unchanged actors and numbers to the saved records', () => {
    const { before, after } = reads();
    const packet = projectCommittedNarration(after, before);
    expect(packet.anchor).toEqual({ worldId: 'world_short', pointId: 'point_1', version: 1, stateDigest: 'point_digest', previousPointId: 'root' });
    expect(renderCommittedNarration(packet)).toBe('林川位于走廊。林川的精神值为10。周宁从走廊走到门厅。周宁的精神值为10。');
    expect(checkFactNarration(packet, renderCommittedNarration(packet))).toEqual({ ok: true, reason: null });
    expect(projectCommittedNarration(before, null).facts).toHaveLength(4);
  });

  test('missing lineage, inconsistent delta and unrecorded changes stop projection', () => {
    const { before, after } = reads();
    expect(() => projectCommittedNarration(after, null)).toThrow(/lineage/);
    const movedWrongActor = structuredClone(after); movedWrongActor.state.characters.person_a.position.containerId = 'hall';
    expect(() => projectCommittedNarration(movedWrongActor, before)).toThrow(/unrecorded_position/);
    const wrongValue = structuredClone(after); wrongValue.state.characters.person_c.position.containerId = 'corridor';
    expect(() => projectCommittedNarration(wrongValue, before)).toThrow(/position_delta_disagrees/);
    const unsupported = structuredClone(after); unsupported.entityDeltas.person_c.appearanceChanges = [{ id: 'c', text: '受伤', supersedes: [] }];
    expect(() => projectCommittedNarration(unsupported, before)).toThrow(/unsupported_committed_delta/);
  });

  test('numeric facts require the saved task and allocated personality cause', () => {
    const { before, after } = reads();
    const task = { id: 'task_pressure', ownerId: 'person_c', parentTaskId: null, goal: '完成压力试验', status: 'pending' as const };
    before.state.initial.characters.person_c.tasks.task_pressure = task;
    before.state.characters.person_c.tasks.task_pressure = { ...task };
    after.state = structuredClone(before.state);
    after.state.characters.person_c.sanity = 8;
    after.state.characters.person_c.tasks.task_pressure.status = 'achieved';
    const change = { id: 'allocated_change_1', text: '经历压力试验后更谨慎', supersedes: [] };
    after.state.characters.person_c.personalityChanges = [{ ...change, sourcePointId: 'point_1', sourceSequence: 1, active: true }];
    after.entityDeltas = { person_c: { entityId: 'person_c', tasksAchieved: ['task_pressure'], personalityChanges: [change], sanitySet: 8 } };
    const packet = projectCommittedNarration(after, before);
    expect(renderCommittedNarration(packet)).toContain('周宁的精神值从10变为8。周宁完成了任务「完成压力试验」。周宁的人格变化为「经历压力试验后更谨慎」。');
    const missingTask = structuredClone(after); delete missingTask.entityDeltas.person_c.tasksAchieved;
    expect(() => projectCommittedNarration(missingTask, before)).toThrow(/complete_numeric_cause/);
    const forgedCause = structuredClone(after); forgedCause.state.characters.person_c.personalityChanges[0].sourcePointId = 'other_point';
    expect(() => projectCommittedNarration(forgedCause, before)).toThrow(/personality_cause/);
  });

  test('wrong actors, locations, numbers, extra events, omissions and repeats fall back', () => {
    const { before, after } = reads(); const packet = projectCommittedNarration(after, before);
    const baseline = renderCommittedNarration(packet);
    for (const candidate of [baseline.replace('周宁从走廊', '林川从走廊'), baseline.replace('到门厅', '到教室'),
      baseline.replace('为10', '为8'), `${baseline}周宁拿到了钥匙。`, baseline.split('。').slice(1).join('。'), `${baseline}林川位于走廊。`]) {
      expect(checkFactNarration(packet, candidate).ok).toBe(false);
      expect(selectFactNarration(packet, candidate)).toMatchObject({ accepted: false, text: baseline });
    }
    expect(checkFactNarration(packet, baseline.replace('周宁从走廊走到门厅', '周宁从走廊来到门厅')).ok).toBe(true);
  });

  test('focused action preserves identity/current facts and removes unrelated task duplication', () => {
    const { before } = reads();
    const input = { actor: 'person_c', advance: { inputText: '走到门厅', intentStatus: 'pending' }, workingState: before.state };
    const prompt = buildTaskPrompt('action', 'person_c', input as any, { inputMode: 'focused' });
    expect(prompt).toContain('本角色就是主角');
    expect(prompt).not.toContain('本角色不是主角');
    expect(prompt).toContain('周宁');
    expect(prompt).toContain('person_a');
    expect(prompt).not.toContain('task_watch');
    expect(prompt.length).toBeLessThan(buildTaskPrompt('action', 'person_c', input as any).length);
  });

  test('focused narration binds original input to saved records without duplicating them into the full arm', () => {
    const { before, after } = reads();
    const input = { pointId: after.pointId, before: before.state, after: after.state,
      delta: { timeAdvance: after.timeAdvance, entityDeltas: after.entityDeltas }, perspective: '周宁视角' } as any;
    expect(projectTaskInput('narration', input)).toBe(input);
    const focused = projectTaskInput('narration', input, { before, after }) as any;
    expect(focused.facts).toHaveLength(4);
    expect(focused.before).toBeUndefined(); expect(focused.after).toBeUndefined();
    expect(JSON.stringify(focused)).not.toContain('initialPersonality');
    const changed = { ...input, pointId: 'other' };
    expect(() => projectTaskInput('narration', changed, { before, after })).toThrow(/read_binding/);
  });
});
