import { describe, expect, it } from 'vitest';
import { validateNarration, visibleEntityNames } from './game-model';
import { SHORT_STATE } from '../runtime/b3-short-samples';
import type { WorldState } from '../types';

const state = (): WorldState => structuredClone(SHORT_STATE) as unknown as WorldState;

describe('length alone does not reject a complete scene', () => {
  it('accepts a short but complete paragraph', () => {
    const after = state();
    const text = '周宁在门厅停下脚步，回头看了一眼身后的走廊。';
    const facts = text;
    const result = validateNarration(text, facts, after, after.protagonistId);
    expect(result).toEqual({ ok: true, reason: '' });
  });

  it('still rejects a near-empty fragment', () => {
    const after = state();
    const result = validateNarration('他停了一下。', '他停了一下。', after, after.protagonistId);
    expect(result.ok).toBe(false);
    expect(result.reason).toBe('too_short');
  });

  it('still rejects a field table even when long enough', () => {
    const after = state();
    const text = ['时间：一分钟', '地点：走廊', '人物：周宁', '周宁在门厅停下脚步，回头看了一眼走廊。'].join(String.fromCharCode(10));
    expect(validateNarration(text, text, after, after.protagonistId).reason).toBe('structure_dump');
  });
});

describe('names resolve against what the viewpoint can see', () => {
  it('accepts a worn item of a character present in the same container', () => {
    const after = state();
    // 林川 stands with 周宁 in the corridor and wears a red band. The band is
    // not in the brief, but it is visible to the viewpoint (aa30 case).
    after.initial.items.band = { id: 'band', name: '红色识别带', initialAppearance: '', initialPosition: null, initialKnowledge: [] } as never;
    after.items.band = { id: 'band', position: { containerId: 'person_a', slotId: 'slot_arm', relativeTo: null }, appearanceChanges: [] };
    const facts = '周宁和林川都在走廊。';
    expect(visibleEntityNames(after, after.protagonistId, facts).has('红色识别带')).toBe(true);
    expect(validateNarration('林川站在走廊里，红色识别带缠在她的左臂上。', facts, after, after.protagonistId).ok).toBe(true);
  });

  it('still rejects a name that is offscreen', () => {
    const after = state();
    after.initial.items.band = { id: 'band', name: '红色识别带', initialAppearance: '', initialPosition: null, initialKnowledge: [] } as never;
    // Worn by nobody visible: it stays out of the scene even if it is a world item.
    after.items.band = { id: 'band', position: { containerId: 'hall', slotId: null, relativeTo: null }, appearanceChanges: [] };
    const result = validateNarration('走廊尽头的箱子里放着那条红色识别带，没有人去动它。', '周宁在走廊。', after, after.protagonistId);
    expect(result.ok).toBe(false);
    expect(result.reason).toContain('unprojected_entity');
  });
});

// The independent fact gate previously returned null on a fatal violation, so
// the in-model writer/program replaced the model's prose. (NARRATION-BOUNDARY)
import { refusedCandidateDraft } from './game-model';

describe('a candidate refused by the independent gate keeps its prose', () => {
  it('returns the model text as a draft with its segments and no accepted timing', () => {
    const kept = refusedCandidateDraft({
      text: '路明非听见巷口传来枪声。',
      segments: [
        { id: 'open', kind: 'open', source: 'model', text: '路明非听见巷口传来枪声。' },
      ],
      candidateId: 'constrained', route: 'constrained', strategyVersion: 'v',
      beatCounts: { model: 1, program: 0 }, issues: [], timings: { totalMs: 1200, firstTokenMs: 300 },
      promptChars: 900, rejectedBy: 'independent_fact_gate', reasons: ['invented_event'],
    });
    expect(kept.text).toContain('枪声');
    expect(kept.segments?.[0].source).toBe('model');
    expect(kept.error).toContain('invented_event');
    expect(kept.promptChars).toBe(900);
  });
});
