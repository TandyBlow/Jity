import { describe, expect, it } from 'vitest';
import { SHORT_STATE } from '../runtime/b3-short-samples';
import type { InitialState } from '../types';
import { instructNarrationInput } from './prompt';
import { buildInitialState } from './state';

describe('instruct narration input', () => {
  it('drops an action place the point never moved to', () => {
    const state = buildInitialState(structuredClone(SHORT_STATE.initial) as unknown as InitialState);
    const { brief } = instructNarrationInput(
      null, {}, state, 'person_c',
      '我在门厅的长椅旁等一会儿，听走廊那边的声音。',
      '周宁：在门厅的长椅旁等一会儿。；林川：看了他一眼。',
    );
    // The committed position is 走廊; 门厅 was only the player's intent.
    // The corridor's background may mention the hall; the action and its
    // repeated result must not carry the unexecuted place.
    expect(brief).not.toMatch(/玩家这回合让周宁做的事：[^。]*门厅/u);
    expect(brief).not.toContain('周宁：在门厅');
    expect(brief).toContain('周宁现在在走廊');
    expect(brief).toContain('听走廊那边的声音');
    expect(brief).toContain('林川：看了他一眼');
  });
});
