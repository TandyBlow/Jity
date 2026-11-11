import { describe, expect, it } from 'vitest';
import { verifyText } from './verify';
import type { SceneSkeleton } from './types';

/** A minimal scene with one structured result fact: 路明非 asks 诺诺 a question
 * and the settlement says the question was answered (completed). */
function scene(outcome: 'completed' | 'failed' | 'blocked' | 'unaffected', text = '诺诺答了路明非的问题。'): SceneSkeleton {
  return {
    anchor: { worldId: 'w', pointId: 'p', version: 1, stateDigest: 'd', previousPointId: 'root' },
    viewpoint: { id: 'lu', name: '路明非', locationId: 'lane', location: '服务巷', note: '', personality: '', sanity: 50 },
    time: null,
    place: { id: 'lane', name: '服务巷', note: '', parentName: null },
    present: [{ id: 'nono', name: '诺诺', note: '', viewpoint: false }],
    objects: [],
    facts: [{
      id: 'f:result:0', kind: 'result', mandatory: true, visibility: 'scene', text,
      structured: { actorId: 'nono', actor: '诺诺', action: '回答', targetId: 'lu', target: '路明非', outcome },
    }],
    licensed: { names: ['路明非', '诺诺'], locations: ['服务巷'], items: [], details: [], quotes: [text] },
    knowledge: { discoveredItemIds: [], visitedLocationIds: [], metCharacterIds: [] },
    priorText: null,
    inputText: null,
    previousAction: null,
    resultsText: null,
    worldNames: { characters: ['路明非', '诺诺'], locations: ['服务巷'], items: [] },
    hasSceneMaterial: true,
    timeOnly: false,
  };
}

const kinds = (text: string, skeleton: SceneSkeleton) => verifyText(text, {
  scene: skeleton, base: { anchor: skeleton.anchor, facts: [] }, minChars: 0, maxChars: 1200,
}).issues.map((issue) => `${issue.severity}:${issue.kind}`);

describe('a structured result is checked by meaning, not wording', () => {
  it('accepts a faithful paraphrase that keeps actor, target and outcome', () => {
    const text = '路明非问了一句，诺诺回答了他，话很短。';
    expect(kinds(text, scene('completed'))).not.toContain('hard:result_semantics');
  });

  it('accepts a completed outcome written without the settled sentence', () => {
    const skeleton = scene('completed', '诺诺答了路明非的问题。');
    const text = '诺诺把答案说给路明非听，语气很淡。';
    expect(kinds(text, skeleton)).not.toContain('hard:result_semantics');
  });

  it('rejects a paraphrase that reverses a failed outcome into a success', () => {
    const skeleton = scene('failed', '诺诺没能回答路明非的问题。');
    const text = '诺诺回答了路明非的问题，说得很清楚。';
    const result = kinds(text, skeleton);
    expect(result).toContain('hard:result_semantics');
  });

  it('rejects a negative outcome written as success for the same actor', () => {
    const skeleton = scene('blocked', '诺诺被拦在巷口，没能回答。');
    const text = '诺诺回答了路明非的问题。';
    expect(kinds(text, skeleton)).toContain('hard:result_semantics');
  });

  it('keeps an undecidable free-text result flagged for manual reading, not auto-passed', () => {
    const skeleton = scene('completed', '诺诺答了路明非的问题。');
    delete (skeleton.facts[0] as { structured?: unknown }).structured;
    const result = verifyText('路明非问了一句，诺诺回答了他，话很短。', {
      scene: skeleton, base: { anchor: skeleton.anchor, facts: [] }, minChars: 0, maxChars: 1200,
    });
    // Without structured fields the verifier still wants the settled sentence.
    expect(result.issues.map((issue) => issue.kind)).toContain('fact_missing');
  });
});

import { settledViolationsFromScene } from '../../narration-generation/licensed-sense';

describe('settled scene states are wired into the constrained route', () => {
  const scene = {
    place: { name: '器材棚', note: '箱子里放着演习弹' },
    present: [{ name: '诺诺', note: '红发用发圈束在脑后' }],
    objects: [{ name: '弗里嘉演习弹', note: '在器材棚的箱子里' }, { name: '护目镜', note: '挂在胸前' }],
    viewpoint: { name: '路明非', note: '' },
  };

  it('an item in the shed is not in his hand', () => {
    const found = settledViolationsFromScene('弗里嘉演习弹在手中发烫。', scene, ['路明非', '诺诺']);
    expect(found.some((violation) => violation.detail.includes('弗里嘉演习弹'))).toBe(true);
  });

  it('a rule-board quote is not read as the narrator wearing goggles', () => {
    const found = settledViolationsFromScene('牌面写明：护目镜必须戴好。', scene, ['路明非', '诺诺']);
    expect(found).toHaveLength(0);
  });
});
