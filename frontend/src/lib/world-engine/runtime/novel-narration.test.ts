import { describe, expect, test } from 'vitest';
import { SHORT_STATE } from './b3-short-samples';
import type { WorldState } from '../types';
import type { CommittedRead } from './committed-narration';
import { narrateFromReads, type RuleNarrationPolisher, type RuleSessionEvent } from './rule-session';
import { buildNovelNarrationPrompt, validateNovelNarration } from './novel-narration';
import { projectCommittedNarration } from './committed-narration';

function fixture() {
  const before: CommittedRead = {
    pointId: 'root', previousPointId: null, version: 0, stateDigest: 'root',
    state: structuredClone(SHORT_STATE) as unknown as WorldState, timeAdvance: null, entityDeltas: {},
  };
  const after = structuredClone(before);
  Object.assign(after, {
    pointId: 'point1', previousPointId: 'root', version: 1, stateDigest: 'next',
    timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'second' } },
    entityDeltas: { person_c: { entityId: 'person_c', positionSet: { containerId: 'hall', slotId: null, relativeTo: null } } },
  });
  after.state.characters.person_c.position.containerId = 'hall';
  after.state.time = { ...after.state.time, dateTime: '2026-10-27T09:00:01' };
  return { before, after };
}

describe('novel narration integration', () => {
  test('prompt is grounded in before/delta/after, protagonist and committed facts', () => {
    const { before, after } = fixture();
    const packet = projectCommittedNarration(after, before);
    const prompt = buildNovelNarrationPrompt({
      pointId: after.pointId, before: before.state,
      after: after.state, delta: { timeAdvance: after.timeAdvance, entityDeltas: after.entityDeltas },
      perspective: '主角视角（林川）',
    }, packet, { index: 1 });
    expect(prompt).toContain('上回合状态');
    expect(prompt).toContain('本回合变化');
    expect(prompt).toContain('本回合状态');
    expect(prompt).toContain('林川');
    expect(prompt).toContain('周宁');
    expect(prompt).toContain('门厅');
    expect(prompt).not.toContain('逐字复制');
  });

  test('natural prose is accepted without demanding static sanity values', async () => {
    const { before, after } = fixture();
    const text = '走廊里的灯光落在林川脚边。周宁从走廊走到门厅，停下回头望了一眼。';
    const packet = projectCommittedNarration(after, before);
    expect(validateNovelNarration(packet, text).accepted).toBe(true);
    const events: RuleSessionEvent[] = [];
    const polisher: RuleNarrationPolisher = async () => ({ text, mode: 'novel' });
    expect(await narrateFromReads(after, before, polisher, (event) => events.push(event))).toBe(text);
    expect(events.find((event) => event.kind === 'narration')).toMatchObject({ polished: true, attempts: 1 });
  });

  test('reversed movement is rejected and the stable template is used', async () => {
    const { before, after } = fixture();
    const text = '周宁从门厅走到走廊。';
    const packet = projectCommittedNarration(after, before);
    expect(validateNovelNarration(packet, text).accepted).toBe(false);
    const polisher: RuleNarrationPolisher = async () => ({ text, mode: 'novel' });
    const events: RuleSessionEvent[] = [];
    const rendered = await narrateFromReads(after, before, polisher, (event) => events.push(event));
    expect(rendered).toContain('周宁从走廊走到门厅');
    expect(events.find((event) => event.kind === 'narration')).toMatchObject({ polished: false, attempts: 2 });
  });

  test('empty text and omitted changed movement cannot overwrite committed narration', () => {
    const { before, after } = fixture();
    const packet = projectCommittedNarration(after, before);
    expect(validateNovelNarration(packet, ' ').accepted).toBe(false);
    expect(validateNovelNarration(packet, '走廊里一片安静。').reason).toBe('missing_changed_fact');
    expect(validateNovelNarration(packet, '周宁从走廊走到门厅，随后砸碎了窗玻璃。').accepted).toBe(false);
  });
});
