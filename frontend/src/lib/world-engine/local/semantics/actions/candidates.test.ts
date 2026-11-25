import { describe, expect, it } from 'vitest';
import { buildScene } from './scene';
import { buildTestWorld } from './fixtures';
import { behaviorCandidates } from './candidates';

describe('behavior candidates', () => {
  it('generates a move candidate from a movement goal', () => {
    const state = buildTestWorld();
    state.characters.ally.tasks.task_ally_watch.goal = '去书房查看情况';
    const rows = behaviorCandidates(buildScene(state, 'ally'), state);
    expect(rows.some((row) => row.category === 'move' && row.text.includes('书房'))).toBe(true);
  });
  it('generates item candidates only for visible items', () => {
    const state = buildTestWorld();
    state.characters.ally.tasks.task_ally_watch.goal = '查看短刀';
    const rows = behaviorCandidates(buildScene(state, 'ally'), state);
    expect(rows.some((row) => row.category === 'observe' && row.text.includes('短刀'))).toBe(true);
    expect(rows.some((row) => row.itemIds.includes('knife'))).toBe(true);
  });
  it('does not invent an assist candidate without an item', () => {
    const state = buildTestWorld();
    state.characters.ally.tasks.task_ally_watch.goal = '帮助路明非';
    const rows = behaviorCandidates(buildScene(state, 'ally'), state);
    expect(rows.some((row) => row.category === 'assist')).toBe(false);
  });
});
