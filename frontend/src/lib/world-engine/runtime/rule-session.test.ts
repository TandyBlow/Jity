import { describe, expect, test } from 'vitest';
import { SHORT_STATE } from './b3-short-samples';
import type { WorldState } from '../types';
import type { CommittedRead } from './committed-narration';
import { narrateFromReads, buildCommandPlan, RuleWorldSession, type PolishAttempt, type RuleNarrationInput, type RuleNarrationPolisher, type RuleSessionEvent } from './rule-session';

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

// 2026-10-28 复核后模板先述本点时间推进（narrateFromReads 传入 after.timeAdvance）。
const BASELINE = '约一秒过去了。林川位于走廊。林川的精神值为10。周宁从走廊走到门厅。周宁的精神值为10。';

describe('per-command identity rotation', () => {
  test('a second command mints a fresh allocation plan over the full slot set', () => {
    const order = Object.keys(SHORT_STATE.initial.characters).sort();
    const first = buildCommandPlan('holder_t', order, 1);
    const second = buildCommandPlan('holder_t', order, 2);
    expect(first.plan.allocationKey).toBe('holder_t_cmd1');
    expect(first.plan.slots.map((slot) => slot.slotKey)).toEqual(['advance', 'input', 'round', 'point', 'group:person_a', 'group:person_c']);
    expect(second.plan.allocationKey).toBe('holder_t_cmd2');
    expect(second.plan.allocationKey).not.toBe(first.plan.allocationKey);
    expect(second.slotKeys).toEqual(first.slotKeys);
  });
});

describe('narration decision: template baseline, judge-gated regeneration, fallback', () => {
  test('without a polisher the template is the narration', async () => {
    const { before, after } = reads();
    const text = await narrateFromReads(after, before, null);
    expect(text).toBe(BASELINE);
  });

  test('a fact-valid first candidate is adopted and carries the focused view', async () => {
    const { before, after } = reads();
    const seen: { input: RuleNarrationInput; focused: Record<string, unknown>; attempt: PolishAttempt }[] = [];
    const polisher: RuleNarrationPolisher = async (input, _packet, focused, attempt) => {
      seen.push({ input, focused: focused as Record<string, unknown>, attempt });
      return '林川位于走廊。林川的精神值为10。周宁从走廊来到门厅。周宁当前精神值是10。';
    };
    const events: RuleSessionEvent[] = [];
    const text = await narrateFromReads(after, before, polisher, (event) => events.push(event));
    expect(text).toBe('林川位于走廊。林川的精神值为10。周宁从走廊来到门厅。周宁当前精神值是10。');
    expect(seen).toHaveLength(1);
    expect(seen[0].input.pointId).toBe('point_1');
    expect(seen[0].input.perspective).toContain('主角视角');
    expect(seen[0].attempt).toEqual({ index: 1, previous: undefined });
    // The focused view carries only the allowed fact phrases — the judge
    // gate's contract, not the full states.
    const facts = seen[0].focused.facts as { id: string; allowedPhrases: string[] }[];
    expect(facts).toHaveLength(4);
    expect(facts[0]).toMatchObject({ id: 'person_a:position' });
    expect(facts.some((fact) => fact.allowedPhrases.includes('周宁从走廊走到门厅'))).toBe(true);
    expect(seen[0].focused).not.toHaveProperty('before');
    const narration = events.find((event) => event.kind === 'narration');
    expect(narration).toMatchObject({ kind: 'narration', polished: true, polishReason: null, attempts: 1 });
  });

  test('a rejected candidate regenerates once with feedback before the template stands', async () => {
    const { before, after } = reads();
    const attempts: PolishAttempt[] = [];
    const polisher: RuleNarrationPolisher = async (_input, _packet, _focused, attempt) => {
      attempts.push(attempt);
      if (attempt.index === 1) return `${BASELINE}周宁捡起了盒子。`; // invented clause
      return '林川位于走廊。林川的精神值为10。周宁从走廊来到门厅。周宁当前精神值是10。'; // valid retry
    };
    const events: RuleSessionEvent[] = [];
    const text = await narrateFromReads(after, before, polisher, (event) => events.push(event));
    expect(text).toBe('林川位于走廊。林川的精神值为10。周宁从走廊来到门厅。周宁当前精神值是10。');
    expect(attempts).toEqual([
      { index: 1, previous: undefined },
      { index: 2, previous: { text: `${BASELINE}周宁捡起了盒子。`, reason: 'unknown_or_ambiguous_clause' } },
    ]);
    const narration = events.find((event) => event.kind === 'narration');
    expect(narration).toMatchObject({ kind: 'narration', polished: true, attempts: 2 });
  });

  test('both candidates rejected → template stands with the final reason', async () => {
    const { before, after } = reads();
    const polisher: RuleNarrationPolisher = async () => `${BASELINE}周宁捡起了盒子。`;
    const events: RuleSessionEvent[] = [];
    const text = await narrateFromReads(after, before, polisher, (event) => events.push(event));
    expect(text).toBe(BASELINE);
    const narration = events.find((event) => event.kind === 'narration');
    expect(narration).toMatchObject({ kind: 'narration', polished: false, polishReason: 'unknown_or_ambiguous_clause', attempts: 2 });
  });

  test('a null polisher (experiment off) keeps the template with no fallback event', async () => {
    const { before, after } = reads();
    const polisher: RuleNarrationPolisher = async () => null;
    const events: RuleSessionEvent[] = [];
    const text = await narrateFromReads(after, before, polisher, (event) => events.push(event));
    expect(text).toBe(BASELINE);
    expect(events.find((event) => event.kind === 'narration')).toMatchObject({ kind: 'narration', polished: false, polishReason: null, attempts: 0 });
    expect(events.find((event) => event.kind === 'polishFallback')).toBeUndefined();
  });

  test('a failing polisher keeps the template usable and emits the fallback', async () => {
    const { before, after } = reads();
    const polisher: RuleNarrationPolisher = async () => {
      throw new Error('engine exploded');
    };
    const events: RuleSessionEvent[] = [];
    const text = await narrateFromReads(after, before, polisher, (event) => events.push(event));
    expect(text).toBe(BASELINE);
    expect(events.find((event) => event.kind === 'polishFallback')).toMatchObject({ kind: 'polishFallback', detail: 'Error: engine exploded' });
    expect(events.find((event) => event.kind === 'narration')).toMatchObject({ kind: 'narration', polished: false, attempts: 0 });
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
