import { describe, expect, it } from 'vitest';
import { SHORT_STATE } from '../runtime/b3-short-samples';
import type { InitialState } from '../types';
import { instructNarrationInput } from './prompt';
import { rulesNarration } from './rules-narration';
import { buildInitialState } from './state';

function narrate() {
  const state = buildInitialState(structuredClone(SHORT_STATE.initial) as unknown as InitialState);
  const resultsText = '周宁：把枪放在桌上。（没有成功）；林川：看了他一眼。（达到目的）';
  const { sentences } = instructNarrationInput(null, {}, state, 'person_c', '我把枪放在桌上', resultsText);
  const text = rulesNarration({
    sentences, resultsText,
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

  it('writes state sentences once per turn but keeps repeated results', () => {
    const state = buildInitialState(structuredClone(SHORT_STATE.initial) as unknown as InitialState);
    const resultsText = '周宁：把枪放在桌上。（没有成功）';
    const { sentences } = instructNarrationInput(null, {}, state, 'person_c', '我把枪放在桌上', resultsText);
    const skip = new Set<string>();
    const input = {
      sentences, resultsText, skipFacts: skip,
      names: ['周宁', '林川'], protagonist: '周宁',
    };
    const first = rulesNarration(input);
    const second = rulesNarration(input);
    expect(first).toContain('现在在走廊');
    expect(first).toContain('却没有成功');
    // The scene is not repeated; the same event line still is.
    expect(second).not.toContain('现在在走廊');
    expect(second).not.toContain('屋里有');
    expect(second).toContain('却没有成功');
  });
});
