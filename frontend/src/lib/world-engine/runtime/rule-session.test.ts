import { describe, expect, test } from 'vitest';
import { SHORT_STATE } from './b3-short-samples';
import { initialMemory } from '../controller';
import type { WorldState } from '../types';
import type { CommittedRead } from './committed-narration';
import { narrateFromReads, rotateCommandPlan, RuleWorldSession, type RuleNarrationInput, type RuleNarrationPolisher, type RuleSessionEvent } from './rule-session';

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

describe('per-command identity rotation', () => {
  test('a second command mints a fresh allocation plan and clears the finished round ids', () => {
    const memory = initialMemory('rule_t', 'holder_t');
    const order = Object.keys(SHORT_STATE.initial.characters).sort();
    rotateCommandPlan(memory, order, 1, '走到门厅');
    const first = memory.allocPlan!;
    memory.ids.advance = 'advance_1';
    memory.ids.input = 'input_1';
    memory.ids.round = 'round_1';
    memory.ids.point = 'point_1';
    memory.ids['group:person_a'] = 'group_1';
    expect(first.allocationKey).toBe('holder_t_cmd1');
    expect(first.slots.map((slot) => slot.slotKey)).toEqual(['advance', 'input', 'round', 'point', 'group:person_a', 'group:person_c']);
    expect(memory.playerInput).toEqual({ text: '走到门厅', order });

    rotateCommandPlan(memory, order, 2, '完成压力试验');
    const second = memory.allocPlan!;
    expect(second.allocationKey).toBe('holder_t_cmd2');
    expect(second.allocationKey).not.toBe(first.allocationKey);
    expect(memory.ids).not.toHaveProperty('advance');
    expect(memory.ids).not.toHaveProperty('input');
    expect(memory.ids).not.toHaveProperty('round');
    expect(memory.ids).not.toHaveProperty('point');
    expect(memory.ids).not.toHaveProperty('group:person_a');
    expect(memory.playerInput).toEqual({ text: '完成压力试验', order });
  });
});

describe('narration decision: template baseline, bounded polish, fallback', () => {
  test('without a polisher the template is the narration', async () => {
    const { before, after } = reads();
    const text = await narrateFromReads(after, before, null);
    expect(text).toBe('林川位于走廊。林川的精神值为10。周宁从走廊走到门厅。周宁的精神值为10。');
  });

  test('a fact-valid rephrase replaces the template and is reported as polished', async () => {
    const { before, after } = reads();
    const seen: RuleNarrationInput[] = [];
    const polisher: RuleNarrationPolisher = async (input) => {
      seen.push(input);
      return '林川位于走廊。林川的精神值为10。周宁从走廊来到门厅。周宁当前精神值是10。';
    };
    const events: RuleSessionEvent[] = [];
    const text = await narrateFromReads(after, before, polisher, (event) => events.push(event));
    expect(text).toBe('林川位于走廊。林川的精神值为10。周宁从走廊来到门厅。周宁当前精神值是10。');
    expect(seen).toHaveLength(1);
    expect(seen[0].pointId).toBe('point_1');
    expect(seen[0].perspective).toContain('主角视角');
    const narration = events.find((event) => event.kind === 'narration');
    expect(narration).toMatchObject({ kind: 'narration', polished: true, polishReason: null, pointId: 'point_1', version: 1 });
  });

  test('an invented clause is rejected and the template stands', async () => {
    const { before, after } = reads();
    const baseline = '林川位于走廊。林川的精神值为10。周宁从走廊走到门厅。周宁的精神值为10。';
    const polisher: RuleNarrationPolisher = async () => `${baseline}周宁捡起了盒子。`;
    const events: RuleSessionEvent[] = [];
    const text = await narrateFromReads(after, before, polisher, (event) => events.push(event));
    expect(text).toBe(baseline);
    const narration = events.find((event) => event.kind === 'narration');
    expect(narration).toMatchObject({ kind: 'narration', polished: false, polishReason: 'unknown_or_ambiguous_clause' });
  });

  test('a failing polisher keeps the template usable and emits the fallback', async () => {
    const { before, after } = reads();
    const baseline = '林川位于走廊。林川的精神值为10。周宁从走廊走到门厅。周宁的精神值为10。';
    const polisher: RuleNarrationPolisher = async () => {
      throw new Error('engine exploded');
    };
    const events: RuleSessionEvent[] = [];
    const text = await narrateFromReads(after, before, polisher, (event) => events.push(event));
    expect(text).toBe(baseline);
    expect(events.find((event) => event.kind === 'polishFallback')).toMatchObject({ kind: 'polishFallback', detail: 'Error: engine exploded' });
    expect(events.find((event) => event.kind === 'narration')).toMatchObject({ kind: 'narration', polished: false });
  });
});

describe('session guards', () => {
  const transport = () => {
    throw new Error('no transport call expected before a guard fires');
  };
  test('a recovered session refuses submit until its attach lands', async () => {
    const session = RuleWorldSession.createRecovered({
      transport: { execute: transport }, initial: structuredClone(SHORT_STATE) as never,
      policy: { routes: [], sanity: { minimum: 0, maximum: 10, effects: { strain: -2, recover: 1 }, milestones: {
        strain: { taskId: 't', goal: 'g', requiredLocationId: 'corridor', minimumElapsedSeconds: 1, personalityText: 'p' },
        recover: { taskId: 't2', goal: 'g2', requiredLocationId: 'corridor', minimumElapsedSeconds: 1, personalityText: 'p' } } } },
    }, 'world_short');
    expect(session.worldId).toBe('world_short');
    await expect(session.submit('走到门厅')).rejects.toThrow('rule_session_recovery_incomplete');
  });
});
