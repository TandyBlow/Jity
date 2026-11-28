import { describe, expect, it } from 'vitest';
import { SHORT_STATE } from '../runtime/b3-short-samples';
import type { InitialState } from '../types';
import { instructNarrationInput } from './prompt';
import { rulesNarration } from './rules-narration';
import { buildInitialState } from './state';

function narrate(previousSentences?: string[]) {
  const state = buildInitialState(structuredClone(SHORT_STATE.initial) as unknown as InitialState);
  const resultsText = '周宁：把枪放在桌上。（没有成功）；林川：看了他一眼。（达到目的）';
  const { sentences } = instructNarrationInput(null, {}, state, 'person_c', '我把枪放在桌上', resultsText);
  const text = rulesNarration({
    sentences, resultsText, previousSentences,
    names: Object.values(state.initial.characters).map((entry) => String(entry.name ?? '')),
    protagonist: '周宁',
  });
  return { sentences, text };
}

describe('rules narration candidate', () => {
  it('writes every settlement result with its outcome label', () => {
    const { text } = narrate();
    expect(text).toContain('周宁把枪放在桌上，却没有成功');
    expect(text).toContain('林川看了他一眼');
    expect(text).not.toContain('（没有成功）');
    expect(text).toContain('现在在走廊');
  });

  it('drops facts the previous point already carried', () => {
    const { sentences, text } = narrate();
    const second = rulesNarration({
      sentences, resultsText: '周宁：把枪放在桌上。（没有成功）',
      previousSentences: sentences,
      names: ['周宁', '林川'], protagonist: '周宁',
    });
    // The anchor and the result survive; the repeated item sentence does not.
    expect(second).toContain('现在在走廊');
    expect(second).toContain('却没有成功');
    expect(second).not.toContain('屋里有');
    expect(second.length).toBeLessThan(text.length);
  });
});
