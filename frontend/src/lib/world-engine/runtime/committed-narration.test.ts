import { describe, expect, test } from 'vitest';
import { SHORT_STATE } from './b3-short-samples';
import { checkFactNarration, projectCommittedNarration, renderCommittedNarration, selectFactNarration,
  type CommittedNarration, type CommittedRead } from './committed-narration';
import type { Json, WorldState } from '../types';
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
    // 事实顺序按六阶段：任务（阶段 3）→ 个性（阶段 5）→ 理智（阶段 6）。
    expect(renderCommittedNarration(packet)).toContain('周宁完成了任务「完成压力试验」。周宁的人格变化为「经历压力试验后更谨慎」。周宁的精神值从10变为8。');
    // 因果链逐级收紧，不再要求三件套同有同无（§6.3）：个性变化必须有本批
    // 任务达成，理智值必须有个性变化；任务达成可以单独成立。
    const taskOnly = structuredClone(after);
    taskOnly.state = structuredClone(before.state);
    taskOnly.state.characters.person_c.tasks.task_pressure.status = 'achieved';
    taskOnly.entityDeltas = { person_c: { entityId: 'person_c', tasksAchieved: ['task_pressure'] } };
    const taskPacket = projectCommittedNarration(taskOnly, before);
    expect(taskPacket.facts.filter((fact) => fact.kind === 'task_achieved')).toHaveLength(1);
    expect(taskPacket.facts.find((fact) => fact.id === 'person_c:sanity')).toMatchObject({ kind: 'sanity', value: 10 });
    expect(renderCommittedNarration(taskPacket)).toContain('周宁完成了任务「完成压力试验」。');
    const personalityWithoutTask = structuredClone(after);
    personalityWithoutTask.state.characters.person_c.tasks.task_pressure.status = 'pending';
    personalityWithoutTask.entityDeltas.person_c = { entityId: 'person_c', personalityChanges: [change], sanitySet: 8 };
    expect(() => projectCommittedNarration(personalityWithoutTask, before)).toThrow(/personality_requires_task/);
    const sanityWithoutPersonality = structuredClone(after);
    sanityWithoutPersonality.entityDeltas.person_c = { entityId: 'person_c', tasksAchieved: ['task_pressure'], sanitySet: 8 };
    expect(() => projectCommittedNarration(sanityWithoutPersonality, before)).toThrow(/sanity_requires_personality/);
    // 个性变化但理智重算后数值不变：Δ 可省略 sanitySet（§5.2 允许同值省略）。
    const personalityWithoutSanity = structuredClone(after);
    delete personalityWithoutSanity.entityDeltas.person_c.sanitySet;
    personalityWithoutSanity.state.characters.person_c.sanity = 10;
    expect(projectCommittedNarration(personalityWithoutSanity, before).facts
      .filter((fact) => fact.kind === 'personality_changed')).toHaveLength(1);
    // 理智值真的变了却不报 delta：仍按未登记变化拒绝。
    const unrecordedSanity = structuredClone(personalityWithoutSanity);
    unrecordedSanity.state.characters.person_c.sanity = 8;
    expect(() => projectCommittedNarration(unrecordedSanity, before)).toThrow(/unrecorded_numeric_change/);
    const forgedCause = structuredClone(after); forgedCause.state.characters.person_c.personalityChanges[0].sourcePointId = 'other_point';
    expect(() => projectCommittedNarration(forgedCause, before)).toThrow(/personality_cause/);
    // §6.3：任何人物的任务达成都可能影响任何人物——A 达成任务、B 个性+理智
    // 是合法批次；个性与理智仍按 B 自己配对。
    const crossEntity = structuredClone(after);
    // 断开 live 状态与 initial 模板的共享引用（SHORT_STATE 里两者同一对象），
    // 否则改 live 任务会被世界变更检查当成 initial 变化。
    crossEntity.state.characters = structuredClone(crossEntity.state.characters);
    crossEntity.state.characters.person_a.tasks.task_watch.status = 'achieved';
    crossEntity.state.characters.person_c.tasks.task_pressure.status = 'pending';
    crossEntity.entityDeltas = {
      person_a: { entityId: 'person_a', tasksAchieved: ['task_watch'] },
      person_c: { entityId: 'person_c', personalityChanges: [change], sanitySet: 8 },
    };
    const crossPacket = projectCommittedNarration(crossEntity, before);
    expect(crossPacket.facts.filter((fact) => fact.kind === 'task_achieved')).toHaveLength(1);
    expect(crossPacket.facts.filter((fact) => fact.kind === 'personality_changed')).toHaveLength(1);
    expect(crossPacket.facts.find((fact) => fact.id === 'person_c:sanity')).toMatchObject({ kind: 'sanity_changed', from: 10, to: 8 });
    // 理智变化必须属于有个性变化的那个人物。
    const mispairedSanity = structuredClone(crossEntity);
    mispairedSanity.state.characters.person_a.sanity = 9;
    mispairedSanity.entityDeltas.person_a = { entityId: 'person_a', tasksAchieved: ['task_watch'], sanitySet: 9 };
    expect(() => projectCommittedNarration(mispairedSanity, before)).toThrow(/sanity_requires_personality/);
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

  // 2026-10-28 复核：模板先述本点时间推进（§5.2 timeAdvance 属于 Δ），空事实点
  // 用「时间 + 没有新的变化」固定句式代替空串——关闭归档记录的两个已知缺口。
  test('the template narrates the elapsed time and fills empty points with a fixed line', () => {
    const { before, after } = reads();
    const packet = projectCommittedNarration(after, before);
    const duration = after.timeAdvance?.duration ?? null;
    const timed = renderCommittedNarration(packet, { time: duration });
    expect(timed.startsWith('约一秒过去了。')).toBe(true);
    expect(timed).toContain('周宁从走廊走到门厅。');
    const empty: CommittedNarration = { anchor: packet.anchor, facts: [] };
    expect(renderCommittedNarration(empty, { time: duration })).toBe('约一秒过去了，没有新的变化。');
    expect(renderCommittedNarration(empty)).toBe('');
    const fallback = selectFactNarration(packet, '周宁拿到了钥匙。', { time: duration });
    expect(fallback.accepted).toBe(false);
    expect(fallback.text).toBe(timed);
  });

  test('focused action preserves identity/current facts and removes unrelated task duplication', () => {
    const { before } = reads();
    const input = { actor: 'person_c', advance: { inputText: '走到门厅', intentStatus: 'pending' }, workingState: before.state };
    const prompt = buildTaskPrompt('action', 'person_c', input as unknown as Json, { inputMode: 'focused' });
    expect(prompt).toContain('本角色就是主角');
    expect(prompt).not.toContain('本角色不是主角');
    expect(prompt).toContain('周宁');
    expect(prompt).toContain('person_a');
    expect(prompt).not.toContain('task_watch');
    expect(prompt.length).toBeLessThan(buildTaskPrompt('action', 'person_c', input as unknown as Json).length);
  });

  test('focused narration binds original input to saved records without duplicating them into the full arm', () => {
    const { before, after } = reads();
    const input = { pointId: after.pointId, before: before.state, after: after.state,
      delta: { timeAdvance: after.timeAdvance, entityDeltas: after.entityDeltas }, perspective: '周宁视角' };
    expect(projectTaskInput('narration', input as unknown as Json)).toBe(input as unknown as Json);
    const focused = projectTaskInput('narration', input as unknown as Json, { before, after }) as {
      facts: Json[]; before?: Json; after?: Json };
    expect(focused.facts).toHaveLength(4);
    expect(focused.before).toBeUndefined(); expect(focused.after).toBeUndefined();
    expect(JSON.stringify(focused)).not.toContain('initialPersonality');
    const changed = { ...input, pointId: 'other' };
    expect(() => projectTaskInput('narration', changed as unknown as Json, { before, after })).toThrow(/read_binding/);
  });
});
